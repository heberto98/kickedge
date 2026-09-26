# KickEdge — núcleo histórico

Dataset local **2015–2025**, temporada regular y playoffs, en Python + DuckDB/Parquet.
La unidad del label es `(game_id, team, player_id)`; XPM y XPA requieren acuerdo
entre player stats y el conteo PBP. **La población es observada después del partido**,
no una lista de titulares conocidos antes del kickoff. Incluye ceros demostrables.

No contiene entrenamiento, predicciones, features, interfaz, odds procesadas ni clima.

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
Antes de features o ML falta definir y reconstruir una población prepartido as-of.
