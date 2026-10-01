# Auditoria breve de ParlayAPI

Fecha local: 2026-09-30 (America/Mexico_City). Mercado: `player_extra_point_made`, NFL. Consultas GET automatizadas, autenticadas por encabezado; clave leida exclusivamente de `.env`. Sin integracion, cambios de fase, commit ni push. Respuestas procesadas en memoria; solo resumen compacto y dos ejemplos por consulta en `tmp/`, ignorado por Git.

## Mercado y cobertura observada

El catalogo confirma `player_extra_point_made`, etiqueta `extra_point_made`, `total_snapshots=2981` y bookmaker `sleeper` en ese momento. Este contador no equivale a partidos, closing rows ni cobertura anual. El historico tambien devuelve `fliff`.

Muestra inicial: 2022-09-11, 2023-09-10, 2024-09-08, 2025-09-07 y 2026-09-27. Una consulta adicional por rango 2022-09-01 a 2026-09-30, limitada a 5,000 filas, encontro 574; `x-archive-truncated=false`. Una comprobacion acotada de identidad sobre 2026-09-02 a 2026-09-28 reprodujo ese resultado.

| Temporada | Jornada muestreada: filas XPM | Filas en rango amplio | Kickers distintos |
|---|---:|---:|---:|
| 2022 | 0 | 0 | 0 |
| 2023 | 0 | 0 | 0 |
| 2024 | 0 | 0 | 0 |
| 2025 | 0 | 0 | 0 |
| 2026 | 75 | 574 | 33 |

Primera fecha **declarada en las filas**: **2026-09-02**; ultima: **2026-09-28**. No son fechas de captura verificadas ni certifican la fecha real del partido. No se encontraron filas anteriores dentro del rango consultado; todas las muestras antiguas respondieron HTTP 200 con lista vacia, no 403. Esto describe lo servido por esta cuenta/endpoint, no demuestra inexistencia absoluta en todos los archivos del proveedor.

El 27/09 devolvio 75 filas, 14 grupos fecha/matchup y 28 kickers. En el rango amplio: 218 grupos fecha/matchup (uno sin equipos), 431 grupos fecha/matchup/kicker y 217 canonical_event_id no vacios. **No interpretar esas cifras como partidos NFL unicos validados**: hay solo 57 pares home/away distintos y cruces repetidos en diferentes fechas con IDs diferentes. Ejemplo: BUF-LAC y CLE-CAR aparecen tanto el 25 como el 27 de septiembre. Se necesita reconciliar el calendario real antes de contar partidos o unir targets.

Existen multiples lineas: 68 grupos fecha/matchup/kicker tienen mas de una; 20 en la muestra del 27/09. Cameron Dicker tiene 1.5/2.5 y Tyler Bass 1.5/2.5/3.5 ese dia. Esto no demuestra que todas coexistieran en el mismo instante.

## Proveedores y formato

- Historico: Sleeper **425 filas**, Fliff **149**. Ningun otro bookmaker XPM aparecio en el rango servido.
- Actual: **29 filas / 29 kickers / 15 grupos fecha/matchup**, solo Sleeper, fechas declaradas 2026-10-01 a 2026-10-04; `x-result-has-more=false`. Es una fotografia del board, no garantia de cobertura completa futura.
- Sleeper: DFS/pick'em segun documentacion; ejemplos actuales llevan `is_dfs_flat_payout=true`, `dfs_normalized=false`. No tratar sus precios como evidencia de una apuesta individual de sportsbook tradicional.
- Fliff: la documentacion del proveedor lo clasifica como sportsbook y distingue sus precios de los DFS. Esto es la clasificacion de ParlayAPI, no una certificacion regulatoria ni equivalencia de reglas/pagos.
- Ambos endpoints devuelven listas JSON. Closing usa `over_odds` / `under_odds` y probabilidades por lado en escala 0-1. Actual usa `over_price` / `under_price`; su `implied_probability` aparece en porcentaje. Requieren mapeo explicito.

## Calidad y temporalidad

| Campo requerido | Historico: faltantes de 574 | Actual: faltantes de 29 |
|---|---:|---:|
| game_date | 0 | 0 |
| home_team | 1 | 0 |
| away_team | 1 | 0 |
| player | 0 | 0 |
| market_key | 0 | 0 |
| line | 0 | 0 |
| over_odds | 0 | 29: campo se llama over_price |
| under_odds | 0 | 29: campo se llama under_price |
| bookmaker | 0 | 0 |
| canonical_event_id | 1 | 0 |

Hallazgos que impiden aprobar directamente un backtest:

1. `commence_time` falta en **574/574 historicas y 29/29 actuales**. Las historicas no incluyen timestamp de captura/actualizacion ni evidencia de disponibilidad al cutoff. Las actuales si incluyen `last_update` y `age_seconds`; no sustituyen el kickoff ausente.
2. **280 probabilidades por lado de Sleeper** difieren de la conversion de su cuota americana en mas de 0.0001; ninguna discrepancia detectada en Fliff. Ejemplo historico: cuota +105 con probabilidad 0.5122, cuando la conversion aritmetica es 100/205 = 0.487805. No utilizar esas probabilidades directamente; primero aclarar semantica DFS/precio y recalcular cuando corresponda. No es una prueba de calibracion estadistica.
3. Los IDs/fechas presentan la ambiguedad indicada arriba; presencia del campo no garantiza identidad correcta.
4. Closing odds no acreditan disponibilidad 60 minutos antes del kickoff, cutoff actual de KickEdge. No aprobar su uso como feature pregame a ese cutoff solo por llamarse closing.

## Cuenta, errores y coste

Cuenta **Free**, 1,000 creditos por periodo y limite reportado de 60 requests/segundo. Al inicio: 33 usados / 967 disponibles. Tras las consultas con cargo: 109 usados / 891 disponibles; **76 creditos consumidos** (7 historicas de 10, props actual 3, mercado general 3).

La documentacion publica indica 48 horas de historico para Free y errores `HISTORICAL_LIMIT` para fechas mas antiguas. **El comportamiento observado de closing-odds no coincide:** acepto 2022 y el rango completo con HTTP 200, sin encabezados `x-historical-window-*`. No se observaron 403 ni 429 en las consultas autenticadas de datos. No se puede prometer que el acceso antiguo permanezca permitido ni extrapolar este comportamiento a otros endpoints. El 403 al consultar el esquema publico mediante urllib no fue una consulta historica autenticada ni evidencia de restriccion de la cuenta.

El catalogo gratuito requirio autenticacion (primer intento 401). Props actual dio un 503 `props_temporarily_busy`; un unico reintento obtuvo 200. Los intentos fallidos y metadatos no aumentaron el consumo observado. La consulta de mercado general obtuvo HTTP 200, 32 entradas y mercados h2h/spreads/totals (282/297/285 bloques, respectivamente; no son conteos de partidos unicos).

## Veredicto: B) suficiente parcialmente

- **Props actuales:** si, con disponibilidad variable y cautelas DFS/calidad.
- **Historico XPM:** parcial, solo filas fechadas en septiembre de 2026 en lo servido; no cubre 2022-2025 ni el dataset de entrenamiento 2015-2025.
- **Backtesting:** no listo para backtesting temporal riguroso; faltan archivo multitemporada, identidad/fecha reconciliada y snapshots verificables al cutoff. Puede servir para exploracion del cierre reciente tras depuracion.
- **Mercado general:** si, moneyline, spread y total confirmados.
- **Fuente adicional faltante:** historico XPM multitemporada de precios reales de sportsbook, con event/player IDs fiables y timestamps de observacion anteriores al cutoff; calendario verificable para reconciliar eventos. No se selecciono ni investigo otro proveedor.

Fuentes oficiales: [documentacion y clasificacion de proveedores](https://parlay-api.com/docs), [contrato OpenAPI](https://parlay-api.com/openapi.json), [distincion de archivos historicos](https://www.parlay-api.com/historical-coverage). Las cifras y defectos de calidad anteriores proceden de las consultas de esta auditoria, no de afirmaciones comerciales de cobertura general.
