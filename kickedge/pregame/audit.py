"""Replay reviewed cases and expose every pregame support record for inspection."""
import json

from kickedge.io import write_json
from .build import markdown_table


def inspect(config, game, team, policy='C'):
    pointer = json.loads((config.data_dir / 'pregame/sequential/latest.json').read_text())
    directory = config.root / pointer['path']
    identities = json.loads((directory / f'identities_{policy}.json').read_text(encoding='utf-8'))
    r = next(r for r in identities if r['game_id'] == game and r['team'] == team)
    # This command intentionally does not open labels or evaluation outcomes.
    meta = json.loads((directory / 'build.json').read_text())
    base = config.data_dir / 'pregame/processed' / meta['inputs']['baseline_build']
    evidence = json.loads((base / 'evidence.json').read_text(encoding='utf-8'))
    return {'identity': r, 'evidence': [e for e in evidence if e['game_id'] == game and e['team'] == team],
            'freeze_sha256': json.loads((directory / 'freeze.json').read_text())['identity_sha256'][policy]}


def audit(config):
    pointer = json.loads((config.data_dir / 'pregame/sequential/latest.json').read_text())
    directory = config.root / pointer['path']
    rows = json.loads((directory / 'labels_C.json').read_text(encoding='utf-8'))
    cases = json.loads((config.root / 'audits/pregame_cases.json').read_text(encoding='utf-8'))
    text = '# Auditoría manual pregame — política C\n\n'
    text += 'Casos dirigidos; no muestra aleatoria ni estimación independiente de precisión. Decisiones de A/B se consultan con el comando inspect.\n\n'
    results = []
    for case in cases:
        r = next(r for r in rows if r['game_id'] == case['game_id'] and r['team'] == case['team'])
        assert (r['expected_kicker_name'], r['expected_kicker_confidence']) == (case['expected'], case['category']), case
        trace = inspect(config, case['game_id'], case['team'])
        results.append({'case': case, 'decision': trace['identity'], 'evaluation': {k: r[k] for k in (
            'actual_placekicker_ids', 'actual_placekicker_names', 'comparison', 'xpa', 'xpm',
            'expected_observed_fga', 'expected_observed_kickoffs', 'expected_kicking_participation')}, 'passed': True})
        text += f'## {case["game_id"]} — {case["team"]}\n\n'
        text += f'Cutoff `{r["prediction_cutoff"]}`. Esperado: **{r["expected_kicker_name"] or "UNKNOWN"}**, {r["expected_kicker_confidence"]}. Racha previa: {r["prior_consecutive_games"]}.\n\n'
        text += case['finding'] + '\n\n'
        if r['history_evidence']:
            text += markdown_table(['Juego anterior', 'Revelación permitida', 'Jugadores'], [[h['game_id'], h['reveal_at'], ', '.join(h['placekicker_ids'])] for h in r['history_evidence'][:2]]) + '\n\n'
        if trace['evidence']:
            text += markdown_table(['Tipo', 'Fuente', 'Disponible / modificado', 'Aceptación'], [[e['kind'],
                f'[Fuente]({e["source_url"]})', str(e['available_at']), 'aceptada' if e['admissible'] else e['rejection_reason']]
                for e in trace['evidence']]) + '\n\n'
        text += f'Evaluación: {r["comparison"]}; reales PAT/FG: {", ".join(r["actual_placekicker_names"]) or "ninguno"}; XPA/XPM={r["xpa"]}/{r["xpm"]}; participación={r["expected_kicking_participation"]}.\n\n'
    text += '## Confirmación externa de no participación\n\n'
    text += 'Gonzalez (2021_15_CAR_BUF) fue descartado en warmups en la [nota oficial](https://www.panthers.com/news/panthers-kicker-zane-gonzalez-helped-off-field-in-pregame). McManus (2025_06_CIN_GB) figura inactivo en la [lista oficial](https://www.packers.com/news/packers-bengals-week-6-inactives-oct-12-2025). Ambos carecen de patadas observadas. Son dos confirmaciones manuales de baja entre las 141 filas C sin evidencia de patadas; no se afirma DNP para las demás. La segunda fuente se descubrió al auditar el error y no alimenta la identidad.\n'
    (config.reports_dir / 'pregame_manual_audit.md').write_text(text, encoding='utf-8')
    write_json(config.reports_dir / 'pregame_manual_audit.json', {'policy': 'C', 'cases_passed': len(results),
        'confirmed_out_or_inactive_cases': ['2021_15_CAR_BUF:CAR', '2025_06_CIN_GB:GB'], 'cases': results})
    print(f'{len(results)} manual cases verified')
