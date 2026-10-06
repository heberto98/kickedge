'use strict';
// KickEdge client: single and multiple XPM selections. Prices are entered as
// decimal odds; every probability, price comparison and combined figure comes
// from the server (7A/7B engine). This file only collects input and displays.

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

const has = (x) => x !== null && x !== undefined;
const pct = (p, d = 1) => has(p) ? (100 * p).toFixed(d) + '%' : '—';
const num = (x, d = 2) => has(x) ? Number(x).toFixed(d) : '—';
const dec = (x) => has(x) ? Number(x).toFixed(2) : '—';
const american = (x) => has(x) ? (x > 0 ? '+' : '') + Math.round(x) : '—';
const signedPP = (x) => has(x) ? (x > 0 ? '+' : '') + x.toFixed(1) + ' pp' : '—';
const signed = (x, d) => (x > 0 ? '+' : x < 0 ? '−' : '±') + Math.abs(x).toFixed(d);
const americanToDecimal = (a) => a > 0 ? 1 + a / 100 : 1 + 100 / -a;

function kickoffLabel(iso, short) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const day = d.toLocaleDateString('en-US', { weekday: short ? 'short' : 'long', month: 'short', day: 'numeric' });
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return short ? `${day} · ${time}` : `${day} — ${time}`;
}
const localTime = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); };

class FieldError extends Error { constructor(field, message) { super(message); this.field = field; } }

function parseDecimal(text, field, required) {
  const t = (text || '').trim().replace(',', '.');
  if (!t) { if (required) throw new FieldError(field, 'Decimal odds are required, e.g. 1.91.'); return null; }
  if (!/^\d{1,4}(\.\d{1,4})?$/.test(t)) throw new FieldError(field, 'Use decimal odds such as 1.30, 1.91 or 2.50.');
  const v = parseFloat(t);
  if (!(v > 1)) throw new FieldError(field, 'Decimal odds must be greater than 1.00.');
  if (v > 1000) throw new FieldError(field, 'Decimal odds must be at most 1000.');
  return v;
}

function parseLine(text, field) {
  const t = (text || '').trim();
  if (!/^\d{1,2}(\.[05])?$/.test(t)) throw new FieldError(field, 'XPM line must be a whole or half number, e.g. 1.5.');
  return parseFloat(t);
}

// Show 1.8 as 1.80 and 2 as 2.00 without ever rounding extra digits away.
function normalizeDecimalInput(input) {
  const t = input.value.trim();
  if (/^\d{1,4}(\.\d{0,2})?$/.test(t) && parseFloat(t) > 1) input.value = parseFloat(t).toFixed(2);
}

// ---------- shared game catalog ----------

const catalog = { games: [], loaded: false, season: null, error: null, pickers: new Set() };
const nickname = (teams, code) => (teams && teams[code] && teams[code].nickname) || code;
const teamName = (teams, code) => (teams && teams[code] && teams[code].name) || code;

async function loadGames() {
  try {
    const res = await fetch('/api/games');
    const data = await res.json();
    if (!res.ok) throw new Error(data && data.error ? data.error.message : 'Games unavailable');
    catalog.games = data.games.map((g) => ({ ...g, search: g.search.toLowerCase() }));
    catalog.season = data.season;
    catalog.error = null;
  } catch (e) {
    catalog.error = 'Upcoming games unavailable (NFL schedule could not be loaded). Use Advanced to enter the teams.';
  }
  catalog.loaded = true;
  catalog.pickers.forEach((p) => p.gamesArrived());
}

// ---------- accessible combobox (ARIA 1.2 list autocomplete) ----------

function combobox(input, list, { options, onSelect, onType, emptyText }) {
  let items = [], active = -1;
  const optionEls = () => list.querySelectorAll('[role=option]');
  function close() {
    list.hidden = true; input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant'); active = -1;
  }
  function highlight(index) {
    const els = optionEls();
    els.forEach((el, i) => el.setAttribute('aria-selected', i === index ? 'true' : 'false'));
    active = index;
    if (index >= 0 && els[index]) {
      input.setAttribute('aria-activedescendant', els[index].id);
      els[index].scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  }
  function open(autoHighlight) {
    const entries = options(input.value.trim());
    items = entries.filter((e) => !e.group);
    let i = 0;
    list.replaceChildren(...(entries.length ? entries.map((e) => e.group
      ? h('li', { class: 'group', role: 'presentation' }, e.group)
      : h('li', { role: 'option', id: `${list.id}-${i++}`, 'aria-selected': 'false', class: 'option' },
          h('span', { class: 'opt-main' }, e.label), e.sub ? h('span', { class: 'opt-sub' }, e.sub) : null))
      : [h('li', { class: 'empty', role: 'presentation' }, emptyText ? emptyText() : 'No matches')]));
    optionEls().forEach((el, index) => {
      el.addEventListener('pointerdown', (ev) => ev.preventDefault()); // keep focus in the input
      el.addEventListener('click', () => choose(index));
    });
    list.hidden = false; input.setAttribute('aria-expanded', 'true');
    highlight(autoHighlight && items.length ? 0 : -1);
  }
  function choose(index) {
    const item = items[index];
    if (!item) return;
    close();
    onSelect(item.value);
  }
  input.addEventListener('input', () => { if (onType) onType(); open(input.value.trim().length > 0); });
  input.addEventListener('focus', () => open(false));
  input.addEventListener('blur', close);
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown') { ev.preventDefault(); if (list.hidden) open(true); else highlight(Math.min(active + 1, items.length - 1)); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); if (!list.hidden) highlight(Math.max(active - 1, 0)); }
    else if (ev.key === 'Enter' && !list.hidden && active >= 0) { ev.preventDefault(); choose(active); }
    else if (ev.key === 'Escape') { if (!list.hidden) { ev.preventDefault(); close(); } }
  });
  // Re-render an open list when its data arrives after the user started typing.
  const refresh = () => { if (!list.hidden) open(input.value.trim().length > 0); };
  return { close, open, refresh };
}

const matches = (query, haystack) => query.toLowerCase().split(/\s+/).filter(Boolean).every((t) => haystack.includes(t));

// ---------- game + kicker picker (one per form or selection card) ----------
// The kicker's team is derived from the chosen kicker; it is never asked twice.

function makePicker(el) {
  const st = { game: null, kicker: null, kickerTeams: [], kickersLoaded: false, manualTeam: null };
  const kickerHint = el.kickerHint.textContent;

  const gameOptions = (query) => {
    const out = []; let week = null;
    for (const g of catalog.games) {
      if (query && !matches(query, g.search)) continue;
      if (g.week !== week) { week = g.week; out.push({ group: g.game_type === 'REG' ? `Week ${g.week}` : `${g.game_type} · Week ${g.week}` }); }
      out.push({ value: g, label: g.display_name, sub: [kickoffLabel(g.kickoff, true), g.venue].filter(Boolean).join(' · ') });
    }
    return out;
  };
  const kickerOptions = (query) => {
    const out = [];
    for (const team of st.kickerTeams) {
      const ks = team.kickers.filter((k) => !query || matches(query, k.kicker_name.toLowerCase() + ' ' + k.kicker_id.toLowerCase()));
      if (!ks.length) continue;
      out.push({ group: team.name });
      for (const k of ks) out.push({ value: k, label: k.kicker_name,
        sub: [k.roster_label, k.season_games ? `${k.season_games} game${k.season_games === 1 ? '' : 's'} this season` : 'No games this season'].join(' · ') });
    }
    return out;
  };

  const gameBox = combobox(el.game, el.gameList, { options: gameOptions, onSelect: (g) => st.selectGame(g),
    emptyText: () => catalog.loaded ? 'No upcoming game matches' : 'Loading upcoming games…',
    onType: () => { if (st.game) { Object.assign(st, { game: null, kickerTeams: [], kicker: null, manualTeam: null }); el.gameClear.hidden = true; } } });
  const kickerBox = combobox(el.kicker, el.kickerList, { options: kickerOptions, onSelect: (k) => st.selectKicker(k),
    emptyText: () => !st.game ? 'Choose a game first, or keep typing a name or ID' : st.kickersLoaded ? 'No kicker matches; keep typing to use a name or ID' : 'Loading kickers…',
    onType: () => { st.kicker = null; st.manualTeam = null; } });

  st.selectGame = async (g) => {
    Object.assign(st, { game: g, kicker: null, manualTeam: null, kickerTeams: [], kickersLoaded: false });
    el.game.value = `${g.display_name} — ${kickoffLabel(g.kickoff, true)}`;
    el.gameClear.hidden = false;
    el.gameHint.textContent = [`Week ${g.week}`, kickoffLabel(g.kickoff), g.venue, g.roof ? `roof: ${g.roof}` : null].filter(Boolean).join(' · ');
    el.kicker.value = '';
    el.kicker.placeholder = 'Search the kicker, e.g. ' + (g.home ? g.home.nickname : 'name');
    el.kickerHint.textContent = 'Loading kickers…';
    try {
      const res = await fetch(`/api/games/${encodeURIComponent(g.game_id)}/kickers`);
      const data = await res.json();
      if (!res.ok) throw new Error(data && data.error ? data.error.message : 'Kickers unavailable');
      if (st.game !== g) return;
      st.kickerTeams = data.teams; st.kickersLoaded = true;
      kickerBox.refresh();
      const count = data.teams.reduce((a, t) => a + t.kickers.length, 0);
      el.kickerHint.textContent = count ? `${count} kicker${count === 1 ? '' : 's'} from nflverse roster and season data. Pick one, or type a name.`
        : 'No kickers found for this game in nflverse data. Type the name; KickEdge derives the team when it can.';
    } catch (e) {
      st.kickersLoaded = true;
      el.kickerHint.textContent = 'Kicker list unavailable. Type the kicker name or ID.';
    }
  };
  st.selectKicker = (k) => {
    st.kicker = k; st.manualTeam = null;
    el.kicker.value = k.kicker_name;
    const team = st.kickerTeams.find((t) => t.code === k.team);
    el.kickerHint.textContent = [team ? team.name : k.team, k.roster_label,
      k.season_games ? `${k.season_games} game${k.season_games === 1 ? '' : 's'} this season` : null].filter(Boolean).join(' · ');
  };
  st.clear = () => {
    Object.assign(st, { game: null, kicker: null, manualTeam: null, kickerTeams: [], kickersLoaded: false });
    el.game.value = ''; el.gameClear.hidden = true;
    st.gamesArrived();
    el.kickerHint.textContent = kickerHint;
    el.game.focus();
  };
  st.gamesArrived = () => {
    if (!st.game) el.gameHint.textContent = catalog.error || (catalog.games.length
      ? `${catalog.games.length} upcoming games in the ${catalog.season} schedule.${el.manualNote ? ' Or use Advanced for a manual matchup.' : ''}`
      : 'No upcoming games in the current schedule.');
    gameBox.refresh();
  };
  // Request fields for the chosen game: team/opponent only when the kicker's team is known.
  st.target = () => {
    const g = st.game;
    if (!g) return null;
    const out = { game_id: g.game_id, season: g.season, week: g.week };
    const team = st.kicker ? st.kicker.team : st.manualTeam;
    if (team) Object.assign(out, { team, opponent: team === g.home_team ? g.away_team : g.home_team });
    return out;
  };
  st.kickerValue = () => st.kicker ? st.kicker.kicker_id : el.kicker.value.trim().replace(/\s+/g, ' ');
  el.gameClear.addEventListener('click', () => st.clear());
  catalog.pickers.add(st);
  if (catalog.loaded) st.gamesArrived();
  return st;
}

// ---------- errors ----------

const ERROR_TITLES = {
  GAME_NOT_FOUND: 'No upcoming game found for that matchup', GAME_AMBIGUOUS: 'Ambiguous game',
  KICKER_NOT_FOUND: 'Kicker not found', KICKER_AMBIGUOUS: 'Ambiguous kicker',
  KICKER_TEAM_MISMATCH: 'Kicker listed on the other team', KICKER_TEAM_UNRESOLVED: "Kicker's team needed",
  INVALID_TEAM: 'Team not recognized',
  NFL_SOURCE_UNAVAILABLE: 'NFL data source unavailable', STALE_DATA: 'Data not usable for this kickoff',
  GAME_STARTED: 'Game already started or too close to kickoff', MODEL_NOT_READY: 'Model not ready',
  INVALID_ODDS: 'Invalid odds', INVALID_LINE: 'Invalid line', RATE_LIMITED: 'Too many requests',
  ANALYSIS_NOT_FOUND: 'Saved analysis not found', INVALID_REQUEST: 'Invalid request', INTERNAL_ERROR: 'Unexpected error',
};
const ERROR_HINTS = {
  GAME_NOT_FOUND: 'Only upcoming games can be analyzed. Pick the game from the list, or check the teams and season.',
  GAME_AMBIGUOUS: 'More than one upcoming meeting matches. Choose the game from the list, or add the week under Advanced.',
  KICKER_NOT_FOUND: 'Pick the kicker from the list, or use the full name as listed by nflverse, or the stable player ID.',
  KICKER_AMBIGUOUS: 'Several players match this name. Use the stable player ID (e.g. 00-0035358).',
  KICKER_TEAM_MISMATCH: "Choose the kicker's own team, or pick the other team's kicker.",
  KICKER_TEAM_UNRESOLVED: 'KickEdge could not tell which team this kicker plays for in this game. Choose the team once.',
  INVALID_TEAM: 'Use a team name (Rams, Los Angeles Rams) or an abbreviation (LA, LAR).',
  INVALID_ODDS: 'Use decimal odds greater than 1.00, e.g. 1.30 or 2.50.',
  NFL_SOURCE_UNAVAILABLE: 'Required NFL data could not be downloaded or verified. Try again later.',
  STALE_DATA: 'Cached sources are newer than the pregame cutoff; analysis would not be pregame.',
  MODEL_NOT_READY: 'The frozen model artifact is missing or failed verification. No analysis was run.',
};

function teamButtons(teams, onPick) {
  return h('div', { class: 'team-choice' }, teams.map((t) => {
    const b = h('button', { type: 'button', class: 'secondary' }, `Kicks for ${t.nickname}`);
    b.addEventListener('click', () => onPick(t.code));
    return b;
  }));
}

function showError(code, message, suggestions, box, extra) {
  box = box || $('error');
  const list = (suggestions || []).length ? h('div', { class: 'suggest' },
    h('p', {}, 'Upcoming games involving these teams:'),
    h('ul', {}, suggestions.map((g) => h('li', {}, $('game')
      ? h('button', { type: 'button', class: 'linkish', 'data-game': g.game_id }, `${g.display_name} — Week ${g.week}, ${kickoffLabel(g.kickoff, true)}`)
      : `${g.display_name} — Week ${g.week}`)))) : null;
  box.replaceChildren(
    h('h2', {}, ERROR_TITLES[code] || 'Error'),
    h('p', {}, message),
    ERROR_HINTS[code] ? h('p', { class: 'muted' }, ERROR_HINTS[code]) : null,
    list, extra || null,
    h('p', { class: 'code' }, code));
  box.querySelectorAll('button[data-game]').forEach((b) => b.addEventListener('click', () => {
    const g = catalog.games.find((x) => x.game_id === b.dataset.game) || (suggestions || []).find((x) => x.game_id === b.dataset.game);
    if (g && single) { box.hidden = true; single.selectGame(g); $('kicker').focus(); }
  }));
  box.hidden = false;
  box.focus();
}

function markField(field, message) {
  const el = $(field);
  if (!el) { showError('INVALID_REQUEST', message); return; }
  if (el.closest('details')) el.closest('details').open = true;
  el.setAttribute('aria-invalid', 'true');
  const hint = h('p', { class: 'field-error', id: field + '-err' }, message);
  el.setAttribute('aria-describedby', hint.id);
  el.after(hint);
  (el.matches('input, select, textarea') ? el : el.querySelector('input') || el).focus();
}

function clearErrors(scope) {
  const root = scope || document;
  root.querySelectorAll('.field-error').forEach((e) => e.remove());
  root.querySelectorAll('.leg-error').forEach((e) => { e.hidden = true; e.replaceChildren(); });
  root.querySelectorAll('[aria-invalid]').forEach((e) => {
    e.removeAttribute('aria-invalid');
    if (e.dataset.hint) e.setAttribute('aria-describedby', e.dataset.hint); else e.removeAttribute('aria-describedby');
  });
}

// ---------- shared result helpers ----------

function fmt(v, kind) {
  if (!has(v)) return 'Not available';
  if (kind === 'pct') return pct(v, 1);
  if (kind === 'bool') return v ? 'Yes' : 'No';
  if (kind === 'homeaway') return v ? 'Home' : 'Away';
  if (kind === 'text') return String(v);
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return typeof v === 'number' ? Number(v).toFixed(kind) : String(v);
}

function stat(label, value, cls) {
  return h('div', { class: 'stat ' + (cls || '') }, h('span', { class: 'stat-label' }, label), h('span', { class: 'stat-value' }, value));
}

const STATE_CLASS = { Verified: 'ok', Available: 'ok', Indoor: 'ok', Warning: 'warn', 'Not verified': 'warn', Unavailable: 'off', 'Not requested': 'off' };

function chip(state) {
  return h('span', { class: 'chip ' + (STATE_CLASS[state] || 'off') }, state);
}

// Price of an analysis: decimal (current) or American (stored before decimal odds).
function price(r) {
  const m = r.market;
  if (m.odds_format === 'decimal') return { decimal: true, label: dec(m.decimal_odds), name: 'decimal odds' };
  return { decimal: false, label: `${american(m.american_odds)} (US, legacy; ≈ ${dec(americanToDecimal(m.american_odds))} decimal)`, name: 'American odds' };
}

// The probability compared with the price: conditional on no push for integer lines.
function comparable(r) {
  const p = r.prop, conditional = p.price_probability_basis !== 'direct';
  return { p: conditional ? p.model_probability_conditional : p.model_side_probability, conditional };
}

// Statistical feedback: price-implied vs model probability, never a recommendation.
function feedbackText(implied, model, diffPP, priceLabel, priceName, conditional) {
  const lead = `At ${priceName} ${priceLabel}, the price implies ${pct(implied)}. ${conditional ? 'Conditional on no push, ' : ''}KickEdge estimates ${pct(model)}.`;
  if (Math.abs(diffPP) < 1) return `${lead} The two estimates are very close (difference ${signedPP(diffPP)}).`;
  return `${lead} The model estimate is ${Math.abs(diffPP).toFixed(1)} percentage points ${diffPP > 0 ? 'higher' : 'lower'} than the probability implied by the price (${signedPP(diffPP)}).`;
}

function diffStat(label, diffPP) {
  const dir = Math.abs(diffPP) < 1 ? 'close' : diffPP > 0 ? 'higher' : 'lower';
  const word = { close: 'very close', higher: 'model higher', lower: 'model lower' }[dir];
  return h('div', { class: `stat diff ${dir}` }, h('span', { class: 'stat-label' }, label),
    h('span', { class: 'stat-value' }, signedPP(diffPP)), h('span', { class: 'stat-note' }, word));
}

function priceFeedback(r) {
  const pr = price(r), c = comparable(r);
  return feedbackText(r.market.implied_probability, c.p, r.analysis.edge_raw_pp, pr.label, pr.name, c.conditional);
}

// ---------- single analysis sections ----------

function storedBanner(r) {
  if (!r.stored || r.stored.fresh) return null;
  const when = r.provenance ? r.provenance.analysis_generated_at : r.generated_at;
  return h('p', { class: 'banner', role: 'note' }, `Saved analysis from ${localTime(when)}. Shown as stored; nothing was re-run.`);
}

function hero(r, ids) {
  const prop = r.prop, side = prop.side, sideName = side === 'over' ? 'Over' : 'Under';
  const g = r.game, teams = r.teams, pr = price(r);
  const matchup = g.home_team && g.away_team ? `${nickname(teams, g.away_team)} @ ${nickname(teams, g.home_team)}` : `${g.team} vs ${g.opponent}`;
  const integer = Number.isInteger(prop.line);
  return h('section', { class: 'card hero', 'aria-labelledby': ids.hero },
    h('div', { class: 'hero-top' },
      h('div', { class: 'hero-id' },
        h('h2', { id: ids.hero }, r.player.kicker_name),
        h('p', { class: 'matchup' }, matchup, h('span', { class: 'muted-inline' }, ` · ${teamName(teams, g.team)}`)),
        h('p', { class: 'muted' }, [kickoffLabel(g.kickoff), g.venue].filter(Boolean).join(' · '))),
      h('div', { class: 'pick' }, h('span', { class: 'eyebrow' }, 'Your pick'),
        h('span', { class: 'pick-text' }, `${sideName} ${prop.line} XPM`),
        h('span', { class: 'pick-odds' }, pr.decimal ? `Decimal odds ${pr.label}` : pr.label))),
    h('div', { class: 'hero-main' },
      h('div', { class: 'prob' }, h('span', { class: 'eyebrow' }, 'KickEdge probability'),
        h('span', { class: 'prob-value', id: ids.prob }, pct(prop.model_side_probability)),
        h('span', { class: 'muted' }, `that ${sideName} ${prop.line} wins`)),
      h('div', { class: 'prob xpm' }, h('span', { class: 'eyebrow' }, 'Expected XPM'),
        h('span', { class: 'prob-value small' }, num(r.prediction.expected_xpm)))),
    h('div', { class: 'stats' },
      stat('P(Over)', pct(prop.p_over), side === 'over' ? 'sel' : ''),
      stat('P(Under)', pct(prop.p_under), side === 'under' ? 'sel' : ''),
      integer ? stat('P(Push)', pct(prop.p_push), 'push') : null),
    h('div', { class: 'feedback', role: 'note' }, h('h3', {}, 'Statistical feedback'), h('p', {}, priceFeedback(r))),
    (r.input_notes || []).length ? h('p', { class: 'note' }, r.input_notes.join(' · ')) : null);
}

function distribution(r, ids) {
  const p = r.prediction.distribution.probabilities, tail = r.prediction.distribution.tail_probability;
  const line = r.prop.line, side = r.prop.side, sideName = side === 'over' ? 'Over' : 'Under';
  const top = Math.max(5, Math.floor(line) + 2);
  const bins = [];
  for (let k = 0; k < top; k++) bins.push([k, String(k), p[k]]);
  bins.push([top, `${top}+`, p.slice(top).reduce((a, b) => a + b, 0) + tail]);
  const outcome = (k) => k === line ? 'push' : ((k > line) === (side === 'over') ? 'win' : 'loss');
  const word = { win: 'Win', loss: 'Loss', push: 'Push' };
  const max = Math.max(...bins.map((b) => b[2]));
  const total = (o) => bins.filter(([k]) => outcome(k) === o).reduce((a, b) => a + b[2], 0);
  const rows = [];
  for (const [k, name, v] of bins) {
    const o = outcome(k);
    rows.push(h('div', { class: `dist-row ${o}` },
      h('span', { class: 'dist-k' }, name),
      h('span', { class: 'dist-track' }, h('span', { class: 'dist-fill', style: `width:${Math.max(1.5, 100 * v / max).toFixed(1)}%` })),
      h('span', { class: 'dist-p' }, pct(v)),
      h('span', { class: 'dist-tag' }, word[o])));
    if (!Number.isInteger(line) && k === Math.floor(line)) rows.push(h('div', { class: 'dist-line', 'aria-hidden': 'true' }, h('span', {}, `Line ${line}`)));
  }
  const label = bins.map(([k, name, v]) => `${name} XPM: ${pct(v)}, ${word[outcome(k)].toLowerCase()}`).join('; ');
  return h('section', { class: 'card', 'aria-labelledby': ids.dist },
    h('h2', { id: ids.dist }, 'XPM distribution'),
    h('p', { class: 'muted' }, `Probability of each made-XPM count (Poisson, expected ${num(r.prediction.expected_xpm)}), marked for your pick: ${sideName} ${line}.`),
    h('div', { class: 'dist', role: 'img', 'aria-label': `Probability by XPM count for ${sideName} ${line}. ${label}` }, rows),
    h('p', { class: 'dist-sum' }, `Win ${pct(total('win'))} · Loss ${pct(total('loss'))}`, Number.isInteger(line) ? ` · Push ${pct(total('push'))}` : ''),
    h('details', {}, h('summary', {}, 'Distribution values 0–12'),
      h('div', { class: 'scroll' }, h('table', {},
        h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'XPM'), h('th', { scope: 'col' }, 'Probability'))),
        h('tbody', {}, p.map((v, k) => h('tr', {}, h('td', {}, k), h('td', {}, pct(v, 3)))),
          h('tr', {}, h('td', {}, '> 12'), h('td', {}, pct(tail, 5))))))));
}

const KEY_DATA = [
  ['Kicker form', null, [
    ['kicker_xpm_before', 'XPM season-to-date', 0], ['kicker_xpm_per_game_before', 'XPM per game (season)', 2],
    ['kicker_xpm_per_game_last_3', 'XPM per game, last 3', 2, 'kicker_xpm_per_game_before'],
    ['kicker_xpm_per_game_last_5', 'XPM per game, last 5', 2, 'kicker_xpm_per_game_before'],
    ['kicker_xp_conversion_rate_before', 'Conversion rate', 'pct'], ['previous_game_xpm', 'Previous game XPM', 0],
    ['days_since_last_game', 'Days since last game', 1], ['kicker_games_before', 'Games of history', 0]]],
  ['Offense', 'team', [
    ['offense_points_per_game_before', 'Points per game', 1], ['offense_touchdowns_per_game_before', 'TD per game', 2],
    ['offense_td_per_drive_before', 'TD per drive', 3], ['offense_red_zone_td_rate_before', 'Red-zone TD rate', 'pct'],
    ['offense_points_per_game_last_3', 'Points per game, last 3', 1, 'offense_points_per_game_before'],
    ['offense_points_per_game_last_5', 'Points per game, last 5', 1, 'offense_points_per_game_before']]],
  ['Opponent defense', 'opponent', [
    ['defense_points_allowed_per_game_before', 'Points allowed per game', 1], ['defense_touchdowns_allowed_per_game_before', 'TD allowed per game', 2],
    ['defense_td_allowed_per_drive_before', 'TD allowed per drive', 3], ['defense_red_zone_td_rate_allowed_before', 'Red-zone TD rate allowed', 'pct'],
    ['defense_points_allowed_per_game_last_3', 'Points allowed, last 3', 1, 'defense_points_allowed_per_game_before'],
    ['defense_points_allowed_per_game_last_5', 'Points allowed, last 5', 1, 'defense_points_allowed_per_game_before']]],
  ['Game context', null, [
    ['is_home', 'Home or away', 'homeaway'], ['team_days_rest', 'Team rest (days)', 1],
    ['opponent_days_rest', 'Opponent rest (days)', 1], ['week', 'Week', 0], ['game_type', 'Game type', 'text'],
    ['team_two_point_attempt_rate_before', '2-pt attempt rate', 'pct'], ['team_two_point_attempts_before', '2-pt attempts (season)', 0]]],
];

function keyData(r, ids) {
  const f = r.features;
  if (!f) {
    return h('section', { class: 'card', 'aria-labelledby': ids.saw }, h('h2', { id: ids.saw }, 'What KickEdge saw'),
      h('p', { class: 'muted' }, 'Model inputs were not stored with this older analysis.'));
  }
  return h('section', { class: 'card', 'aria-labelledby': ids.saw },
    h('h2', { id: ids.saw }, 'What KickEdge saw'),
    h('p', { class: 'muted' }, 'Selected model inputs from the pregame snapshot: data the model used, not causal explanations. Differences compare recent games with the season average.'),
    h('div', { class: 'groups' }, KEY_DATA.map(([title, who, rows]) => h('div', { class: 'group' },
      h('h3', {}, who ? `${title} · ${nickname(r.teams, r.game[who])}` : title),
      h('dl', {}, rows.map(([k, label, kind, base]) => {
        const v = f[k], b = base ? f[base] : null;
        const delta = base && has(v) && has(b) ? h('span', { class: 'delta' }, `${signed(v - b, kind)} vs season`) : null;
        return [h('dt', {}, label), h('dd', { class: has(v) ? '' : 'na' }, fmt(v, kind), delta)];
      }))))),
    h('details', {}, h('summary', {}, `View all ${Object.keys(f).length} model inputs`),
      h('div', { class: 'scroll' }, h('table', { class: 'inputs' },
        h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, '#'), h('th', { scope: 'col' }, 'Input'), h('th', { scope: 'col' }, 'Value'))),
        h('tbody', {}, Object.entries(f).map(([k, v], i) => h('tr', {}, h('td', {}, i + 1), h('td', { class: 'mono' }, k),
          h('td', { class: v === null ? 'na' : '' }, v === null ? 'NULL (frozen imputer)' : (typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(4) : String(v)))))))),
      h('p', { class: 'muted' }, 'NULL inputs are handled by the frozen preprocessing pipeline (median imputation with missing-value indicators).')));
}

function weatherState(r) {
  const q = r.data_quality, w = (r.context && r.context.weather) || {}, v = w.values || {};
  if (q.weather_requested === false) return 'Not requested';
  if (v.is_dome === true || ['dome', 'closed'].includes(r.game.roof)) return 'Indoor';
  return w.available ? 'Available' : 'Unavailable';
}

function rosterMessage(r) {
  const verified = r.data_quality.kicker_current_team_verified;
  return (r.player && r.player.roster && r.player.roster.message) ||
    (verified ? 'Current team affiliation verified.' : 'Kicker identity is verified from NFL history, but current team affiliation could not be independently confirmed.');
}

function quality(r, ids) {
  const q = r.data_quality, f = r.features || {}, fresh = q.source_data_freshness || [];
  const oldest = fresh.length ? Math.max(...fresh.map((s) => s.age_seconds)) : null;
  const latest = q.latest_game_used, verified = q.kicker_current_team_verified;
  const games = f.kicker_games_before;
  const roster = rosterMessage(r);
  const short = !has(games) || games >= 5 ? null
    : `Only ${games} prior game${games === 1 ? '' : 's'} this season; ${games < 3 ? 'rolling-3 and rolling-5' : 'rolling-5'} inputs are unavailable and handled by the frozen preprocessing pipeline.`;
  const marketState = !q.market_requested ? 'Not requested' : (q.market_availability ? 'Available' : 'Unavailable');
  const stale = oldest !== null && oldest > 6 * 3600;
  const summary = [
    ['Game', q.target_game_verified ? 'Verified' : 'Unavailable'],
    ['Features', q.feature_schema_verified ? `${q.feature_count}/82` : 'Unavailable', q.feature_schema_verified ? 'ok' : 'off'],
    ['Source', oldest === null ? 'Unknown' : `${stale ? 'Stale' : 'Fresh'} · ${(oldest / 3600).toFixed(1)} h`, stale ? 'warn' : 'ok'],
    ['Kicker team', verified === true ? 'Verified' : 'Not verified'],
    ['History', has(games) ? `${games} game${games === 1 ? '' : 's'}` : '—', has(games) && games < 5 ? 'warn' : 'ok'],
    ['Weather', weatherState(r)],
    ['Market', marketState],
  ];
  const rows = [
    ['Target game', q.target_game_verified ? 'Verified' : 'Unavailable', r.game.game_id],
    ['Kicker identity', q.kicker_identity_verified ? 'Verified' : 'Unavailable', r.player.kicker_id],
    ['Current team affiliation', verified === true ? 'Verified' : 'Not verified', roster],
    ['Feature schema', q.feature_schema_verified ? 'Verified' : 'Unavailable', `${q.feature_count}/82 inputs, frozen order`],
    ['Frozen model', q.model_verified ? 'Verified' : 'Unavailable', 'SHA-256 checked before loading'],
    ['Source age', stale ? 'Warning' : 'Available', oldest === null ? '—' : `${(oldest / 3600).toFixed(1)} h (oldest source)`],
    ['Latest completed game used', latest ? 'Available' : 'Unavailable', latest ? latest.game_id : 'No prior games this season'],
    ['Nullable inputs', q.null_feature_count ? 'Warning' : 'Available', `${q.null_feature_count} handled by frozen imputer`],
    ['Market context', marketState, 'Context only'],
    ['Weather context', weatherState(r), 'Context only'],
  ];
  const warnings = q.warnings || [];
  return h('section', { class: 'card', 'aria-labelledby': ids.dq },
    h('h2', { id: ids.dq }, 'Data quality'),
    h('ul', { class: 'qsum' }, summary.map(([k, v, forced]) => h('li', { class: 'qchip ' + (forced || STATE_CLASS[v] || 'off') },
      h('span', { class: 'qk' }, k), h('span', { class: 'qv' }, v)))),
    h('p', { class: verified === true ? 'qnote' : 'qnote warn' }, roster),
    short ? h('p', { class: 'qnote' }, short) : null,
    h('details', {}, h('summary', {}, `View details${warnings.length ? ` and ${warnings.length} notes` : ''}`),
      h('ul', { class: 'dq' }, rows.map(([label, st, detail]) => h('li', {}, h('span', {}, label), chip(st), h('span', { class: 'muted' }, detail)))),
      warnings.length ? h('div', { class: 'notes' }, h('h3', {}, 'Notes and warnings'), h('ul', {}, warnings.map((w) => h('li', {}, w)))) : null));
}

function market(r, ids) {
  const m = r.market, a = r.analysis, pr = price(r), c = comparable(r);
  const fair = pr.decimal ? (has(a.fair_odds.decimal) ? dec(a.fair_odds.decimal) : '—')
                          : (has(a.fair_odds.american) ? american(a.fair_odds.american) : '—');
  return h('section', { class: 'card', 'aria-labelledby': ids.mk },
    h('h2', { id: ids.mk }, 'Market comparison'),
    c.conditional ? h('p', { class: 'muted' }, 'Integer line: price comparison is conditional on no push.') : null,
    h('div', { class: 'stats' },
      pr.decimal ? stat('Decimal odds', pr.label) : stat('American odds (legacy)', american(m.american_odds)),
      stat('Odds-implied probability', pct(m.implied_probability)),
      stat('KickEdge probability' + (c.conditional ? ' (no push)' : ''), pct(c.p)),
      diffStat('Probability difference', a.edge_raw_pp),
      stat(pr.decimal ? 'Model fair odds (decimal)' : 'Model fair odds (American)', fair),
      has(m.no_vig_probability) ? stat('No-vig market probability', pct(m.no_vig_probability)) : null,
      has(m.overround) ? stat('Overround', pct(m.overround, 2)) : null,
      has(a.edge_novig_pp) ? diffStat('Difference vs no-vig', a.edge_novig_pp) : null),
    h('details', {}, h('summary', {}, 'Mathematical price comparison'),
      h('p', {}, `Expected value per 1 unit under model assumptions: ${num(a.expected_value_per_unit, 3)} units.`),
      h('p', { class: 'muted' }, 'This is a mathematical output based on the model probability, not a betting recommendation.')));
}

const WMO = { 0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast', 45: 'Fog', 48: 'Rime fog',
  51: 'Light drizzle', 53: 'Drizzle', 55: 'Dense drizzle', 56: 'Freezing drizzle', 57: 'Freezing drizzle',
  61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 66: 'Freezing rain', 67: 'Freezing rain', 71: 'Light snow',
  73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains', 80: 'Rain showers', 81: 'Rain showers', 82: 'Violent rain showers',
  85: 'Snow showers', 86: 'Snow showers', 95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Thunderstorm with hail' };

function weatherBlock(r) {
  const w = (r.context && r.context.weather) || {}, v = w.values || {}, st = weatherState(r);
  if (st === 'Not requested') return h('p', { class: 'muted' }, 'Weather not requested.');
  if (st === 'Indoor') return h('p', {}, 'Indoor / closed roof — outdoor weather is not a game condition here.');
  if (st === 'Available') {
    const rows = [
      ['Temperature', has(v.temperature) ? `${num(v.temperature, 0)} °C · ${num(v.temperature * 9 / 5 + 32, 0)} °F` : null],
      ['Wind', has(v.wind_speed) ? `${num(v.wind_speed, 0)} km/h · ${num(v.wind_speed / 1.609, 0)} mph` : null],
      ['Gusts', has(v.wind_gust) ? `${num(v.wind_gust, 0)} km/h · ${num(v.wind_gust / 1.609, 0)} mph` : null],
      ['Precipitation chance', has(v.precipitation_probability) ? `${num(v.precipitation_probability, 0)}%` : null],
      ['Precipitation', has(v.precipitation) ? `${num(v.precipitation, 1)} mm` : null],
      ['Conditions', has(v.weather_code) ? (WMO[v.weather_code] || `WMO code ${v.weather_code}`) : null],
    ].filter(([, x]) => x !== null);
    const captured = w.provenance && w.provenance.weather && w.provenance.weather.observed_at;
    return [h('dl', {}, rows.map(([k, x]) => [h('dt', {}, k), h('dd', {}, x)])),
      h('p', { class: 'muted' }, `Open-Meteo forecast for the kickoff hour${captured ? `, captured ${localTime(captured)}` : ''}.`)];
  }
  if (r.game.roof === 'retractable') return h('p', { class: 'muted' }, 'Retractable roof — game-day roof status is not yet known, so outdoor weather is not shown.');
  const reason = (r.data_quality.warnings || []).find((x) => /weather|venue|roof/i.test(x));
  return [h('p', { class: 'muted' }, 'Weather data unavailable.'), reason ? h('p', { class: 'muted small' }, reason) : null];
}

function context(r, ids) {
  const mk = (r.context && r.context.market) || {}, decimal = price(r).decimal;
  // Provider moneylines are American; show them in the analysis's own price format.
  const ml = (x) => !has(x) ? '—' : decimal ? dec(americanToDecimal(x)) : american(x);
  return h('section', { class: 'card', 'aria-labelledby': ids.cx },
    h('h2', { id: ids.cx }, 'Game context'),
    h('span', { class: 'tag' }, 'Context only — not currently used by the probability model'),
    h('div', { class: 'groups' },
      h('div', { class: 'group' }, h('h3', {}, 'Weather'), weatherBlock(r),
        h('p', { class: 'muted' }, `Roof: ${r.game.roof || 'unknown'} · Venue: ${r.game.venue || 'unknown'}${r.game.venue_city ? `, ${r.game.venue_city}` : ''}`)),
      h('div', { class: 'group' }, h('h3', {}, 'Market'),
        mk.available ? h('div', { class: 'scroll' }, h('table', {},
          h('thead', {}, h('tr', {}, ['Book', 'Spread (team)', 'Total', 'ML team', 'ML opp.'].map((t) => h('th', { scope: 'col' }, t)))),
          h('tbody', {}, (mk.quotes || []).map((q) => h('tr', {}, h('td', {}, (q.provenance || {}).bookmaker || '—'),
            h('td', {}, num(q.values.game_spread, 1)), h('td', {}, num(q.values.game_total, 1)),
            h('td', {}, ml(q.values.moneyline_team)), h('td', {}, ml(q.values.moneyline_opponent))))))) :
          h('p', { class: 'muted' }, r.data_quality.market_requested ? 'Market data unavailable.' : 'Market context not requested.'))));
}

function details(r) {
  const pv = r.provenance, fp = pv.features;
  const kv = [['Analysis generated', pv.analysis_generated_at], ['Snapshot generated', fp.generated_at],
    ['Target kickoff (UTC)', fp.target_kickoff], ['Feature cutoff (UTC)', fp.cutoff],
    ['Latest game used', fp.latest_game_used ? fp.latest_game_used.game_id : 'none'],
    ['Feature schema version', fp.feature_schema_version], ['Model version', pv.model_version],
    ['Model artifact SHA-256', r.model.artifact_sha256], ['Snapshot SHA-256', pv.feature_snapshot_sha256],
    r.stored ? ['Saved analysis id', r.stored.id] : null].filter(Boolean);
  return h('details', { class: 'card' }, h('summary', {}, 'Technical details'),
    h('dl', { class: 'mono-dl' }, kv.map(([k, v]) => [h('dt', {}, k), h('dd', { class: 'mono' }, v || '—')])),
    h('h3', {}, 'Sources'),
    h('div', { class: 'scroll' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Dataset', 'Provider', 'Fetched at', 'SHA-256'].map((t) => h('th', { scope: 'col' }, t)))),
      h('tbody', {}, (fp.sources || []).map((s) => h('tr', {}, h('td', {}, s.dataset), h('td', {}, s.provider || '—'),
        h('td', { class: 'mono' }, s.fetched_at || '—'), h('td', { class: 'mono' }, (s.sha256 || '').slice(0, 16) + '…')))))),
    h('p', { class: 'muted' }, `History games used: ${(fp.history_games || []).map((g) => g.game_id).join(', ') || 'none'}`));
}

// All sections of one analysis; ids are prefixed so several can coexist on a page.
function sections(r, prefix) {
  const ids = { hero: `${prefix}hero-h`, prob: `${prefix}pick-probability`, dist: `${prefix}dist-h`, saw: `${prefix}saw-h`,
                dq: `${prefix}dq-h`, mk: `${prefix}mk-h`, cx: `${prefix}cx-h` };
  return [storedBanner(r), hero(r, ids), distribution(r, ids), keyData(r, ids), quality(r, ids), market(r, ids), context(r, ids), details(r)].filter(Boolean);
}

// ---------- official pick tracking ----------

const sideLabel = (side) => side === 'over' ? 'Over' : 'Under';

function trackBar(r) {
  if (!r.stored || !/^[0-9a-f]{64}$/.test(r.stored.id) || !$('tracked-body')) return null;
  const started = new Date(r.game.kickoff) <= new Date();
  const status = h('p', { class: 'muted', role: 'status' }, started
    ? 'Kickoff has passed: only pregame analyses can be tracked.'
    : 'Track pick freezes this pregame probability as an official pick, to evaluate later.');
  const button = h('button', { type: 'button', class: 'secondary', disabled: started }, 'Track pick');
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = 'Tracking…';
    try {
      const res = await fetch('/api/tracked', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                               body: JSON.stringify({ analysis_id: r.stored.id }) });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) {
        status.textContent = (data && data.error && data.error.message) || `Tracking failed (${res.status}).`;
        button.disabled = false;
        return;
      }
      const p = data.pick;
      status.textContent = data.already_tracked
        ? `Already tracked on ${localTime(p.created_at)}; the original pick is unchanged.`
        : `Tracked: ${sideLabel(p.side)} ${p.line} XPM frozen at ${pct(p.kickedge_probability)}.`;
      button.textContent = 'Tracked';
      loadTracked();
    } catch (e) {
      status.textContent = 'The server could not be reached.';
      button.disabled = false;
    }
  });
  return h('section', { class: 'card track-bar', 'aria-label': 'Track pick' }, button, status);
}

// key: unique element id stem; url: settle/correct endpoint; reload: refreshes the owning panel.
function settleForm(key, url, reload) {
  const id = `settle-${key}`;
  const input = h('input', { id, type: 'number', min: '0', max: '20', step: '1', inputmode: 'numeric', required: true });
  const note = h('span', { class: 'ri-sub', role: 'status' });
  const form = h('form', { class: 'settle-form' }, h('label', { for: id }, 'Actual XPM'), input,
    h('button', { type: 'submit', class: 'secondary' }, 'Settle'), note);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const value = Number(input.value);
    if (input.value.trim() === '' || !Number.isInteger(value) || value < 0 || value > 20) {
      note.textContent = 'Enter a whole number from 0 to 20.';
      return;
    }
    try {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                     body: JSON.stringify({ actual_xpm: value }) });
      const data = await res.json().catch(() => null);
      if (!res.ok) { note.textContent = (data && data.error && data.error.message) || `Settle failed (${res.status}).`; return; }
      reload();
    } catch (e) {
      note.textContent = 'The server could not be reached.';
    }
  });
  return form;
}

const CORRECT_PROMPT = 'Correct this settled result?\nThe original settlement will remain in the audit history.';

function correctForm(key, url, reload) {
  const id = `correct-${key}`;
  const input = h('input', { id, type: 'number', min: '0', max: '20', step: '1', inputmode: 'numeric', required: true });
  const reason = h('input', { id: id + '-reason', type: 'text', maxlength: '200', placeholder: 'e.g. Entered wrong result' });
  const note = h('span', { class: 'ri-sub', role: 'status' });
  const form = h('form', { class: 'settle-form', hidden: true },
    h('label', { for: id }, 'Actual XPM corrected to'), input,
    h('label', { for: id + '-reason' }, 'Reason (optional)'), reason,
    h('button', { type: 'submit', class: 'secondary' }, 'Apply correction'), note);
  const toggle = h('button', { type: 'button', class: 'secondary link-button', 'aria-expanded': 'false' }, 'Correct result');
  toggle.addEventListener('click', () => {
    form.hidden = !form.hidden;
    toggle.setAttribute('aria-expanded', String(!form.hidden));
    if (!form.hidden) input.focus();
  });
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const value = Number(input.value);
    if (input.value.trim() === '' || !Number.isInteger(value) || value < 0 || value > 20) {
      note.textContent = 'Enter a whole number from 0 to 20.';
      return;
    }
    if (!window.confirm(CORRECT_PROMPT)) { note.textContent = 'Correction cancelled; nothing changed.'; return; }
    const body = { actual_xpm: value, confirm: true };
    if (reason.value.trim()) body.reason = reason.value.trim();
    try {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json().catch(() => null);
      if (!res.ok) { note.textContent = (data && data.error && data.error.message) || `Correction failed (${res.status}).`; return; }
      reload();
    } catch (e) {
      note.textContent = 'The server could not be reached.';
    }
  });
  return [toggle, form];
}

function correctionHistory(t) {
  const o = t.original_settlement;
  const rows = [h('li', {}, `Original: ${o.actual_xpm} XPM — ${o.result} · ${localTime(o.settled_at)}`),
    ...t.corrections.map((c) => h('li', {}, `Corrected: ${c.new_actual_xpm} XPM — ${c.new_result}`,
      c.reason ? ` · Reason: ${c.reason}` : '', ` · ${localTime(c.corrected_at)}`))];
  return h('details', { class: 'history' }, h('summary', {}, 'View correction history'), h('ol', {}, rows));
}

function trackedItem(t) {
  const p = t.pick, s = t.settlement;
  const children = [
    h('span', { class: 'ri-main' }, p.kicker),
    h('span', { class: 'ri-sub' }, `${p.team} vs ${p.opponent} · ${sideLabel(p.side)} ${p.line} XPM · ${dec(p.decimal_odds)}`),
    h('span', { class: 'ri-sub' }, `KickEdge: ${pct(p.kickedge_probability)} · kickoff ${kickoffLabel(p.kickoff, true)}`)];
  if (s) {
    children.push(h('span', { class: 'status ' + s.result.toLowerCase() }, `SETTLED — ${s.result}`, t.corrected ? h('span', { class: 'chip warn' }, 'Corrected') : null),
      h('span', { class: 'ri-sub' }, `Actual XPM: ${s.actual_xpm} · Result: ${s.result}`),
      t.corrected ? correctionHistory(t) : null, correctForm(p.tracking_id.slice(0, 12), `/api/tracked/${p.tracking_id}/correct`, loadTracked));
  }
  else if (new Date(p.kickoff) > new Date()) children.push(h('span', { class: 'status' }, 'OPEN — awaiting kickoff'));
  else children.push(h('span', { class: 'status' }, 'OPEN — enter the result'), settleForm(p.tracking_id.slice(0, 12), `/api/tracked/${p.tracking_id}/settle`, loadTracked));
  return h('li', { class: 'tracked-item' }, children);
}

async function loadTracked() {
  const body = $('tracked-body');
  if (!body) return;
  try {
    const res = await fetch('/api/tracked');
    const data = await res.json();
    if (!res.ok) throw new Error();
    const sm = data.summary;
    if (!sm.tracked) { body.replaceChildren(h('p', { class: 'hint' }, 'No tracked picks yet.')); return; }
    const parts = [h('div', { class: 'tracked-summary' }, stat('Tracked', sm.tracked), stat('Settled', sm.settled), stat('Open', sm.open))];
    if (sm.graded) {
      const pushes = sm.pushes ? ` (${sm.pushes} push${sm.pushes === 1 ? '' : 'es'} excluded)` : '';
      parts.push(h('div', { class: 'tracked-summary' }, stat('Avg. probability', pct(sm.average_probability)),
        stat('Observed freq.', pct(sm.observed_frequency)), stat('Brier score', num(sm.brier_score, 3))),
        h('p', { class: 'hint' }, `Sample: ${sm.graded} settled pick${sm.graded === 1 ? '' : 's'}${pushes}. Small samples can be noisy; lower Brier is better.`));
    }
    for (const [title, items] of [['Open', data.open], ['Settled', data.settled]]) {
      if (items.length) parts.push(h('h3', {}, title), h('ul', { class: 'recent-list' }, items.map(trackedItem)));
    }
    body.replaceChildren(...parts);
  } catch (e) {
    body.replaceChildren(h('p', { class: 'hint' }, 'Tracked picks unavailable.'));
  }
}

// ---------- official multi tracking ----------

function trackMultiBar(rec) {
  if (!rec.combined_available || !rec.stored || !/^[0-9a-f]{64}$/.test(rec.stored.id) || !$('tracked-multi-body')) return null;
  const started = rec.selections.some((l) => new Date(l.result.game.kickoff) <= new Date());
  const status = h('p', { class: 'muted', role: 'status' }, started
    ? 'At least one selection has reached kickoff: the multi can only be tracked before every game starts.'
    : 'Track multi freezes every selection and the combined figures as an official prediction, to evaluate later.');
  const button = h('button', { type: 'button', class: 'secondary', disabled: started }, 'Track multi');
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = 'Tracking…';
    try {
      const res = await fetch('/api/tracked-multi', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                     body: JSON.stringify({ analysis_id: rec.stored.id }) });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) {
        status.textContent = (data && data.error && data.error.message) || `Tracking failed (${res.status}).`;
        button.disabled = false;
        return;
      }
      const m = data.manifest;
      status.textContent = data.already_tracked
        ? `Already tracked on ${localTime(m.created_at)}; the original multi is unchanged.`
        : `Tracked: ${m.selection_count}-leg multi frozen at ${pct(m.approximate_kickedge_combined_probability)} (approx.).`;
      button.textContent = 'Tracked';
      setTrackedTab('multi');
      loadTrackedMulti();
    } catch (e) {
      status.textContent = 'The server could not be reached.';
      button.disabled = false;
    }
  });
  return h('section', { class: 'card track-bar', 'aria-label': 'Track multi' }, button, status);
}

function trackedLeg(m, l) {
  const p = l.leg, s = l.settlement, key = `${m.tracking_id.slice(0, 10)}-${p.leg}`;
  const base = `/api/tracked-multi/${m.tracking_id}/legs/${p.leg}`;
  const children = [h('span', { class: 'ri-main' }, p.kicker),
    h('span', { class: 'ri-sub' }, `${sideLabel(p.side)} ${p.line} XPM · ${p.team} vs ${p.opponent} · ${dec(p.decimal_odds)}`),
    h('span', { class: 'ri-sub' }, `KickEdge: ${pct(p.kickedge_probability)} · kickoff ${kickoffLabel(p.kickoff, true)}`)];
  if (s) {
    children.push(h('span', { class: 'status ' + s.result.toLowerCase() }, `Actual XPM: ${s.actual_xpm} · ${s.result}`,
      l.corrected ? h('span', { class: 'chip warn' }, 'Corrected') : null),
      l.corrected ? correctionHistory(l) : null, correctForm(key, `${base}/correct`, loadTrackedMulti));
  } else if (new Date(p.kickoff) > new Date()) children.push(h('span', { class: 'status' }, 'OPEN — awaiting kickoff'));
  else children.push(h('span', { class: 'status' }, 'OPEN — enter the result'), settleForm(key, `${base}/settle`, loadTrackedMulti));
  return h('li', {}, children);
}

function trackedMultiItem(t) {
  const m = t.manifest;
  const status = t.status + (t.outcome ? ` — ${t.outcome}` : t.status === 'PARTIALLY SETTLED' ? ` (${t.settled_legs}/${m.selection_count} legs)` : '');
  return h('li', { class: 'tracked-item' },
    h('span', { class: 'ri-main' }, `${m.selection_count}-leg multi`,
      m.same_game_correlation_warning ? h('span', { class: 'chip warn' }, 'Same game') : null),
    h('span', { class: 'ri-sub' }, `Combined odds: ${dec(m.combined_decimal_odds)} · KickEdge approximate probability: ${pct(m.approximate_kickedge_combined_probability)}`),
    h('span', { class: 'status ' + (t.outcome === 'ALL LEGS WON' ? 'win' : t.outcome === 'HAS LOSS' ? 'loss' : '') }, `Status: ${status}`),
    t.push_note ? h('span', { class: 'ri-sub' }, t.push_note) : null,
    h('ul', { class: 'multi-legs' }, t.legs.map((l) => trackedLeg(m, l))));
}

function multiGroupStats(title, g) {
  if (!g.tracked) return [];
  const parts = [h('p', { class: 'group-title' }, `${title}: ${g.tracked} tracked · ${g.settled} settled`)];
  if (g.settled) {
    parts.push(h('div', { class: 'tracked-summary' }, stat('All legs won', g.all_legs_won), stat('Has loss', g.has_loss),
      stat('No-loss with push', g.no_loss_with_push)),
    h('div', { class: 'tracked-summary' }, stat('Avg. combined prob.', pct(g.average_combined_probability)),
      stat('All-win freq.', pct(g.observed_all_win_frequency)), stat('All-win Brier', num(g.all_win_brier_score, 3))));
  }
  return parts;
}

async function loadTrackedMulti() {
  const body = $('tracked-multi-body');
  if (!body) return;
  try {
    const res = await fetch('/api/tracked-multi');
    const data = await res.json();
    if (!res.ok) throw new Error();
    const sm = data.summary;
    if (!sm.tracked) { body.replaceChildren(h('p', { class: 'hint' }, 'No tracked multis yet.')); return; }
    const lg = sm.legs;
    const parts = [...multiGroupStats('Independent-game multis', sm.multis.independent_games),
      ...multiGroupStats('Same-game / correlated multis', sm.multis.same_game_correlated),
      h('p', { class: 'hint' }, `${sm.combined_note} Same-game multis are reported separately.`)];
    if (lg.graded) {
      parts.push(h('p', { class: 'group-title' }, 'Individual legs (source: multi legs)'),
        h('div', { class: 'tracked-summary' }, stat('Avg. probability', pct(lg.average_probability)),
          stat('Observed freq.', pct(lg.observed_frequency)), stat('Brier score', num(lg.brier_score, 3))),
        h('p', { class: 'hint' }, `Sample: ${lg.graded} settled leg${lg.graded === 1 ? '' : 's'}${lg.pushes ? ` (${lg.pushes} push${lg.pushes === 1 ? '' : 'es'} excluded)` : ''}. ${lg.note} Small samples can be noisy.`));
    }
    parts.push(h('ul', { class: 'recent-list' }, data.multis.map(trackedMultiItem)));
    body.replaceChildren(...parts);
  } catch (e) {
    body.replaceChildren(h('p', { class: 'hint' }, 'Tracked multis unavailable.'));
  }
}

function setTrackedTab(kind) {
  const multi = kind === 'multi';
  $('tracked-tab-single').setAttribute('aria-pressed', String(!multi));
  $('tracked-tab-multi').setAttribute('aria-pressed', String(multi));
  $('tracked-body').hidden = multi;
  $('tracked-multi-body').hidden = !multi;
}

function render(r) {
  const box = $('result');
  const parts = sections(r, ''), bar = trackBar(r);
  if (bar) parts.splice(parts.findIndex((el) => el.classList.contains('hero')) + 1, 0, bar);  // right below the pick
  box.replaceChildren(...parts);
  box.hidden = false;
  const guide = $('guide');
  if (guide) guide.hidden = true;
  const heading = box.querySelector('#hero-h');
  heading.setAttribute('tabindex', '-1');
  heading.focus();
}

// ---------- multiple selections: results ----------

const legTitle = (r) => `${r.player.kicker_name} · ${r.prop.side === 'over' ? 'Over' : 'Under'} ${r.prop.line} XPM`;
const SAME_GAME_PREFIX = 'These selections belong';

function legCard(leg, sameGame) {
  const title = `Selection ${leg.index}`, hid = `mr-leg-${leg.index}`;
  if (leg.status !== 'ok') {
    const e = leg.error, sel = leg.input || {};
    return h('section', { class: 'card leg-result failed', 'aria-labelledby': hid },
      h('h3', { id: hid }, `${title} failed: ${e.code}`),
      h('p', {}, e.message),
      ERROR_HINTS[e.code] ? h('p', { class: 'muted' }, ERROR_HINTS[e.code]) : null,
      sel.kicker ? h('p', { class: 'muted' }, `Input: ${sel.kicker} · ${sel.side} ${sel.line} · decimal odds ${dec(sel.decimal_odds)}`) : null);
  }
  const r = leg.result, g = r.game, c = comparable(r);
  const detailsBox = h('div', { class: 'leg-detail' });
  const more = h('details', { class: 'leg-more' }, h('summary', {}, 'Full analysis'), detailsBox);
  more.addEventListener('toggle', () => { if (more.open && !detailsBox.childElementCount) detailsBox.append(...sections(r, `leg${leg.index}-`)); });
  const verified = r.data_quality.kicker_current_team_verified;
  const games = r.features ? r.features.kicker_games_before : null;
  return h('section', { class: 'card leg-result', 'aria-labelledby': hid },
    h('div', { class: 'leg-head' },
      h('div', {},
        h('p', { class: 'eyebrow' }, title),
        h('h3', { id: hid, class: 'leg-name' }, legTitle(r)),
        h('p', { class: 'muted' }, `${teamName(r.teams, g.team)} · ${nickname(r.teams, g.away_team)} @ ${nickname(r.teams, g.home_team)} · ${kickoffLabel(g.kickoff, true)}`)),
      h('div', { class: 'pick' }, h('span', { class: 'eyebrow' }, 'Decimal odds'), h('span', { class: 'pick-text' }, dec(r.market.decimal_odds)))),
    sameGame ? h('p', { class: 'leg-flag' }, `Same game as selection ${sameGame.join(', ')}: correlated legs.`) : null,
    h('div', { class: 'stats' },
      stat('KickEdge probability' + (c.conditional ? ' (no push)' : ''), pct(c.p), 'sel'),
      stat('Odds-implied probability', pct(r.market.implied_probability)),
      diffStat('Difference', r.analysis.edge_raw_pp),
      stat('Expected XPM', num(r.prediction.expected_xpm))),
    Number.isInteger(r.prop.line) ? h('p', { class: 'muted' }, `Integer line: P(Win) ${pct(r.prop.model_side_probability)}, P(Push) ${pct(r.prop.p_push)}, P(Loss) ${pct(r.prop.p_loss)}.`) : null,
    h('p', { class: 'feedback-text' }, priceFeedback(r)),
    h('ul', { class: 'qsum' },
      h('li', { class: 'qchip ' + (verified === true ? 'ok' : 'warn') }, h('span', { class: 'qk' }, 'Kicker team'), h('span', { class: 'qv' }, verified === true ? 'Verified' : 'Not verified')),
      has(games) ? h('li', { class: 'qchip ' + (games < 5 ? 'warn' : 'ok') }, h('span', { class: 'qk' }, 'History'), h('span', { class: 'qv' }, `${games} games`)) : null,
      h('li', { class: 'qchip ' + (STATE_CLASS[weatherState(r)] || 'off') }, h('span', { class: 'qk' }, 'Weather'), h('span', { class: 'qv' }, weatherState(r)))),
    more);
}

function multiSummary(rec) {
  const c = rec.combined, failed = rec.selections.filter((l) => l.status !== 'ok');
  if (!rec.combined_available) {
    return h('section', { class: 'card summary', 'aria-labelledby': 'ms-h' },
      h('h2', { id: 'ms-h' }, 'Multi-selection summary'),
      h('p', { class: 'warnbox', role: 'alert' }, `Combined analysis unavailable: ${failed.map((l) => `selection ${l.index} failed (${l.error.code})`).join(', ')}. Correct ${failed.length === 1 ? 'it' : 'them'} and analyze again; KickEdge never combines a subset of your selections.`));
  }
  const diff = c.difference_pp;
  const lead = `The combined decimal price ${dec(c.combined_decimal_odds)} implies ${pct(c.implied_probability)}. Assuming independent selections, KickEdge's approximate all-win probability is ${pct(c.model_probability)}.`;
  const text = Math.abs(diff) < 1 ? `${lead} The two estimates are very close (difference ${signedPP(diff)}).`
    : `${lead} The model estimate is ${Math.abs(diff).toFixed(1)} percentage points ${diff > 0 ? 'higher' : 'lower'} than the probability implied by the combined price (${signedPP(diff)}).`;
  const sameGame = c.warnings.find((w) => w.startsWith(SAME_GAME_PREFIX));
  return h('section', { class: 'card summary', 'aria-labelledby': 'ms-h' },
    h('h2', { id: 'ms-h' }, 'Multi-selection summary'),
    sameGame ? h('div', { class: 'warnbox', role: 'alert' },
      h('strong', {}, 'Same-game selections'), h('p', {}, sameGame),
      h('p', { class: 'muted' }, `Games with more than one selection: ${c.same_game_ids.join(', ')}`)) : null,
    h('div', { class: 'stats' },
      stat('Selections', String(c.selection_count)),
      stat('Combined decimal odds', dec(c.combined_decimal_odds)),
      stat('Price-implied probability', pct(c.implied_probability)),
      stat('KickEdge approximate probability', pct(c.model_probability), 'sel'),
      diffStat('Difference', diff),
      has(c.no_loss_probability) ? stat('No-loss probability (approx.)', pct(c.no_loss_probability)) : null),
    h('p', { class: 'approx-label' }, 'Independence approximation: the product of each selection’s win probability. Not an exact combined probability.'),
    h('div', { class: 'feedback', role: 'note' }, h('h3', {}, 'Statistical feedback'), h('p', {}, text)),
    h('ul', { class: 'combined-notes' }, c.warnings.filter((w) => w !== sameGame).map((w) => h('li', {}, w))));
}

function renderMulti(rec) {
  const box = $('multi-result');
  const byGame = {};
  rec.selections.forEach((l) => { if (l.status === 'ok') (byGame[l.result.game.game_id] = byGame[l.result.game.game_id] || []).push(l.index); });
  const sameGame = (l) => {
    if (l.status !== 'ok') return null;
    const others = byGame[l.result.game.game_id].filter((i) => i !== l.index);
    return others.length ? others : null;
  };
  const banner = rec.stored && !rec.stored.fresh ? h('p', { class: 'banner', role: 'note' }, `Saved analysis from ${localTime(rec.generated_at)}. Shown as stored; nothing was re-run.`) : null;
  box.replaceChildren(...[banner, multiSummary(rec), trackMultiBar(rec), h('h2', { class: 'legs-title' }, 'Selections'),
    ...rec.selections.map((l) => legCard(l, sameGame(l)))].filter(Boolean));
  box.hidden = false;
  const guide = $('guide');
  if (guide) guide.hidden = true;
  const heading = box.querySelector('#ms-h');
  heading.setAttribute('tabindex', '-1');
  heading.focus();
}

// ---------- multiple selections: form ----------

const MAX_LEGS = 10, MIN_LEGS = 2;
const legs = [];
let legSeq = 0;

function legField(id, label, input) {
  return h('div', { class: 'field' }, h('label', { for: id }, label), input);
}

function addLeg() {
  if (legs.length >= MAX_LEGS) return null;
  const uid = ++legSeq, p = `leg${uid}`;
  const combo = (kind, label, placeholder) => {
    const input = h('input', { id: `${p}-${kind}`, type: 'text', role: 'combobox', 'aria-autocomplete': 'list', 'aria-expanded': 'false',
      'aria-controls': `${p}-${kind}-list`, 'aria-describedby': `${p}-${kind}-hint`, 'data-hint': `${p}-${kind}-hint`,
      autocomplete: 'off', spellcheck: 'false', maxlength: kind === 'kicker' ? '60' : null, placeholder });
    const clear = kind === 'game' ? h('button', { type: 'button', class: 'clear', id: `${p}-game-clear`, 'aria-label': 'Clear selected game', hidden: true }, '×') : null;
    const list = h('ul', { id: `${p}-${kind}-list`, role: 'listbox', 'aria-label': kind === 'game' ? 'Upcoming games' : 'Kickers', hidden: true });
    const hint = h('p', { id: `${p}-${kind}-hint`, class: 'hint' }, kind === 'game' ? 'Loading upcoming games…' : 'The team comes with the kicker.');
    return { node: h('div', { class: 'field combo' }, h('label', { for: input.id }, label), h('div', { class: 'combo-box' }, input, clear, list), hint), input, clear, list, hint };
  };
  const game = combo('game', 'Game', 'Search a team, e.g. Jaguars');
  const kicker = combo('kicker', 'Kicker', 'Choose a game first');
  const legend = h('legend', { class: 'leg-title' }, 'Selection');
  const remove = h('button', { type: 'button', class: 'secondary leg-remove' }, 'Remove');
  const odds = h('input', { id: `${p}-odds`, type: 'number', step: '0.01', min: '1.01', max: '1000', inputmode: 'decimal', placeholder: '1.91', class: 'decimal', autocomplete: 'off' });
  const other = h('input', { id: `${p}-other`, type: 'number', step: '0.01', min: '1.01', max: '1000', inputmode: 'decimal', placeholder: '1.91', class: 'decimal', autocomplete: 'off' });
  const card = h('fieldset', { class: 'leg', 'data-uid': uid },
    legend,
    h('div', { class: 'leg-tools' }, remove),
    game.node, kicker.node,
    h('div', { class: 'row3' },
      h('fieldset', { class: 'field side' }, h('legend', {}, 'Side'), h('div', { class: 'seg' },
        h('input', { type: 'radio', id: `${p}-over`, name: `${p}-side`, value: 'over', checked: true }), h('label', { for: `${p}-over` }, 'Over'),
        h('input', { type: 'radio', id: `${p}-under`, name: `${p}-side`, value: 'under' }), h('label', { for: `${p}-under` }, 'Under'))),
      legField(`${p}-line`, 'XPM line', h('input', { id: `${p}-line`, inputmode: 'decimal', placeholder: '1.5', maxlength: '4', autocomplete: 'off' })),
      legField(`${p}-odds`, 'Decimal odds', odds)),
    h('details', { class: 'advanced leg-advanced' }, h('summary', {}, 'Advanced'),
      h('div', { class: 'grid' },
        legField(`${p}-other`, 'Other side odds (decimal)', other),
        legField(`${p}-team`, 'Team (manual)', h('input', { id: `${p}-team`, maxlength: '40', placeholder: 'e.g. JAX', autocomplete: 'off' })),
        legField(`${p}-opponent`, 'Opponent (manual)', h('input', { id: `${p}-opponent`, maxlength: '40', placeholder: 'e.g. CIN', autocomplete: 'off' }))),
      h('p', { class: 'hint' }, 'Manual teams are used only when no game is selected. Other side odds enable the no-vig comparison.')),
    h('div', { class: 'leg-error', id: `${p}-err`, role: 'alert', hidden: true }));
  $('legs').append(card);
  for (const input of [odds, other]) input.addEventListener('blur', () => normalizeDecimalInput(input));
  const picker = makePicker({ game: game.input, gameList: game.list, gameClear: game.clear, gameHint: game.hint,
                              kicker: kicker.input, kickerList: kicker.list, kickerHint: kicker.hint });
  const leg = { uid, card, picker, legend, remove };
  remove.addEventListener('click', () => removeLeg(leg));
  legs.push(leg);
  renumberLegs();
  return leg;
}

function removeLeg(leg) {
  if (legs.length <= MIN_LEGS) return;
  const index = legs.indexOf(leg);
  catalog.pickers.delete(leg.picker);
  leg.card.remove();
  legs.splice(index, 1);
  renumberLegs();
  legs[Math.min(index, legs.length - 1)].card.querySelector('input').focus();
}

function renumberLegs() {
  legs.forEach((leg, i) => {
    leg.legend.textContent = `Selection ${i + 1}`;
    leg.remove.setAttribute('aria-label', `Remove selection ${i + 1}`);
    leg.remove.hidden = legs.length <= MIN_LEGS;
  });
  $('add-leg').disabled = legs.length >= MAX_LEGS;
  $('leg-count').textContent = `${legs.length} of ${MAX_LEGS} selections${legs.length >= MAX_LEGS ? ' (maximum reached)' : ''}`;
}

function collectLeg(leg) {
  const p = `leg${leg.uid}`, st = leg.picker, val = (s) => ($(`${p}-${s}`).value || '').trim();
  const side = leg.card.querySelector(`input[name="${p}-side"]:checked`).value;
  const sel = { side, line: parseLine(val('line'), `${p}-line`), decimal_odds: parseDecimal(val('odds'), `${p}-odds`, true) };
  const otherSide = parseDecimal(val('other'), `${p}-other`, false);
  if (otherSide !== null) Object.assign(sel, side === 'over'
    ? { over_decimal_odds: sel.decimal_odds, under_decimal_odds: otherSide }
    : { over_decimal_odds: otherSide, under_decimal_odds: sel.decimal_odds });
  const target = st.target();
  if (target) Object.assign(sel, target);
  else {
    const team = val('team'), opponent = val('opponent');
    if (!team && !opponent) throw new FieldError(`${p}-game`, 'Choose the game for this selection.');
    if (!/^[A-Za-z0-9 .'&-]{2,40}$/.test(team)) throw new FieldError(`${p}-team`, 'Enter the team, e.g. JAX.');
    if (!/^[A-Za-z0-9 .'&-]{2,40}$/.test(opponent)) throw new FieldError(`${p}-opponent`, 'Enter the opponent, e.g. CIN.');
    Object.assign(sel, { team, opponent });
  }
  sel.kicker = st.kickerValue();
  if (sel.kicker.length < 2) throw new FieldError(`${p}-kicker`, 'Choose or type the kicker.');
  return sel;
}

function legErrorBox(index) {
  const leg = legs[index - 1];
  return leg ? $(`leg${leg.uid}-err`) : null;
}

function showLegErrors(rec) {
  rec.selections.filter((l) => l.status !== 'ok').forEach((l) => {
    const box = legErrorBox(l.index);
    if (!box) return;
    const leg = legs[l.index - 1];
    const pickTeam = l.error.teams ? teamButtons(l.error.teams, (code) => {
      leg.picker.manualTeam = code;
      box.replaceChildren(h('p', {}, `Team set: ${l.error.teams.find((t) => t.code === code).name}. Analyze again.`));
    }) : null;
    box.replaceChildren(h('p', {}, h('strong', {}, `Selection ${l.index} failed: ${l.error.code}`), ` — ${l.error.message}`), pickTeam);
    box.hidden = false;
  });
}

async function submitMulti(event) {
  event.preventDefault();
  const form = event.currentTarget, button = $('multi-submit'), status = $('multi-status');
  if (button.disabled) return;
  clearErrors($('panel-multi'));
  $('multi-error').hidden = true;
  let selections;
  try { selections = legs.map(collectLeg); } catch (e) { if (e instanceof FieldError) { markField(e.field, e.message); return; } throw e; }
  const f = new FormData(form);
  button.disabled = true; form.setAttribute('aria-busy', 'true'); button.textContent = 'Analyzing…';
  status.textContent = `Analyzing ${selections.length} selections… each one runs the full single-pick pipeline.`;
  try {
    const res = await fetch('/api/analyze-multi', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selections, include_weather: f.has('include_weather'), refresh_data: f.has('refresh_data') }) });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data) {
      const err = (data && data.error) || { code: 'INTERNAL_ERROR', message: `Request failed (${res.status}).` };
      const m = /selections\.(\d+)\./.exec(err.message || '');
      const legBox = m ? legErrorBox(parseInt(m[1], 10) + 1) : null;
      if (legBox) { legBox.replaceChildren(h('p', {}, h('strong', {}, `Selection ${parseInt(m[1], 10) + 1}: ${err.code}`), ` — ${err.message}`)); legBox.hidden = false; }
      $('multi-result').hidden = true;
      showError(err.code, err.message, null, $('multi-error'));
      status.textContent = '';
    } else {
      renderMulti(data);
      showLegErrors(data);
      status.textContent = data.combined_available ? 'Analysis complete.' : 'Some selections failed; see the errors.';
      if ($('recent-list')) loadRecent();
    }
  } catch (e) {
    showError('NETWORK', 'The server could not be reached. Check that KickEdge is still running.', null, $('multi-error'));
    status.textContent = '';
  } finally {
    button.disabled = false; form.removeAttribute('aria-busy'); button.textContent = 'Analyze selections';
  }
}

// ---------- tabs ----------

function setMode(mode, focusTab) {
  for (const m of ['single', 'multi']) {
    const tab = $(`tab-${m}`), panel = $(`panel-${m}`), active = m === mode;
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.tabIndex = active ? 0 : -1;
    panel.hidden = !active;
    if (active && focusTab) tab.focus();
  }
  // Each mode keeps its own result and error areas; only the active mode's are shown.
  document.querySelectorAll('[data-mode]').forEach((box) => {
    if (box.dataset.mode !== mode) {
      if (!box.hidden) { box.dataset.parked = '1'; box.hidden = true; }
    } else if (box.dataset.parked) { delete box.dataset.parked; box.hidden = false; }
  });
}

function initTabs() {
  const tabs = ['single', 'multi'];
  tabs.forEach((m, i) => {
    const tab = $(`tab-${m}`);
    tab.addEventListener('click', () => setMode(m));
    tab.addEventListener('keydown', (ev) => {
      const move = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
      if (move) { ev.preventDefault(); setMode(tabs[(i + move + tabs.length) % tabs.length], true); }
      else if (ev.key === 'Home' || ev.key === 'End') { ev.preventDefault(); setMode(tabs[ev.key === 'Home' ? 0 : tabs.length - 1], true); }
    });
  });
}

// ---------- recent analyses ----------

async function loadRecent() {
  const list = $('recent-list');
  try {
    const res = await fetch('/api/analyses?limit=20');
    const data = await res.json();
    if (!res.ok) throw new Error();
    if (!data.analyses.length) { list.replaceChildren(h('li', { class: 'hint' }, 'No saved analyses yet.')); return; }
    list.replaceChildren(...data.analyses.map((a) => h('li', {}, a.kind === 'multi'
      ? h('button', { type: 'button', class: 'recent-item', 'data-id': a.id, 'data-kind': 'multi' },
          h('span', { class: 'ri-main' }, `${a.selection_count} selections · combined ${dec(a.combined_decimal_odds)}`),
          h('span', { class: 'ri-sub' }, `${a.legs.join(' · ')} · approx. ${pct(a.model_probability)}${a.same_game_correlation_warning ? ' · same game' : ''}`),
          h('span', { class: 'ri-time' }, localTime(a.generated_at)))
      : h('button', { type: 'button', class: 'recent-item', 'data-id': a.id, 'data-kind': 'single' },
          h('span', { class: 'ri-main' }, `${a.kicker} — ${a.side === 'over' ? 'Over' : 'Under'} ${a.line} · ${dec(a.decimal_odds)}${a.odds_format === 'american' ? ' (legacy US)' : ''}`),
          h('span', { class: 'ri-sub' }, `${a.matchup} · ${pct(a.probability)} · exp. ${num(a.expected_xpm)} XPM`),
          h('span', { class: 'ri-time' }, localTime(a.generated_at))))));
    list.querySelectorAll('button[data-id]').forEach((b) => b.addEventListener('click', () => openStored(b.dataset.id, b.dataset.kind)));
  } catch (e) {
    list.replaceChildren(h('li', { class: 'hint' }, 'Recent analyses unavailable.'));
  }
}

async function openStored(id, kind) {
  if (!/^[0-9a-f]{64}$/.test(id)) return;
  const multi = kind === 'multi';
  if ($('tab-single')) setMode(multi ? 'multi' : 'single');
  const status = $(multi ? 'multi-status' : 'status'), errorBox = $(multi ? 'multi-error' : 'error');
  clearErrors();
  errorBox.hidden = true;
  status.textContent = 'Opening saved analysis…';
  try {
    const res = await fetch(`/api/${multi ? 'multi' : 'analyses'}/${id}`);
    const data = await res.json();
    if (!res.ok) {
      showError((data && data.error && data.error.code) || 'ANALYSIS_NOT_FOUND', (data && data.error && data.error.message) || 'Saved analysis not found.', null, errorBox);
      status.textContent = '';
      return;
    }
    if (multi) renderMulti(data); else render(data);
    status.textContent = 'Saved analysis opened. Nothing was re-run.';
  } catch (e) {
    showError('NETWORK', 'The server could not be reached.', null, errorBox);
    status.textContent = '';
  }
}

// ---------- single pick: form ----------

let single = null;

function collect(form) {
  const f = new FormData(form);
  const text = (k) => (f.get(k) || '').toString().trim();
  const body = { side: text('side'), include_weather: f.has('include_weather'),
                 include_market: f.has('include_market'), refresh_data: f.has('refresh_data') };
  const teamOk = (v) => /^[A-Za-z0-9 .'&-]{2,40}$/.test(v);
  const target = single ? single.target() : null;
  if (target) Object.assign(body, target);
  else {
    body.team = text('team'); body.opponent = text('opponent');
    if (!body.team && !body.opponent && $('game')) throw new FieldError('game', 'Choose an upcoming game, or enter the teams under Advanced.');
    if (!teamOk(body.team)) throw new FieldError('team', 'Enter a team name or abbreviation, e.g. Rams or LAR.');
    if (!teamOk(body.opponent)) throw new FieldError('opponent', 'Enter the opponent, e.g. Eagles or PHI.');
    for (const k of ['season', 'week']) {
      const v = text(k);
      if (v) { if (!/^\d{1,4}$/.test(v)) throw new FieldError(k, 'Must be a whole number.'); body[k] = parseInt(v, 10); }
    }
    const gid = text('game_id').toUpperCase();
    if (gid) { if (!/^\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}$/.test(gid)) throw new FieldError('game_id', 'Format: 2026_04_GB_TB.'); body.game_id = gid; }
  }
  body.kicker = single ? single.kickerValue() : text('kicker').replace(/\s+/g, ' ');
  if (body.kicker.length < 2) throw new FieldError('kicker', 'Choose or type the kicker.');
  body.line = parseLine(text('line'), 'line');
  body.decimal_odds = parseDecimal(text('odds'), 'odds', true);
  const over = parseDecimal(text('over_odds'), 'over_odds', false);
  const under = parseDecimal(text('under_odds'), 'under_odds', false);
  if ((over === null) !== (under === null)) throw new FieldError(over === null ? 'over_odds' : 'under_odds', 'Supply both Over and Under odds, or neither.');
  if (over !== null) {
    if ((body.side === 'over' ? over : under) !== body.decimal_odds) throw new FieldError('odds', 'Odds must equal the selected side of the paired quote.');
    body.over_decimal_odds = over; body.under_decimal_odds = under;
  }
  return body;
}

async function submit(event) {
  event.preventDefault();
  const form = event.currentTarget, button = $('submit'), status = $('status');
  if (button.disabled) return;
  clearErrors($('panel-single') || undefined);
  $('error').hidden = true;
  let body;
  try { body = collect(form); } catch (e) { if (e instanceof FieldError) { markField(e.field, e.message); return; } throw e; }
  button.disabled = true; form.setAttribute('aria-busy', 'true');
  button.textContent = 'Analyzing…';
  status.textContent = 'Analyzing… building the pregame snapshot and running the model. The first run of the day may download NFL data.';
  try {
    const res = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data) {
      const err = (data && data.error) || { code: 'INTERNAL_ERROR', message: `Request failed (${res.status}).` };
      $('result').hidden = true;
      // Only when the kicker's team cannot be derived is it asked for, once.
      const extra = err.teams && single ? teamButtons(err.teams, (code) => { single.manualTeam = code; $('error').hidden = true; form.requestSubmit(); }) : null;
      showError(err.code, err.message, err.suggestions, $('error'), extra);
      status.textContent = '';
    } else {
      render(data);
      status.textContent = 'Analysis complete.';
      if ($('recent-list')) loadRecent();
    }
  } catch (e) {
    showError('NETWORK', 'The server could not be reached. Check that KickEdge is still running.');
    status.textContent = '';
  } finally {
    button.disabled = false; form.removeAttribute('aria-busy'); button.textContent = 'Analyze pick';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const form = $('pick');
  if (form) form.addEventListener('submit', submit);
  for (const id of ['error', 'multi-error']) if ($(id)) $(id).setAttribute('tabindex', '-1');
  document.querySelectorAll('input.decimal').forEach((input) => input.addEventListener('blur', () => normalizeDecimalInput(input)));
  if ($('game') && $('game-list')) {
    single = makePicker({ game: $('game'), gameList: $('game-list'), gameClear: $('game-clear'), gameHint: $('game-hint'),
                          kicker: $('kicker'), kickerList: $('kicker-list'), kickerHint: $('kicker-hint'), manualNote: true });
    $('game').dataset.hint = 'game-hint'; $('kicker').dataset.hint = 'kicker-hint';
  }
  if ($('tab-single')) initTabs();
  if ($('multi')) {
    $('multi').addEventListener('submit', submitMulti);
    $('add-leg').addEventListener('click', () => { const leg = addLeg(); if (leg) leg.card.querySelector('input').focus(); });
    addLeg(); addLeg();
  }
  if ($('game') || $('multi')) loadGames();
  if ($('recent-list')) loadRecent();
  loadTracked();
  if ($('tracked-tab-single')) {
    $('tracked-tab-single').addEventListener('click', () => setTrackedTab('single'));
    $('tracked-tab-multi').addEventListener('click', () => setTrackedTab('multi'));
    loadTrackedMulti();
  }
});
