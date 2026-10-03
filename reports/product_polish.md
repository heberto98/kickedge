# KickEdge V1: polish pass final (uso local)

Fecha: 2026-10-03. Base: `010b4c6`. Alcance: UX, entrada, resolución de partido,
identidad del kicker, clima, presentación y comodidad local. **Sin cambios** en el
modelo, las 82 features, el preprocesado, alpha, la calibración ni la matemática
de 7A/7B.

## Problemas de UX encontrados

- `LAR` (abreviatura habitual de los Rams) daba `GAME_NOT_FOUND`: nflverse usa `LA`.
- Había que escribir equipo y rival a mano y conocer los códigos de nflverse.
- El kicker se escribía libremente; la afiliación al equipo nunca se verificaba.
- El clima casi nunca funcionaba: el schedule de nflverse no trae coordenadas.
- El resultado mostraba demasiado arriba, con avisos técnicos ocupando media pantalla.
- No había forma de volver a ver un análisis anterior ni un arranque de doble clic.
- Encontrados durante la QA y corregidos: (1) al escribir antes de que cargara la
  lista de partidos aparecía "No matches" y la lista no se actualizaba; (2) en
  escritorio, una lista larga de análisis recientes empujaba el resultado hacia
  abajo; (3) en móvil, el historial quedaba entre el formulario y el resultado;
  (4) el navegador podía servir CSS/JS viejos tras una actualización.

## Cambios

### Aliases de equipos (`kickedge/teams.py`)

Capa central usada por la API, la CLI (vía `resolve_target`), el selector de
partidos y el proveedor de mercado (que antes tenía su propia tabla duplicada).
Conserva los códigos canónicos de nflverse (`transform.TEAM_MACRO`); un test
verifica que coinciden.

| Entrada | Canónico |
|---|---|
| `LAR`, `lar`, `LA`, `Rams`, `Los Angeles Rams`, `LA Rams`, `STL`, `St. Louis Rams` | `LA` |
| `JAC`, `JAX`, `Jaguars`, `Jacksonville` | `JAX` (nflverse usa `JAX`; `JAC` es el alias) |
| `WSH`, `WAS`, `Washington`, `Commanders` | `WAS` |
| `OAK`, `LVR` → `LV`; `SD`, `SDG`, `LA Chargers` → `LAC`; `GNB`, `KAN`, `NWE`, `NOR`, `SFO`, `TAM`, `ARZ`, `BLT`, `CLV`, `HST` | códigos nflverse |

Mayúsculas/minúsculas y espacios no importan. `Los Angeles`, `New York` y `NY`
nunca se adivinan (`INVALID_TEAM` con las opciones). Códigos cortos desconocidos
pasan sin cambios y simplemente no coinciden con ningún partido. La API informa
`Normalized LAR → LA`.

### Selector de partidos (`GET /api/games`)

Lee el cache 7B (sin descargar si está fresco; `?refresh=true` fuerza descarga):
solo partidos futuros de la temporada actual, en orden cronológico, con nombres
amigables (`Rams @ Eagles`), códigos canónicos, venue, techo y términos de
búsqueda que incluyen los aliases. En la interfaz es un combobox ARIA 1.2:
búsqueda por tokens (`ram`, `rams eagles`, `LAR`, `week 4`), flechas, `Enter`,
`Escape`, agrupado por semana y con hora local del navegador. Al elegir el
partido quedan resueltos `game_id`, temporada, semana, kickoff y equipos.

### Selector de kicker (`GET /api/games/{game_id}/kickers`)

Lista los kickers de ambos equipos: entradas del roster nflverse (`ACT` y
practice squad `DEV`) y quienes han pateado para el equipo esta temporada, con
etiqueta de estado y partidos jugados. Elegir un kicker fija su equipo (control
"Kicker's team"). Se puede escribir un nombre o ID libremente: nunca se depende
solo del autocompletado.

### Verificación de roster

Fuente: el `players.parquet` de nflverse que 7B ya descargaba (`latest_team`,
`status`, `last_season`; sin descarga nueva). Se añadieron esas columnas al
bundle derivado con nombres explícitos (`latest_team`, `roster_status`,
`last_season`); nunca son features. `kicker_affiliation` devuelve:

- `verified=True`: mismo equipo, roster activo, temporada actual → "Current team affiliation verified."
- `verified=False`: otro estado (`Practice squad`, `Released`, …), sin entrada de
  la temporada actual u otro equipo → aviso claro.
- `verified=None`: sin datos de roster → "Kicker identity is verified from NFL
  history, but current team affiliation could not be independently confirmed."
- Conflicto: roster activo del rival en ese partido → `KICKER_TEAM_MISMATCH`
  (409). Nunca se sustituye al kicker.

En vivo: Harrison Mevis (LA), Jake Elliott (PHI), Will Reichard (MIN) y Brandon
Aubrey (DAL) quedaron verificados.

### Metadata de estadios (`kickedge/venues.json`, `kickedge/venues.py`)

39 estadios: todos los venues de los schedules nflverse 2024–2026, con aliases
de patrocinio (`Reliant Stadium` → NRG Stadium, `Mercedes-Benz Superdome`,
`FC Bayern Munich Stadium` → Allianz Arena, `Estadio Banorte`/`Azteca Stadium`, …).
Coordenadas de Wikipedia vía la API de MediaWiki (una consulta, 2026-10-03), sin
geocoding en tiempo de ejecución. Tipo de techo físico a partir de los valores
que nflverse registró en partidos completados 2016–2025; para sedes sin partidos
completados (MCG, Stade de France, Maracanã, Bernabéu) se anota la evidencia.

La resolución es **por nombre** del venue: nflverse asigna a veces el stadium id
del equipo local a partidos en sede neutral (p. ej. un partido de JAX en
Tottenham con id `JAX00`), así que el id solo se usa como verificación cruzada.
Nombres desconocidos → sin coordenadas → clima no disponible con aviso (nunca se
adivina). El techo del día respeta lo físico: un estadio abierto nunca se trata
como domo (nflverse marca `dome` en algunos partidos futuros al aire libre), un
domo nunca como exterior, y en techos retráctiles se usa el estado `open`/`closed`
del schedule si existe. La evidencia del venue se fecha en el último entre la
captura del schedule y la fecha de la metadata.

### Clima

Con coordenadas verificadas y techo abierto, Open-Meteo para la hora del kickoff:
temperatura, viento, ráfagas, probabilidad y cantidad de precipitación y código
WMO. Domo/techo cerrado: "Indoor / closed roof", sin clima exterior. Techo
retráctil sin estado: no se muestra clima exterior. Más de 16 días antes del
kickoff: aviso "forecast not yet available" sin llamada ni fallo. Sigue siendo
**solo contexto**: un test verifica que con y sin clima las 82 features, la
predicción y las probabilidades son idénticas.

En vivo (2026-10-03, Rams @ Eagles, Lincoln Financial Field): 16 °C, viento
13 km/h, ráfagas 29 km/h, 11 % de precipitación, 0.0 mm, nublado. Vikings
(U.S. Bank Stadium): indoor. Texans (NRG, retráctil sin estado): sin clima exterior.

### Interfaz

- Flujo principal: partido → kicker → (equipo del kicker) → Over/Under → línea →
  cuota → Analyze. Lo técnico va en `Advanced`. Guía de 4 pasos antes del primer análisis.
- Resultado: probabilidad del pick (grande), expected XPM, P(Over)/P(Under)/P(Push),
  distribución con la línea marcada y Win/Loss/Push por conteo, "What KickEdge
  saw" en tarjetas (forma del kicker, ofensiva, defensa rival, contexto) con
  diferencias numéricas recientes vs temporada y sin adjetivos, las 82 entradas
  auditables, calidad de datos compacta (chips + "View details"), comparación de
  precio neutral (EV en desplegable), contexto (clima/mercado) y detalles técnicos.
- Kickoff en hora local del navegador ("Sunday, Oct 4 — 11:00 AM"); UTC en provenance.
- Errores con sugerencias: `GAME_NOT_FOUND` lista los próximos partidos de ambos
  equipos y se pueden elegir con un clic.
- Mientras analiza: botón "Analyzing…" deshabilitado (sin doble envío).
- La interfaz se sirve con `Cache-Control: no-cache` (el navegador revalida con ETag).

### Análisis recientes (`GET /api/analyses`, `GET /api/analyses/{id}`)

Se leen los `analysis.json` que 7B ya guardaba en `data/current/analyses/<sha256>/`
(ignorado por Git). El id debe ser 64 hex y la ruta resuelta debe quedar dentro
del directorio; no se aceptan rutas arbitrarias. Abrir uno solo lee el archivo y
lo muestra con el aviso "Shown as stored; nothing was re-run": no se llama al
motor ni a proveedores (test explícito). El motor ahora guarda también qué
contexto se pidió (`market_requested`, `weather_requested`) y los nombres de equipo.

### Lanzador (`start-kickedge.bat`)

Doble clic: se ubica en la carpeta del proyecto, comprueba `.venv`, ejecuta
`python -m kickedge.web --open` y muestra "Press Ctrl+C to stop KickEdge.".
`--open` abre `http://127.0.0.1:8000` cuando `/healthz` responde. Si el puerto
ya lo usa KickEdge, solo abre el navegador; si lo usa otro programa, lo dice y
sale sin tocarlo. Sin administrador, servicios, registro ni arranque automático.
Finales de línea CRLF forzados en `.gitattributes`.

## QA (servidor local real, datos nflverse en vivo, Edge headless vía DevTools)

| Prueba | Resultado |
|---|---|
| A. Escritorio 1280×900: `rams eagles` → Enter, `mev` → Enter, Over 1.5, -333 | Rams @ Eagles, Harrison Mevis, **64.5 %**, expected 2.20, clima disponible, afiliación verificada |
| B. Alias/manual: Advanced `LAR`/`phi`, kicker escrito, línea 2, +120 | Resuelto a `2026_04_LA_PHI`, "Normalized LAR → LA", P(Push) 26.8 % |
| C. Historia corta | "Only 3 prior games this season; rolling-5 inputs are unavailable…" |
| D. Clima exterior | Lincoln Financial Field con pronóstico real (ver arriba) |
| E. Mercado sin `PARLAY_API_KEY` (segunda instancia, sin tocar `.env`) | Mercado "Unavailable", fallo no crítico, mismo 64.5 % |
| F. Móvil 390×844 | Mismo flujo completo; sin scroll horizontal; historial al final |
| G. Reabrir análisis reciente | Banner de análisis guardado; nada se volvió a ejecutar |
| Error | `LAR` vs `NYJ`: "No upcoming game found for that matchup" + 8 sugerencias; clic → partido seleccionado |
| Interior / retráctil | Vikings: "Indoor"; Texans (NRG): sin clima exterior |

Sin scroll horizontal en ninguna captura (escritorio y móvil).

## Verificación de regresión

- Fixture 7A (`examples/inference_demo_2024.json`, Over 2.5 +119): lambda
  `1.774292350651335`, P(Over) `0.2625051047104534`, cola `5.379582350402028e-08`,
  idénticos bit a bit (test explícito nuevo).
- Paridad histórica/actual de los 16 casos 2024 × 82 features: pasa dentro de la
  suite (se re-ejecutó porque cambiaron `sources.py` y `snapshot.py`).
- `model.joblib` SHA-256 `c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0`;
  metadata canónica `1365f870…6a32` (local y versionada); `contract.json`
  `a8030cbf…8879`; `release.json` sin cambios; alpha 0.1; refit 2016–2024; 82
  features en el mismo orden.
- `git diff 010b4c6` vacío en `kickedge/features`, `modeling`, `validation`,
  `inference`, `providers`, `transform.py`, `build.py`, `models/` y `render.yaml`.

## Tests

**619 aprobados: 547 previos + 72 nuevos**, 0 fallos, ningún test previo modificado.

- `tests/test_teams_venues.py` (42): aliases (LAR/lar/LA, JAX/JAC, WSH/WAS y más),
  nombres ambiguos, coherencia con `TEAM_MACRO`, catálogo de estadios completo,
  aliases y normalización de venues, nombre por encima de un id erróneo, techo del día.
- `tests/test_polish_current.py` (14): partidos futuros ordenados y resolubles,
  aliases en `resolve_target`, sugerencias, candidatos de kicker sin sustitución,
  estados de afiliación, clima exterior/domo/retráctil/fuera de ventana, motor
  con alias y roster, conflicto de roster, clima sin efecto en features ni predicción.
- `tests/test_web_polish.py` (13): `/api/games` (orden, futuro, nombres, códigos,
  reutilización del cache y refresh), `/api/games/{id}/kickers`, aliases por HTTP,
  `INVALID_TEAM`, sugerencias, `GAME_AMBIGUOUS`, `KICKER_TEAM_MISMATCH`, análisis
  recientes sin re-ejecución, ids y path traversal rechazados, regresión 7A,
  lanzador seguro y manejo del puerto ocupado.
- `tests/test_web_polish_frontend.py` (3): `index.html` + `app.js` reales en Edge
  headless: flujo completo con teclado (búsqueda, Escape, Enter, kicker, equipo,
  envío), fallback manual, banner de análisis guardado y sugerencias de error.

## Seguridad

Ids de partido y de análisis validados por patrón y confinados al directorio
permitido; sin lectura de archivos arbitrarios, sin URLs proporcionadas por el
usuario (las coordenadas vienen del archivo versionado), sin secretos en la
interfaz ni en JSON; `.env` y `data/` nunca se sirven; `PARLAY_API_KEY` solo en
servidor. Búsqueda de claves, tokens y rutas locales en archivos versionados: sin
hallazgos (solo el valor ficticio preexistente de `tests/test_parlay.py`).

## Limitaciones restantes

- La afiliación depende de los datos de jugadores de nflverse (actualización
  diaria); la participación real el día del partido no se verifica.
- Clima solo dentro de 16 días del kickoff; en techos retráctiles sin estado
  publicado no se muestra clima exterior.
- Un estadio nuevo o renombrado que no esté en `venues.json` deja el clima no
  disponible hasta añadirlo (con aviso, sin adivinar).
- El mercado sigue dependiendo de ParlayAPI y solo se pide de forma explícita.
- Una temporada de holdout ciego, supuesto Poisson e incertidumbre en la cola alta
  siguen siendo las limitaciones del modelo; no hay garantía de rendimiento futuro.
