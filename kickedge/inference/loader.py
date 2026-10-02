"""Fail-closed loader for a pinned trusted local release, without dataset access."""
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
from importlib.resources import files
import io
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from kickedge.features import load_contract
from kickedge.io import sha256_file
from kickedge.modeling.count_models import CountModel, CANDIDATES
from kickedge.modeling.dataset import predictor_columns
from kickedge.modeling.preprocessing import MedianWithAllIndicators, NormalizePredictors


@dataclass(frozen=True)
class LoadedModel:
    _model: CountModel
    info: dict
    categories: tuple

    def predict(self, frame):
        return self._model.predict(frame)


def _canonical_hash(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def load_model(model_dir=Path('data/models/phase5')):
    """Verify bytes before joblib deserialization. Never download, fit or repair.

    The release manifest ships with reviewed code; callers cannot supply a new
    trust anchor through the CLI. This supports only the approved frozen model.
    """
    folder=Path(model_dir)
    try:
        release=json.loads(files(__package__).joinpath('release.json').read_text(encoding='utf-8'))
        meta=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise ValueError('Frozen model metadata/release missing or invalid; inference unavailable') from exc
    if _canonical_hash(meta)!=release['metadata_canonical_sha256']:
        raise ValueError('Frozen model metadata hash does not match approved release')
    try:
        blob=(folder/'model.joblib').read_bytes()
    except OSError as exc:
        raise ValueError('Frozen model artifact missing; inference unavailable') from exc
    digest=hashlib.sha256(blob).hexdigest()
    if digest!=release['artifact_sha256'] or digest!=meta['artifacts']['model.joblib']:
        raise ValueError('Frozen model artifact hash mismatch')
    source=Path(__file__).resolve().parents[1]
    if sha256_file(source/'features/contract.json')!=meta['contract_sha256']:
        raise ValueError('Frozen feature contract hash mismatch')
    for name,expected in meta['code_sha256'].items():
        if sha256_file(source/'modeling'/name)!=expected:
            raise ValueError('Frozen modeling source hash mismatch')
    if any(version(name)!=expected for name,expected in meta['versions'].items()):
        raise ValueError('Model runtime versions do not match frozen release')
    features=predictor_columns()
    if (meta['selected']!=CANDIDATES[1] or meta['features']!=features or len(features)!=82
            or meta['refit_seasons']!=list(range(2016,2025))):
        raise ValueError('Frozen model specification mismatch')
    try:
        # Deserialize the same verified bytes, not a path that could change after hashing.
        model=joblib.load(io.BytesIO(blob))
        if (not isinstance(model,CountModel) or not model.fitted_ or model.config!=CANDIDATES[1]
                or model.features_!=features or model.fit_seasons_!=meta['refit_seasons']
                or model.fit_row_count_!=meta['refit_rows']):
            raise ValueError('Fitted model structure mismatch')
        estimator=model.pipeline_['regressor']
        if not isinstance(estimator,PoissonRegressor) or any(getattr(estimator,k)!=v for k,v in CANDIDATES[1]['params'].items()):
            raise ValueError('Expected approved Poisson GLM alpha=0.1')
        prep=model.pipeline_['preprocess']
        if not isinstance(prep['normalize'],NormalizePredictors) or list(prep['normalize'].feature_names_in_)!=features:
            raise ValueError('Preprocessing feature order mismatch')
        cols=prep['columns']
        nums=cols.named_transformers_['numeric']
        cat=cols.named_transformers_['categorical']
        expected_numeric=[n for n in features if n!='game_type']
        if (not isinstance(nums['impute'],MedianWithAllIndicators)
                or list(nums['impute'].feature_names_in_)!=expected_numeric
                or nums['impute'].imputer_.strategy!='median'
                or not nums['impute'].imputer_.keep_empty_features
                or nums['impute'].indicator_.features!='all'
                or not isinstance(nums['scale'],StandardScaler)
                or not isinstance(cat,OneHotEncoder) or cat.handle_unknown!='ignore'
                or estimator.n_features_in_!=len(prep.get_feature_names_out())
                or not np.isfinite(estimator.coef_).all() or not np.isfinite(estimator.intercept_)):
            raise ValueError('Frozen preprocessing/estimator compatibility mismatch')
        categories=tuple(str(v) for v in cat.categories_[0])
    except Exception as exc:
        raise ValueError('Frozen model artifact incompatible with expected estimator/preprocessing') from exc
    info={'name':release['name'],'version':release['version'],'artifact_sha256':digest,
          'model_type':'Poisson GLM','alpha':.1,'training_period':'2016-2024',
          'feature_count':82,'feature_order':features,'feature_contract_version':load_contract()['schema_version'],
          'phase5_commit':release['phase5_commit'],'phase6_commit':release['phase6_commit'],
          'phase6_verdict':release['phase6_verdict']}
    return LoadedModel(model,info,categories)
