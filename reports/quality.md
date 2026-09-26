# Calidad histórica de KickEdge

Build `c7300725b93c79971254`. Informe generado; el detalle completo está en `quality.json` del build.

Población **observada después del partido**: registros históricos de posición K y
otros jugadores con PAT/FG, con participación en patadas comprobada en PBP para
publicar un label. Incluye especialistas que solo realizaron kickoffs, señalados
en `role_evidence`. No identifica al kicker esperado antes del partido.

- Partidos: 3028; equipos-partido: 6056.
- Temporada regular: 2895; playoffs: 133.
- Filas desde 2016, reservadas para una etapa posterior: 5535.
- Observaciones candidatas: 6083; jugadores: 122.
- Labels con acuerdo: 6083; XPM=0: 714.
- En cuarentena: 0; registros solo con kickoffs: 90.
- Equipos-partido sin candidato: 10.
- Equipos-partido con varios participantes: 37.
- Equipos-partido con más de un jugador intentando PAT/FG: 10.
- Fallos de cobertura: 0.
- Discrepancias numéricas de totales PAT por equipo: 0.
- Equipos-partido sin player stats de pateo para reconciliar: 10.
- Jugadas de tipo extra_point sin intento oficial: 21.
- Filas de kickoff anuladas, sin atribuir participación: 57.
- Intentos válidos de 2PT con play_type=no_play: 29.

## Temporadas

| season | games | observations | kickers | zeros | quarantined |
| --- | --- | --- | --- | --- | --- |
| 2015 | 267 | 548 | 41 | 65 | 0 |
| 2016 | 267 | 537 | 37 | 50 | 0 |
| 2017 | 267 | 535 | 44 | 63 | 0 |
| 2018 | 267 | 534 | 42 | 69 | 0 |
| 2019 | 267 | 536 | 43 | 72 | 0 |
| 2020 | 269 | 539 | 47 | 51 | 0 |
| 2021 | 285 | 570 | 49 | 73 | 0 |
| 2022 | 284 | 572 | 46 | 64 | 0 |
| 2023 | 285 | 571 | 41 | 80 | 0 |
| 2024 | 285 | 571 | 45 | 67 | 0 |
| 2025 | 285 | 570 | 43 | 60 | 0 |

## Distribución de XPM

| xpm | observations |
| --- | --- |
| 0 | 714 |
| 1 | 1410 |
| 2 | 1642 |
| 3 | 1237 |
| 4 | 680 |
| 5 | 271 |
| 6 | 109 |
| 7 | 14 |
| 8 | 4 |
| 9 | 1 |
| 10 | 1 |

## Ceros

| zero_context | observations |
| --- | --- |
| all_pat_failed_or_blocked | 125 |
| other_player_took_team_pat | 32 |
| team_only_two_point_tries | 195 |
| team_without_recorded_try | 362 |

Los ceros requieren un cero explícito en player stats, participación comprobada
y PBP con cierre y marcador consistentes. `team_without_recorded_try` describe lo
observado; no asegura que reglamentariamente no hubiera oportunidad. Una ausencia
estadística conserva NULL y no produce un label canónico.

## Datos faltantes

| column | nulls | percent |
| --- | --- | --- |
| game_id | 0 | 0.0 |
| player_id | 0 | 0.0 |
| kicker_name | 0 | 0.0 |
| opponent | 0 | 0.0 |
| stats_xpa | 0 | 0.0 |
| stats_xpm | 0 | 0.0 |
| pbp_xpa | 0 | 0.0 |
| pbp_xpm | 0 | 0.0 |
| xpa | 0 | 0.0 |
| xpm | 0 | 0.0 |
| expected_kicker_id | 6083 | 100.0 |

`expected_kicker_id` es deliberadamente NULL en el 100% de la población.
`eligible_for_pregame_training=false` en todas las filas.

## Reconciliación y cuarentena

| label_status | observations |
| --- | --- |
| agreed | 6083 |

Ningún caso.

| game_id | team | team_xpa | team_xpm | stats_xpa | stats_xpm |
| --- | --- | --- | --- | --- | --- |
| 2015_14_ATL_CAR | ATL | 0 | 0 | None | None |
| 2017_07_JAX_IND | IND | 0 | 0 | None | None |
| 2018_13_IND_JAX | IND | 0 | 0 | None | None |
| 2019_01_ATL_MIN | ATL | 0 | 0 | None | None |
| 2021_15_CAR_BUF | CAR | 0 | 0 | None | None |
| 2022_05_DET_NE | DET | 0 | 0 | None | None |
| 2022_19_DAL_TB | TB | 0 | 0 | None | None |
| 2023_17_CAR_JAX | CAR | 0 | 0 | None | None |
| 2024_17_NYJ_BUF | NYJ | 0 | 0 | None | None |
| 2025_18_NYJ_BUF | NYJ | 0 | 0 | None | None |

## Integridad

| check | violations |
| --- | --- |
| unique_games | 0 |
| unique_players | 0 |
| unique_pbp_plays | 0 |
| unique_player_stats | 0 |
| unique_labels | 0 |
| valid_label_ids | 0 |
| valid_game_team | 0 |
| stats_team_opponent | 0 |
| valid_pbp_game | 0 |
| pbp_game_metadata | 0 |
| unrounded_stats_counts | 0 |
| valid_pbp_kicking_team | 0 |
| valid_touchdown_team | 0 |
| valid_counts | 0 |
| canonical_only_agreement | 0 |
| pregame_not_inferred | 0 |
| td_counted_once | 0 |
| team_xpa_matches_events | 0 |
| td_components_complete | 0 |

## Varios participantes y equipos sin candidato

| game_id | team | players | placekickers | names |
| --- | --- | --- | --- | --- |
| 2015_01_IND_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_02_NE_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_03_BUF_MIA | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_04_NYG_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_05_BUF_TEN | BUF | 2 | 1 | Billy Cundiff, Dan Carpenter |
| 2015_07_BUF_JAX | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_09_MIA_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_10_BUF_NYJ | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_11_BUF_NE | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_12_BUF_KC | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_13_HOU_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_14_BUF_PHI | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_15_BUF_WAS | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_16_DAL_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2015_17_NYJ_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2016_01_BUF_BAL | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2016_03_ARI_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2016_12_JAX_BUF | BUF | 2 | 1 | Dan Carpenter, Jordan Gay |
| 2017_07_DAL_SF | DAL | 2 | 2 | Dan Bailey, Jeff Heath |
| 2017_12_LAC_DAL | LAC | 2 | 2 | Nick Novak, Drew Kaser |
| 2018_19_LAC_NE | LAC | 2 | 1 | Nick Rose, Mike Badgley |
| 2019_13_TEN_IND | TEN | 2 | 1 | Ryan Succop, Ryan Santoso |
| 2019_14_TEN_OAK | TEN | 2 | 1 | Ryan Succop, Ryan Santoso |
| 2019_15_HOU_TEN | TEN | 2 | 1 | Ryan Succop, Ryan Santoso |
| 2020_16_CLE_NYJ | CLE | 2 | 2 | Cody Parkey, Jamie Gillan |
| 2021_05_MIA_TB | TB | 2 | 2 | Ryan Succop, Bradley Pinion |
| 2022_01_KC_ARI | KC | 2 | 2 | Harrison Butker, Justin Reid |
| 2022_05_SF_CAR | SF | 2 | 2 | Robbie Gould, Mitch Wishnowsky |
| 2022_08_ARI_MIN | ARI | 2 | 1 | Matt Prater, Rodrigo Blankenship |
| 2022_10_DAL_GB | GB | 2 | 1 | Mason Crosby, Ramiz Ahmed |
| 2022_13_BUF_NE | NE | 2 | 1 | Nick Folk, Tristan Vizcaino |
| 2022_16_CIN_NE | NE | 2 | 1 | Nick Folk, Tristan Vizcaino |
| 2023_09_TB_HOU | HOU | 2 | 2 | Ka'imi Fairbairn, Dare Ogunbowale |
| 2023_15_NYG_NO | NYG | 2 | 2 | Randy Bullock, Jamie Gillan |
| 2024_02_NYG_WAS | NYG | 2 | 1 | Graham Gano, Jamie Gillan |
| 2024_05_ARI_SF | SF | 2 | 2 | Mitch Wishnowsky, Jake Moody |
| 2025_03_KC_NYG | NYG | 2 | 2 | Graham Gano, Jamie Gillan |

| game_id | team | team_xpa | touchdowns |
| --- | --- | --- | --- |
| 2015_14_ATL_CAR | ATL | 0 | 0 |
| 2017_07_JAX_IND | IND | 0 | 0 |
| 2018_13_IND_JAX | IND | 0 | 0 |
| 2019_01_ATL_MIN | ATL | 0 | 2 |
| 2021_15_CAR_BUF | CAR | 0 | 2 |
| 2022_05_DET_NE | DET | 0 | 0 |
| 2022_19_DAL_TB | TB | 0 | 2 |
| 2023_17_CAR_JAX | CAR | 0 | 0 |
| 2024_17_NYJ_BUF | NYJ | 0 | 2 |
| 2025_18_NYJ_BUF | NYJ | 0 | 1 |

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
