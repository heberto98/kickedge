"""Historical, outcome-based diagnosis using strictly temporal V1-style clones.

The reader filters seasons in SQL before projecting outcomes. This module never
loads or writes a V1 artifact and never reads live analyses or market quotes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import poisson

from kickedge.modeling.count_models import CANDIDATES, CountModel
from kickedge.modeling.dataset import predictor_columns
from kickedge.modeling.preprocessing import NormalizePredictors
from kickedge.validation.statistics import reliability, score_rows


SOURCE = Path('data/features/environment/d0e256364dde3016c76f/kicker_game_features.parquet')
AUDIT_DIRECTORY = Path('data/v2/audit')
EVALUATION_YEARS = tuple(range(2020, 2026))
KEYS = ('game_id', 'team', 'kicker_id')
AUDIT_SCHEMA_VERSION = 1


def _integer_values(values, name, *, low, high):
    try:
        result = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid {name}') from exc
    if (result.ndim != 1 or not np.isfinite(result).all()
            or (result != np.floor(result)).any() or (result < low).any() or (result > high).any()):
        raise ValueError(f'Invalid {name}; expected integers from {low} through {high}')
    return result.astype(int)


def validate_development(frame):
    """Reject unapproved input partitions before any fitting or scoring."""
    if not isinstance(frame, pd.DataFrame) or not len(frame) or frame.columns.has_duplicates:
        raise ValueError('Development data must be a nonempty frame with unique columns')
    required = {*KEYS, *predictor_columns(), 'xpm'}
    if not required <= set(frame.columns):
        raise ValueError('Invalid development schema: missing ' + ', '.join(sorted(required - set(frame.columns))))
    _integer_values(frame.season, 'development season', low=2016, high=2025)
    _integer_values(frame.week, 'week', low=1, high=30)
    if ('eligible_for_phase_4_training' in frame
            and not frame.eligible_for_phase_4_training.fillna(False).eq(True).all()):
        raise ValueError('Only eligible development rows are permitted')
    if frame[list(KEYS)].isna().any().any():
        raise ValueError('NULL identity key')
    if frame.duplicated(list(KEYS)).any():
        raise ValueError('Duplicate development row key')
    _integer_values(frame.xpm, 'target XPM', low=0, high=np.iinfo(np.int32).max)
    return frame


def load_development(path=SOURCE):
    """Load eligible 2016–2025 rows and exactly the existing 82 predictors.

    Identifiers and XPM are audit columns and never supplied as predictors.
    Future and ineligible targets are excluded by SQL before materialization.
    """
    columns = predictor_columns()
    selected = [*KEYS, *columns, 'xpm']
    projection = ', '.join('"' + name + '"' for name in selected)
    with duckdb.connect() as con:
        schema = {row[0] for row in con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(path)]).fetchall()}
        required = {*selected, 'eligible_for_phase_4_training'}
        if not required <= schema:
            raise ValueError('Invalid development schema: missing ' + ', '.join(sorted(required - schema)))
        frame = con.execute(
            f'SELECT {projection} FROM read_parquet(?) '
            'WHERE eligible_for_phase_4_training IS TRUE AND season BETWEEN 2016 AND 2025 '
            'ORDER BY season, game_id, team, kicker_id', [str(path)]).fetchdf()
    validate_development(frame)
    frame[columns] = NormalizePredictors().transform(frame[columns])
    return frame


def temporal_oof(frame, *, evaluation_years=EVALUATION_YEARS):
    """Refit diagnostic V1 clones only on seasons earlier than each fold.

    Hyperparameters are the frozen V1 GLM settings. The latest clone fits through
    2024 and predicts 2025. This is retrospective architectural diagnosis, not a
    newly blind selection process; V1's configuration was chosen previously.
    """
    validate_development(frame)
    years = _integer_values(evaluation_years, 'evaluation season', low=2020, high=2025)
    if not len(years) or len(set(years)) != len(years):
        raise ValueError('Evaluation seasons must be nonempty and unique')
    columns = predictor_columns()
    source = frame.sort_values(['season', *KEYS]).reset_index(drop=True)
    features = NormalizePredictors().transform(source[columns])
    output = []
    for year in sorted(years):
        train = source.season < year
        evaluation = source.season == year
        if not train.any():
            raise ValueError(f'No earlier training rows for evaluation season {year}')
        if not evaluation.any():
            raise ValueError(f'No evaluation rows for season {year}')
        model = CountModel(CANDIDATES[1]).fit(features.loc[train], source.loc[train, 'xpm'].to_numpy(), refit=True)
        values = model.predict(features.loc[evaluation])
        selected = [*KEYS, 'season', 'week', 'kicker_games_before',
                    'kicker_has_3_prior_games', 'kicker_has_5_prior_games', 'xpm']
        rows = source.loc[evaluation, selected].copy()
        rows['null_count'] = features.loc[evaluation].isna().sum(axis=1).to_numpy()
        rows['lambda'] = values
        rows['fold'] = int(year)
        rows['fold_train_min'] = int(source.loc[train, 'season'].min())
        rows['fold_train_max'] = int(source.loc[train, 'season'].max())
        rows['fold_train_count'] = int(train.sum())
        output.append(rows)
    return pd.concat(output, ignore_index=True)


def metrics(y, means):
    """Generic finite proper scores plus descriptive decile calibration."""
    rows = score_rows(y, means)
    if not all(np.isfinite(values).all() for values in rows.values()):
        raise ValueError('Nonfinite score')
    average = lambda values: math.fsum(float(value) for value in values) / len(values)
    result = {key: average(values) for key, values in rows.items() if key != 'squared_error'}
    result.update(count=len(rows['nll']), rmse=math.sqrt(average(rows['squared_error'])),
                  predicted_mean=average(means), observed_mean=average(y))
    targets, values = np.asarray(y, dtype=float), np.asarray(means, dtype=float)
    result['calibration'] = {f'ge_{threshold}': reliability(poisson.sf(threshold - 1, values), targets >= threshold)
                             for threshold in (2, 3, 4)}
    json.dumps(result, allow_nan=False)
    return result


def _validate_oof(frame):
    required = {*KEYS, 'season', 'week', 'kicker_games_before', 'kicker_has_3_prior_games',
                'kicker_has_5_prior_games', 'xpm', 'lambda', 'fold', 'fold_train_min',
                'fold_train_max', 'fold_train_count', 'null_count'}
    if not isinstance(frame, pd.DataFrame) or not len(frame) or not required <= set(frame.columns):
        raise ValueError('Invalid OOF schema')
    if frame[list(KEYS)].isna().any().any() or frame.duplicated(list(KEYS)).any():
        raise ValueError('Invalid or duplicate OOF identity key')
    seasons = _integer_values(frame.season, 'OOF season', low=2020, high=2025)
    train_max = _integer_values(frame.fold_train_max, 'training season', low=2016, high=2024)
    train_min = _integer_values(frame.fold_train_min, 'first training season', low=2016, high=2024)
    if (train_max >= seasons).any() or (train_min > train_max).any():
        raise ValueError('OOF training seasons must be strictly earlier than evaluation rows')
    if not np.array_equal(frame.fold.to_numpy(), seasons):
        raise ValueError('OOF fold must match evaluation season')
    _integer_values(frame.week, 'OOF week', low=1, high=30)
    _integer_values(frame.kicker_games_before, 'kicker history', low=0, high=100)
    _integer_values(frame.null_count, 'NULL count', low=0, high=82)
    _integer_values(frame.fold_train_count, 'training row count', low=1, high=np.iinfo(np.int32).max)
    for column in ('kicker_has_3_prior_games', 'kicker_has_5_prior_games'):
        _integer_values(frame[column], column, low=0, high=1)
    score_rows(frame.xpm, frame['lambda'])


def summarize_oof(frame):
    """Stratify a single validated OOF cohort, preserving probability deciles."""
    _validate_oof(frame)
    work = frame.copy()
    work['week_group'] = np.select([work.week <= 4, work.week <= 8], ['1-4', '5-8'], default='9+')
    work['kicker_history_group'] = np.select(
        [work.kicker_games_before == 0, work.kicker_games_before <= 2, work.kicker_games_before <= 4],
        ['0', '1-2', '3-4'], default='5+')
    work['null_bin'] = np.select([work.null_count == 0, work.null_count <= 20], ['0', '1-20'], default='21+')
    def grouped(column):
        return {str(int(key)) if isinstance(key, (float, int, np.number, bool)) else str(key):
                metrics(rows.xpm, rows['lambda'])
                for key, rows in work.groupby(column, sort=True, observed=True)}
    result = {'pooled': metrics(work.xpm, work['lambda']),
              'by_season': grouped('season'), 'by_fold': grouped('fold'),
              'by_week_group': grouped('week_group'), 'by_week': grouped('week'),
              'by_kicker_games_before': grouped('kicker_history_group'),
              'by_has_3_games': grouped('kicker_has_3_prior_games'),
              'by_has_5_games': grouped('kicker_has_5_prior_games'), 'by_null_bin': grouped('null_bin')}
    result['by_season_week_group'] = {
        str(int(year)): {str(group): metrics(rows.xpm, rows['lambda'])
                        for group, rows in season.groupby('week_group', sort=True, observed=True)}
        for year, season in work.groupby('season', sort=True, observed=True)}
    result['probability_deciles'] = {'all': deepcopy(result['pooled']['calibration'])}
    result['probability_deciles'].update({group: deepcopy(value['calibration'])
                                         for group, value in result['by_week_group'].items()})
    return result


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run_audit(source=SOURCE, output_directory=AUDIT_DIRECTORY, *, reuse=True, evaluation_years=EVALUATION_YEARS):
    """Persist exact predictions, summary, and lineage; reuse verified predictions."""
    source, directory = Path(source), Path(output_directory)
    years = [int(year) for year in _integer_values(evaluation_years, 'evaluation season', low=2020, high=2025)]
    identity = {'audit_schema_version': AUDIT_SCHEMA_VERSION, 'source_sha256': _sha256(source),
                'source_path': source.as_posix(), 'evaluation_years': years,
                'model_config': deepcopy(CANDIDATES[1]), 'predictor_columns': predictor_columns()}
    metadata_path, prediction_path = directory / 'metadata.json', directory / 'oof_predictions.parquet'
    if reuse and metadata_path.exists() and prediction_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if (all(metadata.get(key) == value for key, value in identity.items())
                and metadata.get('prediction_sha256') == _sha256(prediction_path)):
            with duckdb.connect() as con:
                predictions = con.execute('SELECT * FROM read_parquet(?)', [str(prediction_path)]).fetchdf()
            _validate_oof(predictions)
            if sorted(set(predictions.season.astype(int))) != sorted(years):
                raise ValueError('Cached OOF seasons do not match the requested folds')
            summary = summarize_oof(predictions)
            (directory / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n', encoding='utf-8')
            return predictions, summary, metadata
    development = load_development(source)
    predictions = temporal_oof(development, evaluation_years=years)
    summary = summarize_oof(predictions)
    directory.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.register('oof', predictions)
        con.execute('COPY oof TO ? (FORMAT PARQUET)', [str(prediction_path)])
    metadata = {**identity, 'created_at': datetime.now(timezone.utc).isoformat(),
                'development_seasons': sorted(set(development.season.astype(int))),
                'development_row_count': len(development), 'prediction_row_count': len(predictions),
                'prediction_sha256': _sha256(prediction_path),
                'excluded_seasons': 'All years after 2025 excluded before development outcome projection.',
                'folds': [{'evaluation_season': int(year), 'train_min': int(rows.fold_train_min.iloc[0]),
                           'train_max': int(rows.fold_train_max.iloc[0]), 'train_rows': int(rows.fold_train_count.iloc[0]),
                           'evaluation_rows': len(rows)} for year, rows in predictions.groupby('season')],
                'market_comparison': 'Not assessed here: no market quotes or live analyses read.',
                'diagnostic_limit': 'V1 architecture chosen previously; historical folds are retrospective diagnostics, not blind model selection.'}
    metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return predictions, summary, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output-directory', type=Path, default=AUDIT_DIRECTORY)
    parser.add_argument('--recompute', action='store_true')
    args = parser.parse_args()
    _, summary, metadata = run_audit(args.source, args.output_directory, reuse=not args.recompute)
    print(json.dumps({'metadata': metadata, 'pooled': summary['pooled'], 'by_week_group': summary['by_week_group']}, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
