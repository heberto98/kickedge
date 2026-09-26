# Contrato de tablas y campos

Todos los esquemas exactos y tipos están en `build.json`. Conteos son enteros;
NULL significa desconocido/ausente y nunca se debe convertir a cero por defecto.
`historical_base` tiene la misma población y clave que `labels`; no es otro muestreo.

| Tabla | Clave | Contenido |
| --- | --- | --- |
| games | game_id | Temporada, semana, tipo, equipos, fecha, marcador y OT |
| players | player_id | Crosswalk estable y nombre de presentación |
| game_coverage | game_id | Cantidad PBP, cierre, marcador y coverage_ok |
| pbp_events | game_id + play_id | Patadas, tries, TD y seguridad; incluye filas no contadas para auditoría |
| player_stats_kicking | game_id + team + player_id | Conteos del proveedor y posición histórica registrada |
| pbp_kicker_totals | game_id + team + player_id | Conteos PBP; incluye punters que solo hacen kickoffs, fuera del label si no cumplen población |
| team_games | game_id + team | Universo completo de ambos equipos y estado de identidad/reconciliación |
| labels | game_id + team + player_id | Resultado individual y evidencia |
| historical_base | game_id + team + player_id | Labels unidos a contexto de resultados equipo/partido |

## Labels

| Campo | Significado |
| --- | --- |
| player_id | GSIS ID estable; identificador del pateador, aunque su posición no sea K |
| kicker_name | Nombre de presentación, nunca clave de join |
| team, opponent, is_home | Identidad normalizada y condición según schedules; un partido neutral conserva los lados nominales |
| game_type | REG, WC, DIV, CON o SB |
| stats_xpa, stats_xpm | Valores explícitos de player stats; ausencias quedan NULL |
| pbp_xpa, pbp_xpm | Conteos por ID y equipo; un cero requiere presencia en patadas para ser aceptado |
| xpa, xpm | Valores canónicos solo cuando label_status=agreed |
| statistical_label_usable | Acuerdo de resultados; no significa aptitud prepartido |
| label_status | agreed, source_discrepancy, missing_player_stats, missing_pbp, incomplete_pbp, participation_unverified, unknown_pat_result, invalid_count, unmapped_player_id o invalid_schedule_identity |
| role_evidence | placekick_observed, kickoff_only_observed o stats_record_only |
| population_basis | Registro de posición K o intento de placekick por otra posición |
| participation_observed | Evidencia de PAT/FG/kickoff válido del jugador |
| participation_status | observed_postgame o unverified; no clasifica inactivos |
| multiple_kicking_participants | Más de un candidato con participación comprobada en ese equipo-partido |
| multiple_placekickers | Más de un candidato intentando PAT/FG; no prueba lesión |
| first_kicking_sequence, last_kicking_sequence | Orden de primera/última patada observada; no fecha de disponibilidad prepartido |
| zero_context | Contexto de los ceros según la tabla siguiente |
| label_evidence | Fundamento del label; distingue cero explícito corroborado y cuarentena |
| identity_method | Join por ID estable, sin matching por nombre |
| id_in_players, schedule_identity_ok, coverage_ok | Controles de identidad y cobertura |
| *_source_sha256 | Hash del original correspondiente en source_lock.json |
| target_season_eligible | Temporada >=2016; señal exclusivamente temporal |
| pregame_identity_status | not_reconstructed en esta versión |
| expected_kicker_id | NULL reservado para reconstrucción prepartido posterior |
| eligible_for_pregame_training | false siempre |

| zero_context | Lectura correcta |
| --- | --- |
| all_pat_failed_or_blocked | Intentó al menos un PAT y no convirtió ninguno |
| team_without_recorded_try | Jugador sin XPA; equipo sin PAT/2PT registrado |
| team_only_two_point_tries | Jugador sin XPA; equipo solo registró tries de 2PT |
| other_player_took_team_pat | Jugador sin XPA; otro ID hizo los PAT del equipo |
| not_zero / NULL | XPM positivo / label sin resolver |

## Jugadas y equipos

`counted_pat`, `made_pat`, `counted_fg`, `counted_kickoff`, `counted_two_pt` y
`counted_td` son las decisiones de conteo explícitas. `not_deleted` solo significa
que el proveedor no marcó la fila como eliminada; no certifica que toda acción
descrita sea válida. Los indicadores y descripciones originales se conservan.
Los retornos defensivos de tries se preservan en los campos
`defensive_two_point_*`/`defensive_extra_point_*`, separados del XPM del kicker.

`team_games` tiene touchdowns, su clasificación, XPA/XPM de equipo, intentos y
aciertos de 2PT, PAT fallados/bloqueados y `recorded_tries`. Estos son resultados,
no features listas para usar. `observed_kicker_count` y `placekicker_count`
describen la población de labels; `kicker_identity_status` distingue los equipos
sin candidato. `stats_team_xpa/xpm` permanecen NULL donde faltan registros de
pateo, y `team_reconciliation_status` conserva ese motivo.

Para trazar una fila: clave del label → hashes de fuentes → `source_lock.json` →
original. Para PAT individuales: mismo game_id/player_id/team → pbp_events → play_id.
Las rutas raw incluyen el hash completo y los reportes incluyen el build ID.
