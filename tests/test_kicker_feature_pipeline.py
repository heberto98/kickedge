from datetime import timedelta
import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from kickedge.io import sha256_file, write_json, write_parquet, sql_literal
from test_kicker_features import fixture


def module(name):
    assert importlib.util.find_spec('kickedge.features.'+name) is not None, 'Feature pipeline not implemented'
    return importlib.import_module('kickedge.features.'+name)


def source_fixture(tmp_path):
    ids, manifest = fixture(tmp_path, n=7)
    config = SimpleNamespace(root=tmp_path, data_dir=tmp_path/'data', reports_dir=tmp_path/'reports')
    base = config.data_dir/'processed/base'
    base.mkdir(parents=True)
    labels, games, clocks = [], [], []
    for i in ids:
        stats = json.loads((tmp_path/manifest[i['game_id']]['filename']).read_text())[0]
        labels.append({**{k:v for k,v in i.items() if k not in ('kickoff','prediction_cutoff')}, **stats, 'player_id': i['kicker_id'], 'label_status': 'agreed',
                       'id_in_players': True, 'schedule_identity_ok': True,
                       'eligible_for_pregame_training': False, 'target_season_eligible': True, 'multiple_kicking_participants': False})
        games.append({k: i[k] for k in ['game_id','season','week','game_type']} |
                     dict(gameday=i['kickoff'][:10], gametime='13:00', home_team='A', away_team='B'))
        from kickedge.features.kicker import instant
        dt = instant(i['kickoff'])
        clocks.append(dict(game_id=i['game_id'], start_time=dt.strftime('%m/%d/%y, 13:00:00'), desc='END GAME', play_deleted=0,
                           time_of_day=(dt+timedelta(hours=3)).isoformat()))
    with duckdb.connect() as con:
        for name, rows in [('labels',labels),('games',games),('pbp',clocks)]:
            p = base/(name+'.json');write_json(p,rows)
            write_parquet(con, f'SELECT * FROM read_json_auto({sql_literal(str(p))},convert_strings_to_integers=false)',base/(name+'.parquet'))
    write_json(base/'build.json', {'artifacts':[dict(path=str(base/(n+'.parquet')),sha256=sha256_file(base/(n+'.parquet'))) for n in ['labels','games']]})
    write_json(base/'source_lock.json', {'sources':[dict(dataset='pbp',season=2025,path=str((base/'pbp.parquet').relative_to(tmp_path)),
        sha256=sha256_file(base/'pbp.parquet'),downloaded_at='2026-09-26T00:00:00+00:00')]})
    write_json(config.data_dir/'processed/latest.json', {'path':'data/processed/base'})
    return config, base


def test_materialization_reproducible_and_preserves_targets_flags(tmp_path):
    config, base = source_fixture(tmp_path)
    prep = module('prepare').prepare(config)
    p = module('materialize').build(config, prep)
    first = {x.name:sha256_file(x) for x in p.iterdir() if x.is_file()}
    again = module('materialize').build(config, prep)
    assert again == p
    assert first == {x.name:sha256_file(x) for x in again.iterdir() if x.is_file()}
    rows = json.loads((p/'kicker_game_features.json').read_text())
    assert len(rows)==7 and rows[3]['xpm']==4 and rows[3]['previous_game_xpm']==3
    assert rows[3]['source_label']['multiple_placekickers'] is False
    assert all(r['features_temporally_verified'] and r['eligible_for_final_training'] for r in rows)
    assert rows[3]['features_technically_reconstructible']
    con=duckdb.connect()
    assert con.execute('select count(*) from read_parquet(?)',[str(p/'kicker_game_features.parquet')]).fetchone()[0]==7


def test_prepared_target_file_removal_does_not_block_prediction(tmp_path):
    config, _ = source_fixture(tmp_path)
    prep = module('prepare').prepare(config)
    manifest=json.loads((prep/'manifest.json').read_text())
    ids=json.loads((prep/'identities.json').read_text())
    from kickedge.features.kicker import LabelOracle, simulate
    before=simulate(ids,LabelOracle(prep/'outcomes',manifest),lambda e:None,stop_at='g4')
    (prep/'outcomes'/manifest['g4']['filename']).unlink()
    after=simulate(ids,LabelOracle(prep/'outcomes',manifest),lambda e:None,stop_at='g4')
    assert before==after


def test_contract_validation_rejects_target_as_predictor_and_wrong_runtime_values():
    from kickedge.features import load_contract
    from kickedge.features.kicker import FEATURE_NAMES
    validator=module('validation')
    contract=load_contract()
    validator.validate_contract(contract)
    fields={f['name']:f for f in contract['fields']}
    assert all(fields[n]['implemented'] and fields[n]['predictive_input_allowed'] for n in FEATURE_NAMES)
    fields['xpm']['predictive_input_allowed']=True
    with pytest.raises(ValueError,match='predict'):
        validator.validate_contract(contract)


def test_input_hash_mismatch_is_rejected(tmp_path):
    config, base = source_fixture(tmp_path)
    with (base/'labels.parquet').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='integrity'):
        module('prepare').prepare(config)


def test_prepare_winter_actual_kickoff_delay_keeps_original_cutoff(tmp_path):
    config, base = source_fixture(tmp_path)
    with duckdb.connect() as con:
        con.execute('CREATE TABLE games AS SELECT * FROM read_parquet(?)',[str(base/'games.parquet')])
        con.execute("UPDATE games SET gameday='2025-12-07' WHERE game_id='g7'")
        write_parquet(con,'SELECT * FROM games',base/'games.parquet')
        con.execute('CREATE TABLE pbp AS SELECT * FROM read_parquet(?)',[str(base/'pbp.parquet')])
        con.execute("UPDATE pbp SET start_time='12/07/25, 14:00:00',time_of_day='2025-12-07T22:00:00Z' WHERE game_id='g7'")
        write_parquet(con,'SELECT * FROM pbp',base/'pbp.parquet')
    meta=json.loads((base/'build.json').read_text())
    for artifact in meta['artifacts']:
        artifact['sha256']=sha256_file(Path(artifact['path']))
    write_json(base/'build.json',meta)
    lock=json.loads((base/'source_lock.json').read_text())
    lock['sources'][0]['sha256']=sha256_file(base/'pbp.parquet')
    write_json(base/'source_lock.json',lock)
    prep=module('prepare').prepare(config)
    row=next(r for r in json.loads((prep/'identities.json').read_text()) if r['game_id']=='g7')
    assert row['kickoff']=='2025-12-07T19:00:00+00:00'  # 14 Eastern, winter UTC-5
    assert row['prediction_cutoff']=='2025-12-07T17:00:00+00:00'  # scheduled 13 Eastern minus 1h


def test_real_materialization_matches_independent_sql_and_preserves_population():
    root=Path(__file__).resolve().parents[1]
    pointer=root/'data/features/kicker/latest.json'
    if not pointer.exists():
        pytest.skip('Materialize Phase 1 locally to audit historical data')
    directory=root/json.loads(pointer.read_text())['path']
    metadata=json.loads((directory/'build.json').read_text())
    prep=root/'data/features/kicker_inputs'/metadata['inputs']['prepared_build']
    base=root/'data/processed'/metadata['inputs']['historical_build']
    rows=json.loads((directory/'kicker_game_features.json').read_text())
    manifest=json.loads((prep/'manifest.json').read_text())
    con=duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute('CREATE TABLE ids AS SELECT * FROM read_json_auto(?)',[str(prep/'identities.json')])
    con.execute('CREATE TABLE labels AS SELECT * FROM read_parquet(?)',[str(base/'labels.parquet')])
    con.execute('CREATE TABLE clocks(game_id VARCHAR,last_event TIMESTAMPTZ)')
    con.executemany('INSERT INTO clocks VALUES (?,?)',[(g,s['last_event']) for g,s in manifest.items()])
    con.execute('''CREATE TABLE previous AS SELECT g.game_id,g.team,g.kicker_id,h.game_id prior_id,
        h.team prior_team,h.kickoff::TIMESTAMPTZ prior_kickoff,l.xpa,l.xpm,
        row_number() OVER(PARTITION BY g.game_id,g.team,g.kicker_id
            ORDER BY h.kickoff::TIMESTAMPTZ DESC,h.game_id DESC,h.team DESC) rn
        FROM ids g JOIN ids h ON g.kicker_id=h.kicker_id AND g.season=h.season
        JOIN clocks c ON c.game_id=h.game_id
        JOIN labels l ON l.game_id=h.game_id AND l.team=h.team AND l.player_id=h.kicker_id
        WHERE h.kickoff::TIMESTAMPTZ < g.kickoff::TIMESTAMPTZ
          AND greatest(h.kickoff::TIMESTAMPTZ+INTERVAL '24 hours',c.last_event) <= g.prediction_cutoff::TIMESTAMPTZ''')
    ref=con.execute('''SELECT g.game_id,g.team,g.kicker_id,count(p.prior_id),coalesce(sum(xpa),0),coalesce(sum(xpm),0),
        sum(xpa) FILTER(WHERE rn<=3),sum(xpm) FILTER(WHERE rn<=3),
        sum(xpa) FILTER(WHERE rn<=5),sum(xpm) FILTER(WHERE rn<=5),
        max(xpa) FILTER(WHERE rn=1),max(xpm) FILTER(WHERE rn=1),
        epoch(g.prediction_cutoff::TIMESTAMPTZ-max(prior_kickoff))/86400,
        list(prior_id ORDER BY prior_kickoff,prior_id,prior_team) FILTER(WHERE prior_id IS NOT NULL)
        FROM ids g LEFT JOIN previous p USING(game_id,team,kicker_id)
        GROUP BY g.game_id,g.team,g.kicker_id,g.prediction_cutoff''').fetchall()
    by_key={(r['game_id'],r['team'],r['kicker_id']):r for r in rows}
    original=con.execute('SELECT game_id,team,player_id,xpa,xpm,multiple_placekickers,multiple_kicking_participants FROM labels').fetchall()
    assert set(by_key)=={r[:3] for r in original} and len(rows)==len(original)==6083
    for g,t,k,a,m,multiple,kicking in original:
        row=by_key[g,t,k]
        assert row['xpm']==m and row['source_label']['xpa']==a
        assert row['multiple_kickers_flag']==multiple
        assert row['source_label']['multiple_kicking_participants']==kicking
        assert row['features_temporally_verified'] is True
        assert row['eligible_for_final_training'] == row['source_label']['target_season_eligible']
    for g,t,k,n,a,m,a3,m3,a5,m5,pa,pm,days,history_ids in ref:
        expected=dict(kicker_games_before=n,kicker_xpa_before=a,kicker_xpm_before=m,
            kicker_xp_conversion_rate_before=m/a if a else None,
            kicker_xpm_per_game_before=m/n if n else None,kicker_xpa_per_game_before=a/n if n else None,
            kicker_xpa_last_3=a3 if n>=3 else None,kicker_xpm_last_3=m3 if n>=3 else None,
            kicker_xp_conversion_last_3=m3/a3 if n>=3 and a3 else None,kicker_xpm_per_game_last_3=m3/3 if n>=3 else None,
            kicker_xpa_last_5=a5 if n>=5 else None,kicker_xpm_last_5=m5 if n>=5 else None,
            kicker_xp_conversion_last_5=m5/a5 if n>=5 and a5 else None,kicker_xpm_per_game_last_5=m5/5 if n>=5 else None,
            previous_game_xpa=pa,previous_game_xpm=pm,days_since_last_game=days,
            kicker_has_prior_game=n>0,kicker_has_3_prior_games=n>=3,kicker_has_5_prior_games=n>=5,kicker_low_sample_flag=n<5)
        row=by_key[g,t,k]
        for name,value in expected.items():
            if type(value) is float:
                assert row[name]==pytest.approx(value), (g,t,k,name)
            else:
                assert row[name]==value, (g,t,k,name)
        assert [h['game_id'] for h in row['feature_provenance']['history']]==(history_ids or [])
    con.close()


def test_real_freeze_reveal_chain_and_all_artifact_hashes():
    import hashlib
    root=Path(__file__).resolve().parents[1]
    pointer=root/'data/features/kicker/latest.json'
    if not pointer.exists():
        pytest.skip('Materialize Phase 1 locally')
    directory=root/json.loads(pointer.read_text())['path']
    meta=json.loads((directory/'build.json').read_text())
    for artifact in meta['artifacts']:
        assert sha256_file(directory/artifact['filename'])==artifact['sha256']
    chain,frozen='0'*64,set()
    with (directory/'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            event=json.loads(line)
            assert event['previous_sha256']==chain
            content={k:v for k,v in event.items() if k!='event_sha256'}
            chain=hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()
            assert chain==event['event_sha256']
            if event['kind']=='freeze':
                frozen.add(event['game_id'])
            else:
                assert event['game_id'] in frozen
                from kickedge.features.kicker import instant
                assert instant(event['available_at'])<=instant(event['decision_time'])
    assert len(frozen)==3028
    assert chain==json.loads((directory/'freeze.json').read_text())['event_chain_final_sha256']
