# Fase 3: contexto del partido

Se incorporan 21 predictores: 18 columnas nuevas y la habilitación de `season`,
`week` y `game_type`, cuyos valores ya existían. La matriz conjunta tiene 82
predictores; las 61 features anteriores y sus snapshots no cambian.

## Calendario y descanso

El usuario autorizó **phase3-calendar-v1**, una aproximación histórica limitada
a matchup, local/visitante, temporada, semana, tipo de partido y descanso. La
clase `historical_schedule_context` no afirma evidencia point-in-time:
`calendar_historical_approximation=true`, `calendar_point_in_time_verified=false`.
El contrato y la validación usan una lista cerrada de campos autorizados.

No se extiende a mercado/odds, clima, lesiones, inactivos, roster, noticias ni QB.
Esos grupos mantienen la política `point_in_time_context_data` y exigen evidencia
de disponibilidad de la versión anterior al cutoff. Los eventos anteriores
mantienen `event-context-v1` sin modificación.

`is_home` / `is_away` identifican al equipo designado en schedules, incluso en
sede neutral; no son una afirmación de ventaja de local. `game_type` usa
REG/WC/DIV/CON/SB y la temporada NFL, no el año calendario de los playoffs.

Para cada lado:

`days_rest = (kickoff programado de G - kickoff real del último juego previo) / 86400`

Si no existe kickoff programado, se permite el kickoff histórico de G como
fallback explícitamente marcado en provenance. Se preserva el cutoff de Fases
1/2; el partido previo debe haber concluido antes y superado el margen conservador
de incorporación +24 h. Se ordenan juegos reales, no números de semana.

Los días son fraccionarios UTC: short week `<6`, long rest `>8`, sin redondear
antes de evaluar flags. Bye se refleja naturalmente; playoffs continúan la misma
temporada. Sin partido previo de esa temporada, rest y sus flags son NULL. No se
usa la temporada anterior. Los flags de muestra indican al menos 3/5 partidos
previos del equipo y rival, coherentes con los conteos de Fase 2.

## Tendencia 2PT

Se reutiliza `team_games.parquet` del snapshot histórico auditado. Numerador:
intentos PBP no eliminados con `two_point_attempt=1`; denominador:
`two_pt_attempts + team_xpa` (PAT intentados, incluidos fallados/bloqueados).
No se cuentan conversiones anuladas ni retornos defensivos como nuevas elecciones.
Se incluyen decisiones tras TD de cualquier fase; TD sin intento registrado no
entra al denominador. Es frecuencia de elección **entre intentos registrados**,
no probabilidad situacional exacta ni tasa de éxito de la conversión.

Season-to-date y rolling 3/5 suman numeradores y denominadores; no promedian tasas.
Las ventanas incluyen exactamente 3/5 juegos previos, aunque alguno tenga cero
conversiones. Sin ventana completa: NULL. Con denominador cero: tasa NULL.
Sin historial: conteo acumulado cero, tasa NULL. Reinicio por temporada.

## Ejecución y controles

```powershell
.\.venv\Scripts\python.exe -m kickedge.features prepare-context
.\.venv\Scripts\python.exe -m kickedge.features build-context
.\.venv\Scripts\python.exe -m pytest -q
```

`prepare-context --phase2 RUTA` fija Fase 2 y `build-context --inputs RUTA` fija
los inputs. No hay red ni descargas. Se preparan calendario sin resultados y
archivos de conversiones separados por partido. La simulación congela G antes
de revelar sus resultados a observaciones posteriores. El join de targets y
las 61 features previas ocurre después de congelar todo el contexto.

La salida vive en `data/features/context/`, ignorada por Git. Incluye JSON/Parquet,
contrato, cadena freeze/reveal y hashes. `calendar_provenance` registra reloj
programado/fallback, último juego de cada lado, política y hashes; el historial
registra intentos, PAT, ventanas, tiempos y hashes por partido fuente.

Para entrenamiento conjunto usar `eligible_for_phase_3_training` y exclusivamente
`predictor_columns_through_phase_3`. Se exige elegibilidad de Fase 2 y no tener
historial pendiente. Se admiten los NULL semánticos descritos. Los campos de
elegibilidad anteriores permanecen intactos y no certifican por sí solos Fase 3.

El schedule local incluye IDs/nombres de QB, pero son registros retrospectivos
sin evidencia pregame: no se implementaron `starting_qb_known` ni cambios de QB.
Injuries/roster continúan pendientes; no se investigaron fuentes adicionales.
