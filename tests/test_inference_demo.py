"""Reproduce a feature-only 2024 fixture; never project outcome columns."""
import json
from pathlib import Path

import pytest

from scripts.create_inference_demo import BUILD, create_demo


def test_demo_reproduces_from_frozen_feature_projection(tmp_path):
    source = Path('data/features/environment') / BUILD / 'kicker_game_features.parquet'
    if not source.exists():
        pytest.skip('Frozen local feature artifact intentionally excluded from Git')
    first, second = tmp_path / 'first.json', tmp_path / 'second.json'
    a = create_demo(source, first)
    b = create_demo(source, second)
    checked_in = json.loads(Path('examples/inference_demo_2024.json').read_text(encoding='utf-8'))
    assert a == b == checked_in
    assert first.read_bytes() == second.read_bytes()
    assert len(a['features']) == 82
    assert 'xpm' not in a['features']
    assert a['metadata']['game_id'].startswith('2024_')
    assert a['provenance']['demo'] is True
