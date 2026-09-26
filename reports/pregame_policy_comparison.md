# Comparación secuencial de expected kicker

Build `c721eeb55acb4eb9cb73`. Ver protocolo fijado en `docs/pregame_sequential_protocol.md`.

| Política | ID/6056 | Cobertura | VERIFIED | STRONG | INFERRED | AMBIGUOUS | UNKNOWN | Matches/evaluables | Accuracy | Errores | XPA=0 | XPM=0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 2 | 0.03% | 1 | 1 | 0 | 0 | 6054 | 2/2 | 100.00% | 0 | 1 | 1 |
| B | 447 | 7.38% | 1 | 1 | 445 | 37 | 5572 | 432/440 | 98.18% | 8 | 42 | 47 |
| C | 4992 | 82.43% | 1 | 1 | 4990 | 37 | 1027 | 4806/4934 | 97.41% | 128 | 447 | 543 |

A: confirmación oficial. B: A + continuidad de dos partidos y rol actual coincidente. C: A + continuidad experimental, sin inventar verificación de disponibilidad actual. Todas las filas conservan `eligible_for_pregame_training=false` a la espera de revisión de política.

## Política A: por temporada

| Año | Team-games | ID | Cobertura | Matches/evaluables | Accuracy | Discrepancias | Ambiguous | Unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2016 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2017 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2018 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2019 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2020 | 538 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 538 |
| 2021 | 570 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 570 |
| 2022 | 568 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 568 |
| 2023 | 570 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 570 |
| 2024 | 570 | 2 | 0.35% | 2/2 | 100.00% | 0 | 0 | 568 |
| 2025 | 570 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 570 |

| Cohorte | N | ID | Matches/evaluables | Discrepancias | Sin evidencia de patada | Label faltante |
| --- | --- | --- | --- | --- | --- | --- |
| Week 1 | 350 | 0 | 0/0 | 0 | 0 | 0 |
| Resto | 5706 | 2 | 2/2 | 0 | 0 | 0 |
| Cambio de ejecutor real | 229 | 2 | 2/2 | 0 | 0 | 0 |
| Cambio real con único ejecutor actual | 220 | 2 | 2/2 | 0 | 0 | 0 |
| Sin cambio de ejecutor real | 5342 | 0 | 0/0 | 0 | 0 | 0 |
| Múltiples ejecutores reales | 10 | 0 | 0/0 | 0 | 0 | 0 |
| Desarrollo 2015-2020 | 3208 | 0 | 0/0 | 0 | 0 | 0 |
| Evaluación temporal 2021-2024 | 2278 | 2 | 2/2 | 0 | 0 | 0 |
| 2025 previamente inspeccionado | 570 | 0 | 0/0 | 0 | 0 | 0 |
| Temporadas objetivo 2016-2025 | 5522 | 2 | 2/2 | 0 | 0 | 0 |

## Política B: por temporada

| Año | Team-games | ID | Cobertura | Matches/evaluables | Accuracy | Discrepancias | Ambiguous | Unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2016 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2017 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 2 | 532 |
| 2018 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2019 | 534 | 0 | 0.00% | 0/0 | N/A | 0 | 0 | 534 |
| 2020 | 538 | 0 | 0.00% | 0/0 | N/A | 0 | 1 | 537 |
| 2021 | 570 | 0 | 0.00% | 0/0 | N/A | 0 | 1 | 569 |
| 2022 | 568 | 0 | 0.00% | 0/0 | N/A | 0 | 2 | 566 |
| 2023 | 570 | 0 | 0.00% | 0/0 | N/A | 0 | 2 | 568 |
| 2024 | 570 | 2 | 0.35% | 2/2 | 100.00% | 0 | 1 | 567 |
| 2025 | 570 | 445 | 78.07% | 430/438 | 98.17% | 8 | 28 | 97 |

| Cohorte | N | ID | Matches/evaluables | Discrepancias | Sin evidencia de patada | Label faltante |
| --- | --- | --- | --- | --- | --- | --- |
| Week 1 | 350 | 0 | 0/0 | 0 | 0 | 0 |
| Resto | 5706 | 447 | 432/440 | 8 | 9 | 9 |
| Cambio de ejecutor real | 229 | 11 | 3/11 | 8 | 8 | 8 |
| Cambio real con único ejecutor actual | 220 | 10 | 2/10 | 8 | 8 | 8 |
| Sin cambio de ejecutor real | 5342 | 429 | 429/429 | 0 | 0 | 0 |
| Múltiples ejecutores reales | 10 | 1 | 1/1 | 0 | 0 | 0 |
| Desarrollo 2015-2020 | 3208 | 0 | 0/0 | 0 | 0 | 0 |
| Evaluación temporal 2021-2024 | 2278 | 2 | 2/2 | 0 | 0 | 0 |
| 2025 previamente inspeccionado | 570 | 445 | 430/438 | 8 | 9 | 9 |
| Temporadas objetivo 2016-2025 | 5522 | 447 | 432/440 | 8 | 9 | 9 |

## Política C: por temporada

| Año | Team-games | ID | Cobertura | Matches/evaluables | Accuracy | Discrepancias | Ambiguous | Unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015 | 534 | 450 | 84.27% | 436/445 | 97.98% | 9 | 0 | 84 |
| 2016 | 534 | 459 | 85.96% | 452/457 | 98.91% | 5 | 0 | 75 |
| 2017 | 534 | 434 | 81.27% | 413/424 | 97.41% | 11 | 2 | 98 |
| 2018 | 534 | 438 | 82.02% | 416/430 | 96.74% | 14 | 0 | 96 |
| 2019 | 534 | 445 | 83.33% | 429/441 | 97.28% | 12 | 0 | 89 |
| 2020 | 538 | 446 | 82.90% | 428/446 | 95.96% | 18 | 1 | 91 |
| 2021 | 570 | 454 | 79.65% | 429/448 | 95.76% | 19 | 1 | 115 |
| 2022 | 568 | 471 | 82.92% | 456/468 | 97.44% | 12 | 2 | 95 |
| 2023 | 570 | 478 | 83.86% | 464/469 | 98.93% | 5 | 2 | 90 |
| 2024 | 570 | 471 | 82.63% | 452/467 | 96.79% | 15 | 1 | 98 |
| 2025 | 570 | 446 | 78.25% | 431/439 | 98.18% | 8 | 28 | 96 |

| Cohorte | N | ID | Matches/evaluables | Discrepancias | Sin evidencia de patada | Label faltante |
| --- | --- | --- | --- | --- | --- | --- |
| Week 1 | 350 | 0 | 0/0 | 0 | 0 | 0 |
| Resto | 5706 | 4992 | 4806/4934 | 128 | 141 | 141 |
| Cambio de ejecutor real | 229 | 139 | 11/139 | 128 | 128 | 128 |
| Cambio real con único ejecutor actual | 220 | 130 | 2/130 | 128 | 128 | 128 |
| Sin cambio de ejecutor real | 5342 | 4795 | 4795/4795 | 0 | 0 | 0 |
| Múltiples ejecutores reales | 10 | 9 | 9/9 | 0 | 0 | 0 |
| Desarrollo 2015-2020 | 3208 | 2672 | 2574/2643 | 69 | 75 | 75 |
| Evaluación temporal 2021-2024 | 2278 | 1874 | 1801/1852 | 51 | 57 | 57 |
| 2025 previamente inspeccionado | 570 | 446 | 431/439 | 8 | 9 | 9 |
| Temporadas objetivo 2016-2025 | 5522 | 4542 | 4370/4489 | 119 | 131 | 131 |

Accuracy: pertenencia del esperado al conjunto de ejecutores de PAT/FG, solo si hay identidad y algún intento real. No incluye UNKNOWN, AMBIGUOUS ni equipos sin intentos. Las fuentes y algunos casos ya habían sido inspeccionados: no es validación independiente.
