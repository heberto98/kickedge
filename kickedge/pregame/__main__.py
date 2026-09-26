import argparse
from pathlib import Path
import tomllib

from kickedge.config import load_config
from .build import build
from .ingest import ingest
from .official import ingest_official


def main():
    parser = argparse.ArgumentParser(description='KickEdge point-in-time kicker reconstruction')
    parser.add_argument('command', choices=['ingest', 'build', 'prepare-history', 'compare', 'compare-changes', 'audit', 'inspect'])
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    parser.add_argument('--policy', type=Path, default=Path('pregame.toml'))
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--source-lock', type=Path, help='Replay an immutable pregame source_lock.json')
    parser.add_argument('--game')
    parser.add_argument('--team')
    parser.add_argument('--policy-name', choices=['A', 'B', 'C'], default='C')
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == 'ingest':
        ingest(config, args.refresh)
        settings = tomllib.loads(args.policy.read_text(encoding='utf-8'))['sources']
        ingest_official(config, config.root / settings['claims'], config.root / settings['official_manifest'], args.refresh)
        ingest_official(config, config.root / 'audits/pregame_evaluation_sources.json', config.data_dir / 'pregame/manifests/evaluation_official.json', args.refresh)
    elif args.command == 'prepare-history':
        import json
        from .history import prepare_oracle
        pointer = json.loads((config.data_dir / 'processed/latest.json').read_text())
        base = config.root / pointer['path']
        prepare_oracle(base, config.data_dir / 'pregame/history_oracle' / base.name)
        print('Historical oracle prepared; no identity prediction performed')
    elif args.command == 'compare-changes':
        from .change_compare import run
        run(config)
    elif args.command == 'compare':
        from .compare import compare
        compare(config, args.policy, args.source_lock)
    elif args.command == 'audit':
        from .audit import audit
        audit(config)
    elif args.command == 'inspect':
        import json
        from .audit import inspect
        if not args.game or not args.team:
            parser.error('inspect requires --game and --team')
        print(json.dumps(inspect(config, args.game, args.team, args.policy_name), indent=2, ensure_ascii=False))
    else:
        build(config, args.policy, args.source_lock)


if __name__ == '__main__':
    main()
