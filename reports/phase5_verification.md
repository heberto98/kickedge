# Verificacion Fase 5

Fecha: 2026-10-01. Entorno: Python 3.12.14, dependencias en `requirements.lock.txt`.

- Suite completa: **340 passed in 19.89s** (274 anteriores + 66 de modeling).
- Comando: `$env:LOKY_MAX_CPU_COUNT='1'; .venv/Scripts/python.exe -m pytest -q`.
- `pip check`: no hay dependencias incompatibles.
- Revision independiente y revision de correcciones: sin hallazgos pendientes.
  Se corrigio el veto metodologico de ECE y se reforzo el test de orquestacion.
  La politica original y su resultado siguen registrados junto a la enmienda.
- Fase 4 preservada: Parquet SHA-256
  `bb1730a0f957aea3dd86f22f5448858bf182cdbb39d8bf09ac238013f20ebb3f`;
  contrato SHA-256 `a8030cbf2224e3cebea5e48cd38b2559c154c73175881fdab5d7e8000caa8879`.
  Ambos coinciden con el build anterior; ninguna de las 82 features se reconstruyo.
- Los hashes de codigo y artefactos finales coinciden con `phase5_metrics.json`.
- TRAIN: 4,394 filas; VALIDATION: 571; refit: 4,965. Holdout: 570 filas,
  inspeccionado exclusivamente por schema/conteo. **Sin targets ni predicciones de 2025.**
- Pruebas de extremo a extremo: targets venenosos en 2025 sintetico no se leen;
  alterar solamente esas filas no cambia metricas, seleccion ni predicciones
  de los dos modelos guardados. Spies comprueban fitting y evaluacion antes de refit.
- Probabilidades no negativas, masa completa con cola, predicciones finitas,
  orden de filas invariante, mismo seed con predicciones identicas y recarga
  de artefacto con predicciones identicas. Ceros de target conservados.
- Rango de esperanza del GLM elegido sobre 2024: **1.221779–3.758346 XPM**.

## Comprobacion de contexto ofensivo

Diagnostico adicional con features de 2024 y el modelo seleccionado entrenado
hasta 2023; esta comprobacion no proyecto el target. Se agruparon observaciones
segun `offense_td_per_drive_before` disponible, sin cambiar ninguna feature:

| Grupo | Umbral | Filas | Esperanza XPM media |
|---|---:|---:|---:|
| Cuartil inferior | <=0.1682292123 | 135 | 1.8220897301 |
| Cuartil superior | >=0.2730823864 | 135 | 2.6326368426 |

Los NULL quedan fuera de este diagnostico, no del entrenamiento. Es una
asociacion descriptiva: los grupos tambien difieren en otros predictores.
No demuestra causalidad ni impone monotonia. Un test sintetico separado
comprueba que el GLM puede aprender una relacion ofensiva sin codificarla a mano.

La reproducibilidad determinista no demuestra estabilidad temporal o muestral;
no se cuantifico la incertidumbre del ranking. No se ejecutaron Fase 6,
calibracion formal, backtesting financiero ni nuevas consultas de fuentes.
