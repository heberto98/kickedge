# KickEdge V2 — validación forward 2026 (evaluación única)

## Veredicto

**V1 REMAINS CHAMPION.** La selección histórica no eligió un candidato nuevo y la muestra forward (84 filas) no alcanza las 150 exigidas. V2 final no se adopta y no se retoca nada después de la revelación.

## Cronología

| Evento | Momento (UTC) |
| --- | --- |
| Congelamiento y preregistro (`reports/v2_freeze.json`) | 2026-10-03T21:19:44.275567+00:00 |
| Commit del congelamiento `5faf00a` (publicado) | 2026-10-03T21:21:19+00:00 |
| Primer intento de revelación: marcador escrito, 0 filas, nada puntuado | 2026-10-03T21:23:25.484368+00:00 |
| Commit de la enmienda `467261a` (publicado) | 2026-10-03T21:26:36+00:00 |
| Revelación única con enmienda registrada | 2026-10-03T21:26:53.111219+00:00 |

Enmienda (texto literal registrado en `data/v2/forward/result.json`): First attempt (2026-10-03T21:23:25Z) built 0 rows because the forward filter required eligible_for_pregame_training, a label flag that build.py hard-codes to false (the preregistration wording named it too). No outcome was scored and no metric computed; models and freeze unchanged. Rows now follow the V1 materializer training rule: usable label, identity checks, target season, complete released history, no missing team metric. Fix committed as 467261a before resuming.

Antes de escribir el marcador se verificaron los SHA-256 de los artefactos congelados y se cargó el artefacto V1 con su verificación. Una segunda llamada devuelve el resultado guardado; un marcador sin resultado bloquea cualquier reintento salvo enmienda explícita.

## Filas

Todas las filas kicker-partido 2026 de partidos completados en la caché nflverse local al momento de revelar: 84 filas, 42 partidos, semanas 1, 2, 3, 4. Mismas reglas que el entrenamiento V1: etiqueta utilizable, identidad verificada, historia completa y liberada antes del cutoff (kickoff programado − 60 min), sin métricas de equipo faltantes. Features: las 82 V1 reconstruidas por los builders 7B y carryover 2025. Los tres modelos se puntúan en exactamente las mismas filas.

Exclusiones (14): `history_unavailable_before_cutoff` 14 — un partido previo de 2026 todavía no había pasado la compuerta conservadora de liberación en el cutoff; el entrenamiento excluye esas filas igual.

## Resultados

| Modelo | n | NLL | RPS | Brier ≥2 | Brier ≥3 | Brier ≥4 | Brier medio | Media predicha | Media observada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 (campeón congelado) | 84 | 1.769816 | 0.812019 | 0.227749 | 0.244504 | 0.157779 | 0.210011 | 2.2229 | 2.2738 |
| V2 final (A reentrenado 2016–2025) | 84 | 1.776566 | 0.817641 | 0.229003 | 0.247158 | 0.158879 | 0.211680 | 2.2352 | 2.2738 |
| Retador B2 (carryover α1) | 84 | 1.741668 | 0.783287 | 0.218494 | 0.234810 | 0.149407 | 0.200904 | 2.2078 | 2.2738 |

| Modelo | ECE ≥2 / ≥3 / ≥4 (pp) | Sesgo ≥2 / ≥3 / ≥4 (pp) |
| --- | --- | --- |
| V1 (campeón congelado) | 7.4 / 7.6 / 6.8 | -1.2 / -3.5 / -1.3 |
| V2 final (A reentrenado 2016–2025) | 10.1 / 8.2 / 5.8 | -1.0 / -3.2 / -1.1 |
| Retador B2 (carryover α1) | 5.3 / 5.7 / 4.5 | -1.5 / -3.9 / -1.7 |

Diferencias frente a V1 (negativo = mejor que V1):

| Modelo | Δ NLL | Δ RPS | Δ Brier medio |
| --- | --- | --- | --- |
| V2 final (A reentrenado 2016–2025) | +0.38% | +0.69% | +0.0017 |
| Retador B2 (carryover α1) | -1.59% | -3.54% | -0.0091 |

Por semana (NLL):

| Semana | n | V1 (campeón congelado) | V2 final (A reentrenado 2016–2025) | Retador B2 (carryover α1) |
| --- | --- | --- | --- | --- |
| 1 | 26 | 1.8667 | 1.8750 | 1.8527 |
| 2 | 28 | 1.7865 | 1.7970 | 1.7466 |
| 3 | 28 | 1.6867 | 1.6888 | 1.6516 |
| 4 | 2 | 1.4401 | 1.4405 | 1.4899 |

## Compuerta de adopción (registrada antes de revelar)

| Condición | Resultado |
| --- | --- |
| La selección histórica eligió un candidato nuevo | no |
| ≥150 filas forward comunes | no (84) |
| V2 final sin deterioro >2% NLL/RPS ni >0.005 Brier medio frente a V1 | sí |

Adopción de V2: **no**.

## Interpretación

- V2 final es la arquitectura V1 con 2025 añadido al ajuste; en estas 84 filas queda ligeramente peor que V1 (+0.38% NLL), dentro del ruido de una muestra tan pequeña.
- El retador B2 mejora a V1 en las semanas 1–4 de 2026 (-1.59% NLL, -3.54% RPS), en línea con su ventaja histórica al inicio de temporada. No fue la selección registrada y 84 filas de un solo bloque de semanas tempranas no bastan: no se adopta ni se promueve tras mirar 2026. Si se quiere probar, debe ser una nueva evaluación preregistrada sobre semanas posteriores con el artefacto ya congelado.
- 2026, semanas 1–4: media predicha por V1 2.223 frente a 2.274 observada (-2.2%); sesgo ≥2 -1.2 pp. Ligera subestimación temprana, del mismo orden que la variación entre temporadas del audit histórico.

## Auditoría de mercado (después del congelamiento y de la revelación)

Descriptiva: no alimenta ninguna selección ni calibración y no usa cuotas como target. Probabilidades: raw implied = 1/cuota decimal (incluye el margen), no-vig = normalización proporcional del par over/under, KickEdge = Poisson con la λ congelada de V1 para esa fila forward.

### Fuentes

1. Análisis guardados en la app (`data/current/analyses`): 26 análisis, 11 cotizaciones distintas, solo 1 con ambos precios. KickEdge − raw implied: media -8.2 pp, mediana -12.4 pp, KickEdge por debajo en 82% de las cotizaciones. 10 de 11 son overs y 7 de ellas Over 1.5 favoritos (−200 a −500, raw implied 67–83%), muy por encima del Over 1.5 de cierre de Fliff (raw medio 57%); no se puede verificar el libro ni el momento de esas cotizaciones manuales. Con un solo par, la diferencia frente a no-vig no es estimable con esta fuente.
2. Archivo de cierre ParlayAPI (`/v1/historical/.../closing-odds`, XPM, 2026-09-02 a 2026-09-30), una captura de solo lectura a las 2026-10-03T21:31:30.307484+00:00 (SHA-256 `c6dc26147fb5989ec5e8d7f570a33c753a4b3e367064d466a9c3979f73d7ed8a`, 574 filas). Emparejado con las filas forward por nombre del kicker y fecha más cercana (≤3 días): 208 cotizaciones en 82 kicker-partidos; 73 duplicados descartados (se conserva la fecha más cercana, nunca se promedia).

Limitación importante: el archivo no trae hora de la cotización ni kickoff (574 de 574 filas sin `commence_time`) y contiene precios en vivo (por ejemplo, un kicker que terminó con 8 XPM cotizado Over 5.5 a −145, y escaleras donde Over 2.5 paga más que Over 3.5). No es evidencia pregame verificada: no se puntúan outcomes con estos precios, y un filtro de escalera (P no-vig de over decreciente con la línea, por libro y kicker-partido) marca los conjuntos que no pueden ser un tablero pregame único. Sleeper es DFS de pago fijo (no cuota de sportsbook) y se muestra aparte.

### Resultados

| Muestra | n | Lado | Raw implied | No-vig | KickEdge V1 | KE − raw media/mediana (pp) | KE < raw | KE − no-vig media/mediana (pp) | KE − no-vig p10/p25/p75/p90 | KE < no-vig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fliff (sportsbook), todas | 111 | over | 53.4% | 48.2% | 46.1% | -7.3 / -5.3 | 63% | -2.1 / -0.5 | [-28.2, -15.4, +11.3, +25.5] | 50% |
| Fliff (sportsbook), todas | 111 | under | 57.4% | 51.8% | 53.9% | -3.5 / -5.4 | 61% | +2.1 / +0.5 | [-25.5, -11.3, +15.4, +28.2] | 50% |
| Fliff, escalera consistente | 94 | over | 53.6% | 48.4% | 47.6% | -6.0 / -5.2 | 63% | -0.8 / -0.2 | [-26.9, -11.9, +11.4, +25.4] | 50% |
| Fliff, escalera consistente | 94 | under | 57.2% | 51.6% | 52.4% | -4.7 / -5.6 | 64% | +0.8 / +0.2 | [-25.4, -11.4, +11.9, +26.9] | 50% |
| Sleeper (DFS) | 97 | over | 56.5% | 50.0% | 48.2% | -8.2 / -8.5 | 78% | -1.8 / -1.7 | [-16.2, -10.7, +4.9, +13.9] | 59% |
| Sleeper (DFS) | 97 | under | 56.4% | 50.0% | 51.8% | -4.6 / -4.3 | 65% | +1.8 / +1.7 | [-13.9, -4.9, +10.7, +16.2] | 41% |

Overround medio: Fliff 10.8 pp (mediana 10.8); Sleeper 12.9 pp.

Por línea (Fliff, escalera consistente; lado over):

| Línea | n | Raw implied | No-vig | KickEdge V1 | KE − no-vig media/mediana (pp) | KE < no-vig |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | 5 | 59.2% | 53.6% | 88.1% | +34.5 / +29.6 | 0% |
| 1.5 | 38 | 57.1% | 51.5% | 63.4% | +12.0 / +11.3 | 18% |
| 2.5 | 35 | 51.6% | 46.6% | 38.5% | -8.1 / -6.5 | 71% |
| 3.5 | 11 | 40.9% | 36.9% | 22.2% | -14.7 / -13.9 | 91% |
| 4.5 | 4 | 65.8% | 59.6% | 7.2% | -52.3 / -55.9 | 100% |
| 5.5 | 1 | 58.3% | 52.2% | 1.7% | -50.5 / -50.5 | 100% |

Las líneas 0.5 y ≥4.5 son casi con seguridad precios en vivo (P no-vig ≈ 50% para Over 4.5 XPM es imposible antes del partido); se muestran sin ocultar.

### Por qué KickEdge "siempre quedaba debajo"

1. **Base de comparación (efecto principal y mecánico).** El precio de un solo lado incluye el margen: con un overround de ~11–13 pp, cada lado tiene un raw implied ~5–6 pp por encima de su no-vig. Una probabilidad justa (que suma 1) queda debajo del raw implied **en ambos lados**: en Fliff KickEdge está por debajo del raw implied en 63% de los overs y en 61% de los unders. Frente a no-vig la diferencia media es -0.8 pp (mediana -0.2) y KickEdge queda debajo en 50% de los casos: no hay un desfase global de nivel.
2. **Qué se miraba.** En uso manual se ingresaba casi siempre un solo precio (sin no-vig posible) y de overs favoritos, donde el raw implied es más alto.
3. **Forma de la distribución, no nivel.** Por línea, KickEdge da más probabilidad que el mercado a Over 1.5 y menos a Over 2.5/3.5. Con esta fuente sin horas no puede atribuirse a mercado o modelo: es una diferencia de dispersión, no un sesgo uniforme, y no justifica subir probabilidades.
4. **Outcomes.** No hay subestimación global histórica (media predicha +1.5% sobre lo observado 2020–2025). En 2026 semanas 1–4, V1 quedó -2.2% en media, una desviación pequeña.

No se eligió ni se modificó ningún modelo por su parecido con el mercado.

## Reproducción

- Resultado forward guardado: `data/v2/forward/result.json` (incluye predicciones por fila); marcador: `data/v2/forward/reveal_marker.json`. `kickedge.v2.forward.reveal` solo devuelve el resultado guardado.
- Auditoría de mercado: `.venv/Scripts/python.exe -m kickedge.v2 market` sobre la captura guardada en `data/v2/market/closing_odds_2026.json`; salida en `data/v2/market/audit.json`.
