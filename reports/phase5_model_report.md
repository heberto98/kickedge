# Fase 5: primer modelo probabilistico XPM

2025 permanece ciego: solo se consultaron schema y conteo, sin labels ni predicciones.

Poblacion condicionada a participacion observada del kicker. El usuario del producto proporciona el kicker. No se predice su titularidad. Se preservan ceros y todas las filas previamente elegibles.

## Target antes de fitting

| Fold | n | Media | Varianza muestral | Var/media | Max | 0 / 1 / 2 / 3 / 4 / 5+ |
|---|---:|---:|---:|---:|---:|---|
| train_2016_2023 | 4394 | 2.182066 | 2.104336 | 0.964377 | 10 | 522 / 1008 / 1184 / 905 / 494 / 281 |
| validation_2024 | 571 | 2.180385 | 2.179685 | 0.999679 | 7 | 67 / 138 / 152 / 113 / 57 / 44 |

No se incluye Negative Binomial: varianza/media TRAIN=0.964377, sin sobredispersion marginal clara (>1.2 como umbral previo). NB agrega dispersion y no aborda subdispersion; no se justifica ampliar este primer conjunto.

## Comparacion: solo 2024

| Modelo | NLL | RPS | Brier >=2 | Brier >=3 | Brier >=4 | MAE | RMSE | Deviance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| global_poisson | 1.757053 | 0.812282 | 0.230124 | 0.234326 | 0.145595 | 1.178696 | 1.475083 | 1.143870 |
| poisson_glm_alpha_0.1 | 1.706835 | 0.766108 | 0.217911 | 0.215753 | 0.134145 | 1.109963 | 1.395622 | 1.043434 |
| poisson_glm_alpha_1.0 | 1.706866 | 0.766229 | 0.218044 | 0.215565 | 0.134338 | 1.106376 | 1.396790 | 1.043495 |
| poisson_boost_leaves_7 | 1.705301 | 0.764618 | 0.218638 | 0.214572 | 0.133286 | 1.106272 | 1.393425 | 1.040366 |
| poisson_boost_leaves_15 | 1.706756 | 0.766024 | 0.219238 | 0.214467 | 0.133496 | 1.109656 | 1.395526 | 1.043276 |

Seleccion enmendada: **poisson_glm_alpha_0.1**. Preferencia por simplicidad; cambio de familia exige mejora NLL >=1%, deterioro medio Brier <=0.002 y RPS sin deterioro. Dentro de familia: menor NLL. ECE es diagnostico, no veto entre familias. Enmienda posterior a revision de validacion; no significancia estadistica.

Seleccion bajo regla original: **global_poisson**. Preferencia por simplicidad; cambio de familia exige mejora NLL >=1%, deterioro medio Brier <=0.002 y deterioro medio ECE <=0.02. Dentro de familia: menor NLL. Regla original previa a validacion.

selection_policy_amendment: post-validation-review. Las cinco configuraciones permanecen intactas. El veto ECE original confundia calibracion empirica con resolucion entre familias: una prediccion constante puede tener ECE casi cero sin discriminar contextos; bins variables tambien reflejan error muestral. Esta seleccion explora 2024; no constituye evidencia independiente de superioridad.

No hay calibracion ajustada. ECE bruto de bins fijos (10 bins de ancho 0.1):

| Modelo | ECE >=2 | ECE >=3 | ECE >=4 |
|---|---:|---:|---:|
| global_poisson | 0.000056 | 0.002307 | 0.000250 |
| poisson_glm_alpha_0.1 | 0.064921 | 0.036243 | 0.017837 |
| poisson_glm_alpha_1.0 | 0.027950 | 0.052762 | 0.033619 |
| poisson_boost_leaves_7 | 0.027990 | 0.045251 | 0.039373 |
| poisson_boost_leaves_15 | 0.025056 | 0.042071 | 0.016745 |

## Diagnostico de influencia

standardized numeric coefficients; unscaled category contrasts; log-mean scale, not causal

| Variable | Coeficiente o incremento NLL |
|---|---:|
| numeric__defense_points_allowed_per_game_last_5 | 0.063315 |
| numeric__defense_success_rate_allowed_last_3 | 0.045085 |
| numeric__offense_points_per_game_last_5 | 0.042998 |
| numeric__defense_td_allowed_per_drive_last_3 | -0.042154 |
| numeric__defense_td_allowed_per_drive_last_5 | -0.040638 |
| numeric__defense_success_rate_allowed_last_5 | -0.039784 |
| numeric__offense_success_rate_before | 0.034219 |
| numeric__kicker_xpm_per_game_before | 0.034191 |
| numeric__is_home | 0.029259 |
| numeric__is_away | -0.029259 |
| numeric__kicker_games_before | -0.025036 |
| numeric__kicker_xpm_before | 0.024761 |
| numeric__kicker_xpa_before | 0.023124 |
| numeric__team_two_point_attempt_rate_before | -0.022126 |
| numeric__team_days_rest | 0.020242 |

## Artefactos y limites

Refit final: 4965 filas 2016–2024; receta e hiperparametros congelados. Se reajustan medianas, escalas, categorias y parametros con ese conjunto. Nunca con 2025.

Binarios locales ignorados: model.joblib (refit), selection_model.joblib (entrenado hasta 2023), metadata.json. Las metricas publicadas corresponden al segundo; no miden el rendimiento del refit.

El JSON adjunto registra todas las configuraciones, bins con conteos, hashes, versiones y sanity checks. RPS usa la identidad exacta de Poisson con funciones de Bessel escaladas; la cola no se trunca.

Limites: una sola temporada de validacion, predictores correlacionados, distribucion condicional Poisson, historia retrospectiva con la excepcion acotada de calendario ya aprobada. La dispersion marginal no prueba la adecuacion de toda la distribucion condicional. No hay inferencia causal, calibracion formal, validacion externa, evidencia de ROI ni comparacion con mercado. Fase 6 no ejecutada. La repeticion con seed fijo demuestra reproducibilidad determinista, no estabilidad temporal ni muestral. La incertidumbre del ranking de arquitecturas no fue cuantificada.
