# Auditoría manual pregame — política C

Casos dirigidos; no muestra aleatoria ni estimación independiente de precisión. Decisiones de A/B se consultan con el comando inspect.

## 2015_04_HOU_ATL — HOU

Cutoff `2015-10-04T16:00:00+00:00`. Esperado: **Randy Bullock**, INFERRED. Racha previa: 3.

Cambio de kicker: tres partidos previos señalan Bullock. C conserva la inferencia y falla frente a Novak. No había un feed completo de altas/bajas en la selección. El registro oficial de fichajes localizado después sirve como opción de mejora global, no como parche de este error.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2015_03_TB_HOU | 2015-09-28T17:00:00+00:00 | 00-0029421 |
| 2015_02_HOU_CAR | 2015-09-21T17:00:00+00:00 | 00-0029421 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| untimed_depth_charts | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2015.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2015.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2015.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: mismatch; reales PAT/FG: Nick Novak; XPA/XPM=None/None; participación=no_kicking_evidence.

## 2015_09_JAX_NYJ — NYJ

Cutoff `2015-11-08T17:00:00+00:00`. Esperado: **Nick Folk**, INFERRED. Racha previa: 7.

Sustituto de otra posición: siete partidos previos señalan Folk; Quigley ejecutó los PAT/FG. La identidad esperada se conserva y el label individual queda NULL. Los eventos del partido se usan solamente para medir la discrepancia.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2015_08_NYJ_OAK | 2015-11-02T21:05:00+00:00 | 00-0025565 |
| 2015_07_NYJ_NE | 2015-10-26T17:00:00+00:00 | 00-0025565 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| untimed_depth_charts | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2015.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2015.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2015.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: mismatch; reales PAT/FG: Ryan Quigley; XPA/XPM=None/None; participación=no_kicking_evidence.

## 2019_02_LAC_DET — LAC

Cutoff `2019-09-15T16:00:00+00:00`. Esperado: **UNKNOWN**, UNKNOWN. Racha previa: 1.

Asignación oficial de patadas a Ty Long, pero la copia del artículo fue modificada en 2023. Solo hay un partido previo de Long en esa temporada: no alcanza la regla de dos. No se rescata la identidad usando el resultado real.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2019_01_IND_LAC | 2019-09-09T20:05:00+00:00 | 00-0031543 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| official_assignment | [Fuente](https://www.chargers.com/news/inactives-chargers-at-lions) | 2023-02-28T09:05:37.166000+00:00 | content_modified_after_cutoff |
| official_unavailable | [Fuente](https://www.chargers.com/news/inactives-chargers-at-lions) | 2023-02-28T09:05:37.166000+00:00 | content_modified_after_cutoff |
| untimed_depth_charts | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2019.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2019.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2019.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: expected_unknown; reales PAT/FG: Ty Long; XPA/XPM=None/None; participación=unknown_identity.

## 2021_15_CAR_BUF — CAR

Cutoff `2021-12-19T17:00:00+00:00`. Esperado: **Zane Gonzalez**, INFERRED. Racha previa: 12.

C espera Gonzalez por doce juegos previos. La noticia de su baja en warmups se publicó a 17:09Z, después del cutoff de 17:00Z; excluirla es correcto incluso aunque preceda al kickoff. La evaluación confirma baja y ausencia de patadas. No se convierte el label ausente a cero.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2021_14_ATL_CAR | 2021-12-13T18:00:00+00:00 | 00-0033862 |
| 2021_12_CAR_MIA | 2021-11-29T18:00:00+00:00 | 00-0033862 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| official_unavailable | [Fuente](https://www.panthers.com/news/panthers-kicker-zane-gonzalez-helped-off-field-in-pregame) | 2023-02-28T08:56:31.005000+00:00 | after_cutoff |
| official_context | [Fuente](https://www.panthers.com/news/dj-moore-active-for-panthers-against-the-bills) | 2023-02-28T08:56:31.619000+00:00 | content_modified_after_cutoff |
| untimed_depth_charts | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2021.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2021.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2021.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: no_actual_placekick; reales PAT/FG: ninguno; XPA/XPM=None/None; participación=no_kicking_evidence.

## 2024_02_NYG_WAS — WAS

Cutoff `2024-09-15T16:00:00+00:00`. Esperado: **Austin Seibert**, STRONG. Racha previa: 1.

Alta de Seibert en roster activo y salida de York durante la semana, corroboradas con lista completa de inactivos gameday. La fuente positiva vence la continuidad de York. Cero XPA/XPM conservado; siete FG observados solo en evaluación.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2024_01_WAS_TB | 2024-09-09T20:25:00+00:00 | 00-0038097 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| official_roster | [Fuente](https://www.commanders.com/news/commanders-sign-k-austin-seibert-to-active-roster-add-t-anim-dankwah-to-practice-squad) | 2024-09-10T16:29:17.928000+00:00 | aceptada |
| official_unavailable | [Fuente](https://www.commanders.com/news/commanders-sign-k-austin-seibert-to-active-roster-add-t-anim-dankwah-to-practice-squad) | 2024-09-10T16:29:17.928000+00:00 | aceptada |
| official_inactives | [Fuente](https://www.commanders.com/news/inactives-commanders-vs-giants-week-2) | 2024-09-15T15:29:11.830000+00:00 | aceptada |
| untimed_depth_charts | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2024.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2024.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2024.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: exclusive_match; reales PAT/FG: Austin Seibert; XPA/XPM=0/0; participación=observed_kicking.

## 2024_02_NYG_WAS — NYG

Cutoff `2024-09-15T16:00:00+00:00`. Esperado: **UNKNOWN**, UNKNOWN. Racha previa: 1.

La nota que dice que Gano pateará tiene modificación a 16:54:57Z, posterior a T-60=16:00Z. Falta una segunda observación previa en la temporada. No se elige a Gillan por haber ejecutado el PAT real.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2024_01_MIN_NYG | 2024-09-09T17:00:00+00:00 | 00-0026858 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| official_assignment | [Fuente](https://www.giants.com/news/nfl-week-2-injury-report-statuses-for-giants-vs-commanders) | 2024-09-15T16:54:57.382000+00:00 | content_modified_after_cutoff |
| untimed_depth_charts | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2024.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2024.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2024.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: expected_unknown; reales PAT/FG: Jamie Gillan; XPA/XPM=None/None; participación=unknown_identity.

## 2024_09_WAS_NYG — NYG

Cutoff `2024-11-03T17:00:00+00:00`. Esperado: **Jude McAtamney**, VERIFIED. Racha previa: 6.

Joseph out y luego IR; elevación oficial de McAtamney el sábado y confirmación de debut el domingo. Última modificación válida de la confirmación a 16:35:14Z, antes de cutoff=17:00Z. La evidencia explícita vence seis partidos previos de Joseph.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2024_08_NYG_PIT | 2024-10-30T00:15:00+00:00 | 00-0034450 |
| 2024_07_PHI_NYG | 2024-10-21T17:00:00+00:00 | 00-0034450 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| official_unavailable | [Fuente](https://www.giants.com/news/jude-mcatamney-greg-joseph-kicker-week-9-washington-commanders-tyrone-tracy) | 2024-11-01T21:24:41.161000+00:00 | aceptada |
| official_roster | [Fuente](https://www.giants.com/news/tomon-fox-greg-joseph-jude-mcatamney-jakob-johnson-week-9-washington-commanders-roster-moves) | 2024-11-02T23:03:38.468000+00:00 | aceptada |
| official_unavailable | [Fuente](https://www.giants.com/news/tomon-fox-greg-joseph-jude-mcatamney-jakob-johnson-week-9-washington-commanders-roster-moves) | 2024-11-02T23:03:38.468000+00:00 | aceptada |
| official_assignment | [Fuente](https://www.giants.com/news/nfl-week-9-inactives-who-s-in-who-s-out-for-commanders-at-giants) | 2024-11-03T16:35:14.918000+00:00 | aceptada |
| official_unavailable | [Fuente](https://www.giants.com/news/nfl-week-9-inactives-who-s-in-who-s-out-for-commanders-at-giants) | 2024-11-03T16:35:14.918000+00:00 | aceptada |
| untimed_depth_charts | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2024.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2024.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2024.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: exclusive_match; reales PAT/FG: Jude McAtamney; XPA/XPM=1/1; participación=observed_kicking.

## 2025_06_CIN_GB — GB

Cutoff `2025-10-12T19:25:00+00:00`. Esperado: **Brandon McManus**, INFERRED. Racha previa: 4.

Dos kickers en depth chart: McManus rank 1, Havrisik rank 2. Cuatro partidos previos corroboran a McManus, incluyendo un bye. B y C fallan. La auditoría externa posterior encontró que McManus había sido declarado inactivo. Evidencia que falta integrar sistemáticamente, no error corregido con hindsight.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2025_04_GB_DAL | 2025-09-30T00:20:00+00:00 | 00-0029822 |
| 2025_03_GB_CLE | 2025-09-22T17:00:00+00:00 | 00-0029822 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2025.parquet) | None | forbidden_or_untimed_source_kind |
| depth_snapshot | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet) | 2025-10-12T07:13:37+00:00 | aceptada |
| depth_snapshot | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet) | 2025-10-12T07:13:37+00:00 | aceptada |

Evaluación: mismatch; reales PAT/FG: Lucas Havrisik; XPA/XPM=None/None; participación=no_kicking_evidence.

## 2025_07_GB_ARI — GB

Cutoff `2025-10-19T19:25:00+00:00`. Esperado: **UNKNOWN**, AMBIGUOUS. Racha previa: 1.

El último juego revelado identifica Havrisik pero el snapshot sigue situando McManus primero. Se conservan ambos candidatos y la contradicción; no se selecciona al que sabemos retrospectivamente que pateó.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2025_06_CIN_GB | 2025-10-13T20:25:00+00:00 | 00-0038152 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2025.parquet) | None | forbidden_or_untimed_source_kind |
| depth_snapshot | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet) | 2025-10-19T07:13:17+00:00 | aceptada |
| depth_snapshot | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet) | 2025-10-19T07:13:17+00:00 | aceptada |

Evaluación: expected_unknown; reales PAT/FG: Lucas Havrisik; XPA/XPM=None/None; participación=unknown_identity.

## 2025_07_GB_ARI — ARI

Cutoff `2025-10-19T19:25:00+00:00`. Esperado: **Chad Ryland**, INFERRED. Racha previa: 6.

El snapshot actual no tiene fila PK: el estudio inicial y B quedan UNKNOWN. C puede inferir Ryland por seis juegos previos, declarando que falta corroboración actual. No busca una fila PK en un snapshot futuro ni revive automáticamente una fila antigua.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2025_06_ARI_IND | 2025-10-13T17:00:00+00:00 | 00-0038567 |
| 2025_05_TEN_ARI | 2025-10-06T20:05:00+00:00 | 00-0038567 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2025.parquet) | None | forbidden_or_untimed_source_kind |

Evaluación: exclusive_match; reales PAT/FG: Chad Ryland; XPA/XPM=2/2; participación=observed_kicking.

## 2025_07_LV_KC — LV

Cutoff `2025-10-19T16:00:00+00:00`. Esperado: **Daniel Carlson**, INFERRED. Racha previa: 6.

Seis juegos anteriores y rol fresco. El equipo no tuvo PAT/FG; Carlson sí tiene kickoff y label reconciliado 0/0. La fila sobrevive, pero no entra al denominador de comparación con ejecutores reales de PAT/FG.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2025_06_TEN_LV | 2025-10-13T20:05:00+00:00 | 00-0034161 |
| 2025_05_LV_IND | 2025-10-06T17:00:00+00:00 | 00-0034161 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2025.parquet) | None | forbidden_or_untimed_source_kind |
| depth_snapshot | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet) | 2025-10-19T07:13:17+00:00 | aceptada |

Evaluación: no_actual_placekick; reales PAT/FG: ninguno; XPA/XPM=0/0; participación=observed_kicking.

## 2025_03_KC_NYG — NYG

Cutoff `2025-09-21T23:20:00+00:00`. Esperado: **Graham Gano**, INFERRED. Racha previa: 2.

Dos juegos previos y snapshot coincidente. Se observan después Gano en FG y Gillan en PAT: expected pertenece al conjunto real, pero no hay igualdad de conjunto exacto. XPA/XPM de Gano=0/0 se conservan.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2025_02_NYG_DAL | 2025-09-15T17:00:00+00:00 | 00-0026858 |
| 2025_01_NYG_WAS | 2025-09-08T17:00:00+00:00 | 00-0026858 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| official_context | [Fuente](https://www.giants.com/news/andrew-thomas-active-snf-chiefs-inactive-list-xavier-worthy-injury-status) | 2025-09-21T22:56:07.114000+00:00 | aceptada |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2025.parquet) | None | forbidden_or_untimed_source_kind |
| depth_snapshot | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet) | 2025-09-21T07:13:06+00:00 | aceptada |

Evaluación: expected_among_multiple; reales PAT/FG: Graham Gano, Jamie Gillan; XPA/XPM=0/0; participación=observed_kicking.

## 2025_18_NYJ_BUF — NYJ

Cutoff `2026-01-04T20:25:00+00:00`. Esperado: **Nick Folk**, INFERRED. Racha previa: 16.

Dieciséis juegos previos y depth chart identifican Folk. No hay evidencia de patadas ni label individual validado. Se mantiene la identidad, XPA/XPM NULL y participación indeterminada. No tener intentos no prueba DNP.

| Juego anterior | Revelación permitida | Jugadores |
| --- | --- | --- |
| 2025_17_NE_NYJ | 2025-12-29T18:00:00+00:00 | 00-0025565 |
| 2025_16_NYJ_NO | 2025-12-22T18:00:00+00:00 | 00-0025565 |

| Tipo | Fuente | Disponible / modificado | Aceptación |
| --- | --- | --- | --- |
| untimed_weekly_rosters | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.parquet) | None | forbidden_or_untimed_source_kind |
| untimed_injuries | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2025.parquet) | None | forbidden_or_untimed_source_kind |
| depth_snapshot | [Fuente](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet) | 2026-01-04T07:17:56+00:00 | aceptada |

Evaluación: no_actual_placekick; reales PAT/FG: ninguno; XPA/XPM=None/None; participación=no_kicking_evidence.

## Confirmación externa de no participación

Gonzalez (2021_15_CAR_BUF) fue descartado en warmups en la [nota oficial](https://www.panthers.com/news/panthers-kicker-zane-gonzalez-helped-off-field-in-pregame). McManus (2025_06_CIN_GB) figura inactivo en la [lista oficial](https://www.packers.com/news/packers-bengals-week-6-inactives-oct-12-2025). Ambos carecen de patadas observadas. Son dos confirmaciones manuales de baja entre las 141 filas C sin evidencia de patadas; no se afirma DNP para las demás. La segunda fuente se descubrió al auditar el error y no alimenta la identidad.
