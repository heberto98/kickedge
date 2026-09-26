"""Offline extension of the historical pipeline; never downloads or trains."""
import argparse
from pathlib import Path

from kickedge.config import load_config


def main():
    parser=argparse.ArgumentParser(description='Phase 1 kicker-only experimental features')
    parser.add_argument('command',choices=['prepare','build'])
    parser.add_argument('--config',type=Path,default=Path('config.toml'))
    parser.add_argument('--base',type=Path,help='Frozen historical build for prepare')
    parser.add_argument('--inputs',type=Path,help='Prepared identity/outcome inputs for build')
    args=parser.parse_args()
    config=load_config(args.config)
    if args.command=='prepare':
        from .prepare import prepare
        output=prepare(config,args.base)
    else:
        from .materialize import build
        output=build(config,args.inputs)
    print(output.relative_to(config.root).as_posix())


if __name__=='__main__':
    main()
