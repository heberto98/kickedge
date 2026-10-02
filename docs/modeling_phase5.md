# Fase 5: modelos de conteo

## Poblacion y temporalidad

Una fila representa un kicker-game condicionado a la participacion observada.
El producto recibira el kicker como entrada; el modelo no estima su titularidad.
Se conserva exactamente la elegibilidad de Fase 4 y sus ceros XPM/XPA.
2015 solo aporta historia. TRAIN es 2016–2023 (4,394 filas), VALIDATION es
2024 (571), y 2025 es un holdout ciego (570 filas; solo conteo/schema).

`load_split` permite unicamente `train`, `validation` o `refit` (2016–2024).
Proyecta las columnas explicitamente mediante SQL y restringe temporadas antes
de devolver los targets. No devuelve targets de 2025. La evaluacion exige
un vector de temporadas exclusivamente 2024. El wrapper de modelos tambien
bloquea fitting fuera de 2016–2023, salvo el refit explicito hasta 2024.

Se usa la lista congelada de 82 predictores de `predictor_columns_through_phase_4`.
El loader valida orden, roles y aprobacion historica. Identidades solo ordenan
filas y comprueban unicidad; nunca entran en X. Ningun target, dato del partido
objetivo, campo experimental o captura current/forward se agrega a X.
Los valores de features historicas se consumen del build existente sin recalcularlos.
Las features de un partido de validacion pueden incluir partidos anteriores de
2024 conforme a la politica temporal existente; el fitting sigue congelado hasta 2023.

## Preprocesamiento

81 campos numericos/booleanos: mediana ajustada en TRAIN y un indicador por
columna. Si toda la columna TRAIN es NULL, el fallback es cero mas su indicador
de ausencia; esto no representa un cero deportivo observado. No se reemplazan
todos los NULL por cero. `game_type` usa one-hot con categorias aprendidas en
TRAIN; categorias nuevas producen todos ceros. El GLM estandariza numericos e
indicadores, tambien ajustando solo en TRAIN. Las categorias no se estandarizan.

Durante el refit se conserva la receta, las 82 entradas, la arquitectura y sus
hiperparametros; las medianas/escalas/categorias y parametros se reajustan sobre
2016–2024. El artefacto refit no tiene metricas de generalizacion en esta fase.

## Modelos, distribuciones y evaluacion

Conjunto pequeno y registrado antes de fitting: Poisson global, GLM alpha 0.1/1,
boosting Poisson 7/15 hojas, 100 iteraciones, learning rate 0.05,
min_samples_leaf 40 y regularizacion L2 10. Sin early stopping, particiones
aleatorias ni busqueda automatica; seed 42 y un hilo numerico.
La dispersion TRAIN decide si revisar NB, no VALIDATION ni 2025.

`CountModel.predict_distribution(X)` devuelve probabilidades de 0 a 12 por
defecto, cola `P(X>12)` y la media completa. El rango visual no recorta la media.
`line_probabilities` usa colas exactas: Over estricto, Under estricto, y push
solo para lineas enteras. Las probabilidades no se renormalizan descartando cola.

NLL y Brier son reglas de puntuacion propias; RPS cubre soporte infinito mediante
una identidad exacta Poisson/Skellam con Bessel escalada. Tambien se reportan MAE,
RMSE y deviance. Calibracion bruta: diez bins fijos por threshold >=2, >=3 y >=4,
con conteos, probabilidad media, frecuencia y ECE. No se ajusta ningun calibrador.
Los resultados y decisiones estan en [el reporte](../reports/phase5_model_report.md)
y [las metricas reproducibles](../reports/phase5_metrics.json).

## Reproduccion local

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m kickedge.modeling train --dataset data/features/environment/d0e256364dde3016c76f/kicker_game_features.parquet
.venv/Scripts/python.exe -m pytest -q
```

Sin `--dataset`, usa el build de Fase 4 referenciado por `latest.json`. El hash del
Parquet y del contrato identifica exactamente los datos usados; hashear bytes
del archivo no expone ni evalua sus targets de holdout. No descarga datos.

Salidas ignoradas bajo `data/models/phase5/`:

- `selection_model.joblib`: modelo elegido, ajustado solo hasta 2023.
- `model.joblib`: arquitectura elegida, refit 2016–2024, listo para Fase 6.
- `metadata.json`: features, folds, configuraciones, metricas 2024, hashes de
  datos/codigo/artefactos, versiones, fecha y verificaciones de reproducibilidad.

Solo cargar artefactos joblib locales de confianza: su formato no es seguro para
archivos de origen desconocido. Conservar el entorno bloqueado al reutilizarlos.
El CLI no contiene un comando de evaluacion de 2025. Las pruebas sinteticas usan
labels venenosos en filas ficticias de 2025 para detectar acceso accidental.

## Limites

La validacion de una sola temporada sirve para la primera seleccion, no demuestra
estabilidad futura ni ventaja economica. La aproximacion Poisson condicionada
puede equivocarse en colas aun si la dispersion marginal parece adecuada.
Los coeficientes/permutaciones son diagnosticos, no causales; las variables
correlacionadas dificultan repartir influencia. No se seleccionaron features a
partir de esos diagnosticos. La calibracion formal y el holdout esperan Fase 6.


## Enmienda metodologica posterior a revision de validacion

La regla original se conserva en el plan y en metadata, junto con su eleccion.
La enmienda `selection_policy_amendment` se registra como `post-validation-review`:
se elimina ECE bruto como veto entre familias porque confunde calibracion empirica
con resolucion; una constante puede tener ECE casi cero sin discriminar contextos.
Se preservan las cinco configuraciones y los margenes NLL >=1% y Brier medio
<= incumbente +0.002, y se exige RPS sin deterioro. Los bins ECE permanecen como
diagnosticos. No se ajustaron tolerancias para favorecer un candidato.
Se reportan ambas elecciones. Esta seleccion explora la temporada 2024 ya
inspeccionada; no es evidencia independiente de superioridad.
La repeticion con seed fijo prueba reproducibilidad determinista, no estabilidad
temporal o muestral. La incertidumbre del ranking de arquitecturas no fue
cuantificada. No se agregan bootstrap, tuning ni acceso a 2025.
