# Fase 6: validación blind de 2025

**Resultado: PASS**. Evaluación UTC: 2026-10-02T20:29:05.975985+00:00.

2025 fue utilizado una única vez como blind holdout y no se utilizó para modificar el modelo.

## Integridad y protocolo congelado

Preflight UTC: 2026-10-02T20:28:51.402161+00:00. Targets accedidos durante preflight: False.

Modelo SHA-256: `c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0`. Dataset: `bb1730a0f957aea3dd86f22f5448858bf182cdbb39d8bf09ac238013f20ebb3f`. Contrato: `a8030cbf2224e3cebea5e48cd38b2559c154c73175881fdab5d7e8000caa8879`.

Modelo: {'name': 'poisson_glm_alpha_0.1', 'family': 'glm', 'params': {'alpha': 0.1, 'max_iter': 2000, 'tol': 1e-08}}; 82 features; temporadas [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]; 4965 filas. Preprocessing congelado: {'numeric_median_fields': 81, 'missing_indicators': 81, 'numeric_standard_scaler': True, 'game_type_categories': ['CON', 'DIV', 'REG', 'SB', 'WC'], 'unknown_categories': 'ignore; frozen from refit'}; hash `858b6f058cfdcf8637ed9bcec7ecfca9`.

Baseline lambda=2.18187, media aritmética de temporadas [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024], fijada antes de apertura. Filas 2025 features-only: 570.

Sanity: finite_positive_means=True; finite_nonnegative_probabilities=True; mass_including_tail_one=True; deterministic=True; row_order_invariant=True; exact_82_features=True; no_2025_fitting=True; phase5_artifact_unchanged=True; no_calibration_fit=True; target_reads=1; target_used_only_for_evaluation=True

Política preregistrada: version=phase6-prereveal-v1; seed=42; bootstrap_resamples=1000; calibration_reasonable_ece_max=0.05; calibration_slight_ece_max=0.1; calibration_severe_fail_above=0.15; global_bias_pass_max=0.05; pass_requires_paired_delta_nll_rps_upper95_below_zero=True; signal_requires_nll_rps_improve_and_at_least_two_briers_improve=True; subgroup_min_n=50; subgroup_nll_warning_relative=0.2; year_degradation_warning_relative=0.1; top_feature_missing_shift_warning=0.1; ece_is_descriptive_not_significance_test=True

## Distribución del target y comparación histórica

| Población | n | Media | Varianza muestral | Var/media | Máximo | Histograma 0/1/2/3/4/5+ |
| --- | --- | --- | --- | --- | --- | --- |
| 2025 | 570 | 2.22456 | 2.06899 | 0.930067 | 7 | {'0': 60, '1': 136, '2': 152, '3': 109, '4': 75, '5+': 38} |
| train_2016_2023 | 4394 | 2.18207 | 2.10434 | 0.964377 | 10 | {'0': 522, '1': 1008, '2': 1184, '3': 905, '4': 494, '5+': 281} |
| validation_2024 | 571 | 2.18039 | 2.17968 | 0.999679 | 7 | {'0': 67, '1': 138, '2': 152, '3': 113, '4': 57, '5+': 44} |

## Métricas GLM vs baseline y 2024

Menor es mejor. Delta = GLM menos referencia; porcentaje = 100 × delta / referencia. Comparación anual descriptiva: 2024 fit hasta 2023; 2025 refit congelado hasta 2024.

| Métrica | GLM 2025 | Baseline 2025 | Delta baseline | % baseline | 2024 | Delta 2024 | % 2024 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nll | 1.71736 | 1.74596 | -0.0286022 | -1.6382 | 1.70684 | 0.0105222 | 0.616475 |
| rps | 0.77008 | 0.798856 | -0.0287762 | -3.60217 | 0.766108 | 0.00397219 | 0.51849 |
| brier_ge_2 | 0.218176 | 0.22585 | -0.00767352 | -3.39762 | 0.217911 | 0.000264801 | 0.121518 |
| brier_ge_3 | 0.228586 | 0.238075 | -0.00948918 | -3.9858 | 0.215753 | 0.0128324 | 5.94774 |
| brier_ge_4 | 0.15066 | 0.159392 | -0.00873208 | -5.47838 | 0.134145 | 0.0165142 | 12.3107 |
| mae | 1.12887 | 1.16301 | -0.0341407 | -2.93554 | 1.10996 | 0.0189071 | 1.7034 |
| rmse | 1.38962 | 1.43777 | -0.048149 | -3.34886 | 1.39562 | -0.00600016 | -0.429927 |
| poisson_deviance | 1.0233 | 1.0805 | -0.0572045 | -5.29424 | 1.04343 | -0.0201346 | -1.92965 |

## Bootstrap pareado

Método: paired IID row bootstrap, percentile; seed=42; resamples=1000; confianza=0.95. Los mismos índices de filas se usan para todas las métricas; deltas GLM menos baseline.

| Estimación | Punto | Inferior 95% | Superior 95% |
| --- | --- | --- | --- |
| nll | 1.71736 | 1.67276 | 1.76098 |
| rps | 0.77008 | 0.724492 | 0.811922 |
| brier_ge_2 | 0.218176 | 0.205358 | 0.229427 |
| brier_ge_3 | 0.228586 | 0.216499 | 0.241357 |
| brier_ge_4 | 0.15066 | 0.132508 | 0.171445 |
| delta_nll | -0.0286022 | -0.0496737 | -0.00716757 |
| delta_rps | -0.0287762 | -0.0480882 | -0.00843638 |

Shared games, teams and kickers imply dependence; row intervals may be optimistic. No model estimation uncertainty or bias correction.

## Calibración descriptiva

### ge_2

Predicho global=0.631194; observado global=0.65614; bias predicho−observado=-0.0249463; ECE=0.0253606; categoría=reasonably_calibrated.

| Bin | n | Predicho medio | Frecuencia observada | Wilson inferior 95% | Wilson superior 95% |
| --- | --- | --- | --- | --- | --- |
| [0.0, 0.1) | 0 | — | — | — | — |
| [0.1, 0.2) | 0 | — | — | — | — |
| [0.2, 0.3) | 0 | — | — | — | — |
| [0.3, 0.4) | 9 | 0.365995 | 0.555556 | 0.266651 | 0.811221 |
| [0.4, 0.5) | 53 | 0.463253 | 0.509434 | 0.378835 | 0.638758 |
| [0.5, 0.6) | 146 | 0.560732 | 0.582192 | 0.501088 | 0.659081 |
| [0.6, 0.7) | 215 | 0.648779 | 0.67907 | 0.613996 | 0.737857 |
| [0.7, 0.8) | 127 | 0.741087 | 0.740157 | 0.657633 | 0.80858 |
| [0.8, 0.9) | 20 | 0.823088 | 0.85 | 0.639581 | 0.947631 |
| [0.9, 1.0] | 0 | — | — | — | — |

### ge_3

Predicho global=0.371739; observado global=0.389474; bias predicho−observado=-0.0177345; ECE=0.0265366; categoría=reasonably_calibrated.

| Bin | n | Predicho medio | Frecuencia observada | Wilson inferior 95% | Wilson superior 95% |
| --- | --- | --- | --- | --- | --- |
| [0.0, 0.1) | 0 | — | — | — | — |
| [0.1, 0.2) | 27 | 0.169279 | 0.222222 | 0.106072 | 0.407569 |
| [0.2, 0.3) | 111 | 0.252723 | 0.297297 | 0.220208 | 0.387947 |
| [0.3, 0.4) | 221 | 0.350718 | 0.339367 | 0.28016 | 0.404062 |
| [0.4, 0.5) | 138 | 0.444634 | 0.456522 | 0.375718 | 0.53968 |
| [0.5, 0.6) | 60 | 0.537962 | 0.566667 | 0.441034 | 0.684276 |
| [0.6, 0.7) | 12 | 0.618354 | 0.833333 | 0.551969 | 0.953035 |
| [0.7, 0.8) | 1 | 0.702491 | 1 | 0.206549 | 1 |
| [0.8, 0.9) | 0 | — | — | — | — |
| [0.9, 1.0] | 0 | — | — | — | — |

### ge_4

Predicho global=0.183742; observado global=0.198246; bias predicho−observado=-0.0145034; ECE=0.0159767; categoría=reasonably_calibrated.

| Bin | n | Predicho medio | Frecuencia observada | Wilson inferior 95% | Wilson superior 95% |
| --- | --- | --- | --- | --- | --- |
| [0.0, 0.1) | 81 | 0.0755095 | 0.0987654 | 0.0509001 | 0.182965 |
| [0.1, 0.2) | 289 | 0.153702 | 0.152249 | 0.115411 | 0.19821 |
| [0.2, 0.3) | 148 | 0.244043 | 0.27027 | 0.205206 | 0.346958 |
| [0.3, 0.4) | 47 | 0.338767 | 0.361702 | 0.239662 | 0.504641 |
| [0.4, 0.5) | 5 | 0.43129 | 0.8 | 0.375535 | 0.963776 |
| [0.5, 0.6) | 0 | — | — | — | — |
| [0.6, 0.7) | 0 | — | — | — | — |
| [0.7, 0.8) | 0 | — | — | — | — |
| [0.8, 0.9) | 0 | — | — | — | — |
| [0.9, 1.0] | 0 | — | — | — | — |

ECE ≤0.05: razonablemente calibrado; (0.05,0.10]: desviación ligera; >0.10: desviación importante. Bandas operacionales, no pruebas de significancia; sin ajuste de calibración.

## Distribución completa predicha vs observada

Media predicha=2.18626; observada=2.22456; diferencia=-0.0383018.

| XPM | Probabilidad predicha | Frecuencia observada | Conteo observado | Conteo esperado |
| --- | --- | --- | --- | --- |
| 0 | 0.121816 | 0.105263 | 60 | 69.4353 |
| 1 | 0.24699 | 0.238596 | 136 | 140.784 |
| 2 | 0.259455 | 0.266667 | 152 | 147.889 |
| 3 | 0.187997 | 0.191228 | 109 | 107.158 |
| 4 | 0.105551 | 0.131579 | 75 | 60.1643 |
| 5+ | 0.0781908 | 0.0666667 | 38 | 44.5688 |

Ceros: predicho=0.121816; observado=0.105263; diferencia=0.0165531. Comparación aritmética descriptiva.

Cola alta exacta P(X≥5): predicho=0.0781908; observado=0.0666667; diferencia=0.0115241. Comparación aritmética descriptiva.

## Props fijos Over/Under

| Prop | Probabilidad media | Frecuencia observada | Brier | ECE | Bias | Categoría |
| --- | --- | --- | --- | --- | --- | --- |
| over_1.5 | 0.631194 | 0.65614 | 0.218176 | 0.0253606 | -0.0249463 | reasonably_calibrated |
| under_1.5 | 0.368806 | 0.34386 | 0.218176 | 0.0253606 | 0.0249463 | reasonably_calibrated |
| over_2.5 | 0.371739 | 0.389474 | 0.228586 | 0.0265366 | -0.0177345 | reasonably_calibrated |
| under_2.5 | 0.628261 | 0.610526 | 0.228586 | 0.0265366 | 0.0177345 | reasonably_calibrated |
| over_3.5 | 0.183742 | 0.198246 | 0.15066 | 0.0159767 | -0.0145034 | reasonably_calibrated |
| under_3.5 | 0.816258 | 0.801754 | 0.15066 | 0.0159767 | 0.0145034 | reasonably_calibrated |

## Subgrupos

Grupos con n<50: muestra pequeña, sin conclusión ni alerta. Grupos y comparaciones son descriptivos.

| Grupo | n | NLL GLM | NLL baseline | RPS GLM | RPS baseline | Advertencia |
| --- | --- | --- | --- | --- | --- | --- |
| home:home | 286 | 1.74335 | 1.77753 | 0.783452 | 0.822446 | ninguna |
| home:away | 284 | 1.69118 | 1.71416 | 0.756614 | 0.7751 | ninguna |
| week:early | 243 | 1.72064 | 1.75436 | 0.770577 | 0.805196 | ninguna |
| week:late | 327 | 1.71492 | 1.73972 | 0.76971 | 0.794145 | ninguna |
| history:limited | 205 | 1.72467 | 1.75293 | 0.774872 | 0.802914 | ninguna |
| history:established | 365 | 1.71325 | 1.74204 | 0.767389 | 0.796577 | ninguna |
| lambda:below2 | 180 | 1.63205 | 1.64957 | 0.707641 | 0.720103 | ninguna |
| lambda:2to3 | 371 | 1.75123 | 1.76573 | 0.79671 | 0.812546 | ninguna |
| lambda:3plus | 19 | 1.86412 | 2.27312 | 0.841627 | 1.27762 | n<50; sin conclusión |
| rest:short | 73 | 1.64974 | 1.62584 | 0.682689 | 0.669096 | ninguna |
| rest:long | 110 | 1.69144 | 1.73174 | 0.740167 | 0.779046 | ninguna |
| rest:normal | 355 | 1.75347 | 1.78943 | 0.810299 | 0.84526 | ninguna |
| rest:unknown | 32 | 1.5601 | 1.58668 | 0.626089 | 0.648176 | n<50; sin conclusión |
| offense:strong | 225 | 1.78165 | 1.8277 | 0.819752 | 0.872123 | ninguna |
| offense:weak | 184 | 1.62645 | 1.64023 | 0.698967 | 0.706098 | ninguna |
| offense:unknown | 161 | 1.7314 | 1.75256 | 0.781935 | 0.802474 | ninguna |
| defense:strong | 193 | 1.66562 | 1.67236 | 0.730715 | 0.735652 | ninguna |
| defense:permissive | 216 | 1.75472 | 1.80426 | 0.796097 | 0.848924 | ninguna |
| defense:unknown | 161 | 1.72926 | 1.75597 | 0.782365 | 0.807451 | ninguna |

## Drift

Drift calendario esperado 2025: True. game_type referencia=['CON', 'DIV', 'REG', 'SB', 'WC']; holdout=['CON', 'DIV', 'REG', 'SB', 'WC']; nuevas=[].

|SMD|>0.5 se marca; SMD usa std de referencia. Sin inferencia causal.

| Top feature | Población | Media | Mediana | Std | p05 | p25 | p75 | p95 | SMD | Flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| defense_points_allowed_per_game_last_5 | reference | 22.6306 | 22.4 | 4.89171 | 14.8 | 19.2 | 26 | 30.8 | 0.0756103 | False |
| defense_points_allowed_per_game_last_5 | holdout | 23.0005 | 22.8 | 5.0025 | 15.2 | 19.4 | 26.4 | 31.6 | 0.0756103 | False |
| defense_success_rate_allowed_last_3 | reference | 0.433335 | 0.4336 | 0.0466106 | 0.354466 | 0.402062 | 0.466284 | 0.507949 | 0.131944 | False |
| defense_success_rate_allowed_last_3 | holdout | 0.439485 | 0.44 | 0.0507272 | 0.352493 | 0.402985 | 0.475936 | 0.517488 | 0.131944 | False |
| offense_points_per_game_last_5 | reference | 23.0624 | 22.8 | 5.63542 | 14.39 | 19 | 27 | 32.6 | 0.0816789 | False |
| offense_points_per_game_last_5 | holdout | 23.5227 | 23.4 | 5.40243 | 14.6 | 19.6 | 27.2 | 32.72 | 0.0816789 | False |
| defense_td_allowed_per_drive_last_3 | reference | 0.218844 | 0.216216 | 0.0777206 | 0.0967742 | 0.162162 | 0.27027 | 0.352941 | 0.200668 | False |
| defense_td_allowed_per_drive_last_3 | holdout | 0.23444 | 0.228571 | 0.0833166 | 0.106391 | 0.178571 | 0.290323 | 0.387097 | 0.200668 | False |
| defense_td_allowed_per_drive_last_5 | reference | 0.218614 | 0.214286 | 0.0622614 | 0.118644 | 0.175439 | 0.259259 | 0.326923 | 0.247177 | False |
| defense_td_allowed_per_drive_last_5 | holdout | 0.234003 | 0.230769 | 0.0658577 | 0.126852 | 0.189655 | 0.277778 | 0.345204 | 0.247177 | False |
| defense_success_rate_allowed_last_5 | reference | 0.433335 | 0.434148 | 0.0381511 | 0.369338 | 0.407532 | 0.460067 | 0.493635 | 0.174801 | False |
| defense_success_rate_allowed_last_5 | holdout | 0.440004 | 0.440252 | 0.0427246 | 0.363509 | 0.414201 | 0.469841 | 0.510279 | 0.174801 | False |
| offense_success_rate_before | reference | 0.436851 | 0.438272 | 0.0428955 | 0.370198 | 0.408163 | 0.464567 | 0.504162 | 0.140321 | False |
| offense_success_rate_before | holdout | 0.44287 | 0.443101 | 0.0402328 | 0.369261 | 0.419507 | 0.468383 | 0.506928 | 0.140321 | False |
| kicker_xpm_per_game_before | reference | 2.20998 | 2.125 | 0.825273 | 1 | 1.66667 | 2.75 | 3.57738 | 0.0347883 | False |
| kicker_xpm_per_game_before | holdout | 2.23869 | 2.25 | 0.813311 | 1 | 1.66667 | 2.72078 | 3.5 | 0.0347883 | False |
| is_home | reference | 0.500101 | 1 | 0.5 | 0 | 0 | 1 | 1 | 0.00330736 | False |
| is_home | holdout | 0.501754 | 1 | 0.499997 | 0 | 0 | 1 | 1 | 0.00330736 | False |
| is_away | reference | 0.499899 | 0 | 0.5 | 0 | 0 | 1 | 1 | -0.00330736 | False |
| is_away | holdout | 0.498246 | 0 | 0.499997 | 0 | 0 | 1 | 1 | -0.00330736 | False |
| kicker_games_before | reference | 7.25579 | 7 | 4.97335 | 0 | 3 | 11 | 16 | 0.0162972 | False |
| kicker_games_before | holdout | 7.33684 | 7 | 5.07372 | 0 | 3 | 11.75 | 16 | 0.0162972 | False |
| kicker_xpm_before | reference | 16.3162 | 14 | 13.0086 | 0 | 6 | 24 | 41 | 0.0363807 | False |
| kicker_xpm_before | holdout | 16.7895 | 14 | 13.1868 | 0 | 6 | 25.75 | 41.55 | 0.0363807 | False |
| kicker_xpa_before | reference | 17.1511 | 15 | 13.6443 | 0 | 6 | 26 | 43 | 0.0181166 | False |
| kicker_xpa_before | holdout | 17.3982 | 15 | 13.5493 | 0 | 6 | 27 | 42 | 0.0181166 | False |
| team_two_point_attempt_rate_before | reference | 0.0979938 | 0.0769231 | 0.110706 | 0 | 0 | 0.136364 | 0.3 | 0.0150203 | False |
| team_two_point_attempt_rate_before | holdout | 0.0996567 | 0.0789474 | 0.106858 | 0 | 0.0241279 | 0.142857 | 0.27028 | 0.0150203 | False |
| team_days_rest | reference | 7.4992 | 6.99826 | 2.12701 | 4.30383 | 6.85731 | 7.18341 | 13.9857 | -0.00988963 | False |
| team_days_rest | holdout | 7.47817 | 6.9982 | 2.14699 | 4.30028 | 6.85667 | 7.30341 | 13.9921 | -0.00988963 | False |

Missingness revisado en 82 campos; rango en 82 campos. Cambios absolutos >10 puntos porcentuales se marcan.

| Campo | Missing ref | Missing 2025 | Delta | Flag >10pp | Top feature | Fuera de rango ref |
| --- | --- | --- | --- | --- | --- | --- |
| defense_epa_allowed_per_play_last_5 | 0.291037 | 0.282456 | -0.00858112 | False | False | 1 |
| season | 0 | 0 | 0 | False | False | 570 |

Campos sin excepción de missingness/rango: kicker_games_before, kicker_xpa_before, kicker_xpm_before, kicker_xp_conversion_rate_before, kicker_xpm_per_game_before, kicker_xpa_per_game_before, kicker_xpa_last_3, kicker_xpm_last_3, kicker_xp_conversion_last_3, kicker_xpm_per_game_last_3, kicker_xpa_last_5, kicker_xpm_last_5, kicker_xp_conversion_last_5, kicker_xpm_per_game_last_5, days_since_last_game, previous_game_xpa, previous_game_xpm, kicker_has_prior_game, kicker_has_3_prior_games, kicker_has_5_prior_games, kicker_low_sample_flag, offense_games_before, offense_points_per_game_before, offense_touchdowns_per_game_before, offense_drives_per_game_before, offense_td_per_drive_before, offense_red_zone_td_rate_before, offense_epa_per_play_before, offense_success_rate_before, offense_points_per_game_last_3, offense_touchdowns_per_game_last_3, offense_td_per_drive_last_3, offense_red_zone_td_rate_last_3, offense_epa_per_play_last_3, offense_success_rate_last_3, offense_points_per_game_last_5, offense_touchdowns_per_game_last_5, offense_td_per_drive_last_5, offense_red_zone_td_rate_last_5, offense_epa_per_play_last_5, offense_success_rate_last_5, defense_games_before, defense_points_allowed_per_game_before, defense_touchdowns_allowed_per_game_before, defense_drives_faced_per_game_before, defense_td_allowed_per_drive_before, defense_red_zone_td_rate_allowed_before, defense_epa_allowed_per_play_before, defense_success_rate_allowed_before, defense_points_allowed_per_game_last_3, defense_touchdowns_allowed_per_game_last_3, defense_td_allowed_per_drive_last_3, defense_red_zone_td_rate_allowed_last_3, defense_epa_allowed_per_play_last_3, defense_success_rate_allowed_last_3, defense_points_allowed_per_game_last_5, defense_touchdowns_allowed_per_game_last_5, defense_td_allowed_per_drive_last_5, defense_red_zone_td_rate_allowed_last_5, defense_success_rate_allowed_last_5, is_home, is_away, week, team_days_rest, opponent_days_rest, team_short_week_flag, opponent_short_week_flag, team_long_rest_flag, opponent_long_rest_flag, team_two_point_attempt_rate_before, team_two_point_attempts_before, team_two_point_attempt_rate_last_3, team_two_point_attempts_last_3, team_two_point_attempt_rate_last_5, team_two_point_attempts_last_5, team_has_3_prior_games, team_has_5_prior_games, opponent_has_3_prior_games, opponent_has_5_prior_games

Campos sin rango de referencia disponible: game_type

## Casos extremos (diagnóstico, sin tuning)

- game_id=2025_18_SEA_SF; team=SF; opponent=SEA; kicker_id=00-0034173; kicker_name=Eddy Pineiro; lambda=2.99928; real=0; PMF(real)=0.049823; P(X≥3)=0.576648; NLL=2.99928; motivos=['largest_overprediction']. Contexto: week=18; is_home=1; kicker_games_before=13; offense_points_per_game_last_5=34.6; defense_points_allowed_per_game_last_5=14.4; team_short_week_flag=1; team_long_rest_flag=0; team_days_rest=5.98373.

- game_id=2025_15_IND_SEA; team=SEA; opponent=IND; kicker_id=00-0031492; kicker_name=Jason Myers; lambda=2.85016; real=0; PMF(real)=0.0578353; P(X≥3)=0.542416; NLL=2.85016; motivos=['largest_overprediction']. Contexto: week=15; is_home=1; kicker_games_before=13; offense_points_per_game_last_5=31.2; defense_points_allowed_per_game_last_5=26.2; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=7.1408.

- game_id=2025_17_PHI_BUF; team=BUF; opponent=PHI; kicker_id=00-0034084; kicker_name=Mike Badgley; lambda=2.84183; real=0; PMF(real)=0.058319; P(X≥3)=0.540457; NLL=2.84183; motivos=['largest_overprediction']. Contexto: week=17; is_home=1; kicker_games_before=8; offense_points_per_game_last_5=28.4; defense_points_allowed_per_game_last_5=17.6; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=7.14073.

- game_id=2025_02_CHI_DET; team=DET; opponent=CHI; kicker_id=00-0039172; kicker_name=Jake Bates; lambda=2.28652; real=7; PMF(real)=0.00658832; P(X≥3)=0.400384; NLL=5.02246; motivos=['largest_underprediction']. Contexto: week=2; is_home=1; kicker_games_before=1; offense_points_per_game_last_5=—; defense_points_allowed_per_game_last_5=—; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.8572.

- game_id=2025_16_CIN_MIA; team=CIN; opponent=MIA; kicker_id=00-0036854; kicker_name=Evan McPherson; lambda=1.69747; real=6; PMF(real)=0.00608527; P(X≥3)=0.242109; NLL=5.10188; motivos=['largest_underprediction']. Contexto: week=16; is_home=0; kicker_games_before=14; offense_points_per_game_last_5=19.6; defense_points_allowed_per_game_last_5=16.2; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.99807.

- game_id=2025_03_CIN_MIN; team=MIN; opponent=CIN; kicker_id=00-0039404; kicker_name=Will Reichard; lambda=1.74704; real=6; PMF(real)=0.00688261; P(X≥3)=0.255242; NLL=4.97876; motivos=['largest_underprediction']. Contexto: week=3; is_home=1; kicker_games_before=2; offense_points_per_game_last_5=—; defense_points_allowed_per_game_last_5=—; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.69215.

- game_id=2025_13_MIN_SEA; team=SEA; opponent=MIN; kicker_id=00-0031492; kicker_name=Jason Myers; lambda=3.14183; real=2; PMF(real)=0.213234; P(X≥3)=0.607823; NLL=1.54536; motivos=['highest_failed_ge3']. Contexto: week=13; is_home=1; kicker_games_before=11; offense_points_per_game_last_5=31.6; defense_points_allowed_per_game_last_5=26; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=7.12635.

- game_id=2025_09_CAR_GB; team=GB; opponent=CAR; kicker_id=00-0029822; kicker_name=Brandon McManus; lambda=3.12782; real=1; PMF(real)=0.13704; P(X≥3)=0.604828; NLL=1.98748; motivos=['highest_failed_ge3']. Contexto: week=9; is_home=1; kicker_games_before=5; offense_points_per_game_last_5=27.8; defense_points_allowed_per_game_last_5=27.8; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.73432.

- game_id=2025_10_ATL_IND; team=IND; opponent=ATL; kicker_id=00-0034084; kicker_name=Mike Badgley; lambda=3.00831; real=1; PMF(real)=0.148536; P(X≥3)=0.578669; NLL=1.90693; motivos=['highest_failed_ge3']. Contexto: week=10; is_home=1; kicker_games_before=4; offense_points_per_game_last_5=33.4; defense_points_allowed_per_game_last_5=23.8; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.85244.

- game_id=2025_16_LV_HOU; team=LV; opponent=HOU; kicker_id=00-0034161; kicker_name=Daniel Carlson; lambda=1.19211; real=3; PMF(real)=0.0857176; P(X≥3)=0.118806; NLL=2.4567; motivos=['lowest_successful_ge3']. Contexto: week=16; is_home=0; kicker_games_before=14; offense_points_per_game_last_5=11.4; defense_points_allowed_per_game_last_5=15.6; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=7.14016.

- game_id=2025_15_TEN_SF; team=TEN; opponent=SF; kicker_id=00-0035192; kicker_name=Joey Slye; lambda=1.24739; real=3; PMF(real)=0.0929226; P(X≥3)=0.130949; NLL=2.37599; motivos=['lowest_successful_ge3']. Contexto: week=15; is_home=0; kicker_games_before=12; offense_points_per_game_last_5=18.2; defense_points_allowed_per_game_last_5=21; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=7.14045.

- game_id=2025_12_CLE_LV; team=CLE; opponent=LV; kicker_id=00-0038428; kicker_name=Andre Szmyt; lambda=1.41496; real=3; PMF(real)=0.114702; P(X≥3)=0.170129; NLL=2.16541; motivos=['lowest_successful_ge3']. Contexto: week=12; is_home=0; kicker_games_before=10; offense_points_per_game_last_5=17.8; defense_points_allowed_per_game_last_5=22.8; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.98589.

- game_id=2025_10_LA_SF; team=LA; opponent=SF; kicker_id=00-0039498; kicker_name=Harrison Mevis; lambda=1.88942; real=6; PMF(real)=0.00955145; P(X≥3)=0.293423; NLL=4.65106; motivos=['highest_nll_fill']. Contexto: week=10; is_home=0; kicker_games_before=0; offense_points_per_game_last_5=27.2; defense_points_allowed_per_game_last_5=22.6; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=7.01369.

- game_id=2025_16_SF_IND; team=SF; opponent=IND; kicker_id=00-0034173; kicker_name=Eddy Pineiro; lambda=2.35591; real=6; PMF(real)=0.0225144; P(X≥3)=0.41873; NLL=3.7936; motivos=['highest_nll_fill']. Contexto: week=16; is_home=0; kicker_games_before=11; offense_points_per_game_last_5=30; defense_points_allowed_per_game_last_5=24.4; team_short_week_flag=0; team_long_rest_flag=1; team_days_rest=8.15919.

- game_id=2025_04_CAR_NE; team=NE; opponent=CAR; kicker_id=00-0040200; kicker_name=Andy Borregales; lambda=2.49797; real=6; PMF(real)=0.0277546; P(X≥3)=0.455665; NLL=3.58435; motivos=['highest_nll_fill']. Contexto: week=4; is_home=1; kicker_games_before=3; offense_points_per_game_last_5=—; defense_points_allowed_per_game_last_5=—; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.99831.

- game_id=2025_17_CHI_SF; team=SF; opponent=CHI; kicker_id=00-0034173; kicker_name=Eddy Pineiro; lambda=2.5975; real=6; PMF(real)=0.0317629; P(X≥3)=0.480943; NLL=3.44946; motivos=['highest_nll_fill']. Contexto: week=17; is_home=1; kicker_games_before=12; offense_points_per_game_last_5=34.4; defense_points_allowed_per_game_last_5=18; team_short_week_flag=0; team_long_rest_flag=0; team_days_rest=6.00201.

## Gate preregistrado

**PASS**; señal puntual=True; mejora pareada robusta NLL/RPS=True.

FAIL: fallo de integridad/leakage/probabilidades, cualquier ECE>0.15, o falta de mejora puntual conjunta NLL/RPS y al menos dos Brier. PASS: señal puntual; superior95 de ambos deltas NLL/RPS<0; ningún Brier peor; todos ECE≤0.05; |bias global|≤0.05; sin advertencias. En otro caso con señal y sin FAIL: PASS WITH CAUTION.

Advertencias congeladas: >10% deterioro NLL/RPS vs 2024; subgrupo n≥50 con NLL >baseline por >20%; missingness top15 cambia >10pp; game_type nuevo. Las demás condiciones de PASS incumplidas se informan como cautelas.

Fallos: ninguno

Advertencias: ninguna

## Limitaciones

- IID row bootstrap may underestimate uncertainty from shared games/teams/kickers.

- 2024 uses model fit through 2023; 2025 uses the frozen refit through 2024; year comparison is descriptive.

- No calibration intercept/slope fitted; reliability, Wilson intervals, ECE and Brier only.

- Subgroups and extreme errors are descriptive, not tuning or causal inference.

- No financial evaluation and no Phase 7.
