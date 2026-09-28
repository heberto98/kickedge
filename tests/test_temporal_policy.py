from copy import deepcopy
import json

import pytest
import duckdb

from kickedge.features import load_contract
from kickedge.features import validation
from kickedge.features.kicker import instant, FEATURE_NAMES, LabelOracle
from kickedge.io import sha256_file, write_json, write_parquet
from test_kicker_features import fixture
from test_kicker_feature_pipeline import source_fixture


def approved(evidence, cutoff='2025-09-15T16:00:00+00:00'):
    checker = getattr(validation, 'temporal_evidence_valid', None)
    assert callable(checker), 'Temporal classes have not been implemented'
    return checker(evidence, instant(cutoff))


def event():
    return dict(temporal_class='historical_event_data', event_completed=True,
                actual_kickoff='2025-09-07T17:00:00+00:00', last_event='2025-09-07T20:00:00+00:00',
                available_at='2025-09-08T17:00:00+00:00', availability_verified=False,
                source_sha256='frozen_event_source', publication_at=None,
                downloaded_at='2026-09-28T00:00:00+00:00')


def test_past_event_does_not_require_historical_file_publication():
    assert approved(event())
    later_copy = event() | {'downloaded_at':'2030-01-01T00:00:00+00:00'}
    assert approved(later_copy)


@pytest.mark.parametrize('change', [
    {'event_completed':False}, {'last_event':'2025-09-16T00:00:00+00:00'},
    {'last_event':'2025-09-15T16:00:00+00:00'}, {'source_sha256':None},
    {'actual_kickoff':'2025-09-17T17:00:00+00:00'},
])
def test_future_incomplete_or_untraceable_event_is_not_approved(change):
    assert not approved(event() | change)


def test_context_still_needs_verified_pre_cutoff_version():
    context = dict(temporal_class='point_in_time_context_data', available_at='2025-09-15T15:00:00+00:00',
                   availability_verified=False, source_sha256='snapshot')
    assert not approved(context)
    context['availability_verified'] = True
    assert approved(context)
    assert not approved(context | {'modified_at':'2025-09-15T17:00:00+00:00'})
    assert not approved(context | {'published_at':'2025-09-15T17:00:00+00:00'})
    assert not approved(context | {'available_at':'2025-09-15T17:00:00+00:00'})


def test_unknown_class_never_inherits_event_exemption():
    assert not approved(event() | {'temporal_class':'other'})


def test_context_contract_cannot_be_reclassified_as_event_to_waive_publication():
    c=load_contract()
    field=next(f for f in c['fields'] if f['group']=='market')
    field.update(temporal_class='historical_event_data',publication_timestamp_required=False)
    with pytest.raises(ValueError,match='temporal'):
        validation.validate_contract(c)


def test_prepare_rejects_event_without_end_game_evidence(tmp_path):
    from kickedge.features.prepare import prepare
    config,base=source_fixture(tmp_path)
    with duckdb.connect() as con:
        con.execute('CREATE TABLE pbp AS SELECT * FROM read_parquet(?)',[str(base/'pbp.parquet')])
        con.execute('UPDATE pbp SET play_deleted=1 WHERE game_id=\'g7\'')
        write_parquet(con,'SELECT * FROM pbp',base/'pbp.parquet')
    lock=json.loads((base/'source_lock.json').read_text())
    lock['sources'][0]['sha256']=sha256_file(base/'pbp.parquet')
    write_json(base/'source_lock.json',lock)
    with pytest.raises(ValueError,match='Incomplete'):
        prepare(config)


def test_contract_approves_only_implemented_kicker_event_features():
    c = load_contract()
    fields = {f['name']:f for f in c['fields']}
    for name in FEATURE_NAMES:
        assert fields[name].get('temporal_class') == 'historical_event_data'
        assert fields[name].get('historical_training_approved') is True
        assert fields[name].get('publication_timestamp_required') is False
    for f in fields.values():
        if f['group'] in ('market','injuries_personnel','weather'):
            assert f['temporal_class']=='point_in_time_context_data'
            assert f['publication_timestamp_required'] and not f['historical_training_approved']
    bad = deepcopy(c)
    next(f for f in bad['fields'] if f['name']==FEATURE_NAMES[0])['temporal_class']='point_in_time_context_data'
    with pytest.raises(ValueError,match='temporal'):
        validation.validate_contract(bad)


def test_oracle_rejects_forged_early_release_of_unfinished_event(tmp_path):
    _, manifest = fixture(tmp_path)
    manifest['g1'].update(event())
    manifest['g1']['available_at']='2025-09-07T17:00:00+00:00'
    with pytest.raises(ValueError,match='temporal'):
        LabelOracle(tmp_path,manifest).reveal('g1','2025-09-07T18:00:00+00:00',{'g1'})


def test_eligibility_preserves_season_quality_and_legacy_replay_gates(tmp_path):
    from kickedge.features.prepare import prepare
    from kickedge.features.materialize import build
    config, _ = source_fixture(tmp_path)
    prep = prepare(config)
    manifest = json.loads((prep/'manifest.json').read_text())
    # Labels are attached after freeze; eligibility must still respect audit gates.
    path=prep/'outcomes'/manifest['g7']['filename']
    targets=json.loads(path.read_text())
    targets[0]['target_season_eligible']=False
    write_json(path,targets)
    manifest['g7']['sha256']=sha256_file(path)
    write_json(prep/'manifest.json',manifest)
    source=json.loads((prep/'source.json').read_text())
    source['manifest_sha256']=sha256_file(prep/'manifest.json')
    write_json(prep/'source.json',source)
    directory=build(config,prep)
    rows=json.loads((directory/'kicker_game_features.json').read_text())
    assert all(r['features_temporally_verified'] for r in rows)
    assert all(r['eligible_for_final_training'] for r in rows[:-1])
    assert not rows[-1]['eligible_for_final_training']
    assert rows[-1]['training_exclusion_reasons']==['outside_target_seasons']
    # Previously experimental inputs must not be promoted silently by new code.
    source['inputs']['policy']={'availability':'experimental_result_plus_24h'}
    write_json(prep/'source.json',source)
    legacy=build(config,prep)
    old=json.loads((legacy/'kicker_game_features.json').read_text())
    assert not any(r['eligible_for_final_training'] or r['features_temporally_verified'] for r in old)


@pytest.mark.parametrize('change,reason', [
    ({'statistical_label_usable':False},'unusable_target_label'),
    ({'id_in_players':False},'identity_problem'),
])
def test_temporal_approval_does_not_override_bad_target_or_identity(tmp_path,change,reason):
    from kickedge.features.prepare import prepare
    from kickedge.features.materialize import build
    config,_=source_fixture(tmp_path)
    prep=prepare(config)
    manifest=json.loads((prep/'manifest.json').read_text())
    path=prep/'outcomes'/manifest['g7']['filename']
    targets=json.loads(path.read_text())
    targets[0].update(change)
    write_json(path,targets)
    manifest['g7']['sha256']=sha256_file(path)
    write_json(prep/'manifest.json',manifest)
    source=json.loads((prep/'source.json').read_text())
    source['manifest_sha256']=sha256_file(prep/'manifest.json')
    write_json(prep/'source.json',source)
    directory=build(config,prep)
    row=json.loads((directory/'kicker_game_features.json').read_text())[-1]
    assert row['features_temporally_verified']
    assert not row['eligible_for_final_training']
    assert row['training_exclusion_reasons']==[reason]
