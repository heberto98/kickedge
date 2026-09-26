# Auditoría manual de partidos reales

Build `c7300725b93c79971254`. Inspección manual de descripciones PBP y registros de player stats: 2026-09-26.
Las expectativas están fijadas en `audits/cases.json`; no se recalculan a partir del label. El comando `audit` comprueba esas expectativas y exporta las jugadas concretas a `manual_audit.json`. Una nueva versión del PBP requiere revisar nuevamente los casos.

Los ID de jugada siguientes se refieren al original identificado por SHA-256. La secuencia se consulta mediante `order_sequence`: `play_id` es una clave, no garantiza orden cronológico.

## 2015_03_CHI_SEA — Cero y touchdown de special teams

Robbie Gould figura con 0 XPA y 0 XPM explícitos y participó en el kickoff 1844, retornado por Tyler Lockett para TD de Seattle. Chicago no registró TD ni try. Hauschka convirtió los dos PAT de Seattle; el retorno se atribuye a SEA y cuenta una sola vez.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| CHI | 00-0023252 | Robbie Gould | 0 | 0 | 0 | 0 |
| SEA | 00-0025944 | Steven Hauschka | 2 | 2 | 2 | 2 |

Jugadas revisadas: 1844, 1862, 2408, 2428.
PBP SHA-256: `01b5ae7d06633a2e66b418404461a3d4ff055ad2f3a87d453cebcc8d3fda7ed9`.

## 2015_03_SF_ARI — Touchdowns defensivos

Arizona registró seis TD: cuatro ofensivos y dos retornos de intercepción, de Bethel y Mathieu (257 y 402). Catanzaro convirtió seis PAT. El equipo anotador se toma de td_team; no se suman TD de pase y recepción como eventos separados.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| ARI | 00-0030896 | Chandler Catanzaro | 6 | 6 | 6 | 6 |
| SF | 00-0004091 | Phil Dawson | 1 | 1 | 1 | 1 |

Jugadas revisadas: 257, 287, 402, 430, 997, 1015, 1400, 1417, 2404, 2425, 3448, 3469.
PBP SHA-256: `01b5ae7d06633a2e66b418404461a3d4ff055ad2f3a87d453cebcc8d3fda7ed9`.

## 2016_21_NE_ATL — PAT fallado, 2PT, overtime y TD sin try

Gostkowski falló su único PAT (2820). New England convirtió dos intentos de 2 puntos (3534, 4041); el segundo tiene play_type=no_play por una falta entre jugadas, pero la conversión vale. El TD de White en overtime (4504) terminó el partido sin PAT posterior. El label es XPA=1, XPM=0, aunque NE tuvo cuatro TD. La temporada es 2016, aunque el Super Bowl se disputó en febrero de 2017.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| ATL | 00-0020578 | Matt Bryant | 4 | 4 | 4 | 4 |
| NE | 00-0024333 | Stephen Gostkowski | 1 | 0 | 1 | 0 |

Jugadas revisadas: 2820, 3534, 4041, 4504.
PBP SHA-256: `95eba04e2145e3c1c8ca502f2a3a76cfb0a5990680c3fb480f02a74a45f54a3b`.

## 2017_07_DAL_SF — Sustitución y jugador de posición S

Bailey convirtió los dos primeros PAT. Después del intento fallado de 2PT (1461), Heath convirtió, falló y convirtió (2524, 3079, 3384): 3 XPA, 2 XPM. Se mantienen ambos IDs. La crónica oficial confirma la lesión de Bailey y el ingreso del safety Heath; la causa no se infiere automáticamente por haber dos jugadores.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| DAL | 00-0028660 | Dan Bailey | 2 | 2 | 2 | 2 |
| DAL | 00-0030196 | Jeff Heath | 3 | 2 | 3 | 2 |
| SF | 00-0023252 | Robbie Gould | 1 | 1 | 1 | 1 |

Jugadas revisadas: 219, 580, 1461, 2524, 3079, 3384.
PBP SHA-256: `84eacd963c1fdd45965f6222c62e9329a7f3412f029d92c1ac5e34a1bb4d3710`.

Contexto adicional: [Dallas Cowboys: Heath sustituye a Bailey](https://www.dallascowboys.com/news/with-bailey-hurt-heath-makes-kicking-cameo-for-first-time-since-high-scho-444326).

## 2020_06_DET_JAX — PAT bloqueado anulado y repetido

El bloqueo de Prater en 2519 fue anulado por offside; extra_point_attempt=0 y no tiene kicker ID estadístico. El intento repetido 2546 fue bueno. Los cuatro PAT oficiales fueron buenos: XPA=4, XPM=4. No se transforma el texto de un bloqueo anulado en un fallo oficial.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| DET | 00-0023853 | Matt Prater | 4 | 4 | 4 | 4 |
| JAX | 00-0032835 | Jon Brown | 1 | 1 | 1 | 1 |

Jugadas revisadas: 421, 900, 2519, 2546, 3143, 3695.
PBP SHA-256: `8889f5d8782b5c5dce3c3644acdc0322b228a7e9cb13fa36cbac250e260e9f60`.

## 2023_03_DEN_MIA — Diez XPM y retorno de kickoff

Se inspeccionaron los diez PAT buenos de Jason Sanders: 10 XPA, 10 XPM. Miami tuvo diez TD. El retorno de Mims en 3968 es un TD de Denver, aunque Sanders aparece como pateador del kickoff; no se atribuye ese TD al equipo que pateó.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| DEN | 00-0032569 | Wil Lutz | 2 | 2 | 2 | 2 |
| MIA | 00-0034794 | Jason Sanders | 10 | 10 | 10 | 10 |

Jugadas revisadas: 128, 486, 1203, 1943, 2061, 2890, 3370, 3503, 3953, 3968, 4068.
PBP SHA-256: `bd3484731408def6b0ec93225bba2bd7b2c65769ca707a2b9444d891abdc6776`.

Contexto adicional: [Miami Dolphins: victoria 70-20 y diez touchdowns](https://www.miamidolphins.com/news/game-recap-dolphins-break-franchise-scoring-record-dominate-denver-in-historic-7).

## 2024_02_NYG_WAS — Kicker lesionado con cero y sustituto

Gano participó en el kickoff 41, sin PAT ni FG. El TD del retorno fue anulado por holding, pero el kickoff fue una jugada válida. La crónica oficial confirma su lesión. Gillan falló el PAT 782 y NYG falló luego dos 2PT. Gano y Gillan conservan XPM=0 por razones distintas. Seibert hizo siete FG y ningún PAT. Este caso demuestra que multiple_placekickers=false no descarta una sustitución: Gano no alcanzó a intentar PAT/FG.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| NYG | 00-0026858 | Graham Gano | 0 | 0 | 0 | 0 |
| NYG | 00-0035042 | Jamie Gillan | 1 | 0 | 1 | 0 |
| WAS | 00-0035145 | Austin Seibert | 0 | 0 | 0 | 0 |

Jugadas revisadas: 41, 782, 1936, 3303.
PBP SHA-256: `3fd2896bc0b911b615142d2f1fabae54a4bbba5ab7b73b28187b118ef8af6a3b`.

Contexto adicional: [New York Giants: lesión de Gano y PAT fallado de Gillan](https://www.giants.com/news/giants-come-up-short-in-last-second-loss-to-commanders).

## 2025_03_KC_NYG — PAT bloqueado oficial y sustitución observada

El PAT de Gillan 1809 fue bloqueado oficialmente: extra_point_attempt=1 y resultado blocked. XPA=1, XPM=0. Gano tiene un intento de FG y ningún PAT; se conservan ambos participantes. Butker convirtió 2720 y falló 3795: 2 XPA, 1 XPM. La evidencia estadística identifica el relevo en los intentos, sin inferir aquí su causa médica.

| team | player_id | kicker_name | stats_xpa | stats_xpm | pbp_xpa | pbp_xpm |
| --- | --- | --- | --- | --- | --- | --- |
| KC | 00-0033303 | Harrison Butker | 2 | 1 | 2 | 1 |
| NYG | 00-0026858 | Graham Gano | 0 | 0 | 0 | 0 |
| NYG | 00-0035042 | Jamie Gillan | 1 | 0 | 1 | 0 |

Jugadas revisadas: 1809, 2720, 3795.
PBP SHA-256: `c6ecedd6d678cc37ed316b23ef84ee1ec6abb69c514bb11868a7ebd5a367df29`.

## Alcance de la evidencia

La lesión/sustitución de Gano (2024) y Bailey (2017) se contrastó con crónicas oficiales de sus equipos. Los demás casos se auditaron sobre los archivos nflverse. Esto valida ejemplos del procesamiento, no certifica todos los partidos mediante gamebooks independientes ni reconstruye la población prepartido.
