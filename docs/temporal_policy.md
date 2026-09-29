# Política temporal final — event-context-v1

Decisión adoptada el 2026-09-28. Sustituye el bloqueo general por ausencia de
timestamps históricos de publicación; no elimina ningún control de leakage.

## Historical event data

Resultados de partidos concluidos: XPM, XPA, touchdowns, puntos, drives, EPA,
success rate, resultados de red zone y estadísticas boxscore/PBP. Pueden
reconstruirse retrospectivamente para predecir partidos posteriores si:

- el partido fuente ya terminó antes del cutoff del objetivo;
- se excluyen el partido objetivo, los futuros y los aún en curso;
- el orden cronológico y las ventanas están preservados;
- existe trazabilidad hacia partido, valores utilizados y fuente/hash.

No se exige demostrar cuándo se publicó el archivo descargado retrospectivamente.
Una corrección estadística del mismo evento concluido no convierte ese evento en
futuro. Esto no autoriza introducir información de partidos futuros en agregados
o transformaciones. La regla tampoco aprueba todavía implementaciones futuras
de ofensiva/defensa ni transformaciones/modelos auxiliares: deberán respetarla.

Ejemplo: A termina con 3/3 XPM; ese 3/3 puede contribuir a B una semana después,
aunque el archivo histórico se haya descargado hoy.

## Point-in-time context data

Odds, spreads/totals, props, lesiones, inactivos, depth charts, roster/noticias,
pronósticos meteorológicos y todo dato cuyo valor/versión conocida importe.
Requieren evidencia de disponibilidad de la **versión utilizada** antes/al cutoff.
Publicaciones o modificaciones posteriores no sirven; clima realizado no sustituye
un pronóstico previo. La clasificación como evento no puede usarse para eximir
estas fuentes. Los builders correspondientes permanecen fuera de esta tarea.

## Aplicación a Fase 1

Las **21 features del kicker** son historical event data y quedan aprobadas para
entrenamiento histórico. Recencia se mide al cutoff desde el inicio del último
partido previo; no utiliza el kickoff futuro del objetivo como predictor.
Identidad y participación observada solo definen la fila; XPM objetivo es target.

Se conserva `available_at=max(inicio real +24h, último evento registrado)` como
**margen conservador de incorporación**, no como publicación supuesta. Se exige
además un marcador PBP END GAME no eliminado como evidencia de partido concluido
y último evento estrictamente anterior al cutoff. El
nombre available_at se mantiene por compatibilidad con el oracle existente.
Así no cambian los valores numéricos ni las ventanas del snapshot anterior.

- `features_temporally_verified`: conformidad con esta política de eventos;
  no afirma que se verificó la fecha de publicación del archivo.
- `feature_sources_verified`: evidencia de publicación, conservada separadamente;
  false no bloquea historical event data.
- `features_technically_reconstructible`: historia técnicamente completa/utilizable;
  se permiten los NULL semánticos de primer partido, muestra o denominador cero.
- `eligible_for_final_training`: elegibilidad **de Fase 1** en 2016–2025, con
  temporalidad aprobada, historial técnicamente válido, target utilizable e
  identidad resuelta. 2015 continúa como reserva histórica.
- `training_exclusion_reasons`: motivos de exclusión explícitos. No se agrega
  una exclusión automática de múltiples kickers; sus flags permanecen disponibles.

La población sigue siendo condicional a participación observada. Esta decisión no
entrena un modelo, no valida un split de evaluación ni resuelve no participación.
Se aprueba el uso de las features y filas que cumplen los criterios declarados.

## Compatibilidad y validación

Los snapshots originales, el pregame/change detector y sus informes se conservan.
Los inputs de replay antiguo sin esta política explícita siguen experimentales:
no se aprueban por ejecutar código nuevo. Los nuevos inputs llevan clasificación,
estado del evento y relojes, y producen un nuevo artifact con hashes.

Se mantienen los tests de target/future leakage, eliminación física del resultado,
rolling, season-to-date, cronología, freeze/reveal y comparación SQL independiente.
Se añaden pruebas que aceptan un evento previo descargado después y rechazan
contexto sin versión demostrada, eventos incompletos/futuros y clases desconocidas.

## Excepción de calendario autorizada para Fase 3

`phase3-calendar-v1` permite usar el schedule histórico exclusivamente para
matchup, home/away, temporada, semana, game_type y descanso. Es una tercera clase,
`historical_schedule_context`, aprobada para entrenamiento como aproximación;
no se etiqueta como publicación prepartido verificada ni como resultado deportivo.
Para rest se prefiere kickoff programado de G y kickoff real del partido previo;
si falta el programado se registra el uso del histórico de G. Esta autorización
no aplica a mercado/odds, clima, lesiones, inactivos, roster, noticias o QB.
Los controles de eventos y contexto point-in-time anteriores permanecen vigentes.
Detalles y trazabilidad en [game_context_phase3.md](game_context_phase3.md).
