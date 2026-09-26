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

## Contrato y esqueleto

`kickedge/features/contract.json` define identidad, target, auditoría, kicker,
ofensiva, defensa rival, contexto y grupos futuros opcionales. Cada campo tiene
nombre, tipo, definición, fuente prevista, requisito as-of, estado de implementación,
riesgo de leakage y permiso explícito de uso predictivo. Las ventanas iniciales
de 3 partidos son especificaciones pendientes, no métricas ya calculadas.

Todos los campos están sin materializar en este nuevo dataset. El estado
`existing_upstream_not_materialized` distingue IDs/labels ya existentes de nuevos
builders planificados. El contrato no asegura que cada fuente prevista tenga
disponibilidad histórica suficiente. Los grupos market, injuries/personnel,
weather y 2PT son opcionales y permanecen sin implementar.

`FeatureContext` transporta únicamente contexto de identidad y cutoff;
`FeatureBuilder` es una interfaz futura, sin cálculo, descargas ni acceso a labels.
Cada futuro valor requerirá trazabilidad: fuente/versión, partidos contribuyentes,
fecha de disponibilidad y motivo de faltante. El contrato es especificación;
todavía no existe un motor que valide filas o haga joins temporales.

La investigación anterior se conserva íntegra en `kickedge/pregame/`, `audits/`
y `reports/pregame_*`. Su conclusión sobre identificación automática permanece
válida para aquel experimento, pero deja de ser un bloqueo para definir esta nueva
población. No se continúa esa línea de desarrollo.
