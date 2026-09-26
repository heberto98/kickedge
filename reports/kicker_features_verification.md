# Verificación Fase 1

- Build de features: `18a2c65f746116405ec5`.
- Inputs preparados: `803e506961eff007e0f0`; histórico original: `c7300725b93c79971254`.
- Suite completa: **132 tests aprobados** (109 existentes + 23 nuevos), sin eliminar ni reducir pruebas.
- Repetición del build real: **8 archivos idénticos byte por byte**, incluidos Parquet,
  features congeladas, targets, manifiesto y log encadenado.
- Auditoría SQL independiente: coincidencia de **21 features × 6,083 filas**, con
  historial reconstruido desde labels originales, identidades y relojes cacheados;
  no se usaron las sumas del builder como valores esperados.
- Se preservaron las 6,083 claves y XPM targets originales y los flags de múltiples
  ejecutores. Hay 20 filas marcadas con múltiples placekickers. No se filtraron.
- Se verificó la cadena freeze/reveal de los 3,028 partidos y todos los hashes de
  artefactos. Cada reveal ocurre después del freeze y de la disponibilidad asumida.

## Pruebas temporales

Mutar XPM/XPA de G no cambia sus features; eliminar físicamente su resultado no
cambia su predicción ni su freeze; mutar un futuro no cambia el pasado; G sí
actualiza observaciones posteriores. Se verificaron ventanas exactas 3/5,
season-to-date, entrada desordenada, empates de kickoff, historial global al cambiar
de equipo, reinicio anual, primeros partidos, 0/0, labels inválidos, resultados aún
no disponibles y el corte conservador ante retrasos con horario de invierno.

La revisión de código no encontró defectos importantes ni leakage en los valores.
Detectó un motivo de NULL que usaba validez de toda la temporada para una ventana
rolling. Se reprodujo con test fallido y se corrigió para usar los contribuyentes
de cada feature. La regresión quedó incluida en la suite.

## Cinco filas contrastadas

| Caso | Fila | Historia previa comprobada | Target XPM |
|---|---|---|---:|
| Primera observación de temporada | 2015_01_PIT_NE / NE / Stephen Gostkowski | n=0; acumulados 0; tasas y rolling NULL | 4 |
| Historial largo | 2021_22_LA_CIN / LA / Matt Gay | n=20; XPA=58, XPM=57; últimos 3: 9/9 | 2 |
| Cambio de equipo | 2015_07_NO_IND / NO / Kai Forbath | conserva 2015_01_MIA_WAS con WAS; n=1; XPA/XPM=1/1 | 3 |
| XPM=0 | 2015_04_NYG_BUF / BUF / Jordan Gay | 3 observaciones previas 0/0; sumas 0; conversión NULL | 0 |
| Múltiples placekickers | 2017_07_DAL_SF / DAL / Dan Bailey | n=5; XPA/XPM=14/14; flag múltiple conservado | 2 |

Estas cinco filas también forman parte de la comparación numérica independiente
de toda la población. La procedencia por partido se detalla en
`reports/kicker_features_phase1.json`. Primera observación no implica rookie.

## Alcance de la conclusión

Las **6,083 filas son técnicamente reconstruibles** bajo el replay +24 h autorizado.
**0 verificadas temporalmente y 0 aprobadas para entrenamiento final**. Los tests
demuestran ausencia de target/future leakage en el cálculo; no demuestran cuándo
se publicaron las versiones históricas descargadas retrospectivamente.
La Fase 1 está completa como builder y validación experimental. No se inició Fase 2.
