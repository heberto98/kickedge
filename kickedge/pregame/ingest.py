"""Additional public sources; downloads never prove historical availability."""
from dataclasses import replace
import json

from kickedge.ingest import download, verify_source, BASE
from kickedge.io import utc_now, write_json


def ingest(config, refresh=False):
    config=replace(config,data_dir=config.data_dir/'pregame')
    target=config.data_dir/'manifests/sources.json'
    previous=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'sources':[]}
    cache={(r['dataset'],r['season']):r for r in previous['sources']}
    manifest={'manifest_version':1,'created_at':utc_now(),'sources':[]}
    for season in config.seasons:
        for tag,filename in [('depth_charts',f'depth_charts_{season}.parquet'),
                             ('weekly_rosters',f'roster_weekly_{season}.parquet'),
                             ('injuries',f'injuries_{season}.parquet')]:
            source={'dataset':tag,'tag':tag,'season':season,'filename':filename,
                    'url':f'{BASE}/{tag}/{filename}'}
            key=tag,season
            if key in cache and not refresh:
                verify_source(config,cache[key]); record=cache[key]
                print(f'Verified: {filename}',flush=True)
            else:
                print(f'Downloading: {filename}',flush=True)
                record=download(config,source)
            manifest['sources'].append(record)
            write_json(target,manifest)
    snapshot=target.with_name('sources-'+manifest['created_at'].replace(':','').replace('+','_')+'.json')
    write_json(snapshot,manifest)
    return snapshot
