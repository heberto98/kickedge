# Validación breve de Fase 2

- Inputs: `33a2e40dac8e5844655f`; build: `3ebe56f85f679fe7352b`.
- 6,083 filas kicker-game; 40 features nuevas (20 ofensiva, 20 defensa rival).
- 5,535 filas elegibles para entrenamiento conjunto; 548 de 2015 quedan como
  reserva histórica por la regla ya existente de Fase 1.
- Cobertura de las 40 columnas: **83.98%**. Los conteos de juegos tienen 100%.
- Por columna, promedios/tasas season-to-date: 354 NULL por lado, salvo red zone
  (357 ofensiva y 358 defensa). Rolling 3: 1,063 NULL; rolling 5: 1,771 NULL.
- En todas las columnas: 13,452 NULL por ausencia de historial, 25,512 por ventana
  insuficiente y 7 por denominador cero. Ninguno por métrica fuente faltante.

| Caso | Partido / equipo del kicker | Historial previo relevante |
|---|---|---|
| Ofensiva fuerte | 2015_06_ARI_PIT / ARI | 5 partidos, 38.0 puntos por juego; EPA/play 0.1883 |
| Defensa permisiva | 2020_07_DAL_WAS / WAS | Rival DAL: 6 partidos, 36.33 puntos permitidos por juego; EPA permitido/play 0.1556 |
| Early-season | 2015_01_PIT_NE / NE | 0 partidos previos en ambos lados; promedios/tasas NULL |

Las filas de ejemplo de 2015 describen la reserva histórica y no son elegibles
para entrenamiento. Conteos completos y ejemplos en `team_features_phase2.json`.

**Pruebas:** 161 tests aprobados (147 previos + 14 de Fase 2). Cubren mutaciones de
puntos/TD/EPA del objetivo, futuro, borrado físico de resultado objetivo, ventanas
3/5, season-to-date desplazado, bye, reset, rival correcto, pooling de tasas,
source SQL, NULLs y determinismo. Comparación SQL independiente sobre las 6,083
filas; todas las columnas originales de Fase 1 permanecen exactamente iguales.
La repetición del build real conserva los ocho archivos byte por byte.

Definiciones y límites en `docs/team_features_phase2.md`. No hay datos nuevos,
modelo entrenado, cambios a expected_kicker ni trabajo de Fase 3. El dataset es
apto para entrenamiento histórico bajo `event-context-v1`, condicionado a
participación observada y utilizando la selección de 61 predictores del contrato.
