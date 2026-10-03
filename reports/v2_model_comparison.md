# KickEdge V2 — comparación de modelos (walk-forward 2020–2025)

## Resultado

Ningún candidato cumple la regla de selección registrada antes de ver resultados. Se selecciona el baseline con arquitectura V1 (`v1_style_glm_alpha_0.1`, 82 features), reentrenado 2016–2025 como "V2 final". El mejor retador es `carryover_glm_alpha_1` (101 features): mejora NLL agrupada 0.32% y RPS 0.69%, por debajo del umbral de 1% exigido para ambos. El carryover ayuda claramente en semanas 1–4 y en kickers sin historia de la temporada, pero la mejora total es pequeña.

No se retuvo calibración: el factor multiplicativo histórico es consistente en signo (λ algo alto), pero en evaluación rodante 2022–2025 empeora NLL y RPS en todos los candidatos. El retador estructural pierde frente al baseline.

## Datos y protocolo

- Dataset V2: 5,535 filas elegibles 2016–2025 (`data/v2/dataset/dataset.parquet`, SHA-256 de contenido `4acd9cff8d2e48381864fd28a3adeec9d0a18bdfa8add8c0ba95675986d04b94`), las 82 features V1 sin cambios más 19 columnas de carryover separadas. Ningún dato 2026.
- Walk-forward: cada temporada 2020–2025 se predice con un modelo ajustado solo en temporadas anteriores (2016 … año−1). 3,393 predicciones fuera de muestra por candidato, mismas filas para todos.
- El candidato A reproduce bit a bit las predicciones OOF del audit V1 (`data/v2/audit/oof_predictions.parquet`).
- Los resultados agrupados 2020–2025 son evidencia de desarrollo, no un test intocado: el audit de diagnóstico informó el diseño del carryover, así que existe optimismo de selección posible.

### Carryover (V2)

Temporada inmediatamente anterior y completa, nunca el partido objetivo ni el futuro; cada contribución tiene `available_at` ≤ cutoff. El historial del kicker sigue al jugador (ID estable aunque cambie de equipo); ofensiva y defensa siguen al equipo. Sin temporada previa → NULL explícito (no cero). Columnas: kicker `games/xpa/xpm/conversion_rate/xpm_per_game/xpa_per_game`; ofensiva `points/TD por partido, td_per_drive, red_zone_td_rate, epa_per_play, success_rate`; defensa los equivalentes permitidos; y `current_season_games_before`. Validación: el dataset se reconstruye con el mismo hash, el carryover del kicker coincide con las etiquetas s−1 en 4,663 filas y los puntos ofensivos con el bundle de origen; 872 filas sin temporada previa del kicker quedan NULL.

## Candidatos

| Candidato | Familia | Features | Hiperparámetros |
| --- | --- | --- | --- |
| A · GLM estilo V1 α0.1 (`v1_style_glm_alpha_0.1`) | glm | 82 | alpha 0.1, max_iter 2000, tol 1e-08 |
| B · GLM+carryover α0.1 (`carryover_glm_alpha_0.1`) | glm | 101 | alpha 0.1, max_iter 2000, tol 1e-08 |
| B2 · GLM+carryover α1 (`carryover_glm_alpha_1`) | glm | 101 | alpha 1.0, max_iter 2000, tol 1e-08 |
| C · Boosting Poisson+carryover (`carryover_poisson_boost`) | boost | 101 | 7 hojas, 100 iteraciones, learning rate 0.05, L2 10.0, hoja mínima 40, sin early stopping, seed 42 |
| D · Estructural (`structural_tries_pat_conversion`) | structural | 101 | tries Poisson alpha 0.1; logísticas C 1.0, max_iter 2000 |

Preprocesado de todos: receta V1 (imputación por mediana con indicadores de faltante en todas las columnas, StandardScaler salvo boosting, one-hot de `game_type`). El estructural modela oportunidades de TD (Poisson) → elección PAT vs 2PT (logística) → conversión (logística), y λ = E[TD]·P(PAT)·P(convertir); solo usa información pregame. Limitación documentada: no separa TD defensivos/especiales.

Ajuste "pequeño": solo α ∈ {0.1, 1} para el GLM con carryover y una configuración fija de boosting; no hubo búsqueda adicional.

## Regla de selección registrada

Un candidato reemplaza al baseline solo si mejora NLL y RPS agrupadas ≥1% (≥2% NLL para boosting o estructural), no empeora el Brier medio de umbrales más de 0.002, mejora NLL en al menos 4 de 6 temporadas y no empeora NLL/RPS de semanas 1–4. Nunca se selecciona por parecido con el mercado.

## OOF agrupado 2020–2025

| Modelo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Brier medio | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A · GLM estilo V1 α0.1 | 3393 | 1.716477 | 0.772023 | 0.219795 | 0.223207 | 0.142567 | 0.195190 | 2.2194 | 2.1857 |
| B · GLM+carryover α0.1 | 3393 | 1.717962 | 0.773201 | 0.220004 | 0.222822 | 0.142748 | 0.195191 | 2.2097 | 2.1857 |
| B2 · GLM+carryover α1 | 3393 | 1.710948 | 0.766659 | 0.218165 | 0.220807 | 0.141210 | 0.193394 | 2.2018 | 2.1857 |
| C · Boosting Poisson+carryover | 3393 | 1.712624 | 0.768142 | 0.219117 | 0.221389 | 0.141254 | 0.193920 | 2.1983 | 2.1857 |
| D · Estructural | 3393 | 1.720183 | 0.775012 | 0.220318 | 0.223084 | 0.143246 | 0.195550 | 2.2258 | 2.1857 |

## Aplicación de la regla

| Candidato | Ganancia NLL | Ganancia RPS | Δ Brier medio | Temporadas con mejor NLL | Δ NLL sem. 1–4 | Δ RPS sem. 1–4 | Umbral NLL | Pasa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B · GLM+carryover α0.1 | -0.09% | -0.15% | +0.0000 | 2/6 | -0.0154 | -0.0154 | 1% | no |
| B2 · GLM+carryover α1 | +0.32% | +0.69% | -0.0018 | 4/6 | -0.0235 | -0.0224 | 1% | no |
| C · Boosting Poisson+carryover | +0.22% | +0.50% | -0.0013 | 5/6 | -0.0232 | -0.0217 | 2% | no |
| D · Estructural | -0.22% | -0.39% | +0.0004 | 3/6 | -0.0151 | -0.0153 | 2% | no |

Ganancia positiva = mejor que A. Seleccionado: `v1_style_glm_alpha_0.1`.

## Por temporada (NLL / RPS)

| Temporada | n | A | B | B2 | C | D |
| --- | --- | --- | --- | --- | --- | --- |
| 2020 | 539 | 1.7458 / 0.7824 | 1.7565 / 0.7912 | 1.7469 / 0.7827 | 1.7432 / 0.7795 | 1.7669 / 0.7991 |
| 2021 | 570 | 1.7376 / 0.7976 | 1.7431 / 0.8019 | 1.7342 / 0.7926 | 1.7400 / 0.7985 | 1.7481 / 0.8064 |
| 2022 | 572 | 1.6687 / 0.7297 | 1.6692 / 0.7312 | 1.6577 / 0.7200 | 1.6611 / 0.7228 | 1.6715 / 0.7330 |
| 2023 | 571 | 1.7243 / 0.7870 | 1.7195 / 0.7814 | 1.7132 / 0.7763 | 1.7163 / 0.7794 | 1.7211 / 0.7823 |
| 2024 | 571 | 1.7068 / 0.7661 | 1.7115 / 0.7713 | 1.7092 / 0.7692 | 1.7066 / 0.7661 | 1.7066 / 0.7675 |
| 2025 | 570 | 1.7174 / 0.7701 | 1.7103 / 0.7634 | 1.7066 / 0.7601 | 1.7103 / 0.7633 | 1.7097 / 0.7633 |

## Por grupo de semanas (NLL / RPS)

| Semanas | n | A | B | B2 | C | D |
| --- | --- | --- | --- | --- | --- | --- |
| 1-4 | 769 | 1.7235 / 0.7757 | 1.7081 / 0.7603 | 1.7000 / 0.7533 | 1.7004 / 0.7540 | 1.7085 / 0.7604 |
| 5-8 | 697 | 1.7129 / 0.7686 | 1.7154 / 0.7709 | 1.7107 / 0.7659 | 1.7229 / 0.7765 | 1.7170 / 0.7723 |
| 9+ | 1927 | 1.7149 / 0.7718 | 1.7228 / 0.7792 | 1.7154 / 0.7723 | 1.7138 / 0.7708 | 1.7260 / 0.7818 |

## Por historia previa del kicker en la temporada (NLL / RPS)

| Partidos previos | n | A | B | B2 | C | D |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 271 | 1.6782 / 0.7509 | 1.6519 / 0.7274 | 1.6476 / 0.7246 | 1.6504 / 0.7259 | 1.6481 / 0.7252 |
| 1-2 | 482 | 1.7385 / 0.7893 | 1.7360 / 0.7862 | 1.7219 / 0.7744 | 1.7266 / 0.7792 | 1.7382 / 0.7866 |
| 3-4 | 451 | 1.7209 / 0.7747 | 1.7163 / 0.7691 | 1.7067 / 0.7604 | 1.7152 / 0.7684 | 1.7188 / 0.7709 |
| 5+ | 2189 | 1.7154 / 0.7703 | 1.7225 / 0.7769 | 1.7172 / 0.7715 | 1.7167 / 0.7709 | 1.7254 / 0.7795 |

## ¿Ayudó el carryover?

Sí al inicio de temporada y con poca historia; casi nada en total.

- Semanas 1–4: NLL 1.72353 (A) → 1.70003 (B2), -1.36%; RPS 0.77567 → 0.75329, -2.88%.
- Sin partidos previos en la temporada (n=271): NLL 1.67824 → 1.64759 (-1.83%).
- Con 5+ partidos previos (n=2189, la mayoría de filas): 1.71545 → 1.71724 (+0.10%), es decir, sin mejora cuando ya hay historia actual.
- Agrupado: B2 -0.32% NLL, -0.69% RPS, Brier medio -0.0018. Con α 0.1 (B) el carryover empeora levemente el total (+0.09% NLL; mejor solo en 2 de 6 temporadas): 19 columnas más con poca regularización añaden varianza.
- Boosting (C): -0.22% NLL, lejos del 2% exigido para su complejidad adicional.

Como pide la especificación, no se adopta el carryover solo porque mejora el inicio de temporada: el total no alcanza el umbral registrado.

## Calibración

Prueba rodante: para cada temporada 2022–2025, factor multiplicativo sum(y)/sum(λ) ajustado solo con OOF de temporadas anteriores; nunca en la misma fila ni con 2026, nunca con cuotas.

| Candidato | Factores 2022–2025 | NLL cruda → calibrada | RPS cruda → calibrada | ECE media cruda → calibrada | Retenida |
| --- | --- | --- | --- | --- | --- |
| A · GLM estilo V1 α0.1 | 0.967, 0.958, 0.969, 0.978 | 1.70429 → 1.70492 | 0.76319 → 0.76405 | 3.31 → 3.32 pp | no |
| B · GLM+carryover α0.1 | 0.955, 0.953, 0.970, 0.986 | 1.70260 → 1.70429 | 0.76180 → 0.76351 | 3.20 → 3.57 pp | no |
| B2 · GLM+carryover α1 | 0.958, 0.959, 0.975, 0.989 | 1.69665 → 1.69821 | 0.75639 → 0.75815 | 3.15 → 3.59 pp | no |
| C · Boosting Poisson+carryover | 0.982, 0.974, 0.985, 0.994 | 1.69857 → 1.69899 | 0.75789 → 0.75847 | 2.70 → 2.96 pp | no |
| D · Estructural | 0.948, 0.948, 0.963, 0.978 | 1.70220 → 1.70390 | 0.76149 → 0.76330 | 3.53 → 3.47 pp | no |

Todos los factores son < 1: históricamente los modelos predicen λ algo alto (A: media predicha 2.2194 frente a 2.1857 observada, +1.5%). No hay subestimación global que corregir hacia arriba. La corrección hacia abajo tampoco mejora fuera de muestra: el exceso medio viene de la cola (≥4 sobreestimado) mientras ≥2 está levemente subestimado, y un factor uniforme sobre λ desplaza todos los umbrales a la vez. Calibración excluida.

## Retador estructural

D · Estructural: NLL 1.720183 frente a 1.716477 (+0.22%), RPS +0.39%. Mejora semanas 1–4 (por el carryover que comparte) pero pierde en total y necesitaría +2%. Se documenta como perdedor y no se congela.

## Congelamiento

Antes de leer cualquier outcome 2026 (`reports/v2_freeze.json`, 2026-10-03T21:19:44.275567+00:00): V2 final = `v1_style_glm_alpha_0.1` y retador = `carryover_glm_alpha_1` (mejor NLL agrupada restante), ambos reajustados 2016–2025 con artefactos en `models/v2/<nombre>/model.joblib` y SHA-256 registrados, features, hiperparámetros, preprocesado, calibración (ninguna), hashes de código y del dataset. Resultado forward: `reports/v2_forward_2026_validation.md`.

## Reproducción

```
.venv/Scripts/python.exe -m kickedge.v2 dataset   # data/v2/dataset (mismo content hash)
.venv/Scripts/python.exe -m kickedge.v2 compare   # data/v2/comparison/*.parquet y comparison.json
```

`compare` reproduce bit a bit `comparison.json` y los cinco parquet OOF (verificado). Los módulos congelados (`carryover.py`, `models.py`, `training.py`, `audit.py`, `freeze.py`) mantienen los hashes registrados en el congelamiento.
