# Dataset futuro: una observación kicker-game

## Decisión metodológica

El producto recibe del usuario kicker, partido/matchup, línea XPM, lado Over/Under
y cuota. Después recopilará información prepartido, construirá features, estimará
una distribución de XPM y comparará su probabilidad con la implícita del mercado.
Mostrará tendencias, factores e incertidumbre; la decisión final será del usuario.
Estos componentes todavía no están implementados.

Para construir el dataset histórico, el kicker observado que participa puede
definir la observación **kicker-game**, con clave `(game_id, team, kicker_id)`.
Su identidad puede conocerse retrospectivamente: es una decisión de población,
no una feature prepartido. No se exige reconstruir `expected_kicker_id`.
El XPM del partido objetivo se usa exclusivamente como target.

**Para el partido G, toda feature debe usar exclusivamente información disponible
ANTES del kickoff y como máximo en el cutoff de G.** Se conserva la convención
T−60 minutos como cutoff inicial configurable. Tanto el evento utilizado como la
disponibilidad de la versión de la fuente deben cumplir el límite; una revisión
posterior no se convierte en prepartido por pertenecer a un partido antiguo.
Si no se demuestra disponibilidad, el valor queda faltante con su motivo.

Excepción experimental autorizada para Fase 1: reconstruir únicamente el historial
del kicker suponiendo disponibilidad del resultado a `max(inicio real + 24 h,
último evento registrado)`. Esos valores sirven para validar el builder, no prueban
disponibilidad de la versión histórica. Se separan `features_technically_reconstructible`
y `features_temporally_verified`; todas las filas del replay tienen este último
en false y `eligible_for_final_training=false`. La regla estricta anterior sigue
siendo el requisito para aprobar entrenamiento final.

Target, participación observada, sustituciones, flags derivados del resultado y
conteos del partido objetivo nunca son inputs predictivos. Un XPM histórico de
un partido anterior sí podrá ser una feature cuando ya esté disponible al cutoff.
Los rolling se desplazan un partido: excluyen G y los partidos aún no disponibles.
Divisiones sin denominador o historial insuficiente quedan NULL, no cero.

Se preservan flags de múltiples kickers, sustitución atípica, identidad ambigua y
problemas de reconciliación/label para revisión o exclusión explícita posterior.
No se colapsan varios ejecutores en un único kicker. No se confunde label ausente
con XPM=0. Las reglas de población originales permanecen conservadas; cualquier
ampliación de participantes necesitará una decisión posterior documentada.

Esta población describe XPM **condicional a participar**. No estima por sí sola
la probabilidad de participar, y su selección retrospectiva puede diferir de los
kickers consultados por usuarios. La admisión a entrenamiento y el tratamiento
de no participación siguen pendientes; no se modifican flags de elegibilidad
existentes ni se declara aprobada una población en esta etapa.

## Contrato y Fase 1

`kickedge/features/contract.json` define identidad, target, auditoría, kicker,
ofensiva, defensa rival, contexto y grupos futuros opcionales. Cada campo tiene
nombre, tipo, definición, fuente prevista, requisito as-of, estado de implementación,
riesgo de leakage y permiso explícito de uso predictivo. Fase 1 materializa
21 predictores del kicker, con ventanas de 3 y 5 partidos. Los nombres iniciales
del esqueleto se sustituyeron coherentemente por los solicitados en Fase 1 y se
registran como retirados en el contrato; ningún dataset previo los materializaba.

El estado de cada campo distingue lo implementado de builders planificados.
El contrato no asegura que cada fuente prevista tenga
disponibilidad histórica suficiente. Los grupos market, injuries/personnel,
weather y 2PT son opcionales y permanecen sin implementar.

`FeatureContext` transporta únicamente identidad, temporada y cutoff.
`KickerFeatureBuilder` utiliza exclusivamente resultados previos revelados.
La trazabilidad incluye fuentes/hashes, partidos contribuyentes, disponibilidad
asumida y motivos de NULL. La validación comprueba contrato, tipos y límites
temporales. Ver [protocolo de Fase 1](kicker_features_phase1.md).

La investigación anterior se conserva íntegra en `kickedge/pregame/`, `audits/`
y `reports/pregame_*`. Su conclusión sobre identificación automática permanece
válida para aquel experimento, pero deja de ser un bloqueo para definir esta nueva
población. No se continúa esa línea de desarrollo.
