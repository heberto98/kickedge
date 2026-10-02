# Fase 6: evaluacion unica del holdout 2025

El modelo de Fase 5, sus 82 entradas y su preprocessing son inmutables. Esta
fase no modifica ningun modulo de `kickedge/modeling`, ni el contrato o Parquet
de features, ni los artefactos guardados de Fase 5. Se evalua exactamente el
Poisson GLM alpha=0.1 reajustado con 2016–2024.

## Dos pasos deliberados

```powershell
.venv/Scripts/python.exe -m kickedge.validation prepare
.venv/Scripts/python.exe -m kickedge.validation reveal
```

`prepare` comprueba el hash del modelo antes de cargar joblib, igualdad de la
metadata local con su reporte versionado, hashes de fuentes originales/contrato/
dataset y versiones del entorno. Verifica tipo GLM, alpha, temporadas, 82
predictores y preprocessing ajustado. El baseline es la media XPM de las filas
elegibles 2016–2024; no usa la media de 2025.

Solo entonces carga las 82 features y las identidades de 2025, sin el target.
Congela las predicciones y verifica orden de filas, determinismo, valores finitos
y masa probabilistica completa. Guarda `reports/phase6_preregistration.json`
y un reporte preliminar antes de cualquier lectura de targets del holdout.

`reveal` comprueba de nuevo hashes del modelo, bundle, codigo y protocolo. Crea
un marcador exclusivo antes de la unica proyeccion SQL de targets 2025. Une
outcomes y predicciones por la clave completa game/team/kicker sin filtrar por
resultados o errores. Un marcador existente impide una segunda ejecucion.
El marcador no se elimina si ocurre una excepcion. Una falla posterior se
documenta como tal; no autoriza otra evaluacion que se presente como ciega.

Las predicciones preparadas y el snapshot de auditoria con outcomes quedan
ignorados bajo `data/validation/phase6/`. Los reportes pequenos si se versionan.
No borrar ese directorio para reabrir el holdout. En otro checkout conservar
tambien el registro versionado de evaluacion; cambiar rutas no convierte datos
ya observados nuevamente en ciegos.

## Metricas y diagnosticos congelados

Las definiciones NLL, RPS, Brier >=2/3/4, MAE, RMSE, deviance y bins son iguales
a Fase 5, con pruebas sinteticas de equivalencia. La nueva interfaz permite
solo temporadas 2025; los guards originales de entrenamiento/validacion siguen
intactos. RPS conserva soporte infinito; toda distribucion visual conserva cola.

Bootstrap pareado de filas, 1,000 remuestreos, seed 42, percentiles 2.5 y 97.5.
Los mismos indices se usan para ambos modelos y todas las metricas. No incluye
incertidumbre de estimacion del modelo, ni dependencia entre observaciones del
mismo partido/equipo/kicker; los intervalos pueden ser optimistas.

Calibracion: diez bins fijos, frecuencias con intervalos Wilson, ECE y Brier.
No se ajustan interceptos, slopes ni calibradores con 2025. Los Under complementan
los Over y se evalua cada lado explicitamente, sin cuotas ni simulacion de apuestas.

Los subgrupos dependen solo de features/predicciones: home/away, semana <=8/>8,
historia del kicker <5/>=5, lambda <2/[2,3)/>=3, descanso y ofensiva/defensiva
recientes respecto de medianas 2016–2024. Los desconocidos conservan grupo propio.
Con menos de 50 filas no se emiten advertencias fuertes de subgrupo.

Drift: top15 de Fase 5 con resumen y diferencia de medias estandarizada;
missingness y rangos en las 82 entradas. La temporada 2025 fuera del rango de
entrenamiento es esperable y se distingue de otras extrapolaciones. Los errores
extremos son descriptivos; no generan nuevas features, filtros o modelos.

## Gate anterior a la apertura

Los criterios completos estan en el plan y en la preregistracion, incluyendo
sus umbrales operativos. Se exige mejorar NLL/RPS y al menos dos Brier para
tener senal. PASS exige ademas intervalos pareados favorables, todos los Brier
no peores, ECE <=0.05, sesgo global <=0.05 y ausencia de advertencias. Senal con
advertencias da PASS WITH CAUTION. Falta de senal, ECE >0.15 o un fallo de
integridad/leakage da FAIL. No se cambian los cortes despues de observar 2025.

Esos cortes no son leyes estadisticas: clasifican riesgo operativo con evidencia
numerica, sin demostrar rentabilidad. Los cambios entre 2024 y 2025 tambien
comparan dos periodos de fitting distintos (hasta2023 vs hasta2024) y se reportan
descriptivamente. La calibracion, los subgrupos y el drift no se usan para tuning.

Independientemente del veredicto, esta tarea termina tras reportes, tests y push.
No se ejecuta Fase 7.
