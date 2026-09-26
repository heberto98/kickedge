"""Build/evaluate the sequential experiment and export complete policy comparisons."""
import hashlib
import json

import duckdb

from kickedge.io import sha256_file, write_json, write_parquet, sql_literal
from .build import build, markdown_table
from .evaluate import evaluate, summarize
from .history import OutcomeOracle
from .sequential import SEQUENTIAL_POLICY, simulate


def stats(rows):
    if not rows:
        return None
    s = summarize(rows)['total']
    s['expected_xpa_zero'] = sum(r['xpa'] == 0 for r in rows)
    s['multiple_pregame_candidates'] = sum(len(r['expected_kicker_candidates']) > 1 for r in rows)
    return s


def comparison_report(config, directory, metrics, evaluated):
    headers = ['Política', 'ID/6056', 'Cobertura', 'VERIFIED', 'STRONG', 'INFERRED', 'AMBIGUOUS', 'UNKNOWN', 'Matches/evaluables', 'Accuracy', 'Errores', 'XPA=0', 'XPM=0']
    table = []
    for p, m in metrics.items():
        s = m['total']
        table.append([p, s['identified'], f'{s["coverage_pct"]:.2f}%', *s['categories'].values(),
            f'{s["membership_matches"]}/{s["comparable"]}', f'{s["membership_accuracy_pct"]:.2f}%',
            s['comparisons'].get('mismatch', 0), s['expected_xpa_zero'], s['expected_xpm_zero']])
    text = '# Comparación secuencial de expected kicker\n\n'
    text += f'Build `{directory.name}`. Ver protocolo fijado en `docs/pregame_sequential_protocol.md`.\n\n'
    text += markdown_table(headers, table) + '\n\n'
    text += 'A: confirmación oficial. B: A + continuidad de dos partidos y rol actual coincidente. C: A + continuidad experimental, sin inventar verificación de disponibilidad actual. Todas las filas conservan `eligible_for_pregame_training=false` a la espera de revisión de política.\n\n'
    for p, m in metrics.items():
        text += f'## Política {p}: por temporada\n\n'
        text += markdown_table(['Año', 'Team-games', 'ID', 'Cobertura', 'Matches/evaluables', 'Accuracy', 'Discrepancias', 'Ambiguous', 'Unknown'],
            [[year, s['team_games'], s['identified'], f'{s["coverage_pct"]:.2f}%', f'{s["membership_matches"]}/{s["comparable"]}',
              f'{s["membership_accuracy_pct"]:.2f}%' if s['comparable'] else 'N/A', s['comparisons'].get('mismatch', 0), s['categories']['AMBIGUOUS'], s['categories']['UNKNOWN']]
             for year, s in m['seasons'].items()]) + '\n\n'
        text += markdown_table(['Cohorte', 'N', 'ID', 'Matches/evaluables', 'Discrepancias', 'Sin evidencia de patada', 'Label faltante'],
            [[label, s['team_games'], s['identified'], f'{s["membership_matches"]}/{s["comparable"]}', s['comparisons'].get('mismatch', 0),
              s['known_without_kicking_evidence'], s['expected_missing_label']] for label, s in m['cohorts'].items() if s]) + '\n\n'
    text += 'Accuracy: pertenencia del esperado al conjunto de ejecutores de PAT/FG, solo si hay identidad y algún intento real. No incluye UNKNOWN, AMBIGUOUS ni equipos sin intentos. Las fuentes y algunos casos ya habían sido inspeccionados: no es validación independiente.\n'
    (config.reports_dir / 'pregame_policy_comparison.md').write_text(text, encoding='utf-8')
    write_json(config.reports_dir / 'pregame_policy_comparison.json', metrics)
    lines = '# Todas las discrepancias del simulador secuencial\n\n'
    for p, rows in evaluated.items():
        mismatch = [r for r in rows if r['comparison'] == 'mismatch']
        lines += f'## Política {p} — {len(mismatch)} discrepancias\n\n'
        lines += markdown_table(['Game', 'Team', 'Esperado', 'Reales PAT/FG', 'Tipo', 'Último game conocido', 'Racha previa'],
            [[r['game_id'], r['team'], r['expected_kicker_name'], ', '.join(r['actual_placekicker_names']), r['inference_subtype'],
              r['prior_game_id'], r['prior_consecutive_games']] for r in mismatch]) + '\n\n'
    (config.reports_dir / 'pregame_sequential_mismatches.md').write_text(lines, encoding='utf-8')
    cases = '# Registro de ambigüedad y ausencia de patadas — política C\n\n'
    cases += 'Registro completo. Ausencia de evidencia de patadas no demuestra DNP ni autoriza convertir un label faltante en cero.\n\n'
    for title, group in [
        ('Ambiguos', [r for r in evaluated['C'] if r['expected_kicker_ambiguous']]),
        ('Esperado sin evidencia de patadas', [r for r in evaluated['C'] if r['expected_kicking_participation'] == 'no_kicking_evidence']),
        ('Sin ejecutor real de PAT/FG', [r for r in evaluated['C'] if r['comparison'] == 'no_actual_placekick'])]:
        cases += f'## {title} ({len(group)})\n\n'
        cases += markdown_table(['Game', 'Team', 'Esperado', 'Categoría', 'Candidatos pregame', 'Reales PAT/FG', 'XPA/XPM'],
            [[r['game_id'], r['team'], r['expected_kicker_name'] or 'NULL', r['expected_kicker_confidence'],
              ', '.join(sorted({c.get('name') or c.get('player_id') or 'sin ID' for c in r['expected_kicker_candidates']})),
              ', '.join(r['actual_placekicker_names']) or 'ninguno', f'{r["xpa"]}/{r["xpm"]}'] for r in group]) + '\n\n'
    (config.reports_dir / 'pregame_case_register.md').write_text(cases, encoding='utf-8')


def compare(config, policy_path, source_lock=None):
    baseline = build(config, policy_path, source_lock, identities_only=True)
    baseline_meta = json.loads((baseline / 'identity_build.json').read_text())
    base = config.data_dir / 'processed' / baseline_meta['inputs']['base_build']
    oracle_dir = config.data_dir / 'pregame/history_oracle' / base.name
    if not (oracle_dir / 'source.json').exists():
        raise ValueError('Prepare the game-partitioned oracle in a separate process: python -m kickedge.pregame prepare-history')
    oracle_source = json.loads((oracle_dir / 'source.json').read_text(encoding='utf-8'))
    historical_meta = json.loads((base / 'build.json').read_text(encoding='utf-8'))
    expected_totals_sha = next(a['sha256'] for a in historical_meta['artifacts'] if a['path'].endswith('/pbp_kicker_totals.parquet'))
    if (oracle_source['historical_build'] != base.name or
            oracle_source['source_hashes']['pbp_kicker_totals.parquet'] != expected_totals_sha or
            oracle_source['manifest_sha256'] != sha256_file(oracle_dir / 'manifest.json')):
        raise ValueError('Historical oracle provenance does not match the frozen source')
    oracle_manifest = json.loads((oracle_dir / 'manifest.json').read_text(encoding='utf-8'))
    oracle = OutcomeOracle(oracle_dir, oracle_manifest)
    baselines = json.loads((baseline / 'identities.json').read_text(encoding='utf-8'))
    with duckdb.connect() as con:
        names = dict(con.execute('SELECT player_id,display_name FROM read_parquet(?)', [str(base / 'players.parquet')]).fetchall())
    inputs = {'baseline_build': baseline.name, 'baseline_identity_sha256': sha256_file(baseline / 'identities.json'),
        'protocol': SEQUENTIAL_POLICY, 'oracle_manifest_sha256': sha256_file(oracle_dir / 'manifest.json'),
        'protocol_document_sha256': sha256_file(config.root / 'docs/pregame_sequential_protocol.md')}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]
    directory = config.data_dir / 'pregame/sequential' / digest
    directory.mkdir(parents=True, exist_ok=True)
    print(f'Simulating in chronological order: {digest}', flush=True)
    with (directory / 'events.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
        def sink(event):
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n')
            stream.flush()  # persisted freeze precedes any target oracle access
        predictions, event_sha = simulate(baselines, oracle, names, sink)
    frozen = {}
    for p, rows in predictions.items():
        identity = directory / f'identities_{p}.json'
        write_json(identity, rows)
        frozen[p] = sha256_file(identity)
    write_json(directory / 'freeze.json', {'inputs': inputs, 'identity_sha256': frozen,
        'event_chain_final_sha256': event_sha, 'event_file_sha256': sha256_file(directory / 'events.jsonl')})
    print('All policy identities frozen; starting outcome evaluation', flush=True)
    metrics, evaluated = {}, {}
    for p in predictions:
        rows = evaluate(directory / f'identities_{p}.json', frozen[p], base)
        for r in rows:
            prior, actual = set(r['previous_placekicker_ids']), set(r['actual_placekicker_ids'])
            r['actual_kicker_changed_since_prior_game'] = bool(prior != actual) if prior and actual else None
        evaluated[p] = rows
        m = summarize(rows)
        m['total'] = stats(rows)
        subsets = {
            'Week 1': [r for r in rows if r['week'] == 1],
            'Resto': [r for r in rows if r['week'] != 1],
            'Cambio de ejecutor real': [r for r in rows if r['actual_kicker_changed_since_prior_game'] is True],
            'Cambio real con único ejecutor actual': [r for r in rows if r['actual_kicker_changed_since_prior_game'] is True and len(r['actual_placekicker_ids']) == 1],
            'Sin cambio de ejecutor real': [r for r in rows if r['actual_kicker_changed_since_prior_game'] is False],
            'Múltiples ejecutores reales': [r for r in rows if r['actual_multiple_placekickers']],
            'Desarrollo 2015-2020': [r for r in rows if r['season'] <= 2020],
            'Evaluación temporal 2021-2024': [r for r in rows if 2021 <= r['season'] <= 2024],
            '2025 previamente inspeccionado': [r for r in rows if r['season'] == 2025],
            'Temporadas objetivo 2016-2025': [r for r in rows if r['season'] >= 2016],
        }
        m['cohorts'] = {key: stats(value) for key, value in subsets.items()}
        metrics[p] = m
        write_json(directory / f'labels_{p}.json', rows)
        with duckdb.connect() as con:
            query = f"""SELECT * REPLACE(prediction_cutoff::TIMESTAMPTZ AS prediction_cutoff,
                kickoff_utc::TIMESTAMPTZ AS kickoff_utc)
                FROM read_json_auto({sql_literal(str(directory / f'labels_{p}.json'))}, maximum_object_size=2000000)"""
            write_parquet(con, query, directory / f'labels_{p}.parquet')
    write_json(directory / 'metrics.json', metrics)
    write_json(directory / 'build.json', {'build_id': digest, 'inputs': inputs,
        'artifacts': [{'path': f.relative_to(config.root).as_posix(), 'sha256': sha256_file(f)} for f in sorted(directory.iterdir()) if f.name != 'build.json']})
    write_json(config.data_dir / 'pregame/sequential/latest.json', {'build_id': digest, 'path': directory.relative_to(config.root).as_posix()})
    comparison_report(config, directory, metrics, evaluated)
    print(json.dumps({p: m['total'] for p, m in metrics.items()}, indent=2), flush=True)
    return directory
