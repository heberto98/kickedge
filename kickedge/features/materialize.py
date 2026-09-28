"""Materialize kicker features offline, then attach targets after the freeze."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform

import duckdb

from kickedge.io import sha256_file, sql_literal, write_json, write_parquet
from . import load_contract
from .kicker import FEATURE_NAMES, LabelOracle, key, simulate, instant
from .validation import validate_contract, validate_rows
from .temporal import HISTORICAL_EVENT, POLICY_VERSION, temporal_evidence_valid


def summarize(rows):
    total = len(rows)
    coverage = {name: {'non_null':sum(r[name] is not None for r in rows),
                      'null':sum(r[name] is None for r in rows),
                      'coverage_pct':100*sum(r[name] is not None for r in rows)/total if total else None}
                for name in FEATURE_NAMES}
    histogram = Counter(r['kicker_games_before'] for r in rows)
    examples = {}
    predicates = {
        'first_observed_game_not_necessarily_rookie': lambda r:r['kicker_games_before']==0,
        'long_history':lambda r:r['kicker_games_before']==max(histogram,default=0),
        'team_change':lambda r:bool(r['feature_provenance']['history']) and r['feature_provenance']['history'][-1]['team']!=r['team'],
        'zero_xpm':lambda r:r['xpm']==0,
        'multiple_or_unusual':lambda r:r['multiple_kickers_flag'] or r['source_label'].get('multiple_kicking_participants')}
    used = set()
    for title, predicate in predicates.items():
        options = [r for r in rows if predicate(r)]
        if title == 'zero_xpm':
            options.sort(key=lambda r:r['kicker_games_before'] < 3)
        elif title == 'multiple_or_unusual':
            options.sort(key=lambda r:not r['multiple_kickers_flag'])
        r = next((r for r in options if key(r) not in used), options[0] if options else None)
        if r:
            used.add(key(r))
            examples[title] = {k:r[k] for k in ('game_id','team','kicker_id','kicker_name','season','week','kickoff','prediction_cutoff','xpm','multiple_kickers_flag')} | {
                'features':{name:r[name] for name in FEATURE_NAMES}, 'provenance':r['feature_provenance']}
        else:
            examples[title] = None
    return {'rows':total,'coverage':coverage,'games_before_histogram':dict(sorted(histogram.items())),
        'sample_groups':{'0':histogram[0],'1-2':sum(v for k,v in histogram.items() if 1<=k<=2),
                         '3-4':sum(v for k,v in histogram.items() if 3<=k<=4),
                         '5+':sum(v for k,v in histogram.items() if k>=5)},
        'technically_reconstructible':sum(r['features_technically_reconstructible'] for r in rows),
        'temporally_verified':sum(r['features_temporally_verified'] for r in rows),
        'training_eligible':sum(r['eligible_for_final_training'] for r in rows),
        'training_exclusions':dict(Counter(reason for r in rows for reason in r['training_exclusion_reasons'])),
        'temporal_policy':rows[0]['temporal_policy'] if rows else None,
        'unavailable_history_rows':sum(r['history_unavailable_before_cutoff'] for r in rows),
        'multiple_placekicker_rows':sum(r['multiple_kickers_flag'] for r in rows),
        'manual_examples':examples}


def report(config, directory, summary):
    config.reports_dir.mkdir(parents=True,exist_ok=True)
    write_json(config.reports_dir/'kicker_features_phase1.json',{'build_id':directory.name,**summary})
    lines = ['# Fase 1 — features del kicker', '', f'Build `{directory.name}`. Filas: **{summary["rows"]}**.', '',
        f'Política temporal: `{summary["temporal_policy"]}`. Eventos terminados antes del cutoff no requieren '
        'fecha de publicación del archivo retrospectivo; el contexto point-in-time conserva ese requisito. '
        f'Filas conformes temporalmente: {summary["temporally_verified"]}; elegibles para entrenamiento histórico de Fase 1: {summary["training_eligible"]}.',
        'Se mantiene el margen conservador +24 h para incorporar eventos. No representa una fecha de publicación. '
        '2015 permanece como reserva histórica; las temporadas objetivo son 2016–2025. Los snapshots experimentales anteriores permanecen sin modificar.', '',
        '| Feature | No NULL | NULL | Cobertura |','|---|---:|---:|---:|']
    for name,c in summary['coverage'].items():
        lines.append(f'| {name} | {c["non_null"]} | {c["null"]} | {c["coverage_pct"]:.2f}% |')
    lines += ['', 'Distribución de partidos previos: '+', '.join(f'{k}: {v}' for k,v in summary['sample_groups'].items())+'.',
              'Histograma completo: `kicker_features_phase1.json`.', '', '## Ejemplos para auditoría', '',
              '| Caso | Game / team / kicker | Previos | XPA/XPM previos | Últimos 3 XPA/XPM | XPM target |',
              '|---|---|---:|---|---|---:|']
    for title,r in summary['manual_examples'].items():
        if r:
            f=r['features']
            lines.append(f'| {title} | {r["game_id"]} / {r["team"]} / {r["kicker_name"]} | {f["kicker_games_before"]} | '
                         f'{f["kicker_xpa_before"]}/{f["kicker_xpm_before"]} | {f["kicker_xpa_last_3"]}/{f["kicker_xpm_last_3"]} | {r["xpm"]} |')
    lines += ['', 'El JSON adjunto conserva partidos, valores y hashes que contribuyen a cada ejemplo. '
              'Primer partido significa primera observación de esa temporada, no prueba de rookie. '
              'Los flags originales y el target se adjuntan después de congelar todas las features, bajo `source_label`. '
              'La matriz predictiva usa exclusivamente las 21 columnas declaradas en el contrato.', '',
              'Historia global del kicker: cambiar de equipo no reinicia sus métricas personales. '
              'Una historia kicker+team descartaría evidencia reciente del mismo ejecutor; puede ser útil para contexto del equipo en otra fase. '
              'Esta fase usa `(season, kicker_id)` y no mezcla temporadas.', '',
              'Reproducción: `python -m kickedge.features prepare`, luego `python -m kickedge.features build`. '
              'El comando prepare consume únicamente el build histórico y el PBP ya cacheado; el builder solo recibe identidades '
              'y resultados revelados de partidos anteriores. No se modifica el pipeline ni el snapshot histórico original.']
    (config.reports_dir/'kicker_features_phase1.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def build(config, prepared=None):
    if prepared is None:
        prepared = config.root/json.loads((config.data_dir/'features/kicker_inputs/latest.json').read_text())['path']
    prepared=Path(prepared)
    source=json.loads((prepared/'source.json').read_text())
    for filename,hashkey in [('identities.json','identities_sha256'),('manifest.json','manifest_sha256')]:
        if sha256_file(prepared/filename)!=source[hashkey]:
            raise ValueError('Prepared input integrity failure')
    contract=load_contract()
    validate_contract(contract)
    code={p.name:sha256_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    inputs={'prepared_source_sha256':sha256_file(prepared/'source.json'), 'prepared_build':prepared.name,
            'contract_sha256':sha256_file(Path(__file__).parent/'contract.json'), 'code_sha256':code,
            'python':platform.python_version(),'duckdb':duckdb.__version__,'historical_build':source['inputs']['historical_build']}
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    directory=config.data_dir/'features/kicker'/digest
    directory.mkdir(parents=True,exist_ok=True)
    identities=json.loads((prepared/'identities.json').read_text())
    manifest=json.loads((prepared/'manifest.json').read_text())
    oracle=LabelOracle(prepared/'outcomes',manifest)
    chain='0'*64
    with (directory/'events.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        def sink(event):
            nonlocal chain
            payload={'previous_sha256':chain,**event}
            chain=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            stream.write(json.dumps({**payload,'event_sha256':chain},sort_keys=True)+'\n')
            stream.flush()
        rows=simulate(identities,oracle,sink)
    validate_rows(rows,contract)
    feature_path=directory/'features_frozen.json'
    write_json(feature_path,rows)
    feature_sha=sha256_file(feature_path)
    write_json(directory/'freeze.json',{'inputs':inputs,'features_sha256':feature_sha,
        'event_chain_final_sha256':chain,'events_sha256':sha256_file(directory/'events.jsonl')})
    # Only now attach targets/audit flags. This phase cannot feed the builder.
    targets={}
    for game,spec in sorted(manifest.items()):
        path=prepared/'outcomes'/spec['filename']
        if sha256_file(path)!=spec['sha256']:
            raise ValueError('Target attachment integrity failure')
        for target in json.loads(path.read_text(encoding='utf-8')):
            targets[key(target)]=target
    if set(targets)!={key(r) for r in rows}:
        raise ValueError('Target population differs from frozen identities')
    dataset=[]
    for r in rows:
        label=targets[key(r)]
        policy=source['inputs']['policy']
        approved_policy=(policy.get('temporal_policy')==POLICY_VERSION and policy.get('temporal_class')==HISTORICAL_EVENT
                         and policy.get('historical_training_approved') is True)
        history=r['feature_provenance']['history']
        temporal_ok=approved_policy and all(h.get('temporal_class')==HISTORICAL_EVENT and
            temporal_evidence_valid(h,instant(r['prediction_cutoff'])) for h in history)
        technical=not r['history_unavailable_before_cutoff'] and not r['feature_provenance']['unusable_prior_game_ids']
        identity_problem=not label.get('id_in_players',False) or not label.get('schedule_identity_ok',False)
        reasons=[]
        if not temporal_ok: reasons.append('temporal_policy_not_approved')
        if not technical: reasons.append('history_incomplete_or_unusable')
        if not label.get('target_season_eligible',False): reasons.append('outside_target_seasons')
        if not label['statistical_label_usable']: reasons.append('unusable_target_label')
        if identity_problem: reasons.append('identity_problem')
        dataset.append({**r,'xpm':label['xpm'],'source_label':label,
            'multiple_kickers_flag':bool(label.get('multiple_placekickers')),
            'unusual_substitution_flag':None,
            'identity_problem_flag':identity_problem,
            'label_quality_flag':not label['statistical_label_usable'] or label.get('label_status')!='agreed',
            'features_technically_reconstructible':technical,
            'temporal_policy':POLICY_VERSION if approved_policy else 'legacy_experimental_replay',
            'features_temporally_verified':temporal_ok,'eligible_for_final_training':not reasons,
            'training_exclusion_reasons':reasons})
    if sha256_file(feature_path)!=feature_sha:
        raise ValueError('Frozen features changed during target attachment')
    write_json(directory/'kicker_game_features.json',dataset)
    write_json(directory/'contract.json',contract)
    with duckdb.connect() as con:
        write_parquet(con,f"SELECT * FROM read_json_auto({sql_literal(str(directory/'kicker_game_features.json'))}, sample_size=-1, maximum_object_size=4000000)",directory/'kicker_game_features.parquet')
    summary=summarize(dataset)
    write_json(directory/'summary.json',summary)
    write_json(directory/'build.json',{'build_id':digest,'inputs':inputs,'row_count':len(rows),
        'artifacts':[{'filename':p.name,'sha256':sha256_file(p)} for p in sorted(directory.iterdir()) if p.is_file() and p.name!='build.json']})
    write_json(config.data_dir/'features/kicker/latest.json',{'build_id':digest,'path':directory.relative_to(config.root).as_posix()})
    report(config,directory,summary)
    return directory
