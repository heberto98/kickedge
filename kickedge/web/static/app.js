'use strict';
// KickEdge client: collects the user's pick, calls /api/analyze and renders the
// engine's own numbers. No probability or price arithmetic is redone here.

const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v; // CSSOM: allowed under CSP
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const pct = (p, d = 1) => (p === null || p === undefined) ? '—' : (100 * p).toFixed(d) + '%';
const num = (x, d = 2) => (x === null || x === undefined) ? '—' : Number(x).toFixed(d);
const american = (x) => (x === null || x === undefined) ? '—' : (x > 0 ? '+' : '') + Math.round(x);
const signedPP = (x) => (x === null || x === undefined) ? '—' : (x > 0 ? '+' : '') + x.toFixed(1) + ' pp';

function parseOdds(text, name, required) {
  const t = (text || '').trim();
  if (!t) { if (required) throw new FieldError(name, 'American odds are required, e.g. +115 or -140.'); return null; }
  if (!/^[+-]?\d{3,5}$/.test(t)) throw new FieldError(name, 'Use American odds such as +115 or -140 (|odds| ≥ 100).');
  const v = parseInt(t, 10);
  if (Math.abs(v) < 100) throw new FieldError(name, 'American odds must be at least 100 in magnitude.');
  return v;
}

class FieldError extends Error { constructor(field, message) { super(message); this.field = field; } }

function collect(form) {
  const f = new FormData(form);
  const text = (k) => (f.get(k) || '').toString().trim();
  const body = {
    kicker: text('kicker'), team: text('team').toUpperCase(), opponent: text('opponent').toUpperCase(),
    side: text('side'), include_weather: f.has('include_weather'),
    include_market: f.has('include_market'), refresh_data: f.has('refresh_data'),
  };
  if (body.kicker.length < 2) throw new FieldError('kicker', 'Enter the kicker name or ID.');
  if (!/^[A-Z]{2,3}$/.test(body.team)) throw new FieldError('team', 'Use a team abbreviation such as TB.');
  if (!/^[A-Z]{2,3}$/.test(body.opponent)) throw new FieldError('opponent', 'Use a team abbreviation such as GB.');
  if (body.team === body.opponent) throw new FieldError('opponent', 'Team and opponent must differ.');
  const line = text('line');
  if (!/^\d{1,2}(\.[05])?$/.test(line)) throw new FieldError('line', 'XPM line must be a whole or half number, e.g. 2.5.');
  body.line = parseFloat(line);
  body.odds = parseOdds(text('odds'), 'odds', true);
  const over = parseOdds(text('over_odds'), 'over_odds', false);
  const under = parseOdds(text('under_odds'), 'under_odds', false);
  if ((over === null) !== (under === null)) throw new FieldError(over === null ? 'over_odds' : 'under_odds', 'Supply both Over and Under odds, or neither.');
  if (over !== null) {
    if ((body.side === 'over' ? over : under) !== body.odds) throw new FieldError('odds', 'Odds must equal the selected side of the paired quote.');
    body.over_odds = over; body.under_odds = under;
  }
  for (const k of ['season', 'week']) {
    const v = text(k);
    if (v) { if (!/^\d{1,4}$/.test(v)) throw new FieldError(k, 'Must be a whole number.'); body[k] = parseInt(v, 10); }
  }
  const gid = text('game_id').toUpperCase();
  if (gid) { if (!/^\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}$/.test(gid)) throw new FieldError('game_id', 'Format: 2026_04_GB_TB.'); body.game_id = gid; }
  return body;
}

const ERROR_TITLES = {
  GAME_NOT_FOUND: 'Game not found', GAME_AMBIGUOUS: 'Ambiguous game', KICKER_NOT_FOUND: 'Kicker not found',
  KICKER_AMBIGUOUS: 'Ambiguous kicker', NFL_SOURCE_UNAVAILABLE: 'NFL data source unavailable',
  STALE_DATA: 'Data not usable for this kickoff', GAME_STARTED: 'Game already started or too close to kickoff',
  MODEL_NOT_READY: 'Model not ready', INVALID_ODDS: 'Invalid odds', INVALID_LINE: 'Invalid line',
  RATE_LIMITED: 'Too many requests', INVALID_REQUEST: 'Invalid request', INTERNAL_ERROR: 'Unexpected error',
};
const ERROR_HINTS = {
  GAME_NOT_FOUND: 'Check the team abbreviations and season. Only upcoming games can be analyzed.',
  GAME_AMBIGUOUS: 'More than one upcoming meeting matches. Add the week or game ID under Advanced.',
  KICKER_NOT_FOUND: 'Use the full name as listed by nflverse, or the stable player ID.',
  KICKER_AMBIGUOUS: 'Several players match this name. Use the stable player ID (e.g. 00-0035358).',
  NFL_SOURCE_UNAVAILABLE: 'Required NFL data could not be downloaded or verified. Try again later.',
  STALE_DATA: 'Cached sources are newer than the pregame cutoff; analysis would not be pregame.',
  MODEL_NOT_READY: 'The frozen model artifact is missing or failed verification. No analysis was run.',
};

function showError(code, message) {
  const box = $('error');
  box.replaceChildren(
    h('h2', {}, ERROR_TITLES[code] || 'Error'),
    h('p', {}, message),
    ERROR_HINTS[code] ? h('p', { class: 'muted' }, ERROR_HINTS[code]) : null,
    h('p', { class: 'code' }, code));
  box.hidden = false;
  box.focus();
}

function markField(field, message) {
  const input = $(field);
  if (!input) { showError('INVALID_REQUEST', message); return; }
  if (input.closest('details')) input.closest('details').open = true;
  input.setAttribute('aria-invalid', 'true');
  const hint = h('p', { class: 'field-error', id: field + '-err' }, message);
  input.setAttribute('aria-describedby', hint.id);
  input.after(hint);
  input.focus();
}

function clearErrors() {
  $('error').hidden = true;
  document.querySelectorAll('.field-error').forEach((e) => e.remove());
  document.querySelectorAll('[aria-invalid]').forEach((e) => { e.removeAttribute('aria-invalid'); e.removeAttribute('aria-describedby'); });
}

// ---------- rendering ----------

const KEY_DATA = [
  ['Kicker', [
    ['kicker_xpm_before', 'XPM season-to-date', 0], ['kicker_xpa_before', 'XPA season-to-date', 0],
    ['kicker_xp_conversion_rate_before', 'Conversion rate', 'pct'], ['kicker_xpm_per_game_before', 'XPM per game', 2],
    ['kicker_xpm_per_game_last_3', 'XPM per game, last 3', 2], ['kicker_xpm_per_game_last_5', 'XPM per game, last 5', 2],
    ['previous_game_xpm', 'Previous game XPM', 0], ['days_since_last_game', 'Days since last game', 1],
    ['kicker_games_before', 'Games in history', 0]]],
  ['Offense', [
    ['offense_points_per_game_before', 'Points per game', 1], ['offense_touchdowns_per_game_before', 'TD per game', 2],
    ['offense_td_per_drive_before', 'TD per drive', 3], ['offense_red_zone_td_rate_before', 'Red-zone TD rate', 'pct'],
    ['offense_epa_per_play_before', 'EPA per play', 3], ['offense_success_rate_before', 'Success rate', 'pct'],
    ['offense_points_per_game_last_3', 'Points per game, last 3', 1], ['offense_points_per_game_last_5', 'Points per game, last 5', 1]]],
  ['Opponent defense', [
    ['defense_points_allowed_per_game_before', 'Points allowed per game', 1], ['defense_touchdowns_allowed_per_game_before', 'TD allowed per game', 2],
    ['defense_td_allowed_per_drive_before', 'TD allowed per drive', 3], ['defense_red_zone_td_rate_allowed_before', 'Red-zone TD rate allowed', 'pct'],
    ['defense_epa_allowed_per_play_before', 'EPA allowed per play', 3], ['defense_success_rate_allowed_before', 'Success rate allowed', 'pct'],
    ['defense_points_allowed_per_game_last_3', 'Points allowed, last 3', 1], ['defense_points_allowed_per_game_last_5', 'Points allowed, last 5', 1]]],
  ['Game context', [
    ['is_home', 'Home game', 'bool'], ['week', 'Week', 0], ['game_type', 'Game type', 'text'],
    ['team_days_rest', 'Team days of rest', 1], ['opponent_days_rest', 'Opponent days of rest', 1],
    ['team_short_week_flag', 'Team short week', 'bool'], ['team_long_rest_flag', 'Team long rest', 'bool'],
    ['team_two_point_attempt_rate_before', '2-pt attempt rate', 'pct']]],
];

function fmt(v, kind) {
  if (v === null || v === undefined) return 'Not available';
  if (kind === 'pct') return pct(v, 1);
  if (kind === 'bool') return v ? 'Yes' : 'No';
  if (kind === 'text') return String(v);
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return typeof v === 'number' ? Number(v).toFixed(kind) : String(v);
}

function stat(label, value, cls) {
  return h('div', { class: 'stat ' + (cls || '') }, h('span', { class: 'stat-label' }, label), h('span', { class: 'stat-value' }, value));
}

function chip(state) {
  const cls = { Verified: 'ok', Available: 'ok', Warning: 'warn', Unavailable: 'off', 'Not verified': 'warn', 'Not requested': 'off' }[state] || 'off';
  return h('span', { class: 'chip ' + cls }, state);
}

function distribution(r) {
  const p = r.prediction.distribution.probabilities;
  const bins = [0, 1, 2, 3, 4].map((k) => [String(k), p[k]]);
  bins.push(['5+', p.slice(5).reduce((a, b) => a + b, 0) + r.prediction.distribution.tail_probability]);
  const max = Math.max(...bins.map((b) => b[1]));
  const line = r.prop.line;
  const label = bins.map(([k, v]) => `${k} XPM: ${pct(v)}`).join('; ');
  return h('section', { class: 'card', 'aria-labelledby': 'dist-h' },
    h('h2', { id: 'dist-h' }, 'XPM distribution'),
    h('p', { class: 'muted' }, `Poisson distribution around expected XPM ${num(r.prediction.expected_xpm)}. Highlighted bars are counts above the line (Over ${line}).`),
    h('div', { class: 'bars', role: 'img', 'aria-label': 'Probability by XPM count. ' + label },
      bins.map(([k, v], i) => {
        const value = i === 5 ? 5 : i;
        const over = value > line;
        return h('div', { class: 'bar' + (over ? ' over' : '') },
          h('span', { class: 'bar-val' }, pct(v)),
          h('span', { class: 'bar-fill', style: `height:${Math.max(2, 100 * v / max).toFixed(1)}%` }),
          h('span', { class: 'bar-k' }, k));
      })),
    h('details', {}, h('summary', {}, 'Distribution values 0–12'),
      h('div', { class: 'scroll' }, h('table', {},
        h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'XPM'), h('th', { scope: 'col' }, 'Probability'))),
        h('tbody', {}, p.map((v, k) => h('tr', {}, h('td', {}, k), h('td', {}, pct(v, 3)))),
          h('tr', {}, h('td', {}, '> 12'), h('td', {}, pct(r.prediction.distribution.tail_probability, 5))))))));
}

function hero(r) {
  const prop = r.prop, side = prop.side, sideName = side === 'over' ? 'Over' : 'Under';
  const integer = Number.isInteger(prop.line);
  return h('section', { class: 'card hero', 'aria-labelledby': 'hero-h' },
    h('div', { class: 'hero-id' },
      h('h2', { id: 'hero-h' }, r.player.kicker_name),
      h('p', { class: 'muted' }, `${r.game.team} ${r.game.is_home ? 'vs' : '@'} ${r.game.opponent} · ${r.game.game_id} · kickoff ${new Date(r.game.kickoff).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`)),
    h('div', { class: 'hero-main' },
      h('div', { class: 'pick' }, h('span', { class: 'eyebrow' }, 'Your pick'),
        h('span', { class: 'pick-text' }, `${sideName} ${prop.line} XPM`),
        h('span', { class: 'muted' }, `at ${american(r.market.american_odds)}`)),
      h('div', { class: 'prob' }, h('span', { class: 'eyebrow' }, 'KickEdge probability'),
        h('span', { class: 'prob-value', id: 'pick-probability' }, pct(prop.model_side_probability)),
        h('span', { class: 'muted' }, `that ${sideName} ${prop.line} settles as a win`)),
      h('div', { class: 'prob' }, h('span', { class: 'eyebrow' }, 'Expected XPM'),
        h('span', { class: 'prob-value small' }, num(r.prediction.expected_xpm)))),
    h('div', { class: 'stats' },
      stat('P(Over)', pct(prop.p_over), side === 'over' ? 'sel' : ''),
      stat('P(Under)', pct(prop.p_under), side === 'under' ? 'sel' : ''),
      integer ? stat('P(Push)', pct(prop.p_push), 'push') : null));
}

function keyData(r) {
  const f = r.features;
  return h('section', { class: 'card', 'aria-labelledby': 'saw-h' },
    h('h2', { id: 'saw-h' }, 'What KickEdge saw'),
    h('p', { class: 'muted' }, 'Selected model inputs from the pregame snapshot. These are data the model used, not causal explanations.'),
    h('div', { class: 'groups' }, KEY_DATA.map(([title, rows]) => h('div', { class: 'group' },
      h('h3', {}, title),
      h('dl', {}, rows.map(([k, label, kind]) => [h('dt', {}, label), h('dd', { class: f[k] === null ? 'na' : '' }, fmt(f[k], kind))]))))),
    h('details', {}, h('summary', {}, `View all ${Object.keys(f).length} model inputs`),
      h('div', { class: 'scroll' }, h('table', { class: 'inputs' },
        h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, '#'), h('th', { scope: 'col' }, 'Input'), h('th', { scope: 'col' }, 'Value'))),
        h('tbody', {}, Object.entries(f).map(([k, v], i) => h('tr', {}, h('td', {}, i + 1), h('td', { class: 'mono' }, k),
          h('td', { class: v === null ? 'na' : '' }, v === null ? 'NULL (frozen imputer)' : (typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(4) : String(v)))))))),
      h('p', { class: 'muted' }, 'NULL inputs are handled by the frozen preprocessing pipeline (median imputation with missing-value indicators).')));
}

function quality(r) {
  const q = r.data_quality, fresh = q.source_data_freshness || [];
  const oldest = fresh.length ? Math.max(...fresh.map((s) => s.age_seconds)) : null;
  const latest = q.latest_game_used;
  const rows = [
    ['Target game', q.target_game_verified ? 'Verified' : 'Unavailable', r.game.game_id],
    ['Kicker identity', q.kicker_identity_verified ? 'Verified' : 'Unavailable', r.player.kicker_id],
    ['Current team affiliation', q.kicker_current_team_verified ? 'Verified' : 'Not verified', 'No roster source is used'],
    ['Feature schema', q.feature_schema_verified ? 'Verified' : 'Unavailable', `${q.feature_count}/82 inputs, frozen order`],
    ['Frozen model', q.model_verified ? 'Verified' : 'Unavailable', 'SHA-256 checked before loading'],
    ['Source age', oldest !== null && oldest > 6 * 3600 ? 'Warning' : 'Available', oldest === null ? '—' : `${(oldest / 3600).toFixed(1)} h (oldest source)`],
    ['Latest completed game used', latest ? 'Available' : 'Unavailable', latest ? latest.game_id : 'No prior games this season'],
    ['Nullable inputs', q.null_feature_count ? 'Warning' : 'Available', `${q.null_feature_count} handled by frozen imputer`],
    ['Market context', !q.market_requested ? 'Not requested' : (q.market_availability ? 'Available' : 'Unavailable'), 'Context only'],
    ['Weather context', !q.weather_requested ? 'Not requested' : (q.weather_availability ? 'Available' : 'Unavailable'), 'Context only'],
  ];
  return h('section', { class: 'card', 'aria-labelledby': 'dq-h' },
    h('h2', { id: 'dq-h' }, 'Data quality'),
    h('ul', { class: 'dq' }, rows.map(([label, state, detail]) => h('li', {}, h('span', {}, label), chip(state), h('span', { class: 'muted' }, detail)))));
}

function warnings(r) {
  const list = r.data_quality.warnings || [];
  if (!list.length) return null;
  return h('section', { class: 'card notes', 'aria-labelledby': 'w-h' },
    h('h2', { id: 'w-h' }, `Notes and warnings (${list.length})`),
    h('ul', {}, list.map((w) => h('li', {}, w))));
}

function market(r) {
  const m = r.market, a = r.analysis, p = r.prop;
  const conditional = p.price_probability_basis !== 'direct';
  const kp = conditional ? p.model_probability_conditional : p.model_side_probability;
  return h('section', { class: 'card', 'aria-labelledby': 'mk-h' },
    h('h2', { id: 'mk-h' }, 'Market comparison'),
    conditional ? h('p', { class: 'muted' }, 'Integer line: price comparison is conditional on no push.') : null,
    h('div', { class: 'stats' },
      stat('American odds', american(m.american_odds)),
      stat('Market implied probability', pct(m.implied_probability)),
      stat('KickEdge probability' + (conditional ? ' (no push)' : ''), pct(kp)),
      stat('Probability difference', signedPP(a.edge_raw_pp)),
      stat('Model fair odds', a.fair_odds.american === null ? '—' : american(a.fair_odds.american)),
      m.no_vig_probability !== null ? stat('No-vig market probability', pct(m.no_vig_probability)) : null,
      m.overround !== null ? stat('Overround', pct(m.overround, 2)) : null,
      a.edge_novig_pp !== null ? stat('Difference vs no-vig', signedPP(a.edge_novig_pp)) : null),
    h('details', {}, h('summary', {}, 'Mathematical price comparison'),
      h('p', {}, `Expected value per 1 unit under model assumptions: ${num(a.expected_value_per_unit, 3)} units.`),
      h('p', { class: 'muted' }, 'This is a mathematical output based on the model probability, not a betting recommendation.')));
}

function contextValues(values) {
  const entries = Object.entries(values || {}).filter(([, v]) => v !== null && v !== undefined);
  if (!entries.length) return h('p', { class: 'muted' }, 'No values.');
  return h('dl', {}, entries.map(([k, v]) => [h('dt', {}, k.replace(/_/g, ' ')), h('dd', {}, typeof v === 'number' ? num(v, 1) : String(v))]));
}

function context(r) {
  const w = r.context.weather || {}, mk = r.context.market || {};
  const tag = h('span', { class: 'tag' }, 'Context only — not currently used by the probability model');
  return h('section', { class: 'card', 'aria-labelledby': 'cx-h' },
    h('h2', { id: 'cx-h' }, 'Game context'), tag,
    h('div', { class: 'groups' },
      h('div', { class: 'group' }, h('h3', {}, 'Weather'),
        w.available ? contextValues(w.values) : h('p', { class: 'muted' },
          r.data_quality.weather_requested ? 'Weather data unavailable.' : 'Weather not requested.'),
        h('p', { class: 'muted' }, `Roof: ${r.game.roof || 'unknown'} · Venue: ${r.game.venue || 'unknown'}`)),
      h('div', { class: 'group' }, h('h3', {}, 'Market'),
        mk.available ? h('div', { class: 'scroll' }, h('table', {},
          h('thead', {}, h('tr', {}, ['Book', 'Spread (team)', 'Total', 'ML team', 'ML opp.'].map((t) => h('th', { scope: 'col' }, t)))),
          h('tbody', {}, (mk.quotes || []).map((q) => h('tr', {}, h('td', {}, (q.provenance || {}).bookmaker || '—'),
            h('td', {}, num(q.values.game_spread, 1)), h('td', {}, num(q.values.game_total, 1)),
            h('td', {}, american(q.values.moneyline_team)), h('td', {}, american(q.values.moneyline_opponent))))))) : h('p', { class: 'muted' },
          r.data_quality.market_requested ? 'Market data unavailable.' : 'Market context not requested.'))));
}

function details(r) {
  const pv = r.provenance, fp = pv.features;
  const kv = [['Analysis generated', pv.analysis_generated_at], ['Snapshot generated', fp.generated_at],
    ['Target kickoff', fp.target_kickoff], ['Feature cutoff', fp.cutoff],
    ['Latest game used', fp.latest_game_used ? fp.latest_game_used.game_id : 'none'],
    ['Feature schema version', fp.feature_schema_version], ['Model version', pv.model_version],
    ['Model artifact SHA-256', r.model.artifact_sha256], ['Snapshot SHA-256', pv.feature_snapshot_sha256]];
  return h('details', { class: 'card' }, h('summary', {}, 'Data details'),
    h('dl', { class: 'mono-dl' }, kv.map(([k, v]) => [h('dt', {}, k), h('dd', { class: 'mono' }, v || '—')])),
    h('h3', {}, 'Sources'),
    h('div', { class: 'scroll' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Dataset', 'Provider', 'Fetched at', 'SHA-256'].map((t) => h('th', { scope: 'col' }, t)))),
      h('tbody', {}, (fp.sources || []).map((s) => h('tr', {}, h('td', {}, s.dataset), h('td', {}, s.provider || '—'),
        h('td', { class: 'mono' }, s.fetched_at || '—'), h('td', { class: 'mono' }, (s.sha256 || '').slice(0, 16) + '…')))))),
    h('p', { class: 'muted' }, `History games used: ${(fp.history_games || []).map((g) => g.game_id).join(', ') || 'none'}`));
}

function render(r) {
  const box = $('result');
  box.replaceChildren(hero(r), distribution(r), keyData(r), quality(r), warnings(r) || '', market(r), context(r), details(r));
  box.hidden = false;
  box.querySelector('h2').setAttribute('tabindex', '-1');
  box.querySelector('h2').focus();
}

async function submit(event) {
  event.preventDefault();
  const form = event.currentTarget, button = $('submit'), status = $('status');
  if (button.disabled) return;
  clearErrors();
  let body;
  try { body = collect(form); } catch (e) { if (e instanceof FieldError) { markField(e.field, e.message); return; } throw e; }
  button.disabled = true; form.setAttribute('aria-busy', 'true');
  button.textContent = 'Analyzing…';
  status.textContent = 'Analyzing… loading NFL data, building the pregame snapshot and running the model.';
  try {
    const res = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data) {
      const err = (data && data.error) || { code: 'INTERNAL_ERROR', message: `Request failed (${res.status}).` };
      $('result').hidden = true;
      showError(err.code, err.message);
      status.textContent = '';
    } else {
      render(data);
      status.textContent = 'Analysis complete.';
    }
  } catch (e) {
    showError('NETWORK', 'The server could not be reached. Check your connection and try again.');
    status.textContent = '';
  } finally {
    button.disabled = false; form.removeAttribute('aria-busy'); button.textContent = 'Analyze pick';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const form = $('pick');
  if (form) form.addEventListener('submit', submit);
  const err = $('error');
  if (err) err.setAttribute('tabindex', '-1');
});
