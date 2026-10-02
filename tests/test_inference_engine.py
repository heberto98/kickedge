import copy
import json
from pathlib import Path
import socket

import pytest

from kickedge.inference.contracts import read_snapshot, FeatureSnapshot
from kickedge.inference.engine import analyze


def test_external_predictor_cannot_bypass_release_verification():
    from types import SimpleNamespace
    fake = SimpleNamespace(predict=lambda frame: [99.], info={'version': 'unverified'}, categories=('REG',))
    snapshot = read_snapshot('examples/inference_demo_2024.json')
    with pytest.raises(TypeError, match='model'):
        analyze(snapshot, 2.5, 'over', 119, model=fake)


@pytest.fixture
def loaded():
    from kickedge.inference.loader import load_model
    if not Path('data/models/phase5/model.joblib').exists():
        pytest.skip('Frozen release binary is local and intentionally ignored')
    return load_model()


def test_frozen_demo_deterministic_no_fit_network_or_dotenv(loaded, monkeypatch):
    from kickedge.modeling.count_models import CountModel
    from sklearn.pipeline import Pipeline
    import dotenv
    forbidden=lambda *a,**k:pytest.fail('No fitting/network/dotenv allowed in inference')
    monkeypatch.setattr(CountModel,'fit',forbidden)
    monkeypatch.setattr(Pipeline,'fit',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(dotenv,'load_dotenv',forbidden)
    snapshot=read_snapshot('examples/inference_demo_2024.json')
    a=analyze(snapshot,2.5,'over',119)
    b=analyze(snapshot,2.5,'over',119)
    assert a==b
    json.dumps(a,allow_nan=False)
    distribution=a['prediction']['distribution']
    assert sum(distribution['probabilities'])+distribution['tail_probability']==pytest.approx(1)
    assert min(distribution['probabilities'])>=0
    assert a['data_quality']['demo'] is True
    assert a['data_quality']['model_verified'] is True
    assert a['prop']['p_push']==0


def test_props_and_metadata_never_enter_model(loaded):
    snapshot=read_snapshot('examples/inference_demo_2024.json')
    a=analyze(snapshot,2.5,'over',119)
    b=analyze(snapshot,2.,'under',-110,over_odds=-110,under_odds=-110)
    assert a['prediction']==b['prediction']
    assert b['prop']['p_push']>0
    assert b['prop']['price_probability_basis']=='conditional on no push'
    assert sum(b['prop'][k] for k in ['p_over','p_under','p_push'])==pytest.approx(1)
    assert b['market']['no_vig_probability']==.5


def test_snapshot_revalidated_after_mutation_and_unknown_category_warned(loaded):
    snapshot=read_snapshot('examples/inference_demo_2024.json')
    snapshot.features['xpm']=3
    with pytest.raises(ValueError):
        analyze(snapshot,2.5,'over',119)
    snapshot=read_snapshot('examples/inference_demo_2024.json')
    snapshot.features['game_type']='UNSEEN'
    result=analyze(snapshot,2.5,'over',119)
    assert any('categor' in w for w in result['data_quality']['warnings'])


def test_timestamp_and_identity_override_rejected(loaded):
    snapshot=read_snapshot('examples/inference_demo_2024.json')
    with pytest.raises(ValueError,match='timestamp'):
        analyze(snapshot,2.5,'over',119,timestamp='not a date')
    with pytest.raises(ValueError,match='metadata'):
        analyze(snapshot,2.5,'over',119,metadata_overrides={'team':'OTHER'})
