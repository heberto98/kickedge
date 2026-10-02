# Fase 7A: verificacion del motor de inferencia

Fecha: 2026-10-02. Base: `02c8edf`, Fase 6 publicada, PASS.

## Resultado

**469 tests aprobados: 377 previos + 92 nuevos**, sin fallos ni skips en este
workspace. Comando: `.venv/Scripts/python.exe -m pytest -q`; duracion 48.14 s.
La revision independiente termino PASS tras corregir dos hallazgos: inyeccion
de un predictor externo y division por masa no-push numericamente nula. Ambos
tienen pruebas de regresion que fallaron antes del arreglo y pasaron despues.

Las pruebas nuevas cubren contrato exacto/orden de las 82 features, targets y
campos extra rechazados, NULL/tipos, metadata separada, errores JSON/CLI sin eco
de entradas invalidas, artifact adulterado rechazado antes de deserializar,
modelo local aprobado, determinismo, distribucion y cola, lineas 1.5/2/2.5,
push, odds positivas/negativas, no-vig, overround, edge, fair odds, EV y fixture
reproducible. Los tests de inferencia bloquean fitting, conexiones y dotenv;
la suite previa conserva sus pruebas sinteticas de entrenamiento.

## Integridad y alcance

- GLM Poisson alpha=0.1, refit 2016–2024, 82 predictores sin cambios.
- Modelo final SHA-256:
  `c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0`.
- Todos los artifacts de Fase 5 registrados en metadata conservan sus hashes;
  tambien el codigo de modeling y el contrato de features.
- Sin modificaciones en `kickedge/features`, `kickedge/modeling` o
  `kickedge/validation`. No se reentreno el artifact, cambio alpha, recalibro,
  uso 2025 para fitting ni repitio el reveal real de Fase 6.
- Sin consultas de datos live, ParlayAPI, Open-Meteo, web ni lectura de `.env`.
  La unica operacion remota prevista es Git para publicar el trabajo autorizado.
- Dataset historico no reconstruido. Demo mediante proyeccion local restringida
  a 2024, identidades/tiempos y features, sin seleccionar el target.
- Datos, binarios, secretos, caches, entorno y reportes temporales siguen ignorados.

## Demo / test fixture

Brandon Aubrey, DAL vs SF, `2024_08_DAL_SF`. Precios **hipoteticos** Over +119,
Under -140 en ambos ejemplos; no representan un mercado observado. Lambda
`1.774292350651335` en ambos casos, cola P(X>12) `5.379582350402028e-08`.

| Resultado (lado Over) | Linea 2.5 | Linea 2.0 |
|---|---:|---:|
| P(Over) | 0.262505105 | 0.262505105 |
| P(Under) | 0.737494895 | 0.470529490 |
| P(Push) | 0 | 0.266965406 |
| Probabilidad comparable al precio | 0.262505105 | 0.358107389 |
| Implied +119 | 0.456621005 | 0.456621005 |
| No-vig Over | 0.439077936 | 0.439077936 |
| Overround | 0.039954338 | 0.039954338 |
| Edge raw (pp) | -19.411590 | -9.851362 |
| Edge no-vig (pp) | -17.657283 | -8.097055 |
| Fair American | +280.944973 | +179.245844 |
| EV por unidad | -0.425114 | -0.158148 |

Linea 2.0 usa **conditional on no push** para comparar precios y obtener fair
odds. El EV conserva probabilidades sin condicionar. Se reutiliza la implementacion
Poisson de Fase 5. Distribucion 0..12 mas cola y Over+Under+Push suman 1.

La fixture se reproduce dos veces con bytes iguales y coincide semanticamente
con el JSON versionado (independiente de LF/CRLF). No es evaluacion fuera de
muestra: 2024 pertenece al refit. No es prediccion actual ni recomendacion.

## Limites y cierre

La validacion estructural no acredita temporalidad ni identidad real de los
valores suministrados. `pregame_availability_verified=false` mantiene explicita
esa limitacion. No verifica que ambas cuotas provengan del mismo evento/book/time;
su timestamp opcional no acredita frescura. Fair odds extremas se representan
como null con razon cuando no hay precio finito. Lineas de cuarto no soportadas.

El artifact local aprobado y las versiones exactas de runtime son necesarios;
en otro checkout sin binarios, los tests que los requieren se omiten y el loader
bloquea inferencia. No se incluye modelo binario en Git.

**Fase 7A completa en su alcance offline. Fase 7B no iniciada.**
Contrato, formulas y comandos: [documentacion](../docs/inference_phase7a.md).
