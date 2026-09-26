# Reconstrucción prepartido T−60

Build: `3ed70bf1799e0a1de5c3`. Pipeline local; no entrenamiento.

| Temporada | Team-games | ID | Cobertura | VERIFIED | STRONG | INFERRED | AMBIGUOUS | UNKNOWN | Elegibles | Coincidencias/evaluables | Coincidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015 | 534 | 0 | 0.00% | 0 | 0 | 0 | 0 | 534 | 0 | 0/0 | N/A |
| 2016 | 534 | 0 | 0.00% | 0 | 0 | 0 | 0 | 534 | 0 | 0/0 | N/A |
| 2017 | 534 | 0 | 0.00% | 0 | 0 | 0 | 0 | 534 | 0 | 0/0 | N/A |
| 2018 | 534 | 0 | 0.00% | 0 | 0 | 0 | 0 | 534 | 0 | 0/0 | N/A |
| 2019 | 534 | 0 | 0.00% | 0 | 0 | 0 | 0 | 534 | 0 | 0/0 | N/A |
| 2020 | 538 | 0 | 0.00% | 0 | 0 | 0 | 0 | 538 | 0 | 0/0 | N/A |
| 2021 | 570 | 0 | 0.00% | 0 | 0 | 0 | 0 | 570 | 0 | 0/0 | N/A |
| 2022 | 568 | 0 | 0.00% | 0 | 0 | 0 | 0 | 568 | 0 | 0/0 | N/A |
| 2023 | 570 | 0 | 0.00% | 0 | 0 | 0 | 0 | 570 | 0 | 0/0 | N/A |
| 2024 | 570 | 2 | 0.35% | 1 | 1 | 0 | 0 | 568 | 1 | 2/2 | 100.00% |
| 2025 | 570 | 569 | 99.82% | 0 | 0 | 569 | 0 | 1 | 0 | 544/560 | 97.14% |

Total: 571/6056 identidades (9.43%). Solo 2 tienen evidencia VERIFIED/STRONG; 1 cumplen la política conservadora VERIFIED y label válido.

Las categorías son niveles de evidencia, no probabilidades. La cobertura mide lo reconstruido con las fuentes integradas; no es un límite superior de lo históricamente recuperable. Los casos oficiales son una muestra dirigida.

| Categoría | N | % de todos los team-games |
| --- | --- | --- |
| VERIFIED | 1 | 0.0165% |
| STRONG | 1 | 0.0165% |
| INFERRED | 569 | 9.3956% |
| AMBIGUOUS | 0 | 0.0000% |
| UNKNOWN | 5485 | 90.5713% |

| Comparación | N |
| --- | --- |
| expected_unknown | 5485 |
| exclusive_match | 545 |
| no_actual_placekick | 9 |
| expected_among_multiple | 1 |
| mismatch | 16 |

Coincidencia de pertenencia: 546/562 = 97.1530%. Coincidencia de conjunto exacto: 96.9751%. El denominador exige ID esperado y algún PAT/FG real. No cuenta UNKNOWN ni equipos sin PAT/FG. No es precisión predictiva fuera de muestra.

10 team-games tienen varios ejecutores reales de PAT/FG; 17 IDs esperados no tienen evidencia de ninguna patada (incluye kickoff). No observar patadas no demuestra DNP; la participación total no puede determinarse con estas tablas.

59 resultados esperados conservan XPM=0; 17 IDs esperados no tienen label individual validado y conservan NULL.

| Control | Resultado |
| --- | --- |
| one_row_per_team_game | PASS |
| two_teams_per_game | PASS |
| exact_T_minus_60 | PASS |
| unknown_and_ambiguous_have_no_identity | PASS |
| known_id_has_provenance | PASS |
| all_accepted_timestamps_before_cutoff | PASS |
| evaluation_did_not_mutate_identity | PASS |
| missing_labels_stay_null | PASS |
| training_policy_enforced | PASS |
| evaluation_preserves_population | PASS |

La metodología, límites temporales y política de elegibilidad están en `docs/pregame_methodology.md`; evidencia fila por fila en el directorio del build.
