# Fase 4: mercado, clima y datos actuales

La Fase 4 agrega 8 variables de mercado y 8 de clima/sede. No cambia los 82
predictores aprobados, sus valores ni la poblacion elegible de Fase 3.

## Tres usos separados

| Uso | Fuente y condicion | Salida |
|---|---|---|
| training-historical | 82 predictores anteriores; nuevo contexto solo con identidad y disponibilidad verificadas antes del cutoff | Selector `predictor_columns_through_phase_4`, actualmente los mismos 82 nombres |
| current/forward | Capturas de ParlayAPI y forecasts actuales Open-Meteo; conservar fuente/hash y momento real de recepcion | Adaptadores opcionales; no forman parte de builds offline |
| experimental | Schedule nflverse retrospectivo: closing lines, temperatura/viento observados y techo reportado | `enrichment.json`, fuera del selector de entrenamiento |

La elegibilidad de cada observacion y la aprobacion del selector son controles
distintos. Los builders pueden validar una captura pre-cutoff, pero eso no
promueve automaticamente una nueva columna al selector historico. En esta
materializacion no hay nuevos valores aprobados de mercado/clima: sus 16
columnas son NULL y `phase_4_additions_verified=false`. La elegibilidad de
5,535 filas se refiere exclusivamente a la seleccion de 82 columnas anterior.

## Mercado general

`game_spread` es el handicap del equipo del kicker: negativo indica favorito.
El `spread_line` local de nflverse tiene signo positivo cuando el local es
favorito; se invierte para el local y se conserva para el visitante.

- `game_total`: total de puntos cotizado, nunca marcador final.
- `moneyline_team`, `moneyline_opponent`: cuotas americanas del mismo snapshot.
- `implied_team_strength`: probabilidad moneyline de dos lados sin margen,
  `p_team / (p_team + p_opponent)`. No modela el empate ni certifica calibracion.
- `implied_game_environment`: alias de game_total.
- `implied_team_total = (game_total - game_spread) / 2`.
- `implied_opponent_total = (game_total + game_spread) / 2`.

Los totales por equipo son una asignacion derivada del spread y total, no un
mercado independiente ofrecido por el book ni una prediccion calibrada. Operandos
faltantes o incompatibles producen NULL. Para cuota americana A, p=100/(100+A)
si A>=100; p=(-A)/(100-A) si A<=-100. No se aplica a DFS automaticamente.

`market_features(identity, evidence)` requiere juego/equipos coincidentes y
snapshot con captura <= cutoff < kickoff, fuente y hash valido. No admite una
cotizacion posterior al cutoff ni siquiera si last_update es antiguo. Las
closing lines locales sin evidencia de version son solo experimentales.

## Adaptadores actuales

```python
from kickedge.providers.parlay import ParlayClient
client = ParlayClient()  # PARLAY_API_KEY del entorno o .env; no lo modifica
xpm = client.current_xpm()
general = client.current_markets()
```

Cada resultado contiene `rows`, `observed_at`, `source`, `source_sha256` y
`metadata`. No hay reintento ni paginacion automatica. Una pagina exitosa no
garantiza cobertura completa. Persistir la captura local permite conservar
evidencia futura; los builds historicos no invocan la red.

XPM normaliza line, over_price/under_price, bookmaker, tipo, IDs, jugador y
last_update. Las probabilidades del proveedor se retienen como no confiables.
Solo sportsbooks conocidos reciben conversion propia de cuotas; Sleeper y otros
DFS mantienen precios cotizados y probabilidades propias NULL. Los IDs y kickoff
deben reconciliarse; la auditoria detecto horas faltantes y ambiguedad historica.

Para usar un snapshot general con el builder:

```python
from kickedge.features.market import parlay_market_features
# identity: game_id, team, opponent, kickoff y prediction_cutoff, con zona horaria.
# mapping: nombres exactos del proveedor -> codigos de equipo verificados.
result = parlay_market_features(identity, general, event_id, "fliff", mapping)
```

Se elige un evento/book exacto, se exige kickoff coincidente y lados compatibles;
no se hace matching aproximado ni se mezclan books para derivar totales.

## Clima y sede

`OpenMeteoClient.forecast(latitude, longitude, kickoff)` obtiene una sola fecha
en UTC. Devuelve temperature (C), wind_speed y wind_gust (km/h),
precipitation_probability (%), precipitation (mm) y weather_code (WMO).
Se selecciona la hora UTC que contiene el kickoff; no es una agregacion del
clima durante todo el partido. Tambien hay `roof_type` e `is_dome`.

```python
from kickedge.providers.weather import OpenMeteoClient, weather_features
forecast = OpenMeteoClient().forecast(latitude, longitude, identity["kickoff"])
forecast["game_id"] = identity["game_id"]
result = weather_features(identity, forecast, venue)
```

`venue` debe contener game_id, latitude, longitude, roof_type, observed_at,
source y source_sha256 de una fuente verificada antes del cutoff. Esta fase no
inventa coordenadas, no geocodifica estadios automaticamente ni infiere el techo
abierto de una sede retractil. El llamador debe proporcionar esa identidad.
La captura posterior al cutoff no puede aprobarse retroactivamente. Publicacion
opcional debe preceder la captura. Los flags separados certifican sede y clima.

Dome/closed deja clima exterior NULL; unknown/retractable sin estado resuelto
tampoco supone exposicion. El schedule local conserva techo y observaciones
solo como experimentales. Temperatura F se convierte a C y viento mph a km/h.

No hay forecast historico aprobado para 2015-2025 en esta fase. La investigacion
previa encontro archivos stitched sin prueba suficiente de disponibilidad y
runs ECMWF antiguos descritos como hindcasts. Inicializacion no equivale a
publicacion. No se descargan series masivas ni se presenta clima realizado como
forecast. El soporte forward permite empezar a conservar evidencia correcta.

## Reproducir y validar

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m kickedge.features build-environment
.\.venv\Scripts\python.exe -m pytest -q
```

`--phase3 RUTA` fija el build anterior. El builder verifica hashes del baseline,
contrato y schedule, selecciona solo identidad para enriquecer y congela el
sidecar antes de adjuntar el dataset con targets. Lee los timestamps originales
del JSON: su conversion previa a Parquet omite el tipo con zona horaria. No
modifica ninguno de esos archivos anteriores. Escribe un nuevo Parquet con
todos los valores originales, columnas nuevas seguras NULL, sidecar y hashes.

Datos y capturas viven bajo `data/`, ignorado por Git; .env tambien se ignora.
Las excepciones HTTP no muestran credenciales ni cuerpos de error. Pruebas de
red se documentan aparte y no son requisito para ejecutar los tests offline.

Fuentes consultadas durante el diseno: [nflfastR: signo de spread_line](https://nflverse.r-universe.dev/nflfastR/doc/manual.html),
[ParlayAPI](https://parlay-api.com/docs), [Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api)
y [Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api).
