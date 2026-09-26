# Verificación final de la etapa expected kicker

Build secuencial: `c721eeb55acb4eb9cb73`. Build de evidencia inicial: `3ed70bf1799e0a1de5c3`. Histórico original: `c7300725b93c79971254`.

- Tests: **91 passed**, incluidos los 37 originales y 54 nuevos. Última ejecución: `python -m pytest -q`.
- Auditoría manual: **13/13 casos**.
- Integridad histórica: **19/19 controles**, cero violaciones. `python -m kickedge validate` reconstruyó hashes Parquet y quality report idénticos.
- Controles del build pregame: **10/10 PASS**.
- Todos los artefactos del build secuencial verificados por SHA-256.
- Repetición con source lock: **10/10 artefactos deterministas idénticos**: cadena de eventos, identidades A/B/C y labels JSON/Parquet A/B/C. Los metadatos de ejecución pueden variar; las decisiones no.
- Prueba crítica: eliminar físicamente el archivo de resultados del target no cambia su decisión; nunca se abre ese archivo antes de congelarla.
- Otra prueba ejecuta el builder de identidades con outcomes inexistentes y un evaluator que falla si se invoca. Pasa.
- Pruebas de cutoff UTC/DST, fuentes futuras, revisiones posteriores, estados UNKNOWN, conflictos, ceros, discrepancias, reset anual, bye/playoffs y revelación de hechos reales para juegos futuros.

## Hashes de las identidades congeladas

- A: `cc509c793bf04d8e1d549cd900e3444ec1075ea7598e0fe8878c938a8bc3836d`
- B: `84f37d485016e34ce051909cb12d6caf7859edffd3f25b3ec995d1717173c8b7`
- C: `77d42060b0e141d6983f65e187ab40ed0791c9975c5c7f7d0dab84c5576ea7b5`

Hash final de la cadena: `302d3187aa646bbe516dda2497fd1b88ba09aa6290cd853b7a484cc566c4cef1`.

## Estado Git

`main` y la referencia local `origin/main` permanecen en `b5db8cc`. Los cinco commits publicados no se alteraron. No se ejecutó commit, push, reset ni cambio de rama. El índice sigue vacío; README modificado y archivos nuevos sin staging. Datos, caches, oracle, temporales y entorno virtual siguen ignorados.

## Correcciones al retomar

Se corrigió la consulta del nombre/ID en la tabla transformada (`player_id`, no `gsis_id`) y el alias SQL de dos fixtures DST. Se reforzó la exclusión de inactivos y el uso del máximo publicación/modificación de artículos. La evaluación inicial se separó del proceso secuencial y el oracle se prepara en otro comando. Ninguna de estas correcciones se utilizó para ajustar identidades a los resultados del target; las decisiones secuenciales y sus errores se conservan.

## Estado de elegibilidad

Todas las filas secuenciales A/B/C mantienen `eligible_for_pregame_training=false`, pendientes de revisión de política. C sirve como referencia experimental de continuidad. No se ejecutaron features del modelo XPM, entrenamiento, odds, clima, frontend ni deployment.
