"""Polish pass: central team aliases and versioned venue metadata."""
import duckdb
import pytest

from kickedge.teams import TEAMS, normalize_team, search_terms, team_code, team_display
from kickedge.transform import TEAM_MACRO
from kickedge.venues import _catalog, game_roof, resolve_venue, venue_context


@pytest.mark.parametrize('raw,code', [
    ('LAR', 'LA'), ('lar', 'LA'), ('LA', 'LA'), (' LA ', 'LA'), ('Los Angeles Rams', 'LA'), ('rams', 'LA'),
    ('LA Rams', 'LA'), ('St. Louis Rams', 'LA'), ('JAX', 'JAX'), ('JAC', 'JAX'), ('jac', 'JAX'),
    ('Jacksonville Jaguars', 'JAX'), ('WSH', 'WAS'), ('WAS', 'WAS'), ('Washington', 'WAS'),
    ('Commanders', 'WAS'), ('OAK', 'LV'), ('LVR', 'LV'), ('SD', 'LAC'), ('LA Chargers', 'LAC'),
    ('GNB', 'GB'), ('Green Bay', 'GB'), ('KAN', 'KC'), ('NWE', 'NE'), ('NOR', 'NO'), ('SFO', 'SF'),
    ('49ers', 'SF'), ('TAM', 'TB'), ('Bucs', 'TB'), ('ARZ', 'ARI'), ('  philadelphia   eagles ', 'PHI')])
def test_aliases_normalize_to_nflverse_codes(raw, code):
    assert normalize_team(raw) == code


@pytest.mark.parametrize('raw', ['Los Angeles', 'New York', 'ny'])
def test_shared_city_names_are_never_guessed(raw):
    with pytest.raises(ValueError, match='Ambiguous team name'):
        normalize_team(raw)
    assert team_code(raw) is None


def test_unknown_input_handling():
    assert normalize_team('aaa') == 'AAA'  # unknown short codes pass through and simply match no game
    for raw in ('Springfield Isotopes', '', '   '):
        with pytest.raises(ValueError, match='Unknown team'):
            normalize_team(raw)


def test_canonical_codes_agree_with_the_data_pipeline_macro():
    with duckdb.connect() as con:
        con.execute(TEAM_MACRO)
        for code in TEAMS:
            assert con.execute('SELECT team_code(?)', [code]).fetchone()[0] == code
        for alias in ('STL', 'LAR', 'OAK', 'SD', 'SDG', 'JAC'):
            assert con.execute('SELECT team_code(?)', [alias]).fetchone()[0] == normalize_team(alias)


def test_display_and_search_terms():
    assert team_display('LA') == {'code': 'LA', 'name': 'Los Angeles Rams', 'nickname': 'Rams', 'city': 'Los Angeles'}
    assert team_display('AAA')['nickname'] == 'AAA'
    assert {'LAR', 'Rams', 'Los Angeles Rams'} <= set(search_terms('LA'))


def test_venue_file_is_complete_and_unambiguous():
    doc, venues, names, digest = _catalog()
    assert len(digest) == 64 and doc['verified_at'].endswith('+00:00')
    for v in venues.values():
        assert -90 <= v['latitude'] <= 90 and -180 <= v['longitude'] <= 180
        assert v['roof'] in {'outdoors', 'dome', 'retractable'} and v['roof_evidence'] and v['stadium_ids']
    # Every venue name used by the nflverse 2024-2026 schedules resolves.
    schedule_names = [
        'Mercedes-Benz Stadium', 'M&T Bank Stadium', 'Gillette Stadium', 'Highmark Stadium', 'Bank of America Stadium',
        'Soldier Field', 'Paycor Stadium', 'Huntington Bank Field', 'FirstEnergy Stadium', 'AT&T Stadium',
        'Empower Field at Mile High', 'Ford Field', 'Lambeau Field', 'Reliant Stadium', 'NRG Stadium', 'Lucas Oil Stadium',
        'EverBank Stadium', 'TIAA Bank Stadium', 'GEHA Field at Arrowhead Stadium', 'SoFi Stadium', 'Wembley Stadium',
        'Tottenham Stadium', 'Tottenham Hotspur Stadium', 'Bernabeu', 'Melbourne Cricket Ground', 'Estadio Banorte',
        'Azteca Stadium', 'Hard Rock Stadium', 'U.S. Bank Stadium', 'FC Bayern Munich Stadium', 'Allianz Arena',
        'Nissan Stadium', 'Caesars Superdome', 'Mercedes-Benz Superdome', 'MetLife Stadium', 'Stade de France',
        'Lincoln Financial Field', 'State Farm Stadium', 'Acrisure Stadium', 'Maracana Stadium', 'Arena Corinthians',
        'Lumen Field', "Levi's Stadium", 'Raymond James Stadium', 'Allegiant Stadium', 'Northwest Stadium', 'FedExField']
    assert [n for n in schedule_names if resolve_venue(n) is None] == []


def test_venue_aliases_normalization_and_unknown_names():
    assert resolve_venue('Reliant Stadium')['name'] == 'NRG Stadium'
    assert resolve_venue('  geha field at ARROWHEAD stadium ')['slug'] == 'arrowhead-stadium'
    assert resolve_venue('Bernabéu')['slug'] == resolve_venue('Bernabeu')['slug'] == 'bernabeu'
    assert resolve_venue('FC Bayern Munich Stadium')['name'] == 'Allianz Arena'
    assert resolve_venue('Mercedes-Benz Superdome')['name'] == 'Caesars Superdome'
    for unknown in ('Unknown Field', '', None):
        assert resolve_venue(unknown) is None


def test_name_wins_over_a_wrong_stadium_id():
    venue = resolve_venue('Tottenham Hotspur Stadium', 'JAX00')
    assert venue['city'] == 'London, UK' and venue['latitude'] == 51.6044
    assert venue['stadium_id_consistent'] is False
    assert resolve_venue('Lincoln Financial Field', 'PHI00')['stadium_id_consistent'] is True


def test_game_day_roof_respects_physical_type():
    mcg, att, ford = (resolve_venue(n) for n in ('Melbourne Cricket Ground', 'AT&T Stadium', 'Ford Field'))
    assert game_roof(mcg, 'dome') == 'outdoors'          # open-air ground cannot be closed
    assert game_roof(ford, 'outdoors') == 'dome'          # fixed roof
    assert [game_roof(att, r) for r in ('open', 'closed', 'dome', '', None, 'retractable')] == \
        ['open', 'closed', 'closed', 'retractable', 'retractable', 'retractable']


def test_venue_context_adds_coordinates_and_provenance_only_when_resolved():
    ctx = venue_context({'venue': 'Lincoln Financial Field', 'roof': 'outdoors', 'stadium_id': 'PHI00'})
    assert (ctx['latitude'], ctx['longitude'], ctx['roof']) == (39.90083333, -75.1675, 'outdoors')
    assert ctx['venue_source'] == 'kickedge/venues.json' and len(ctx['venue_source_sha256']) == 64
    assert venue_context({'venue': 'Nowhere Park', 'roof': 'outdoors'}) == {}
    # Schedule coordinates, when present, stay authoritative.
    assert venue_context({'venue': 'AT&T Stadium', 'latitude': 1.0, 'longitude': 2.0}) == {}
