# Fase 7B: verificacion

Fecha: 2026-10-03. Base: `9a9cd7f` (7A).

## Resultado

**522 tests aprobados: 469 previos + 53 nuevos**, 0 fallos, 0 skips
(`.venv/Scripts/python.exe -m pytest -q`, 39.9 s). Nuevos: sources 11,
optional, snapshot, engine, cli y paridad historica (16 casos x 82 features).

## Integridad

- Modelo `data/models/phase5/model.joblib` SHA-256
  `c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0` (sin cambios).
- `git diff 9a9cd7f` vacio en `kickedge/features`, `modeling`, `validation`,
  `inference`, `providers`, `transform.py`, `build.py`. Unico cambio fuera de
  `kickedge/current`: despacho del subcomando `analyze` en `kickedge/__main__.py`.
- Sin retrain, recalibracion ni cambio de alpha/features. Datos, caches,
  analisis y `.env` siguen ignorados.

## Demo live (2026-10-03 08:10 UTC)

Chase McLaughlin, TB vs GB, `2026_04_GB_TB`, kickoff 2026-10-04 17:00 UTC.
Cache nflverse 2026 (49 partidos completados). Ultimo partido usado
`2026_03_MIN_TB`. 82 features, NULLs de rolling-5 por historia corta (3 juegos)
imputados por el imputer congelado. Prop **manual hipotetica** Over 2.5 +115 /
Under -145: lambda 2.042090, P(Over)=0.334714, EV -0.280364 por unidad.

- ParlayAPI: HTTP 500 del proveedor, un intento, sin reintentos -> warning,
  continua con prop manual.
- Open-Meteo: no consultado; schedule sin coordenadas de venue -> warning.
- Mercado general: no disponible (mismo fallo de ParlayAPI).

## Limitaciones

- Afiliacion actual y participacion del kicker no verificadas (sin fuente de
  rosters/depth charts aprobada).
- Clima inutilizable hasta tener coordenadas de venue verificadas.
- Compuerta de 24 h es conservadora: partidos de las ultimas 24 h antes del
  cutoff se excluyen con warning.
- Cuotas automaticas dependen de la disponibilidad de ParlayAPI.
