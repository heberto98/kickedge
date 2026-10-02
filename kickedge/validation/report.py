"""Pure Markdown rendering of the frozen blind-validation result."""

METRICS = ('nll', 'rps', 'brier_ge_2', 'brier_ge_3', 'brier_ge_4', 'mae', 'rmse', 'poisson_deviance')


def _text(value):
    return str(value).replace('|', '\\|').replace('\n', ' ') if value is not None else '—'


def _num(value):
    return f'{value:.6g}' if isinstance(value, (int, float)) else _text(value)


def _table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(_text(x) for x in row) + ' |' for row in rows])


def render_report(report):
    """Render only supplied report fields; never read outcomes or fit anything."""
    pre, gate = report['preregistration'], report['gate']
    sections = ['# Fase 6: validación blind de 2025',
                f"**Resultado: {gate['verdict']}**. Evaluación UTC: {_text(report['evaluated_at_utc'])}.",
                report['one_time_blind_statement'], '## Integridad y protocolo congelado',
                f"Preflight UTC: {_text(pre['prepared_at_utc'])}. Targets accedidos durante preflight: {_text(pre['targets_2025_accessed'])}.",
                f"Modelo SHA-256: `{pre['model_sha256']}`. Dataset: `{pre.get('dataset_sha256')}`. Contrato: `{pre.get('contract_sha256')}`.",
                f"Modelo: {_text(pre['selected'])}; {len(pre['features'])} features; temporadas {_text(pre['training_seasons'])}; {_text(pre['training_rows'])} filas. Preprocessing congelado: {_text(pre.get('preprocessing'))}; hash `{pre.get('preprocessing_hash')}`.",
                f"Baseline lambda={_num(pre['baseline_mean'])}, media aritmética de temporadas {_text(pre['baseline_seasons'])}, fijada antes de apertura. Filas 2025 features-only: {_text(pre['holdout_rows_feature_only'])}.",
                'Sanity: ' + '; '.join(f'{k}={_text(v)}' for k, v in report['sanity'].items()),
                'Política preregistrada: ' + '; '.join(f'{k}={_text(v)}' for k, v in pre['policy'].items()),
                '## Distribución del target y comparación histórica']
    summaries = {'2025': report['target_summary_2025'], **report['past_target_summaries']}
    sections.append(_table(['Población', 'n', 'Media', 'Varianza muestral', 'Var/media', 'Máximo', 'Histograma 0/1/2/3/4/5+'],
                           [[name, s.get('count'), _num(s.get('mean')), _num(s.get('sample_variance')), _num(s.get('variance_to_mean')), s.get('max'), s.get('histogram')] for name, s in summaries.items()]))
    sections += ['## Métricas GLM vs baseline y 2024',
                 'Menor es mejor. Delta = GLM menos referencia; porcentaje = 100 × delta / referencia. Comparación anual descriptiva: 2024 fit hasta 2023; 2025 refit congelado hasta 2024.',
                 _table(['Métrica', 'GLM 2025', 'Baseline 2025', 'Delta baseline', '% baseline', '2024', 'Delta 2024', '% 2024'],
                        [[k, _num(report['glm'][k]), _num(report['baseline'][k]), _num(report['vs_baseline'][k]['delta']), _num(report['vs_baseline'][k]['percent_change']),
                          _num(report['vs_2024'][k]['reference']), _num(report['vs_2024'][k]['delta']), _num(report['vs_2024'][k]['percent_change'])] for k in METRICS]),
                 '## Bootstrap pareado',
                 f"Método: {report['bootstrap']['method']}; seed={report['bootstrap']['seed']}; resamples={report['bootstrap']['resamples']}; confianza={_num(report['bootstrap']['confidence_level'])}. Los mismos índices de filas se usan para todas las métricas; deltas GLM menos baseline.",
                 _table(['Estimación', 'Punto', 'Inferior 95%', 'Superior 95%'], [[k, _num(v['point']), _num(v['lower']), _num(v['upper'])] for k,v in report['bootstrap']['estimates'].items()]),
                 report['bootstrap']['limitations'], '## Calibración descriptiva']
    for name, c in report['glm']['calibration'].items():
        sections += [f"### {name}", f"Predicho global={_num(c['predicted_mean'])}; observado global={_num(c['observed_frequency'])}; bias predicho−observado={_num(c['bias'])}; ECE={_num(c['ece'])}; categoría={c['category']}.",
                     _table(['Bin', 'n', 'Predicho medio', 'Frecuencia observada', 'Wilson inferior 95%', 'Wilson superior 95%'],
                            [[f"[{b['lower']:.1f}, {b['upper']:.1f}{']' if b['upper']==1 else ')'}", b['count'], _num(b['predicted_mean']), _num(b['observed_frequency']),
                              _num(b['observed_ci95'][0]) if b['observed_ci95'] else '—', _num(b['observed_ci95'][1]) if b['observed_ci95'] else '—'] for b in c['bins']])]
    sections.append('ECE ≤0.05: razonablemente calibrado; (0.05,0.10]: desviación ligera; >0.10: desviación importante. Bandas operacionales, no pruebas de significancia; sin ajuste de calibración.')
    d = report['distribution']
    sections += ['## Distribución completa predicha vs observada',
                 f"Media predicha={_num(d['predicted_mean'])}; observada={_num(d['observed_mean'])}; diferencia={_num(d['predicted_mean']-d['observed_mean'])}.",
                 _table(['XPM', 'Probabilidad predicha', 'Frecuencia observada', 'Conteo observado', 'Conteo esperado'], [[b['label'], _num(b['predicted_probability']), _num(b['observed_frequency']), b['observed_count'], _num(b['expected_count'])] for b in d['bins']])]
    for label in ('0','5+'):
        b = next(b for b in d['bins'] if b['label'] == label)
        sections.append(f"{'Ceros' if label=='0' else 'Cola alta exacta P(X≥5)'}: predicho={_num(b['predicted_probability'])}; observado={_num(b['observed_frequency'])}; diferencia={_num(b['predicted_probability']-b['observed_frequency'])}. Comparación aritmética descriptiva.")
    sections += ['## Props fijos Over/Under',
                 _table(['Prop', 'Probabilidad media', 'Frecuencia observada', 'Brier', 'ECE', 'Bias', 'Categoría'],
                        [[k, _num(v['predicted_mean']), _num(v['observed_frequency']), _num(v['brier']), _num(v['reliability']['ece']), _num(v['reliability']['bias']), v['reliability']['category']] for k,v in report['props'].items()]),
                 '## Subgrupos', 'Grupos con n<50: muestra pequeña, sin conclusión ni alerta. Grupos y comparaciones son descriptivos.',
                 _table(['Grupo', 'n', 'NLL GLM', 'NLL baseline', 'RPS GLM', 'RPS baseline', 'Advertencia'],
                        [[k, g['n'], _num(g['model']['nll']), _num(g['baseline']['nll']), _num(g['model']['rps']), _num(g['baseline']['rps']), 'n<50; sin conclusión' if g['small_sample'] else 'NLL > baseline +20%' if g['warning'] else 'ninguna'] for k,g in report['subgroups'].items() if g['n']])]
    drift = report['drift']
    sections += ['## Drift', f"Drift calendario esperado 2025: {_text(drift['expected_calendar_drift'])}. game_type referencia={_text(drift['game_type']['reference_categories'])}; holdout={_text(drift['game_type']['holdout_categories'])}; nuevas={_text(drift['game_type']['new_categories'])}.",
                 '|SMD|>0.5 se marca; SMD usa std de referencia. Sin inferencia causal.',
                 _table(['Top feature', 'Población', 'Media', 'Mediana', 'Std', 'p05', 'p25', 'p75', 'p95', 'SMD', 'Flag'],
                        [[name, population, *[_num(v[population].get(k)) for k in ('mean','median','std','p05','p25','p75','p95')], _num(v['smd']), v['smd_flag']] for name,v in drift['top_features'].items() for population in ('reference','holdout')]),
                 f"Missingness revisado en {len(drift['missingness'])} campos; rango en {len(drift['outside_reference_range'])} campos. Cambios absolutos >10 puntos porcentuales se marcan.",
                 _table(['Campo', 'Missing ref', 'Missing 2025', 'Delta', 'Flag >10pp', 'Top feature', 'Fuera de rango ref'],
                        [[k, _num(v['reference']), _num(v['holdout']), _num(v['delta']), v['flag'], v['top_feature'], drift['outside_reference_range'].get(k)] for k,v in drift['missingness'].items() if v['flag'] or drift['outside_reference_range'].get(k) not in (0,None)]),
                 'Campos sin excepción de missingness/rango: ' + ', '.join(k for k,v in drift['missingness'].items() if not v['flag'] and drift['outside_reference_range'].get(k) == 0),
                 'Campos sin rango de referencia disponible: ' + ', '.join(k for k,v in drift['outside_reference_range'].items() if v is None),
                 '## Casos extremos (diagnóstico, sin tuning)']
    for case in report['error_cases']:
        identity = '; '.join(f'{k}={_text(case.get(k))}' for k in ('game_id','team','opponent','kicker_id','kicker_name'))
        context = '; '.join(f'{k}={_num(v)}' for k,v in case.items() if k not in ('game_id','team','opponent','kicker_id','kicker_name','target','lambda','observed_pmf','probability_ge3','nll','reasons'))
        sections.append(f"- {identity}; lambda={_num(case['lambda'])}; real={case['target']}; PMF(real)={_num(case['observed_pmf'])}; P(X≥3)={_num(case['probability_ge3'])}; NLL={_num(case['nll'])}; motivos={_text(case['reasons'])}. Contexto: {context}.")
    sections += ['## Gate preregistrado', f"**{gate['verdict']}**; señal puntual={gate['point_signal']}; mejora pareada robusta NLL/RPS={gate['robust_paired_nll_rps_improvement']}.",
                 'FAIL: fallo de integridad/leakage/probabilidades, cualquier ECE>0.15, o falta de mejora puntual conjunta NLL/RPS y al menos dos Brier. PASS: señal puntual; superior95 de ambos deltas NLL/RPS<0; ningún Brier peor; todos ECE≤0.05; |bias global|≤0.05; sin advertencias. En otro caso con señal y sin FAIL: PASS WITH CAUTION.',
                 'Advertencias congeladas: >10% deterioro NLL/RPS vs 2024; subgrupo n≥50 con NLL >baseline por >20%; missingness top15 cambia >10pp; game_type nuevo. Las demás condiciones de PASS incumplidas se informan como cautelas.',
                 'Fallos: ' + ('; '.join(gate['failures']) or 'ninguno'), 'Advertencias: ' + ('; '.join(gate['warnings']) or 'ninguna'),
                 '## Limitaciones', *['- ' + x for x in report['limitations']]]
    return '\n\n'.join(sections) + '\n'
