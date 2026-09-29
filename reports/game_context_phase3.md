# Cierre de Fase 3

- Inputs existentes: `e0388f555b0d3336a926`; build final: `96c91563d48708f787b8`.
- 6,083 filas kicker-game; 5,535 elegibles y 548 excluidas por elegibilidad heredada de Fase 2.
- 21 predictores de contexto: 18 columnas nuevas y season/week/game_type habilitadas; 82 predictores conjuntos.
- Cobertura de las 21 columnas: 93.60%. Rest y sus flags tienen 354 NULL por lado. Tasas 2PT acumulada/rolling 3/rolling 5: 379/1,064/1,771 NULL, respectivamente. No se imputan ventanas incompletas ni denominadores cero.
- Los 3,028 partidos tienen kickoff programado; no se utilizo fallback de kickoff historico.
- Rest: diferencia UTC, en dias fraccionarios, entre kickoff programado objetivo y kickoff real del ultimo partido anterior disponible de la misma temporada. Short week <6; long rest >8.
- 2PT rate: suma de intentos 2PT dividida entre suma de intentos 2PT + PAT, usando exclusivamente juegos anteriores. Rolling exige exactamente 3/5 juegos; no promedia tasas.
- Suite completa registrada antes de la interrupcion: 180 tests aprobados. Verificacion de cierre: 34 tests de contexto y politica temporal aprobados, en 2.46 s.
- Comparacion independiente en SQL sobre las 6,083 filas: 85 campos escalares anteriores preservados, incluidos predictores, target y elegibilidad; rest, flags y ventanas 2PT coinciden. La consulta de auditoria fija UTC para evitar aritmetica dependiente del horario local.
- Verificados hashes del contrato final, codigo y todos los artefactos declarados. La actualizacion final reutilizo inputs existentes para incorporar el texto definitivo del contrato; no hubo descargas ni cambios de implementacion.
- Las listas de los 61 predictores anteriores permanecen iguales. El contrato tambien corrige caracteres danados en descripciones previas, sin cambiar sus formulas.

La politica `phase3-calendar-v1` autoriza solamente calendario y descanso como aproximacion historica; no acredita disponibilidad point-in-time del schedule. Mercado, clima, lesiones, roster, noticias y QB siguen requiriendo evidencia pregame y no se implementan aqui. La tasa 2PT describe elecciones entre intentos registrados, no exito ni probabilidad situacional. La poblacion sigue condicionada a participacion observada del kicker.

Fase 3 completa dentro de este alcance. Fase 4 no iniciada.
