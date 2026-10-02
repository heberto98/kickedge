# Fase 7A: inferencia offline y analisis de props

## Alcance y modelo congelado

El motor recibe un snapshot ya materializado de los **82 predictores** y analiza
una cotizacion despues de predecir. No consulta APIs, no lee `.env`, no genera
features actuales, no entrena, no calibra y no vuelve a evaluar 2025.

`kickedge.inference.loader` verifica el manifiesto versionado `release.json`,
el SHA-256 del binario y el hash canonico de metadata **antes** de deserializar.
Deserializa los mismos bytes verificados. Comprueba versiones del runtime,
contrato y codigo de modeling congelados, Poisson GLM alpha=0.1, refit 2016–2024,
82 columnas y orden exactos, imputacion mediana con indicadores, escalado,
encoder y compatibilidad del estimador. Cualquier incompatibilidad bloquea la
inferencia; no descarga ni repara el modelo. El manifiesto incluido en el codigo
es la raiz de confianza, no un manifiesto aportado por el consumidor.

Release: `phase5-c2f8f5ff0071`; artifact SHA-256:
`c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0`.
El consumidor conserva localmente `data/models/phase5/model.joblib` y
`metadata.json`; ambos siguen fuera de Git. Instalar dependencias compatibles
no sustituye disponer del artifact aprobado. El motor verifica el modelo en cada
llamada y no acepta inyectar un predictor externo.

## Entrada

Un JSON con tres espacios separados:

- `features`: los 82 nombres exactos del contrato, con valores tipados. El orden
  del JSON es libre; el DataFrame se ordena segun el modelo. Se rechazan columnas
  adicionales, targets, current/experimental, faltantes, tipos invalidos y NaN/Inf.
- `metadata`: `kicker`, `team`, `opponent` obligatorios; `kicker_id`, `game_id`,
  `event_id`, `kickoff`, `cutoff` opcionales. Timestamps ISO con zona horaria;
  si ambos estan presentes, cutoff debe preceder kickoff. Nunca son predictores.
- `provenance` opcional: `source`, `snapshot_id`, `demo`, `kind`, `build_id`,
  `source_sha256`. La identidad/procedencia declarada no certifica disponibilidad
  pregame. Ese control corresponde al productor del snapshot.

NULL se permite solo en campos nullable del contrato y se procesa mediante la
imputacion congelada; el resultado enumera esos campos. Una categoria desconocida
de `game_type` usa el comportamiento del encoder existente y genera advertencia.
Los JSON con claves duplicadas o constantes no finitas se rechazan.

El prop se entrega por separado: `line`, `side`, `odds`; opcionalmente
`over_odds`, `under_odds`, `source` y `timestamp`. Ambos precios deben venir juntos
y el del lado solicitado debe coincidir con `odds`. La API recibe numeros;
la CLI acepta odds enteras con signo opcional. Se exige magnitud >=100 y se
rechazan cero y strings ambiguos. `side` es `over` o `under`, y la linea es
no negativa, entera o semientera; no se soportan cuartos de punto.

## Ejecucion

```powershell
python -m kickedge infer --features examples/inference_demo_2024.json --line 2.5 --side over --odds +119 --over-odds +119 --under-odds -140 --source "DEMO hypothetical paired quote" --json
```

Omitir `--json` produce salida legible. Tambien existe
`python -m kickedge.inference`. `--model-dir` permite otra ubicacion local del
mismo artifact aprobado. Las identidades opcionales de CLI deben coincidir
con el snapshot: no permiten cambiar silenciosamente el partido o kicker.

```python
from kickedge.inference.contracts import read_snapshot
from kickedge.inference.engine import analyze

result = analyze(read_snapshot('examples/inference_demo_2024.json'),
                 2.5, 'over', 119, over_odds=119, under_odds=-140)
```

La ruta `python -m kickedge infer` se despacha antes de importar el CLI historico
y su configuracion. Ninguna cotizacion o identidad entra al GLM.

## Probabilidades, precios y EV

Se reutilizan `modeling.distributions.poisson_distribution` y
`line_probabilities`. La salida contiene P(X=0)..P(X=12) y P(X>12), sin perder
la cola; la suma y la no negatividad se comprueban.

| Linea | Over | Under | Push |
|---|---|---|---|
| 2.5 | P(X>=3) | P(X<=2) | 0 |
| 2.0 | P(X>=3) | P(X<=1) | P(X=2) |

Para +A: implied=100/(A+100), beneficio=A/100.
Para -A, A absoluto: implied=A/(A+100), beneficio=100/A.
Con ambos lados: no-vig de cada lado=implied_lado/suma_implied;
overround=suma_implied-1. Un overround negativo se conserva con advertencia.
La coincidencia de evento, linea, proveedor y momento de ambos precios depende
del consumidor; 7A no puede verificarla contra una fuente externa.

Para lineas enteras, la probabilidad comparable al precio es
`p_win/(p_win+p_loss)`, etiquetada **conditional on no push**. Para medias lineas
es `p_win`. El edge raw/no-vig es 100 por la diferencia entre esa probabilidad
y la implied/no-vig correspondiente, en puntos porcentuales.

Fair American odds: -100*p/(1-p) si p>=0.5; 100*(1-p)/p si p<0.5.
Se usa la misma probabilidad comparable; p=0/1 o desbordamiento numerico devuelve
`american=null` y una razon. Una masa no-push numericamente irresoluble se rechaza.

**EV por unidad = p_win * beneficio - p_loss**, usando probabilidades sin
condicionar; un push aporta cero. No genera recomendaciones, picks, confidence
scores, Kelly ni tamanos de apuesta.

## Salida y calidad

JSON `schema_version=7a.1`, con objetos `model`, `game`, `prediction`, `prop`,
`market`, `analysis`, `data_quality`. Incluye version/hash/periodo del modelo,
lambda, distribucion y cola, tres probabilidades de liquidacion, probabilidad
raw y conditional del lado, implied/no-vig/overround, edges, fair odds y EV.

Calidad informa verificacion del modelo, conteo de features, campos nullable,
metadata opcional faltante, procedencia, timestamp del precio y advertencias.
`pregame_availability_verified=false` explicita que 7A valida estructura y
modelo, pero no certifica que los valores declarados existieran antes del cutoff.
Un timestamp presente no equivale a precio actual ni a evidencia point-in-time.
La misma entrada y release producen la misma salida; no se agrega la hora actual.

## Demo reproducible

`examples/inference_demo_2024.json` es **DEMO / TEST FIXTURE**:
Brandon Aubrey, DAL vs SF, `2024_08_DAL_SF`. Procede de una proyeccion de features
del dataset local congelado de Fase 4, con hash y build en `provenance`.
`python -m scripts.create_inference_demo` reproduce la seleccion determinista:
DAL, temporada 2024, semana >=8, elegible y al menos cinco partidos previos,
ordenada por semana/game/kicker, primera fila. Proyecta solo identidades, tiempos
y 82 predictores; no proyecta XPM target ni filas de 2025. No reconstruye el dataset.

La prueba reproduce contenido igual al fixture versionado y dos ejecuciones
generan bytes iguales. La comparacion con Git es semantica para tolerar LF/CRLF.
2024 pertenece al refit: esta demo demuestra funcionamiento, no rendimiento
fuera de muestra. Los precios +119/-140 son hipoteticos, no precios historicos
verificados ni una prediccion actual. Resultados en el
[reporte de verificacion](../reports/phase7a_verification.md).

Limites: no adquisicion de features/cotizaciones live, certificacion de procedencia,
API web, frontend o deployment. Fase 7B no se inicia.
