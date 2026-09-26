"""Reproducible two-phase reconstruction, isolated from historical label builds."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import platform
import tomllib

import duckdb

from kickedge.io import sha256_file, utc_now, write_json, write_parquet, sql_literal
from .evidence import collect
from .evaluate import evaluate, summarize
from .select import instant, select


def markdown_table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows])


def report(config, directory, summary, rows, inventory, checks):
    dest = config.reports_dir
    total = summary['total']
    table = []
    for season, s in summary['seasons'].items():
        table.append([season, s['team_games'], s['identified'], f'{s["coverage_pct"]:.2f}%',
            *s['categories'].values(), s['training_eligible'],
            f'{s["membership_matches"]}/{s["comparable"]}',
            f'{s["membership_accuracy_pct"]:.2f}%' if s['comparable'] else 'N/A'])
    header = ['Temporada', 'Team-games', 'ID', 'Cobertura', 'VERIFIED', 'STRONG', 'INFERRED',
              'AMBIGUOUS', 'UNKNOWN', 'Elegibles', 'Coincidencias/evaluables', 'Coincidencia']
    text = '# Reconstrucción prepartido T−60\n\n'
    text += f'Build: `{directory.name}`. Pipeline local; no entrenamiento.\n\n'
    text += markdown_table(header, table) + '\n\n'
    text += f'Total: {total["identified"]}/{total["team_games"]} identidades ({total["coverage_pct"]:.2f}%). '
    text += f'Solo {total["sufficient_identity"]} tienen evidencia VERIFIED/STRONG; {total["training_eligible"]} cumplen la política conservadora VERIFIED y label válido.\n\n'
    text += 'Las categorías son niveles de evidencia, no probabilidades. La cobertura mide lo reconstruido con las fuentes integradas; no es un límite superior de lo históricamente recuperable. Los casos oficiales son una muestra dirigida.\n\n'
    text += markdown_table(['Categoría', 'N', '% de todos los team-games'], [[c, n, f'{total["category_pct"][c]:.4f}%'] for c, n in total['categories'].items()]) + '\n\n'
    text += markdown_table(['Comparación', 'N'], total['comparisons'].items()) + '\n\n'
    text += f'Coincidencia de pertenencia: {total["membership_matches"]}/{total["comparable"]} = {total["membership_accuracy_pct"]:.4f}%. '
    text += f'Coincidencia de conjunto exacto: {total["exact_set_accuracy_pct"]:.4f}%. El denominador exige ID esperado y algún PAT/FG real. No cuenta UNKNOWN ni equipos sin PAT/FG. No es precisión predictiva fuera de muestra.\n\n'
    text += f'{total["multiple_actual"]} team-games tienen varios ejecutores reales de PAT/FG; {total["known_without_kicking_evidence"]} IDs esperados no tienen evidencia de ninguna patada (incluye kickoff). '
    text += 'No observar patadas no demuestra DNP; la participación total no puede determinarse con estas tablas.\n\n'
    text += f'{total["expected_xpm_zero"]} resultados esperados conservan XPM=0; {total["expected_missing_label"]} IDs esperados no tienen label individual validado y conservan NULL.\n\n'
    text += markdown_table(['Control', 'Resultado'], [(k, 'PASS' if v else 'FAIL') for k, v in checks.items()]) + '\n\n'
    text += 'La metodología, límites temporales y política de elegibilidad están en `docs/pregame_methodology.md`; evidencia fila por fila en el directorio del build.\n'
    (dest / 'pregame_validation.md').write_text(text, encoding='utf-8')
    write_json(dest / 'pregame_coverage.json', summary)
    inv = markdown_table(['Fuente', 'Año', 'Filas', 'Timestamp', 'Uso'],
        [[r['dataset'], r['season'], r['row_count'], r['timestamp_column'] or 'No disponible', r['selection_use']] for r in inventory])
    (dest / 'pregame_sources.md').write_text('# Inventario de fuentes\n\n' + inv + '\n\nLos hashes, URL, descarga y rangos de timestamps están en `source_inventory.json` del build. `date_modified` de lesiones no demuestra publicación pública.\n', encoding='utf-8')
    mismatches = [r for r in rows if r['comparison'] == 'mismatch']
    unusual = [r for r in rows if r['expected_kicker_id'] and (r['comparison'] in ('expected_among_multiple', 'no_actual_placekick') or r['expected_kicking_participation'] == 'no_kicking_evidence')]
    def table_for(group):
        return markdown_table(['Game', 'Equipo', 'Esperado', 'ID', 'Categoría', 'Reales PAT/FG', 'Comparación', 'XPA/XPM', 'Participación'],
            [[r['game_id'], r['team'], r['expected_kicker_name'], r['expected_kicker_id'], r['expected_kicker_confidence'], ', '.join(r['actual_placekicker_names']) or 'ninguno', r['comparison'], f'{r["xpa"]}/{r["xpm"]}', r['expected_kicking_participation']] for r in group])
    (dest / 'pregame_mismatches.md').write_text('# Todas las discrepancias\n\n' + table_for(mismatches) +
        '\n\n## Casos sin intento, múltiples ejecutores o sin participación de patada\n\n' + table_for(unusual) +
        '\n\nIDs reales proceden exclusivamente de la evaluación posterior al congelamiento. Ninguna discrepancia se usa para corregir la identidad.\n', encoding='utf-8')


def build(config, policy_path, source_lock=None, identities_only=False):
    settings = tomllib.loads(policy_path.read_text(encoding='utf-8'))
    policy = settings['policy']
    if policy['cutoff_minutes'] != 60 or policy['eligible_categories'] != ['VERIFIED']:
        raise ValueError('This reviewed policy version requires T-60 and VERIFIED-only eligibility')
    paths = {k: config.root / v for k, v in settings['sources'].items()}
    if source_lock:
        lock = json.loads(source_lock.read_text(encoding='utf-8'))
        nfl, official, registry = lock['nflverse'], lock['official'], lock['claims']
        base_pointer = lock['historical_build']
        if lock['policy'] != policy or lock['target_start_season'] != config.target_start_season:
            raise ValueError('Replay requires the same policy and target season')
    else:
        nfl = json.loads(paths['manifest'].read_text(encoding='utf-8'))
        official = json.loads(paths['official_manifest'].read_text(encoding='utf-8'))
        registry = json.loads(paths['claims'].read_text(encoding='utf-8'))
        base_pointer = json.loads((config.data_dir / 'processed/latest.json').read_text(encoding='utf-8'))
    base = config.root / base_pointer['path']
    base_metadata = json.loads((base / 'build.json').read_text(encoding='utf-8'))
    for artifact in base_metadata['artifacts']:
        if identities_only and Path(artifact['path']).name not in ('games.parquet', 'players.parquet'):
            continue  # no target outcome file is opened, even for a hash check
        if sha256_file(config.root / artifact['path']) != artifact['sha256']:
            raise ValueError('Historical artifact changed')
    code = {p.relative_to(config.root).as_posix(): sha256_file(p) for p in sorted((config.root / 'kickedge').rglob('*.py'))}
    inputs = {'policy': policy, 'claims_sha256': hashlib.sha256(json.dumps(registry, sort_keys=True).encode()).hexdigest(), 'code': code,
        'runtime': {'python': platform.python_version(), 'duckdb': duckdb.__version__},
        'target_start_season': config.target_start_season,
        'base_build': base_pointer['build_id'], 'base_metadata_sha256': sha256_file(base / 'build.json'),
        'sources': sorted(s['sha256'] for s in nfl['sources']),
        'official': sorted(s['sha256'] for s in official['sources'])}
    build_id = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]
    directory = config.data_dir / 'pregame/processed' / build_id
    games, evidence, inventory, diagnostics = collect(config, base, policy, nfl, official, registry)
    identities, ledger = [], []
    for g in games:
        g['target_season_eligible'] = g['season'] >= config.target_start_season
        row, log = select(g, evidence[g['game_id'], g['team']], policy)
        identities.append(row)
        ledger.extend(log)
    checks = {
        'one_row_per_team_game': len(games) == len({(r['game_id'], r['team']) for r in identities}),
        'two_teams_per_game': len(games) == 2 * len({r['game_id'] for r in games}),
        'exact_T_minus_60': all(instant(r['kickoff_utc']) - instant(r['prediction_cutoff']) == timedelta(minutes=60) for r in identities),
        'unknown_and_ambiguous_have_no_identity': all(r['expected_kicker_id'] is None for r in identities if r['expected_kicker_confidence'] in ('UNKNOWN', 'AMBIGUOUS')),
        'known_id_has_provenance': all(r['expected_kicker_evidence_ids'] for r in identities if r['expected_kicker_id']),
        'all_accepted_timestamps_before_cutoff': all(instant(e['available_at']) <= instant(next(r['prediction_cutoff'] for r in identities if (r['game_id'], r['team']) == (e['game_id'], e['team']))) for e in ledger if e['admissible']),
    }
    if not all(checks.values()):
        raise ValueError(checks)
    # Phase 1 persistence completes before any target-game outcome is loaded.
    directory.mkdir(parents=True, exist_ok=True)
    identity_path = directory / 'identities.json'
    if identity_path.exists() and json.loads(identity_path.read_text(encoding='utf-8')) != identities:
        raise ValueError('Non-deterministic reconstruction for the same inputs')
    write_json(identity_path, identities)
    identity_sha = sha256_file(identity_path)
    write_json(directory / 'evidence.json', ledger)
    write_json(directory / 'freeze.json', {'identity_sha256': identity_sha, 'frozen_at': utc_now(), 'inputs': inputs,
        'evidence_sha256': sha256_file(directory / 'evidence.json')})
    write_json(directory / 'source_inventory.json', inventory)
    write_json(directory / 'snapshot_diagnostics.json', diagnostics)
    write_json(directory / 'source_lock.json', {'nflverse': nfl, 'official': official, 'claims': registry,
        'historical_build': base_pointer, 'policy': policy, 'target_start_season': config.target_start_season})
    for relative in code:
        saved = directory / 'pipeline_source' / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes((config.root / relative).read_bytes())
    write_json(directory / 'effective_policy.json', settings)
    write_json(directory / 'identity_build.json', {'build_id': build_id, 'inputs': inputs,
        'identity_sha256': identity_sha, 'checks': checks})
    print(f'Identities frozen: {build_id}; SHA256 {identity_sha}', flush=True)
    if identities_only:
        return directory
    # Imports in evaluate.py are the only place that retrieves outcome columns.
    rows = evaluate(identity_path, identity_sha, base)
    checks['evaluation_did_not_mutate_identity'] = sha256_file(identity_path) == identity_sha
    checks['missing_labels_stay_null'] = all(r['xpm'] is None and r['xpa'] is None for r in rows if r['outcome_source'] == 'missing_validated_player_label')
    checks['training_policy_enforced'] = all(r['expected_kicker_confidence'] == 'VERIFIED' and r['xpm'] is not None and r['target_season_eligible'] for r in rows if r['eligible_for_pregame_training'])
    checks['evaluation_preserves_population'] = len(rows) == len(identities)
    if not all(checks.values()):
        raise ValueError(checks)
    write_json(directory / 'expected_kicker_labels.json', rows)
    summary = summarize(rows)
    write_json(directory / 'summary.json', summary)
    with duckdb.connect() as con:
        # Preserve timezone-aware cutoff fields explicitly in the Parquet export.
        query = f"""SELECT * REPLACE(prediction_cutoff::TIMESTAMPTZ AS prediction_cutoff,
            kickoff_utc::TIMESTAMPTZ AS kickoff_utc,
            expected_kicker_evidence_timestamp::TIMESTAMPTZ AS expected_kicker_evidence_timestamp)
            FROM read_json_auto({sql_literal(str(directory / 'expected_kicker_labels.json'))}, maximum_object_size=2000000)"""
        write_parquet(con, query, directory / 'expected_kicker_labels.parquet')
    artifacts = [{'path': p.relative_to(config.root).as_posix(), 'sha256': sha256_file(p)} for p in sorted(directory.rglob('*')) if p.is_file() and p != directory / 'build.json']
    write_json(directory / 'build.json', {'build_id': build_id, 'created_at': utc_now(), 'inputs': inputs,
        'checks': checks, 'artifacts': artifacts, 'identity_sha256': identity_sha})
    write_json(config.data_dir / 'pregame/processed/latest.json', {'build_id': build_id, 'path': directory.relative_to(config.root).as_posix()})
    report(config, directory, summary, rows, inventory, checks)
    print(json.dumps(summary['total'], indent=2), flush=True)
    return directory
