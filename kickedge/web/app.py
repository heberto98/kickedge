"""KickEdge web service: a thin HTTP layer over the 7B pipeline and 7A engine.

All feature construction, prediction and price arithmetic stay in
``kickedge.current`` and ``kickedge.inference``. This module only validates
untrusted input, maps errors to HTTP and serves the static interface.
"""
from collections import defaultdict, deque
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Literal

from fastapi import FastAPI, Path as PathParam, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from kickedge.current.catalog import kicker_candidates, upcoming_games
from kickedge.current.engine import analyze_current_prop, current_season
from kickedge.current.sources import CurrentSourceError, load_current_sources
from kickedge.teams import normalize_team, team_display
from .artifact import ensure_model

ROOT = Path(os.environ.get('KICKEDGE_ROOT', '.')).resolve()
STATIC = Path(__file__).with_name('static')
ANALYSES_DIR = ROOT/'data/current/analyses'
GAME_ID = r'^\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}$'
ANALYSIS_ID = r'^[0-9a-f]{64}$'
MAX_BODY_BYTES = 4096
ANALYSES_PER_MINUTE = 12
MARKET_MIN_INTERVAL_SECONDS = 60
log = logging.getLogger('kickedge.web')

_source_lock = threading.Lock()
_limit_lock = threading.Lock()
_recent = defaultdict(deque)
_last_market = [0.]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kicker: str = Field(min_length=2, max_length=60, pattern=r"^[\w .'\-]+$")
    # Codes, aliases or names (LAR, Rams, Los Angeles Rams); normalized server-side.
    team: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9 .'&\-]+$")
    opponent: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9 .'&\-]+$")
    line: float = Field(ge=0, le=20)
    side: Literal['over', 'under']
    odds: StrictInt
    over_odds: StrictInt | None = None
    under_odds: StrictInt | None = None
    season: StrictInt | None = Field(default=None, ge=2015, le=2100)
    week: StrictInt | None = Field(default=None, ge=1, le=23)
    game_id: str | None = Field(default=None, max_length=20, pattern=GAME_ID)
    refresh_data: bool = False
    include_weather: bool = True
    include_market: bool = False

    @field_validator('kicker')
    @classmethod
    def _collapse_spaces(cls, value):
        return ' '.join(value.split())


def _error(status, code, message, **extra):
    return JSONResponse({'error': {'code': code, 'message': message} | extra}, status_code=status)


def _now():
    return datetime.now(timezone.utc)


# Ordered (fragment, status, code); messages come from the 7A/7B validators.
_KNOWN = (
    ('Kicker roster conflict', 409, 'KICKER_TEAM_MISMATCH'),
    ('Ambiguous team name', 422, 'INVALID_TEAM'),
    ('Unknown team', 422, 'INVALID_TEAM'),
    ('No matching future game', 404, 'GAME_NOT_FOUND'),
    ('Invalid target season or matchup', 404, 'GAME_NOT_FOUND'),
    ('Target game ambiguous', 409, 'GAME_AMBIGUOUS'),
    ('Kicker identity unresolved', 404, 'KICKER_NOT_FOUND'),
    ('Kicker identity ambiguous', 409, 'KICKER_AMBIGUOUS'),
    ('Schedule capture after feature cutoff', 409, 'STALE_DATA'),
    ('kickoff passed', 409, 'GAME_STARTED'),
    ('Target started', 409, 'GAME_STARTED'),
    ('inference unavailable', 503, 'MODEL_NOT_READY'),
    ('Frozen', 503, 'MODEL_NOT_READY'),
    ('odds', 422, 'INVALID_ODDS'),
    ('line', 422, 'INVALID_LINE'),
    ('Line', 422, 'INVALID_LINE'),
)


def classify(exc):
    if isinstance(exc, CurrentSourceError):
        return 503, 'NFL_SOURCE_UNAVAILABLE', str(exc)
    message = str(exc)
    for fragment, status, code in _KNOWN:
        if fragment in message:
            return status, code, message
    return 422, 'INVALID_REQUEST', message


def _locked_loader(*args, **kwargs):
    # One writer for the shared nflverse cache; atomic writes protect readers.
    with _source_lock:
        return load_current_sources(*args, **kwargs)


def _bundle(refresh=False):
    """Current-season bundle through the shared, locked 7B cache."""
    now = _now()
    return _locked_loader(ROOT, current_season(now), refresh=refresh, now=now), now


def _allow(client):
    now = time.monotonic()
    with _limit_lock:
        window = _recent[client]
        while window and now-window[0] > 60:
            window.popleft()
        if len(window) >= ANALYSES_PER_MINUTE:
            return False
        window.append(now)
        return True


def _market_allowed():
    now = time.monotonic()
    with _limit_lock:
        if now-_last_market[0] < MARKET_MIN_INTERVAL_SECONDS:
            return False
        _last_market[0] = now
        return True


app = FastAPI(title='KickEdge', docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def guard(request: Request, call_next):
    if request.method == 'POST':
        length = request.headers.get('content-length')
        if length is None or not length.isdigit():
            return _error(411, 'LENGTH_REQUIRED', 'Content-Length required')
        if int(length) > MAX_BODY_BYTES:
            return _error(413, 'REQUEST_TOO_LARGE', 'Request body too large')
    try:
        response = await call_next(request)
    except Exception as exc:
        log.error('Unhandled %s on %s', type(exc).__name__, request.url.path)
        response = _error(500, 'INTERNAL_ERROR', 'Internal error; no details exposed')
    if not request.url.path.startswith('/api/'):
        # Local app: always revalidate the interface so an update is never served stale.
        response.headers['Cache-Control'] = 'no-cache'
    response.headers.update({
        'Content-Security-Policy': "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
        'X-Frame-Options': 'DENY'})
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Report field names only; never echo the submitted values.
    fields = sorted({'.'.join(str(p) for p in e['loc'][1:]) or 'body' for e in exc.errors()})
    code = 'INVALID_ODDS' if any('odds' in f for f in fields) else (
        'INVALID_LINE' if 'line' in fields else 'INVALID_REQUEST')
    return _error(422, code, 'Invalid or missing fields: '+', '.join(fields))


@app.get('/healthz')
def healthz():
    return {'status': 'ok'}


@app.get('/readyz')
def readyz():
    try:
        model = ensure_model(ROOT)
    except ValueError:
        return _error(503, 'MODEL_NOT_READY', 'Frozen model artifact unavailable or failed verification')
    return {'status': 'ready', 'model_verified': True, 'model_version': model.info['version'],
            'artifact_sha256': model.info['artifact_sha256'], 'feature_count': model.info['feature_count']}


@app.get('/api/model')
def model_info():
    try:
        info = ensure_model(ROOT).info
    except ValueError:
        return _error(503, 'MODEL_NOT_READY', 'Frozen model artifact unavailable or failed verification')
    return {key: info[key] for key in ('name', 'version', 'model_type', 'alpha', 'training_period',
                                       'feature_count', 'feature_order', 'feature_contract_version',
                                       'artifact_sha256')} | {
        'artifact_verified': True, 'blind_validation_season': 2025,
        'blind_validation_verdict': info['phase6_verdict'], 'predictors_include_weather_or_market': False}


@app.post('/api/analyze')
def analyze(body: AnalyzeRequest, request: Request):
    if not _allow(request.client.host if request.client else 'unknown'):
        return _error(429, 'RATE_LIMITED', 'Too many analyses; wait a minute and retry')
    try:
        ensure_model(ROOT)
    except ValueError:
        return _error(503, 'MODEL_NOT_READY', 'Frozen model artifact unavailable or failed verification')
    try:
        team, opponent = normalize_team(body.team), normalize_team(body.opponent)
    except ValueError as exc:
        return _error(422, 'INVALID_TEAM', str(exc))
    input_notes = [f'Normalized {raw} → {code}' for raw, code in ((body.team, team), (body.opponent, opponent))
                   if raw.upper() != code]
    no_market = not body.include_market
    notes = []
    if body.include_market and not _market_allowed():
        no_market = True
        notes.append('Market context skipped: provider requests are limited to one per minute.')
    try:
        result = analyze_current_prop(
            body.kicker, team, opponent, body.line, body.side, body.odds,
            over_odds=body.over_odds, under_odds=body.under_odds, season=body.season, week=body.week,
            game_id=body.game_id, root=ROOT, refresh_data=body.refresh_data,
            no_market=no_market, no_weather=not body.include_weather, source_loader=_locked_loader)
    except ValueError as exc:
        status, code, message = classify(exc)
        suggestions = getattr(exc, 'suggestions', None)
        return _error(status, code, message, **({'suggestions': suggestions} if suggestions else {}))
    except OSError:
        return _error(503, 'NFL_SOURCE_UNAVAILABLE', 'Required data could not be read or downloaded')
    quality = result['data_quality']
    quality['warnings'] = quality['warnings']+notes
    quality['market_requested'] = body.include_market
    quality['weather_requested'] = body.include_weather
    result['input_notes'] = input_notes
    return result


@app.get('/api/games')
def games(refresh: bool = False):
    """Upcoming analyzable games of the current season, from the cached schedule."""
    try:
        bundle, now = _bundle(refresh)
    except (CurrentSourceError, OSError):
        return _error(503, 'NFL_SOURCE_UNAVAILABLE', 'NFL schedule could not be loaded; enter teams manually')
    schedule = next((s for s in bundle['sources'] if s['dataset'] == 'schedules'), {})
    return {'season': bundle['season'], 'generated_at': now.isoformat(),
            'schedule_fetched_at': schedule.get('fetched_at'), 'games': upcoming_games(bundle, now)}


@app.get('/api/games/{game_id}/kickers')
def game_kickers(game_id: str = PathParam(pattern=GAME_ID)):
    """Kicker candidates for both teams; roster status is labelled, never assumed."""
    try:
        bundle, now = _bundle()
    except (CurrentSourceError, OSError):
        return _error(503, 'NFL_SOURCE_UNAVAILABLE', 'NFL data could not be loaded; type the kicker manually')
    game = next((g for g in upcoming_games(bundle, now) if g['game_id'] == game_id), None)
    if game is None:
        return _error(404, 'GAME_NOT_FOUND', 'Game is not an upcoming game of the current season')
    players = next((s for s in bundle['sources'] if s['dataset'] == 'players'), {})
    return {'game': game, 'teams': kicker_candidates(bundle, game, now),
            'roster_source': {'dataset': 'nflverse players', 'fetched_at': players.get('fetched_at'),
                              'sha256': players.get('sha256')}}


def _summary(analysis_id, r):
    game = r['game']
    teams = r.get('teams') or {}
    names = {code: (teams.get(code) or team_display(code))['nickname']
             for code in (game.get('home_team'), game.get('away_team')) if code}
    return {'id': analysis_id, 'generated_at': r['provenance']['analysis_generated_at'],
            'kicker': r['player']['kicker_name'], 'team': game['team'], 'opponent': game['opponent'],
            'game_id': game['game_id'], 'kickoff': game.get('kickoff'),
            'matchup': f"{names.get(game.get('away_team'), game.get('away_team'))} @ "
                       f"{names.get(game.get('home_team'), game.get('home_team'))}",
            'side': r['prop']['side'], 'line': r['prop']['line'], 'odds': r['market']['american_odds'],
            'probability': r['prop']['model_side_probability'], 'expected_xpm': r['prediction']['expected_xpm']}


def _stored(analysis_id):
    """Path of a stored analysis; the id pattern and resolution both confine it."""
    if not re.fullmatch(ANALYSIS_ID, analysis_id):
        return None
    base = ANALYSES_DIR.resolve()
    path = (base/analysis_id/'analysis.json').resolve()
    return path if path.is_relative_to(base) and path.is_file() else None


@app.get('/api/analyses')
def analyses(limit: int = Query(default=30, ge=1, le=100)):
    """Most recent locally stored analyses; files are only read, never re-run."""
    found = []
    if ANALYSES_DIR.is_dir():
        for child in ANALYSES_DIR.iterdir():
            path = _stored(child.name)
            if path:
                found.append((path.stat().st_mtime, child.name, path))
    items = []
    for _, analysis_id, path in sorted(found, reverse=True)[:limit]:
        try:
            items.append(_summary(analysis_id, json.loads(path.read_text(encoding='utf-8'))))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {'analyses': items}


@app.get('/api/analyses/{analysis_id}')
def stored_analysis(analysis_id: str = PathParam(pattern=ANALYSIS_ID)):
    path = _stored(analysis_id)
    if path is None:
        return _error(404, 'ANALYSIS_NOT_FOUND', 'Stored analysis not found')
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return _error(404, 'ANALYSIS_NOT_FOUND', 'Stored analysis could not be read')
    saved = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return result | {'stored': {'id': analysis_id, 'saved_at': saved}}


@app.get('/')
def index():
    return FileResponse(STATIC/'index.html')


@app.get('/about')
def about():
    return FileResponse(STATIC/'about.html')


app.mount('/static', StaticFiles(directory=STATIC), name='static')
