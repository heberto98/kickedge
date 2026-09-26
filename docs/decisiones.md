# Decisiones y problemas de esta etapa

## Población y ceros

La población `postgame_observed_kicking_participants_v1` parte de registros de player
stats con posición K, más cualquier jugador con PAT/FG observado, aunque sea P, S o RB.
Para publicar XPA/XPM se exige participación individual en un PAT, FG o kickoff
válido del PBP, identidad estable, cobertura consistente y acuerdo con player stats.
Un registro estadístico sin esa evidencia se conserva en cuarentena.

Resultado del snapshot: 6,083 observaciones, 122 jugadores y 714 XPM=0. Las 90 filas
`kickoff_only_observed` incluyen tanto especialistas de kickoff como kickers que no
tuvieron intentos de PAT/FG. El flag describe el partido, no una especialización
permanente. No se puede excluir a todo ese grupo sin perder ceros como el de Gano.
La distribución resultante pertenece a esta población; no debe trasladarse sin más
a titulares prepartido o a un mercado de apuestas.

Diez equipos-partido carecen de candidato bajo esta definición. Se conservan en
`team_games` con `kicker_identity_status=no_observed_candidate` y estadísticas
individuales ausentes; no se agrega un jugador ni un cero artificial. La lista
completa aparece en el reporte. No se sabe a partir de esa ausencia quién estuvo
inactivo o quién estuvo disponible sin intervenir en patadas.

No se consultaron rosters: todos los candidatos actuales se resolvieron por ID.
Reconstruir titulares/inactivos históricos exigiría otro contrato de evidencia,
con roster, profundidad y disponibilidad fechados; queda pendiente.

## Identidad y sustituciones

Se conserva el `game_id` original. Se normalizan STL/LAR→LA, OAK→LV, SD/SDG→LAC,
JAC→JAX; la tabla de partidos conserva las abreviaturas originales. Los joins usan
`player_id`/`gsis_id`, nunca similitud de nombres. El archivo players aporta solo
ID y nombre; su equipo o estado actuales no se usan como información histórica.

Hay 37 equipos-partido con varios candidatos observados; en 10, dos jugadores
intentaron PAT/FG. No se equiparan automáticamente a lesiones. El caso NYG–WAS
de 2024 conserva Gano 0/0 y Gillan 1/0, aunque Gano solo hizo kickoff. Las causas
de las sustituciones auditadas de 2017 y 2024 se contrastaron con crónicas oficiales
en el informe manual; no se propagaron como reglas a otros partidos.

## Conteos y reconciliación

- PAT: `extra_point_attempt=1`; XPM además exige `extra_point_result='good'`.
  Failed y blocked cuentan como XPA, sin XPM. Se excluyen jugadas eliminadas.
- No se cuenta texto como resultado. Hay 21 filas de tipo extra_point sin intento
  oficial; algunas describen un PAT anulado y repetido.
- Para participación en kickoff se exige también `play_type='kickoff'`. Hay 57
  filas `no_play` con kickoff_attempt=1, anuladas y sin kicker ID: no acreditan
  participación. En kickoffs el pateador pertenece a `defteam`, pues `posteam`
  designa al receptor.
- Para 2PT se usa el indicador final, incluso si `play_type='no_play'`: 29 casos
  válidos contienen faltas entre jugadas. El texto también puede retener una
  anulación revertida; buscar “No Play” globalmente daría falsos negativos.
- TD: una jugada, un `td_team`. Los TD de retorno se atribuyen al anotador.
  No se suman las columnas de TD de pase y recepción. Se distinguen offense,
  defense y special teams por tipo de jugada y equipo anotador.
- `recorded_tries=XPA_equipo+2PT_attempts` son intentos registrados, no una
  reconstrucción reglamentaria de oportunidades. No se fuerza TD=tries ni se
  crea un PAT después de un TD ganador en overtime.
- Se verifica cierre `END GAME` y marcador final contra schedules. `play_id`
  no garantiza orden cronológico: usar su máximo habría producido 33 falsas
  discrepancias de marcador. Las secuencias auditadas usan `order_sequence`.
- Los dos conteos de PAT coinciden en las 6,083 filas y no hay discrepancias
  numéricas de equipo. En los 10 equipos sin registro, player stats queda NULL:
  son ausencias para reconciliación, no discrepancias numéricas ni ceros imputados.
- Si hay desacuerdo, resultado desconocido, falta de una fuente, cobertura no
  confirmada o ID no mapeado, el label canónico queda NULL con motivo explícito.
  No hay correcciones manuales ocultas ni elección automática de la fuente ganadora.

El acuerdo es una comprobación de consistencia del procesamiento. nflfastR puede
calcular estadísticas a partir del propio PBP, según su
[documentación de calculate_stats](https://nflfastr.com/reference/calculate_stats.html).
No se trata de dos mediciones oficiales independientes. Una ampliación futura
podría contrastar una muestra con gamebooks, conservando esa procedencia separada.

## Cobertura, versiones y as-of

Se procesan 3,028 partidos: 2,895 REG y 133 de playoffs, todos los incluidos en las
fuentes para 2015–2025. Hay 271 partidos REG en 2022; `2022_17_BUF_CIN` no aparece
en los originales de schedules/PBP usados. No se sintetizó una observación.
La cobertura de cierre y marcador pasa en todos los partidos; eso no prueba por
sí solo ausencia de errores en cada jugada.

Se almacenan los 24 assets completos como originales, incluso columnas del proveedor
que no usamos. Las salidas seleccionan identidad y resultados, sin trasladar odds,
clima, EPA u otras features. Cada original lleva URL, temporada, descarga UTC,
SHA-256, cabeceras HTTP disponibles, esquema y número de filas. El build identifica
inputs, configuración, código, Python y DuckDB. Una repetición compara los Parquet
byte a byte; una revisión del proveedor crea otro snapshot.

Los archivos se descargaron retrospectivamente: el timestamp no prueba publicación
antes del kickoff histórico. `expected_kicker_id` queda NULL, la identidad prepartido
está `not_reconstructed` y `eligible_for_pregame_training=false` para toda la base.
Las 5,535 filas desde 2016 son solo una reserva temporal para fases posteriores.

Próximo trabajo recomendado, sujeto a autorización: definir la población objetivo
prepartido y la evidencia as-of mínima para resolver titulares, inactivos y cambios.
No se han creado features ni entrenado modelos.
