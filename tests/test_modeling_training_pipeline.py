"""End-to-end synthetic evidence that holdout changes cannot affect fitting."""
import json

import duckdb
import joblib
import numpy as np
import pandas as pd

from kickedge.modeling.dataset import load_split, predictor_columns
from kickedge.modeling.train import run_training
from kickedge.modeling.count_models import CANDIDATES, CountModel
import kickedge.modeling.train as training


def synthetic_frame():
    rows = 100
    # Constant predictors prevent invented signal in this blind-guard test.
    frame = pd.DataFrame({name: np.ones(rows) for name in predictor_columns()})
    frame['season'] = [2016 + i % 8 for i in range(80)] + [2024] * 16 + [2025] * 4
    frame['game_type'] = 'REG'
    frame['game_id'] = [f'game-{i:04d}' for i in range(rows)]
    frame['team'] = 'BUF'
    frame['kicker_id'] = 'synthetic-kicker'
    frame['eligible_for_phase_4_training'] = True
    frame['xpm'] = [i % 4 for i in range(96)] + [-999] * 4
    for name in predictor_columns():
        if name not in ('season', 'game_type'):
            frame.loc[frame.season == 2025, name] = np.nan
    return frame


def write_fixture(path, frame):
    with duckdb.connect() as con:
        con.register('synthetic', frame)
        con.execute('COPY synthetic TO ? (FORMAT PARQUET)', [str(path)])


def test_training_roundtrip_and_holdout_mutation(tmp_path, capsys, monkeypatch):
    stage = {'refit': False, 'fits': 0, 'evaluations': 0}
    original_fit, original_evaluate = CountModel.fit, training.evaluate

    def guarded_fit(self, x, y, *, refit=False):
        if refit:
            assert stage['fits'] == len(CANDIDATES) + 1  # includes reproducibility fit
            assert stage['evaluations'] == len(CANDIDATES)
            assert set(x.season) == set(range(2016, 2025))
            stage['refit'] = True
        else:
            assert not stage['refit']
            assert set(x.season) == set(range(2016, 2024))
        stage['fits'] += 1
        return original_fit(self, x, y, refit=refit)

    def guarded_evaluate(y, means, seasons):
        assert not stage['refit'], 'Refitted model must never be evaluated for selection'
        assert set(seasons) == {2024}
        stage['evaluations'] += 1
        return original_evaluate(y, means, seasons)

    monkeypatch.setattr(CountModel, 'fit', guarded_fit)
    monkeypatch.setattr(training, 'evaluate', guarded_evaluate)

    def check_artifacts(directory, metadata):
        saved_metadata = json.loads((directory / 'metadata.json').read_text())
        for filename, seasons_key, rows_key in (
            ('selection_model.joblib', 'train_seasons', 'selection_rows'),
            ('model.joblib', 'refit_seasons', 'refit_rows'),
        ):
            model = joblib.load(directory / filename)
            assert model.fit_seasons_ == saved_metadata[seasons_key] == metadata[seasons_key]
            assert model.fit_row_count_ == saved_metadata[rows_key] == metadata[rows_key]
            assert model.config == saved_metadata['selected'] == metadata['selected']
        assert stage['fits'] == len(CANDIDATES) + 2
        assert stage['evaluations'] == len(CANDIDATES)

    source = tmp_path / 'synthetic.parquet'
    frame = synthetic_frame()
    write_fixture(source, frame)
    first_dir = tmp_path / 'first'
    report = run_training(source, first_dir, tmp_path / 'report-first')
    output = capsys.readouterr().out
    assert output.index('target_summary_before_fit') < output.index('"model"')
    assert report['validation_season'] == 2024
    assert report['target_summary']['train_2016_2023']['count'] == 80
    assert report['target_summary']['validation_2024']['count'] == 16
    assert report['refit_rows'] == 96
    assert report['holdout_2025_rows_schema_only'] == 4
    assert report['holdout_2025_labels_loaded'] is False
    assert report['holdout_2025_evaluated'] is False
    assert report['features'] == predictor_columns()
    assert len(report['features']) == 82
    assert all(metrics['nll'] >= 0 for metrics in report['metrics_2024'].values())
    past, _ = load_split(source, 'refit')
    loaded = joblib.load(first_dir / 'model.joblib')
    predictions = loaded.predict(past)
    validation, _ = load_split(source, 'validation')
    selection_predictions = joblib.load(first_dir / 'selection_model.joblib').predict(validation)
    check_artifacts(first_dir, report)
    assert np.isfinite(predictions).all()
    assert (predictions > 0).all()
    assert json.loads((first_dir / 'metadata.json').read_text())['refit_rows'] == 96

    blind = frame.season == 2025
    frame.loc[blind, 'xpm'] = -1234567
    frame.loc[blind, 'game_type'] = 'POISON_CATEGORY'
    for name in predictor_columns():
        if name not in ('season', 'game_type'):
            frame.loc[blind, name] = 1234567
    mutated = tmp_path / 'mutated.parquet'
    write_fixture(mutated, frame)
    second_dir = tmp_path / 'second'
    stage.update(refit=False, fits=0, evaluations=0)
    other = run_training(mutated, second_dir, tmp_path / 'report-second')
    assert other['target_summary'] == report['target_summary']
    assert other['metrics_2024'] == report['metrics_2024']
    assert other['selected'] == report['selected']
    assert other['refit_rows'] == report['refit_rows']
    np.testing.assert_array_equal(joblib.load(second_dir / 'model.joblib').predict(past), predictions)

    check_artifacts(second_dir, other)
    np.testing.assert_array_equal(joblib.load(second_dir / 'selection_model.joblib').predict(validation), selection_predictions)
