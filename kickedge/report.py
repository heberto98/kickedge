"""Human-readable report generated from the same tables as quality.json."""


def table(rows, columns):
    if not rows:
        return "Ningún caso.\n"
    return ("| " + " | ".join(columns) + " |\n| " + " | ".join("---" for _ in columns) + " |\n"
            + "\n".join("| " + " | ".join(str(row.get(c)) for c in columns) + " |" for row in rows) + "\n")


def render_quality(summary, build_id):
    c = summary["counts"]
    return f"""# Calidad histórica de KickEdge

Build `{build_id}`. Informe generado; el detalle completo está en `quality.json` del build.

Población **observada después del partido**: registros históricos de posición K y
otros jugadores con PAT/FG, con participación en patadas comprobada en PBP para
publicar un label. Incluye especialistas que solo realizaron kickoffs, señalados
en `role_evidence`. No identifica al kicker esperado antes del partido.

- Partidos: {summary['game_count']}; equipos-partido: {summary['team_game_count']}.
- Temporada regular: {summary['regular_season_games']}; playoffs: {summary['postseason_games']}.
- Filas desde 2016, reservadas para una etapa posterior: {summary['target_season_rows']}.
- Observaciones candidatas: {c['observations']}; jugadores: {c['kickers']}.
- Labels con acuerdo: {c['usable_statistical_labels']}; XPM=0: {c['zeros']}.
- En cuarentena: {c['quarantined']}; registros solo con kickoffs: {c['kickoff_only_rows']}.
- Equipos-partido sin candidato: {len(summary['team_games_without_candidate'])}.
- Equipos-partido con varios participantes: {len(summary['multiple_participant_teams'])}.
- Equipos-partido con más de un jugador intentando PAT/FG: {sum(r['placekickers'] > 1 for r in summary['multiple_participant_teams'])}.
- Fallos de cobertura: {len(summary['coverage_failures'])}.
- Discrepancias numéricas de totales PAT por equipo: {summary['team_numeric_discrepancies']}.
- Equipos-partido sin player stats de pateo para reconciliar: {summary['missing_team_stats']}.
- Jugadas de tipo extra_point sin intento oficial: {summary['nullified_pat_rows']}.
- Filas de kickoff anuladas, sin atribuir participación: {summary['nullified_kickoff_rows']}.
- Intentos válidos de 2PT con play_type=no_play: {summary['valid_two_pt_no_play_rows']}.

## Temporadas

{table(summary['season_counts'], ['season','games','observations','kickers','zeros','quarantined'])}
## Distribución de XPM

{table(summary['xpm_distribution'], ['xpm','observations'])}
## Ceros

{table(summary['zero_basis'], ['zero_context','observations'])}
Los ceros requieren un cero explícito en player stats, participación comprobada
y PBP con cierre y marcador consistentes. `team_without_recorded_try` describe lo
observado; no asegura que reglamentariamente no hubiera oportunidad. Una ausencia
estadística conserva NULL y no produce un label canónico.

## Datos faltantes

{table(summary['missingness'], ['column','nulls','percent'])}
`expected_kicker_id` es deliberadamente NULL en el 100% de la población.
`eligible_for_pregame_training=false` en todas las filas.

## Reconciliación y cuarentena

{table(summary['label_status'], ['label_status','observations'])}
{table(summary['quarantined_labels'], ['game_id','team','player_id','label_status','stats_xpa','stats_xpm','pbp_xpa','pbp_xpm'])}
{table(summary['team_reconciliation'], ['game_id','team','team_xpa','team_xpm','stats_xpa','stats_xpm'])}
## Integridad

{table(summary['checks'], ['check','violations'])}
## Varios participantes y equipos sin candidato

{table(summary['multiple_participant_teams'], ['game_id','team','players','placekickers','names'])}
{table(summary['team_games_without_candidate'], ['game_id','team','team_xpa','touchdowns'])}
Varios participantes no prueban una lesión ni un cambio durante el partido:
pueden ser especialistas simultáneos o sustituciones anteriores al kickoff.
`multiple_placekickers` prueba intentos PAT/FG de dos IDs, no la causa.

## Límites de esta validación

Player stats y PBP comparten procedencia nflverse/NFL; el acuerdo no equivale a
dos registros oficiales independientes. El cierre y marcador son controles de
cobertura, no una prueba de que no falte ninguna jugada. Los originales reflejan
la versión descargada, no el conocimiento disponible antes de cada partido.
No se reconstruyen inactivos, ausencia de participación ni titularidad prepartido.
2015 es historial; `target_season_eligible` desde 2016 indica solo el calendario,
sin habilitar entrenamiento. No se han construido features ni modelos.
"""
