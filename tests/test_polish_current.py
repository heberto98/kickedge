"""Polish pass, current layer: game catalog, kicker candidates, roster affiliation,
alias resolution, venue weather and engine integration. Model and features unchanged."""
from datetime import timedelta
from pathlib import Path

import pytest

from kickedge.current.catalog import kicker_affiliation, kicker_candidates, upcoming_games
from kickedge.current.engine import analyze_current_prop
from kickedge.current.optional import collect_context
from kickedge.current.snapshot import GameNotFound, resolve_kicker, resolve_target
from kickedge.modeling.dataset import predictor_columns
from polish_data import ELLIOTT, FORMER, LINC, MEVIS, NOW, PRACTICE, make_bundle, no_context

needs_model = pytest.mark.skipif(not Path('data/models/phase5/model.joblib').exists(), reason='Local model unavailable')


def target(team='LA', opponent='PHI', **kw):
    return resolve_target(make_bundle(), team, opponent, season=2026, now=NOW, **({'week': 5} | kw))


def test_upcoming_games_future_sorted_named_and_resolvable():
    bundle = make_bundle()
    games = upcoming_games(bundle, NOW)
    assert [g['game_id'] for g in games] == ['2026_05_DAL_HOU', '2026_05_LA_PHI', '2026_06_PHI_DET',
                                              '2026_07_LA_JAX', '2026_08_PHI_LA']
    g = games[1]
    assert (g['away_team'], g['home_team'], g['display_name']) == ('LA', 'PHI', 'Rams @ Eagles')
    assert g['full_name'] == 'Los Angeles Rams @ Philadelphia Eagles' and 'lar' in g['search']
    assert games[0]['venue'] == 'NRG Stadium' and games[0]['roof'] == 'retractable'
    for game in games:  # the catalog never lists a game the resolver would reject
        assert resolve_target(bundle, game['away_team'], game['home_team'], season=2026, now=NOW,
                              game_id=game['game_id'])['game_id'] == game['game_id']
    assert upcoming_games(bundle, NOW+timedelta(days=30)) == []


@pytest.mark.parametrize('team,opponent', [('LAR', 'PHI'), ('lar', 'phi'), ('Los Angeles Rams', 'Eagles'), ('Rams', 'PHI')])
def test_resolve_target_normalizes_team_aliases(team, opponent):
    t = target(team, opponent)
    assert (t['game_id'], t['team'], t['opponent'], t['is_home']) == ('2026_05_LA_PHI', 'LA', 'PHI', False)


def test_jac_alias_and_london_venue():
    t = target('LA', 'JAC', week=7)
    assert t['game_id'] == '2026_07_LA_JAX' and t['opponent'] == 'JAX'
    assert t['venue'] == 'Tottenham Hotspur Stadium' and (t['latitude'], t['longitude']) == (51.6044, -0.0664)
    assert t['venue_stadium_id_consistent'] is False


def test_missing_game_lists_upcoming_games_for_either_team():
    with pytest.raises(GameNotFound, match='No matching future game') as err:
        resolve_target(make_bundle(), 'LAR', 'DAL', season=2026, now=NOW)
    assert [g['game_id'] for g in err.value.suggestions] == ['2026_05_DAL_HOU', '2026_05_LA_PHI',
                                                             '2026_07_LA_JAX', '2026_08_PHI_LA']
    with pytest.raises(ValueError, match='ambiguous'):
        resolve_target(make_bundle(), 'LA', 'PHI', season=2026, now=NOW)


def test_kicker_candidates_follow_roster_and_history_without_substitution():
    bundle = make_bundle()
    game = next(g for g in upcoming_games(bundle, NOW) if g['game_id'] == '2026_05_LA_PHI')
    teams = {t['code']: t for t in kicker_candidates(bundle, game, NOW)}
    assert list(teams) == ['PHI', 'LA'] and teams['LA']['nickname'] == 'Rams'
    la = teams['LA']['kickers']
    assert [k['kicker_id'] for k in la] == [MEVIS]  # former kicker (no 2026 roster) and the WR are excluded
    assert la[0]['roster_verified'] is True and la[0]['season_games'] == 3 and la[0]['season_xpm'] == 9
    phi = teams['PHI']['kickers']
    assert [k['kicker_id'] for k in phi] == [ELLIOTT, PRACTICE]
    assert phi[1]['roster_label'] == 'Practice squad' and phi[1]['roster_verified'] is False


def test_kicker_affiliation_states():
    bundle, t = make_bundle(), target()
    assert kicker_affiliation(bundle, MEVIS, t)['verified'] is True
    conflict = kicker_affiliation(bundle, ELLIOTT, t)
    assert conflict['conflict'] and 'Kicker roster conflict' in conflict['message']
    practice = kicker_affiliation(bundle, PRACTICE, target('PHI', 'LA'))
    assert practice['verified'] is False and not practice['conflict'] and 'Practice squad' in practice['message']
    former = kicker_affiliation(bundle, FORMER, t)
    assert former['verified'] is False and 'no 2026 roster entry' in former['message']
    unknown = kicker_affiliation(bundle, '00-0000001', t)
    assert unknown['verified'] is None and 'could not be independently confirmed' in unknown['message']
    elsewhere = kicker_affiliation(bundle, ELLIOTT, target('DAL', 'HOU'))
    assert elsewhere['verified'] is False and not elsewhere['conflict'] and 'PHI' in elsewhere['message']


class Weather:
    def __init__(self):
        self.calls = []

    def forecast(self, latitude, longitude, kickoff):
        self.calls.append((latitude, longitude))
        return dict(source='https://api.open-meteo.com/v1/forecast', source_sha256='d'*64, kind='forecast',
                    observed_at=NOW.isoformat(), latitude=latitude, longitude=longitude,
                    valid_time='2026-10-11T17:00:00+00:00',
                    values={'temperature': 14, 'wind_speed': 18, 'wind_gust': 30, 'precipitation_probability': 20,
                            'precipitation': 0.2, 'weather_code': 3})


def weather_for(t):
    weather = Weather()
    player = resolve_kicker(make_bundle(), MEVIS, t, cutoff=NOW)
    result = collect_context(t, player, line=1.5, now=NOW, clock=lambda: NOW, no_market=True,
                             weather_factory=lambda **_: weather)
    return weather, result


def test_outdoor_venue_metadata_enables_weather_context():
    weather, result = weather_for(target())
    assert weather.calls == [LINC]
    w = result['context']['weather']
    assert w['available'] and w['values']['wind_gust'] == 30 and w['values']['is_dome'] is False
    assert w['provenance']['venue']['source'] == 'kickedge/venues.json'
    assert w['training_eligible'] is False


def test_dome_retractable_unknown_and_far_games_do_not_request_weather():
    weather, result = weather_for(target('PHI', 'DET', week=6))
    assert weather.calls == [] and result['context']['weather']['values']['is_dome'] is True
    assert result['context']['weather']['available'] is True  # verified indoor venue
    weather, result = weather_for(target('DAL', 'HOU'))
    assert weather.calls == [] and not result['context']['weather']['available']
    assert any('roof exposure' in w for w in result['warnings'])
    weather, result = weather_for(target('LA', 'JAX', week=7))  # 17 days out: beyond the forecast window
    assert weather.calls == [] and result['source_failures'] == []
    assert any('Open-Meteo covers the next 16 days' in w for w in result['warnings'])


def run(kicker=MEVIS, team='LAR', opponent='PHI', collector=no_context, **kw):
    return analyze_current_prop(kicker, team, opponent, 1.5, 'over', -333, season=2026, week=5,
                                clock=lambda: NOW, source_loader=lambda *a, **k: make_bundle(),
                                context_collector=collector, **kw)


@needs_model
def test_engine_alias_roster_and_display(tmp_path):
    seen = {}

    def capture(t, player, **kwargs):
        seen.update(target=t)
        return no_context()
    r = run(collector=capture, output_dir=tmp_path, no_market=True)
    assert r['game']['game_id'] == '2026_05_LA_PHI' and r['game']['team'] == 'LA'
    assert r['data_quality']['kicker_current_team_verified'] is True
    assert not any('affiliation' in w for w in r['data_quality']['warnings'])
    assert r['teams']['LA']['nickname'] == 'Rams' and r['game']['venue'] == 'Lincoln Financial Field'
    assert (seen['target']['latitude'], seen['target']['longitude']) == LINC
    assert list(r['features']) == predictor_columns() and len(r['features']) == 82
    assert r['data_quality']['market_requested'] is False and r['data_quality']['weather_requested'] is True


@needs_model
def test_engine_stops_on_roster_conflict_and_warns_when_unverified(tmp_path):
    with pytest.raises(ValueError, match='Kicker roster conflict'):
        run(kicker=ELLIOTT, output_dir=tmp_path)
    r = run(kicker=PRACTICE, team='PHI', opponent='LA', output_dir=tmp_path)
    assert r['data_quality']['kicker_current_team_verified'] is False
    assert any('Practice squad' in w for w in r['data_quality']['warnings'])


@needs_model
def test_weather_context_never_changes_features_or_prediction(tmp_path):
    def with_weather(t, player, **kwargs):
        weather = Weather()
        return collect_context(t, player, line=1.5, now=NOW, clock=lambda: NOW, no_market=True,
                               weather_factory=lambda **_: weather)
    plain = run(output_dir=tmp_path/'a')
    rich = run(collector=with_weather, output_dir=tmp_path/'b')
    assert rich['context']['weather']['available'] and not plain['context']['weather']['available']
    assert rich['features'] == plain['features']
    assert rich['prediction'] == plain['prediction'] and rich['prop'] == plain['prop']
