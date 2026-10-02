"""Reproducible Phase 5 comparison and frozen refit, never 2025 evaluation."""
from copy import deepcopy
from importlib.metadata import version
import json
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import poisson

from kickedge.io import sha256_file, utc_now, write_json
from .count_models import CANDIDATES, CountModel, SEED
from .dataset import holdout_info, load_split, predictor_columns
from .evaluate import evaluate


def target_summary(y):
    y = np.asarray(y, dtype=float)
    if len(y) < 2 or not np.isfinite(y).all() or (y < 0).any() or (y != np.floor(y)).any():
        raise ValueError('At least two valid integer targets required')
    mean, variance = float(y.mean()), float(y.var(ddof=1))
    return {'count': len(y), 'mean': mean, 'sample_variance': variance,
            'variance_to_mean': variance / mean if mean else None,
            'max': int(y.max()),
            'histogram': {**{str(k): int((y == k).sum()) for k in range(5)},
                          '5+': int((y >= 5).sum())}}


def _quality(metrics):
    return (metrics['nll'], np.mean([metrics[f'brier_ge_{k}'] for k in (2, 3, 4)]),
            np.mean([metrics['calibration'][f'ge_{k}']['ece'] for k in (2, 3, 4)]))


def select_candidate_original(results):
    """Predeclared practical improvement margins, not a significance test."""
    for config in CANDIDATES:
        if not np.isfinite(_quality(results[config['name']])).all():
            raise ValueError('Nonfinite selection metric')
    incumbent = CANDIDATES[0]
    for family in ('glm', 'boost'):
        candidate = min((c for c in CANDIDATES if c['family'] == family),
                        key=lambda c: results[c['name']]['nll'])
        a, b = _quality(results[incumbent['name']]), _quality(results[candidate['name']])
        if b[0] <= .99 * a[0] and b[1] <= a[1] + .002 and b[2] <= a[2] + .02:
            incumbent = candidate
    return deepcopy(incumbent)


ORIGINAL_SELECTION_RULE = 'Preferencia por simplicidad; cambio de familia exige mejora NLL >=1%, deterioro medio Brier <=0.002 y deterioro medio ECE <=0.02. Dentro de familia: menor NLL. Regla original previa a validacion.'
AMENDED_SELECTION_RULE = 'Preferencia por simplicidad; cambio de familia exige mejora NLL >=1%, deterioro medio Brier <=0.002 y RPS sin deterioro. Dentro de familia: menor NLL. ECE es diagnostico, no veto entre familias. Enmienda posterior a revision de validacion; no significancia estadistica.'


def select_candidate(results):
    """Post-validation review amendment; unchanged NLL/Brier margins and ledger."""
    for config in CANDIDATES:
        m = results[config['name']]
        if not np.isfinite((*_quality(m), m['rps'])).all():
            raise ValueError('Nonfinite selection metric')
    incumbent = CANDIDATES[0]
    for family in ('glm', 'boost'):
        candidate = min((c for c in CANDIDATES if c['family'] == family),
                        key=lambda c: results[c['name']]['nll'])
        a, b = results[incumbent['name']], results[candidate['name']]
        if (b['nll'] <= .99 * a['nll'] and _quality(b)[1] <= _quality(a)[1] + .002
                and b['rps'] <= a['rps']):
            incumbent = candidate
    return deepcopy(incumbent)


def _diagnostics(model, x, y):
    if model.config['family'] == 'baseline':
        return {'method': 'constant baseline; no feature influence', 'top_features': []}
    if model.config['family'] == 'glm':
        names = model.pipeline_['preprocess'].get_feature_names_out()
        coefficients = model.pipeline_['regressor'].coef_
        ordered = np.argsort(-np.abs(coefficients), kind='stable')[:15]
        return {'method': 'standardized numeric coefficients; unscaled category contrasts; log-mean scale, not causal',
                'top_features': [{'feature': str(names[i]), 'coefficient': float(coefficients[i])} for i in ordered]}
    rng = np.random.default_rng(SEED)
    baseline = -poisson.logpmf(y, model.predict(x)).mean()
    impacts = []
    for name in predictor_columns():
        values = []
        for _ in range(5):
            permuted = x.copy()
            permuted[name] = rng.permutation(permuted[name].to_numpy())
            values.append(float(-poisson.logpmf(y, model.predict(permuted)).mean() - baseline))
        impacts.append({'feature': name, 'nll_increase': float(np.mean(values)),
                        'repeat_std': float(np.std(values, ddof=1))})
    return {'method': '2024 permutation NLL increase; 5 repeats seed 42; correlated features can mask influence; not causal',
            'top_features': sorted(impacts, key=lambda v: -v['nll_increase'])[:15]}


def _markdown(report):
    lines = ['# Fase 5: primer modelo probabilistico XPM', '',
             '2025 permanece ciego: solo se consultaron schema y conteo, sin labels ni predicciones.', '',
             'Poblacion condicionada a participacion observada del kicker. El usuario del producto proporciona el kicker. '
             'No se predice su titularidad. Se preservan ceros y todas las filas previamente elegibles.', '',
             '## Target antes de fitting', '',
             '| Fold | n | Media | Varianza muestral | Var/media | Max | 0 / 1 / 2 / 3 / 4 / 5+ |',
             '|---|---:|---:|---:|---:|---:|---|']
    for split, summary in report['target_summary'].items():
        histogram = ' / '.join(str(summary['histogram'][k]) for k in ['0', '1', '2', '3', '4', '5+'])
        lines.append(f"| {split} | {summary['count']} | {summary['mean']:.6f} | {summary['sample_variance']:.6f} | {summary['variance_to_mean']:.6f} | {summary['max']} | {histogram} |")
    lines += ['', report['negative_binomial_decision'], '', '## Comparacion: solo 2024', '',
              '| Modelo | NLL | RPS | Brier >=2 | Brier >=3 | Brier >=4 | MAE | RMSE | Deviance |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name, m in report['metrics_2024'].items():
        vals = ' | '.join(f'{m[k]:.6f}' for k in ['nll', 'rps', 'brier_ge_2', 'brier_ge_3', 'brier_ge_4', 'mae', 'rmse', 'poisson_deviance'])
        lines.append(f'| {name} | {vals} |')
    lines += ['', f"Seleccion enmendada: **{report['selected']['name']}**. {report['selection_rule']}", '',
              f"Seleccion bajo regla original: **{report['original_selected']['name']}**. {report['original_selection_rule']}", '',
              'selection_policy_amendment: post-validation-review. Las cinco configuraciones permanecen intactas. '
              'El veto ECE original confundia calibracion empirica con resolucion entre familias: una prediccion constante '
              'puede tener ECE casi cero sin discriminar contextos; bins variables tambien reflejan error muestral. '
              'Esta seleccion explora 2024; no constituye evidencia independiente de superioridad.', '',
              'No hay calibracion ajustada. ECE bruto de bins fijos (10 bins de ancho 0.1):', '',
              '| Modelo | ECE >=2 | ECE >=3 | ECE >=4 |', '|---|---:|---:|---:|']
    for name, m in report['metrics_2024'].items():
        vals = ' | '.join(f"{m['calibration'][f'ge_{k}']['ece']:.6f}" for k in [2, 3, 4])
        lines.append(f'| {name} | {vals} |')
    lines += ['', '## Diagnostico de influencia', '', report['diagnostics']['method'], '',
              '| Variable | Coeficiente o incremento NLL |', '|---|---:|']
    for item in report['diagnostics']['top_features']:
        lines.append(f"| {item['feature']} | {item.get('coefficient', item.get('nll_increase')):.6f} |")
    lines += ['', '## Artefactos y limites', '',
              f"Refit final: {report['refit_rows']} filas 2016–2024; receta e hiperparametros congelados. "
              'Se reajustan medianas, escalas, categorias y parametros con ese conjunto. Nunca con 2025.', '',
              'Binarios locales ignorados: model.joblib (refit), selection_model.joblib (entrenado hasta 2023), metadata.json. '
              'Las metricas publicadas corresponden al segundo; no miden el rendimiento del refit.', '',
              'El JSON adjunto registra todas las configuraciones, bins con conteos, hashes, versiones y sanity checks. '
              'RPS usa la identidad exacta de Poisson con funciones de Bessel escaladas; la cola no se trunca.', '',
              'Limites: una sola temporada de validacion, predictores correlacionados, distribucion condicional Poisson, '
              'historia retrospectiva con la excepcion acotada de calendario ya aprobada. La dispersion marginal no prueba '
              'la adecuacion de toda la distribucion condicional. No hay inferencia causal, calibracion formal, '
              'validacion externa, evidencia de ROI ni comparacion con mercado. Fase 6 no ejecutada. '
              'La repeticion con seed fijo demuestra reproducibilidad determinista, no estabilidad temporal ni muestral. '
              'La incertidumbre del ranking de arquitecturas no fue cuantificada.', '']
    return '\n'.join(lines)


def run_training(dataset_path, output_dir, report_dir):
    dataset_path, output_dir, report_dir = map(Path, (dataset_path, output_dir, report_dir))
    features = predictor_columns()
    x_train, y_train = load_split(dataset_path, 'train')
    x_val, y_val = load_split(dataset_path, 'validation')
    blind = holdout_info(dataset_path)
    summaries = {'train_2016_2023': target_summary(y_train), 'validation_2024': target_summary(y_val)}
    print(json.dumps({'target_summary_before_fit': summaries}, indent=2), flush=True)
    ratio = summaries['train_2016_2023']['variance_to_mean']
    if ratio > 1.2:
        raise ValueError('TRAIN dispersion changed: review NB justification before fitting the frozen Poisson-only ledger')
    nb = ('No se incluye Negative Binomial: varianza/media TRAIN='
          f'{ratio:.6f}, sin sobredispersion marginal clara (>1.2 como umbral previo). '
          'NB agrega dispersion y no aborda subdispersion; no se justifica ampliar este primer conjunto.')
    models, metrics, sanity = {}, {}, {}
    for config in CANDIDATES:
        model = CountModel(config).fit(x_train, y_train)
        means = model.predict(x_val)
        np.testing.assert_allclose(model.predict(x_val.iloc[::-1]), means[::-1], rtol=0, atol=1e-12)
        distribution = model.predict_distribution(x_val)
        np.testing.assert_allclose(distribution['probabilities'].sum(axis=1) + distribution['tail'], 1, atol=1e-12)
        metrics[config['name']] = evaluate(y_val, means, x_val['season'].to_numpy())
        sanity[config['name']] = {'min_expected': float(means.min()), 'max_expected': float(means.max()),
                                  'finite_positive': True, 'mass_one': True, 'row_order_invariant': True}
        models[config['name']] = model
        print(json.dumps({'model': config['name'], 'nll_2024': metrics[config['name']]['nll']}), flush=True)
    original_selected = select_candidate_original(metrics)
    selected = select_candidate(metrics)
    chosen = models[selected['name']]
    repeated = CountModel(selected).fit(x_train, y_train)
    np.testing.assert_array_equal(repeated.predict(x_val), chosen.predict(x_val))
    diagnostics = _diagnostics(chosen, x_val, y_val)
    # Architecture and recipe are now frozen. Only now allow a 2016–2024 refit.
    x_refit, y_refit = load_split(dataset_path, 'refit')
    final_model = CountModel(selected).fit(x_refit, y_refit, refit=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(chosen, output_dir / 'selection_model.joblib')
    joblib.dump(final_model, output_dir / 'model.joblib')
    # Roundtrip is checked on past feature-only rows, never 2025.
    probe = x_train.iloc[:10]
    np.testing.assert_array_equal(joblib.load(output_dir / 'model.joblib').predict(probe), final_model.predict(probe))
    report = {
        'phase': 5, 'created_at_utc': utc_now(), 'seed': SEED,
        'dataset_build_id': dataset_path.parent.name, 'dataset_sha256': sha256_file(dataset_path),
        'contract_sha256': sha256_file(Path(__file__).parents[1] / 'features' / 'contract.json'),
        'code_sha256': {p.name: sha256_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'versions': {n: version(n) for n in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'joblib', 'duckdb', 'threadpoolctl']},
        'features': features, 'train_seasons': list(range(2016, 2024)), 'validation_season': 2024,
        'refit_seasons': list(range(2016, 2025)), 'holdout_2025_evaluated': False,
        'holdout_2025_labels_loaded': False, 'holdout_2025_rows_schema_only': blind['row_count'],
        'target_summary': summaries, 'negative_binomial_decision': nb,
        'configurations': CANDIDATES, 'metrics_2024': metrics, 'selected': selected,
        'selection_rule': AMENDED_SELECTION_RULE,
        'selection_method': 'post-validation-review amended simplicity rule on exploratory 2024 validation',
        'original_selected': original_selected, 'original_selection_rule': ORIGINAL_SELECTION_RULE,
        'selection_policy_amendment': {
            'stage': 'post-validation-review', 'configurations_unchanged': True,
            'reason': 'Original cross-family raw ECE veto conflated empirical calibration and resolution; variable bins also contain sampling error.',
            'changes': 'Remove ECE veto; retain NLL >=1% and average Brier <= incumbent +0.002; require RPS nondegradation.',
            'evidence_status': 'Exploratory selection on already inspected 2024, not independent performance evidence.',
        },
        'ranking_uncertainty_quantified': False,
        'stability_evidence': 'Same-seed deterministic repeatability only; temporal and sampling stability not quantified.',
        'selection_rows': len(y_train),
        'preprocessing': '81 numeric medians + 81 all-column missing indicators; all-NULL train columns fallback=0 plus indicator; game_type unknown-safe one-hot. StandardScaler for GLM only. Fit train only for comparison; refit frozen recipe 2016–2024.',
        'diagnostics': diagnostics, 'sanity_checks': sanity,
        'selected_same_seed_predictions_identical': True, 'artifact_roundtrip_identical': True,
        'refit_rows': len(y_refit),
        'artifacts': {name: sha256_file(output_dir / name) for name in ['model.joblib', 'selection_model.joblib']},
    }
    write_json(output_dir / 'metadata.json', report)
    write_json(report_dir / 'phase5_metrics.json', report)
    (report_dir / 'phase5_model_report.md').write_text(_markdown(report), encoding='utf-8')
    return report
