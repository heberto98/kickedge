# Cierre y verificacion de Fase 6

Fecha: 2026-10-02. Veredicto del protocolo fijado antes de apertura: **A) PASS**.

## Evidencia de una sola apertura

- Preregistro completado: `2026-10-02T20:28:51.402161+00:00`.
- Evaluacion: `2026-10-02T20:29:05.975985+00:00`.
- 570 filas elegibles; una proyeccion SQL de targets 2025, despues del marcador
  exclusivo guardado con flush/fsync. No hay marcador de fallo.
- Marcador de consumo y snapshot de auditoria en `data/validation/phase6/`, ignorados.
- Modelo SHA-256: `c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0`.
- Los dos modelos, metadata, ocho modulos de modeling originales, contrato y
  dataset de Fase 5 conservan sus hashes. El codigo de evaluacion coincide con
  los hashes registrados antes de abrir 2025. No se cambio el gate.
- 2025 nunca participo en fitting; todos los puntos de entrada de fitting de
  modelos/preprocesadores y calibradores habituales estuvieron bloqueados.
- El baseline quedo fijado antes de apertura con 4,965 filas 2016–2024:
  lambda `2.1818731117824774`.

2025 fue utilizado una única vez como blind holdout y no se utilizó para modificar el modelo.

## Verificacion

- Suite completa antes de apertura: **377 passed in 21.23s**.
- Suite completa despues de evaluacion: **377 passed in 19.06s**.
- Son 340 tests previos y 37 nuevos, todos sinteticos en sus accesos a holdout.
- Revision independiente previa y revision de correcciones sin hallazgos pendientes.
- Tests de equivalencia de metricas con Fase 5, bootstrap reproducible, probabilidades
  y cola, thresholds, subgrupos independientes del outcome, artefacto inmutable,
  ausencia de fitting y prohibicion de repetir una apertura incluso despues de fallo.
- `pip check`: sin conflictos. JSON de resultados sin NaN/inf; hash de reporte
  coincide con el registro de finalizacion. Datos y binarios no entran en Git.

## Interpretacion y limites que acompanan al PASS

NLL mejora 1.638% y RPS 3.602% frente al baseline; los IC95 pareados de diferencias
son negativos: NLL [-0.049674, -0.007168], RPS [-0.048088, -0.008436]. Todos los
Brier tambien mejoran al baseline. Esto aporta evidencia bajo el bootstrap IID
de filas especificado; dependencia por partido/equipo/kicker podria ensanchar
los intervalos. No equivale a una garantia de rendimiento futuro o rentabilidad.

Respecto a 2024, NLL empeora 0.616% y RPS 0.518%. Brier >=4 empeora 12.311%,
aunque supera al baseline 2025 y su ECE es 0.015977. Ese cambio anual no se declara
significativo: mezcla temporadas y periodos de fitting distintos. No se uso
para cambiar modelo, parametros, cortes o criterios del gate.

Descanso corto (73 filas) muestra NLL 0.023905 mayor que su baseline: deterioro
puntual aproximado de 1.47%, por debajo de la alerta fijada. Lambda >=3 tiene
solo 19 filas; no permite conclusiones fuertes. Las 161 filas sin metricas
rolling5 de ofensiva/defensiva permanecen en la evaluacion con el preprocessing
congelado; no se eliminaron observaciones por resultados o informacion faltante.

No hay cambios de missingness >10 puntos porcentuales ni |SMD|>0.5 en el top15,
ni nuevas categorias game_type. Hay una observacion de EPA defensivo rolling5
fuera del rango de referencia, ademas de la extrapolacion calendario esperable
de season=2025 en las 570 filas.

La distribucion agregada sobreestima ceros (12.18% vs 10.53%) y 5+ (7.82% vs
6.67%), y subestima exactamente cuatro XPM (10.56% vs 13.16%). Se registran 16
casos extremos para diagnostico, no para tuning. Poblacion condicionada a
participacion observada del kicker; el producto recibe su identidad como entrada.

No se ajustaron calibradores, interceptos o slopes, no se usaron odds, no hubo
backtest financiero y no se inicio Fase 7.
