# Fase 7B: snapshot pregame actual -> motor 7A congelado

`python -m kickedge analyze --kicker "Chase McLaughlin" --team TB --opponent GB --season 2026 --week 4 --line 2.5 --side over --odds +115 --over-odds +115 --under-odds -145 [--json] [--refresh-data] [--no-market] [--no-weather] [--game-id ID] [--bookmaker KEY]`

No entrena, no recalibra, no cambia alpha ni features. El GLM de Fase 5 y el
motor 7A (`kickedge.inference`) se usan sin modificaciones.

## Arquitectura

`kickedge/current/`:

- `sources.py`: cache verificado de nflverse (`data/cache/current/<season>`,
  ignorado). TTL 6 h; `--refresh-data` fuerza descarga. Solo URLs aprobadas de
  `kickedge.ingest.sources`. Hash SHA-256 de originales y del bundle derivado
  (clave = hashes de fuentes + codigo de preprocesado + version DuckDB). Reutiliza
  `transform`, `create_labels` y `team_prepare.aggregate` sobre partidos con
  `END GAME` no borrado. Fuente critica faltante o corrupta -> error; nunca se
  fabrica historia de "primer partido".
- `snapshot.py`: resolucion de partido/kicker y construccion del snapshot con los
  tres builders historicos (`KickerFeatureBuilder`, `TeamFeatureBuilder`,
  `GameContextBuilder`). Valida exactamente 82 features en el orden de
  `predictor_columns()` y el `FeatureSnapshot` de 7A.
- `optional.py`: ParlayAPI (props XPM + mercado general) y Open-Meteo, una
  peticion por endpoint, timeout 10 s, sin reintentos. Nunca entran al frame de 82.
- `engine.py`: `analyze_current_prop` -> fuentes -> partido -> kicker -> snapshot
  -> contexto opcional -> cuota (manual o automatica unica) -> `inference.analyze`.
  Persiste `snapshot.json`, `provenance.json`, `analysis.json` en
  `data/current/analyses/<sha256>/` (ignorado, sin sobrescritura).
- `cli.py`: subcomando `analyze`; errores sin eco de entradas ni traceback.

## Reglas temporales

- Cutoff = min(ahora, kickoff programado - 60 min), el mismo horizonte de training.
- Solo partidos de la temporada objetivo, completados, con kickoff real y
  ultimo evento anteriores al cutoff y con compuerta conservadora
  `max(kickoff+24h, ultimo evento) <= cutoff`. El partido objetivo y futuros se
  excluyen antes de leer resultados.
- Captura de fuente posterior al cutoff -> error. Fuente > 6 h -> warning.

## Identidad

- Partido: identidad explicita en el schedule (equipos, temporada, opcional
  semana/game-id), solo futuro; ambiguo o inexistente -> error.
- Kicker: ID estable o nombre normalizado, posicion K/PK o historial previo
  valido; ambiguo -> error. Afiliacion actual al equipo **no verificada**
  (warning explicito).

## Opcionales

- Fallo de ParlayAPI/Open-Meteo -> `source_failures` (no critico) + warning, y la
  cuota manual sigue funcionando. Cuota automatica exige evento, jugador y linea
  exactos y sportsbook; DFS es informativo; varias candidatas -> pedir manual.
- Clima requiere techo abierto y coordenadas del venue; domos suprimen clima.
  El schedule de nflverse no trae coordenadas, por lo que hoy el clima queda
  `available=false` con warning.

## Paridad historica

`scripts/verify_current_parity.py` reconstruye 16 casos reales de 2024 por la ruta
actual y compara las 82 features con la materializacion congelada de Fase 4
(NULL/tipos exactos, tolerancia numerica 1e-10): primer partido home/away,
historia corta, rolling 3/5, bye, semana corta, playoffs. Test:
`tests/test_current_parity.py`.
