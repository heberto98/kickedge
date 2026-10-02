"""Purely synthetic Markdown report integration coverage."""
import copy
import numpy as np
import pandas as pd
from kickedge.validation.report import render_report
from kickedge.validation.statistics import metrics, paired_bootstrap, distribution_summary, prop_summary
from kickedge.validation.diagnostics import analyze_subgroups, drift, error_cases


def synthetic_report():
    y, means, base = [0, 2, 5], [1., 2., 3.], [2., 2., 2.]
    x = pd.DataFrame({'season': [2025]*3, 'week': [1, 9, 10], 'is_home': [1, 0, 1],
                      'kicker_games_before': [2, 7, 8], 'game_type': ['REG']*3,
                      'offense_points_per_game_last_5': [10., 20., 30.],
                      'defense_points_allowed_per_game_last_5': [30., 20., 10.]})
    ref = x.assign(season=2024)
    identity = pd.DataFrame({'game_id': ['g1','g2','g3'], 'team': ['A','B','C'], 'opponent': ['D','E','F'], 'kicker_id': ['k1','k2','k3'], 'kicker_name': ['A|B','Two','Three']})
    glm, baseline = metrics(y,means,[2025]*3), metrics(y,base,[2025]*3)
    comparison = {k: {'reference': baseline[k], 'delta': glm[k]-baseline[k], 'percent_change': 0} for k in glm if k!='calibration'}
    summary = {'count':3,'mean':7/3,'sample_variance':6.3,'variance_to_mean':2.7,'max':5,'histogram':{'0':1,'2':1,'5+':1}}
    return {'evaluated_at_utc':'synthetic UTC', 'one_time_blind_statement':'one-time synthetic blind statement',
            'preregistration': {'prepared_at_utc':'synthetic preflight UTC','targets_2025_accessed':False,'model_sha256':'synthetic hash','selected':{'name':'glm'},
                'features':[f'f{i}' for i in range(82)],'training_seasons':list(range(2016,2025)),'training_rows':10,'baseline_mean':2.,'baseline_seasons':list(range(2016,2025)),
                'holdout_rows_feature_only':3,'policy':{'seed':42}},
            'sanity':{'target_reads':1}, 'target_summary_2025':summary,'past_target_summaries':{'refit':summary},
            'glm':glm,'baseline':baseline,'vs_baseline':comparison,'vs_2024':comparison,
            'bootstrap':paired_bootstrap(y,means,base,resamples=10),'distribution':distribution_summary(y,means),'props':prop_summary(y,means),
            'subgroups':analyze_subgroups(x,ref,y,means,base), 'drift':drift(ref,x,['week']), 'error_cases':error_cases(identity,x,y,means),
            'gate':{'verdict':'PASS WITH CAUTION','point_signal':True,'robust_paired_nll_rps_improvement':False,'failures':[],'warnings':['synthetic warning']},
            'limitations':['Synthetic limitation']}


def test_full_synthetic_report_is_pure_compact_and_complete():
    report = synthetic_report()
    before = copy.deepcopy(report)
    rendered = render_report(report)
    assert report == before
    assert rendered == render_report(report)
    assert len(rendered) < 22000
    for required in ('82 features','2016','2024','synthetic hash','synthetic preflight UTC','one-time synthetic blind statement',
                     'delta_nll','delta_rps','brier_ge_4','poisson_deviance','Wilson','5+','Cola alta','Ceros','under_3.5',
                     'n<50','SMD','Missingness','PMF(real)','synthetic warning','PASS WITH CAUTION','Synthetic limitation'):
        assert required in rendered
    assert 'A\\|B' in rendered
    assert 'nan' not in rendered.lower()


def test_renderer_retains_failure_and_empty_bin_indicators():
    report = synthetic_report()
    report['gate']['verdict'] = 'FAIL'
    report['gate']['failures'] = ['synthetic integrity failure']
    rendered = render_report(report)
    assert '**FAIL**' in rendered
    assert 'synthetic integrity failure' in rendered
    assert '—' in rendered
