import ast
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path

import duckdb
import pytest

from kickedge.pregame import select as selection_module
from kickedge.pregame.evidence import latest_snapshot, schedule_rows
from kickedge.pregame.evaluate import attach, evaluate, summarize
from kickedge.pregame.official import article_metadata
from kickedge.pregame.select import instant, select


POLICY = {'cutoff_minutes': 60, 'depth_max_age_hours': 48, 'official_max_age_hours': 168,
          'eligible_categories': ['VERIFIED']}
GAME = {'game_id': 'game', 'team': 'A', 'season': 2025, 'target_season_eligible': True,
        'prediction_cutoff': '2025-09-07T16:00:00Z', 'kickoff_utc': '2025-09-07T17:00:00Z'}


def ev(pid='X', kind='depth_snapshot', **extra):
    return {'game_id': 'game', 'team': 'A', 'evidence_id': f'{kind}:{pid}', 'kind': kind,
            'player_id': pid, 'name': pid, 'rank': 1, 'source_url': 'https://source.example',
            'available_at': '2025-09-07T07:00:00Z', **extra}


def choose(evidence):
    return select(GAME, evidence, POLICY)[0]


@pytest.mark.parametrize('kind', ['pbp', 'player_stats', 'box_score', 'first_pat', 'untimed_depth_charts'])
def test_outcomes_and_untimed_sources_cannot_select_identity(kind):
    assert choose([ev(kind=kind)])['expected_kicker_id'] is None


@pytest.mark.parametrize('time', ['2025-09-07T16:00:00.000001Z', '2025-09-08T07:00:00Z'])
def test_future_evidence_never_determines_id_or_candidates(time):
    r = choose([ev(kind='official_assignment', available_at=time)])
    assert r['expected_kicker_id'] is None
    assert r['expected_kicker_candidates'] == []


def test_at_cutoff_is_inclusive_and_timezone_aware():
    assert choose([ev(available_at='2025-09-07T12:00:00-04:00')])['expected_kicker_id'] == 'X'
    with pytest.raises(ValueError):
        choose([ev(available_at='2025-09-07T12:00:00')])


def test_old_publication_does_not_justify_later_revised_content():
    r, log = select(GAME, [ev(kind='official_assignment', modified_at='2025-09-07T16:01:00Z')], POLICY)
    assert r['expected_kicker_confidence'] == 'UNKNOWN'
    assert log[0]['rejection_reason'] == 'content_modified_after_cutoff'


def test_unknown_is_not_filled_from_target_outcomes():
    r = choose([])
    a = attach(r, None, [{'player_id': 'Y', 'pbp_xpa': 4, 'pbp_fga': 2, 'pbp_kickoffs': 5}])
    assert a['expected_kicker_id'] is None and a['xpm'] is None
    assert not a['eligible_for_pregame_training']


def test_selector_has_no_file_network_or_outcome_dependencies():
    tree = ast.parse(Path(selection_module.__file__).read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert imports == ['datetime']
    assert not any(isinstance(n, ast.Import) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {'open', 'eval', 'exec', '__import__'} for n in ast.walk(tree))


def test_two_equal_candidates_are_ambiguous():
    r = choose([ev('X'), ev('Y')])
    assert r['expected_kicker_confidence'] == 'AMBIGUOUS'
    assert r['expected_kicker_id'] is None and len(r['expected_kicker_candidates']) == 2


def test_rank_two_is_recorded_but_not_tied_with_rank_one():
    r = choose([ev('X'), ev('Y', rank=2)])
    assert r['expected_kicker_id'] == 'X' and not r['expected_kicker_ambiguous']
    assert len(r['expected_kicker_candidates']) == 2
    assert choose([ev('Y', rank=2)])['expected_kicker_confidence'] == 'UNKNOWN'


def test_official_non_k_replacement_overrides_depth_role():
    r = choose([ev('X'), ev('Y', kind='official_assignment', position='P'), ev('X', kind='official_unavailable')])
    assert r['expected_kicker_id'] == 'Y' and r['pregame_identity_eligible']
    assert next(c for c in r['expected_kicker_candidates'] if c['player_id'] == 'X')['blocked']


def test_out_inactive_released_candidate_does_not_promote_backup_automatically():
    r = choose([ev('X'), ev('Y', rank=2), ev('X', kind='official_unavailable')])
    assert r['expected_kicker_id'] is None


def test_two_official_assignments_conflict():
    r = choose([ev('X', kind='official_assignment'), ev('Y', kind='official_assignment')])
    assert r['expected_kicker_confidence'] == 'AMBIGUOUS'


def test_inactive_absence_requires_positive_roster_and_does_not_confirm_depth():
    inactive = ev(None, kind='official_inactives', complete_list=True, inactive_ids=[], inactive_names=[])
    assert choose([inactive])['expected_kicker_confidence'] == 'UNKNOWN'
    assert choose([inactive, ev()])['expected_kicker_confidence'] == 'INFERRED'
    assert choose([inactive, ev(kind='official_roster')])['expected_kicker_confidence'] == 'STRONG'
    assert choose([inactive | {'inactive_names': ['X']}, ev(kind='official_roster')])['expected_kicker_confidence'] == 'UNKNOWN'


def test_future_inactive_list_cannot_upgrade_roster():
    r = choose([ev(kind='official_roster'), ev(None, kind='official_inactives', complete_list=True,
               available_at='2025-09-07T16:01:00Z')])
    assert r['expected_kicker_confidence'] == 'INFERRED'


def test_stale_depth_and_unresolved_identity_remain_unknown():
    assert choose([ev(available_at='2025-09-05T15:59:59Z')])['expected_kicker_id'] is None
    r = choose([ev(None, external_id='espn-unmapped')])
    assert r['expected_kicker_confidence'] == 'UNKNOWN'
    assert r['pregame_exclusion_reason'] == 'unresolved_player_id'


def test_latest_team_snapshot_without_pk_does_not_resurrect_old_pk():
    old, new, future = map(instant, ['2025-09-06T07:00:00Z', '2025-09-07T07:00:00Z', '2025-09-08T07:00:00Z'])
    dt, rows, excluded = latest_snapshot([old, new, future], {('A', old): [ev()]}, 'A', instant(GAME['prediction_cutoff']))
    assert dt == new and rows == [] and excluded == 1


def test_future_snapshots_cannot_change_asof_selection():
    old, future = map(instant, ['2025-09-07T07:00:00Z', '2025-09-08T07:00:00Z'])
    before = latest_snapshot([old], {('A', old): [ev()]}, 'A', instant(GAME['prediction_cutoff']))
    after = latest_snapshot([old, future], {('A', old): [ev()], ('A', future): [ev('Y')]}, 'A', instant(GAME['prediction_cutoff']))
    assert before[:2] == after[:2]


@pytest.mark.parametrize('day,expected', [('2025-09-07', '2025-09-07T16:00:00+00:00'), ('2024-11-03', '2024-11-03T17:00:00+00:00')])
def test_scheduled_eastern_time_respects_dst(tmp_path, day, expected):
    path = tmp_path / 'games.parquet'
    with duckdb.connect() as c:
        c.execute("CREATE TABLE g AS SELECT 'game' game_id,2025 AS season,1 AS week,'REG' game_type,'A' home_team,'B' away_team,? gameday,'13:00' gametime", [day])
        c.execute('COPY g TO ? (FORMAT PARQUET)', [str(path)])
        rows = schedule_rows(c, path, 60)
    assert len(rows) == 2 and rows[0]['prediction_cutoff'] == expected


def valid_label(xpa=0, xpm=0):
    return {'xpa': xpa, 'xpm': xpm, 'statistical_label_usable': True, 'pbp_source_sha256': 'pbp', 'stats_source_sha256': 'stats'}


def test_zero_outcome_survives_and_mismatch_does_not_remove_eligibility():
    r = choose([ev(kind='official_assignment')])
    frozen = deepcopy(r)
    a = attach(r, valid_label(), [{'player_id': 'Y', 'pbp_xpa': 3, 'pbp_fga': 1, 'pbp_kickoffs': 4}])
    assert r == frozen
    assert a['expected_kicker_id'] == 'X' and a['comparison'] == 'mismatch'
    assert a['xpm'] == 0 and a['xpa'] == 0 and a['eligible_for_pregame_training']


def test_missing_stats_not_automatically_zero_or_dnp():
    r = attach(choose([ev()]), None, [])
    assert r['xpa'] is None and r['xpm'] is None
    assert r['expected_kicking_participation'] == 'no_kicking_evidence'


def test_multiple_actual_preserved_and_kickoff_only_not_placekicker():
    r = choose([ev()])
    a = attach(r, valid_label(), [{'player_id': p, 'pbp_xpa': xpa, 'pbp_fga': 0, 'pbp_kickoffs': 1}
                                for p, xpa in [('X', 1), ('Y', 1), ('Z', 0)]])
    assert a['comparison'] == 'expected_among_multiple' and a['actual_placekicker_ids'] == ['X', 'Y']


def test_modified_identity_file_rejected_before_loading_outcomes(tmp_path):
    p = tmp_path / 'identities.json'
    p.write_text('[]')
    with pytest.raises(ValueError, match='Frozen identities changed'):
        evaluate(p, 'wrong-sha256', tmp_path / 'absent-outcomes')


def test_article_parser_ignores_future_gallery_metadata():
    article = {'@type': 'NewsArticle', 'url': 'https://a', 'datePublished': '2025-09-07T07:00:00Z', 'dateModified': '2025-09-07T08:00:00Z'}
    gallery = {'@type': 'WebPage', 'dateModified': '2026-01-01T07:00:00Z'}
    html = ''.join('<script type="application/ld+json">' + json.dumps(x) + '</script>' for x in [article, gallery])
    assert article_metadata(html, 'https://a') == article
    with pytest.raises(ValueError):
        article_metadata(html, 'https://different')


@pytest.fixture(scope='module')
def real_pregame():
    root = Path(__file__).resolve().parents[1]
    pointer = root / 'data/pregame/processed/latest.json'
    if not pointer.exists():
        pytest.skip('Build the pregame data for integration tests')
    b = root / json.loads(pointer.read_text())['path']
    return root, b, json.loads((b / 'expected_kicker_labels.json').read_text(encoding='utf-8'))


def test_real_full_population_and_evidence_integrity(real_pregame):
    from kickedge.io import sha256_file
    root, b, rows = real_pregame
    metadata = json.loads((b / 'build.json').read_text())
    assert len(rows) == 6056 and len({(r['game_id'], r['team']) for r in rows}) == 6056
    assert all(metadata['checks'].values())
    for a in metadata['artifacts']:
        assert sha256_file(root / a['path']) == a['sha256']


@pytest.mark.parametrize('game,team,pid,confidence,xpm', [
    ('2024_09_WAS_NYG', 'NYG', '00-0039934', 'VERIFIED', 1),
    ('2024_02_NYG_WAS', 'WAS', '00-0035145', 'STRONG', 0),
    ('2024_02_NYG_WAS', 'NYG', None, 'UNKNOWN', None),
    ('2019_02_LAC_DET', 'LAC', None, 'UNKNOWN', None),
    ('2021_15_CAR_BUF', 'CAR', None, 'UNKNOWN', None),
    ('2025_07_GB_ARI', 'ARI', None, 'UNKNOWN', None),
    ('2025_01_MIA_IND', 'MIA', '00-0036816', 'INFERRED', 0),
    ('2025_06_CIN_GB', 'GB', '00-0029822', 'INFERRED', None),
])
def test_real_audited_pregame_decisions(real_pregame, game, team, pid, confidence, xpm):
    row = next(r for r in real_pregame[2] if r['game_id'] == game and r['team'] == team)
    assert (row['expected_kicker_id'], row['expected_kicker_confidence'], row['xpm']) == (pid, confidence, xpm)


def test_real_provenance_all_support_precedes_cutoff(real_pregame):
    _, b, rows = real_pregame
    evidence = {e['evidence_id']: e for e in json.loads((b / 'evidence.json').read_text(encoding='utf-8'))}
    for r in rows:
        for eid in r['expected_kicker_evidence_ids']:
            e = evidence[eid]
            assert e['admissible'] and instant(e['available_at']) <= instant(r['prediction_cutoff'])
            assert e['source_sha256'] and e['locator']
    summary = summarize(rows)
    assert summary['total']['comparisons']['mismatch'] == 16
    assert summary['total']['expected_xpm_zero'] == 59
