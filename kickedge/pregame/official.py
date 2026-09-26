"""Download exact official pages and parse the article, never embedded galleries."""
import hashlib
import json
import re
import urllib.request

from kickedge.io import sha256_file, utc_now, write_json
from .select import instant, iso


def article_metadata(raw, url):
    candidates = []
    for text in re.findall(r'<script[^>]+type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>', raw, re.S):
        value = json.loads(text)
        if isinstance(value, dict) and value.get('@type') == 'NewsArticle' and value.get('url') == url:
            candidates.append(value)
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one matching NewsArticle: {url}')
    a = candidates[0]
    if not a.get('datePublished') or not a.get('dateModified'):
        raise ValueError(f'Missing article timestamps: {url}')
    return a


def ingest_official(config, claims_path, target, refresh=False):
    registry = json.loads(claims_path.read_text(encoding='utf-8'))
    old = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'sources': []}
    cache = {r['key']: r for r in old['sources']}
    result = []
    for spec in registry['sources']:
        if spec['key'] in cache and not refresh:
            r = cache[spec['key']]
            if r['url'] != spec['url'] or sha256_file(config.root / r['path']) != r['sha256']:
                raise ValueError('Official source cache mismatch')
        else:
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'KickEdge/0.1 historical research'})
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                raw = response.read()
            sha = hashlib.sha256(raw).hexdigest()
            p = config.data_dir / 'pregame/raw/official' / spec['key'] / sha / 'page.html'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            a = article_metadata(raw.decode('utf-8'), spec['url'])
            r = {**spec, 'sha256': sha, 'path': p.relative_to(config.root).as_posix(),
                 'downloaded_at': utc_now(), 'dates': {k: a[k] for k in ('datePublished', 'dateModified')}}
        result.append(r)
        write_json(target, {'sources': result})
    return target


def evidence(config, registry, manifest):
    cache = {r['key']: r for r in manifest['sources']}
    result = []
    for n, claim in enumerate(registry['claims']):
        r = cache[claim['source_key']]
        p = config.root / r['path']
        if sha256_file(p) != r['sha256']:
            raise ValueError('Changed official source')
        a = article_metadata(p.read_text(encoding='utf-8'), r['url'])
        for phrase in claim.get('required_phrases', []):
            if phrase not in a['articleBody']:
                raise ValueError(f'Claim anchor missing: {r["key"]}: {phrase}')
        result.append({**claim, 'evidence_id': f'official:{n:03}', 'source_url': r['url'],
            'source_sha256': r['sha256'], 'source_path': r['path'],
            'available_at': iso(max(instant(a['datePublished']), instant(a['dateModified']))),
            'published_at': a['datePublished'], 'modified_at': a['dateModified'],
            'downloaded_at': r['downloaded_at'], 'temporal_basis': 'publisher_article_metadata',
            'locator': 'NewsArticle.articleBody; manually reviewed claim; see required_phrases'})
    return result
