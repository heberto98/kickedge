"""Frozen preprocessing recipe; callers fit on TRAIN, then only transform VAL.

Each of the 81 numeric/boolean columns receives a missing indicator, including
columns first missing at prediction time. An entirely NULL fit column uses zero
as its explicit fallback median and retains its indicator. Scaling includes
indicators and is fitted only on the data supplied to fit.
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer, MissingIndicator
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from .dataset import predictor_columns


class NormalizePredictors(TransformerMixin, BaseEstimator):
    """Require the exact set, normalize order and reject nonnumeric data/infinity."""

    def fit(self, X, y=None):
        self.transform(X)
        self.feature_names_in_ = np.asarray(predictor_columns(), dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        return self

    def transform(self, X):
        expected = predictor_columns()
        if (not isinstance(X, pd.DataFrame) or X.columns.has_duplicates
                or len(X.columns) != len(expected) or set(X.columns) != set(expected)):
            raise ValueError('Predictor columns must match the exact 82-column contract')
        result = X.loc[:, expected].copy()
        for name in expected:
            if name == 'game_type':
                if result[name].isna().any() or not result[name].map(lambda v: isinstance(v, str)).all():
                    raise ValueError('Invalid categorical game_type')
                continue
            values = result[name]
            if not values.dropna().map(lambda v: isinstance(v, (int, float, bool, np.number))).all():
                raise ValueError('Invalid numeric predictor: ' + name)
            try:
                numbers = values.to_numpy(dtype=float, na_value=np.nan)
            except (TypeError, ValueError) as exc:
                raise ValueError('Invalid numeric predictor: ' + name) from exc
            if np.isinf(numbers).any():
                raise ValueError('Invalid numeric predictor: ' + name)
            result[name] = numbers
        return result

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self)
        return self.feature_names_in_.copy()


class MedianWithAllIndicators(TransformerMixin, BaseEstimator):
    """Median imputation with stable all-column indicators and zero NULL fallback."""

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        self.imputer_ = SimpleImputer(strategy='median', keep_empty_features=True).fit(X)
        self.indicator_ = MissingIndicator(features='all').fit(X)
        return self

    def transform(self, X):
        check_is_fitted(self, 'imputer_')
        return np.hstack([self.imputer_.transform(X), self.indicator_.transform(X).astype(float)])

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, 'imputer_')
        return np.concatenate([self.feature_names_in_, np.asarray(
            ['missingindicator_' + n for n in self.feature_names_in_], dtype=object)])


def make_preprocessor(scale: bool):
    """Create an unfitted transformer with dense, named interpretation features."""
    if not isinstance(scale, bool):
        raise ValueError('scale must be bool')
    numeric = [name for name in predictor_columns() if name != 'game_type']
    numeric_steps = [('impute', MedianWithAllIndicators())]
    if scale:
        numeric_steps.append(('scale', StandardScaler()))
    columns = ColumnTransformer([
        ('numeric', Pipeline(numeric_steps), numeric),
        ('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['game_type']),
    ], remainder='drop', sparse_threshold=0)
    return Pipeline([('normalize', NormalizePredictors()), ('columns', columns)])
