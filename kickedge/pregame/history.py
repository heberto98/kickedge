"""An outcome oracle physically partitioned by game, outside the identity builder."""
from collections import defaultdict
import json

import duckdb

from kickedge.io import records, sha256_file, write_json
from .select import instant


def prepare_oracle(base, directory):
    """Preparation is not prediction: no oracle content is passed to the selector."""
    metadata = json.loads((base / 'build.json').read_text(encoding='utf-8'))
    source_hashes = {}
    for filename in ('games.parquet', 'pbp_kicker_totals.parquet'):
        expected = next(a['sha256'] for a in metadata['artifacts'] if a['path'].endswith('/' + filename))
        if sha256_file(base / filename) != expected:
            raise ValueError('Historical oracle input failed integrity verification')
        source_hashes[filename] = expected
    directory.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    with duckdb.connect() as con:
        for r in records(con, 'SELECT game_id,team,player_id,pbp_xpa,pbp_fga,pbp_source_sha256 FROM read_parquet(?)', [str(base / 'pbp_kicker_totals.parquet')]):
            groups[r['game_id']].append(r)
        games = [r[0] for r in con.execute('SELECT game_id FROM read_parquet(?) ORDER BY game_id', [str(base / 'games.parquet')]).fetchall()]
    manifest = {}
    for game in games:
        p = directory / (game + '.json')
        write_json(p, sorted(groups[game], key=lambda r: (r['team'], r['player_id'])))
        manifest[game] = {'filename': p.name, 'sha256': sha256_file(p)}
    write_json(directory / 'manifest.json', manifest)
    write_json(directory / 'source.json', {'historical_build': base.name, 'source_hashes': source_hashes,
        'manifest_sha256': sha256_file(directory / 'manifest.json')})
    return manifest


class OutcomeOracle:
    def __init__(self, directory, manifest):
        self.directory, self.manifest = directory, manifest
        self.reads = []

    def reveal(self, game_id, now, reveal_at, frozen):
        if game_id not in frozen or instant(now) < instant(reveal_at):
            raise ValueError('Outcome requested before prediction freeze or historical reveal time')
        rec = self.manifest[game_id]
        p = self.directory / rec['filename']
        if sha256_file(p) != rec['sha256']:
            raise ValueError('Outcome oracle original changed')
        self.reads.append(game_id)
        return json.loads(p.read_text(encoding='utf-8'))
