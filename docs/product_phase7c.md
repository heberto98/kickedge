# Fase 7C: producto web, API y deployment

KickEdge analiza un pick XPM que el usuario ya está considerando. No genera,
ordena ni recomienda apuestas, ni sugiere stake.

## Arquitectura

Un único servicio Python (FastAPI + uvicorn) que sirve una interfaz estática
(HTML, CSS, JS vanilla, sin frameworks ni CDNs) y una API JSON. Es una capa
delgada: `kickedge/web/app.py` valida la entrada y llama a
`kickedge.current.engine.analyze_current_prop` (7B), que a su vez usa
`kickedge.inference.analyze` (7A). La web no recalcula features, distribución,
Over/Under/Push, implied/no-vig, diferencia ni EV.

Se eligió FastAPI por validación declarativa (pydantic), servidor ASGI de
producción y cero infraestructura adicional. Jinja2 no hace falta: la página es
estática y el JS construye el resultado con `textContent` (sin `innerHTML`).

Único cambio fuera de `kickedge/web`: `engine.py` añade al resultado
`features` (las 82 entradas del snapshot ya construido) para mostrarlas.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/healthz` | `{"status":"ok"}` sin I/O. |
| GET | `/readyz` | Instala/verifica el artifact (SHA-256, metadata, contrato, versiones, estructura). 503 si falla. No descarga datos NFL. |
| GET | `/api/model` | Tipo, versión, alpha, periodo, 82 features en orden, hash, validación ciega 2025 PASS. Sin rutas locales. |
| POST | `/api/analyze` | Pick manual → análisis completo. |
| GET | `/`, `/about`, `/static/*` | Interfaz. |

`/docs`, `/openapi.json` están desactivados.

`POST /api/analyze` (campos extra rechazados):

```json
{"kicker":"Chase McLaughlin","team":"TB","opponent":"GB","season":2026,"week":4,
 "game_id":null,"line":2.5,"side":"over","odds":115,"over_odds":115,"under_odds":-145,
 "refresh_data":false,"include_weather":true,"include_market":false}
```

Errores: `{"error":{"code","message"}}`, sin eco de valores ni traceback.

| Código | HTTP |
|---|---|
| INVALID_LINE, INVALID_ODDS, INVALID_REQUEST | 422 |
| GAME_NOT_FOUND, KICKER_NOT_FOUND | 404 |
| GAME_AMBIGUOUS, KICKER_AMBIGUOUS, STALE_DATA, GAME_STARTED | 409 |
| RATE_LIMITED | 429 |
| REQUEST_TOO_LARGE / LENGTH_REQUIRED | 413 / 411 |
| NFL_SOURCE_UNAVAILABLE, MODEL_NOT_READY | 503 |
| INTERNAL_ERROR | 500 |

## Interfaz

Orden: (1) probabilidad del pick del usuario, (2) expected XPM y P(Over)/P(Under)/
P(Push si la línea es entera), (3) distribución 0–4 y 5+ en barras CSS con
`aria-label` y tabla 0–12 + cola, (4) "What KickEdge saw": datos seleccionados
del snapshot por kicker/ofensiva/defensa rival/contexto, y desplegable con las 82
entradas (NULL indicado como resuelto por el imputer congelado), (5) data quality
con estados Verified/Available/Warning/Unavailable/Not verified, notas y
warnings reales, (6) market comparison: odds, implied, probabilidad KickEdge
(condicional a no-push en líneas enteras), diferencia en pp, fair odds; con ambos
lados, no-vig, overround y diferencia vs no-vig. EV queda en un desplegable
"Mathematical price comparison" con aviso de no-recomendación. Contexto de clima
y mercado (spread, total, moneyline por book) etiquetado
"Context only — not currently used by the probability model". "Data details"
muestra timestamps, cutoff, último partido, fuentes con fetched_at y hash,
versión de schema/modelo y hashes de artifact y snapshot.

No se muestran contribuciones por feature: con imputación + indicadores +
estandarización, `beta_i * x_i` sería fácil de malinterpretar como causal; se
prefirió mostrar datos reales.

Estados de error con título y guía para cada código; validación en cliente con
mensaje junto al campo; botón deshabilitado y "Analyzing…" durante la consulta;
`aria-live`, labels reales, foco visible, navegación por teclado, sin hover
necesario, layout responsive (2 columnas → 1 en móvil, tablas con scroll
horizontal). Página "About the model" con método, validación y limitaciones.

## Proveedores opcionales

- Mercado: solo si el usuario marca "Include market context" (por defecto no;
  la prop manual nunca llama a ParlayAPI). Como máximo una consulta de mercado por
  minuto para todo el servicio; si se excede se omite con warning. Fallos →
  `source_failures` no críticos + warning; el análisis continúa.
- Clima: Open-Meteo solo si el venue tiene coordenadas y techo abierto. El
  schedule de nflverse no trae coordenadas, así que normalmente queda
  "Weather data unavailable" (no es un error).

## Seguridad

Validación estricta (pydantic `extra=forbid`, enteros estrictos, patrones para
kicker/equipos/game_id), límite de cuerpo 4 KB, 12 análisis/min por IP, CSP
`default-src 'self'` + `frame-ancestors 'none'`, `nosniff`, `no-referrer`,
`X-Frame-Options: DENY`. Sin shell, sin rutas ni URLs proporcionadas por el
usuario, sólo `kickedge/web/static` se sirve. `.env` y `data/` nunca se exponen;
`PARLAY_API_KEY` sólo se lee en servidor. Excepciones no controladas → 500
genérico, registrando sólo el tipo de excepción. Sin cuentas, base de datos,
analytics ni trackers.

## Cache y concurrencia

Se reutiliza el cache 7B (TTL 6 h, hashes verificados). Un `threading.Lock`
serializa la carga/descarga de fuentes; las escrituras son atómicas
(archivo temporal + rename) y los análisis se guardan en directorios por hash
de contenido. Pensado para un proceso uvicorn (un worker).

## Artifact del modelo

`models/phase5/model.joblib` + `metadata.json` se versionan en Git (26 KB y
47 KB; `.gitattributes` los marca binarios). `release.json` fija sus SHA-256.
`kickedge/web/artifact.py::ensure_model`:

1. Si `data/models/phase5` existe, se carga con el loader 7A (verificación
   completa). Nunca se reemplaza un artifact local que no verifica: falla cerrado.
2. Si no existe, verifica el artifact versionado contra `release.json`, lo copia
   atómicamente y lo carga con el mismo loader.
3. Cualquier hash distinto → `MODEL_NOT_READY`. No hay "latest", ni fitting.

No hay GitHub CLI en este equipo, por lo que no se creó un Release asset; el pin
por commit + SHA-256 cumple el mismo papel sin infraestructura adicional.

## Deployment (Render)

`render.yaml`: un Web Service Python 3.12.14, build
`pip install -r requirements.lock.txt && pip install --no-deps .`, start
`uvicorn kickedge.web.app:app --host 0.0.0.0 --port $PORT --proxy-headers`,
health check `/readyz`. Filesystem efímero soportado: artifact reinstalado desde
Git, cache nflverse recreado bajo demanda, análisis guardados no son necesarios.
Variable opcional: `PARLAY_API_KEY` (`sync: false`, se fija en el dashboard).
