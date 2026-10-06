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
from typing import Annotated, Literal

from fastapi import FastAPI, Path as PathParam, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from kickedge.current.catalog import kicker_candidates, upcoming_games
from kickedge.current.engine import analyze_current_prop, current_season
from kickedge.current.multi import MAX_SELECTIONS, MIN_SELECTIONS, analyze_selections
from kickedge.current.optional import collect_context
from kickedge.current import tracking
from kickedge.current.snapshot import digest
from kickedge.current.sources import CurrentSourceError, load_current_sources
from kickedge.inference.odds import american_to_decimal
from kickedge.io import write_json
from kickedge.teams import normalize_team, team_display
from .artifact import ensure_model

ROOT = Path(os.environ.get('KICKEDGE_ROOT', '.')).resolve()
STATIC = Path(__file__).with_name('static')
ANALYSES_DIR = ROOT/'data/current/analyses'
TRACKED_DIR = ROOT/'data/current/tracked'
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


KICKER = r"^[\w .'\-]+$"
TEAM = r"^[A-Za-z0-9 .'&\-]+$"
# Decimal odds (stake included) are the primary price format; never strings, NaN or infinity.
DecimalOdds = Annotated[float, Field(strict=True, gt=1, le=1000, allow_inf_nan=False)]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kicker: str = Field(min_length=2, max_length=60, pattern=KICKER)
    # Codes, aliases or names (LAR, Rams, Los Angeles Rams); normalized server-side.
    # Optional with a game_id: the kicker's team is then derived, never asked twice.
    team: str | None = Field(default=None, min_length=2, max_length=40, pattern=TEAM)
    opponent: str | None = Field(default=None, min_length=2, max_length=40, pattern=TEAM)
    line: float = Field(ge=0, le=20)
    side: Literal['over', 'under']
    decimal_odds: DecimalOdds | None = None
    over_decimal_odds: DecimalOdds | None = None
    under_decimal_odds: DecimalOdds | None = None
    # Legacy American prices, still accepted for older clients and scripts.
    odds: StrictInt | None = None
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


class SelectionRequest(BaseModel):
    """One leg of a multiple-selection analysis: decimal odds only."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kicker: str = Field(min_length=2, max_length=60, pattern=KICKER)
    game_id: str | None = Field(default=None, max_length=20, pattern=GAME_ID)
    team: str | None = Field(default=None, min_length=2, max_length=40, pattern=TEAM)
    opponent: str | None = Field(default=None, min_length=2, max_length=40, pattern=TEAM)
    season: StrictInt | None = Field(default=None, ge=2015, le=2100)
    week: StrictInt | None = Field(default=None, ge=1, le=23)
    line: float = Field(ge=0, le=20)
    side: Literal['over', 'under']
    decimal_odds: DecimalOdds
    over_decimal_odds: DecimalOdds | None = None
    under_decimal_odds: DecimalOdds | None = None

    @field_validator('kicker')
    @classmethod
    def _collapse_spaces(cls, value):
        return ' '.join(value.split())


class MultiRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[SelectionRequest] = Field(min_length=MIN_SELECTIONS, max_length=MAX_SELECTIONS)
    include_weather: bool = True
    refresh_data: bool = False


def _price(body):
    """(odds, over, under, format): decimal or legacy American, never mixed."""
    if (body.decimal_odds is None) == (body.odds is None):
        raise ValueError('Provide decimal odds (or legacy American odds), exactly one price')
    if body.decimal_odds is not None:
        if body.over_odds is not None or body.under_odds is not None:
            raise ValueError('Paired odds must use the same decimal format as the selected odds')
        return body.decimal_odds, body.over_decimal_odds, body.under_decimal_odds, 'decimal'
    if body.over_decimal_odds is not None or body.under_decimal_odds is not None:
        raise ValueError('Paired odds must use the same American format as the selected odds')
    return body.odds, body.over_odds, body.under_odds, 'american'


def _teams(team, opponent, game_id):
    """Canonical (team, opponent, notes); both None when a game lets the server derive them."""
    if team is None and opponent is None:
        if game_id is None:
            raise ValueError('Choose an upcoming game, or provide team and opponent')
        return None, None, []
    if team is None or opponent is None:
        raise ValueError('Provide both team and opponent, or neither with a selected game')
    canonical = normalize_team(team), normalize_team(opponent)
    notes = [f'Normalized {raw} \u2192 {code}' for raw, code in zip((team, opponent), canonical) if raw.upper() != code]
    return canonical[0], canonical[1], notes


def _error(status, code, message, **extra):
    return JSONResponse({'error': {'code': code, 'message': message} | extra}, status_code=status)


def _now():
    return datetime.now(timezone.utc)


# Ordered (fragment, status, code); messages come from the 7A/7B validators.
_KNOWN = (
    ('Kicker roster conflict', 409, 'KICKER_TEAM_MISMATCH'),
    ('Kicker team unresolved', 422, 'KICKER_TEAM_UNRESOLVED'),
    ('Choose an upcoming game', 422, 'INVALID_REQUEST'),
    ('Provide both team and opponent', 422, 'INVALID_REQUEST'),
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


def _error_extra(exc):
    """Structured help carried by resolver errors: game suggestions or the two teams."""
    extra = {}
    if getattr(exc, 'suggestions', None):
        extra['suggestions'] = exc.suggestions
    if getattr(exc, 'teams', None):
        extra['teams'] = [team_display(code) for code in exc.teams]
    return extra


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
        odds, over_odds, under_odds, odds_format = _price(body)
    except ValueError as exc:
        return _error(422, 'INVALID_ODDS', str(exc))
    try:
        team, opponent, input_notes = _teams(body.team, body.opponent, body.game_id)
    except ValueError as exc:
        status, code, message = classify(exc)
        return _error(status, code, message)
    no_market = not body.include_market
    notes = []
    if body.include_market and not _market_allowed():
        no_market = True
        notes.append('Market context skipped: provider requests are limited to one per minute.')
    try:
        result = analyze_current_prop(
            body.kicker, team, opponent, body.line, body.side, odds,
            over_odds=over_odds, under_odds=under_odds, odds_format=odds_format,
            season=body.season, week=body.week,
            game_id=body.game_id, root=ROOT, refresh_data=body.refresh_data,
            no_market=no_market, no_weather=not body.include_weather, source_loader=_locked_loader)
    except ValueError as exc:
        status, code, message = classify(exc)
        return _error(status, code, message, **_error_extra(exc))
    except OSError:
        return _error(503, 'NFL_SOURCE_UNAVAILABLE', 'Required data could not be read or downloaded')
    # The engine stored this exact result under its content digest; expose that id
    # (before web-only notes are added) so the pick can be tracked from the saved copy.
    stored = {'id': digest(result), 'saved_at': result['provenance']['analysis_generated_at'], 'fresh': True}
    quality = result['data_quality']
    quality['warnings'] = quality['warnings']+notes
    quality['market_requested'] = body.include_market
    quality['weather_requested'] = body.include_weather
    result['input_notes'] = input_notes
    return result | {'stored': stored}


@app.post('/api/analyze-multi')
def analyze_multi(body: MultiRequest, request: Request):
    """2-10 selections, each through the unchanged single-analysis pipeline."""
    if not _allow(request.client.host if request.client else 'unknown'):
        return _error(429, 'RATE_LIMITED', 'Too many analyses; wait a minute and retry')
    try:
        ensure_model(ROOT)
    except ValueError:
        return _error(503, 'MODEL_NOT_READY', 'Frozen model artifact unavailable or failed verification')
    bundles, contexts = {}, {}

    def loader(root, season, refresh=False, now=None, clock=None):
        # One verified NFL data load per season for the whole request (refresh at most once).
        if season not in bundles:
            bundles[season] = _locked_loader(root, season, refresh=body.refresh_data, now=now, clock=clock)
        return bundles[season]

    def context(target, player, **kwargs):
        # Market context is off for selections, so context depends only on the game.
        if target['game_id'] not in contexts:
            contexts[target['game_id']] = collect_context(target, player, **kwargs)
        return contexts[target['game_id']]

    def analyze_one(sel):
        team, opponent, _ = _teams(sel['team'], sel['opponent'], sel['game_id'])
        return analyze_current_prop(
            sel['kicker'], team, opponent, sel['line'], sel['side'], sel['decimal_odds'],
            over_odds=sel['over_decimal_odds'], under_odds=sel['under_decimal_odds'], odds_format='decimal',
            season=sel['season'], week=sel['week'], game_id=sel['game_id'], root=ROOT,
            no_market=True, no_weather=not body.include_weather, source_loader=loader,
            context_collector=context, output_dir=ANALYSES_DIR/'legs')

    def describe(exc):
        if isinstance(exc, OSError) and not isinstance(exc, CurrentSourceError):
            return {'code': 'NFL_SOURCE_UNAVAILABLE', 'message': 'Required data could not be read or downloaded'}
        _, code, message = classify(exc)
        return {'code': code, 'message': message} | _error_extra(exc)

    record = analyze_selections([s.model_dump() for s in body.selections], analyze_one, describe)
    record['generated_at'] = _now().isoformat()
    record['include_weather'] = body.include_weather
    if record['combined_available']:
        analysis_id = digest(record)
        write_json(ANALYSES_DIR/analysis_id/'multi.json', record)
        record = record | {'stored': {'id': analysis_id, 'saved_at': record['generated_at'], 'fresh': True}}
    return record


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


def _decimal_price(market):
    """(format, raw odds, decimal odds) for current and legacy American analyses."""
    if market.get('odds_format') == 'decimal':
        return 'decimal', market['decimal_odds'], market['decimal_odds']
    return 'american', market['american_odds'], american_to_decimal(market['american_odds'])


def _summary(analysis_id, r):
    game = r['game']
    teams = r.get('teams') or {}
    names = {code: (teams.get(code) or team_display(code))['nickname']
             for code in (game.get('home_team'), game.get('away_team')) if code}
    odds_format, odds, decimal = _decimal_price(r['market'])
    return {'kind': 'single', 'id': analysis_id, 'generated_at': r['provenance']['analysis_generated_at'],
            'kicker': r['player']['kicker_name'], 'team': game['team'], 'opponent': game['opponent'],
            'game_id': game['game_id'], 'kickoff': game.get('kickoff'),
            'matchup': f"{names.get(game.get('away_team'), game.get('away_team'))} @ "
                       f"{names.get(game.get('home_team'), game.get('home_team'))}",
            'side': r['prop']['side'], 'line': r['prop']['line'],
            'odds_format': odds_format, 'odds': odds, 'decimal_odds': decimal,
            'probability': r['prop']['model_side_probability'], 'expected_xpm': r['prediction']['expected_xpm']}


def _multi_summary(analysis_id, record):
    combined = record['combined']
    legs = [f"{leg['result']['player']['kicker_name']} {leg['result']['prop']['side'].title()} "
            f"{leg['result']['prop']['line']:g}" for leg in record['selections']]
    return {'kind': 'multi', 'id': analysis_id, 'generated_at': record['generated_at'],
            'selection_count': combined['selection_count'], 'legs': legs,
            'combined_decimal_odds': combined['combined_decimal_odds'],
            'implied_probability': combined['implied_probability'],
            'model_probability': combined['model_probability'],
            'same_game_correlation_warning': combined['same_game_correlation_warning']}


def _stored(analysis_id, name='analysis.json'):
    """Path of a stored analysis; the id pattern and resolution both confine it."""
    if not re.fullmatch(ANALYSIS_ID, analysis_id):
        return None
    base = ANALYSES_DIR.resolve()
    path = (base/analysis_id/name).resolve()
    return path if path.is_relative_to(base) and path.is_file() else None


@app.get('/api/analyses')
def analyses(limit: int = Query(default=30, ge=1, le=100)):
    """Most recent locally stored analyses; files are only read, never re-run."""
    found = []
    if ANALYSES_DIR.is_dir():
        for child in ANALYSES_DIR.iterdir():
            for name, summarize in (('analysis.json', _summary), ('multi.json', _multi_summary)):
                path = _stored(child.name, name)
                if path:
                    found.append((path.stat().st_mtime, child.name, path, summarize))
    items = []
    for _, analysis_id, path, summarize in sorted(found, key=lambda f: f[:2], reverse=True)[:limit]:
        try:
            items.append(summarize(analysis_id, json.loads(path.read_text(encoding='utf-8'))))
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


@app.get('/api/multi/{analysis_id}')
def stored_multi(analysis_id: str = PathParam(pattern=ANALYSIS_ID)):
    """A stored multiple-selection analysis, read as saved; nothing is re-run."""
    path = _stored(analysis_id, 'multi.json')
    if path is None:
        return _error(404, 'ANALYSIS_NOT_FOUND', 'Stored analysis not found')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return _error(404, 'ANALYSIS_NOT_FOUND', 'Stored analysis could not be read')
    saved = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return record | {'stored': {'id': analysis_id, 'saved_at': saved}}


class TrackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    analysis_id: str = Field(pattern=ANALYSIS_ID)


class SettleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    actual_xpm: StrictInt = Field(ge=0, le=tracking.MAX_ACTUAL_XPM)


_TRACKING_STATUS = {'INVALID_TRACKING_ID': 422, 'INVALID_ACTUAL_XPM': 422, 'PICK_NOT_FOUND': 404,
                    'GAME_STARTED': 409, 'NOT_STARTED': 409, 'ALREADY_SETTLED': 409, 'PICK_TAMPERED': 409,
                    'INVALID_PICK': 422}
_tracking_lock = threading.Lock()


def _tracking_error(exc):
    return _error(_TRACKING_STATUS.get(getattr(exc, 'code', ''), 422), getattr(exc, 'code', 'INVALID_PICK'), str(exc))


@app.post('/api/tracked')
def track_pick(body: TrackRequest):
    """Freeze a saved pregame single analysis as an official pick; the client sends only its id."""
    path = _stored(body.analysis_id)
    if path is None:
        return _error(404, 'ANALYSIS_NOT_FOUND', 'Stored analysis not found')
    try:
        analysis = json.loads(path.read_text(encoding='utf-8'))
        with _tracking_lock:
            return tracking.track(TRACKED_DIR, analysis, body.analysis_id, _now())
    except tracking.TrackingError as exc:
        return _tracking_error(exc)
    except (OSError, ValueError, KeyError, TypeError):
        return _error(422, 'INVALID_PICK', 'This saved analysis cannot be tracked')


@app.get('/api/tracked')
def tracked_picks():
    """Tracked picks (open and settled) with a probability-quality summary; read only."""
    return tracking.list_tracked(TRACKED_DIR)


@app.get('/api/tracked/{tracking_id}')
def tracked_pick(tracking_id: str = PathParam(pattern=tracking.TRACKING_ID)):
    try:
        return tracking.load(TRACKED_DIR, tracking_id)
    except tracking.TrackingError as exc:
        return _tracking_error(exc)
    except (OSError, ValueError):
        return _error(404, 'PICK_NOT_FOUND', 'Tracked pick could not be read')


@app.post('/api/tracked/{tracking_id}/settle')
def settle_pick(body: SettleRequest, tracking_id: str = PathParam(pattern=tracking.TRACKING_ID)):
    """Add the actual XPM once, after kickoff; the frozen pick is never modified."""
    try:
        with _tracking_lock:
            return tracking.settle(TRACKED_DIR, tracking_id, body.actual_xpm, _now())
    except tracking.TrackingError as exc:
        return _tracking_error(exc)
    except (OSError, ValueError):
        return _error(404, 'PICK_NOT_FOUND', 'Tracked pick could not be read')


@app.get('/')
def index():
    return FileResponse(STATIC/'index.html')


@app.get('/about')
def about():
    return FileResponse(STATIC/'about.html')


app.mount('/static', StaticFiles(directory=STATIC), name='static')
