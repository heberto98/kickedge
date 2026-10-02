import duckdb
import numpy as np
import pandas as pd
import pytest

from kickedge.modeling.dataset import holdout_info, load_split, predictor_columns


def fixture_frame():
    frame = pd.DataFrame({name: [1., 2., 3., 4.] for name in predictor_columns()})
    frame['season'] = [2016, 2023, 2024, 2025]
    frame['game_type'] = ['REG'] * 4
    frame['game_id'] = ['a', 'b', 'c', 'd']
    frame['team'] = ['BUF'] * 4
    frame['kicker_id'] = ['k'] * 4
    frame['eligible_for_phase_4_training'] = True
    frame['xpm'] = [0, 2, 3, 4]
    frame['experimental_weather'] = 999.
    return frame


def parquet(tmp_path, frame, name='data.parquet'):
    path = tmp_path / name
    with duckdb.connect() as con:
        con.register('fixture', frame)
        con.execute('COPY fixture TO ? (FORMAT PARQUET)', [str(path)])
    return path


def test_folds_and_frozen_selector(tmp_path):
    path = parquet(tmp_path, fixture_frame())
    for split, years in [('train', [2016, 2023]), ('validation', [2024]), ('refit', [2016, 2023, 2024])]:
        x, y = load_split(path, split)
        assert list(x.columns) == predictor_columns()
        assert x.season.tolist() == years
        assert len(x.columns) == 82
        assert len(y) == len(years)
    for split in ['holdout', '2025', 2025, 'arbitrary']:
        with pytest.raises(ValueError):
            load_split(path, split)


def test_target_and_holdout_mutations_do_not_change_train_predictors(tmp_path):
    frame = fixture_frame()
    x, y = load_split(parquet(tmp_path, frame), 'train')
    frame['xpm'] = [8, 9, 10, -999]
    frame.loc[frame.season == 2025, predictor_columns()] = np.nan
    other, mutated = load_split(parquet(tmp_path, frame, 'mutated.parquet'), 'train')
    pd.testing.assert_frame_equal(x, other)
    assert mutated.tolist() == [8, 9]
    assert y.tolist() == [0, 2]


@pytest.mark.parametrize('bad', [-1., 1.5, np.nan, np.inf])
def test_invalid_targets(tmp_path, bad):
    frame = fixture_frame()
    frame['xpm'] = frame['xpm'].astype(float)
    frame.loc[0, 'xpm'] = bad
    with pytest.raises(ValueError, match='target'):
        load_split(parquet(tmp_path, frame), 'train')


def test_duplicates_schema_and_eligibility(tmp_path):
    frame = fixture_frame()
    with pytest.raises(ValueError, match='Duplicate'):
        load_split(parquet(tmp_path, pd.concat([frame, frame.iloc[:1]])), 'train')
    with pytest.raises(ValueError, match='schema'):
        load_split(parquet(tmp_path, frame.drop(columns=[predictor_columns()[0]]), 'missing.parquet'), 'train')
    frame.loc[0, 'eligible_for_phase_4_training'] = False
    x, y = load_split(parquet(tmp_path, frame, 'eligible.parquet'), 'train')
    assert y.tolist() == [2]
    assert x.season.tolist() == [2023]


def test_blind_info_never_projects_targets(tmp_path):
    frame = fixture_frame().drop(columns='xpm')
    info = holdout_info(parquet(tmp_path, frame))
    assert info['row_count'] == 1
    assert 'xpm' not in {field['name'] for field in info['schema']}


def test_stable_identity_order(tmp_path):
    frame = fixture_frame().iloc[::-1].reset_index(drop=True)
    x, y = load_split(parquet(tmp_path, frame), 'refit')
    assert y.tolist() == [0, 2, 3]


@pytest.mark.parametrize('change', ['order', 'role', 'approval', 'candidate'])
def test_contract_cannot_expand_or_allow_bad_roles(monkeypatch, change):
    import kickedge.modeling.dataset as module
    contract = module.load_contract()
    first = contract['predictor_columns_through_phase_4'][0]
    if change == 'order':
        contract['predictor_columns_through_phase_4'].reverse()
    elif change == 'candidate':
        contract['phase_4_candidate_columns'].append(first)
    else:
        field = next(f for f in contract['fields'] if f['name'] == first)
        field['role' if change == 'role' else 'historical_training_approved'] = 'target' if change == 'role' else False
    monkeypatch.setattr(module, 'load_contract', lambda: contract)
    with pytest.raises(ValueError):
        predictor_columns()
