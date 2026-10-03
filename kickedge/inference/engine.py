"""Frozen-model prediction first, then independent quote mathematics."""
from copy import deepcopy
from datetime import datetime
import json
import math

from kickedge.modeling.distributions import poisson_distribution
from .contracts import FeatureSnapshot
from .loader import load_model
from .odds import analyze_prop


def analyze(snapshot, line, side, odds, *, over_odds=None, under_odds=None,
            source=None, timestamp=None, model_dir='data/models/phase5', metadata_overrides=None,
            odds_format='american'):
    if isinstance(snapshot,FeatureSnapshot):
        # Dataclass dictionaries can be mutated by callers: validate at the boundary again.
        snapshot=FeatureSnapshot.from_mapping({'features':snapshot.features,'metadata':snapshot.metadata,
                                              'provenance':snapshot.provenance})
    else:
        snapshot=FeatureSnapshot.from_mapping(snapshot)
    for key,value in (metadata_overrides or {}).items():
        if key not in snapshot.metadata or value!=snapshot.metadata[key]:
            raise ValueError('CLI metadata must match the materialized snapshot identity')
    if source is not None and (not isinstance(source,str) or not source.strip()):
        raise ValueError('Prop source must be a nonempty string')
    if timestamp is not None:
        try:
            if not isinstance(timestamp,str) or datetime.fromisoformat(timestamp).utcoffset() is None:
                raise ValueError()
        except (TypeError,ValueError):
            raise ValueError('Prop timestamp must be ISO format with timezone') from None
    # Validate quote independently before loading the artifact, without modifying features.
    analyze_prop(1.,line,side,odds,over_odds,under_odds,odds_format=odds_format)
    frozen=load_model(model_dir)
    frame=snapshot.to_frame()
    mean=float(frozen.predict(frame)[0])
    distribution=poisson_distribution([mean],max_display=12)
    probabilities=distribution['probabilities'][0].tolist()
    tail=float(distribution['tail'][0])
    if not all(math.isfinite(p) and p>=0 for p in [*probabilities,tail]) or not math.isclose(sum(probabilities)+tail,1,abs_tol=1e-12):
        raise ValueError('Model produced an invalid count distribution')
    quote=analyze_prop(mean,line,side,odds,over_odds,under_odds,source,timestamp,odds_format=odds_format)
    outcomes=[quote['prop'][k] for k in ('p_over','p_under','p_push')]
    if not all(math.isfinite(p) and p>=0 for p in outcomes) or not math.isclose(sum(outcomes),1,abs_tol=1e-12):
        raise ValueError('Invalid prop settlement probabilities')
    warnings=list(snapshot.warnings)
    if frame['game_type'].iloc[0] not in frozen.categories:
        warnings.append('game_type category absent from frozen fit; encoded with existing unknown-category handling')
    if timestamp is None: warnings.append('Prop timestamp unavailable; price freshness is unverified')
    if source is None: warnings.append('Prop bookmaker/source unavailable')
    if not snapshot.provenance.get('source'): warnings.append('Feature snapshot source unavailable')
    if over_odds is None: warnings.append('Only one price supplied; no-vig probability unavailable')
    if quote['market']['overround'] is not None and quote['market']['overround']<0:
        warnings.append('Negative overround in supplied pair; verify same event/line/book/time and quote completeness')
    if over_odds is not None:
        warnings.append('Paired prices are caller-supplied; common event/line/book/time is not independently verified')
    if quote['analysis']['fair_odds']['reason'] is not None:
        warnings.append(quote['analysis']['fair_odds']['reason'])
    warnings.append('EV and edge are mathematical outputs under model probabilities, not a betting recommendation')
    demo=bool(snapshot.provenance.get('demo') or snapshot.provenance.get('kind')=='DEMO / TEST FIXTURE')
    optional=['kicker_id','game_id','event_id','kickoff','cutoff']
    missing_metadata=[k for k in optional if k not in snapshot.metadata]
    result={'schema_version':'7a.1','model':deepcopy(frozen.info),'game':dict(snapshot.metadata),
            'prediction':{'expected_xpm':mean,'distribution':{'max_display':12,'support':list(range(13)),
                          'probabilities':probabilities,'tail_event':'XPM > 12','tail_probability':tail}},
            **quote,
            'data_quality':{'model_verified':True,'feature_count':82,'missing_features':[],
                            'nullable_features_used':snapshot.nullable_features,
                            'metadata_complete':not missing_metadata,'missing_optional_metadata':missing_metadata,
                            'prop_timestamp_available':timestamp is not None,'source':snapshot.provenance.get('source'),
                            'provenance':snapshot.provenance,'demo':demo,'pregame_availability_verified':False,
                            'warnings':warnings}}
    json.dumps(result,allow_nan=False)
    return result
