from dataclasses import replace

import pytest

from kickedge.config import Config
from kickedge.ingest import verify_source, sources
from kickedge.io import sha256_file


def test_content_hash_detects_changed_original_and_path_escape(tmp_path):
    data=tmp_path/'data'; data.mkdir()
    original=data/'original.parquet'; original.write_bytes(b'original')
    cfg=Config(tmp_path,2015,2025,2016,('REG',),'postgame',data,tmp_path/'reports')
    entry={'path':'data/original.parquet','sha256':sha256_file(original)}
    assert verify_source(cfg,entry)==original
    original.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed or corrupt'):
        verify_source(cfg,entry)
    outside=tmp_path/'outside.parquet';outside.write_bytes(b'outside')
    with pytest.raises(ValueError,match='outside data directory'):
        verify_source(cfg,{'path':str(outside),'sha256':sha256_file(outside)})


def test_source_universe_is_2015_to_2025_with_both_paths(tmp_path):
    cfg=Config(tmp_path,2015,2025,2016,('REG',),'postgame',tmp_path/'data',tmp_path/'reports')
    records=sources(cfg)
    assert len(records)==24
    assert len({(r['dataset'],r['season']) for r in records})==24
    for season in range(2015,2026):
        assert {r['dataset'] for r in records if r['season']==season}=={'pbp','player_stats'}
