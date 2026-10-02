import numpy as np
import pandas as pd
import pytest

from kickedge.modeling.dataset import predictor_columns
from kickedge.modeling.preprocessing import make_preprocessor


def frame():
    x = pd.DataFrame({name: [1., 3., np.nan] for name in predictor_columns()})
    x['game_type'] = ['REG', 'WC', 'REG']
    x['is_home'] = pd.Series([True, False, None], dtype='boolean')
    return x


def test_train_statistics_all_null_and_new_missing():
    train = frame()
    train['week'] = np.nan
    prep = make_preprocessor(False)
    result = prep.fit_transform(train)
    names = prep.get_feature_names_out().tolist()
    assert result.shape == (3, 164)
    assert result[2, names.index('numeric__kicker_games_before')] == 2
    assert result[0, names.index('numeric__week')] == 0
    val = train.iloc[:1].copy()
    val['kicker_games_before'] = 1000
    val['kicker_xpa_before'] = np.nan
    val['game_type'] = 'SB'
    output = prep.transform(val)
    assert output[0, names.index('numeric__missingindicator_kicker_xpa_before')] == 1
    assert output[0, names.index('numeric__kicker_xpa_before')] == 2
    assert output[0, names.index('categorical__game_type_REG')] == 0
    assert prep.transform(train)[2, names.index('numeric__kicker_games_before')] == 2


def test_scaling_fitted_on_train_and_column_reordering():
    train = frame()
    prep = make_preprocessor(True).fit(train)
    val = train.iloc[:1].copy()
    val['kicker_games_before'] = 100
    assert prep.transform(val)[0, 0] > 100
    np.testing.assert_allclose(prep.transform(train), prep.transform(train[train.columns[::-1]]))


def test_bad_numeric_schema_and_missing_boolean():
    x = frame()
    prep = make_preprocessor(False)
    assert np.isfinite(prep.fit_transform(x)).all()
    with pytest.raises(ValueError, match='columns'):
        prep.transform(x.assign(xpm=1))
    with pytest.raises(ValueError, match='numeric'):
        prep.transform(x.assign(kicker_games_before='bad'))
    with pytest.raises(ValueError, match='numeric'):
        prep.transform(x.assign(kicker_games_before=np.inf))
