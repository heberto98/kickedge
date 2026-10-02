import json

import pandas as pd
import pytest

from kickedge.features import load_contract
from kickedge.modeling.dataset import predictor_columns


def payload():
    fields = {f['name']: f for f in load_contract()['fields']}
    return {'features': {n: ('REG' if fields[n]['dtype'] == 'string' else False if fields[n]['dtype'] == 'boolean' else 1) for n in reversed(predictor_columns())}, 'metadata': {'kicker': 'Synthetic Kicker', 'team': 'AAA', 'opponent': 'BBB'}}


def snapshot(p):
    from kickedge.inference.contracts import FeatureSnapshot
    return FeatureSnapshot.from_mapping(p)


def test_ordered_82_and_metadata_isolation():
    s = snapshot(payload())
    assert list(s.to_frame()) == predictor_columns()
    assert s.to_frame().shape == (1, 82)
    assert s.metadata['team'] == 'AAA'
    assert s.provenance == {}
    assert s.warnings


@pytest.mark.parametrize('name', ['xpm', 'weather_temperature', 'unknown'])
def test_extra_predictors_rejected(name):
    p = payload(); p['features'][name] = 1
    with pytest.raises(ValueError): snapshot(p)


def test_missing_predictor_rejected():
    p = payload(); del p['features']['season']
    with pytest.raises(ValueError, match='season'): snapshot(p)


@pytest.mark.parametrize('field,value', [('season', True), ('season', 1.5), ('season', '2024'), ('season', None), ('offense_points_per_game_before', True), ('offense_points_per_game_before', float('nan')), ('offense_points_per_game_before', float('inf')), ('is_home', 2), ('game_type', '')])
def test_invalid_feature_types(field, value):
    p = payload(); p['features'][field] = value
    with pytest.raises(ValueError, match=field): snapshot(p)


def test_null_and_boolean_normalization():
    p = payload(); p['features']['previous_game_xpm'] = None; p['features']['is_home'] = 1; p['features']['season'] = 2024.0
    s = snapshot(p)
    assert s.nullable_features == ['previous_game_xpm']
    assert pd.isna(s.to_frame().iloc[0]['previous_game_xpm'])
    assert s.to_frame().iloc[0]['is_home'] == 1


@pytest.mark.parametrize('change', [{'kicker': ' '}, {'team': 'BBB'}, {'opponent': None}, {'xpm': 8}, {'kickoff': '2024-01-01T12:00:00'}, {'cutoff': 'bad'}, {'kickoff': '2024-01-01T12:00:00Z', 'cutoff': '2024-01-01T12:00:00Z'}])
def test_invalid_metadata(change):
    p = payload(); p['metadata'].update(change)
    with pytest.raises(ValueError): snapshot(p)


def test_aware_timestamps_and_demo_provenance():
    p = payload(); p['metadata'].update(kickoff='2024-01-01T12:00:00Z', cutoff='2024-01-01T05:00:00-06:00')
    p['provenance'] = {'demo': True, 'kind': 'DEMO / TEST FIXTURE', 'source_sha256': 'a' * 64}
    s = snapshot(p)
    assert s.provenance['demo'] is True
    assert any('demo' in w.lower() for w in s.warnings)


@pytest.mark.parametrize('text', ['{"features":{},"features":{}}', '{"features":{"x":NaN}}', '{"features":{"x":Infinity}}', '{'])
def test_strict_json_reader(tmp_path, text):
    from kickedge.inference.contracts import read_snapshot
    path = tmp_path / 'snapshot.json'; path.write_text(text)
    with pytest.raises(ValueError): read_snapshot(path)


def test_json_round_trip(tmp_path):
    from kickedge.inference.contracts import read_snapshot
    path = tmp_path / 'snapshot.json'; path.write_text(json.dumps(payload()))
    assert read_snapshot(path).to_frame().shape == (1, 82)


def test_no_payload_echo_or_unknown_envelope_fields():
    p = payload(); p['secret_token'] = 'DO_NOT_ECHO'
    with pytest.raises(ValueError) as error: snapshot(p)
    assert 'DO_NOT_ECHO' not in str(error.value)


def test_unknown_category_is_preserved_with_warning():
    p = payload(); p['features']['game_type'] = 'FUTURE'
    s = snapshot(p)
    assert s.to_frame().iloc[0]['game_type'] == 'FUTURE'
    assert any('game_type' in w for w in s.warnings)
