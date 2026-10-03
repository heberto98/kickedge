'use strict';
// KickEdge client: picks a game and kicker, collects the user's pick, calls
// /api/analyze and renders the engine's own numbers. No probability or price
// arithmetic is redone here; display only.

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
const signed = (x, d) => (x > 0 ? '+' : x < 0 ? '−' : '±') + Math.abs(x).toFixed(d);

function kickoffLabel(iso, short) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const day = d.toLocaleDateString('en-US', { weekday: short ? 'short' : 'long', month: 'short', day: 'numeric' });
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return short ? `${day} · ${time}` : `${day} — ${time}`;
}
const localTime = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); };

class FieldError extends Error { constructor(field, message) { super(message); this.field = field; } }

function parseOdds(text, name, required) {
  const t = (text || '').trim();
  if (!t) { if (required) throw new FieldError(name, 'American odds are required, e.g. +115 or -140.'); return null; }
  if (!/^[+-]?\d{3,5}$/.test(t)) throw new FieldError(name, 'Use American odds such as +115, 115 or -140 (|odds| ≥ 100).');
  const v = parseInt(t, 10);
  if (Math.abs(v) < 100) throw new FieldError(name, 'American odds must be at least 100 in magnitude.');
  return v;
}

// ---------- state ----------

const state = { games: [], gamesLoaded: false, game: null, kickerTeams: [], kickersLoaded: false, kicker: null };
const nickname = (teams, code) => (teams && teams[code] && teams[code].nickname) || code;

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

function gameOptions(query) {
  const out = []; let week = null;
  for (const g of state.games) {
    if (query && !matches(query, g.search)) continue;
    if (g.week !== week) { week = g.week; out.push({ group: g.game_type === 'REG' ? `Week ${g.week}` : `${g.game_type} · Week ${g.week}` }); }
    out.push({ value: g, label: g.display_name,
      sub: [kickoffLabel(g.kickoff, true), g.venue].filter(Boolean).join(' · ') });
  }
  return out;
}

function kickerOptions(query) {
  const out = [];
  for (const team of state.kickerTeams) {
    const ks = team.kickers.filter((k) => !query || matches(query, k.kicker_name.toLowerCase() + ' ' + k.kicker_id.toLowerCase()));
    if (!ks.length) continue;
    out.push({ group: team.name });
    for (const k of ks) out.push({ value: k, label: k.kicker_name,
      sub: [k.roster_label, k.season_games ? `${k.season_games} game${k.season_games === 1 ? '' : 's'} this season` : 'No games this season'].join(' · ') });
  }
  return out;
}

function renderTeamChoice(game) {
  const box = $('kteam');
  const choices = [game.away, game.home].map((t) => [
    h('input', { type: 'radio', id: `kteam-${t.code}`, name: 'kteam', value: t.code }),
    h('label', { for: `kteam-${t.code}` }, t.nickname)]);
  box.replaceChildren(...choices.flat());
  $('kteam-field').hidden = false;
}

let gameBox = null, kickerBox = null;

async function selectGame(g) {
  state.game = g; state.kicker = null; state.kickerTeams = []; state.kickersLoaded = false;
  $('game').value = `${g.display_name} — ${kickoffLabel(g.kickoff, true)}`;
  $('game-clear').hidden = false;
  $('game-hint').textContent = [`Week ${g.week}`, kickoffLabel(g.kickoff), g.venue, g.roof ? `roof: ${g.roof}` : null].filter(Boolean).join(' · ');
  $('kicker').value = '';
  $('kicker').placeholder = 'Search the kicker, e.g. ' + (g.home ? g.home.nickname : 'name');
  renderTeamChoice(g);
  const hint = $('kicker-hint');
  hint.textContent = 'Loading kickers…';
  try {
    const res = await fetch(`/api/games/${encodeURIComponent(g.game_id)}/kickers`);
    const data = await res.json();
    if (!res.ok) throw new Error(data && data.error ? data.error.message : 'Kickers unavailable');
    if (state.game !== g) return;
    state.kickerTeams = data.teams; state.kickersLoaded = true;
    if (kickerBox) kickerBox.refresh();
    const count = data.teams.reduce((a, t) => a + t.kickers.length, 0);
    hint.textContent = count ? `${count} kicker${count === 1 ? '' : 's'} from nflverse roster and season data. Pick one, or type a name.`
                             : 'No kickers found for this game in nflverse data. Type the name and choose the team.';
  } catch (e) {
    state.kickersLoaded = true;
    hint.textContent = 'Kicker list unavailable. Type the kicker name or ID and choose the team.';
  }
}

function clearGame() {
  state.game = null; state.kicker = null; state.kickerTeams = [];
  $('game').value = ''; $('game-clear').hidden = true;
  $('kteam-field').hidden = true; $('kteam').replaceChildren();
  if (state.games.length) $('game-hint').textContent = `${state.games.length} upcoming games. Or use Advanced for a manual matchup.`;
  $('kicker-hint').textContent = 'Pick from the list, or type a name or nflverse ID.';
  $('game').focus();
}

function selectKicker(k) {
  state.kicker = k;
  $('kicker').value = k.kicker_name;
  const radio = $(`kteam-${k.team}`);
  if (radio) radio.checked = true;
  $('kicker-hint').textContent = `${k.roster_label}${k.season_games ? ` · ${k.season_games} game${k.season_games === 1 ? '' : 's'} this season` : ''}`;
}

async function initPickers() {
  gameBox = combobox($('game'), $('game-list'), { options: gameOptions, onSelect: selectGame,
    emptyText: () => state.gamesLoaded ? 'No upcoming game matches' : 'Loading upcoming games…',
    onType: () => { if (state.game) { state.game = null; state.kickerTeams = []; $('game-clear').hidden = true; $('kteam-field').hidden = true; } } });
  kickerBox = combobox($('kicker'), $('kicker-list'), { options: kickerOptions, onSelect: selectKicker,
    emptyText: () => !state.game ? 'Choose a game first, or keep typing a name or ID' : state.kickersLoaded ? 'No kicker matches; keep typing to use a name or ID' : 'Loading kickers…',
    onType: () => { state.kicker = null; } });
  $('game-clear').addEventListener('click', clearGame);
  try {
    const res = await fetch('/api/games');
    const data = await res.json();
    if (!res.ok) throw new Error(data && data.error ? data.error.message : 'Games unavailable');
    state.games = data.games.map((g) => ({ ...g, search: g.search.toLowerCase() }));
    state.gamesLoaded = true;
    gameBox.refresh();
    $('game-hint').textContent = state.games.length
      ? `${state.games.length} upcoming games in the ${data.season} schedule. Or use Advanced for a manual matchup.`
      : 'No upcoming games in the current schedule. Use Advanced for a manual matchup.';
  } catch (e) {
    state.gamesLoaded = true;
    $('game-hint').textContent = 'Upcoming games unavailable (NFL schedule could not be loaded). Use Advanced to enter the teams.';
  }
}

// ---------- form ----------

function collect(form) {
  const f = new FormData(form);
  const text = (k) => (f.get(k) || '').toString().trim();
  const body = { side: text('side'), include_weather: f.has('include_weather'),
                 include_market: f.has('include_market'), refresh_data: f.has('refresh_data') };
  const teamOk = (v) => /^[A-Za-z0-9 .'&-]{2,40}$/.test(v);
  if (state.game) {
    const g = state.game, team = text('kteam');
    if (!team) throw new FieldError('kteam', "Choose the kicker's team.");
    Object.assign(body, { team, opponent: team === g.home_team ? g.away_team : g.home_team,
                          game_id: g.game_id, season: g.season, week: g.week });
  } else {
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
  body.kicker = state.kicker ? state.kicker.kicker_id : text('kicker').replace(/\s+/g, ' ');
  if (body.kicker.length < 2) throw new FieldError('kicker', 'Choose or type the kicker.');
  const line = text('line');
  if (!/^\d{1,2}(\.[05])?$/.test(line)) throw new FieldError('line', 'XPM line must be a whole or half number, e.g. 1.5.');
  body.line = parseFloat(line);
  body.odds = parseOdds(text('odds'), 'odds', true);
  const over = parseOdds(text('over_odds'), 'over_odds', false);
  const under = parseOdds(text('under_odds'), 'under_odds', false);
  if ((over === null) !== (under === null)) throw new FieldError(over === null ? 'over_odds' : 'under_odds', 'Supply both Over and Under odds, or neither.');
  if (over !== null) {
    if ((body.side === 'over' ? over : under) !== body.odds) throw new FieldError('odds', 'Odds must equal the selected side of the paired quote.');
    body.over_odds = over; body.under_odds = under;
  }
  return body;
}

const ERROR_TITLES = {
  GAME_NOT_FOUND: 'No upcoming game found for that matchup', GAME_AMBIGUOUS: 'Ambiguous game',
  KICKER_NOT_FOUND: 'Kicker not found', KICKER_AMBIGUOUS: 'Ambiguous kicker',
  KICKER_TEAM_MISMATCH: 'Kicker listed on the other team', INVALID_TEAM: 'Team not recognized',
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
  INVALID_TEAM: 'Use a team name (Rams, Los Angeles Rams) or an abbreviation (LA, LAR).',
  NFL_SOURCE_UNAVAILABLE: 'Required NFL data could not be downloaded or verified. Try again later.',
  STALE_DATA: 'Cached sources are newer than the pregame cutoff; analysis would not be pregame.',
  MODEL_NOT_READY: 'The frozen model artifact is missing or failed verification. No analysis was run.',
};

function showError(code, message, suggestions) {
  const box = $('error');
  const list = (suggestions || []).length ? h('div', { class: 'suggest' },
    h('p', {}, 'Upcoming games involving these teams:'),
    h('ul', {}, suggestions.map((g) => h('li', {}, $('game')
      ? h('button', { type: 'button', class: 'linkish', 'data-game': g.game_id }, `${g.display_name} — Week ${g.week}, ${kickoffLabel(g.kickoff, true)}`)
      : `${g.display_name} — Week ${g.week}`)))) : null;
  box.replaceChildren(
    h('h2', {}, ERROR_TITLES[code] || 'Error'),
    h('p', {}, message),
    ERROR_HINTS[code] ? h('p', { class: 'muted' }, ERROR_HINTS[code]) : null,
    list,
    h('p', { class: 'code' }, code));
  box.querySelectorAll('button[data-game]').forEach((b) => b.addEventListener('click', () => {
    const g = state.games.find((x) => x.game_id === b.dataset.game) || (suggestions || []).find((x) => x.game_id === b.dataset.game);
    if (g) { box.hidden = true; selectGame(g); $('kicker').focus(); }
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

function clearErrors() {
  $('error').hidden = true;
  document.querySelectorAll('.field-error').forEach((e) => e.remove());
  document.querySelectorAll('[aria-invalid]').forEach((e) => {
    e.removeAttribute('aria-invalid');
    const keep = { game: 'game-hint', kicker: 'kicker-hint' }[e.id];
    if (keep) e.setAttribute('aria-describedby', keep); else e.removeAttribute('aria-describedby');
  });
}

// ---------- rendering ----------

function fmt(v, kind) {
  if (v === null || v === undefined) return 'Not available';
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

function storedBanner(r) {
  if (!r.stored) return null;
  return h('p', { class: 'banner', role: 'note' }, `Saved analysis from ${localTime(r.provenance.analysis_generated_at)}. Shown as stored; nothing was re-run.`);
}

function hero(r) {
  const prop = r.prop, side = prop.side, sideName = side === 'over' ? 'Over' : 'Under';
  const g = r.game, teams = r.teams;
  const matchup = g.home_team && g.away_team ? `${nickname(teams, g.away_team)} @ ${nickname(teams, g.home_team)}` : `${g.team} vs ${g.opponent}`;
  const integer = Number.isInteger(prop.line);
  return h('section', { class: 'card hero', 'aria-labelledby': 'hero-h' },
    h('div', { class: 'hero-top' },
      h('div', { class: 'hero-id' },
        h('h2', { id: 'hero-h' }, r.player.kicker_name),
        h('p', { class: 'matchup' }, matchup, h('span', { class: 'muted-inline' }, ` · kicks for ${nickname(teams, g.team)}`)),
        h('p', { class: 'muted' }, [kickoffLabel(g.kickoff), g.venue].filter(Boolean).join(' · '))),
      h('div', { class: 'pick' }, h('span', { class: 'eyebrow' }, 'Your pick'),
        h('span', { class: 'pick-text' }, `${sideName} ${prop.line} XPM`),
        h('span', { class: 'pick-odds' }, american(r.market.american_odds)))),
    h('div', { class: 'hero-main' },
      h('div', { class: 'prob' }, h('span', { class: 'eyebrow' }, 'KickEdge probability'),
        h('span', { class: 'prob-value', id: 'pick-probability' }, pct(prop.model_side_probability)),
        h('span', { class: 'muted' }, `that ${sideName} ${prop.line} wins`)),
      h('div', { class: 'prob xpm' }, h('span', { class: 'eyebrow' }, 'Expected XPM'),
        h('span', { class: 'prob-value small' }, num(r.prediction.expected_xpm)))),
    h('div', { class: 'stats' },
      stat('P(Over)', pct(prop.p_over), side === 'over' ? 'sel' : ''),
      stat('P(Under)', pct(prop.p_under), side === 'under' ? 'sel' : ''),
      integer ? stat('P(Push)', pct(prop.p_push), 'push') : null),
    (r.input_notes || []).length ? h('p', { class: 'note' }, r.input_notes.join(' · ')) : null);
}

function distribution(r) {
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
  return h('section', { class: 'card', 'aria-labelledby': 'dist-h' },
    h('h2', { id: 'dist-h' }, 'XPM distribution'),
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

function keyData(r) {
  const f = r.features;
  if (!f) {
    return h('section', { class: 'card', 'aria-labelledby': 'saw-h' }, h('h2', { id: 'saw-h' }, 'What KickEdge saw'),
      h('p', { class: 'muted' }, 'Model inputs were not stored with this older analysis.'));
  }
  return h('section', { class: 'card', 'aria-labelledby': 'saw-h' },
    h('h2', { id: 'saw-h' }, 'What KickEdge saw'),
    h('p', { class: 'muted' }, 'Selected model inputs from the pregame snapshot: data the model used, not causal explanations. Differences compare recent games with the season average.'),
    h('div', { class: 'groups' }, KEY_DATA.map(([title, who, rows]) => h('div', { class: 'group' },
      h('h3', {}, who ? `${title} · ${nickname(r.teams, r.game[who])}` : title),
      h('dl', {}, rows.map(([k, label, kind, base]) => {
        const v = f[k], b = base ? f[base] : null;
        const delta = base && v !== null && v !== undefined && b !== null && b !== undefined
          ? h('span', { class: 'delta' }, `${signed(v - b, kind)} vs season`) : null;
        return [h('dt', {}, label), h('dd', { class: v === null || v === undefined ? 'na' : '' }, fmt(v, kind), delta)];
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

function quality(r) {
  const q = r.data_quality, f = r.features || {}, fresh = q.source_data_freshness || [];
  const oldest = fresh.length ? Math.max(...fresh.map((s) => s.age_seconds)) : null;
  const latest = q.latest_game_used, verified = q.kicker_current_team_verified;
  const games = f.kicker_games_before;
  const roster = (r.player && r.player.roster && r.player.roster.message) ||
    (verified ? 'Current team affiliation verified.' : 'Kicker identity is verified from NFL history, but current team affiliation could not be independently confirmed.');
  const short = games === undefined || games === null || games >= 5 ? null
    : `Only ${games} prior game${games === 1 ? '' : 's'} this season; ${games < 3 ? 'rolling-3 and rolling-5' : 'rolling-5'} inputs are unavailable and handled by the frozen preprocessing pipeline.`;
  const marketState = !q.market_requested ? 'Not requested' : (q.market_availability ? 'Available' : 'Unavailable');
  const stale = oldest !== null && oldest > 6 * 3600;
  const summary = [
    ['Game', q.target_game_verified ? 'Verified' : 'Unavailable'],
    ['Features', q.feature_schema_verified ? `${q.feature_count}/82` : 'Unavailable', q.feature_schema_verified ? 'ok' : 'off'],
    ['Source', oldest === null ? 'Unknown' : `${stale ? 'Stale' : 'Fresh'} · ${(oldest / 3600).toFixed(1)} h`, stale ? 'warn' : 'ok'],
    ['Kicker team', verified === true ? 'Verified' : 'Not verified'],
    ['History', games === undefined || games === null ? '—' : `${games} game${games === 1 ? '' : 's'}`, games !== undefined && games !== null && games < 5 ? 'warn' : 'ok'],
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
  return h('section', { class: 'card', 'aria-labelledby': 'dq-h' },
    h('h2', { id: 'dq-h' }, 'Data quality'),
    h('ul', { class: 'qsum' }, summary.map(([k, v, forced]) => h('li', { class: 'qchip ' + (forced || STATE_CLASS[v] || 'off') },
      h('span', { class: 'qk' }, k), h('span', { class: 'qv' }, v)))),
    h('p', { class: verified === true ? 'qnote' : 'qnote warn' }, roster),
    short ? h('p', { class: 'qnote' }, short) : null,
    h('details', {}, h('summary', {}, `View details${warnings.length ? ` and ${warnings.length} notes` : ''}`),
      h('ul', { class: 'dq' }, rows.map(([label, st, detail]) => h('li', {}, h('span', {}, label), chip(st), h('span', { class: 'muted' }, detail)))),
      warnings.length ? h('div', { class: 'notes' }, h('h3', {}, 'Notes and warnings'), h('ul', {}, warnings.map((w) => h('li', {}, w)))) : null));
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
    const has = (x) => x !== null && x !== undefined;
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

function context(r) {
  const mk = (r.context && r.context.market) || {};
  return h('section', { class: 'card', 'aria-labelledby': 'cx-h' },
    h('h2', { id: 'cx-h' }, 'Game context'),
    h('span', { class: 'tag' }, 'Context only — not currently used by the probability model'),
    h('div', { class: 'groups' },
      h('div', { class: 'group' }, h('h3', {}, 'Weather'), weatherBlock(r),
        h('p', { class: 'muted' }, `Roof: ${r.game.roof || 'unknown'} · Venue: ${r.game.venue || 'unknown'}${r.game.venue_city ? `, ${r.game.venue_city}` : ''}`)),
      h('div', { class: 'group' }, h('h3', {}, 'Market'),
        mk.available ? h('div', { class: 'scroll' }, h('table', {},
          h('thead', {}, h('tr', {}, ['Book', 'Spread (team)', 'Total', 'ML team', 'ML opp.'].map((t) => h('th', { scope: 'col' }, t)))),
          h('tbody', {}, (mk.quotes || []).map((q) => h('tr', {}, h('td', {}, (q.provenance || {}).bookmaker || '—'),
            h('td', {}, num(q.values.game_spread, 1)), h('td', {}, num(q.values.game_total, 1)),
            h('td', {}, american(q.values.moneyline_team)), h('td', {}, american(q.values.moneyline_opponent))))))) :
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

function render(r) {
  const box = $('result');
  box.replaceChildren(...[storedBanner(r), hero(r), distribution(r), keyData(r), quality(r), market(r), context(r), details(r)].filter(Boolean));
  box.hidden = false;
  const guide = $('guide');
  if (guide) guide.hidden = true;
  const heading = box.querySelector('#hero-h');
  heading.setAttribute('tabindex', '-1');
  heading.focus();
}

// ---------- recent analyses ----------

async function loadRecent() {
  const list = $('recent-list');
  try {
    const res = await fetch('/api/analyses?limit=20');
    const data = await res.json();
    if (!res.ok) throw new Error();
    if (!data.analyses.length) { list.replaceChildren(h('li', { class: 'hint' }, 'No saved analyses yet.')); return; }
    list.replaceChildren(...data.analyses.map((a) => h('li', {}, h('button', { type: 'button', class: 'recent-item', 'data-id': a.id },
      h('span', { class: 'ri-main' }, `${a.kicker} — ${a.side === 'over' ? 'Over' : 'Under'} ${a.line} · ${american(a.odds)}`),
      h('span', { class: 'ri-sub' }, `${a.matchup} · ${pct(a.probability)} · exp. ${num(a.expected_xpm)} XPM`),
      h('span', { class: 'ri-time' }, localTime(a.generated_at))))));
    list.querySelectorAll('button[data-id]').forEach((b) => b.addEventListener('click', () => openStored(b.dataset.id)));
  } catch (e) {
    list.replaceChildren(h('li', { class: 'hint' }, 'Recent analyses unavailable.'));
  }
}

async function openStored(id) {
  if (!/^[0-9a-f]{64}$/.test(id)) return;
  clearErrors();
  $('status').textContent = 'Opening saved analysis…';
  try {
    const res = await fetch(`/api/analyses/${id}`);
    const data = await res.json();
    if (!res.ok) {
      showError((data && data.error && data.error.code) || 'ANALYSIS_NOT_FOUND', (data && data.error && data.error.message) || 'Saved analysis not found.');
      $('status').textContent = '';
      return;
    }
    render(data);
    $('status').textContent = 'Saved analysis opened. Nothing was re-run.';
  } catch (e) {
    showError('NETWORK', 'The server could not be reached.');
    $('status').textContent = '';
  }
}

// ---------- submit ----------

async function submit(event) {
  event.preventDefault();
  const form = event.currentTarget, button = $('submit'), status = $('status');
  if (button.disabled) return;
  clearErrors();
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
      showError(err.code, err.message, err.suggestions);
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
  const err = $('error');
  if (err) err.setAttribute('tabindex', '-1');
  if ($('game') && $('game-list')) initPickers();
  if ($('recent-list')) loadRecent();
});
