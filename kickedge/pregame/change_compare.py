"""Focused cached replay: no ingestion, historical rebuild, or source discovery."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import duckdb

from kickedge.io import sha256_file, write_json
from .changes import VERSION, detect
from .evaluate import evaluate, summarize
from .history import OutcomeOracle
from .official import evidence as official_evidence
from .sequential import simulate


BASELINE = 'c721eeb55acb4eb9cb73'


def key(r):
    return r['game_id'], r['team']


def measure(before, after):
    """Outcome-only comparison, called after all predictions are frozen."""
    new = {key(r): r for r in after}
    if len(new) != len(before) or set(new) != {key(r) for r in before}:
        raise ValueError('Comparison populations differ')
    matched = {'exclusive_match', 'expected_among_multiple'}
    cohort = [r for r in before if r['actual_kicker_changed_since_prior_game'] is True
              and r['comparison'] in matched | {'mismatch'}]
    single = [r for r in cohort if len(r['actual_placekicker_ids']) == 1]
    errors = [r for r in cohort if r['comparison'] == 'mismatch']
    normal = [r for r in before if r['actual_kicker_changed_since_prior_game'] is False and r['comparison'] in matched]

    def fixed(rows):
        correct = sum(new[key(r)]['comparison'] in matched for r in rows)
        wrong = sum(new[key(r)]['comparison'] == 'mismatch' for r in rows)
        return {'total': len(rows), 'correct': correct, 'wrong': wrong,
                'abstained': len(rows) - correct - wrong,
                'correct_pct_fixed_denominator': 100 * correct / len(rows) if rows else None,
                'accuracy_among_identified_pct': 100 * correct / (correct + wrong) if correct + wrong else None}

    metrics = {'baseline_build': BASELINE, 'before': summarize(before)['total'], 'after': summarize(after)['total'],
        'fixed_change_cohort': fixed(cohort), 'fixed_single_change_cohort': fixed(single),
        'change_cases_flagged': sum(bool(new[key(r)].get('change_signal')) for r in cohort),
        'old_errors_corrected': sum(new[key(r)]['comparison'] in matched for r in errors),
        'old_errors_abstained': sum(new[key(r)]['expected_kicker_id'] is None for r in errors),
        'old_errors_remaining': sum(new[key(r)]['comparison'] == 'mismatch' for r in errors),
        'normal_correct_to_wrong': sum(new[key(r)]['comparison'] == 'mismatch' for r in normal),
        'normal_correct_to_abstention': sum(new[key(r)]['expected_kicker_id'] is None for r in normal)}
    metrics['net_additional_correct_identities'] = metrics['after']['membership_matches'] - metrics['before']['membership_matches']
    metrics['net_removed_errors'] = metrics['before']['comparisons'].get('mismatch', 0) - metrics['after']['comparisons'].get('mismatch', 0)
    transitions = [{'game_id': r['game_id'], 'team': r['team'], 'before_id': r['expected_kicker_id'],
        'after_id': new[key(r)]['expected_kicker_id'], 'before_comparison': r['comparison'],
        'after_comparison': new[key(r)]['comparison'], 'change_signal': new[key(r)].get('change_signal'),
        'actual_ids': r['actual_placekicker_ids']} for r in before
        if r['expected_kicker_id'] != new[key(r)]['expected_kicker_id']]
    return metrics, transitions


def run(config):
    root = config.root
    baseline = config.data_dir / 'pregame/sequential' / BASELINE
    freeze = json.loads((baseline / 'freeze.json').read_text())
    snapshot = config.data_dir / 'pregame/processed' / freeze['inputs']['baseline_build']
    meta = json.loads((snapshot / 'identity_build.json').read_text())
    base = config.data_dir / 'processed' / meta['inputs']['base_build']
    # Validate immutable inputs before reading them. Baseline labels are opened
    # only in the evaluation phase below.
    if sha256_file(snapshot / 'identities.json') != freeze['inputs']['baseline_identity_sha256']:
        raise ValueError('Snapshot identity hash mismatch')
    snapshot_build = json.loads((snapshot / 'build.json').read_text())
    expected = next(a['sha256'] for a in snapshot_build['artifacts'] if a['path'].endswith('/evidence.json'))
    if sha256_file(snapshot / 'evidence.json') != expected:
        raise ValueError('Snapshot evidence hash mismatch')
    baselines = json.loads((snapshot / 'identities.json').read_text())
    policy = json.loads((snapshot / 'effective_policy.json').read_text())['policy']
    by_key = {key(r): r for r in baselines}
    evidence = defaultdict(list)
    for e in json.loads((snapshot / 'evidence.json').read_text()):
        evidence[key(e)].append(e)
    claims_path = root / 'audits/pregame_change_claims.json'
    manifest_path = config.data_dir / 'pregame/manifests/evaluation_official.json'
    extra = official_evidence(config, json.loads(claims_path.read_text()), json.loads(manifest_path.read_text()))
    for e in extra:
        e['evidence_id'] = 'change:' + e['evidence_id']
        evidence[key(e)].append(e)

    def detector(game, candidate, last):
        previous = by_key.get((last['game_id'], game['team'])) if last else None
        return detect(game, candidate, evidence[key(game)], previous,
                      evidence[key(previous)] if previous else [], policy)

    oracle_dir = config.data_dir / 'pregame/history_oracle' / base.name
    if sha256_file(oracle_dir / 'manifest.json') != freeze['inputs']['oracle_manifest_sha256']:
        raise ValueError('Oracle manifest mismatch')
    oracle = OutcomeOracle(oracle_dir, json.loads((oracle_dir / 'manifest.json').read_text()))
    with duckdb.connect() as con:
        names = dict(con.execute('SELECT player_id,display_name FROM read_parquet(?)', [str(base / 'players.parquet')]).fetchall())
    inputs = {'version': VERSION, 'baseline': BASELINE, 'baseline_freeze_sha256': sha256_file(baseline / 'freeze.json'),
        'snapshot_evidence_sha256': expected, 'claims_sha256': sha256_file(claims_path),
        'official_manifest_sha256': sha256_file(manifest_path),
        'policy_sha256': sha256_file(snapshot / 'effective_policy.json'),
        'code_sha256': {p.name: sha256_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))}}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]
    directory = config.data_dir / 'pregame/changes' / digest
    directory.mkdir(parents=True, exist_ok=True)
    print('Replaying cached chronological identities with change detector', flush=True)
    with (directory / 'events.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
        def sink(event):
            stream.write(json.dumps(event, sort_keys=True) + '\n')
            stream.flush()
        predictions, chain = simulate(baselines, oracle, names, sink, change_detector=detector)
    identity = directory / 'identities_C_change.json'
    write_json(identity, predictions['C'])
    frozen_sha = sha256_file(identity)
    write_json(directory / 'freeze.json', {'inputs': inputs, 'identity_sha256': frozen_sha,
        'event_chain_final_sha256': chain, 'events_sha256': sha256_file(directory / 'events.jsonl')})
    print('All identities frozen; evaluating fixed baseline cohort', flush=True)
    after = evaluate(identity, frozen_sha, base)
    baseline_meta = json.loads((baseline / 'build.json').read_text())
    expected_labels = next(a['sha256'] for a in baseline_meta['artifacts'] if a['path'].endswith('/labels_C.json'))
    if sha256_file(baseline / 'labels_C.json') != expected_labels:
        raise ValueError('Baseline labels hash mismatch')
    before = json.loads((baseline / 'labels_C.json').read_text())
    metrics, transitions = measure(before, after)
    write_json(directory / 'labels_C_change.json', after)
    write_json(directory / 'metrics.json', metrics)
    write_json(directory / 'transitions.json', transitions)
    write_json(config.data_dir / 'pregame/changes/latest.json', {'build_id': digest, 'path': directory.relative_to(root).as_posix()})
    write_json(config.reports_dir / 'pregame_change_detection.json', {'build_id': digest, 'metrics': metrics, 'transitions': transitions})
    print(json.dumps(metrics, indent=2))
    return directory
