"""Walk-forward V2 candidate evaluation, OOF-only calibration check and selection.

Selection rules were registered in docs/superpowers/plans/2026-10-03-kickedge-v2.md
before any candidate result. Every fold trains on seasons strictly before the
evaluated season; calibration factors are fitted only on earlier OOF predictions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from kickedge.modeling.dataset import predictor_columns
from .audit import metrics
from .models import STRUCTURAL_TARGETS, V2Model, feature_columns

EVALUATION_YEARS = tuple(range(2020, 2026))
KEYS = ('game_id', 'team', 'kicker_id')
STRATA = ('kicker_games_before', 'kicker_has_3_prior_games', 'kicker_has_5_prior_games')


def structural_frame(frame):
    """Structural targets from the dataset's outcome columns (fit only)."""
    if {'team_pat_attempts', 'team_two_pt_attempts'} <= set(frame.columns):
        return pd.DataFrame({'pat_attempts': frame.team_pat_attempts, 'two_pt_attempts': frame.team_two_pt_attempts,
                             'xpa': frame.xpa, 'xpm': frame.xpm})
    return frame[list(STRUCTURAL_TARGETS)]


def candidate_oof(frame, targets, config, years=EVALUATION_YEARS):
    """Predict each evaluation season with a model fitted only on earlier seasons."""
    columns = feature_columns(config)
    source = frame.reset_index(drop=True)
    targets = None if targets is None else pd.DataFrame(targets).reset_index(drop=True)
    output = []
    for year in sorted(years):
        train, evaluation = source.season < year, source.season == year
        if not train.any() or not evaluation.any():
            raise ValueError(f'Fold {year} needs earlier training rows and evaluation rows')
        model = V2Model(config).fit(source.loc[train, columns], source.loc[train, 'xpm'].to_numpy(),
                                    structural_targets=None if targets is None else targets.loc[train])
        rows = source.loc[evaluation, [*KEYS, 'season', 'week', *[c for c in STRATA if c in source], 'xpm']].copy()
        rows['null_count'] = source.loc[evaluation, predictor_columns()].isna().sum(axis=1).to_numpy()
        rows['lambda'] = model.predict(source.loc[evaluation, columns])
        rows['fold'] = int(year)
        rows['fold_train_min'] = int(source.loc[train, 'season'].min())
        rows['fold_train_max'] = int(source.loc[train, 'season'].max())
        rows['fold_train_count'] = int(train.sum())
        output.append(rows)
    return pd.concat(output, ignore_index=True)


def fit_lambda_calibration(oof, *, before_season):
    """Multiplicative lambda factor sum(y)/sum(lambda) from earlier OOF rows only."""
    rows = pd.DataFrame(oof)
    seasons = rows.season.astype(int)
    if (seasons > 2025).any():
        raise ValueError('Calibration never uses seasons after 2025')
    if (seasons >= before_season).any():
        raise ValueError('Calibration rows must precede the season it is applied to')
    if (rows.fold_train_max.astype(int) >= seasons).any():
        raise ValueError('Calibration requires out-of-fold predictions')
    factor = rows.xpm.sum() / rows['lambda'].sum()
    return {'factor': float(factor), 'fit_max_season': int(seasons.max()), 'fit_rows': len(rows)}


def _ece(y, means):
    calibration = metrics(y, means)['calibration']
    return float(np.mean([calibration[k]['ece'] for k in ('ge_2', 'ge_3', 'ge_4')]))


def _brier(m):
    return (m['brier_ge_2'] + m['brier_ge_3'] + m['brier_ge_4']) / 3


def calibration_check(oof, years=(2022, 2023, 2024, 2025)):
    """Rolling evaluation of the factor: fitted on OOF seasons < year, scored on year."""
    rows = []
    for year in years:
        history = oof[oof.season < year]
        current = oof[oof.season == year]
        fitted = fit_lambda_calibration(history, before_season=year)
        raw, adjusted = current['lambda'].to_numpy(), current['lambda'].to_numpy() * fitted['factor']
        a, b = metrics(current.xpm, raw), metrics(current.xpm, adjusted)
        rows.append({'season': year, 'factor': fitted['factor'], 'raw_nll': a['nll'], 'calibrated_nll': b['nll'],
                     'raw_rps': a['rps'], 'calibrated_rps': b['rps'], 'raw_brier': _brier(a), 'calibrated_brier': _brier(b),
                     'raw_ece': _ece(current.xpm, raw), 'calibrated_ece': _ece(current.xpm, adjusted)})
    table = pd.DataFrame(rows)
    pooled = {key: float(np.average(table[key], weights=[len(oof[oof.season == y]) for y in years]))
              for key in table.columns if key != 'season'}
    passed = (pooled['calibrated_nll'] <= pooled['raw_nll'] * .995 and pooled['calibrated_rps'] <= pooled['raw_rps'] * .995
              and pooled['calibrated_brier'] <= pooled['raw_brier'] and pooled['calibrated_ece'] <= pooled['raw_ece']
              and int((table.calibrated_nll < table.raw_nll).sum()) >= 3)
    return {'by_season': table.to_dict('records'), 'pooled': pooled, 'retained': bool(passed)}


def summarize(oof):
    """Pooled, per-season, week-group and history-group scores for one candidate."""
    work = oof.copy()
    work['week_group'] = np.select([work.week <= 4, work.week <= 8], ['1-4', '5-8'], default='9+')
    work['history_group'] = np.select([work.kicker_games_before == 0, work.kicker_games_before <= 2,
                                       work.kicker_games_before <= 4], ['0', '1-2', '3-4'], default='5+')
    def block(rows):
        m = metrics(rows.xpm, rows['lambda'])
        return {key: m[key] for key in ('count', 'nll', 'rps', 'brier_ge_2', 'brier_ge_3', 'brier_ge_4',
                                         'predicted_mean', 'observed_mean')} | {
            'brier_average': _brier(m), 'ece_average': float(np.mean([m['calibration'][k]['ece'] for k in ('ge_2', 'ge_3', 'ge_4')])),
            'bias_ge_2_pp': 100 * m['calibration']['ge_2']['bias']}
    return {'pooled': block(work),
            'by_season': {str(k): block(v) for k, v in work.groupby('season')},
            'by_week_group': {str(k): block(v) for k, v in work.groupby('week_group')},
            'by_history_group': {str(k): block(v) for k, v in work.groupby('history_group')}}


def selection(summaries, baseline='v1_style_glm_alpha_0.1', families=None):
    """Apply the registered rule to each candidate against the V1-style baseline."""
    base = summaries[baseline]
    results = {}
    for name, s in summaries.items():
        if name == baseline:
            continue
        p, b = s['pooled'], base['pooled']
        nll_gain = 1 - p['nll'] / b['nll']
        rps_gain = 1 - p['rps'] / b['rps']
        seasons_better = sum(s['by_season'][y]['nll'] < base['by_season'][y]['nll'] for y in base['by_season'])
        early, early_base = s['by_week_group']['1-4'], base['by_week_group']['1-4']
        required = .02 if (families or {}).get(name) in ('boost', 'structural') else .01
        checks = {'pooled_nll_gain': nll_gain >= required, 'pooled_rps_gain': rps_gain >= .01,
                  'brier_not_worse': p['brier_average'] - b['brier_average'] <= .002,
                  'nll_better_in_4_of_6_seasons': seasons_better >= 4,
                  'weeks_1_4_not_worse': early['nll'] <= early_base['nll'] and early['rps'] <= early_base['rps']}
        results[name] = {'nll_gain_pct': 100 * nll_gain, 'rps_gain_pct': 100 * rps_gain,
                         'brier_delta': p['brier_average'] - b['brier_average'], 'seasons_nll_better': seasons_better,
                         'weeks_1_4_nll_delta': early['nll'] - early_base['nll'], 'weeks_1_4_rps_delta': early['rps'] - early_base['rps'],
                         'required_nll_gain_pct': 100 * required, 'checks': checks, 'passes': all(checks.values())}
    winners = sorted((n for n, r in results.items() if r['passes']), key=lambda n: summaries[n]['pooled']['nll'])
    return {'candidates': results, 'selected': winners[0] if winners else baseline,
            'rule': 'Registered before results: >=1% pooled NLL and RPS gains (>=2% NLL for boosting/structural), '
                    'average threshold Brier not worse by >.002, NLL better in >=4/6 seasons, weeks 1-4 NLL/RPS not worse.'}

