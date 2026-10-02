"""Reproduce one explicitly historical demo snapshot, without projecting targets."""
import argparse
from datetime import timezone
from pathlib import Path

import duckdb

from kickedge.io import sha256_file, write_json
from kickedge.modeling.dataset import predictor_columns
from kickedge.inference.contracts import FeatureSnapshot


BUILD='d0e256364dde3016c76f'
SOURCE_SHA='bb1730a0f957aea3dd86f22f5448858bf182cdbb39d8bf09ac238013f20ebb3f'


def create_demo(source, output):
    source,output=Path(source),Path(output)
    if sha256_file(source)!=SOURCE_SHA:
        raise ValueError('Demo requires the frozen Phase 4 dataset')
    fields=['game_id','kicker_id','kicker_name','team','opponent','kickoff','prediction_cutoff']+predictor_columns()
    with duckdb.connect() as con:
        projection=','.join('"'+n+'"' for n in fields)
        values=con.execute(f'SELECT {projection} FROM read_parquet(?) '
            "WHERE eligible_for_phase_4_training IS TRUE AND season=2024 AND team='DAL' "
            'AND week>=8 AND kicker_has_5_prior_games IS TRUE '
            'ORDER BY week,game_id,kicker_id LIMIT 1',[str(source)]).fetchone()
    if values is None: raise ValueError('Expected historical demo observation unavailable')
    row=dict(zip(fields,values))
    # This frozen parquet stores UTC instants in timezone-naive TIMESTAMP columns.
    utc=lambda value:value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()
    payload={'features':{n:row[n] for n in predictor_columns()},
             'metadata':{'kicker':row['kicker_name'],'kicker_id':row['kicker_id'],
                         'team':row['team'],'opponent':row['opponent'],'game_id':row['game_id'],
                         'kickoff':utc(row['kickoff']),'cutoff':utc(row['prediction_cutoff'])},
             'provenance':{'source':'Frozen local Phase 4 feature-only projection',
                           'snapshot_id':'demo-'+row['game_id']+'-'+row['team']+'-'+row['kicker_id'],
                           'kind':'DEMO / TEST FIXTURE','demo':True,'build_id':BUILD,'source_sha256':SOURCE_SHA}}
    FeatureSnapshot.from_mapping(payload)
    write_json(output,payload)
    return payload


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('data/features/environment')/BUILD/'kicker_game_features.parquet')
    parser.add_argument('--output',type=Path,default=Path('examples/inference_demo_2024.json'))
    args=parser.parse_args()
    result=create_demo(args.source,args.output)
    print('DEMO / TEST FIXTURE: '+result['metadata']['game_id']+'; no target projected')
