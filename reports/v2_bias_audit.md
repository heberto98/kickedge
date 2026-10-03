# KickEdge V2 — audit histórico de sesgo y calibración

## Resultado y decisión previa al diseño V2

El audit no confirma una subestimación general fuerte ni una necesidad de aumentar probabilidades. En 3,393 pronósticos fuera de muestra, XPM ≥2 está subestimado en promedio por 0.93 pp; XPM ≥3 por 0.08 pp; XPM ≥4 está sobreestimado por 0.80 pp. Las ECE agrupadas están alrededor de 1–2 pp y la dirección del error cambia según temporada, semana e historia disponible.

Se autoriza estudiar carryover de temporada anterior como experimento separado: hay una pequeña deterioración probabilística al inicio y desviaciones mayores en algunos estratos con poca historia. No se ajusta ni aplica un calibrador global: la evidencia agregada y de signo mixto no justifica una corrección uniforme. Un futuro calibrador requeriría evidencia más clara y comparación temporal fuera de muestra usando outcomes, nunca cuotas como target.

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Todas las filas | 3393 | 1.716477 | 0.772023 | 0.219795 | 0.223207 | 0.142567 | 2.2194 | 2.1857 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Todas las filas | 3393 | -0.933 | 1.739 | -0.079 | 1.050 | +0.805 | 0.916 |

MAE: 1.129840; RMSE: 1.405229; deviance Poisson: 1.056012. Menor NLL/RPS/Brier indica mejor calidad probabilística en una misma cohorte. El sesgo es media predicha menos frecuencia observada; negativo significa subestimación. ECE usa diez intervalos fijos de probabilidad.

## Probabilidades favoritas

Para XPM ≥2, el intervalo 70–80% contiene 777 filas: promedio predicho 74.42%, frecuencia observada 76.32%, diferencia −1.90 pp. En 80–90% hay 158 filas: 82.96% predicho frente a 81.01% observado, diferencia +1.95 pp. Los intervalos Wilson descriptivos de la frecuencia son 73.21–79.17% y 74.19–86.36%, respectivamente. No aparece una dirección uniforme que justifique elevar todas las probabilidades favoritas. El intervalo 90–100% tiene solo dos filas y no permite una conclusión estable.

## Raw implied, no-vig y KickEdge

`raw_over = 1 / over_decimal` y `raw_under = 1 / under_decimal` incluyen el margen del precio. Cuando las dos cuotas corresponden al mismo mercado, línea y momento, `fair_over = raw_over / (raw_over + raw_under)` y `fair_under = raw_under / (raw_over + raw_under)`. El no-vig proporcional es una referencia de mercado bajo esa convención; no es automáticamente la probabilidad verdadera.

La comparación histórica con mercado queda pendiente de la búsqueda de precios comparables después del congelamiento del modelo. Este audit no leyó mercados ni análisis actuales y no establece si existe una muestra histórica emparejada suficiente. Sin esa muestra no es posible medir cuánto del gap observado por el usuario era vig, ni dar diferencias media/mediana frente al mercado. La desviación frente a outcomes que se mide aquí tampoco cuantifica por sí sola la causa del gap de precio.

## Estabilidad por temporada

| Grupo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2020 | 539 | 1.745842 | 0.782376 | 0.197202 | 0.236841 | 0.171587 | 2.3940 | 2.4082 |
| 2021 | 570 | 1.737550 | 0.797625 | 0.224738 | 0.226541 | 0.144576 | 2.3310 | 2.1667 |
| 2022 | 572 | 1.668726 | 0.729663 | 0.229917 | 0.214696 | 0.120860 | 2.1993 | 2.0682 |
| 2023 | 571 | 1.724318 | 0.786979 | 0.229546 | 0.217618 | 0.135258 | 2.0707 | 2.0788 |
| 2024 | 571 | 1.706835 | 0.766108 | 0.217911 | 0.215753 | 0.134145 | 2.1453 | 2.1804 |
| 2025 | 570 | 1.717358 | 0.770080 | 0.218176 | 0.228586 | 0.150660 | 2.1863 | 2.2246 |

| Grupo | n | Sesgo ≥2 (pp) | ECE ≥2 (pp) | Sesgo ≥3 (pp) | ECE ≥3 (pp) | Sesgo ≥4 (pp) | ECE ≥4 (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2020 | 539 | -4.597 | 5.378 | -2.811 | 4.360 | -0.306 | 2.002 |
| 2021 | 570 | +3.805 | 4.440 | +2.483 | 3.166 | +2.647 | 3.467 |
| 2022 | 572 | +0.822 | 2.768 | +3.276 | 3.276 | +4.388 | 4.388 |
| 2023 | 571 | -1.279 | 3.839 | -0.367 | 4.034 | -0.423 | 2.779 |
| 2024 | 571 | -2.056 | 6.492 | -1.436 | 3.624 | -0.096 | 1.784 |
| 2025 | 570 | -2.495 | 2.536 | -1.773 | 2.654 | -1.450 | 1.598 |

El signo del sesgo ≥2 cambia: subestimación en 2020, 2023, 2024 y 2025, sobreestimación en 2021 y 2022. El resultado agrupado no debe presentarse como garantía para una temporada o selección individual.

## Folds temporales

| Temporada evaluada | Entrenamiento | Filas de entrenamiento | Filas evaluadas |
| --- | --- | --- | --- |
| 2020 | 2016–2019 | 2142 | 539 |
| 2021 | 2016–2020 | 2681 | 570 |
| 2022 | 2016–2021 | 3251 | 572 |
| 2023 | 2016–2022 | 3823 | 571 |
| 2024 | 2016–2023 | 4394 | 571 |
| 2025 | 2016–2024 | 4965 | 570 |

## Calibración por intervalo de probabilidad y grupos de semanas

Los límites son [inferior, superior), salvo el último que incluye 100%. Se muestran también intervalos vacíos. Las bandas Wilson 95% corresponden a frecuencias agregadas; no son intervalos por pick y pueden ser optimistas por la dependencia entre partidos, equipos y kickers. ECE y diferencias por estrato son descripciones, no pruebas de significación. No se aplicó corrección por comparaciones múltiples.

### Todas las semanas

**XPM ≥2** — ECE 1.739 pp; sesgo -0.933 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 0 | — | — | — | — |
| 10–20% | 0 | — | — | — | — |
| 20–30% | 1 | 23.18% | 100.00% | -76.82 | 20.65–100.00% |
| 30–40% | 43 | 36.64% | 53.49% | -16.85 | 38.92–67.49% |
| 40–50% | 291 | 46.17% | 47.08% | -0.91 | 41.42–52.81% |
| 50–60% | 799 | 55.61% | 58.07% | -2.47 | 54.62–61.45% |
| 60–70% | 1322 | 65.02% | 64.22% | +0.80 | 61.60–66.76% |
| 70–80% | 777 | 74.42% | 76.32% | -1.90 | 73.21–79.17% |
| 80–90% | 158 | 82.96% | 81.01% | +1.95 | 74.19–86.36% |
| 90–100% | 2 | 90.57% | 100.00% | -9.43 | 34.24–100.00% |

**XPM ≥3** — ECE 1.050 pp; sesgo -0.079 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 1 | 6.48% | 0.00% | +6.48 | 0.00–79.35% |
| 10–20% | 146 | 17.11% | 20.55% | -3.44 | 14.79–27.82% |
| 20–30% | 672 | 25.50% | 23.96% | +1.54 | 20.88–27.33% |
| 30–40% | 1216 | 35.28% | 35.03% | +0.25 | 32.40–37.76% |
| 40–50% | 839 | 44.51% | 45.65% | -1.14 | 42.31–49.03% |
| 50–60% | 417 | 53.89% | 53.24% | +0.65 | 48.44–57.97% |
| 60–70% | 92 | 63.51% | 68.48% | -4.97 | 58.41–77.07% |
| 70–80% | 10 | 73.28% | 70.00% | +3.28 | 39.68–89.22% |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

**XPM ≥4** — ECE 0.916 pp; sesgo +0.805 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 473 | 7.69% | 7.19% | +0.50 | 5.19–9.88% |
| 10–20% | 1605 | 15.39% | 14.14% | +1.24 | 12.52–15.93% |
| 20–30% | 944 | 24.41% | 24.47% | -0.06 | 21.83–27.31% |
| 30–40% | 307 | 33.83% | 34.20% | -0.37 | 29.12–39.67% |
| 40–50% | 55 | 43.32% | 30.91% | +12.41 | 20.28–44.03% |
| 50–60% | 9 | 53.31% | 55.56% | -2.25 | 26.67–81.12% |
| 60–70% | 0 | — | — | — | — |
| 70–80% | 0 | — | — | — | — |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

### Semanas 1-4

**XPM ≥2** — ECE 1.832 pp; sesgo -0.549 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 0 | — | — | — | — |
| 10–20% | 0 | — | — | — | — |
| 20–30% | 0 | — | — | — | — |
| 30–40% | 0 | — | — | — | — |
| 40–50% | 28 | 46.91% | 46.43% | +0.48 | 29.53–64.19% |
| 50–60% | 162 | 57.04% | 59.26% | -2.22 | 51.56–66.53% |
| 60–70% | 425 | 65.36% | 64.24% | +1.13 | 59.57–68.65% |
| 70–80% | 147 | 73.92% | 77.55% | -3.63 | 70.15–83.54% |
| 80–90% | 7 | 82.39% | 85.71% | -3.32 | 48.69–97.43% |
| 90–100% | 0 | — | — | — | — |

**XPM ≥3** — ECE 2.116 pp; sesgo -0.032 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 0 | — | — | — | — |
| 10–20% | 7 | 18.34% | 42.86% | -24.51 | 15.82–74.95% |
| 20–30% | 87 | 26.16% | 32.18% | -6.03 | 23.30–42.57% |
| 30–40% | 381 | 35.65% | 34.91% | +0.74 | 30.29–39.82% |
| 40–50% | 228 | 44.12% | 42.98% | +1.13 | 36.73–49.47% |
| 50–60% | 60 | 52.65% | 48.33% | +4.32 | 36.18–60.69% |
| 60–70% | 6 | 61.66% | 83.33% | -21.67 | 43.65–96.99% |
| 70–80% | 0 | — | — | — | — |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

**XPM ≥4** — ECE 1.666 pp; sesgo +1.175 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 40 | 8.23% | 12.50% | -4.27 | 5.46–26.11% |
| 10–20% | 445 | 16.08% | 14.38% | +1.70 | 11.43–17.95% |
| 20–30% | 245 | 23.82% | 22.45% | +1.37 | 17.67–28.08% |
| 30–40% | 37 | 32.48% | 32.43% | +0.05 | 19.63–48.54% |
| 40–50% | 2 | 41.11% | 50.00% | -8.89 | 9.45–90.55% |
| 50–60% | 0 | — | — | — | — |
| 60–70% | 0 | — | — | — | — |
| 70–80% | 0 | — | — | — | — |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

### Semanas 5-8

**XPM ≥2** — ECE 2.239 pp; sesgo -1.013 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 0 | — | — | — | — |
| 10–20% | 0 | — | — | — | — |
| 20–30% | 0 | — | — | — | — |
| 30–40% | 11 | 36.84% | 36.36% | +0.48 | 15.17–64.62% |
| 40–50% | 58 | 45.87% | 39.66% | +6.21 | 28.09–52.51% |
| 50–60% | 146 | 55.14% | 57.53% | -2.39 | 49.42–65.26% |
| 60–70% | 251 | 65.21% | 67.73% | -2.52 | 61.72–73.21% |
| 70–80% | 186 | 74.50% | 75.27% | -0.77 | 68.60–80.92% |
| 80–90% | 44 | 83.22% | 81.82% | +1.40 | 68.04–90.49% |
| 90–100% | 1 | 90.50% | 100.00% | -9.50 | 20.65–100.00% |

**XPM ≥3** — ECE 3.895 pp; sesgo +0.664 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 0 | — | — | — | — |
| 10–20% | 33 | 16.98% | 3.03% | +13.95 | 0.54–15.32% |
| 20–30% | 136 | 25.46% | 23.53% | +1.93 | 17.19–31.32% |
| 30–40% | 206 | 35.47% | 40.78% | -5.30 | 34.29–47.60% |
| 40–50% | 189 | 44.44% | 40.74% | +3.70 | 33.99–47.86% |
| 50–60% | 104 | 54.26% | 53.85% | +0.41 | 44.30–63.12% |
| 60–70% | 24 | 63.51% | 58.33% | +5.18 | 38.83–75.53% |
| 70–80% | 5 | 73.31% | 80.00% | -6.69 | 37.55–96.38% |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

**XPM ≥4** — ECE 0.869 pp; sesgo +0.346 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 96 | 7.52% | 4.17% | +3.36 | 1.63–10.23% |
| 10–20% | 289 | 15.31% | 15.57% | -0.26 | 11.85–20.20% |
| 20–30% | 214 | 24.41% | 24.30% | +0.11 | 19.04–30.47% |
| 30–40% | 78 | 34.13% | 33.33% | +0.80 | 23.87–44.36% |
| 40–50% | 16 | 43.33% | 50.00% | -6.67 | 28.00–72.00% |
| 50–60% | 4 | 53.90% | 50.00% | +3.90 | 15.00–85.00% |
| 60–70% | 0 | — | — | — | — |
| 70–80% | 0 | — | — | — | — |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

### Semanas 9+

**XPM ≥2** — ECE 2.594 pp; sesgo -1.057 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 0 | — | — | — | — |
| 10–20% | 0 | — | — | — | — |
| 20–30% | 1 | 23.18% | 100.00% | -76.82 | 20.65–100.00% |
| 30–40% | 32 | 36.57% | 59.38% | -22.80 | 42.26–74.48% |
| 40–50% | 205 | 46.16% | 49.27% | -3.11 | 42.50–56.06% |
| 50–60% | 491 | 55.27% | 57.84% | -2.57 | 53.43–62.13% |
| 60–70% | 646 | 64.72% | 62.85% | +1.88 | 59.06–66.49% |
| 70–80% | 444 | 74.55% | 76.35% | -1.81 | 72.18–80.07% |
| 80–90% | 107 | 82.90% | 80.37% | +2.52 | 71.85–86.79% |
| 90–100% | 1 | 90.64% | 100.00% | -9.36 | 20.65–100.00% |

**XPM ≥3** — ECE 2.941 pp; sesgo -0.366 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 1 | 6.48% | 0.00% | +6.48 | 0.00–79.35% |
| 10–20% | 106 | 17.07% | 24.53% | -7.46 | 17.32–33.51% |
| 20–30% | 449 | 25.39% | 22.49% | +2.89 | 18.87–26.58% |
| 30–40% | 629 | 34.99% | 33.23% | +1.76 | 29.66–37.00% |
| 40–50% | 422 | 44.76% | 49.29% | -4.53 | 44.55–54.04% |
| 50–60% | 253 | 54.03% | 54.15% | -0.12 | 47.99–60.18% |
| 60–70% | 62 | 63.68% | 70.97% | -7.29 | 58.71–80.78% |
| 70–80% | 5 | 73.24% | 60.00% | +13.24 | 23.07–88.24% |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

**XPM ≥4** — ECE 1.473 pp; sesgo +0.823 pp.

| Intervalo | n | Predicho | Observado | Sesgo (pp) | Wilson 95% observado |
| --- | --- | --- | --- | --- | --- |
| 0–10% | 337 | 7.68% | 7.42% | +0.26 | 5.08–10.72% |
| 10–20% | 871 | 15.06% | 13.55% | +1.51 | 11.43–15.98% |
| 20–30% | 485 | 24.72% | 25.57% | -0.85 | 21.89–29.63% |
| 30–40% | 192 | 33.97% | 34.90% | -0.93 | 28.51–41.87% |
| 40–50% | 37 | 43.44% | 21.62% | +21.81 | 11.39–37.20% |
| 50–60% | 5 | 52.84% | 60.00% | -7.16 | 23.07–88.24% |
| 60–70% | 0 | — | — | — | — |
| 70–80% | 0 | — | — | — | — |
| 80–90% | 0 | — | — | — | — |
| 90–100% | 0 | — | — | — | — |

## Alcance y reproducción

Fuente histórica congelada: `data/features/environment/d0e256364dde3016c76f/kicker_game_features.parquet`.
SHA-256 de fuente: `bb1730a0f957aea3dd86f22f5448858bf182cdbb39d8bf09ac238013f20ebb3f`.
SHA-256 de predicciones: `e2fae5a45e764c1b8f5eb116c6c33fd02963d0c785e304e22498357ec85b93ae`.
Cohorte: 5,535 filas elegibles 2016–2025; 3,393 pronósticos temporales fuera de muestra 2020–2025.

El lector proyecta explícitamente claves, las 82 features originales y XPM, después del filtro SQL `eligible_for_phase_4_training IS TRUE AND season BETWEEN 2016 AND 2025`. Cada fold ajusta una réplica diagnóstica de `poisson_glm_alpha_0.1` (alpha 0.1, max_iter 2000, tol 1e-8), incluida su imputación y escalado, exclusivamente en temporadas anteriores a la evaluada. No se abren ni reescriben los artefactos V1. No se consultaron resultados 2026, cuotas, logs de análisis actuales, red ni credenciales.

Reproducir desde la raíz del repositorio con `.venv/Scripts/python.exe -m kickedge.v2.audit`. Las predicciones exactas, sus claves, temporada, semana, historia previa, indicadores de 3/5 juegos, número de NULLs y límites de entrenamiento quedan en `data/v2/audit/oof_predictions.parquet`; el resumen completo está en `data/v2/audit/summary.json` y la procedencia en `data/v2/audit/metadata.json`. El lector reutiliza predicciones cuando coinciden fuente, configuración y checksum del archivo; `--recompute` ejecuta de nuevo los seis folds.

La arquitectura V1 fue elegida previamente. Estos folds sirven para diagnóstico retrospectivo con estimación temporal válida, pero no constituyen una selección de arquitectura históricamente ciega. La temporada 2025, antes holdout de V1, está autorizada ahora para desarrollo V2. Los resultados aquí no son una validación forward de V2.
