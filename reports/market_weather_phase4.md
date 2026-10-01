# Cierre de Fase 4

Build final: `d0e256364dde3016c76f`. Baseline de Fase 3:
`96c91563d48708f787b8`. **6,083 filas; 5,535 elegibles** con los mismos 82
predictores. Las 16 variables nuevas se materializan como NULL en el dataset
seguro y con valores disponibles en un sidecar experimental separado.

## Cobertura local por temporada

Conteos de filas kicker-game, no partidos unicos. Todos estos valores nuevos
son **experimentales**: no acreditan disponibilidad anterior al cutoff.

| Temporada | Filas | Spread/total | Moneyline por lado | Temperatura/viento | Techo |
|---|---:|---:|---:|---:|---:|
| 2015 | 548 | 548 | 548 | 416 | 548 |
| 2016 | 537 | 537 | 537 | 399 | 537 |
| 2017 | 535 | 535 | 533 | 401 | 535 |
| 2018 | 534 | 534 | 534 | 394 | 534 |
| 2019 | 536 | 536 | 536 | 394 | 536 |
| 2020 | 539 | 539 | 539 | 353 | 539 |
| 2021 | 570 | 570 | 570 | 382 | 570 |
| 2022 | 572 | 572 | 572 | 216 | 572 |
| 2023 | 571 | 571 | 571 | 315 | 571 |
| 2024 | 571 | 571 | 571 | 365 | 571 |
| 2025 | 570 | 570 | 570 | 378 | 570 |

Mercado: 6,083 spreads/totales e implied team/opponent totals; 6,081 moneylines
por lado y fortalezas implicitas. Solo 2 NULL por moneyline/fuerza (2017).
Clima observado: 4,013 temperaturas/vientos y 2,070 NULL por variable. Hay 1,714
filas dome/closed con clima exterior suprimido y 356 filas outdoors/open sin
observacion disponible. Techo presente en todas. Gust, precipitation_probability,
precipitation y weather_code: 6,083 NULL cada una en este historico local.

**Ninguna temporada 2015-2025 tiene nuevas features de mercado ni forecasts
aprobados para entrenamiento en esta entrega.** No se descargaron archivos
historicos adicionales ni se repitio la auditoria historica de ParlayAPI.

## Comprobacion actual acotada

- Adaptador Parlay de mercado general: respuesta correcta, 32 entradas de juego;
  279 bloques h2h, 291 spreads y 273 totals. Snapshot local con hash y captura.
- XPM actual: el primer intento fallo; el unico reintento confirmo HTTP **503**.
  No se afirma exito en vivo en esta ejecucion. El soporte esta implementado y
  probado con fixtures, y la auditoria anterior documenta respuestas actuales
  validas de Sleeper. Fliff tambien figura en el historico auditado; no se
  promete que ambos tengan ofertas actuales en cada consulta.
- Open-Meteo: consulta de conectividad/unidades correcta con las seis variables
  meteorologicas. Coordenadas de prueba 40,-75: no constituye mapeo de estadio
  NFL ni cobertura historica. Un uso por partido exige sede y techo verificados.
- Capturas y resumentes auxiliares permanecen en carpetas ignoradas; `.env` se
  verifico sin modificaciones y no se expuso la clave.

## Validacion y resultado

- **274 tests aprobados**, incluidos los 180 existentes y 94 nuevos de Fase 4.
- Pruebas de signos, totales derivados, NULLs, corte temporal, identidad,
  sportsbook/DFS, errores/timeout/secretos, sede, dome, observed/forecast,
  conservacion del baseline y determinismo.
- Revision independiente: dos hallazgos corregidos (lock de dependencias y
  rechazo de hashes/fuentes de mercado invalidos); sin bloqueos restantes.
- Comparacion independiente de todas las columnas originales del Parquet:
  cero filas modificadas y cero diferencias de elegibilidad. Ningun valor nuevo
  experimental entro al dataset seguro ni al selector de 82 predictores.
- Build final: hashes de codigo/contrato verificados; repeticion byte-identica
  de todos los artefactos. Archivos y snapshots anteriores preservados.

**Fase 4 completa en el alcance de soporte y separacion temporal definido.**
Limitaciones: XPM actual temporalmente indisponible por 503; sin evidencia
historica pre-cutoff para las nuevas variables; mapeo de eventos/equipos/sedes
debe ser explicito y verificable; DFS no equivale a precio sportsbook; un cierre
sin timestamp no satisface un cutoff de 60 minutos. No se entrenaron modelos ni
se inicio Fase 5.

Definiciones, unidades y uso: [metodologia de Fase 4](../docs/market_weather_phase4.md).
Detalle de cobertura reproducible: [resumen JSON](market_weather_phase4.json).
