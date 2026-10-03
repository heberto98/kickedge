"""Versioned V2 estimators. V1 modules are reused, never modified.

Candidates are fixed before any V2 result (docs/superpowers/plans/2026-10-03-kickedge-v2.md):
the V1-style GLM, two carryover GLMs, one carryover Poisson boosting model and a
structural challenger (conversion tries -> PAT choice -> kicker conversion, a
Poisson thinning). Fitting accepts 2016–2025 only; 2026 is never a fit season.
"""
from copy import deepcopy
import warnings

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from kickedge.modeling.dataset import predictor_columns
from kickedge.modeling.distributions import poisson_distribution
from kickedge.modeling.preprocessing import MedianWithAllIndicators, make_preprocessor
from .carryover import CARRYOVER_COLUMNS

SEED = 42
GLM = {'max_iter': 2000, 'tol': 1e-8}
CANDIDATES = [
    {'name': 'v1_style_glm_alpha_0.1', 'family': 'glm', 'features': 'v1', 'params': {'alpha': .1, **GLM}},
    {'name': 'carryover_glm_alpha_0.1', 'family': 'glm', 'features': 'carryover', 'params': {'alpha': .1, **GLM}},
    {'name': 'carryover_glm_alpha_1', 'family': 'glm', 'features': 'carryover', 'params': {'alpha': 1., **GLM}},
    {'name': 'carryover_poisson_boost', 'family': 'boost', 'features': 'carryover', 'params': {
        'max_leaf_nodes': 7, 'max_iter': 100, 'learning_rate': .05, 'l2_regularization': 10.,
        'min_samples_leaf': 40, 'early_stopping': False, 'random_state': SEED}},
    {'name': 'structural_tries_pat_conversion', 'family': 'structural', 'features': 'carryover',
     'params': {'tries_alpha': .1, 'logistic_C': 1., 'max_iter': 2000}},
]
STRUCTURAL_TARGETS = ('pat_attempts', 'two_pt_attempts', 'xpa', 'xpm')
FIT_SEASONS = range(2016, 2026)


def feature_columns(config):
    base = predictor_columns()
    return base if config['features'] == 'v1' else base + list(CARRYOVER_COLUMNS)


class NormalizeColumns(TransformerMixin, BaseEstimator):
    """V2 counterpart of V1 NormalizePredictors for an explicit ordered column list."""

    def __init__(self, columns=None):
        self.columns = columns

    def fit(self, X, y=None):
        self.transform(X)
        self.feature_names_in_ = np.asarray(self.columns, dtype=object)
        self.n_features_in_ = len(self.columns)
        return self

    def transform(self, X):
        expected = list(self.columns)
        if not isinstance(X, pd.DataFrame) or list(X.columns) != expected:
            raise ValueError('Expected exactly the ordered V2 predictor columns')
        result = X.copy()
        for name in expected:
            if name == 'game_type':
                if result[name].isna().any() or not result[name].map(lambda v: isinstance(v, str)).all():
                    raise ValueError('Invalid categorical game_type')
                continue
            numbers = pd.to_numeric(result[name], errors='raise').to_numpy(dtype=float, na_value=np.nan)
            if np.isinf(numbers).any():
                raise ValueError('Invalid numeric predictor: ' + name)
            result[name] = numbers
        return result

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.columns, dtype=object)


def make_v2_preprocessor(columns, scale):
    numeric = [name for name in columns if name != 'game_type']
    steps = [('impute', MedianWithAllIndicators())] + ([('scale', StandardScaler())] if scale else [])
    transformer = ColumnTransformer([
        ('numeric', Pipeline(steps), numeric),
        ('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['game_type']),
    ], remainder='drop', sparse_threshold=0)
    return Pipeline([('normalize', NormalizeColumns(list(columns))), ('columns', transformer)])


def _preprocessor(config, scale):
    # The V1-style candidate uses V1's own preprocessing object: identical to the audit clones.
    return make_preprocessor(scale) if config['features'] == 'v1' else make_v2_preprocessor(feature_columns(config), scale)


def _binomial(features, successes, failures, params):
    """L2 logistic MLE on aggregated counts (each row as a success and a failure record)."""
    keep = (successes + failures) > 0
    x = np.vstack([features[keep], features[keep]])
    labels = np.r_[np.ones(keep.sum()), np.zeros(keep.sum())]
    weights = np.r_[successes[keep], failures[keep]].astype(float)
    model = LogisticRegression(C=params['logistic_C'], max_iter=params['max_iter'])
    model.fit(x, labels, sample_weight=weights)
    return model


class V2Model:
    """Mean model with a Poisson predictive distribution; columns are checked on every call."""

    def __init__(self, config):
        if config not in CANDIDATES:
            raise ValueError('Model configuration must come from the V2 candidate ledger')
        self.config = deepcopy(config)
        self.fitted_ = False

    def _check(self, x):
        expected = feature_columns(self.config)
        if not isinstance(x, pd.DataFrame) or list(x.columns) != expected:
            raise ValueError('Expected exactly the ordered V2 predictor columns (no identifiers or targets)')
        if not len(x):
            raise ValueError('Empty predictor frame')

    def fit(self, x, y, *, structural_targets=None):
        self.fitted_ = False
        self._check(x)
        seasons = np.asarray(x['season'], dtype=float)
        if not np.isin(seasons, FIT_SEASONS).all():
            raise ValueError('Forbidden fitting season; V2 fits 2016–2025 only (2026 is forward evaluation)')
        y = np.asarray(y, dtype=float)
        if y.ndim != 1 or len(y) != len(x) or not np.isfinite(y).all() or (y < 0).any() or (y != np.floor(y)).any():
            raise ValueError('Target must be a finite nonnegative integer vector')
        self.fit_seasons_ = sorted(set(seasons.astype(int).tolist()))
        self.fit_row_count_ = len(y)
        self.features_ = feature_columns(self.config)
        family, params = self.config['family'], self.config['params']
        with threadpool_limits(limits=1), warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            if family in ('glm', 'boost'):
                estimator = (PoissonRegressor(**params) if family == 'glm'
                             else HistGradientBoostingRegressor(loss='poisson', **params))
                self.pipeline_ = Pipeline([('preprocess', _preprocessor(self.config, family == 'glm')),
                                           ('regressor', estimator)]).fit(x, y)
            else:
                if structural_targets is None:
                    raise ValueError('The structural challenger requires structural targets to fit')
                targets = pd.DataFrame(structural_targets).reset_index(drop=True)
                if len(targets) != len(x) or not set(STRUCTURAL_TARGETS) <= set(targets.columns):
                    raise ValueError('Invalid structural targets')
                # Copy outcomes: later caller mutations can never reach the fitted model.
                t = {name: targets[name].to_numpy(dtype=float, copy=True) for name in STRUCTURAL_TARGETS}
                self.preprocess_ = _preprocessor(self.config, True).fit(x)
                features = self.preprocess_.transform(x)
                tries = t['pat_attempts'] + t['two_pt_attempts']
                known = np.isfinite(tries)
                self.tries_ = PoissonRegressor(alpha=params['tries_alpha'], max_iter=params['max_iter'],
                                               tol=1e-8).fit(features[known], tries[known])
                ok = np.isfinite(t['pat_attempts']) & np.isfinite(t['two_pt_attempts'])
                self.pat_ = _binomial(features[ok], t['pat_attempts'][ok], t['two_pt_attempts'][ok], params)
                ok = np.isfinite(t['xpa']) & np.isfinite(t['xpm']) & (t['xpm'] <= t['xpa'])
                self.conversion_ = _binomial(features[ok], t['xpm'][ok], t['xpa'][ok] - t['xpm'][ok], params)
        self.fitted_ = True
        return self

    def predict_components(self, x):
        if self.config['family'] != 'structural':
            raise ValueError('Components exist only for the structural challenger')
        self._check(x)
        with threadpool_limits(limits=1):
            features = self.preprocess_.transform(x)
            return {'expected_td': self.tries_.predict(features),
                    'pat_probability': self.pat_.predict_proba(features)[:, 1],
                    'conversion_probability': self.conversion_.predict_proba(features)[:, 1]}

    def predict(self, x):
        if not self.fitted_:
            raise ValueError('Model is not fitted')
        self._check(x)
        if self.config['family'] == 'structural':
            parts = self.predict_components(x)
            means = parts['expected_td'] * parts['pat_probability'] * parts['conversion_probability']
        else:
            with threadpool_limits(limits=1):
                means = np.asarray(self.pipeline_.predict(x), dtype=float)
        if not np.isfinite(means).all() or (means <= 0).any():
            raise ValueError('Invalid predicted Poisson mean')
        return means

    def predict_distribution(self, x, max_display=12):
        return poisson_distribution(self.predict(x), max_display=max_display)
