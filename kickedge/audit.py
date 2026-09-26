"""Replay expectations established by manual inspection; never auto-rebaseline."""
import json

import duckdb

from .build import latest_build
from .io import records, write_json
from .report import table


def audit(config):
    directory=latest_build(config)
    cases=json.loads((config.root/'audits/cases.json').read_text(encoding='utf-8'))
    results=[]
    with duckdb.connect() as con:
        for case in cases:
            labels=records(con,"SELECT team,player_id,kicker_name,xpa,xpm,stats_xpa,stats_xpm,pbp_xpa,pbp_xpm,role_evidence,stats_source_sha256,pbp_source_sha256 FROM read_parquet(?) WHERE game_id=? ORDER BY team,player_id",
                [str(directory/'labels.parquet'),case['game_id']])
            for expected in case['labels']:
                actual=next((r for r in labels if r['player_id']==expected['player_id'] and r['team']==expected['team']),None)
                if actual is None or any(actual[k]!=v for k,v in expected.items()):
                    raise ValueError(f"Manual audit expectation failed: {case['game_id']} {expected}")
                if actual['pbp_source_sha256']!=case['pbp_source_sha256']:
                    raise ValueError(f"Source changed since manual review; re-audit {case['game_id']}")
            all_events=records(con,"SELECT play_id,order_sequence,qtr,posteam,td_team,player_id,counted_pat,made_pat,counted_two_pt,counted_td,counted_kickoff,extra_point_result,two_point_conv_result,description,pbp_source_sha256 FROM read_parquet(?) WHERE game_id=? ORDER BY order_sequence,play_id",
                [str(directory/'pbp_events.parquet'),case['game_id']])
            events=[r for r in all_events if r['play_id'] in case['play_ids']]
            if len(events)!=len(case['play_ids']):
                raise ValueError(f"Audit play IDs missing: {case['game_id']}")
            results.append({**case,'actual_labels':labels,'events':events})
    result={'build_id':directory.name,'manual_review_date':'2026-09-26',
            'method':'Original PBP descriptions and player-stat rows inspected manually; expectations replayed automatically.',
            'cases':results}
    write_json(config.reports_dir/'manual_audit.json',result)
    lines=['# Auditoría manual de partidos reales', '',
           f"Build `{directory.name}`. Inspección manual de descripciones PBP y registros de player stats: 2026-09-26.",
           'Las expectativas están fijadas en `audits/cases.json`; no se recalculan a partir del label. '
           'El comando `audit` comprueba esas expectativas y exporta las jugadas concretas a `manual_audit.json`. '
           'Una nueva versión del PBP requiere revisar nuevamente los casos.', '',
           'Los ID de jugada siguientes se refieren al original identificado por SHA-256. '
           'La secuencia se consulta mediante `order_sequence`: `play_id` es una clave, no garantiza orden cronológico.', '']
    for r in results:
        lines.extend([f"## {r['game_id']} — {r['category']}", '',r['review_notes'],'',
            table(r['actual_labels'],['team','player_id','kicker_name','stats_xpa','stats_xpm','pbp_xpa','pbp_xpm']),
            'Jugadas revisadas: '+', '.join(str(p) for p in r['play_ids'])+'.',
            f"PBP SHA-256: `{r['pbp_source_sha256']}`.",''])
        if r.get('external_source'):
            lines.extend([f"Contexto adicional: [{r['external_title']}]({r['external_source']}).",''])
    lines.extend(['## Alcance de la evidencia','',
        'La lesión/sustitución de Gano (2024) y Bailey (2017) se contrastó con crónicas oficiales de sus equipos. '
        'Los demás casos se auditaron sobre los archivos nflverse. Esto valida ejemplos del procesamiento, '
        'no certifica todos los partidos mediante gamebooks independientes ni reconstruye la población prepartido.'])
    (config.reports_dir/'manual_audit.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f"Manual audit replay passed: {len(results)} games; {sum(len(r['labels']) for r in results)} selected labels")
    return result
