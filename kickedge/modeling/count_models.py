"""Small, frozen count-model family. No randomized validation or early stopping."""
from copy import deepcopy
import warnings

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

from .dataset import predictor_columns
from .distributions import poisson_distribution
from .preprocessing import make_preprocessor


SEED = 42
CANDIDATES = [
    {'name': 'global_poisson', 'family': 'baseline', 'params': {}},
    {'name': 'poisson_glm_alpha_0.1', 'family': 'glm', 'params': {'alpha': 0.1, 'max_iter': 2000, 'tol': 1e-8}},
    {'name': 'poisson_glm_alpha_1.0', 'family': 'glm', 'params': {'alpha': 1., 'max_iter': 2000, 'tol': 1e-8}},
    {'name': 'poisson_boost_leaves_7', 'family': 'boost', 'params': {
        'max_leaf_nodes': 7, 'max_iter': 100, 'learning_rate': .05,
        'l2_regularization': 10., 'min_samples_leaf': 40,
        'early_stopping': False, 'random_state': SEED}},
    {'name': 'poisson_boost_leaves_15', 'family': 'boost', 'params': {
        'max_leaf_nodes': 15, 'max_iter': 100, 'learning_rate': .05,
        'l2_regularization': 10., 'min_samples_leaf': 40,
        'early_stopping': False, 'random_state': SEED}},
]


class CountModel:
    """A mean model plus Poisson predictive distribution, including its tail.

    Fit is restricted to Phase 5 seasons. `refit=True` expands the allowed
    years to 2024 only after selection; it never permits 2025. Predict accepts
    the exact approved feature schema, with no identifiers or target columns.
    """

    def __init__(self, config):
        self.config = deepcopy(config)
        if self.config not in CANDIDATES:
            raise ValueError('Model configuration must be from the frozen candidate ledger')
        self.fitted_ = False

    def _check_x(self, x):
        columns = predictor_columns()
        if list(x.columns) != columns:
            raise ValueError('Expected exactly the ordered 82 approved predictors')
        if not len(x):
            raise ValueError('Empty prediction/fit data')

    def fit(self, x, y, *, refit=False):
        self.fitted_ = False
        self._check_x(x)
        years = np.asarray(x['season'], dtype=float)
        if not np.isin(years, range(2016, 2025 if refit else 2024)).all():
            raise ValueError('Forbidden fitting season; 2025 is a blind holdout')
        y = np.asarray(y, dtype=float)
        if y.ndim != 1 or len(y) != len(x) or not np.isfinite(y).all() or (y < 0).any() or (y != np.floor(y)).any():
            raise ValueError('Target must be a finite nonnegative integer vector')
        if y.sum() <= 0:
            raise ValueError('Positive target sum is required to estimate a count model')
        self.fit_seasons_ = sorted(set(years.astype(int).tolist()))
        self.fit_row_count_ = len(y)
        self.features_ = predictor_columns()
        family = self.config['family']
        if family == 'baseline':
            self.mean_ = float(y.mean())
        else:
            estimator = (PoissonRegressor(**self.config['params']) if family == 'glm'
                         else HistGradientBoostingRegressor(loss='poisson', **self.config['params']))
            self.pipeline_ = Pipeline([
                ('preprocess', make_preprocessor(scale=family == 'glm')),
                ('regressor', estimator),
            ])
            with threadpool_limits(limits=1), warnings.catch_warnings():
                warnings.simplefilter('error', ConvergenceWarning)
                self.pipeline_.fit(x, y)
        self.fitted_ = True
        return self

    def predict(self, x):
        if not self.fitted_:
            raise ValueError('Model is not fitted')
        self._check_x(x)
        with threadpool_limits(limits=1):
            means = (np.full(len(x), self.mean_) if self.config['family'] == 'baseline'
                     else np.asarray(self.pipeline_.predict(x), dtype=float))
        if not np.isfinite(means).all() or (means <= 0).any():
            raise ValueError('Invalid predicted Poisson mean')
        return means

    def predict_distribution(self, x, max_display=12):
        return poisson_distribution(self.predict(x), max_display=max_display)
