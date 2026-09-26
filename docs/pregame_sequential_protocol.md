# Protocolo secuencial v1 — fijado antes de ejecutar la comparación

Se conserva el estudio inicial: 571 identidades, 16 discrepancias, snapshots de 2025 y dos casos oficiales de 2024. Estas observaciones ya se vieron; 2025 NO es validación independiente. El usuario autorizó evaluar continuidad histórica y políticas experimentales. No se corregirán identidades caso por caso después de ver el resultado objetivo.

## Reglas fijadas

- Procesar cutoffs cronológicamente. Congelar las dos decisiones del partido antes de permitir la lectura de su archivo de resultados.
- Un partido anterior entra al estado a kickoff programado + 24 horas. Es una hipótesis conservadora sobre conocimiento del hecho deportivo, no un timestamp de publicación ni una garantía de que las revisiones del proveedor ya existían. Ningún resultado del propio partido puede entrar al estado.
- Resetear al cambiar de temporada. No arrastrar automáticamente el último kicker del año anterior a Week 1.
- Exigir dos partidos anteriores consecutivos del equipo con un único ejecutor de PAT/FG, y el mismo jugador en ambos. La antigüedad máxima y la separación entre partidos es 21 días: admite bye weeks y descansos de playoffs, sin continuidad ilimitada.
- Un partido previo sin PAT/FG interrumpe la evidencia consecutiva. No se rellena con la persona que patee después. Un partido previo con múltiples ejecutores produce AMBIGUOUS.
- Una baja oficial aceptada veta al candidato. Un rol pregame reciente que identifica a otro jugador produce AMBIGUOUS en las inferencias. Una confirmación oficial explícita tiene prioridad sobre la continuidad.
- El historial revela todos los hechos anteriores, también cuando la predicción de ese partido fue UNKNOWN, ambigua o errónea. No se aprende la identidad a partir de la predicción anterior.

## Políticas comparadas

| Política | Regla | Disponibilidad actual |
| --- | --- | --- |
| A | VERIFIED/STRONG del estudio de fuentes fechadas | Documentada bajo los límites de las fuentes oficiales |
| B | A + continuidad de dos partidos y un rol pregame fresco coincidente | Corroboración del rol; salud/roster completo NO verificados |
| C | A + continuidad de dos partidos, incluso sin corroboración actual | Experimental: pertenencia y disponibilidad actuales son hipótesis, no hechos comprobados |

C no convierte ausencia de noticias en ausencia de lesiones, cortes o reemplazos. `transaction_feed_complete=false` e `injury_feed_complete=false` lo hacen explícito. B tampoco recibe categoría STRONG solo por concordancia de una fuente de rol con historia deportiva. Sus casos adicionales siguen siendo INFERRED.

Las categorías describen evidencia. La pertenencia a una política se informa aparte; no se usa accuracy para asignar porcentajes de confianza a filas individuales.

## Evaluación prevista

Desarrollo: 2015–2020. Evaluación temporal descriptiva: 2021–2024, con advertencia de que algunos casos auditados ya eran conocidos. 2025: período previamente inspeccionado. No hay período completamente intacto ni prueba fuera de muestra de un algoritmo de ML.

Para A/B/C se medirán cobertura, categorías, discrepancias, exactitud de pertenencia y conjunto exacto, años, Week 1/resto, cambios frente al ejecutor anterior, múltiples kickers, XPA/XPM=0, ausencia de evidencia de patadas y labels faltantes. Se conservarán todos los errores. No se elegirán umbrales maximizando aciertos del mismo período.

El dataset conservará `eligible_for_pregame_training=false` mientras se comparan políticas. La recomendación final requerirá revisión del usuario; no se ejecutará entrenamiento.
