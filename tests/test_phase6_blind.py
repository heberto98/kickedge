import json
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import pytest

from kickedge.io import sha256_file, write_json
from kickedge.modeling.count_models import CANDIDATES, CountModel
from kickedge.modeling.dataset import predictor_columns
from kickedge.validation.blind import baseline_mean, no_fitting, verify_frozen, prepare, reveal


def synthetic_root(tmp_path):
    """Entirely fictional 2025 data; never touch real local holdout."""
    root = tmp_path / 'repo'
    (root / 'reports').mkdir(parents=True)
    path = root / 'data/features/environment/synthetic/kicker_game_features.parquet'
    path.parent.mkdir(parents=True)
    columns = predictor_columns()
    frame = pd.DataFrame({c: np.ones(90) for c in columns})
    frame['season'] = [2016 + i % 9 for i in range(72)] + [2025] * 18
    frame['game_type'] = 'REG'
    frame['week'] = np.arange(90) % 18 + 1
    frame['xpm'] = np.arange(90) % 4
    frame['game_id'] = [f'game_{i:03}' for i in range(90)]
    frame['team'], frame['opponent'] = 'A', 'B'
    frame['kicker_id'], frame['kicker_name'] = 'k', 'Synthetic'
    frame['eligible_for_phase_4_training'] = True
    with duckdb.connect() as con:
        con.register('fixture', frame)
        con.execute('COPY fixture TO ? (FORMAT PARQUET)', [str(path)])
    model = CountModel(CANDIDATES[1]).fit(frame.loc[:71, columns], frame.loc[:71, 'xpm'], refit=True)
    folder = root / 'data/models/phase5'
    folder.mkdir(parents=True)
    joblib.dump(model, folder / 'model.joblib')
    # Verification checks installed original Phase5 source against this frozen manifest.
    source = Path(__file__).parents[1] / 'kickedge/modeling'
    from importlib.metadata import version
    meta = {'selected': CANDIDATES[1], 'features': columns, 'refit_seasons': list(range(2016,2025)),
            'refit_rows': 72, 'dataset_build_id': 'synthetic', 'dataset_sha256': sha256_file(path),
            'contract_sha256': sha256_file(source.parent / 'features/contract.json'),
            'code_sha256': {p.name: sha256_file(p) for p in source.glob('*.py')},
            'versions': {n:version(n) for n in ['numpy','pandas','scipy','scikit-learn','joblib','duckdb','threadpoolctl']},
            'artifacts': {'model.joblib': sha256_file(folder / 'model.joblib')},
            'holdout_2025_evaluated': False, 'holdout_2025_labels_loaded': False,
            'target_summary': {}, 'metrics_2024': {'poisson_glm_alpha_0.1': {
                'nll':2.,'rps':1.,'brier_ge_2':.25,'brier_ge_3':.25,'brier_ge_4':.25,
                'mae':1.5,'rmse':2.,'poisson_deviance':2.}},
            'diagnostics': {'top_features': [{'feature':'numeric__week'}]}}
    write_json(folder / 'metadata.json', meta)
    write_json(root / 'reports/phase5_metrics.json', meta)
    return root, frame


def test_baseline_and_fit_guards():
    assert baseline_mean([0,2,4], [2016,2020,2024]) == 2
    with pytest.raises(ValueError, match='2025|season'):
        baseline_mean([100], [2025])
    with no_fitting():
        from sklearn.preprocessing import StandardScaler
        with pytest.raises(RuntimeError, match='fit'):
            StandardScaler().fit([[1],[2]])
        with pytest.raises(RuntimeError, match='fit'):
            CountModel(CANDIDATES[0]).fit(None, None)
        from sklearn.isotonic import IsotonicRegression
        with pytest.raises(RuntimeError, match='fit'):
            IsotonicRegression().fit([.2,.8], [0,1])


def test_artifact_tampering_is_rejected_before_load(tmp_path):
    root, _ = synthetic_root(tmp_path)
    verify_frozen(root)
    with (root / 'data/models/phase5/model.joblib').open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(ValueError, match='hash'):
        verify_frozen(root)


def test_prepare_never_reads_targets_and_reveal_only_once(tmp_path, monkeypatch):
    import kickedge.validation.blind as module
    root, frame = synthetic_root(tmp_path)
    model_path = root / 'data/models/phase5/model.joblib'
    before = model_path.read_bytes()
    reader = module._read_targets
    calls = []
    def spy(path):
        assert (root / 'reports/phase6_preregistration.json').exists()
        assert (root / 'data/validation/phase6/reveal.lock').exists()
        calls.append(str(path))
        return reader(path)
    monkeypatch.setattr(module, '_read_targets', spy)
    with no_fitting():
        prepared = prepare(root)
        assert calls == []
        assert prepared['baseline_mean'] == pytest.approx(frame.loc[:71,'xpm'].mean())
        report = reveal(root)
    assert len(calls) == 1
    assert report['target_summary_2025']['count'] == 18
    assert report['sanity']['no_2025_fitting'] is True
    assert model_path.read_bytes() == before
    with pytest.raises(RuntimeError, match='already|once|reveal'):
        reveal(root)
    assert len(calls) == 1
    assert (root / 'reports/phase6_blind_validation.md').exists()


def test_changed_preparation_blocks_reveal_before_target_read(tmp_path, monkeypatch):
    import kickedge.validation.blind as module
    root, _ = synthetic_root(tmp_path)
    prepare(root)
    path = root / 'data/validation/phase6/prepared.joblib'
    with path.open('ab') as stream:
        stream.write(b'changed')
    monkeypatch.setattr(module,'_read_targets',lambda p: pytest.fail('targets must remain closed'))
    with pytest.raises(ValueError, match='hash'):
        reveal(root)


def test_failed_reveal_cannot_be_retried(tmp_path, monkeypatch):
    import kickedge.validation.blind as module
    root, _ = synthetic_root(tmp_path)
    prepare(root)
    def fail_read(path):
        raise ValueError('synthetic target read failure')
    monkeypatch.setattr(module,'_read_targets',fail_read)
    with pytest.raises(ValueError,match='synthetic'):
        reveal(root)
    assert (root/'data/validation/phase6/failure.json').exists()
    with pytest.raises(RuntimeError,match='already'):
        reveal(root)


def test_gate_rules_are_fixed_and_cover_all_verdicts():
    from kickedge.validation.blind import gate, METRICS
    m={k:1. for k in METRICS}
    m['calibration']={f'ge_{t}':{'ece':.02,'bias':.01} for t in [2,3,4]}
    b={k:1.1 for k in METRICS}
    boot={'estimates':{f'delta_{k}':{'upper':-.01} for k in ['nll','rps']}}
    comp={k:{'percent_change':0.} for k in METRICS}
    d={'missingness':{},'game_type':{'new_categories':[]}}
    assert gate(m,b,boot,comp,{},d)['verdict']=='PASS'
    boot['estimates']['delta_nll']['upper']=.01
    assert gate(m,b,boot,comp,{},d)['verdict']=='PASS WITH CAUTION'
    m['calibration']['ge_2']['ece']=.16
    assert gate(m,b,boot,comp,{},d)['verdict']=='FAIL'
    m['calibration']['ge_2']['ece']=.02
    assert gate(m,b,boot,comp,{},d,integrity=False)['verdict']=='FAIL'
    m['nll']=1.2
    assert gate(m,b,boot,comp,{},d)['verdict']=='FAIL'


def test_durable_lock_precedes_read_and_post_read_failure_consumes_reveal(tmp_path, monkeypatch):
    import kickedge.validation.blind as module
    root, _ = synthetic_root(tmp_path)
    prepare(root)
    work = root / 'data/validation/phase6'
    reader = module._read_targets
    fsync = module.os.fsync
    events = []

    def spy_fsync(fd):
        # The JSON must already be flushed and readable before durability is requested.
        marker = json.loads((work / 'reveal.lock').read_text(encoding='utf-8'))
        assert marker['status'] == 'consumed; never reset even after failure'
        fsync(fd)
        events.append('fsync')

    def spy_reader(path):
        assert events == ['fsync']
        outcomes = reader(path)
        events.append('read_returned')
        return outcomes

    def fail_metrics(*args, **kwargs):
        assert events == ['fsync', 'read_returned']
        raise ValueError('synthetic post-read statistics failure')

    monkeypatch.setattr(module.os, 'fsync', spy_fsync)
    monkeypatch.setattr(module, '_read_targets', spy_reader)
    monkeypatch.setattr(module, 'metrics', fail_metrics)
    with pytest.raises(ValueError, match='synthetic post-read'):
        reveal(root)
    failure = json.loads((work / 'failure.json').read_text(encoding='utf-8'))
    assert failure['blind_reveal_consumed'] is True
    assert failure['do_not_rerun'] is True
    assert failure['error_type'] == 'ValueError'
    assert failure['message'] == 'synthetic post-read statistics failure'
    assert (work / 'reveal.lock').exists()
    with pytest.raises(RuntimeError, match='already'):
        reveal(root)
    assert events == ['fsync', 'read_returned']
