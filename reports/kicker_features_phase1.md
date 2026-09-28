# Fase 1 — features del kicker

Build `834c779fa5a01a6c8372`. Filas: **6083**.

Política temporal: `event-context-v1`. Eventos terminados antes del cutoff no requieren fecha de publicación del archivo retrospectivo; el contexto point-in-time conserva ese requisito. Filas conformes temporalmente: 6083; elegibles para entrenamiento histórico de Fase 1: 5535.
Se mantiene el margen conservador +24 h para incorporar eventos. No representa una fecha de publicación. 2015 permanece como reserva histórica; las temporadas objetivo son 2016–2025. Los snapshots experimentales anteriores permanecen sin modificar.

| Feature | No NULL | NULL | Cobertura |
|---|---:|---:|---:|
| kicker_games_before | 6083 | 0 | 100.00% |
| kicker_xpa_before | 6083 | 0 | 100.00% |
| kicker_xpm_before | 6083 | 0 | 100.00% |
| kicker_xp_conversion_rate_before | 5536 | 547 | 91.01% |
| kicker_xpm_per_game_before | 5605 | 478 | 92.14% |
| kicker_xpa_per_game_before | 5605 | 478 | 92.14% |
| kicker_xpa_last_3 | 4729 | 1354 | 77.74% |
| kicker_xpm_last_3 | 4729 | 1354 | 77.74% |
| kicker_xp_conversion_last_3 | 4711 | 1372 | 77.45% |
| kicker_xpm_per_game_last_3 | 4729 | 1354 | 77.74% |
| kicker_xpa_last_5 | 3912 | 2171 | 64.31% |
| kicker_xpm_last_5 | 3912 | 2171 | 64.31% |
| kicker_xp_conversion_last_5 | 3903 | 2180 | 64.16% |
| kicker_xpm_per_game_last_5 | 3912 | 2171 | 64.31% |
| days_since_last_game | 5605 | 478 | 92.14% |
| previous_game_xpa | 5605 | 478 | 92.14% |
| previous_game_xpm | 5605 | 478 | 92.14% |
| kicker_has_prior_game | 6083 | 0 | 100.00% |
| kicker_has_3_prior_games | 6083 | 0 | 100.00% |
| kicker_has_5_prior_games | 6083 | 0 | 100.00% |
| kicker_low_sample_flag | 6083 | 0 | 100.00% |

Distribución de partidos previos: 0: 478, 1-2: 876, 3-4: 817, 5+: 3912.
Histograma completo: `kicker_features_phase1.json`.

## Ejemplos para auditoría

| Caso | Game / team / kicker | Previos | XPA/XPM previos | Últimos 3 XPA/XPM | XPM target |
|---|---|---:|---|---|---:|
| first_observed_game_not_necessarily_rookie | 2015_01_PIT_NE / NE / Stephen Gostkowski | 0 | 0/0 | None/None | 4 |
| long_history | 2021_22_LA_CIN / LA / Matt Gay | 20 | 58/57 | 9/9 | 2 |
| team_change | 2015_07_NO_IND / NO / Kai Forbath | 1 | 1/1 | None/None | 3 |
| zero_xpm | 2015_04_NYG_BUF / BUF / Jordan Gay | 3 | 0/0 | 0/0 | 0 |
| multiple_or_unusual | 2017_07_DAL_SF / DAL / Dan Bailey | 5 | 14/14 | 11/11 | 2 |

El JSON adjunto conserva partidos, valores y hashes que contribuyen a cada ejemplo. Primer partido significa primera observación de esa temporada, no prueba de rookie. Los flags originales y el target se adjuntan después de congelar todas las features, bajo `source_label`. La matriz predictiva usa exclusivamente las 21 columnas declaradas en el contrato.

Historia global del kicker: cambiar de equipo no reinicia sus métricas personales. Una historia kicker+team descartaría evidencia reciente del mismo ejecutor; puede ser útil para contexto del equipo en otra fase. Esta fase usa `(season, kicker_id)` y no mezcla temporadas.

Reproducción: `python -m kickedge.features prepare`, luego `python -m kickedge.features build`. El comando prepare consume únicamente el build histórico y el PBP ya cacheado; el builder solo recibe identidades y resultados revelados de partidos anteriores. No se modifica el pipeline ni el snapshot histórico original.
