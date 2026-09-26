# Campos y artefactos pregame

Los Parquet son exportaciones; los JSON congelados conservan exactamente IDs, arrays y fechas UTC ISO8601. No deducir disponibilidad a partir de timestamps de descarga.

| Campo | Significado |
| --- | --- |
| game_id, team, prediction_cutoff | Clave de cada observación en una política |
| kickoff_utc, cutoff_basis | Inicio programado de schedules convertido desde Eastern; no snapshot archivado del calendario |
| expected_kicker_id, expected_kicker_name | ID esperado; NULL para UNKNOWN/AMBIGUOUS; nombre solo descriptivo |
| expected_kicker_confidence | Categoría de evidencia, no probabilidad |
| expected_kicker_source | URLs de soporte de identidad |
| expected_kicker_evidence_type | Tipos de evidencia que sustentan el ID |
| expected_kicker_evidence_timestamp | Último instante admisible usado; puede ser revelación histórica asumida y no publicación; consultar temporal_basis |
| expected_kicker_evidence_ids | Referencias al ledger oficial/depth o hechos históricos revelados |
| expected_kicker_candidates | Candidatos conocidos antes del cutoff, rango, fuentes y veto; no contiene candidatos extraídos de versiones futuras rechazadas |
| expected_kicker_ambiguous | Conflicto explícito; no equivale simplemente a tener un backup |
| policy | A, B o C; mismo universo completo para comparar |
| inference_subtype | official_confirmation, continuity_with_current_role, experimental_continuity_only o NULL |
| prior_game_id, previous_placekicker_ids | Último juego del equipo revelado; su información ya era historia al decidir |
| prior_consecutive_games | Racha del candidato de continuidad, no necesariamente del seleccionado por una confirmación oficial que lo reemplaza |
| history_evidence | Game, equipo, IDs, kickoff, reveal_at, hash y locator de cada hecho previo empleado |
| history_availability_basis | Señala explícitamente game_event_plus_24h_assumption_not_publication_timestamp |
| current_availability_verified, current_roster_verified | False para todas las inferencias B/C; True bajo la evidencia oficial y sus límites |
| transaction_feed_complete, injury_feed_complete | False; no hay feed exhaustivo integrado. No interpretar falta de reportes como jugador sano/activo |
| historical_evaluation_split | Período de desarrollo, evaluación temporal con solapamiento conocido o 2025 ya inspeccionado |
| actual_placekicker_ids/names | Solo evaluación posterior: conjunto de ejecutores PAT/FG |
| comparison | exclusive_match, expected_among_multiple, mismatch, no_actual_placekick, expected_unknown |
| expected_kicking_participation | observed_kicking, no_kicking_evidence o unknown_identity; no es un registro completo de snaps/DNP |
| expected_observed_fga/kickoffs | Conteos del ID esperado solo si tiene evidencia PBP; ausencia permanece NULL |
| xpa, xpm | Resultado del label reconciliado del ID esperado, nunca del sustituto; NULL cuando falta label válido |
| outcome_source, outcome_*_sha256 | Procedencia de la etiqueta, independiente de la evidencia usada para seleccionar |
| actual_kicker_changed_since_prior_game | Diagnóstico postgame: conjuntos previo/actual no vacíos y diferentes. Nunca entra al selector |
| pregame_identity_eligible | False en A/B/C hasta revisión; el experimento inicial conserva su política anterior independiente |
| eligible_for_pregame_training | False en todos los datasets secuenciales; no filtrar por match para obtener una población artificialmente limpia |
| pregame_exclusion_reason | Razón de abstención o revisión pendiente |

En `evidence.json`, `published_at`, `modified_at`, `available_at`, `downloaded_at`, `temporal_basis`, `source_sha256`, `source_path`, `locator`, `admissible` y `rejection_reason` permiten reconstruir cada aceptación/rechazo. Para artículos se usa el máximo entre publicación y modificación de la versión actual; se ignoran fechas de galerías.

En `events.jsonl`, cada `freeze` persiste decisiones antes de permitir el `reveal` del mismo partido. La cadena SHA-256 detecta modificaciones; el oracle guarda un archivo separado por juego. `freeze.json` fija hashes de identidades y cadena. `build.json` fija inputs y artefactos. El build base guarda código y el lock de fuentes para reejecutar offline.
