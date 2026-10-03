"""Feature-only parity with the frozen 2024 materialization; no model evaluation."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import duckdb

from kickedge.current.sources import prepare_bundle
from kickedge.current.snapshot import resolve_target, resolve_kicker, build_snapshot
from kickedge.modeling.dataset import predictor_columns
from kickedge.io import records


def verify(root=Path('.')):
    root=Path(root).resolve()
    phase4=root/'data/features/environment/d0e256364dde3016c76f/kicker_game_features.parquet'
    if not phase4.exists():
        raise FileNotFoundError('Frozen Phase 4 local feature artifact required for parity')
    inputs=root/'data/features/kicker_inputs/125f3ca711124ac270c1'
    source=json.loads((inputs/'source.json').read_text())
    base=root/'data/processed'/source['inputs']['historical_build']
    lock=json.loads((base/'source_lock.json').read_text())
    now=datetime.now(timezone.utc)
    bundle=prepare_bundle(root,2024,lock['sources'],now=now)
    identities={(r['game_id'],r['team'],r['kicker_id']):r for r in
                json.loads((inputs/'identities.json').read_text()) if r['season']==2024}
    predicates={
        'first_home':'kicker_games_before=0 AND is_home',
        'first_away':'kicker_games_before=0 AND is_away',
        'short_history':'kicker_games_before=1',
        'rolling3':'kicker_games_before=3',
        'rolling5':'kicker_games_before=5',
        'bye':'team_long_rest_flag AND kicker_games_before>=5',
        'short_rest':'team_short_week_flag AND kicker_games_before>=5',
        'playoffs':"game_type='WC' AND kicker_games_before>=5",
    }
    columns=predictor_columns()
    projection=','.join('"'+name+'"' for name in ['game_id','team','kicker_id']+columns)
    cases=[]
    with duckdb.connect() as con:
        for category,predicate in predicates.items():
            rows=records(con,f'SELECT {projection} FROM read_parquet(?) WHERE season=2024 '
                         f'AND ({predicate}) ORDER BY game_id,team,kicker_id LIMIT 2',[str(phase4)])
            if not rows: raise AssertionError('Parity category missing: '+category)
            for row in rows:
                identity=identities[row['game_id'],row['team'],row['kicker_id']]
                target=resolve_target(bundle,identity['team'],identity['opponent'],season=2024,
                                      game_id=row['game_id'],now=now,replay=True)
                # The original historical run had actual kickoff available for identity;
                # scheduled kickoff remains the rest reference in both routes.
                target['kickoff']=identity['kickoff']
                player=resolve_kicker(bundle,row['kicker_id'],target,cutoff=identity['prediction_cutoff'])
                built=build_snapshot(bundle,target,player,now=now,cutoff=identity['prediction_cutoff'],replay=True)
                actual=built['snapshot']['features']
                differences=[]
                for name in columns:
                    a,b=actual[name],row[name]
                    equal=(a is None and b is None) or (a is not None and b is not None and
                          (math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10) if isinstance(a,(int,float)) else a==b))
                    if not equal: differences.append({'name':name,'current':a,'historical':b})
                if differences: raise AssertionError(json.dumps({'game':row['game_id'],'differences':differences}))
                cases.append({'category':category,'game_id':row['game_id'],'team':row['team'],
                              'kicker_id':row['kicker_id'],'features_compared':len(actual),
                              'nulls':sum(v is None for v in actual.values()),'matched':True})
    return {'season':2024,'cases':cases,'case_count':len(cases),'features_per_case':82,
            'numeric_tolerance':{'absolute':1e-10,'relative':1e-10},
            'target_outcomes_projected':False,'model_fitted_or_evaluated':False}


if __name__=='__main__':
    print(json.dumps(verify(),indent=2,allow_nan=False))
