# KickEdge

KickEdge estima la probabilidad de un pick de **extra points convertidos (XPM)**
de un kicker NFL que **el usuario ya está considerando**. El usuario aporta
kicker, partido, línea, lado (Over/Under) y cuota americana. KickEdge construye
un snapshot pregame con datos actuales de nflverse, ejecuta el modelo congelado y
muestra la probabilidad del pick, la distribución XPM, los datos usados, la
calidad de datos y una comparación neutral con el precio.

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

## Uso local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m kickedge.web          # http://127.0.0.1:8000
```

Abre `http://127.0.0.1:8000`, escribe kicker, equipo, rival, línea, lado y cuota,
y pulsa **Analyze pick**. La primera consulta descarga y cachea los datos nflverse
de la temporada (`data/cache/current`, ignorado por Git); las siguientes reutilizan
el cache durante 6 h. "Refresh NFL data" fuerza una descarga nueva. El modelo se
instala solo desde `models/phase5` si falta `data/models/phase5`.

Variables de entorno (todas opcionales):

| Variable | Uso |
|---|---|
| `PARLAY_API_KEY` | Contexto de mercado opcional (ParlayAPI). Sin ella el mercado queda "unavailable" y el análisis manual funciona igual. Solo servidor. |
| `PORT`, `HOST` | Puerto/host de `python -m kickedge.web` (por defecto 8000 / 127.0.0.1). |
| `KICKEDGE_ROOT` | Directorio de trabajo para datos y cache (por defecto el actual). |

CLI equivalente:
`python -m kickedge analyze --kicker "Chase McLaughlin" --team TB --opponent GB --season 2026 --week 4 --line 2.5 --side over --odds +115`

API: `GET /healthz`, `GET /readyz`, `GET /api/model`, `POST /api/analyze`
(detalles en [docs/product_phase7c.md](docs/product_phase7c.md)).

## Deployment

`render.yaml` define un único Web Service en Render: build con
`requirements.lock.txt`, start con `uvicorn kickedge.web.app:app --port $PORT`,
health check `/readyz`. El filesystem puede ser efímero: el artifact se reinstala
desde Git verificando SHA-256 y el cache nflverse se recrea bajo demanda.
`PARLAY_API_KEY` se configura solo en el dashboard de Render.

## Limitaciones

- No es un sistema de recomendación de apuestas; las estimaciones son inciertas.
- Una sola temporada de holdout ciego; supuesto Poisson; cola alta de XPM más incierta.
- Historias de inicio de temporada escasas (rolling NULL resueltos por el imputer congelado).
- La afiliación actual del kicker no se verifica contra rosters.
- Proveedores opcionales pueden fallar; el clima casi nunca está disponible porque
  el schedule de nflverse no trae coordenadas del estadio.
- Las predicciones dependen de la frescura de los datos fuente. Sin garantía de rendimiento futuro.

## Tests y estructura

`python -m pytest -q` (547 tests; los de interfaz usan Edge/Chrome headless si existe).

```
kickedge/ingest, transform, build   datos históricos nflverse y labels
kickedge/features                   builders de features + contrato de 82 columnas
kickedge/modeling, validation       entrenamiento (fases 5–6, ya congelado)
kickedge/inference                  motor 7A: carga verificada, distribución, odds
kickedge/current                    pipeline 7B: datos actuales -> snapshot
kickedge/web                        API FastAPI + interfaz estática (7C)
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
