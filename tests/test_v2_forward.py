"""2026 forward evaluation mechanics on synthetic 2026 data (never real 2026 outcomes):
row construction, exclusions, single reveal, frozen artifacts verified first."""
from pathlib import Path
import shutil

import duckdb
import pytest

from kickedge.modeling.dataset import predictor_columns
from kickedge.v2 import forward
from kickedge.v2.carryover import CARRYOVER_COLUMNS
from polish_data import ELLIOTT, MEVIS, NOW, make_bundle

needs_data = pytest.mark.skipif(not Path('data/cache/current/2025').exists() or not Path('reports/v2_freeze.json').exists(),
                                reason='Local 2025 season cache and V2 freeze required')


def synthetic_bundle(unusable_first=False):
    bundle = make_bundle()
    for game in bundle['games']:
        for k in game['kickers']:
            k.update(target_season_eligible=True, id_in_players=True, schedule_identity_ok=True)
    bundle['games'][-1]['kickers'][0]['id_in_players'] = False        # one explicit identity exclusion
    if unusable_first:
        bundle['games'][0]['kickers'][0]['statistical_label_usable'] = False
    return bundle


@needs_data
def test_forward_rows_rebuild_training_features_with_2025_carryover():
    rows, exclusions = forward.forward_rows('.', now=NOW, loader=lambda *a, **k: synthetic_bundle())
    assert len(rows) == 5 and len(exclusions) == 1 and exclusions[0]['reason'] == 'identity_problem'
    assert set(predictor_columns()) <= set(rows.columns) and set(CARRYOVER_COLUMNS) <= set(rows.columns)
    first = rows[(rows.kicker_id == MEVIS) & (rows.game_id == '2026_02_SF_LA')].iloc[0]
    assert first.kicker_games_before == 1 and first.current_season_games_before == 1   # only the week-1 game before
    assert first.kicker_prior_season_games > 0          # Mevis kicked for the Rams in 2025
    assert rows[rows.kicker_id == ELLIOTT].offense_prior_season_points_per_game.notna().all()


def test_reveal_runs_once_and_verifies_freeze_first(tmp_path, monkeypatch):
    root = Path('.')
    if not (root/'reports/v2_freeze.json').exists():
        pytest.skip('V2 freeze required')
    shutil.copytree(root/'models/v2', tmp_path/'models/v2')
    shutil.copytree(root/'models/phase5', tmp_path/'data/models/phase5')
    (tmp_path/'reports').mkdir()
    shutil.copy(root/'reports/v2_freeze.json', tmp_path/'reports/v2_freeze.json')
    with duckdb.connect() as con:
        rows = con.execute("SELECT * FROM read_parquet('data/v2/dataset/dataset.parquet') ORDER BY game_id LIMIT 20").fetchdf()
    rows = rows.assign(season=2026)
    calls = []

    def fake_rows(r, *, now, loader):
        calls.append(1)
        return rows.drop(columns=['kickoff', 'prediction_cutoff']), [{'reason': 'example'}]
    monkeypatch.setattr(forward, 'forward_rows', fake_rows)
    first = forward.reveal(tmp_path, now=NOW)
    assert first['rows'] == 20 and first['adopt_v2'] is False and not first['adoption_gate']['rows_at_least_150']
    assert set(first['scores']) == {'V1', 'v2_final:v1_style_glm_alpha_0.1', 'challenger:carryover_glm_alpha_1'}
    assert forward.reveal(tmp_path, now=NOW) == first and len(calls) == 1          # stored result, no second reveal
    (tmp_path/forward.RESULT).unlink()
    with pytest.raises(ValueError, match='manually'):
        forward.reveal(tmp_path, now=NOW)                                          # marker without result: never silently rerun
    resumed = forward.reveal(tmp_path, now=NOW, amendment='documented reason')     # explicit, recorded amendment only
    assert len(resumed['aborted_attempts']) == 1 and resumed['aborted_attempts'][0]['amendment'] == 'documented reason'
    (tmp_path/forward.RESULT).unlink()
    (tmp_path/forward.REVEAL_MARKER).unlink()
    (tmp_path/'models/v2/carryover_glm_alpha_1/model.joblib').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        forward.reveal(tmp_path, now=NOW)
    assert not (tmp_path/forward.REVEAL_MARKER).exists()                           # no marker before verification


@needs_data
def test_unusable_prior_label_excludes_later_rows_like_training():
    rows, exclusions = forward.forward_rows('.', now=NOW, loader=lambda *a, **k: synthetic_bundle(unusable_first=True))
    reasons = sorted(e['reason'] for e in exclusions)
    assert reasons == ['history_incomplete_or_unusable', 'history_incomplete_or_unusable', 'identity_problem',
                       'unusable_target_label'] and len(rows) == 2
