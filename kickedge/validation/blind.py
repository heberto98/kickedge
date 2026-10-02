"""Prepare, then reveal one locked holdout once. Never fit or alter Phase 5."""
from contextlib import contextmanager, ExitStack
from importlib.metadata import version
import json
import os
from pathlib import Path
from unittest.mock import patch

import duckdb
import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer, MissingIndicator
from sklearn.linear_model import PoissonRegressor, LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from kickedge.io import sha256_file, utc_now, write_json
from kickedge.modeling.count_models import CANDIDATES, CountModel
from kickedge.modeling.dataset import load_split, predictor_columns
from kickedge.modeling.distributions import poisson_distribution
from kickedge.modeling.preprocessing import NormalizePredictors, MedianWithAllIndicators
from kickedge.modeling.train import target_summary
from .statistics import metrics, paired_bootstrap, distribution_summary, prop_summary
from .diagnostics import analyze_subgroups, drift, error_cases


KEYS = ['game_id', 'team', 'kicker_id']
IDENTITY = KEYS + ['opponent', 'kicker_name']
METRICS = ['nll','rps','brier_ge_2','brier_ge_3','brier_ge_4','mae','rmse','poisson_deviance']
POLICY = {
    'version': 'phase6-prereveal-v1', 'seed': 42, 'bootstrap_resamples': 1000,
    'calibration_reasonable_ece_max': .05, 'calibration_slight_ece_max': .10,
    'calibration_severe_fail_above': .15, 'global_bias_pass_max': .05,
    'pass_requires_paired_delta_nll_rps_upper95_below_zero': True,
    'signal_requires_nll_rps_improve_and_at_least_two_briers_improve': True,
    'subgroup_min_n': 50, 'subgroup_nll_warning_relative': .20,
    'year_degradation_warning_relative': .10, 'top_feature_missing_shift_warning': .10,
    'ece_is_descriptive_not_significance_test': True,
}


def _blocked_fit(*args, **kwargs):
    raise RuntimeError('All fit and calibration fitting are forbidden during blind validation')


@contextmanager
def no_fitting():
    """Tripwire around all model and preprocessing fit entry points in this workflow."""
    classes = [CountModel, Pipeline, ColumnTransformer, PoissonRegressor,
               HistGradientBoostingRegressor, SimpleImputer, MissingIndicator,
               StandardScaler, OneHotEncoder, NormalizePredictors, MedianWithAllIndicators,
               LogisticRegression, IsotonicRegression, CalibratedClassifierCV]
    with ExitStack() as stack:
        for cls in classes:
            for method in ('fit', 'fit_transform'):
                if hasattr(cls, method):
                    stack.enter_context(patch.object(cls, method, _blocked_fit))
        yield


def baseline_mean(y, seasons):
    y, seasons = np.asarray(y, float), np.asarray(seasons)
    if y.ndim != 1 or not len(y) or seasons.shape != y.shape or not np.isin(seasons, range(2016,2025)).all():
        raise ValueError('Baseline seasons must precede 2025')
    if not np.isfinite(y).all() or (y<0).any() or (y!=np.floor(y)).any() or y.mean()<=0:
        raise ValueError('Invalid baseline targets')
    return float(y.mean())


def verify_frozen(root):
    root = Path(root)
    folder = root / 'data/models/phase5'
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    tracked = json.loads((root / 'reports/phase5_metrics.json').read_text(encoding='utf-8'))
    if meta != tracked:
        raise ValueError('Phase 5 local metadata differs from its versioned record')
    source = Path(__file__).resolve().parents[1]
    dataset = root / 'data/features/environment' / meta['dataset_build_id'] / 'kicker_game_features.parquet'
    expected_files = {folder/'model.joblib':meta['artifacts']['model.joblib'],
                      source/'features/contract.json':meta['contract_sha256'],
                      dataset:meta['dataset_sha256']}
    expected_files.update({source/'modeling'/n:h for n,h in meta['code_sha256'].items()})
    for path, expected in expected_files.items():
        if sha256_file(path) != expected:
            raise ValueError('Frozen hash mismatch: ' + path.name)
    if any(version(n) != v for n,v in meta['versions'].items()):
        raise ValueError('Frozen runtime versions changed')
    features = predictor_columns()
    if (meta['selected'] != CANDIDATES[1] or meta['features'] != features
            or len(features)!=82 or meta['refit_seasons']!=list(range(2016,2025))
            or meta['holdout_2025_evaluated'] or meta['holdout_2025_labels_loaded']):
        raise ValueError('Frozen Phase 5 specification mismatch')
    # Hash checked before trusted local joblib deserialization.
    model = joblib.load(folder / 'model.joblib')
    if (not isinstance(model,CountModel) or model.config!=meta['selected']
            or model.features_!=features or model.fit_seasons_!=meta['refit_seasons']
            or model.fit_row_count_!=meta['refit_rows'] or not model.fitted_):
        raise ValueError('Frozen fitted model specification mismatch')
    regressor = model.pipeline_['regressor']
    if not isinstance(regressor,PoissonRegressor) or regressor.alpha!=.1:
        raise ValueError('Expected Poisson GLM alpha=0.1')
    prep = model.pipeline_['preprocess']
    if list(prep['normalize'].feature_names_in_)!=features:
        raise ValueError('Frozen preprocessing input mismatch')
    columns = prep['columns']
    numeric = columns.named_transformers_['numeric']
    categorical = columns.named_transformers_['categorical']
    if (not isinstance(numeric['impute'],MedianWithAllIndicators)
            or numeric['impute'].imputer_.strategy!='median'
            or numeric['impute'].indicator_.features!='all'
            or not isinstance(numeric['scale'],StandardScaler)
            or not isinstance(categorical,OneHotEncoder) or categorical.handle_unknown!='ignore'
            or numeric['impute'].n_features_in_!=81):
        raise ValueError('Frozen preprocessing recipe mismatch')
    return model, meta, dataset


def _code_hashes():
    return {p.name:sha256_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))}


def _paths(root):
    return Path(root)/'data/validation/phase6', Path(root)/'reports'


def _read_features(dataset):
    projection = ','.join('"'+n+'"' for n in IDENTITY+predictor_columns())
    with duckdb.connect() as con:
        frame = con.execute(f'SELECT {projection} FROM read_parquet(?) '
            'WHERE eligible_for_phase_4_training IS TRUE AND season=2025 '
            'ORDER BY game_id, team, kicker_id',[str(dataset)]).fetchdf()
    if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any() or frame.empty:
        raise ValueError('Invalid/duplicate/empty holdout identities')
    return frame[IDENTITY].copy(), NormalizePredictors().transform(frame[predictor_columns()])


def _read_targets(dataset):
    """The sole holdout target projection, only called after durable reveal lock."""
    with duckdb.connect() as con:
        return con.execute('SELECT game_id,team,kicker_id,xpm FROM read_parquet(?) '
            'WHERE eligible_for_phase_4_training IS TRUE AND season=2025 '
            'ORDER BY game_id,team,kicker_id',[str(dataset)]).fetchdf()


def prepare(root=Path('.')):
    root = Path(root)
    work, reports = _paths(root)
    if (work/'reveal.lock').exists() or (work/'prepared.json').exists() or (reports/'phase6_metrics.json').exists():
        raise RuntimeError('Phase 6 already prepared or revealed; do not reset its one-time record')
    with no_fitting():
        model, meta, dataset = verify_frozen(root)
        reference, past_y = load_split(dataset,'refit')
        if len(reference)!=meta['refit_rows']:
            raise ValueError('Reference population mismatch')
        baseline = baseline_mean(past_y,reference['season'])
        identity, x = _read_features(dataset)
        means = model.predict(x)
        np.testing.assert_array_equal(means,model.predict(x))
        np.testing.assert_allclose(means[::-1],model.predict(x.iloc[::-1]),rtol=0,atol=1e-12)
        distribution = model.predict_distribution(x)
        probabilities, tail = distribution['probabilities'], distribution['tail']
        if not np.isfinite(probabilities).all() or not np.isfinite(tail).all() or (probabilities<0).any() or (tail<0).any():
            raise ValueError('Invalid probabilities')
        np.testing.assert_allclose(probabilities.sum(axis=1)+tail,1,rtol=0,atol=1e-12)
        work.mkdir(parents=True,exist_ok=True)
        reports.mkdir(parents=True,exist_ok=True)
        bundle = {'reference':reference,'x':x,'identity':identity,'means':means}
        joblib.dump(bundle,work/'prepared.joblib')
        preparation = {
            'prepared_at_utc':utc_now(), 'targets_2025_accessed':False,
            'model_sha256':meta['artifacts']['model.joblib'],
            'phase5_metadata_sha256':sha256_file(root/'data/models/phase5/metadata.json'),
            'dataset_sha256':meta['dataset_sha256'], 'contract_sha256':meta['contract_sha256'],
            'selected':meta['selected'],'features':predictor_columns(),'training_seasons':model.fit_seasons_,
            'training_rows':model.fit_row_count_, 'preprocessing_hash':joblib.hash(model.pipeline_['preprocess']),
            'preprocessing':{'numeric_median_fields':81,'missing_indicators':81,'numeric_standard_scaler':True,
                             'game_type_categories':model.pipeline_['preprocess']['columns'].named_transformers_['categorical'].categories_[0].tolist(),
                             'unknown_categories':'ignore; frozen from refit'},
            'baseline_mean':baseline, 'baseline_seasons':list(range(2016,2025)),
            'holdout_rows_feature_only':len(x), 'prepared_bundle_sha256':sha256_file(work/'prepared.joblib'),
            'evaluation_code_sha256':_code_hashes(),'policy':POLICY,
            'sanity':{'finite_positive_means':True,'finite_nonnegative_probabilities':True,'mass_including_tail_one':True,
                      'deterministic':True,'row_order_invariant':True,'exact_82_features':True,'no_2025_fitting':True},
        }
        write_json(work/'prepared.json',preparation)
        write_json(reports/'phase6_preregistration.json',preparation)
        (reports/'phase6_blind_validation.md').write_text(
            '# Fase 6: verificacion previa a apertura\n\n'
            f"Registrada: {preparation['prepared_at_utc']}. Targets 2025 NO abiertos.\n\n"
            f"Modelo congelado SHA-256: `{preparation['model_sha256']}`.\n\n"
            f'Poisson GLM alpha=0.1, 82 features, preprocessing congelado, refit 2016–2024 '
            f'({len(reference)} filas). Baseline pre-2025 lambda={baseline:.12f}.\n\n'
            'No se aprobaron campos current/forward, experimentales ni targets como inputs. '
            'La preregistracion JSON contiene la receta verificada y criterios del gate anteriores al reveal.\n',
            encoding='utf-8')
    return preparation


def _comparison(model_metrics, reference_metrics):
    return {k:{'reference':reference_metrics[k], 'value':model_metrics[k],
               'delta':model_metrics[k]-reference_metrics[k],
               'percent_change':100*(model_metrics[k]-reference_metrics[k])/reference_metrics[k] if reference_metrics[k] else None,
               'direction':'improvement' if model_metrics[k]<reference_metrics[k] else 'degradation' if model_metrics[k]>reference_metrics[k] else 'equal'} for k in METRICS}


def gate(model_metrics, baseline_metrics, bootstrap, comparison_2024, groups, drift_report, *, integrity=True):
    """Operational criteria fixed in POLICY before the single target reveal."""
    brier_improvements = sum(model_metrics[f'brier_ge_{k}']<baseline_metrics[f'brier_ge_{k}'] for k in (2,3,4))
    calibration = list(model_metrics['calibration'].values())
    eces = [c['ece'] for c in calibration]
    signal = model_metrics['nll']<baseline_metrics['nll'] and model_metrics['rps']<baseline_metrics['rps'] and brier_improvements>=2
    failures=[]
    if not integrity: failures.append('Integrity/leakage/probability failure')
    if max(eces)>POLICY['calibration_severe_fail_above']: failures.append('Threshold ECE exceeds preregistered severe 0.15 limit')
    if not signal: failures.append('No consistent out-of-sample point improvement over baseline')
    warnings=[]
    for metric in ('nll','rps'):
        if comparison_2024[metric]['percent_change']>100*POLICY['year_degradation_warning_relative']:
            warnings.append(metric+' deteriorated >10% vs 2024 (descriptive comparison)')
    warnings.extend('Subgroup: '+name for name,g in groups.items() if g['warning'])
    # Drift warnings are finalized using the diagnostics module's explicit top-field records.
    for name,d in drift_report['missingness'].items():
        if d['top_feature'] and d['delta'] is not None and abs(d['delta'])>POLICY['top_feature_missing_shift_warning']:
            warnings.append('Top feature missingness shift >10pp: '+name)
    if drift_report['game_type']['new_categories']:
        warnings.append('Unseen game_type category')
    robust=all(bootstrap['estimates']['delta_'+k]['upper']<0 for k in ('nll','rps'))
    if not robust: warnings.append('Paired bootstrap does not establish both improvements at 95%')
    if max(eces)>POLICY['calibration_reasonable_ece_max']: warnings.append('At least one ECE exceeds 0.05')
    if any(abs(c['bias'])>POLICY['global_bias_pass_max'] for c in calibration): warnings.append('Global threshold probability bias exceeds 0.05')
    if any(model_metrics[f'brier_ge_{k}']>baseline_metrics[f'brier_ge_{k}'] for k in (2,3,4)): warnings.append('A Brier score is worse than baseline')
    verdict='FAIL' if failures else 'PASS WITH CAUTION' if warnings else 'PASS'
    return {'verdict':verdict,'failures':failures,'warnings':warnings,'point_signal':bool(signal),
            'robust_paired_nll_rps_improvement':bool(robust),'criteria':POLICY}


def reveal(root=Path('.')):
    root=Path(root)
    work,reports=_paths(root)
    if (work/'reveal.lock').exists() or (reports/'phase6_metrics.json').exists():
        raise RuntimeError('Holdout already revealed; exactly one evaluation is allowed')
    pre=json.loads((work/'prepared.json').read_text(encoding='utf-8'))
    if pre!=json.loads((reports/'phase6_preregistration.json').read_text(encoding='utf-8')):
        raise ValueError('Preregistration changed')
    if (sha256_file(work/'prepared.joblib')!=pre['prepared_bundle_sha256']
            or _code_hashes()!=pre['evaluation_code_sha256'] or pre['policy']!=POLICY):
        raise ValueError('Preparation/code/policy hash mismatch')
    with no_fitting():
        model,meta,dataset=verify_frozen(root)
        if (sha256_file(root/'data/models/phase5/metadata.json')!=pre['phase5_metadata_sha256']
                or joblib.hash(model.pipeline_['preprocess'])!=pre['preprocessing_hash']):
            raise ValueError('Phase 5 metadata/preprocessing hash mismatch')
        bundle=joblib.load(work/'prepared.joblib')
        x,identity,means,reference=(bundle[k] for k in ('x','identity','means','reference'))
        with (work/'reveal.lock').open('x',encoding='utf-8') as stream:
            json.dump({'started_at_utc':utc_now(),'preparation_sha256':sha256_file(work/'prepared.json'),
                       'policy':POLICY['version'],'status':'consumed; never reset even after failure'},stream)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            outcomes=_read_targets(dataset)
            if not outcomes[KEYS].equals(identity[KEYS]):
                raise ValueError('Holdout target identity mismatch')
            y=outcomes['xpm'].to_numpy(dtype=float)
            joblib.dump({**bundle,'y':y},work/'revealed_audit.joblib')
            baseline=np.full(len(y),pre['baseline_mean'])
            glm_metrics=metrics(y,means,x['season'].to_numpy())
            baseline_metrics=metrics(y,baseline,x['season'].to_numpy())
            bootstrap=paired_bootstrap(y,means,baseline,seed=POLICY['seed'],resamples=POLICY['bootstrap_resamples'])
            groups=analyze_subgroups(x,reference,y,means,baseline)
            top=[item['feature'].removeprefix('numeric__') for item in meta['diagnostics']['top_features']]
            drift_report=drift(reference,x,top)
            comparison=_comparison(glm_metrics,meta['metrics_2024'][meta['selected']['name']])
            report={
                'phase':6,'evaluated_at_utc':utc_now(),'one_time_blind_statement':'2025 fue utilizado una única vez como blind holdout y no se utilizó para modificar el modelo.',
                'preregistration':pre,'target_summary_2025':target_summary(y),'past_target_summaries':meta['target_summary'],
                'glm':glm_metrics,'baseline':baseline_metrics,'vs_baseline':_comparison(glm_metrics,baseline_metrics),
                'vs_2024':comparison,'bootstrap':bootstrap,'distribution':distribution_summary(y,means),
                'props':prop_summary(y,means),'subgroups':groups,'drift':drift_report,'error_cases':error_cases(identity,x,y,means),
                'sanity':{**pre['sanity'],'phase5_artifact_unchanged':sha256_file(root/'data/models/phase5/model.joblib')==pre['model_sha256'],
                          'no_calibration_fit':True,'target_reads':1,'target_used_only_for_evaluation':True},
                'limitations':['IID row bootstrap may underestimate uncertainty from shared games/teams/kickers.',
                               '2024 uses model fit through 2023; 2025 uses the frozen refit through 2024; year comparison is descriptive.',
                               'No calibration intercept/slope fitted; reliability, Wilson intervals, ECE and Brier only.',
                               'Subgroups and extreme errors are descriptive, not tuning or causal inference.',
                               'No financial evaluation and no Phase 7.'],
            }
            report['gate']=gate(glm_metrics,baseline_metrics,bootstrap,comparison,groups,drift_report,integrity=report['sanity']['phase5_artifact_unchanged'])
            write_json(reports/'phase6_metrics.json',report)
            from .report import render_report
            (reports/'phase6_blind_validation.md').write_text(render_report(report),encoding='utf-8')
            write_json(work/'completed.json',{'completed_at_utc':utc_now(),'report_sha256':sha256_file(reports/'phase6_metrics.json'),
                                            'verdict':report['gate']['verdict']})
            return report
        except Exception as error:
            write_json(work/'failure.json',{'failed_at_utc':utc_now(),'error_type':type(error).__name__,
                                           'message':str(error),'blind_reveal_consumed':True,'do_not_rerun':True})
            raise
