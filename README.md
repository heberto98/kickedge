# KickEdge

KickEdge estima la probabilidad de un pick de **extra points convertidos (XPM)**
de un kicker NFL que **el usuario ya está considerando**. El usuario aporta
partido, kicker, lado (Over/Under), línea y **cuota decimal** (por ejemplo 1.91).
KickEdge construye un snapshot pregame con datos actuales de nflverse, ejecuta el
modelo congelado y muestra la probabilidad del pick, la distribución XPM, los datos
usados, la calidad de datos y una comparación neutral con el precio. También analiza
**varias selecciones** a la vez (2–10), cada una con el mismo pipeline individual.

**Qué NO es:** no es un sistema de picks. No busca ni ordena apuestas, no dice
BET/PASS, no recomienda stake, no usa Kelly ni gestiona bankroll. La decisión es
siempre del usuario.

## Arquitectura y flujo

```
Navegador (HTML/CSS/JS sin framework)
  -> FastAPI  kickedge/web        validación, errores HTTP, rate limit, estáticos
  -> 7B       kickedge/current    cache nflverse, partido, kicker, 82 features
  -> 7A       kickedge/inference  modelo verificado por SHA-256, distribución, odds
```

Una sola fuente de verdad: las features salen de los builders históricos
(`kickedge/features`) y toda la matemática de probabilidad/odds/no-vig/EV de
`kickedge/inference`. La web no recalcula nada.

## Modelo y validación

- Poisson GLM, alpha = 0.1, 82 predictores pregame, refit 2016–2024, congelado.
- Validación ciega preregistrada en 2025 (no usada para ajustar): **PASS**; mejora
  NLL, RPS y Brier frente al baseline congelado.
- Clima y mercado **no** son predictores: se muestran solo como contexto.
- Artifact versionado en `models/phase5/`, fijado por SHA-256 en
  `kickedge/inference/release.json`; se instala y verifica al arrancar.

## Uso local (diario)

KickEdge está pensado para usarse **solo en tu PC** (`127.0.0.1`): sin cuentas,
sin base de datos, sin telemetría ni servicios en la nube.

**Opción fácil:** doble clic en `start-kickedge.bat`. Verifica `.venv`, arranca
el servidor y abre el navegador en `http://127.0.0.1:8000` cuando está listo.
Para detenerlo: `Ctrl+C` en esa ventana. Si KickEdge ya estaba abierto, solo
abre el navegador; si el puerto 8000 lo usa otro programa, lo dice y no toca nada.

**Opción terminal:**

```powershell
.\.venv\Scripts\python.exe -m kickedge.web           # http://127.0.0.1:8000
.\.venv\Scripts\python.exe -m kickedge.web --open    # además abre el navegador
```

Instalación (una sola vez):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

### Flujo: Single pick

1. **Upcoming game:** busca y elige el partido (`ram`, `eagles`, `LAR`, `week 4`).
   La lista sale del schedule nflverse cacheado, solo partidos futuros, en orden
   cronológico y con hora local del navegador.
2. **Kicker:** al elegir el partido aparecen los kickers de ambos equipos
   (roster nflverse y quienes han pateado esta temporada), con su estado
   (`Active roster`, `Practice squad`, ...). **El equipo sale del kicker elegido**
   y se muestra como dato ("Los Angeles Rams · Active roster"); no se pide dos veces.
   Si escribes un kicker a mano, KickEdge deriva su equipo (roster, luego partidos
   de la temporada); solo si no puede, te pide elegirlo una vez.
3. **Side** (Over/Under), **XPM line** y **Decimal odds** (`1.30`, `1.91`, `2.00`;
   se aceptan `1.8` o `2`, que se muestran como `1.80` y `2.00`).
4. **Analyze pick.**

Teclado: flechas, `Enter` y `Escape` en ambas listas. `Advanced` conserva la
entrada manual (equipo/rival, temporada, semana, game id, cuotas decimales de
ambos lados para no-vig, contexto de mercado y clima, refresh de datos).

**Cuotas decimales:** formato principal de la interfaz (stake incluido, siempre
mayor que 1). Probabilidad implícita = `1 / cuota` (2.00 → 50.0 %, 1.50 → 66.7 %,
1.91 → 52.4 %); beneficio por unidad si gana = `cuota − 1`; cuota justa del modelo =
`1 / p` (en líneas enteras, `p` condicional a no-push). Los análisis guardados antes
con cuotas americanas siguen abriéndose y se muestran como "legacy US" con su
equivalente decimal (`+A → 1 + A/100`, `−A → 1 + 100/A`). La API y la CLI siguen
aceptando cuotas americanas por compatibilidad.

### Flujo: Multiple selections

1. Pestaña **Multiple selections**: empieza con 2 selecciones; **+ Add selection**
   añade hasta 10 y **Remove** quita cualquiera (se renumeran sin perder datos).
2. En cada selección: partido, kicker (el equipo se deriva igual que en Single),
   Over/Under, línea y cuota decimal; `Advanced` por selección: cuota del otro lado
   y equipos manuales.
3. **Analyze selections.**

Cada selección pasa por **exactamente** el mismo pipeline que un Single pick (mismo
snapshot de 82 features, mismo modelo, misma probabilidad); los datos NFL se cargan
una vez por petición y el clima una vez por partido. El resultado muestra cada
selección (probabilidad KickEdge, probabilidad implícita, diferencia, expected XPM y
feedback) y un resumen combinado:

- **Cuota decimal combinada** = producto de las cuotas; **probabilidad implícita
  combinada** = `1 / cuota combinada` (1.50 × 1.40 = 2.10 → 47.6 %).
- **Probabilidad aproximada de KickEdge** = producto de las probabilidades de que
  cada selección gane (todas ganan). **Supone independencia**: KickEdge no modela
  correlación entre selecciones. Selecciones del **mismo partido** (mismo `game_id`)
  generan un aviso visible: pueden estar correlacionadas y la aproximación puede ser
  muy inexacta.
- Líneas enteras pueden hacer push: se informa la probabilidad de que todas ganen
  (y la de no perder ninguna), sin simular reglas de parlay de cada casa.
- Si alguna selección falla (p. ej. `KICKER_NOT_FOUND`), se indica en esa selección
  y **no** se calcula el combinado sobre un subconjunto.

### Resultado

En orden: probabilidad de tu pick, expected XPM, P(Over)/P(Under)/P(Push),
distribución con la línea marcada (Win/Loss/Push por conteo), "What KickEdge saw"
(forma del kicker, ofensiva, defensa rival, contexto; diferencias recientes vs
temporada, sin adjetivos), las 82 entradas auditables, calidad de datos compacta,
comparación neutral con el precio y detalles técnicos. El EV queda en un
desplegable secundario.

**Feedback estadístico:** debajo de la probabilidad, un párrafo compara la
probabilidad que implica la cuota con la que estima KickEdge, por ejemplo: "At
decimal odds 1.30, the price implies 76.9%. KickEdge estimates 64.5%. The model
estimate is 12.4 percentage points lower than the probability implied by the
price." Nunca dice si conviene apostar; las diferencias llevan signo y texto
("model higher/lower"), no solo color.

**Afiliación del kicker:** se verifica con los datos de jugadores de nflverse
(`latest_team`, `status`, `last_season`) ya descargados. Si coincide con el roster
activo: "Current team affiliation verified." Si no se puede confirmar, aparece un
aviso neutral. Si nflverse lo lista en el roster activo del rival, el análisis se
detiene (`KICKER_TEAM_MISMATCH`) y nunca se sustituye al kicker.

**Clima:** `kickedge/venues.json` (versionado) da coordenadas y tipo de techo de
los 39 estadios de los schedules 2024–2026; se resuelve por nombre y alias del
venue, nunca por geocoding en vivo. Estadios abiertos: pronóstico Open-Meteo
para la hora del kickoff (temperatura, viento, ráfagas, probabilidad y cantidad
de precipitación, condición), disponible dentro de 16 días. Domo/techo cerrado:
"Indoor / closed roof". Techo retráctil sin estado confirmado: no se muestra
clima exterior. El clima es solo contexto y **no** entra al modelo.

**Análisis recientes:** cada análisis (single o multi) se guarda localmente en
`data/current/analyses/<sha256>/` (ignorado por Git). El panel "Recent analyses"
los lista y los reabre tal como se guardaron, sin volver a consultar proveedores.

**Tracked picks (oficiales):** después de un análisis Single, "Track pick" congela
lo que KickEdge decía antes del partido (probabilidad, P(Over/Under/Push), expected
XPM, cuota decimal, versión de modelo, hash del snapshot y avisos) en
`data/current/tracked/<id>/pick.json` (ignorado por Git). Solo se permite antes del
kickoff; el archivo se crea una vez y nunca se reescribe (un hash de integridad
detecta ediciones). Trackear el mismo pick (partido, kicker, lado, línea y cuota)
devuelve el original. Después del kickoff se introduce a mano el XPM real; KickEdge
añade una sola vez `settled_at`, `actual_xpm` y `result` (WIN/LOSS/PUSH) en
`settlement.json`. Si el XPM real se escribió mal, "Correct result" (con confirmación
y razón opcional) añade `corrections/NNNN.json` con valores previos y nuevos; el
settlement original y las correcciones anteriores no se tocan, la corrección más
reciente es el resultado efectivo y el historial se ve en "View correction
history". El panel muestra Open/Settled y, con picks liquidados, la
probabilidad media, la frecuencia observada y el Brier score (pushes excluidos;
con línea entera se usa la probabilidad condicionada a no push). Sin stake, ROI ni
recomendaciones: solo calidad de las probabilidades.

**Tracked multis:** después de un análisis Multi, "Track multi" congela en
`data/current/tracked_multi/<id>/manifest.json` (ignorado por Git, hash de
integridad) las cuotas y probabilidades combinadas, los avisos de independencia y
same-game, y cada selección con los mismos campos que un pick Single. Solo si
ninguna selección llegó a su kickoff; la misma combinación (partido, kicker, lado,
línea y cuota de cada leg) devuelve el original. Cada leg se liquida por separado
después de su kickoff y admite "Correct result" auditado igual que Single
(`legs/<n>/settlement.json` y `corrections/`). Estados: OPEN, PARTIALLY SETTLED,
SETTLED; resultado descriptivo ALL LEGS WON, HAS LOSS o NO-LOSS WITH PUSH (nunca se
recalcula el pago con push: las reglas del sportsbook varían). Métricas: legs
individuales (fuente `multi_leg`, separadas de Single y posiblemente correlacionadas)
y, por grupo independiente vs same-game, el evento "all legs win" frente a la
probabilidad combinada aproximada, que asume independencia.

**Tracking flow:** Analyze → Track → Refresh results → auto-settle → performance.
Al abrir la web (y con el botón **Refresh results**) KickEdge revisa los datos nflverse
ya aprobados, respetando el cache de 6 h, y liquida solos los picks y legs cuyo partido
está completado (play END GAME) cuando el kicker trackeado tiene un único label
reconciliado por dos fuentes (mismo ID estable y equipo; un 0 solo si la fuente lo
verifica con participación observada). Si falta algo, el pick sigue OPEN con un aviso
(`AUTO_SETTLEMENT_UNRESOLVED`); nunca se adivina ni se sustituye al kicker. El
settlement automático guarda `settlement_source=auto_nflverse`, partido, hash y hora de
la fuente, y se registra en `data/current/monitoring/settlement_log.jsonl`. **Settle**
manual sigue como respaldo; un resultado manual nunca se reemplaza (si no coincide con
nflverse aparece `MANUAL_RESULT_DIFFERS_FROM_SOURCE`) y **Correct result** funciona
igual sobre resultados automáticos. Cada settlement muestra su fuente: Auto — nflverse,
Manual o Corrected.

**Data freshness / Performance / Monitoring:** la tarjeta Data freshness muestra cuándo
se descargaron los datos NFL, el último partido y semana completos, la política de
cutoff y el modelo, con avisos si la fuente tiene más de 6 h o falta un partido que ya
debería haber terminado. La pestaña **Performance** usa solo picks trackeados (nunca
análisis recientes sin trackear): probabilidad media, frecuencia observada y Brier
(pushes excluidos), buckets de calibración con gráfico, rangos de probabilidad, por
línea y por semana, siempre con n y "Small sample" si n < 20; Singles y legs de Multi
por separado, y multis independientes vs same-game por separado. Un snapshot de
monitoreo (`data/current/monitoring/snapshots/`) se escribe solo si algo cambió, e
incluye el hash del modelo V1 y la referencia "84 / 150 observations at last V2 audit"
con el conteo de observaciones 2026 elegibles por label (no evalúa V2).

**Prediction movement / Compare XPM lines:** si la misma selección (partido, kicker,
lado, línea) se analizó varias veces, el resultado muestra el movimiento del modelo
(probabilidad y expected XPM por snapshot, con los inputs que cambiaron, sin atribuir
causas) y, aparte, el de las cuotas que tú ingresaste. "Compare XPM lines" muestra
P(Over), P(Under), P(Push) y cuota justa para 0.5–4.5 con la misma distribución del
análisis, sin volver a ejecutar el modelo.

Variables de entorno (todas opcionales):

| Variable | Uso |
|---|---|
| `PARLAY_API_KEY` | Contexto de mercado opcional (ParlayAPI), solo si marcas "Include market context". Sin ella el mercado queda "Unavailable" y el análisis manual funciona igual. Solo servidor. |
| `PORT`, `HOST` | Puerto/host local (por defecto 8000 / 127.0.0.1). |
| `KICKEDGE_ROOT` | Directorio de trabajo para datos y cache (por defecto el actual). |

La primera consulta del día descarga y cachea los datos nflverse de la temporada
(`data/cache/current`); después se reutiliza el cache durante 6 h. El modelo se
instala solo desde `models/phase5` si falta `data/models/phase5`, verificando SHA-256.

CLI equivalente (acepta los mismos aliases; conserva cuotas americanas por compatibilidad):
`python -m kickedge analyze --kicker "Harrison Mevis" --team LAR --opponent PHI --season 2026 --week 4 --line 1.5 --side over --odds -333`

API local: `GET /healthz`, `/readyz`, `/api/model`, `/api/games`,
`/api/games/{game_id}/kickers`, `/api/analyses`, `/api/analyses/{id}`,
`/api/multi/{id}`, `/api/tracked`, `/api/tracked/{id}`, `POST /api/analyze`,
`POST /api/analyze-multi`, `POST /api/tracked`, `POST /api/tracked/{id}/settle`,
`POST /api/tracked/{id}/correct`, `/api/tracked-multi`, `/api/tracked-multi/{id}`,
`POST /api/tracked-multi`, `POST /api/tracked-multi/{id}/legs/{n}/settle|correct`,
`POST /api/tracking/refresh-results`, `/api/performance`, `/api/monitoring`,
`/api/prediction-movement/{id}` y `/api/line-comparison/{id}` (ver
[reports/tracking_monitoring_update.md](reports/tracking_monitoring_update.md),
[docs/product_phase7c.md](docs/product_phase7c.md),
[reports/product_polish.md](reports/product_polish.md) y
[reports/final_multi_decimal_polish.md](reports/final_multi_decimal_polish.md)).

`render.yaml` se conserva del cierre de 7C, pero KickEdge se usa solo localmente;
no hace falta ningún servicio en la nube.

## Limitaciones

- No es un sistema de recomendación de apuestas; las estimaciones son inciertas.
- Una sola temporada de holdout ciego; supuesto Poisson; cola alta de XPM más incierta.
- Historias de inicio de temporada escasas (rolling NULL resueltos por el imputer congelado).
- La afiliación se verifica con datos de jugadores de nflverse cuando existen; la
  participación real el día del partido no se verifica.
- Clima: solo dentro de 16 días del kickoff; estadios con techo retráctil sin
  estado publicado no muestran clima exterior.
- Selecciones múltiples: la probabilidad combinada es una aproximación que supone
  independencia; selecciones del mismo partido pueden estar correlacionadas.
- Proveedores opcionales pueden fallar sin bloquear el análisis.
- Las predicciones dependen de la frescura de los datos fuente. Sin garantía de rendimiento futuro.

## Tests y estructura

`python -m pytest -q` (685 tests; los de interfaz usan Edge/Chrome headless si existe).

```
start-kickedge.bat                  lanzador local de Windows
kickedge/ingest, transform, build   datos históricos nflverse y labels
kickedge/features                   builders de features + contrato de 82 columnas
kickedge/modeling, validation       entrenamiento (fases 5–6, ya congelado)
kickedge/inference                  motor 7A: carga verificada, distribución, odds
kickedge/current                    pipeline 7B: datos actuales -> snapshot; catalog (partidos, kickers, roster); multi (combinado)
kickedge/teams.py                   metadata y aliases de equipos
kickedge/venues.py, venues.json     estadios versionados (coordenadas, techo)
kickedge/web                        API FastAPI + interfaz estática
models/phase5                       artifact congelado versionado
docs/, reports/                     metodología y verificación por fase
```

## Núcleo histórico (pipeline de datos)

Dataset local **2015–2025**, temporada regular y playoffs, en Python + DuckDB/Parquet.
La unidad del label es `(game_id, team, player_id)`; XPM y XPA requieren acuerdo
entre player stats y el conteo PBP. **La población es observada después del partido**,
no una lista de titulares conocidos antes del kickoff. Incluye ceros demostrables.

Incluye features historicas y adaptadores opcionales de mercado/clima con controles temporales. Las fases siguientes (5–7C) añaden el modelo congelado, la inferencia y el producto web.

## Ejecutar

Desde la carpeta del repositorio, en PowerShell, use Python 3.12 (verificado con
3.12.14). El entorno virtual y los datasets no están incluidos en GitHub:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m kickedge ingest
.\.venv\Scripts\python.exe -m kickedge build
.\.venv\Scripts\python.exe -m kickedge audit
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m kickedge validate
```

Solo `ingest` necesita red en la primera descarga. Las siguientes ingestas verifican
SHA-256 y reutilizan el caché. `ingest --refresh` consulta versiones nuevas y conserva
los originales anteriores. Los casos auditados deben revisarse si cambia su PBP.
Los tests con datos reales se omiten explícitamente si todavía no existe un build.

`build --manifest RUTA` fija un lock de fuentes concreto. `validate` reconstruye con
el lock del último build y compara todos los hashes Parquet y el reporte de calidad.
Si cambió el código/configuración/runtime, primero se debe crear otro build.

## Archivos y salidas

| Ruta | Uso |
| --- | --- |
| `config.toml` | Temporadas, tipos de partido, carpetas y población |
| `kickedge/ingest.py` | Descargas originales, hashes, esquema y procedencia |
| `kickedge/transform.py`, `labels.py` | Tablas intermedias y política de labels |
| `kickedge/validate.py` | Controles de integridad y reconciliación |
| `data/raw/<fuente>/<temporada>/<sha256>/` | Original Parquet y `source.json` |
| `data/manifests/` | Locks de fuentes; `sources.json` apunta al último conjunto descargado |
| `data/processed/latest.json` | Ruta e ID del último build publicado |
| `data/processed/<build_id>/historical_base.parquet` | Base integrada de kicker-partido y resultados del equipo |
| `data/processed/<build_id>/labels.parquet` | Labels, evidencia, flags e IDs de procedencia |
| `data/processed/<build_id>/team_games.parquet` | Universo completo, incluidos equipos sin kicker identificable |
| `data/processed/<build_id>/build.json` | Configuración efectiva, versiones, hashes y esquemas de salidas |
| `reports/quality.md` | Conteos, distribución, faltantes, exclusiones y controles |
| `reports/manual_audit.md` | Ocho partidos revisados, con IDs de jugada |
| `docs/decisiones.md`, `docs/diccionario.md` | Límites metodológicos y significado de campos |

También se guardan `games`, `players`, `game_coverage`, `player_stats_kicking`,
`pbp_kicker_totals` y `pbp_events`, todos en Parquet. El build conserva su propio
`source_lock.json`, reporte de calidad y copia del código en `pipeline_source/`.
Datos y entorno quedan fuera de Git; el versionado de datos es local por contenido.
Conserve originales, lock y código para reproducir un snapshot aunque nflverse lo revise.

Los reportes Markdown/JSON de `reports/` y los casos pequeños de `audits/` se
versionan como evidencia de la validación realizada. No reemplazan los datasets.
Una clonación nueva debe ejecutar la ingesta y construcción antes de validar los
datos reales. Los reportes publicados describen el snapshot original; si las fuentes
cambiaron, las expectativas de auditoría pueden requerir otra revisión manual.

## Trazar una observación

```powershell
.\.venv\Scripts\python.exe -m kickedge inspect --game 2024_02_NYG_WAS --team NYG --player 00-0026858
```

Muestra el label de Graham Gano, ambos conteos, contexto del cero, identidad,
flags y jugadas. Los campos `*_source_sha256` llevan a la entrada correspondiente
del `source_lock.json`, que contiene URL, archivo original, esquema y descarga UTC.

`target_season_eligible` marca solo 2016–2025 (2015 se reserva como historia inicial).
`eligible_for_pregame_training` permanece **false para todas las filas**.
Los archivos históricos conservan ese contrato. La investigación prepartido está
separada en `kickedge/pregame/`, con las políticas comparadas que se describen abajo.

## Dirección actual: kicker indicado por el usuario

KickEdge recibirá kicker, partido, línea XPM, lado Over/Under y cuota. El futuro
modelo estimará XPM para ese kicker; no necesita predecir automáticamente su identidad.
La observación histórica será kicker-game, definida por participación observada,
con XPM exclusivamente como target y todas las features disponibles antes del cutoff.
La participación y los flags postpartido no son inputs predictivos.

Véanse la [decisión metodológica](docs/feature_dataset.md) y el
[contrato de features](kickedge/features/contract.json). La Fase 1 implementa
21 features del historial del kicker aprobadas para entrenamiento histórico bajo
la [política temporal event-context-v1](docs/temporal_policy.md): eventos previos
concluidos y trazables no requieren timestamps de publicación del archivo histórico.
El contexto point-in-time sí los requiere. Se conserva el margen conservador +24 h.
La elegibilidad de cada fila respeta las temporadas objetivo y calidad/identidad.
No se ha entrenado ningún modelo.
La investigación pregame/change detection siguiente se conserva como trabajo previo.

La [Fase 2](docs/team_features_phase2.md) añade 20 features ofensivas y 20 de defensa
rival en un artefacto separado que integra las 21 de Fase 1 sin alterarlas.
Se ejecuta con `python -m kickedge.features prepare-teams` y
`python -m kickedge.features build-teams`. Para la matriz conjunta de 61 predictores
usar `eligible_for_phase_2_training`; ver cobertura y ejemplos en
`reports/team_features_phase2.json`.

La [Fase 3](docs/game_context_phase3.md) añade contexto de calendario, descanso,
tendencia 2PT y muestra. Usa `prepare-context` / `build-context` en el mismo CLI.
La matriz conjunta tiene 82 predictores y requiere `eligible_for_phase_3_training`.
El calendario/descanso utiliza una aproximación histórica expresamente autorizada;
mercado, clima, lesiones y QB siguen requiriendo evidencia point-in-time.

```powershell
.\.venv\Scripts\python.exe -m kickedge.features prepare
.\.venv\Scripts\python.exe -m kickedge.features build
```

Consume solo el snapshot histórico y PBP ya cacheado. Véanse el
[protocolo de Fase 1](docs/kicker_features_phase1.md) y el
[reporte de cobertura y ejemplos](reports/kicker_features_phase1.md).

## Investigación conservada: reconstrucción prepartido y simulación secuencial

La simulación congela expected kicker antes de revelar cada partido y utiliza sus
resultados solamente como historia para juegos futuros. Compara confirmación
oficial (A), continuidad corroborada (B) y continuidad experimental (C).
La disponibilidad actual no se presenta como verificada cuando solo existe historia.

```powershell
.\.venv\Scripts\python.exe -m kickedge.pregame ingest
.\.venv\Scripts\python.exe -m kickedge.pregame prepare-history
.\.venv\Scripts\python.exe -m kickedge.pregame compare
.\.venv\Scripts\python.exe -m kickedge.pregame audit
.\.venv\Scripts\python.exe -m kickedge.pregame inspect --game 2024_09_WAS_NYG --team NYG --policy-name C
.\.venv\Scripts\python.exe -m pytest -q
```

`ingest` cachea 33 activos adicionales de nflverse y las páginas oficiales registradas.
`prepare-history` prepara el oracle por partido en un proceso separado.
`compare` es offline, construye únicamente la evidencia e identidades iniciales y genera decisiones
congeladas A/B/C, un log encadenado freeze/reveal, evaluación y reportes completos.
No carga la evaluación del estudio inicial antes de simular. Para reproducir también
los reportes independientes de aquel estudio, ejecute `python -m kickedge.pregame build`.
`inspect` muestra la identidad, historia y aceptación/rechazo de evidencia **sin
abrir los outcomes**. `audit` reproduce los 13 casos revisados.

Salidas locales en `data/pregame/processed/` (estudio inicial) y
`data/pregame/sequential/` (comparación). Cada carpeta tiene `latest.json`.
La comparación incluye `identities_A/B/C.json`, `labels_A/B/C.json` y Parquet,
`events.jsonl`, `freeze.json`, `metrics.json` y `build.json`.
Los datos y caches continúan ignorados por Git.

Para repetir con fuentes fijas, añada `--source-lock` con el `source_lock.json`
del build pregame base, manteniendo código, política y dependencias congelados.
El código del build base se copia a `pipeline_source/`; las fuentes oficiales pueden
cambiar en origen, de modo que conservar los originales locales es necesario.

Resultados y límites: [comparación A/B/C](reports/pregame_policy_comparison.md),
[todas las discrepancias](reports/pregame_sequential_mismatches.md),
[auditoría manual](reports/pregame_manual_audit.md),
[metodología](docs/pregame_methodology.md),
[diccionario](docs/pregame_dictionary.md) e
[investigación de fuentes](docs/pregame_sources_research.md).
La cobertura de C es amplia pero falla especialmente cuando cambia el kicker;
no se ha aprobado una política de entrenamiento. Todas las filas de la comparación
secuencial conservan `eligible_for_pregame_training=false`.
## Fase 4: mercado y clima

La extension de [mercado/clima](docs/market_weather_phase4.md) conserva los 82
predictores anteriores y separa capturas current/forward de datos experimentales.
`python -m kickedge.features build-environment` materializa desde los snapshots
locales, sin red. Las closing lines, el clima observado y el techo retrospectivo
no se aprueban como point-in-time; no bloquean las 5,535 filas elegibles previas.
ParlayAPI y Open-Meteo se consultan solo mediante sus adaptadores opcionales.

## Fase 5: primer modelo probabilistico

`python -m kickedge.modeling train` compara un baseline, GLM y boosting Poisson
con los 82 predictores historicos. Entrena 2016–2023, valida exclusivamente en
2024 y deja un refit 2016–2024. **2025 permanece ciego, sin evaluar.**
Los binarios quedan ignorados bajo `data/models/phase5/`.
Consulta la [metodologia](docs/modeling_phase5.md), el
[reporte](reports/phase5_model_report.md) y las [metricas](reports/phase5_metrics.json).

## Fase 6: validacion ciega

El flujo `python -m kickedge.validation prepare` registra el modelo congelado y
el baseline pre-2025 antes de abrir targets. `python -m kickedge.validation reveal`
consume una unica evaluacion de 2025 y bloquea repeticiones. No entrena ni calibra.
Consulta la [metodologia](docs/blind_validation_phase6.md), la
[preregistracion](reports/phase6_preregistration.json), el
[reporte](reports/phase6_blind_validation.md) y las [metricas](reports/phase6_metrics.json).

## Fase 7A: inferencia offline y props

`python -m kickedge infer --features examples/inference_demo_2024.json --line 2.5 --side over --odds +119 --json`
carga y verifica el GLM congelado, recibe exactamente 82 features materializadas
y devuelve lambda, distribucion con cola, Over/Under/Push, implied/no-vig,
edge, fair odds, EV y advertencias. No entrena ni consulta APIs.
El ejemplo es **DEMO / TEST FIXTURE historica de 2024**, con precio hipotetico;
requiere el modelo local aprobado, que sigue ignorado por Git.
Consulta [contrato y uso](docs/inference_phase7a.md) y
[verificacion](reports/phase7a_verification.md). No se inicia Fase 7B.

## Fase 7B: snapshot pregame actual

`python -m kickedge analyze --kicker "Chase McLaughlin" --team TB --opponent GB --season 2026 --week 4 --line 2.5 --side over --odds +115 --over-odds +115 --under-odds -145`
descarga/verifica fuentes nflverse actuales (cache local ignorado), resuelve
partido y kicker, construye las 82 features con los builders historicos y
ejecuta el motor 7A congelado. ParlayAPI y Open-Meteo son opcionales y nunca
bloquean la prop manual. Consulta [arquitectura](docs/current_phase7b.md) y
[verificacion](reports/phase7b_verification.md). No se inicia Fase 7C.

## Fase 7C: producto web, API y deployment

Ver [producto](docs/product_phase7c.md) y [verificación](reports/phase7c_verification.md).

## V2: carryover, retadores y validación forward 2026

V1 sigue como campeón. V2 (carryover de temporada previa, GLM/boosting/estructural)
se evaluó con walk-forward 2020–2025 y una única evaluación forward 2026 después de
congelar; ningún candidato pasó la regla registrada y la muestra forward fue menor que
la exigida. Artefactos V2 versionados aparte en `models/v2/`; V1 sin cambios. Ver
[comparación](reports/v2_model_comparison.md), [forward 2026 y mercado](reports/v2_forward_2026_validation.md),
[sesgo](reports/v2_bias_audit.md) e [inicio de temporada](reports/v2_early_season_audit.md).
