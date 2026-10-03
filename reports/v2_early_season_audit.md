# KickEdge V2 — audit de inicio de temporada

## Resultado y alcance de la evidencia

Las semanas 1–4 tienen una pequeña deterioración agrupada de NLL/RPS frente a 5–8 y 9+, especialmente en Brier ≥3, pero no un conservadurismo general: la media predicha es 2.2318 frente a 2.1834 XPM observados. El sesgo ≥2 es −0.55 pp y ≥3 −0.03 pp. Semana 1 sobreestima; semanas 2 y 4 subestiman; semana 3 sobreestima.

Esto justifica un experimento V2 de carryover separado, conservando intactas las 82 features V1. La justificación es evaluar contexto adicional para historia escasa, no corregir una supuesta dirección universal. La adopción depende de una comparación temporal convincente y estable. No se ajusta ni se aplica calibración global con esta evidencia.

## Grupos de semanas

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1-4 | 769 | 1.723531 | 0.775667 | 0.221958 | 0.233721 | 0.143730 | 2.2318 | 2.1834 |
| 5-8 | 697 | 1.712938 | 0.768573 | 0.211705 | 0.224462 | 0.148806 | 2.2643 | 2.2095 |
| 9+ | 1927 | 1.714942 | 0.771816 | 0.221858 | 0.218556 | 0.139846 | 2.1983 | 2.1780 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1-4 | 769 | -0.549 | 1.832 | -0.032 | 2.116 | +1.175 | 1.666 |
| 5-8 | 697 | -1.013 | 2.239 | +0.664 | 3.895 | +0.346 | 0.869 |
| 9+ | 1927 | -1.057 | 2.594 | -0.366 | 2.941 | +0.823 | 1.473 |

Los grupos tienen distinta composición de partidos y distribuciones de outcomes. Por eso una diferencia de score entre grupos no prueba por sí sola que la falta de historia cause el error. ECE es sensible al tamaño muestral y puede aumentar en estratos pequeños.

## Cada semana

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 193 | 1.659507 | 0.723006 | 0.236379 | 0.218233 | 0.125884 | 2.2097 | 2.0311 |
| 2 | 193 | 1.764921 | 0.815478 | 0.224806 | 0.244169 | 0.158319 | 2.2097 | 2.2435 |
| 3 | 193 | 1.735157 | 0.784370 | 0.228375 | 0.230839 | 0.129392 | 2.2542 | 2.1347 |
| 4 | 190 | 1.734715 | 0.779882 | 0.197898 | 0.241770 | 0.161605 | 2.2541 | 2.3263 |
| 5 | 178 | 1.699058 | 0.757171 | 0.216283 | 0.227576 | 0.139326 | 2.2972 | 2.1966 |
| 6 | 172 | 1.676725 | 0.740772 | 0.218203 | 0.219050 | 0.126510 | 2.2761 | 2.0698 |
| 7 | 168 | 1.749442 | 0.805143 | 0.201428 | 0.228940 | 0.163076 | 2.2442 | 2.2202 |
| 8 | 179 | 1.727277 | 0.772303 | 0.210551 | 0.222364 | 0.166265 | 2.2390 | 2.3464 |
| 9 | 169 | 1.731829 | 0.778154 | 0.225505 | 0.239205 | 0.143425 | 2.2192 | 2.2604 |
| 10 | 169 | 1.676496 | 0.747469 | 0.240541 | 0.203424 | 0.124985 | 2.1863 | 2.0355 |
| 11 | 172 | 1.675841 | 0.748087 | 0.239603 | 0.208026 | 0.135534 | 2.1831 | 2.0233 |
| 12 | 180 | 1.641475 | 0.703503 | 0.218128 | 0.213378 | 0.131004 | 2.1937 | 2.0556 |
| 13 | 179 | 1.730423 | 0.799974 | 0.226954 | 0.214456 | 0.144839 | 2.1832 | 2.1061 |
| 14 | 170 | 1.741714 | 0.792831 | 0.213484 | 0.229450 | 0.161257 | 2.1643 | 2.3235 |
| 15 | 192 | 1.780765 | 0.815426 | 0.209686 | 0.232475 | 0.142984 | 2.1657 | 2.2812 |
| 16 | 194 | 1.701226 | 0.749020 | 0.208997 | 0.214335 | 0.129742 | 2.1734 | 2.1907 |
| 17 | 188 | 1.722189 | 0.776891 | 0.201071 | 0.209918 | 0.153189 | 2.1955 | 2.3404 |
| 18 | 171 | 1.706433 | 0.773626 | 0.240777 | 0.207491 | 0.116318 | 2.1793 | 2.0409 |
| 19 | 67 | 1.752652 | 0.800771 | 0.218132 | 0.242995 | 0.143457 | 2.2922 | 2.2537 |
| 20 | 44 | 1.780104 | 0.835647 | 0.226655 | 0.245429 | 0.170624 | 2.4764 | 2.3636 |
| 21 | 22 | 1.782441 | 0.826152 | 0.216448 | 0.212997 | 0.178970 | 2.4950 | 2.4091 |
| 22 | 10 | 1.665652 | 0.736789 | 0.223721 | 0.184394 | 0.152099 | 2.2153 | 2.1000 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 193 | +2.457 | 2.457 | +6.354 | 6.354 | +3.825 | 3.825 |
| 2 | 193 | -1.236 | 3.280 | -3.598 | 6.299 | -1.050 | 1.944 |
| 3 | 193 | +1.535 | 4.430 | +1.751 | 7.533 | +3.374 | 4.610 |
| 4 | 190 | -5.023 | 8.926 | -4.708 | 6.993 | -1.489 | 2.518 |
| 5 | 178 | +0.200 | 4.934 | +3.556 | 8.355 | +2.452 | 4.421 |
| 6 | 172 | +0.904 | 4.605 | +5.681 | 8.386 | +4.594 | 4.812 |
| 7 | 168 | -0.149 | 9.611 | -1.887 | 4.476 | -2.357 | 5.074 |
| 8 | 179 | -4.874 | 4.910 | -4.638 | 7.965 | -3.293 | 5.154 |
| 9 | 169 | -4.280 | 8.332 | -6.382 | 7.156 | +0.738 | 3.260 |
| 10 | 169 | +1.265 | 6.536 | +5.771 | 8.308 | +4.939 | 8.704 |
| 11 | 172 | +5.349 | 6.546 | +3.347 | 3.967 | +2.106 | 5.786 |
| 12 | 180 | +3.216 | 7.411 | +1.222 | 7.019 | +1.325 | 4.811 |
| 13 | 179 | +1.944 | 3.236 | +0.147 | 5.635 | +1.072 | 4.504 |
| 14 | 170 | -4.171 | 7.220 | -6.427 | 8.258 | -4.278 | 7.180 |
| 15 | 192 | -6.950 | 8.660 | -5.589 | 6.905 | -1.126 | 5.024 |
| 16 | 194 | -4.973 | 8.386 | -0.848 | 3.937 | +2.268 | 7.078 |
| 17 | 188 | -3.453 | 8.012 | -0.996 | 5.900 | -2.611 | 4.289 |
| 18 | 171 | +1.596 | 10.194 | +5.271 | 9.941 | +3.861 | 5.940 |
| 19 | 67 | -4.929 | 8.682 | +2.489 | 8.814 | +2.699 | 5.874 |
| 20 | 44 | +5.701 | 17.613 | -3.353 | 13.887 | +1.444 | 14.316 |
| 21 | 22 | +2.105 | 13.869 | +4.207 | 14.082 | -2.849 | 14.904 |
| 22 | 10 | +4.420 | 14.782 | +8.043 | 12.094 | -1.374 | 3.561 |

## Estabilidad del contraste temprano frente a semanas 9+

Deltas positivos significan mayor error en semanas 1–4. El NLL temprano es mayor en 4 de 6 temporadas y el RPS en 3 de 6, así que la evidencia no es uniforme entre temporadas.

| Temporada | n temprano | Δ NLL temprano−tardío | Δ RPS temprano−tardío | Sesgo ≥2 temprano (pp) | Sesgo ≥3 temprano (pp) |
| --- | --- | --- | --- | --- | --- |
| 2020 | 126 | -0.005125 | -0.012202 | -7.009 | -6.198 |
| 2021 | 128 | +0.016873 | -0.015931 | -3.316 | -4.080 |
| 2022 | 129 | +0.045883 | +0.041490 | +2.683 | +7.275 |
| 2023 | 128 | +0.074493 | +0.078197 | +1.749 | -1.275 |
| 2024 | 129 | -0.099434 | -0.087444 | +2.788 | +5.013 |
| 2025 | 129 | +0.017419 | +0.018311 | -0.344 | -1.112 |

## Historia previa del kicker

`kicker_games_before` cuenta partidos previos del kicker en la temporada actual, no su carrera. Con 0 partidos, el modelo sobreestima: 2.0930 XPM predichos frente a 1.9373 observados, y sesgos ≥2/≥3 de +3.39/+3.87 pp. Con 1–2 partidos los signos se invierten: −1.34/−2.55 pp. El estrato 3–4 partidos tiene ECE ≥3 de 7.32 pp aunque su sesgo promedio es casi cero: errores de signo contrario se compensan entre bins.

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 271 | 1.678243 | 0.750945 | 0.240041 | 0.211461 | 0.113001 | 2.0930 | 1.9373 |
| 1-2 | 482 | 1.738470 | 0.789280 | 0.226996 | 0.235197 | 0.141491 | 2.1641 | 2.1763 |
| 3-4 | 451 | 1.720932 | 0.774672 | 0.212496 | 0.232818 | 0.148843 | 2.2716 | 2.2306 |
| 5+ | 2189 | 1.715450 | 0.770286 | 0.217206 | 0.220040 | 0.145172 | 2.2365 | 2.2092 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 271 | +3.393 | 4.167 | +3.868 | 6.153 | +3.450 | 3.450 |
| 1-2 | 482 | -1.342 | 5.228 | -2.548 | 3.511 | +0.244 | 1.006 |
| 3-4 | 451 | -1.884 | 3.301 | -0.056 | 7.321 | +0.882 | 2.183 |
| 5+ | 2189 | -1.182 | 1.566 | -0.028 | 1.725 | +0.585 | 1.444 |

## Disponibilidad de tres juegos previos

0 significa menos de tres juegos previos en la temporada; 1 significa al menos tres. Se utiliza el indicador original `kicker_has_3_prior_games`.

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 753 | 1.716795 | 0.775483 | 0.231691 | 0.226655 | 0.131238 | 2.1385 | 2.0903 |
| 1 | 2640 | 1.716386 | 0.771036 | 0.216402 | 0.222223 | 0.145799 | 2.2425 | 2.2129 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 753 | +0.362 | 4.142 | -0.239 | 3.734 | +1.397 | 1.829 |
| 1 | 2640 | -1.302 | 1.509 | -0.033 | 2.001 | +0.636 | 1.023 |

## Disponibilidad de cinco juegos previos

0 significa menos de cinco juegos previos en la temporada; 1 significa al menos cinco. Se utiliza el indicador original `kicker_has_5_prior_games`.

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1204 | 1.718345 | 0.775179 | 0.224501 | 0.228963 | 0.137832 | 2.1884 | 2.1429 |
| 1 | 2189 | 1.715450 | 0.770286 | 0.217206 | 0.220040 | 0.145172 | 2.2365 | 2.2092 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1204 | -0.479 | 2.722 | -0.171 | 2.188 | +1.204 | 1.908 |
| 1 | 2189 | -1.182 | 1.566 | -0.028 | 1.725 | +0.585 | 1.444 |

## Cantidad de features faltantes antes de imputación

Se cuenta el número de NULL/NaN en las 82 features normalizadas antes de imputar. La imputación usa únicamente el entrenamiento anterior de cada fold. Los grupos con faltantes tienen mayor ECE ≥2/≥3, pero no una dirección uniforme: 1–20 NULLs subestima; 21+ sobreestima. El número de faltantes se relaciona con semana e historia, así que este contraste no identifica un efecto causal independiente.

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 2173 | 1.717464 | 0.772056 | 0.217559 | 0.220635 | 0.145798 | 2.2379 | 2.2126 |
| 1-20 | 605 | 1.711733 | 0.770230 | 0.216525 | 0.226090 | 0.137041 | 2.1641 | 2.1554 |
| 21+ | 615 | 1.717656 | 0.773668 | 0.230909 | 0.229456 | 0.136588 | 2.2085 | 2.1203 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 2173 | -1.212 | 1.599 | -0.137 | 1.770 | +0.517 | 1.431 |
| 1-20 | 605 | -2.041 | 3.296 | -1.413 | 4.495 | +0.704 | 1.977 |
| 21+ | 615 | +1.144 | 3.499 | +1.442 | 3.786 | +1.923 | 2.087 |

## Límites y decisión

Las diferencias son descriptivas y no equivalen a una mejora garantizada para V2. Hay dependencia por partido, equipo y kicker; las muestras cambian entre estratos y las direcciones no son estables en todas las temporadas. No se sostiene que añadir carryover resuelva estas desviaciones antes de comparar sus resultados temporales. No se extrae una afirmación de rentabilidad ni una recomendación de apuesta.

Decisión registrada antes de construir nuevas features: experimentar con información de la temporada previa completada, ligada a jugador/equipo según corresponda, como columnas separadas; conservar el baseline V1; no aplicar incremento manual de probabilidades ni calibrador global. Todos los datos de desarrollo terminan en 2025. El diseño, selección y ajuste no utilizan outcomes 2026.

## Alcance y reproducción

Fuente histórica congelada: `data/features/environment/d0e256364dde3016c76f/kicker_game_features.parquet`.
SHA-256 de fuente: `bb1730a0f957aea3dd86f22f5448858bf182cdbb39d8bf09ac238013f20ebb3f`.
SHA-256 de predicciones: `e2fae5a45e764c1b8f5eb116c6c33fd02963d0c785e304e22498357ec85b93ae`.
Cohorte: 5,535 filas elegibles 2016–2025; 3,393 pronósticos temporales fuera de muestra 2020–2025.

El lector proyecta explícitamente claves, las 82 features originales y XPM, después del filtro SQL `eligible_for_phase_4_training IS TRUE AND season BETWEEN 2016 AND 2025`. Cada fold ajusta una réplica diagnóstica de `poisson_glm_alpha_0.1` (alpha 0.1, max_iter 2000, tol 1e-8), incluida su imputación y escalado, exclusivamente en temporadas anteriores a la evaluada. No se abren ni reescriben los artefactos V1. No se consultaron resultados 2026, cuotas, logs de análisis actuales, red ni credenciales.

Reproducir desde la raíz del repositorio con `.venv/Scripts/python.exe -m kickedge.v2.audit`. Las predicciones exactas, sus claves, temporada, semana, historia previa, indicadores de 3/5 juegos, número de NULLs y límites de entrenamiento quedan en `data/v2/audit/oof_predictions.parquet`; el resumen completo está en `data/v2/audit/summary.json` y la procedencia en `data/v2/audit/metadata.json`. El lector reutiliza predicciones cuando coinciden fuente, configuración y checksum del archivo; `--recompute` ejecuta de nuevo los seis folds.

La arquitectura V1 fue elegida previamente. Estos folds sirven para diagnóstico retrospectivo con estimación temporal válida, pero no constituyen una selección de arquitectura históricamente ciega. La temporada 2025, antes holdout de V1, está autorizada ahora para desarrollo V2. Los resultados aquí no son una validación forward de V2.

## Resultado posterior del experimento de carryover

Ejecutado después de registrar la decisión anterior (`reports/v2_model_comparison.md`). Con el carryover de temporada previa (GLM α1, B2) las semanas 1–4 mejoran NLL -1.36% y RPS -2.88%, y los kickers sin partidos previos en la temporada (n=271) mejoran NLL -1.83%. En total el cambio es -0.32% NLL y -0.69% RPS (mejoras menores al 1% registrado), así que el carryover no se adoptó solo por su mejora temprana. En la evaluación forward única de 2026 (semanas 1–4, 84 filas) el mismo retador mejoró a V1 -1.59% NLL, coherente con este patrón, pero la muestra no alcanza la compuerta de 150 filas y el retador no fue la selección registrada: V1 sigue como campeón (`reports/v2_forward_2026_validation.md`).
