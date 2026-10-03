# KickEdge: polish final (cuotas decimales y selecciones múltiples)

Fecha: 2026-10-03. Base: `ad0bc89`. Sin cambios en el modelo, las 82 features, los
builders, el corte temporal, la paridad histórica, alpha ni la calibración. La
probabilidad de una selección para un mismo snapshot no cambia.

## Migración a cuotas decimales

- **Precio de primera clase en la capa de precios** (`kickedge/inference/odds.py`):
  `validate_decimal_odds` (finito y > 1), `decimal_implied_probability` (1/d),
  `decimal_profit_per_unit` (d − 1), `decimal_no_vig` (misma semántica que la
  versión americana: q = 1/d, overround = q_over + q_under − 1, normalización),
  `fair_decimal_odds` (1/p; p = 0 sin precio finito) y `american_to_decimal`
  (+A → 1 + A/100, −A → 1 + 100/A) para análisis legacy.
- `analyze_prop(..., odds_format='american'|'decimal')`: la liquidación (P(Over),
  P(Under), P(Push), win/loss, condicional a no-push) es común y no depende del
  formato. La salida americana conserva exactamente las mismas claves, valores y
  orden; la decimal usa `odds_format`, `decimal_odds`, `over_decimal_odds`,
  `under_decimal_odds` y `fair_odds.decimal`. EV por unidad = p_win·(d − 1) − p_loss
  (push aporta 0). En líneas enteras la cuota justa usa p_win/(p_win + p_loss).
- `inference.engine.analyze` y `current.engine.analyze_current_prop` reciben el
  formato y lo pasan; el cálculo del modelo (lambda, distribución) no se toca.
- La interfaz usa solo cuotas decimales (`type=number`, `step=0.01`, mínimo > 1,
  placeholder 1.91; `1.8`/`2` se muestran como `1.80`/`2.00` sin redondear dígitos
  extra). Cuota justa del modelo en decimal.

## Compatibilidad

- La API sigue aceptando cuotas americanas (`odds`, `over_odds`, `under_odds`) y
  rechaza mezclar formatos (`INVALID_ODDS`). La CLI 7A/7B sigue siendo americana.
- Los análisis guardados antes de este cambio se abren igual: se muestran como
  "legacy US" con su equivalente decimal (también en Recent analyses). No se
  migró ni borró ningún análisis.
- Las moneylines del contexto de mercado se muestran en el formato del análisis
  (decimal en análisis nuevos, americano en los legacy).

## Single pick

Se conserva todo (selectores, clima, roster, calidad de datos, What KickEdge saw,
distribución, comparación de precio, recientes, provenance). Cambios: cuota
decimal, párrafo **Statistical feedback** bajo la probabilidad y **sin selector de
equipo redundante**: el equipo sale del kicker elegido y se muestra como dato
("Los Angeles Rams · Active roster"). Si se escribe un kicker a mano con un partido
elegido, el servidor deriva el equipo (`resolve_kicker_team`: roster nflverse de la
temporada; si no, el equipo con el que pateó esta temporada). Solo si no puede,
responde `KICKER_TEAM_UNRESOLVED` con los dos equipos y la interfaz pide elegirlo
una vez. Advanced conserva la entrada manual (equipo/rival, temporada, semana,
game id, cuotas de ambos lados).

## Multiple selections

- Pestañas accesibles "Single pick" / "Multiple selections" (flechas, Home/End).
- 2 a 10 selecciones; "+ Add selection" (se desactiva en 10) y "Remove" (oculto en
  el mínimo de 2); numeración automática y renumeración al quitar sin perder datos.
  Cada selección: partido, kicker (equipo derivado), Over/Under, línea, cuota
  decimal; Advanced por selección: cuota del otro lado y equipos manuales.
- `POST /api/analyze-multi` valida 2–10 selecciones, cuotas decimales > 1, líneas,
  lados y campos (extra prohibidos). Los errores de validación nombran la selección
  (`selections.1.decimal_odds`) y se muestran en su tarjeta.
- **Mismo pipeline**: cada selección llama a `analyze_current_prop` exactamente como
  Single (mismo snapshot de 82 features, mismo modelo). Test: la selección 1 de una
  combinada es idéntica (predicción, probabilidades, features, mercado y análisis)
  al Single equivalente.
- Eficiencia: una carga verificada de datos NFL por temporada y por petición; el
  contexto de clima se consulta una vez por partido (el mercado no se pide en multi).
- Fallos: una selección con error crítico se marca ("Selection 2 failed:
  KICKER_NOT_FOUND") y el combinado queda **no disponible**; nunca se combina un
  subconjunto. Clima/mercado opcionales nunca bloquean.
- Cada combinada exitosa se guarda en `data/current/analyses/<sha256>/multi.json`
  (selecciones, probabilidades, cuotas, combinado, avisos) y aparece en Recent
  analyses; reabrirla no ejecuta nada (`GET /api/multi/{id}`).

### Resumen combinado (`kickedge/current/multi.py`)

- Cuota decimal combinada = ∏ dᵢ (1.50 × 1.40 = 2.10).
- Probabilidad implícita combinada = 1 / cuota combinada (2.10 → 47.62 %).
- Probabilidad aproximada de KickEdge = ∏ p_winᵢ, rotulada siempre como
  **independence approximation** ("Approximate combined probability assuming
  independent selections"). KickEdge no modela correlación.
- Mismo partido: detectado por `game_id` canónico (no por texto). Aviso visible:
  "These selections belong to the same game. KickEdge does not currently model
  correlation between legs. The combined probability shown is an independence
  approximation and may be materially inaccurate." Cada tarjeta indica con qué
  selección comparte partido.
- Push: cada selección conserva p_win, p_loss, p_push. El combinado informa la
  probabilidad de que todas ganen (∏ p_win) y la de no perder ninguna
  (∏ (p_win + p_push)), con el aviso "Integer lines can push. Combined settlement
  varies by sportsbook…". No se inventa una cuota ajustada por push ni un no-vig
  combinado.

## Feedback estadístico

Texto automático y neutral, en Single, en cada selección y en el combinado:
"At decimal odds 1.30, the price implies 76.9%. KickEdge estimates 64.5%. The model
estimate is 12.4 percentage points lower than the probability implied by the price
(-12.4 pp)." Con |diferencia| < 1 pp: "The two estimates are very close". Las
diferencias llevan signo, texto ("model higher/lower", "very close") y símbolo; no
dependen del color. Nunca se usan "value", "good/bad price", "bet", ni similares.

## QA real (servidor local, datos nflverse en vivo, Edge headless; cuotas **hipotéticas**)

| Prueba | Resultado |
|---|---|
| Single 1280×900: Rams @ Eagles, Harrison Mevis, Over 1.5, 1.30 | Equipo derivado (sin selector); KickEdge 64.5 %, implícita 76.9 %, −12.4 pp, cuota justa 1.55 |
| Multi 3: Cam Little O1.5 @1.35, Brandon Aubrey O1.5 @1.40, Mevis O1.5 @1.30 | 69.2 % vs 74.1 % (−4.8 pp); 71.7 % vs 71.4 % (+0.3, "very close"); 64.5 % vs 76.9 % (−12.4); combinada 2.46, implícita 40.7 %, aproximación 32.1 %, −8.6 pp |
| Mismo partido: Mevis O1.5 @1.30 + Jake Elliott O2.5 @1.85 | Aviso de correlación con `2026_04_LA_PHI`; combinada 2.41, implícita 41.6 %, aproximación 21.9 % |
| Multi 4 (las 3 + Elliott) | Aviso de mismo partido; combinada 4.55, implícita 22.0 % |
| Móvil 390×844: Multi (Little + Mevis) y Single | Tarjetas apiladas, Add/Analyze visibles, combinada 1.76 / 57.0 % / 44.7 %; Single 64.5 % |

La selección de Mevis da el mismo 64.5 % en Single y en todas las combinadas. Sin
scroll horizontal en ninguna captura. Recent analyses lista las combinadas y los
análisis legacy americanos con su equivalente decimal. Corregido en QA: el título de
cada selección salía en mayúsculas por especificidad CSS.

## Tests

**685 aprobados: 619 previos + 66 nuevos**, 0 fallos.

- `tests/test_decimal_multi.py` (61): implícita decimal (2.00, 1.50, 1.91, 2.50),
  beneficio, cuota justa, inválidas (1, 0, negativa, NaN, inf, bool, texto),
  conversión legacy, no-vig, liquidación idéntica en ambos formatos, fixture 7A
  idéntica en ambos formatos, equipo derivado y no resoluble, combinado de 2 y 3
  selecciones, mismo partido, push, límites, API Single decimal/legacy/inválidas,
  multi = single, una carga de datos y un clima por partido, etiqueta de
  independencia, push, selección inválida bloquea el combinado, 1/2/10/11
  selecciones, campos inválidos por selección, guardado/listado/reapertura sin
  re-ejecución, listado legacy con conversión.
- `tests/test_multi_frontend.py` (5, `index.html` + `app.js` reales en Edge
  headless): pestañas con teclado, añadir/quitar/renumerar sin perder datos y
  máximo 10, flujo multi completo (equipos derivados, cuotas decimales, combinado
  renderizado), aviso de mismo partido, selección fallida y push, dirección y
  valores del feedback (+5.0 pp / −6.0 pp / "very close"), y equipo pedido solo
  cuando no se puede derivar.
- Tests previos actualizados por cambios de comportamiento pedidos explícitamente
  (no para ocultar fallos): en `tests/test_web_polish_frontend.py`, los dos flujos
  de interfaz ahora escriben cuotas decimales (antes americanas) y verifican que no
  existe selector de equipo y que el equipo enviado sale del kicker (antes leían el
  radio "Kicker's team", eliminado). El resto de sus aserciones no cambió. Los 5
  tests de interfaz de 7C siguen pasando sin cambios (renderizan análisis legacy).

## Integridad

- `model.joblib` SHA-256 `c2f8f5ff00712546023b769a7c8374478399b7d00e343dc4e5e928c10977f0d0`;
  metadata canónica `1365f870…6a32`; `contract.json` `a8030cbf…8879`;
  `release.json` sin cambios; alpha 0.1; refit 2016–2024; 82 features en el mismo orden.
- Fixture 7A: lambda `1.774292350651335`, P(Over 2.5) `0.2625051047104534`, cola
  `5.379582350402028e-08`, idénticos bit a bit (también con el precio en decimal).
- `git diff ad0bc89` vacío en `kickedge/features`, `modeling`, `validation`,
  `providers`, `transform.py`, `build.py`, `current/sources.py`, `current/catalog.py`,
  `current/optional.py`, `models/` y `render.yaml`. En `inference` solo se añadió el
  formato decimal a la capa de precios y su paso por `analyze` (salida americana idéntica).
- Paridad histórica de los 16 casos 2024 × 82 features: pasa en la suite.

## Limitaciones

- La probabilidad combinada es una aproximación de independencia; KickEdge no
  modela correlación entre selecciones (especialmente del mismo partido).
- Con líneas enteras, la liquidación de combinadas depende de cada casa; se informa
  "todas ganan" y "ninguna pierde", no la liquidación de cada sportsbook.
- No hay no-vig combinado; el no-vig existe solo por selección cuando se dan ambos lados.
- El contexto de mercado (ParlayAPI) no se pide en el modo múltiple.
- La CLI conserva cuotas americanas.
