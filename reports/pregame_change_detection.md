# Detección de cambios — evaluación local enfocada

Baseline C: `c721eeb55acb4eb9cb73`. Experimento: `e039ad65c95358716bc6`.
Reproducción: `.venv/Scripts/python.exe -m kickedge.pregame compare-changes`.
Reutiliza identidades, evidencia y oracle guardados; no descarga ni reconstruye
el pipeline histórico. Los punteros de los experimentos anteriores se conservan.

## Reglas fijadas antes de medir

Antes de continuidad y freeze: una baja oficial (corte, IR, OUT o inactivo)
bloquea al histórico. Una asignación oficial explícita permite reemplazo; una
baja más un único sustituto en roster activo permite inferencia. Contradicciones
o varios candidatos producen AMBIGUOUS; baja sin sustituto suficiente, UNKNOWN.
Un nuevo candidato de roster sin asignación clara produce AMBIGUOUS.

En snapshots fechados, pasar de histórico rank 1 a un único nuevo rank 1 permite
reemplazo INFERRED; añadir otro kicker sin cambio claro produce AMBIGUOUS.
Se comparan snapshots admisibles del partido previo y actual. Ausencia de PK
en un snapshot no demuestra corte. Sin señal se conserva continuidad. Week 1
permanece UNKNOWN. No se infiere salud ni disponibilidad desde un depth chart.

## Resultado sin cambiar el denominador

| Métrica | Baseline | Con detector |
|---|---:|---:|
| Cambios evaluables originales | 11/139 (7.91%) | 12/139 (8.63%) |
| Cambios con único ejecutor actual | 2/130 (1.54%) | 3/130 (2.31%) |
| Errores en los 139 | 128 | 124 |
| Abstenciones en los 139 | 0 | 3 |
| Identidades / 6,056 | 4,992 (82.43%) | 5,002 (82.60%) |
| Accuracy global entre identificados evaluables | 4,806/4,934 (97.41%) | 4,818/4,944 (97.45%) |
| Errores globales | 128 | 126 |

Hay señales en 6/139 casos: dos ya acertados, uno corregido y tres abstenciones.
La accuracy condicional en cambios es 12/136 (8.82%); las tres abstenciones no
son aciertos. Fuera del grupo fijo se recuperan 12 identidades correctas y se
introducen 2 errores desde antiguas abstenciones. De los casos normales antes
correctos, ninguno pasa a error y uno pasa a AMBIGUOUS. Efecto neto global:
12 aciertos adicionales y 2 errores menos, con 10 identidades más.

Las 19 transiciones individuales y las métricas están en
`reports/pregame_change_detection.json`; evidencia y log encadenado en
`data/pregame/changes/e039ad65c95358716bc6/`. Se congelan las decisiones antes
de revelar cada resultado. No se usa el resultado objetivo para seleccionar.

## Límite y veredicto

Se reutilizaron snapshots 2025 y avisos oficiales ya descargados, incluidos dos
artículos de Packers con baja/asignación pre-cutoff. Esos artículos proceden de
auditorías de errores previas: desarrollo retrospectivo, no validación independiente.
Roster/depth históricos sin publicación demostrada y lesiones sin disponibilidad
pública verificable permanecen excluidos. No existe un feed histórico completo
de cortes, IR, elevaciones o inactivos en el caché actual. No se investigaron fuentes
nuevas ni se ajustaron reglas individuales después de ver estos resultados.

**C — NO RESUELTO.** La reducción de 128 a 124 errores antiguos es insuficiente;
se necesita una fuente histórica adicional con disponibilidad verificable antes
de admitir esta población. Una opción futura es un archivo oficial fechado de
transacciones e inactivos; no se integra en esta ejecución. Todas las filas
siguen fuera de entrenamiento. Sin commit ni push.

Validación final: **109 tests aprobados** (91 existentes + 18 nuevos), incluyendo
eliminación física del outcome objetivo, cutoff, contradicciones y verificación
del log encadenado del replay real.
