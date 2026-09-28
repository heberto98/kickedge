# Cierre temporal de Fase 1

Política `event-context-v1`, adoptada el 2026-09-28.

- Historical event data: resultados de partidos concluidos antes del cutoff,
  excluyendo objetivo/futuros y con trazabilidad; no exige publicación histórica
  del archivo descargado retrospectivamente.
- Point-in-time context data: mantiene evidencia de disponibilidad de la versión
  antes/al cutoff. No puede reclasificarse para eludir ese requisito.
- Las 21 features implementadas del kicker quedan aprobadas para entrenamiento
  histórico en el contrato 0.3.0. Ninguna queda experimental en el nuevo build.

## Materialización y elegibilidad

- Inputs: `125f3ca711124ac270c1`; build: `834c779fa5a01a6c8372`.
- Histórico original conservado: `c7300725b93c79971254`.
- 6,083 filas técnicamente reconstruibles y conformes temporalmente.
- 5,535 filas elegibles para entrenamiento histórico, temporadas 2016–2025.
- 548 filas de 2015 permanecen como reserva histórica; única exclusión actual:
  `outside_target_seasons`.
- Se conservan flags de calidad/identidad y las 20 filas con múltiples placekickers.
  La aprobación temporal no anula controles de target, identidad ni historial.
- Los snapshots de replay anteriores conservan su estado experimental.

## Evidencia de validación

- 147 tests aprobados, incluyendo las pruebas previas de target/future leakage,
  eliminación física de resultados, freeze/reveal, ventanas y SQL independiente.
- 15 pruebas nuevas cubren clases temporales, eventos incompletos/futuros,
  disponibilidad de contexto, contrato, elegibilidad y replay antiguo.
- Ninguna feature incorpora el partido objetivo ni partidos futuros. Cada
  contribución apunta a un partido previo con conteos, relojes y hash.
- La preparación exige END GAME no eliminado; se valida fin anterior al cutoff
  y se conserva el margen conservador +24 h, que no representa publicación.
- Comparación con `18a2c65f746116405ec5`: las 6,083 claves, targets y source_label
  se conservan; los 127,743 valores (21 features por fila) no cambian.
- Repetición del nuevo build: ocho archivos idénticos byte por byte.

Fase 1 queda cerrada para entrenamiento histórico de la población condicional a
participación observada, usando exclusivamente sus 21 columnas predictivas.
Los NULL por muestra/ventana insuficiente se conservan. No se entrenó un modelo
ni se inició Fase 2. Datasets y snapshots locales siguen ignorados por Git.
