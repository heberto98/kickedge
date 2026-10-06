"""Data freshness and local season monitoring snapshots for the frozen V1 model.

Monitoring only describes: what the verified nflverse source contains, how tracked
predictions performed, and how close the season is to the forward-validation size
preregistered for the V2 challenger. It never evaluates V2, refits or recalibrates.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path

from kickedge.current.auto_settlement import EXPECTED_END, completed_events
from kickedge.current.snapshot import digest
from kickedge.current.tracking import create_json

STALE_AFTER, TOO_STALE_AFTER = timedelta(hours=6), timedelta(hours=24)
CUTOFF_POLICY = ('Pregame cutoff = kickoff − 60 min; a completed game enters features only after a '
                 'conservative 24 h release gate.')
RELEASE = Path(__file__).resolve().parents[1]/'inference/release.json'
# The single 2026 forward evaluation (reports/v2_forward_2026_validation.md) is immutable.
FORWARD_REFERENCE = {'season': 2026, 'last_audit_rows': 84, 'threshold': 150,
                     'last_audit_revealed_at': '2026-10-03T21:26:53+00:00',
                     'report': 'reports/v2_forward_2026_validation.md'}
SNAPSHOTS = 'snapshots'


def model_identity():
    """The pinned V1 release (version and artifact SHA-256) the app verifies before inference."""
    release = json.loads(RELEASE.read_text(encoding='utf-8'))
    return {'name': 'KickEdge V1', 'version': release['version'], 'artifact_sha256': release['artifact_sha256']}


def _instant(value):
    return datetime.fromisoformat(value) if value else None


def freshness(bundle, now, *, fetched_at=None, failure=None):
    """What the source contains and how old it is; warnings never block analyses.

    ``bundle`` may be None when the source could not be loaded: then ``fetched_at``
    (from the cache manifest) and ``failure`` describe the last good capture.
    """
    warnings = []
    if bundle is not None:
        times = [s.get('fetched_at') for s in bundle.get('sources', []) if s.get('fetched_at')]
        fetched_at = min(times) if times else fetched_at
    if failure:
        warnings.append({'code': 'SOURCE_UNAVAILABLE', 'detail': failure})
    age = now - _instant(fetched_at) if fetched_at else None
    if age is not None and age > TOO_STALE_AFTER:
        warnings.append({'code': 'DATA_TOO_STALE', 'detail': 'NFL data is more than 24 h old.'})
    elif age is not None and age > STALE_AFTER:
        warnings.append({'code': 'SOURCE_OLDER_THAN_6H', 'detail': 'NFL data is more than 6 h old.'})
    out = {'season': bundle.get('season') if bundle else None, 'nfl_data_fetched_at': fetched_at,
           'age_hours': age.total_seconds() / 3600 if age is not None else None,
           'latest_completed_game': None, 'latest_completed_week': None, 'completed_games': None,
           'feature_cutoff_policy': CUTOFF_POLICY, 'model': model_identity(), 'warnings': warnings}
    if bundle is None:
        return out
    events = completed_events(bundle)
    if events:
        latest = max(events.values(), key=lambda g: g['source']['actual_kickoff'])
        out['latest_completed_game'] = {'game_id': latest['game_id'], 'kickoff': latest['source']['actual_kickoff']}
    weeks = defaultdict(set)
    for game in bundle.get('schedules', []):
        weeks[game['week']].add(game['game_id'])
    done = [week for week, ids in weeks.items() if ids and ids <= set(events)]
    out['latest_completed_week'] = max(done) if done else None
    out['completed_games'] = len(events)
    missing = sorted(g['game_id'] for g in bundle.get('schedules', []) if g.get('scheduled_kickoff')
                     and _instant(g['scheduled_kickoff']) + EXPECTED_END <= now and g['game_id'] not in events)
    if missing:
        warnings.append({'code': 'COMPLETED_GAME_NOT_YET_IN_SOURCE', 'game_ids': missing,
                         'detail': 'Games that should have ended are not yet completed in nflverse.'})
    return out


def label_eligible_count(bundle):
    """Completed 2026 kicker-games passing the V2 forward label rules (published V2 helper).

    Counts rows only: nothing is predicted, scored or compared. It is an upper bound of
    the forward rows, because the V2 audit also applies history-release rules.
    """
    from kickedge.v2.forward import label_exclusions     # published label rule; no model is loaded
    return sum(1 for game in completed_events(bundle).values() for k in game.get('kickers', [])
               if not label_exclusions(k))


def forward_status(count=None):
    reference = dict(FORWARD_REFERENCE)
    status = reference | {'label_eligible_completed_observations': count,
                          'threshold_reached': count is not None and count >= reference['threshold']}
    status['message'] = (f"Forward validation reference: {reference['last_audit_rows']} / {reference['threshold']} "
                         'observations at last V2 audit.')
    if status['threshold_reached']:
        status['threshold_message'] = ('V2 re-evaluation threshold reached (label-eligible count). Nothing was '
                                       're-evaluated; a re-evaluation is a separate, preregistered, manual step.')
    return status


def snapshot_content(dashboard, fresh, forward):
    """What a monitoring snapshot records; capture times are excluded so reloads do not create copies."""
    def core(section):
        return {k: section[k] for k in ('tracked', 'settled', 'pushes', 'graded', 'average_probability',
                                        'observed_frequency', 'brier_score', 'small_sample')} | {
            'calibration': section['calibration']}
    return {'season': fresh.get('season'), 'latest_completed_week': fresh.get('latest_completed_week'),
            'latest_completed_game': (fresh.get('latest_completed_game') or {}).get('game_id'),
            'counts': dashboard['counts'], 'single': core(dashboard['single']),
            'multi_legs': core(dashboard['multi_legs']), 'multis': dashboard['multis'],
            'model': model_identity(),
            'forward_validation': {k: forward[k] for k in ('last_audit_rows', 'threshold',
                                                           'label_eligible_completed_observations', 'threshold_reached')}}


def latest_snapshot(directory):
    directory = Path(directory)/SNAPSHOTS
    names = sorted(p.name for p in directory.glob('*.json')) if directory.is_dir() else []
    for name in reversed(names):
        try:
            return json.loads((directory/name).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
    return None


def record_snapshot(directory, content, now):
    """Write a new snapshot only when its content differs from the latest one; returns (snapshot, written)."""
    content_sha256 = digest(content)
    latest = latest_snapshot(directory)
    if latest and latest.get('content_sha256') == content_sha256:
        return latest, False
    snapshot = {'generated_at': now.isoformat(), 'content_sha256': content_sha256} | content
    name = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{content_sha256[:12]}.json"
    try:
        create_json(Path(directory)/SNAPSHOTS/name, snapshot)
    except FileExistsError:
        return latest_snapshot(directory), False
    return snapshot, True


def snapshot_count(directory):
    directory = Path(directory)/SNAPSHOTS
    return len(list(directory.glob('*.json'))) if directory.is_dir() else 0
