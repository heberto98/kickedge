import numpy as np
import pytest

from kickedge.modeling.train import select_candidate, select_candidate_original, target_summary


def metric(nll, brier=.2, ece=.03, rps=.8):
    return {'nll': nll, 'rps': rps, **{f'brier_ge_{k}': brier for k in [2, 3, 4]},
            'calibration': {f'ge_{k}': {'ece': ece} for k in [2, 3, 4]}}


def results(glm=1.85, boost=1.8, boost_brier=.2, boost_ece=.03):
    return {'global_poisson': metric(2.), 'poisson_glm_alpha_0.1': metric(glm),
            'poisson_glm_alpha_1.0': metric(glm + .002),
            'poisson_boost_leaves_7': metric(boost, boost_brier, boost_ece),
            'poisson_boost_leaves_15': metric(boost + .002, boost_brier, boost_ece)}


def test_select_prefers_simplicity_over_trivial_gain():
    assert select_candidate(results(boost=1.84))['name'] == 'poisson_glm_alpha_0.1'
    assert select_candidate(results())['name'] == 'poisson_boost_leaves_7'
    assert select_candidate(results(glm=1.995, boost=1.99))['name'] == 'global_poisson'


def test_selection_keeps_ece_diagnostic_and_vetoes_brier_and_rps():
    assert select_candidate(results(boost_brier=.21))['family'] == 'glm'
    assert select_candidate(results(boost_ece=.06))['family'] == 'boost'
    assert select_candidate_original(results(boost_ece=.06))['family'] == 'glm'
    values = results()
    values['poisson_boost_leaves_7']['rps'] = .81
    assert select_candidate(values)['family'] == 'glm'


def test_target_histogram_preserves_zeros_and_tail():
    summary = target_summary(np.array([0, 1, 2, 3, 4, 5, 10]))
    assert summary['histogram'] == {'0': 1, '1': 1, '2': 1, '3': 1, '4': 1, '5+': 2}
    assert summary['max'] == 10
    assert sum(summary['histogram'].values()) == summary['count']


def test_selection_rejects_nonfinite_metric():
    values = results()
    values['global_poisson']['nll'] = float('nan')
    with pytest.raises(ValueError):
        select_candidate(values)
