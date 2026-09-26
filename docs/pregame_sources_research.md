# Investigación de fuentes y decisiones de integración

## Fuentes empleadas

| Fuente | Cobertura inspeccionada | Tiempo disponible | Uso y límite |
| --- | --- | --- | --- |
| nflverse PBP ya congelado | 2015–2025 | Fecha/hora del partido, no captura histórica del archivo | Identidad PAT/FG en juegos ANTERIORES, revelada con demora de 24h; target solo después del freeze para evaluación |
| nflverse player stats reconciliado | 2015–2025 | Archivo descargado retrospectivamente | Únicamente outcomes del esperado después de congelar; no construye identidad |
| nflverse schedules | 2015–2025 | Gameday/gametime Eastern | Universo e inicio programado; no prueba de versiones de calendario pregame |
| nflverse players | Crosswalk de IDs | Versión actual congelada | Identidad estática; no estado de roster actual |
| nflverse depth_charts | 2015–2025, 11 activos descargados | dt en 2025; sin captura en 2015–2024 | 2025 aporta rol as-of; anteriores excluidos de selección. No prueban disponibilidad médica |
| nflverse weekly_rosters | 2015–2025, 11 activos descargados | Semana, sin publicación/captura por fila | Inventario y evaluación metodológica; no se usa una fila semanal como roster confirmado a T−60 |
| nflverse injuries | 2015–2025, 11 activos descargados | date_modified en 2015–2024; ausente en 2025 | Actualización del dato no demuestra publicación. Se conserva y se excluye de la asignación temporal verificada |
| Artículos oficiales de clubes | Casos dirigidos 2019, 2021, 2024, 2025 | NewsArticle.datePublished/dateModified con zona UTC | 11 páginas cacheadas; 15 claims aceptados/rechazados por contenido y tiempo. No es cobertura exhaustiva de NFL |
| Packers: inactivos Week 6 y 7 | Dos juegos de 2025 | Metadatos editoriales | Dos páginas adicionales exclusivamente para auditoría de errores; no se pasan al selector |

Los 33 activos adicionales de nflverse se guardan con SHA-256, esquema, conteos y descarga. El inventario exacto está en `reports/pregame_sources.md` y el `source_inventory.json` del build. Los manifiestos congelados conservan URLs, hashes y archivos originales locales. Las fuentes oficiales se anotan en `audits/pregame_claims.json`; los enlaces externos de auditoría están separados en `audits/pregame_evaluation_sources.json`.

## Hallazgos que impiden afirmar temporalidad perfecta

Los [rosters semanales](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html) representan una semana, pero no incluyen cuándo se observó/publicó cada estado. Desplazar arbitrariamente una semana no reconstruye transacciones intermedias ni garantiza ausencia de correcciones retrospectivas.

El [calendario de nflverse](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) explica el cambio de depth charts en 2025 y las actualizaciones de PBP. El snapshot de depth 2025 descargado contiene 554,215 filas y 221 instantes distintos. Los IDs pueden remapearse posteriormente: se trata como normalización estática, no como nueva información de roster.

La documentación de lesiones aún indica una carencia de 2025, pero el activo descargado existe: 6,068 filas, 42 para K, sin `date_modified`. No se dedujo su disponibilidad histórica de que hoy exista. Los años anteriores incluyen entre 15 y 47 filas de K cada uno y un tiempo de actualización; no equivalen a una lista exhaustiva de sanos/inactivos. El [diccionario](https://nflreadr.nflverse.com/articles/dictionary_injuries.html) define el campo temporal y el [código de actualización](https://raw.githubusercontent.com/nflverse/nflverse-rosters/main/exec/update-injuries.R) señala al proveedor NFL API.

## Fuentes adicionales evaluadas

| Fuente | Aporte | Cobertura/tiempo comprobados | Decisión |
| --- | --- | --- | --- |
| NFL.com Transactions | Altas, bajas, reserva y otros movimientos | Se inspeccionaron páginas mensuales 2015, 2024 y 2025; fechas civiles, paginación y sin publicación por registro | Potencial para una siguiente integración sistemática. No se recorrieron todas las temporadas ni se convirtió una página parcial en feed completo; no fundamenta el selector actual |
| nflreadr trades | Operaciones de intercambio | Tabla mantenida con fecha de trade | Insuficiente para cortes, IR, firmas y elevaciones; no cubre el ciclo completo del kicker |
| Roster final de offseason / preseason | Arranque de Week 1 | No se verificó un archivo uniforme con captura pregame 2015–2025 en las fuentes integradas | Pendiente. No arrastrar el titular de enero sin demostrar continuidad de roster |
| Archivos web y boletines oficiales | Versiones históricas y confirmaciones gameday | Recuperación caso por caso; cobertura uniforme no demostrada | Alternativa a evaluar; no se asume una copia archivada inexistente ni se evita una restricción de acceso |

Referencias primarias para explorar transacciones: [archivo NFL 2015](https://www.nfl.com/transactions/league/signings/2015/9), [archivo NFL 2024](https://www.nfl.com/transactions/league/signings/2024/9), [archivo NFL 2025](https://www.nfl.com/transactions/league/signings/2025/9), [nflreadr load_trades](https://nflreadr.nflverse.com/reference/load_trades.html). Las páginas parciales no permiten afirmar “no hubo transacción”.

No se implementó scraping masivo dependiente de HTML ni endpoints privados. La evidencia oficial puntual tiene parser que falla si no encuentra exactamente el artículo esperado y exige revisión si las anclas del claim cambian. La continuidad histórica puede ejecutarse offline sin esas páginas, pero pierde sus dos confirmaciones oficiales.
