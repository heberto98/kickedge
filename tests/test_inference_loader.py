from pathlib import Path
import shutil

import pytest

from kickedge.inference.loader import load_model


def test_missing_model_fails_closed(tmp_path):
    with pytest.raises(ValueError, match='artifact|model|metadata'):
        load_model(tmp_path)


def test_malformed_metadata_does_not_deserialize(tmp_path, monkeypatch):
    import kickedge.inference.loader as module
    (tmp_path/'metadata.json').write_text('{"selected":"wrong"}')
    (tmp_path/'model.joblib').write_bytes(b'invalid untrusted artifact')
    monkeypatch.setattr(module.joblib,'load',lambda *a,**k:pytest.fail('must not deserialize unverified data'))
    with pytest.raises(ValueError,match='metadata|hash'):
        load_model(tmp_path)


@pytest.fixture
def local_model_copy(tmp_path):
    source=Path('data/models/phase5')
    if not (source/'model.joblib').exists():
        pytest.skip('Frozen binary is intentionally local; release integrity tests need the local artifact')
    for name in ['metadata.json','model.joblib']:
        shutil.copyfile(source/name,tmp_path/name)
    return tmp_path


def test_exact_frozen_model_loads_without_training_or_dataset(local_model_copy, monkeypatch):
    from kickedge.modeling.count_models import CountModel
    monkeypatch.setattr(CountModel,'fit',lambda *a,**k:pytest.fail('inference cannot fit'))
    frozen=load_model(local_model_copy)
    assert frozen.info['feature_count']==82
    assert frozen.info['alpha']==.1
    assert frozen.info['training_period']=='2016-2024'
    assert frozen.info['phase6_verdict']=='PASS'


def test_tampered_artifact_rejected_before_deserialization(local_model_copy, monkeypatch):
    import kickedge.inference.loader as module
    with (local_model_copy/'model.joblib').open('ab') as stream:
        stream.write(b'tamper')
    monkeypatch.setattr(module.joblib,'load',lambda *a,**k:pytest.fail('unverified artifact'))
    with pytest.raises(ValueError,match='hash'):
        load_model(local_model_copy)
