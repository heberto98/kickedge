# Fase 1: historial personal del kicker

## Alcance y definición

Se procesan las filas kicker-game existentes, sin resolver identidades nuevas ni
filtrar silenciosamente casos raros. No se cambia el build histórico ni el sistema
pregame. Se materializan exclusivamente los 21 predictores del grupo
`kicker_pregame` de `kickedge/features/contract.json`.

Se compararon dos claves conceptuales: **global kicker** preserva experiencia y
forma personal al cambiar de equipo; **kicker+team** mide solo la experiencia con
ese equipo, pero reinicia innecesariamente la muestra del ejecutor. Conforme a la
instrucción del usuario, esta fase usa `(season, kicker_id)`, sin team en la clave.
El reinicio por temporada conserva el contrato previo: season-to-date, rolling y
recencia se limitan a esa temporada, incluyendo playoffs. No se llena Week 1 con
datos futuros ni se intenta reconstruir el titular.

## Orden y separación temporal

1. `prepare` verifica los hashes del snapshot histórico y PBP ya cacheado.
   Proyecta identidades sin conteos y particiona labels en archivos por partido.
   Esta preparación retrospectiva define la población, no construye features.
2. `build` ordena por inicio real UTC, luego game_id/team/kicker_id para desempates.
   El inicio proviene de `PBP.start_time`, convertido de Eastern con reglas DST.
   Se detiene ante horarios faltantes/ambiguos. Usa exclusivamente metadatos de
   reloj del partido objetivo, nunca sus conteos ni participación como predictores.
3. Cutoff = `min(inicio real, inicio programado) - 60 minutos`: un retraso no
   permite incorporar información posterior al corte original.
4. Antes de G, revela solo resultados de partidos previamente congelados cuya
   disponibilidad asumida no supera el cutoff. Construye y persiste las filas de
   ambos equipos/múltiples kickers de G antes de permitir revelar G.
5. El resultado de G se incorpora únicamente para partidos futuros. No se leen
   ni siquiera los bytes/hash de su archivo de resultados para construir su fila.
6. Tras congelar todas las features, se adjuntan XPM target y `source_label`, que
   conserva todos los campos/flags originales. El acceso predictivo se limita a
   `predictor_columns_phase_1`; no usar todo el Parquet como matriz del modelo.

El usuario autorizó **replay experimental +24 h**: disponibilidad asumida = máximo
entre inicio real +24 h y último evento del partido. Evita resultados de partidos
aún en curso, pero NO demuestra publicación histórica ni descarta revisiones
posteriores del proveedor. `features_temporally_verified=false` y
`eligible_for_final_training=false` en todas las filas, incluso sin historia.
`feature_sources_verified` describe las fuentes efectivamente utilizadas (true
vacuamente sin fuentes); no equivale a aprobación de la fila.

## Nulos, ventanas y calidad

- Sin observaciones previas disponibles: games/XPA/XPM acumulados = 0; tasas,
  medias, recencia y previous-game = NULL. Has-prior/3/5=false; low-sample=true.
- Low-sample significa menos de 5 observaciones previas, independientemente de
  calidad estadística. Los flags has-3/5 indican cantidad, no garantía de labels.
- Rolling 3/5 exige la ventana completa; antes de alcanzarla todas sus métricas
  son NULL. XPA/XPM last_N son sumas; XPM per-game last_N divide entre N.
- Conversión = suma XPM / suma XPA; sin intentos queda NULL. Una observación
  válida 0/0 se conserva: cuenta como partido y aporta cero a las sumas.
- Si un label previo es inutilizable, cuenta como observación pero sus conteos
  no se imputan. Acumulados derivados quedan NULL; una ventana que lo contiene
  queda NULL. No se salta ese partido buscando otro más antiguo para completarla.
- `days_since_last_game` son días fraccionarios desde el inicio del último partido
  previo hasta el **cutoff**, no hasta el inicio futuro del partido objetivo.
- Resultados aún no disponibles no se usan. `history_unavailable_before_cutoff`
  y los IDs pendientes distinguen esta situación de un verdadero debut.
- Se preservan múltiples ejecutores y flags originales. `unusual_substitution_flag`
  permanece NULL: no existe una regla validada para declararlo true/false.

## Reproducir y auditar

```powershell
.\.venv\Scripts\python.exe -m kickedge.features prepare
.\.venv\Scripts\python.exe -m kickedge.features build
.\.venv\Scripts\python.exe -m pytest -q
```

`prepare --base RUTA` fija un build histórico y `build --inputs RUTA` fija la
preparación. No hay red. Salidas ignoradas por Git:
`data/features/kicker_inputs/<id>/` y `data/features/kicker/<id>/`.
El build contiene features congeladas, log freeze/reveal encadenado por hashes,
contrato, dataset JSON/Parquet con targets y flags separados, resumen y hashes.
El ID depende de fuentes, contrato, código y versiones Python/DuckDB. Repetir
con los mismos inputs/runtime debe producir los mismos bytes. Los punteros
históricos y pregame originales no cambian.

`feature_provenance.history` enumera cada partido previo, equipo, inicio,
disponibilidad asumida, conteos y hash. Las listas last_3/last_5 indican sus
contribuyentes disponibles; si no están completas, el valor sigue siendo NULL.
El reporte `reports/kicker_features_phase1.*` incluye cobertura, nulos,
histograma y cinco ejemplos. Una primera observación no demuestra que sea rookie.

Fase 1 completa técnicamente significa features reconstruidas y pruebas de
no-leakage aprobadas **bajo este replay autorizado**; no significa población
aprobada para entrenamiento final ni disponibilidad histórica verificada.
