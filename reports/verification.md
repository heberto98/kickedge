# Verificación de entrega

Fecha UTC: 2026-09-26. Build validado para GitHub: `c7300725b93c79971254`.
Entorno: Windows, Python 3.12.14, DuckDB 1.5.5, pytest 9.1.1.

| Ejecución | Resultado observado |
| --- | --- |
| `python -m pytest -q` | 37 passed, 0 failed, 0 skipped |
| `python -m kickedge build` | 6,083 labels; 122 IDs; 714 ceros; 19 controles de integridad con 0 violaciones |
| `python -m kickedge audit` | 8 partidos, 15 labels seleccionados; expectativas verificadas |
| `python -m kickedge ingest` (segunda ejecución) | Los 24 originales se verificaron y reutilizaron desde caché |
| `python -m kickedge validate` | Mismo build ID, hashes idénticos en los 9 Parquet y mismo quality.json |
| `python -m kickedge inspect --game 2024_02_NYG_WAS --team NYG --player 00-0026858` | Graham Gano: XPA=0, XPM=0, agreed; evidencia de participación y fuentes disponibles |

La suite cubre ceros explícitos, ausencia de player stats, participación no
confirmada, cobertura inconsistente, discrepancias, bloqueos, fallos, anulaciones,
2PT válidos con penalización, TD ofensivos/defensivos/special teams, overtime,
sustitutos no-K, duplicados, configuración de tipos de partido, IDs de partido
desconocidos, corrupción de originales y hashes de artefactos. Incluye expectativas
fijas de los ocho partidos reales auditados.

El detalle de población, distribución, exclusiones y faltantes está en
`quality.md`; las jugadas revisadas y fuentes de contexto están en `manual_audit.md`
y `manual_audit.json`. No se ejecutó entrenamiento ni generación de features.

## Preparación del repositorio

Se añadieron exclusiones de datos, entornos, cachés, credenciales, archivos del IDE
y temporales. Los reportes pequeños se conservaron como evidencia; los datasets
se reconstruyen mediante los scripts. El README se adaptó a una clonación nueva.

Se normalizaron a LF los finales de línea mezclados de `kickedge/transform.py` y se
comprobó que su árbol sintáctico no cambió. Esta modificación de formato cambia
el hash del código y, por tanto, el build ID respecto al snapshot anterior
`9aac64196c9368bde1ed`. Se repitieron construcción, auditoría y validación: se
mantienen las 6,083 observaciones, 122 jugadores y 714 ceros, con 19 controles sin
violaciones y reproducción idéntica de los nueve Parquet.

Los primeros cuatro commits se comprobaron también desde copias aisladas de sus
árboles, verificando que sus módulos pudieran importarse con las dependencias
disponibles en cada etapa. No se cambió la lógica de labels ni de población.
