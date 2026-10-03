"""Prior-season (carryover) features for V2, built with the frozen V1 builders.

For a row in season s the frozen KickerFeatureBuilder/TeamFeatureBuilder are
fed every completed game of season s-1 and queried as of the row's own
prediction cutoff. Their season-to-date output over s-1 is the prior-season
aggregate: identical definitions to V1, kicker history keyed by player (it
follows him across teams), offense keyed by the team and defense by the
opponent. The 82 V1 columns are never modified; carryover is a separate family.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from kickedge.current.sources import prepare_bundle
from kickedge.features import FeatureContext
from kickedge.features.kicker import KickerFeatureBuilder, instant
from kickedge.features.team import TeamFeatureBuilder
from kickedge.modeling.dataset import predictor_columns
from kickedge.modeling.preprocessing import NormalizePredictors

SOURCE = Path('data/features/environment/d0e256364dde3016c76f/kicker_game_features.parquet')
INPUTS = Path('data/features/kicker_inputs/125f3ca711124ac270c1/source.json')
DATASET_DIRECTORY = Path('data/v2/dataset')
KEYS = ('game_id', 'team', 'kicker_id')
DATASET_VERSION = 1

KICKER_CARRYOVER = {
    'kicker_prior_season_games': 'kicker_games_before',
    'kicker_prior_season_xpa': 'kicker_xpa_before',
    'kicker_prior_season_xpm': 'kicker_xpm_before',
    'kicker_prior_season_conversion_rate': 'kicker_xp_conversion_rate_before',
    'kicker_prior_season_xpm_per_game': 'kicker_xpm_per_game_before',
    'kicker_prior_season_xpa_per_game': 'kicker_xpa_per_game_before',
}
OFFENSE_CARRYOVER = {
    'offense_prior_season_points_per_game': 'offense_points_per_game_before',
    'offense_prior_season_touchdowns_per_game': 'offense_touchdowns_per_game_before',
    'offense_prior_season_td_per_drive': 'offense_td_per_drive_before',
    'offense_prior_season_red_zone_td_rate': 'offense_red_zone_td_rate_before',
    'offense_prior_season_epa_per_play': 'offense_epa_per_play_before',
    'offense_prior_season_success_rate': 'offense_success_rate_before',
}
DEFENSE_CARRYOVER = {
    'defense_prior_season_points_allowed_per_game': 'defense_points_allowed_per_game_before',
    'defense_prior_season_touchdowns_allowed_per_game': 'defense_touchdowns_allowed_per_game_before',
    'defense_prior_season_td_allowed_per_drive': 'defense_td_allowed_per_drive_before',
    'defense_prior_season_red_zone_td_rate_allowed': 'defense_red_zone_td_rate_allowed_before',
    'defense_prior_season_epa_allowed_per_play': 'defense_epa_allowed_per_play_before',
    'defense_prior_season_success_rate_allowed': 'defense_success_rate_allowed_before',
}
# Current-season sample size the carryover complements (same value as V1 kicker_games_before).
CURRENT = {'current_season_games_before': 'kicker_games_before'}
CARRYOVER_COLUMNS = [*KICKER_CARRYOVER, *OFFENSE_CARRYOVER, *DEFENSE_CARRYOVER, *CURRENT]
STRUCTURAL_TARGETS = ('xpa', 'xpm', 'team_pat_attempts', 'team_two_pt_attempts', 'team_tries')


def historical_sources(root=Path('.')):
    """The frozen historical source lock behind V1's feature materialization."""
    root = Path(root)
    inputs = json.loads((root/INPUTS).read_text(encoding='utf-8'))
    lock = json.loads((root/'data/processed'/inputs['inputs']['historical_build']/'source_lock.json').read_text(encoding='utf-8'))
    return lock['sources']


def season_games(root, season, sources=None, now=None):
    """Completed-game events of one season (7B prepare_bundle, verified and cached)."""
    now = now or datetime.now(timezone.utc)
    bundle = prepare_bundle(Path(root), int(season), sources if sources is not None else historical_sources(root), now=now)
    return bundle['games']


def _utc(value):
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.utcoffset() is None else value.astimezone(timezone.utc)
    return instant(value)


class PriorSeason:
    """Frozen builders fed every completed game of one season (the prior season)."""

    def __init__(self, season, games):
        self.season = int(season)
        self.kicker, self.team = KickerFeatureBuilder(), TeamFeatureBuilder()
        self.last_event = None
        for game in games:
            if game['season'] != self.season:
                raise ValueError('Prior-season events must all belong to the prior season')
            source = game['source']
            for row in game['kickers']:
                self.kicker.observe(row | {'kickoff': source['actual_kickoff']}, row, source)
            self.team.observe(game['teams'], source)
            end = instant(source['last_event'])
            self.last_event = end if self.last_event is None else max(self.last_event, end)

    def features(self, row):
        """Carryover for one target row (season = prior season + 1), gated at its cutoff."""
        if int(row['season']) != self.season + 1:
            raise ValueError('Carryover uses only the immediately preceding season')
        kickoff, cutoff = _utc(row['kickoff']), _utc(row['prediction_cutoff'])
        if self.last_event is not None and self.last_event >= cutoff:
            raise ValueError('Prior season not completed before the target cutoff')
        context = FeatureContext(row['game_id'], row['team'], row['opponent'], row['kicker_id'], kickoff, cutoff, self.season)
        kicker = self.kicker.build(context)
        team = self.team.build({'game_id': row['game_id'], 'team': row['team'], 'opponent': row['opponent'],
                                'season': self.season, 'prediction_cutoff': cutoff.isoformat()})
        for entry in kicker['feature_provenance']['history']:
            if instant(entry['available_at']) > cutoff or instant(entry['kickoff']) >= kickoff:
                raise ValueError('Carryover history after the target cutoff')
        out = {name: kicker[source] for name, source in KICKER_CARRYOVER.items()}
        if not out['kicker_prior_season_games']:
            # No prior-season games: totals are explicitly unknown, not zero.
            out.update(kicker_prior_season_xpa=None, kicker_prior_season_xpm=None)
        out.update({name: team[source] for name, source in OFFENSE_CARRYOVER.items()})
        out.update({name: team[source] for name, source in DEFENSE_CARRYOVER.items()})
        return out


def structural_targets(games):
    """Outcome columns used only to fit the structural challenger (never predictors)."""
    rows = {}
    for game in games:
        tries = {r['team']: r for r in game['conversions']}
        for k in game['kickers']:
            conversion = tries.get(k['team'], {})
            pat, two = conversion.get('team_xpa'), conversion.get('two_pt_attempts')
            rows[k['game_id'], k['team'], k['kicker_id']] = {
                'xpa': k.get('xpa'), 'team_pat_attempts': pat, 'team_two_pt_attempts': two,
                'team_tries': pat + two if pat is not None and two is not None else None}
    return rows


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def load_rows(path=SOURCE, seasons=(2016, 2025)):
    """Eligible V1 rows (2016–2025 only, filtered in SQL) with identity and timing."""
    low, high = seasons
    if high > 2025:
        raise ValueError('Development rows end in 2025; 2026 is a forward evaluation only')
    columns = predictor_columns()
    selected = [*KEYS, 'opponent', 'kickoff', 'prediction_cutoff', *columns, 'xpm']
    projection = ', '.join('"' + name + '"' for name in selected)
    with duckdb.connect() as con:
        frame = con.execute(
            f'SELECT {projection} FROM read_parquet(?) WHERE eligible_for_phase_4_training IS TRUE '
            'AND season BETWEEN ? AND ? ORDER BY season, game_id, team, kicker_id', [str(path), low, high]).fetchdf()
    frame[columns] = NormalizePredictors().transform(frame[columns])
    return frame


def add_carryover(rows, events_by_season):
    """Attach carryover and structural targets; events_by_season maps season -> games."""
    out = rows.copy()
    priors, targets = {}, {}
    records = []
    for index, row in out.iterrows():
        season = int(row['season'])
        if season - 1 not in priors:
            priors[season - 1] = PriorSeason(season - 1, events_by_season[season - 1])
        if season not in targets:
            targets[season] = structural_targets(events_by_season[season])
        features = priors[season - 1].features(row)
        features['current_season_games_before'] = row['kicker_games_before']
        target = targets[season].get((row['game_id'], row['team'], row['kicker_id']), {})
        features.update({name: target.get(name) for name in ('xpa', 'team_pat_attempts', 'team_two_pt_attempts', 'team_tries')})
        records.append(features)
    extra = pd.DataFrame.from_records(records, index=out.index)
    for name in CARRYOVER_COLUMNS:
        out[name] = pd.to_numeric(extra[name], errors='raise').astype(float)
    for name in ('xpa', 'team_pat_attempts', 'team_two_pt_attempts', 'team_tries'):
        out[name] = pd.to_numeric(extra[name], errors='raise').astype(float)
    return out


def build_dataset(root=Path('.'), output_directory=DATASET_DIRECTORY, *, now=None):
    """Reproducible V2 development dataset 2016–2025 with lineage and content hash."""
    root = Path(root)
    sources = historical_sources(root)
    rows = load_rows(root/SOURCE)
    seasons = sorted(set(rows.season.astype(int)))
    events = {s: season_games(root, s, sources, now) for s in sorted({*seasons, *(s - 1 for s in seasons)})}
    dataset = add_carryover(rows, events)
    validate_dataset(dataset)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/'dataset.parquet'
    stored = dataset.drop(columns=['kickoff', 'prediction_cutoff']).assign(
        kickoff=dataset.kickoff.astype(str), prediction_cutoff=dataset.prediction_cutoff.astype(str))
    with duckdb.connect() as con:
        con.register('v2', stored)
        con.execute('COPY (SELECT * FROM v2 ORDER BY season, game_id, team, kicker_id) TO ? (FORMAT PARQUET)', [str(path)])
    package = Path(__file__).resolve().parents[1]
    metadata = {'dataset_version': DATASET_VERSION, 'rows': len(dataset), 'seasons': seasons,
                'source_sha256': _sha256(root/SOURCE), 'source_path': SOURCE.as_posix(),
                'content_sha256': content_hash(dataset),
                'code_sha256': {name: _sha256(package/name) for name in (
                    'v2/carryover.py', 'features/kicker.py', 'features/team.py', 'current/sources.py')},
                'carryover_columns': CARRYOVER_COLUMNS, 'v1_predictors': predictor_columns(),
                'null_counts': {name: int(dataset[name].isna().sum()) for name in CARRYOVER_COLUMNS},
                'policy': 'Prior season s-1 only, every contributing game completed and released before the '
                          'row cutoff; kicker history keyed by player, offense by team, defense by opponent; '
                          'V1 82 predictors unchanged; no season after 2025 read.'}
    (directory/'metadata.json').write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return dataset, metadata


def content_hash(frame):
    """Order-independent content hash of the modelling columns (reproducibility check)."""
    columns = [*KEYS, 'season', *predictor_columns(), *CARRYOVER_COLUMNS, 'xpm', 'xpa',
               'team_pat_attempts', 'team_two_pt_attempts', 'team_tries']
    ordered = frame.sort_values(list(KEYS))[columns].reset_index(drop=True)
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def validate_dataset(frame):
    if frame.duplicated(list(KEYS)).any():
        raise ValueError('Duplicate dataset row')
    seasons = frame.season.astype(int)
    if seasons.min() < 2016 or seasons.max() > 2025:
        raise ValueError('Development dataset must stay within 2016–2025')
    no_prior = frame.kicker_prior_season_games.eq(0)
    if frame.loc[no_prior, ['kicker_prior_season_xpa', 'kicker_prior_season_xpm',
                            'kicker_prior_season_conversion_rate']].notna().any().any():
        raise ValueError('Kickers without a prior season must have NULL prior-season statistics')
    if not np.array_equal(frame.current_season_games_before.to_numpy(), frame.kicker_games_before.to_numpy()):
        raise ValueError('current_season_games_before must equal the V1 season-to-date count')
    return frame


def load_dataset(directory=DATASET_DIRECTORY):
    path = Path(directory)/'dataset.parquet'
    with duckdb.connect() as con:
        frame = con.execute('SELECT * FROM read_parquet(?) ORDER BY season, game_id, team, kicker_id', [str(path)]).fetchdf()
    columns = predictor_columns()
    frame[columns] = NormalizePredictors().transform(frame[columns])
    return validate_dataset(frame)
