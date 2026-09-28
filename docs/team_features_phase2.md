# Fase 2: ofensiva y defensa rival

Se añaden 40 predictores al kicker-game: 20 de ofensiva del equipo del kicker y
20 de producción permitida por **su rival**. Cada grupo tiene 8 season-to-date,
6 rolling 3 y 6 rolling 5. Las 21 columnas de Fase 1 se conservan sin cambios.
Nombres, fórmulas, fuentes y requisitos están en `kickedge/features/contract.json`.

## Definiciones

- **Puntos:** marcador final del equipo, incluidas todas las fases del juego.
  Points allowed es el marcador del contrario, no una atribución exclusivamente
  a las jugadas de la defensa. TD y EPA sí describen producción ofensiva.
- **TD:** touchdown no eliminado, `td_team=posteam`, sin return TD, special teams,
  patadas ni conversiones de dos puntos. Son anotaciones ofensivas potencialmente
  generadoras de PAT; no se exige que finalmente se intente el PAT.
- **Drives:** `fixed_drive` distintos por partido/equipo con al menos una jugada
  run, pass, punt, field_goal, qb_kneel o qb_spike válida. Incluye posesiones solo
  de kneel; no cuenta kickoffs, PAT, 2PT ni secuencias solo administrativas/no-play.
- **Red zone:** denominador = drives anteriores con una jugada válida iniciada
  en down 1–4 y `yardline_100` entre 0 y 20. Numerador = esos drives que terminan
  anotando un TD ofensivo. Un TD largo sin snap en red zone no entra al denominador.
- **EPA/play:** suma del `epa` nflverse/nflfastR cacheado / jugadas run/pass con EPA
  finito, incluidos sacks. Excluye plays eliminados, no-play, kneels, spikes y 2PT.
- **Success rate:** fracción de esas mismas jugadas con `epa > 0`.

Las tasas agrupan numeradores y denominadores; no promedian tasas por partido.
Promedios dividen por partidos anteriores. Reset por temporada para todo el
historial. Rolling requiere exactamente 3/5 juegos previos; bye weeks no cambian
las ventanas. Sin historia, muestra insuficiente o denominador cero: NULL.
Los conteos de partidos son cero al inicio. No se imputa ni se omite un partido
para completar artificialmente una ventana. Se conservan razones de NULL.

## Temporalidad e integración

Se aplica `event-context-v1`: evento concluido antes del cutoff, END GAME y hashes
del snapshot de Fase 1, sin timestamp de publicación del archivo retrospectivo.
Se conserva el margen `max(kickoff+24h, last_event)` y cutoff de Fase 1.
Cada partido congela todas sus filas antes de revelar su archivo de estadísticas
para partidos posteriores. El dataset de Fase 1, que contiene targets, se lee
para el join **después** de congelar todas las nuevas features.

`team_feature_provenance` conserva partidos, equipos, conteos, numeradores,
denominadores, relojes, hashes y ventanas de cada lado. La defensa se actualiza
con la producción del contrario y se consulta por `opponent` del partido objetivo.

Para entrenamiento conjunto usar `eligible_for_phase_2_training` y únicamente
`predictor_columns_through_phase_2` (61 columnas). La elegibilidad requiere la de
Fase 1 y ninguna historia pendiente ni métrica fuente faltante. Los NULL semánticos
están permitidos. La elegibilidad original de Fase 1 no se sobrescribe.
Identidad, participación, target y flags de auditoría nunca son predictores.

## Reproducción local

```powershell
.\.venv\Scripts\python.exe -m kickedge.features prepare-teams
.\.venv\Scripts\python.exe -m kickedge.features build-teams
.\.venv\Scripts\python.exe -m pytest -q
```

`prepare-teams --phase1 RUTA` fija el snapshot de Fase 1;
`build-teams --inputs RUTA` fija los inputs preparados. No hay descargas.
Los nuevos artefactos en `data/features/team_inputs/` y `data/features/teams/`
están ignorados por Git; los punteros y datasets de Fase 1 permanecen intactos.
El build incluye datos, contrato, features congeladas, cadena freeze/reveal y hashes.

Limitaciones: población condicionada a participación observada; historia reiniciada
por temporada; puntos incluyen defensa/special teams; EPA es el valor histórico
del proveedor con su versión congelada por hash, sin reentrenamiento ni afirmación
de reproducir su modelo de EP en cada fecha. No se desarrollan otras fases.
