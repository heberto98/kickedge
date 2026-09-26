# Expected kicker: reconstrucción y simulación histórica

## Resultado y alcance

Se implementó una simulación secuencial 2015–2025 sobre 6,056 team-games. Se conservan dos experimentos separados: selección con fuentes fechadas y comparación cronológica A/B/C. El segundo consigue cobertura histórica amplia como **inferencia**, sin convertirla en confirmación de disponibilidad del jugador.

El selector no conoce el kicker real del target. Esto no garantiza exactitud de la identidad ni que las versiones actuales de archivos retrospectivos sean idénticas a las publicadas en su momento. Se distinguen expresamente el hecho deportivo anterior, la fecha de publicación, la modificación editorial, la captura de un proveedor y la descarga local.

Los 6,083 labels originales permanecen intactos como población observada postgame. La nueva unidad es `(game_id, team, prediction_cutoff)` con ID esperado opcional. Cada política tiene exactamente una fila por team-game; el ID no forma una clave obligatoria, porque UNKNOWN y AMBIGUOUS deben conservarse.

## Fuentes y temporalidad

- El universo y los horarios proceden del build histórico congelado. Se proyectan solo identidad, equipos, temporada, semana y horario, sin marcador. El horario de schedules es Eastern y se convierte con `America/New_York`, incluido DST, antes de restar 60 minutos. Es el kickoff programado registrado retrospectivamente, no una copia archivada de lo que figuraba en el calendario a T−60; las reprogramaciones siguen siendo una limitación.
- Los snapshots de depth charts 2025 usan `dt`, que el proveedor define como momento de carga. Se elige el último snapshot de TODO el equipo anterior o igual al cutoff; después se filtra PK. Si el snapshot carece de PK, no se rescata una fila de otro snapshot. Antigüedad máxima: 48 horas, fijada antes de evaluar. Un rank 1 único puede inferir rol, pero no prueba salud ni roster activo. El [diccionario](https://nflreadr.nflverse.com/articles/dictionary_depth_charts.html) y el [código del proveedor](https://raw.githubusercontent.com/nflverse/nflverse-rosters/main/exec/update-depth-charts.R) describen los snapshots y las actualizaciones de IDs.
- Los depth charts 2015–2024 y los rosters semanales carecen de timestamp de publicación/captura por fila. No se les inventa uno a partir de la semana. Las lesiones 2015–2024 tienen `date_modified`, definido como actualización de la información, no publicación pública. En el archivo 2025 descargado falta esa columna. Esos activos se incluyen en el inventario, se hashean y se excluyen de la asignación temporal; no se convierten en prueba de disponibilidad por falta de una baja. Ver [diccionario de lesiones](https://nflreadr.nflverse.com/articles/dictionary_injuries.html).
- Los artículos oficiales se cachean por SHA-256. Se selecciona el objeto JSON-LD `NewsArticle` cuya URL coincide exactamente, excluyendo galerías y contenido relacionado. Para la versión actual, `available_at=max(datePublished,dateModified)`. Publicación y modificación tienen que preceder a T−60; una modificación posterior invalida esa versión aunque el titular original sea anterior. El contenido se anota manualmente con anclas breves y una interpretación explícita. No se extraen asignaciones libres de cualquier artículo.
- La evidencia oficial aceptada confía en los metadatos editoriales del club: no hay archivo web independiente de cada versión. VERIFIED significa confirmación explícita bajo ese contrato, no prueba criptográfica independiente de publicación histórica. Se conserva esta limitación junto con la evidencia.
- GSIS/ESPN/nombres sirven solamente como crosswalk estático. No se consultan equipo actual ni estado actual del jugador para determinar pertenencia histórica. Un ID no resoluble o conflictivo queda sin seleccionar. No se hace matching mediante participantes del target.

## Jerarquía

| Categoría | Significado exacto |
| --- | --- |
| VERIFIED | Asignación oficial explícita para el partido, con publicación y versión modificada válidas antes del cutoff, ID resoluble y sin veto aceptado |
| STRONG | K en roster activo según fuente fechada y corroboración mediante lista oficial completa de inactivos; no hay contradicción aceptada. No se afirma independencia estadística de ambas señales |
| INFERRED | Rol de snapshot, o continuidad de partidos anteriores, según el experimento. `inference_subtype` separa continuidad corroborada de continuidad experimental sin disponibilidad actual verificada |
| AMBIGUOUS | Candidatos en conflicto: asignaciones/rank 1 empatados, múltiples ejecutores del juego previo, o continuidad contraria al rol pregame actual |
| UNKNOWN | Evidencia insuficiente, antigua, sin timestamp admisible, ID sin resolver, ausencia de rol o historia insuficiente |

Rank 2 y rank 3 quedan como alternativas, no empatan automáticamente con rank 1. Una baja veta al jugador, pero no asciende automáticamente al suplente. Las alternativas rechazadas por tiempo no aparecen como candidatos disponibles; permanecen en el ledger con motivo de rechazo.

## Simulación cronológica

El [protocolo secuencial](pregame_sequential_protocol.md) se escribió antes de ejecutar las políticas. No se cambiaron las reglas para corregir los 128 errores observados.

1. `prepare-history` prepara un archivo de resultados por partido como oracle en un proceso separado. `compare` solo carga su manifiesto sin identidades, no la tabla completa de resultados ni la evaluación del estudio inicial. El selector no recibe el contenido del oracle ni puede consultarlo directamente.
2. Al llegar al cutoff de un juego, se revelan únicamente juegos previos ya congelados y cuyo kickoff + 24 horas sea anterior o igual al cutoff actual. Se actualiza el estado por equipo y temporada.
3. Se calculan las identidades de ambos equipos con el estado revelado y la evidencia pregame admisible. Se persiste un evento `freeze` con las decisiones A/B/C.
4. Solo después se habilita la futura revelación del juego. Cada acceso al oracle exige tanto congelamiento previo como cumplimiento de la hora de revelación.
5. El resultado real actualiza la historia futura incluso si la predicción anterior fue UNKNOWN, ambigua o errónea. Nunca se usa la identidad predicha como sustituto del hecho real.

La demora de 24 horas es una **hipótesis de disponibilidad de hechos deportivos anteriores**, no una fecha de publicación fabricada. El proveedor describe actualizaciones nocturnas y correcciones posteriores; las copias descargadas hoy pueden incorporar correcciones. Consultar [calendario de actualización](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html). No se usan features de resultado ni información ofensiva: solo identidad de quien intentó PAT/FG en juegos previos.

La continuidad exige el mismo ejecutor único en dos juegos anteriores consecutivos, dentro de la misma temporada, con separaciones y antigüedad de hasta 21 días. Permite bye y playoffs. Un juego sin PAT/FG interrumpe la racha; múltiples ejecutores crean ambigüedad. No se salta selectivamente un partido que contradiga la historia. `prior_consecutive_games` describe la racha del candidato histórico; una confirmación oficial puede seleccionar a otro jugador y vencer esa racha.

Cada evento lleva número de secuencia, hash anterior y hash propio. La cadena y los archivos de identidades se guardan antes de iniciar la evaluación global. La preparación offline del oracle contiene resultados; esto no equivale a revelarlos al selector. La prueba de borrado físico del target verifica la frontera de acceso.

## Políticas y evaluación

A admite VERIFIED/STRONG; B añade continuidad corroborada por rol actual; C añade continuidad sin corroboración actual y la marca experimental. El estudio inicial de snapshots se conserva como referencia: no equivale a B.

`actual_placekicker_ids` contiene quienes intentaron PAT o FG; no incluye a un punter solamente por ejecutar kickoffs. `exclusive_match` exige un único real igual al esperado; `expected_among_multiple` significa pertenencia a un conjunto real más amplio; `mismatch` exige un esperado conocido y un conjunto real no vacío que no lo contiene. Sin PAT/FG real se usa `no_actual_placekick`, sin clasificar automáticamente error o acierto.

Accuracy de pertenencia = (exclusive_match + expected_among_multiple) / casos con ID y PAT/FG real. Accuracy exacta usa solo exclusive_match en el numerador. UNKNOWN/AMBIGUOUS y equipos sin intentos se muestran aparte. Un 100% en equipos sin cambio es consecuencia de una regla de continuidad y no demuestra habilidad para anticipar transiciones.

Se enlazan XPA/XPM ya reconciliados para el ID esperado. Los ceros válidos sobreviven; un label individual ausente queda NULL. Las discrepancias no se borran ni se cambian al ID real. Este límite deja 141 IDs de C sin label validado; eliminar esas filas para entrenar introduciría selección favorable retrospectiva. Resolver sus outcomes exigiría un contrato adicional de ceros para no participantes, no un `fillna(0)`.

`no_kicking_evidence` no significa DNP: una persona puede jugar sin PAT/FG/kickoff. Dos bajas se confirmaron manualmente; no hay medición exhaustiva de participación total en estas tablas.

## Week 1 y períodos de evaluación

Los 350 team-games de Week 1 quedan UNKNOWN en A/B/C. El reset anual impide inferir roster de septiembre usando simplemente enero. La temporada 2017 tiene dos equipos que comienzan después de Week 1 en schedules. Para 2025, el experimento inicial sí obtiene 32 IDs de Week 1 por snapshot; 31 son comparables y coinciden, uno no tuvo PAT/FG. Se mantienen INFERRED y no se flexibilizó B después de ver ese resultado.

La cobertura de C fuera de Week 1 es 4,992/5,706. El futuro trabajo razonable para Week 1 sería una fuente histórica de roster final, transacciones de offseason y asignación/depth anterior al opener. No se integró un scraping masivo ni se asumió que esos archivos existen con temporalidad completa.

2015–2020 es desarrollo; 2021–2024 evaluación temporal descriptiva con algunos casos ya auditados; 2025 ya había sido inspeccionado al construir el estudio de snapshots. No hay un período totalmente intacto, y no se presenta esta evaluación como validación independiente.

## Recomendación y punto de parada

C demuestra que es posible construir una hipótesis histórica reproducible sin consultar el target: cobertura 82.43%, coincidencia 97.41%. Sin embargo, en cambios reales identificados acierta 11/139; nueve de esos once son pertenencia a conjuntos de múltiples ejecutores. Cuando cambia a un único ejecutor actual diferente, solo acierta 2/130. El promedio está dominado por continuidad estable. B mejora el promedio pero también falla 8/11 cambios evaluables. A cubre solo dos casos dirigidos.

No recomiendo aprobar todavía una población definitiva de entrenamiento. C sirve como baseline de investigación; B como subconjunto corroborado, aún incompleto; A como evidencia para auditoría, demasiado pequeña para modelar. Los datasets secuenciales mantienen elegibilidad falsa para todas las filas mientras el usuario revisa la política. El estudio inicial conserva su recomendación VERIFIED-only como resultado anterior, separado del dataset secuencial.

El siguiente paso metodológico sería ampliar sistemáticamente fuentes de bajas/altas e inactivos con una estrategia de acceso estable y temporalidad explícita, y reservar una evaluación nueva; alternativamente, comenzar captura prospectiva a T−60. No se inició ninguna de esas etapas, ni features ni ML.
