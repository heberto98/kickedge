# KickEdge — Tracking & Monitoring Update

Actualización de producto encima del sistema existente. **Mide** el modelo V1 congelado
(Poisson GLM, alpha 0.1, 82 features, artefacto `c2f8f5ff…f0d0`); no cambia el modelo, las
features, el cutoff ni la matemática de inferencia o de cuotas, no reentrena, no recalibra y
no toca V2.

Flujo: **Analyze → Track → Refresh results → auto-settle → performance → movement / calibration.**
Todo es local: archivos JSON bajo `data/current/` (ignorado por Git), sin cuentas, sin nube,
sin base de datos, sin servicios en segundo plano.

## 1. Auto-settlement

**Cuándo corre.** Al abrir la web y al pulsar **Refresh results**
(`POST /api/tracking/refresh-results`). No hay cron, daemon ni servicio. La fuente se carga con
las reglas del cache actual: si los datos tienen menos de 6 h se reutilizan; si no, se descargan
una vez. `{"refresh_data": true}` fuerza una descarga explícita (la interfaz no lo hace).

**Fuente.** Solo el bundle nflverse de temporada actual ya aprobado y verificado por hash
(`kickedge.current.sources`), el mismo que construye las features. No hay scraping ni fuentes nuevas.

**Reglas para resolver el XPM real** (`kickedge/current/auto_settlement.py`):

1. El `game_id` debe aparecer como evento **completado**: jugada no borrada "END GAME" en
   play-by-play (`event_completed`). Que el kickoff haya pasado no basta.
2. El kicker trackeado debe tener **exactamente una** fila de label en ese partido, con el
   **mismo ID estable de nflverse** y el **mismo equipo**. Nunca hay coincidencia por nombre ni
   sustitución por otro kicker.
3. La fila debe ser utilizable bajo la política de labels del entrenamiento:
   `statistical_label_usable` (player stats y play-by-play coinciden, cobertura completa,
   participación observada, sin resultados de PAT desconocidos, ID y calendario verificados).
4. Un **0** solo se acepta con la evidencia explícita de la fuente
   (`explicit_stats_zero_and_complete_pbp_with_participation`). Una fila ausente nunca es un 0.

**Casos que quedan sin resolver** (el pick sigue OPEN):

- `kicker_not_in_completed_game`: no jugó, fue reemplazado o no hay fila.
- `kicker_ambiguous`: más de una fila con ese ID.
- `kicker_team_mismatch`.
- `label_not_usable:<estado>`, por ejemplo discrepancia entre fuentes, participación no
  verificada o PBP incompleto.
- `zero_not_verified`.
- `xpm_missing_or_invalid`.

Cada uno genera el aviso `AUTO_SETTLEMENT_UNRESOLVED`. Si el partido aún no figura como
completado, el pick queda pendiente. Cuatro horas después del kickoff aparece además el aviso
`TRACKED_GAME_PENDING_IN_SOURCE`.

**Escritura.** `settlement.json` se crea con escritura exclusiva y la misma semántica
WIN/LOSS/PUSH que el manual. Además guarda:

- `settlement_source: "auto_nflverse"`
- `source_game_id`
- `source_fetched_at`
- `source_hash` (hash del evento)
- `source_bundle_id`
- `auto_settled_at`

`pick.json` y `manifest.json` no se tocan. Cada liquidación automática añade una línea a
`data/current/monitoring/settlement_log.jsonl` con timestamp, tracking_id, tipo, leg, game_id,
kicker, actual_xpm, result, hash de la fuente y hora de captura. No contiene secretos.

**Protecciones:**

- **Manual primero:** un settlement existente nunca se reemplaza. Si el resultado manual (o
  corregido) difiere de la fuente, aparece `MANUAL_RESULT_DIFFERS_FROM_SOURCE` y no se modifica nada.
- **Settle manual:** sigue disponible como respaldo para picks sin liquidar; tras un auto-settlement
  queda bloqueado (`ALREADY_SETTLED`).
- **Correct result:** funciona igual sobre resultados automáticos. El settlement automático se
  conserva como original en el historial y la corrección más reciente es el resultado efectivo.
- **Fallo de la fuente:** si nflverse falla, ningún estado cambia, nada se marca como LOSS y se
  muestra `SOURCE_UNAVAILABLE`.

**Multi.** Cada leg se liquida por separado con las mismas reglas. El estado de la combinada
(OPEN, PARTIALLY SETTLED, SETTLED) y su resultado descriptivo se recalculan solos a partir de las legs.

**Legacy.** Los picks y multis trackeados antes de esta actualización se liquidan igual: no
hubo migración, y la ausencia de `settlement_source` significa "Manual".

**Fuente del resultado en la interfaz:** Auto — nflverse, Manual o Corrected.

## 2. Data freshness

Tarjeta lateral **Data freshness**, que se actualiza en cada refresh:

- cuándo se descargaron los datos NFL (por ejemplo "2 h ago");
- último partido completado incorporado;
- última semana con todos sus partidos completados;
- política de cutoff: kickoff − 60 min, y un partido completado entra en las features solo
  tras la compuerta conservadora de 24 h;
- modelo: KickEdge V1 · `phase5-c2f8f5ff0071`.

**Avisos.** Nunca bloquean análisis:

- `SOURCE_OLDER_THAN_6H` (más de 6 h) y `DATA_TOO_STALE` (más de 24 h);
- `COMPLETED_GAME_NOT_YET_IN_SOURCE`: partidos que debían haber terminado (4 h tras el kickoff)
  y aún no figuran;
- `SOURCE_UNAVAILABLE`: muestra la última hora de descarga conocida, leída del manifiesto del cache.

## 3. Performance dashboard (pestaña Performance)

Usa **solo picks trackeados**, con su resultado efectivo más reciente. Los análisis recientes
no trackeados nunca cuentan.

**Probabilidad usada:** la probabilidad KickEdge del lado elegido. En líneas enteras va
condicionada a no push y los pushes se excluyen, igual que el Brier del tracker.

**Métricas globales:**

- Singles trackeados y liquidados, legs de Multi liquidadas, multis liquidadas.
- Probabilidad media, frecuencia observada y Brier, cada uno con su n.

**Calibración:**

- 10 buckets (0–10% … 90–100%) con n, media predicha, frecuencia observada y Brier.
- Gráfico SVG de predicho frente a observado, con la diagonal de calibración perfecta.
- Solo aparecen buckets con muestra.

**Agrupaciones** (solo filas con muestra):

- **Rangos legibles:** <50%, 50–60, 60–70, 70–80, 80–90, 90%+.
- **Por línea:** Over/Under 0.5, 1.5, 2.5, 3.5…
- **Por semana:** temporada y semana.

**Single frente a Multi.** Hay secciones separadas para Single tracked picks y Multi legs, más
"All individual tracked selections" con la nota "Multi legs may be correlated."

**Multis.** Independent-game y same-game/correlated se muestran por separado, nunca mezclados.
Cada grupo indica n, probabilidad combinada aproximada media, frecuencia observada de "todas
ganan" y su Brier, con la nota "Combined probability assumes independence."

**Muestra pequeña.** Todo bloque con n < 20 lleva la etiqueta **Small sample**. Las secciones
largas son desplegables y las tablas usan scroll horizontal controlado en móvil.

## 4. Prediction movement y snapshot diff

Detecta análisis guardados de la misma selección: mismo `game_id`, kicker (ID estable), lado y
línea. Usa análisis Single y legs de Multi; describe cambios de predicción, no rendimiento.

- **Model movement:** un punto por snapshot distinto, en orden cronológico, con hora,
  probabilidad, expected XPM y hash del snapshot. Incluye el cambio desde el primero y desde el
  anterior, y un gráfico de línea SVG.
- **Price movement:** separado. Solo aparece si tú analizaste esa misma selección con cuotas
  distintas; nunca se infiere el movimiento de un sportsbook.
- **Snapshot diff:** lista las features cuyo valor almacenado cambió entre snapshots (por
  ejemplo `days_since_last_game` o `kicker_xpm_last_3`), solo como datos. El texto dice
  expresamente que no explica el cambio de probabilidad.

Aparece en el resultado Single (también al reabrir un análisis reciente) y como desplegable en
cada pick trackeado. Los archivos de los análisis solo se leen.

## 5. Line comparison

Desplegable **Compare XPM lines** del resultado Single
(`GET /api/line-comparison/{analysis_id}`).

- Líneas 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0 y 4.5, más la analizada.
- Para cada una: P(Over), P(Under), P(Push) y cuota justa de Over y Under.
- Usa la **misma distribución** del análisis (su media de Poisson guardada) con
  `line_probabilities`, la función del motor. No vuelve a ejecutar el modelo.
- En líneas enteras la cuota justa está condicionada a no push, como en el análisis Single.
- La línea analizada reproduce exactamente las probabilidades guardadas (verificado en tests y
  en QA con datos reales).
- No pide cuotas por línea: para evaluar otro precio, se analiza esa línea como un Single nuevo.

## 6. Monitoring snapshots y referencia de 150 observaciones

**Snapshots.** Se guardan en `data/current/monitoring/snapshots/` e incluyen:

- temporada, última semana y último partido completados;
- conteos de liquidados (singles, legs, multis);
- métricas y calibración de Single y de legs;
- grupos de multis;
- hash del modelo V1;
- estado de validación forward.

Se escriben **solo si el contenido cambió**: nuevos settlements, una semana completada o
métricas distintas. Las horas de captura se excluyen del contenido, así que recargar la página
no crea copias.

**Referencia V2.** Se muestra siempre "Forward validation reference: 84 / 150 observations at
last V2 audit".

- **Conteo:** partidos-kicker completados de 2026 que pasan la regla de labels del forward V2
  (`kickedge.v2.forward.label_exclusions`, una función pura ya publicada).
- **Qué no hace:** no carga modelos V2, no calcula métricas V2, no compara V1 con B2 y no corre tuning.
- **Cota superior:** el audit V2 también aplica reglas de liberación del historial (14 de 98
  filas excluidas en el último audit), así que el número real de filas puede ser menor.
- **Al llegar a 150:** se muestra "V2 re-evaluation threshold reached (label-eligible count)."
  No se adopta nada; una reevaluación sería un paso manual y preregistrado aparte.
- **Estado actual (QA con datos reales, semanas 1–4 completas):** 128 / 150.

## 7. API

| Endpoint | Uso |
| --- | --- |
| `POST /api/tracking/refresh-results` | Auto-settlement + freshness + performance + snapshot. Cuerpo opcional `{"refresh_data": bool}` estricto. |
| `GET /api/performance` | Dashboard desde los registros locales; no lee la fuente. |
| `GET /api/monitoring` | Último snapshot, número de snapshots, referencia forward e identidad del modelo. |
| `GET /api/prediction-movement/{id}` | `id` de un análisis guardado o de un pick trackeado (64 hex). |
| `GET /api/line-comparison/{analysis_id}` | Líneas a partir de un análisis Single guardado. |

Todos los IDs se validan con patrón estricto y confinamiento de ruta. Los cuerpos rechazan
campos extra.

## 8. QA

**Datos reales (cache nflverse 2026 de hoy, sin descarga).** Se usó un estado temporal de QA:
el tracker real del usuario no se tocó.

- **Picks trackeados:** desde análisis genuinamente pregame de la semana 4, congelados en su
  hora de generación: 5 singles y 2 multis, una de ellas same-game.
- **A) Partidos completados:** 11 liquidaciones automáticas con XPM oficial, entre ellas un 0
  verificado (Reichard: 0 XPM, LOSS) y la multi same-game con HAS LOSS.
- **B) Picks futuros** (semanas 5 y 15): siguen OPEN.
- **Segundo refresh:** 0 liquidaciones nuevas y ningún snapshot nuevo.
- **C) Performance y calibración:** visibles.
- **D) Movement real:** 9 análisis de McLaughlin con el input `days_since_last_game` cambiando
  (±0.0 pp).
- **E) Line comparison:** coincide con el análisis.
- **G) Estado de las multis:** correcto.

**Capturas a 1280×900 y 390×844**, con la app real servida localmente; en móvil, sin scroll
horizontal de página. Para fijar el viewport, el proceso de QA sirve la app dentro de un iframe
quitando `X-Frame-Options` solo en ese proceso; el producto no cambia.

**Bugs de layout encontrados y corregidos:**

1. **Hueco bajo las pestañas en escritorio.** Con una columna lateral alta, el hueco grande bajo
   las pestañas venía de la fila de las pestañas, que se estiraba. Ahora la fila flexible es la
   del panel.
2. **Estado de tracked picks de 220 px.** La línea de estado heredaba el `flex-basis` del estado
   del formulario.

**Tests automatizados:**

- Los tests de navegador nuevos usan viewports exactos de 1280 y 390 px y comprueban que no
  haya overflow horizontal.
- Suite completa: 827 passed (790 antes + 37 nuevos).

## 9. Limitaciones conocidas

**Fuente y momento del resultado:**

- El auto-settlement depende de que nflverse publique el play-by-play con "END GAME" y que ambas
  fuentes coincidan. Hasta entonces (normalmente horas), el pick queda pendiente.
- Con el cache de 6 h, un resultado recién publicado puede tardar hasta 6 h en verse, salvo
  descarga explícita por API.
- Un kicker inactivo o reemplazado nunca se liquida automáticamente. Las reglas de "void" de
  cada sportsbook varían; se decide a mano.
- Una diferencia manual frente a la fuente solo se avisa; corregir es decisión del usuario.

**Métricas:**

- Con muestras pequeñas las métricas son ruidosas. Las legs de una misma multi pueden estar
  correlacionadas.
- La probabilidad combinada de las multis asume independencia.

**Movement:**

- El snapshot incluye el momento del análisis. Reanálisis seguidos pueden aparecer como puntos
  con cambios mínimos, por ejemplo días desde el último partido.

**Referencia de 150:**

- El conteo es una cota superior basada en labels, no el número exacto de filas de un audit V2.
