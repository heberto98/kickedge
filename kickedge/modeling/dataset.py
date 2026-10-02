"""Explicit approved predictors and guarded historical parquet folds.

No public API can load 2025 targets. SQL filters season/eligibility before the
explicit predictor/target projection; stable identity keys are never predictors.
"""
from pathlib import Path

import duckdb
import numpy as np

from kickedge.features import load_contract

_FROZEN_COLUMNS = ('kicker_games_before', 'kicker_xpa_before', 'kicker_xpm_before', 'kicker_xp_conversion_rate_before', 'kicker_xpm_per_game_before', 'kicker_xpa_per_game_before', 'kicker_xpa_last_3', 'kicker_xpm_last_3', 'kicker_xp_conversion_last_3', 'kicker_xpm_per_game_last_3', 'kicker_xpa_last_5', 'kicker_xpm_last_5', 'kicker_xp_conversion_last_5', 'kicker_xpm_per_game_last_5', 'days_since_last_game', 'previous_game_xpa', 'previous_game_xpm', 'kicker_has_prior_game', 'kicker_has_3_prior_games', 'kicker_has_5_prior_games', 'kicker_low_sample_flag', 'offense_games_before', 'offense_points_per_game_before', 'offense_touchdowns_per_game_before', 'offense_drives_per_game_before', 'offense_td_per_drive_before', 'offense_red_zone_td_rate_before', 'offense_epa_per_play_before', 'offense_success_rate_before', 'offense_points_per_game_last_3', 'offense_touchdowns_per_game_last_3', 'offense_td_per_drive_last_3', 'offense_red_zone_td_rate_last_3', 'offense_epa_per_play_last_3', 'offense_success_rate_last_3', 'offense_points_per_game_last_5', 'offense_touchdowns_per_game_last_5', 'offense_td_per_drive_last_5', 'offense_red_zone_td_rate_last_5', 'offense_epa_per_play_last_5', 'offense_success_rate_last_5', 'defense_games_before', 'defense_points_allowed_per_game_before', 'defense_touchdowns_allowed_per_game_before', 'defense_drives_faced_per_game_before', 'defense_td_allowed_per_drive_before', 'defense_red_zone_td_rate_allowed_before', 'defense_epa_allowed_per_play_before', 'defense_success_rate_allowed_before', 'defense_points_allowed_per_game_last_3', 'defense_touchdowns_allowed_per_game_last_3', 'defense_td_allowed_per_drive_last_3', 'defense_red_zone_td_rate_allowed_last_3', 'defense_epa_allowed_per_play_last_3', 'defense_success_rate_allowed_last_3', 'defense_points_allowed_per_game_last_5', 'defense_touchdowns_allowed_per_game_last_5', 'defense_td_allowed_per_drive_last_5', 'defense_red_zone_td_rate_allowed_last_5', 'defense_epa_allowed_per_play_last_5', 'defense_success_rate_allowed_last_5', 'is_home', 'is_away', 'season', 'week', 'game_type', 'team_days_rest', 'opponent_days_rest', 'team_short_week_flag', 'opponent_short_week_flag', 'team_long_rest_flag', 'opponent_long_rest_flag', 'team_two_point_attempt_rate_before', 'team_two_point_attempts_before', 'team_two_point_attempt_rate_last_3', 'team_two_point_attempts_last_3', 'team_two_point_attempt_rate_last_5', 'team_two_point_attempts_last_5', 'team_has_3_prior_games', 'team_has_5_prior_games', 'opponent_has_3_prior_games', 'opponent_has_5_prior_games')
_SPLITS = {'train': (2016, 2023), 'validation': (2024, 2024), 'refit': (2016, 2024)}
_KEYS = ('game_id', 'team', 'kicker_id')


def predictor_columns():
    """Return a fresh ordered list, rejecting any changed or unapproved contract."""
    contract = load_contract()
    if tuple(contract['predictor_columns_through_phase_4']) != _FROZEN_COLUMNS:
        raise ValueError('Phase 5 frozen predictor contract changed')
    fields = {f['name']: f for f in contract['fields']}
    if len(fields) != len(contract['fields']):
        raise ValueError('Duplicate contract field')
    for name in _FROZEN_COLUMNS:
        field = fields[name]
        if (field.get('role') not in ('feature', 'context')
                or not field.get('implemented') or not field.get('predictive_input_allowed')
                or not field.get('historical_training_approved')
                or name in contract['phase_4_candidate_columns']):
            raise ValueError('Unapproved predictor: ' + name)
    return list(_FROZEN_COLUMNS)


def load_split(path: str | Path, split: str):
    """Return exactly 82 X columns and nonnegative integral XPM targets.

    Only train (2016–2023), validation (2024), and refit (2016–2024)
    are supported. Zero outcomes are retained, and targets never filter rows.
    """
    if not isinstance(split, str) or split not in _SPLITS:
        raise ValueError('Only train, validation and refit splits are allowed; 2025 is blind')
    columns = predictor_columns()
    low, high = _SPLITS[split]
    projection = ', '.join('"' + n + '"' for n in [*_KEYS, *columns, 'xpm'])
    with duckdb.connect() as con:
        schema = {r[0] for r in con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(path)]).fetchall()}
        required = {*_KEYS, *columns, 'xpm', 'eligible_for_phase_4_training'}
        if not required <= schema:
            raise ValueError('Invalid dataset schema: missing ' + ', '.join(sorted(required - schema)))
        frame = con.execute(
            f'SELECT {projection} FROM read_parquet(?) '
            'WHERE eligible_for_phase_4_training IS TRUE AND season BETWEEN ? AND ? '
            'ORDER BY game_id, team, kicker_id', [str(path), low, high]).fetchdf()
    if frame[list(_KEYS)].isna().any().any():
        raise ValueError('Invalid NULL identity key')
    if frame.duplicated(list(_KEYS)).any():
        raise ValueError('Duplicate model row key')
    try:
        y = frame['xpm'].to_numpy(dtype=float, na_value=np.nan)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid target') from exc
    if not np.isfinite(y).all() or (y < 0).any() or (y != np.floor(y)).any():
        raise ValueError('Invalid target: XPM must be finite nonnegative integers')
    from .preprocessing import NormalizePredictors
    x = NormalizePredictors().transform(frame.loc[:, columns])
    x.attrs['split'] = split
    x.attrs['seasons'] = sorted(int(value) for value in x.season.unique())
    return x, y


def holdout_schema_count(path: str | Path):
    """Inspect schema and 2025 count only; never project a holdout target."""
    with duckdb.connect() as con:
        schema = con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(path)]).fetchall()
        count = con.execute('SELECT count(*) FROM read_parquet(?) WHERE season = 2025', [str(path)]).fetchone()[0]
    return {'row_count': count, 'schema': [{'name': r[0], 'type': r[1]} for r in schema]}


holdout_info = holdout_schema_count
