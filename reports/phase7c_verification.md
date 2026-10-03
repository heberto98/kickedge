# Fase 7C: verificación

Fecha: 2026-10-03. Base: `811d42e` (7B).

## Tests

**547 aprobados: 522 previos + 25 nuevos**, 0 fallos
(`.venv/Scripts/python.exe -m pytest -q`, 77 s). Ningún test previo modificado.

- `tests/test_web_api.py` (20): healthz/readyz/model info, análisis manual igual
  al motor directo, sin llamada de mercado por defecto, línea/odds/campos
  inválidos (422 sin eco), kicker inexistente (404), partido inexistente (404),
  partido ambiguo (409), fuente NFL caída (503), fallo opcional de proveedor con
  resultado manual intacto y límite de mercado, rate limit (429), límite de
  cuerpo (413), sin secretos ni rutas internas (`/docs`, `/.env`, artifact),
  bootstrap del artifact y fallo cerrado ante artifact local o versionado
  adulterado, artifact versionado = release.
- `tests/test_web_frontend.py` (5): página y formulario con labels, sin scripts
  inline/terceros ni copy de apuestas; `app.js` real en Edge headless renderiza
  probabilidad, distribución, 82 entradas, data quality, warnings, contexto,
  push y base condicional en línea entera, mercado no disponible, tabla de
  mercado y estado de error.

Durante QA se encontró que las listas de "What KickEdge saw" mostraban
`[object HTMLElement]` (aplanado de un solo nivel). Se corrigió y se añadió una
aserción que falla sin el arreglo y pasa con él.

## Integridad del modelo

- `model.joblib` SHA-256 `c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0`
  (local, versionado y release idénticos); metadata canónica idéntica en ambas
  copias; `contract.json` `a8030cbf…8879` sin cambios.
- `git diff 811d42e` vacío en `kickedge/features`, `modeling`, `validation`,
  `inference`, `providers`, `transform.py`, `build.py`.
- Loader 7A: alpha 0.1, refit 2016–2024, 82 features en orden. Sin retrain,
  recalibración ni cambios de features.

## Portabilidad del artifact

Copia limpia con sólo los archivos versionados (sin `data/`, sin `model.joblib`
local): `/readyz` 200, artifact instalado con SHA-256 `c2f8f5ff…f0d0`, y la
fixture 7A da lambda `1.774292350651335` y P(Over 2.5) `0.2625051047104534`,
idénticos bit a bit al entorno original y al valor registrado en 7A.

## Demo end-to-end (2026-10-03 ~08:32 UTC, datos live)

Formulario web en Edge headless → `POST /api/analyze` → `2026_04_GB_TB`
(kickoff 2026-10-04 17:00 UTC) → cache nflverse 2026 → 82 features → modelo
congelado → resultado renderizado. Chase McLaughlin (00-0035358), TB (local) vs GB,
Over 2.5 a +115 / Under -145 (precios **introducidos manualmente, hipotéticos**):
KickEdge 33.5 %, expected XPM 2.04, último partido usado `2026_03_MIN_TB`,
18 entradas NULL resueltas por el imputer. Mercado: ParlayAPI respondió en la
consulta API con contexto de 6 books (p. ej. FanDuel spread +3.5, total 39.5,
ML +150/-178); el resultado no lo usa como predictor. Clima: no disponible
(sin coordenadas del venue). Error de kicker inexistente y línea 2.25 verificados
en la UI.

## QA visual

Escritorio 1280×900 y móvil 390×844 (Edge headless vía DevTools Protocol):
inicio, resultado completo, warnings, error de API y error de campo. Sin scroll
horizontal en ningún caso. Corregido: alineación del selector Over/Under,
placeholder truncado en móvil, texto de la distribución y formato de fecha.

## Seguridad

Búsqueda en archivos versionados de API keys, tokens, rutas absolutas locales y
`.env`: sin hallazgos (sólo un valor ficticio preexistente en
`tests/test_parlay.py`). `.env`, `data/` y caches siguen ignorados.

## Deployment

Listo para Render (`render.yaml`). No se desplegó: no hay credenciales ni CLI de
Render en este entorno. Paso manual restante: en Render, "New → Blueprint",
conectar `heberto98/kickedge` (rama main) y, si se quiere mercado, fijar
`PARLAY_API_KEY` en el dashboard.
