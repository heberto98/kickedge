"""Frozen outcome-free groups and descriptive holdout diagnostics."""
import numpy as np
import pandas as pd
from scipy.stats import poisson


def _num(frame, field):
    return pd.to_numeric(frame.get(field, pd.Series(np.nan, index=frame.index)), errors='coerce').to_numpy(dtype=float, na_value=np.nan)


def _finite(value):
    return float(value) if np.isfinite(value) else None


def subgroups(X, reference, means):
    result = {}
    def split(family, v, labels):
        for label, mask in labels:
            result[f'{family}:{label}'] = np.isfinite(v) & mask
        result[f'{family}:unknown'] = ~np.isfinite(v)
    v = _num(X, 'is_home')
    split('home', v, [('home',v==1),('away',v==0)])
    v = _num(X, 'week')
    split('week', v, [('early',v<=8),('late',v>8)])
    v = _num(X, 'kicker_games_before')
    split('history', v, [('limited',v<5),('established',v>=5)])
    v = np.asarray(means,dtype=float)
    if len(v)!=len(X): raise ValueError('means and X must have equal length')
    split('lambda',v,[('below2',v<2),('2to3',(v>=2)&(v<3)),('3plus',v>=3)])
    s,l = _num(X,'team_short_week_flag'),_num(X,'team_long_rest_flag')
    known = np.isfinite(s)&np.isfinite(l)
    result.update({'rest:short':known&(s==1),'rest:long':known&(s!=1)&(l==1),
                   'rest:normal':known&(s==0)&(l==0),'rest:unknown':~known})
    for family,field in [('offense','offense_points_per_game_last_5'),('defense','defense_points_allowed_per_game_last_5')]:
        v,r = _num(X,field),_num(reference,field)
        median = np.median(r[np.isfinite(r)]) if np.isfinite(r).any() else np.nan
        if not np.isfinite(median): v=np.full(len(X),np.nan)
        labels = [('strong',v>=median),('weak',v<median)] if family=='offense' else [('strong',v<=median),('permissive',v>median)]
        split(family,v,labels)
    return result


def analyze_subgroups(X, reference, y, means, baseline_means):
    from .statistics import metrics
    y,means,baseline_means=map(np.asarray,(y,means,baseline_means))
    if not len(X)==len(y)==len(means)==len(baseline_means): raise ValueError('inputs must have equal length')
    result={}
    for name,mask in subgroups(X,reference,means).items():
        n=int(mask.sum())
        model=metrics(y[mask],means[mask],np.full(n,2025)) if n else None
        base=metrics(y[mask],baseline_means[mask],np.full(n,2025)) if n else None
        if n:
            model={k:v for k,v in model.items() if k!='calibration'}
            base={k:v for k,v in base.items() if k!='calibration'}
        delta={k:_finite(v-base[k]) for k,v in model.items() if isinstance(v,(int,float)) and isinstance(base.get(k),(int,float))} if n else None
        result[name]={'n':n,'model':model,'baseline':base,'delta':delta,'small_sample':n<50,
                      'warning':bool(n>=50 and model['nll']>base['nll']*1.2)}
    return result


def _summary(v):
    v=v[np.isfinite(v)]
    keys=('mean','median','std','p05','p25','p75','p95')
    if not len(v): return dict.fromkeys(keys)
    return dict(zip(keys,map(_finite,[v.mean(),np.median(v),v.std(),*np.percentile(v,[5,25,75,95])])))


def drift(reference, X, top_features):
    top=list(dict.fromkeys(str(f).removeprefix('numeric__') for f in top_features))
    result={'top_features':{},'missingness':{},'outside_reference_range':{}}
    for field in X.columns:
        r,v=_num(reference,field),_num(X,field)
        rm=float(reference[field].isna().mean()) if field in reference and len(reference) else None
        xm=float(X[field].isna().mean()) if len(X) else None
        d=xm-rm if xm is not None and rm is not None else None
        result['missingness'][field]={'reference':rm,'holdout':xm,'delta':d,'flag':bool(d is not None and abs(d)>.1),'top_feature':field in top}
        r=r[np.isfinite(r)]
        result['outside_reference_range'][field]=int(((v<r.min())|(v>r.max())).sum()) if len(r) else None
    for field in top:
        rs,xs=_summary(_num(reference,field)),_summary(_num(X,field))
        smd=(xs['mean']-rs['mean'])/rs['std'] if rs['std'] and xs['mean'] is not None else None
        result['top_features'][field]={'reference':rs,'holdout':xs,'smd':_finite(smd) if smd is not None else None,'smd_flag':bool(smd is not None and abs(smd)>.5)}
    cats=lambda f:sorted(set(f['game_type'].dropna().astype(str))) if 'game_type' in f else []
    r,v=cats(reference),cats(X)
    result['game_type']={'reference_categories':r,'holdout_categories':v,'new_categories':sorted(set(v)-set(r))}
    v=_num(X,'season')
    result['expected_calendar_drift']=bool(len(v) and np.isfinite(v).all() and (v==2025).all())
    return result


def error_cases(identity, X, y, means):
    y,means=np.asarray(y),np.asarray(means,dtype=float)
    if not len(identity)==len(X)==len(y)==len(means): raise ValueError('inputs must have equal length')
    if identity.duplicated(['game_id','team','opponent','kicker_id']).any(): raise ValueError('identity must have unique full kicker-game keys')
    p=poisson.sf(2,means); nll=-poisson.logpmf(y,means); selected={}
    def take(indices,reason):
        for i in indices[:3]: selected.setdefault(int(i),[]).append(reason)
    over=np.flatnonzero(means>y); under=np.flatnonzero(means<y)
    take(over[np.argsort(-(means-y)[over],kind='stable')],'largest_overprediction')
    take(under[np.argsort(-(y-means)[under],kind='stable')],'largest_underprediction')
    f=np.flatnonzero(y<3); s=np.flatnonzero(y>=3)
    take(f[np.argsort(-p[f],kind='stable')],'highest_failed_ge3')
    take(s[np.argsort(p[s],kind='stable')],'lowest_successful_ge3')
    for i in np.argsort(-nll,kind='stable'):
        if len(selected)>=min(16,len(y)): break
        if int(i) not in selected: selected[int(i)]=['highest_nll_fill']
    def clean(v):
        if pd.isna(v): return None
        if isinstance(v,np.generic): return v.item()
        return v
    context=['week','is_home','kicker_games_before','offense_points_per_game_last_5','defense_points_allowed_per_game_last_5','team_short_week_flag','team_long_rest_flag','team_days_rest']
    result=[]
    for i,reasons in selected.items():
        row={k:clean(v) for k,v in identity.iloc[i].to_dict().items()}
        row.update({k:clean(X.iloc[i][k]) if k in X else None for k in context})
        row.update(target=int(y[i]),**{'lambda':_finite(means[i])},observed_pmf=_finite(poisson.pmf(y[i],means[i])),probability_ge3=_finite(p[i]),nll=_finite(nll[i]),reasons=reasons)
        result.append(row)
    return result
