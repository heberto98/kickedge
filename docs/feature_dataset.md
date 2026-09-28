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

**Para el partido G, nunca usar datos del objetivo ni de partidos futuros.**
Según [event-context-v1](temporal_policy.md), historical event data exige eventos
concluidos antes del cutoff, cronología y trazabilidad; no exige timestamps de
publicación de archivos retrospectivos. Point-in-time context data sí exige
la versión disponible antes/al cutoff. La excepción de eventos no se extiende
a odds, lesiones, roster/noticias, depth charts ni pronósticos.

Las 21 features del kicker quedan aprobadas para entrenamiento histórico.
Se conserva `max(inicio real +24h, último evento registrado)` como margen
conservador de incorporación. No representa una fecha de publicación supuesta.
El cutoff sigue siendo `min(inicio real, programado)-60m`.

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
kickers consultados por usuarios. Se aprueban las filas de Fase 1 de 2016–2025
con temporalidad válida, historial utilizable, target válido e identidad resuelta.
2015 permanece como historia de referencia. El tratamiento prospectivo de no
participación sigue pendiente; los flags originales bajo source_label se conservan.

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
La trazabilidad incluye fuentes/hashes, partidos contribuyentes, clase temporal,
relojes del evento, margen de incorporación y motivos de NULL. La validación comprueba contrato, tipos y límites
temporales. Ver [protocolo de Fase 1](kicker_features_phase1.md).

La investigación anterior se conserva íntegra en `kickedge/pregame/`, `audits/`
y `reports/pregame_*`. Su conclusión sobre identificación automática permanece
válida para aquel experimento, pero deja de ser un bloqueo para definir esta nueva
población. No se continúa esa línea de desarrollo.
