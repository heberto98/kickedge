from pathlib import Path
import pytest


def test_actual_current_preparation_matches_frozen_2024_features():
    if not Path('data/features/kicker_inputs/125f3ca711124ac270c1/source.json').exists():
        pytest.skip('Frozen local event sources required for historical parity')
    from scripts.verify_current_parity import verify
    report=verify()
    assert report['case_count']==16
    assert all(c['matched'] and c['features_compared']==82 for c in report['cases'])
    assert len({c['team'] for c in report['cases']})>=3
