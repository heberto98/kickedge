"""Explicit two-step, one-time blind holdout workflow; no training command."""
import argparse
import json
from .blind import prepare, reveal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','reveal'])
    args=parser.parse_args()
    if args.command=='prepare':
        result=prepare()
        print(json.dumps({'prepared_at_utc':result['prepared_at_utc'],
                          'model_sha256':result['model_sha256'],'baseline_mean':result['baseline_mean'],
                          'holdout_rows_feature_only':result['holdout_rows_feature_only'],
                          'targets_2025_accessed':False},indent=2))
    else:
        result=reveal()
        print(json.dumps({'gate':result['gate'],'glm':{k:v for k,v in result['glm'].items() if k!='calibration'},
                          'target_summary_2025':result['target_summary_2025']},indent=2))


if __name__=='__main__':
    main()
