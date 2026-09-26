import argparse
from pathlib import Path

from .config import load_config
from .ingest import ingest
from .build import build, inspect_label, validate_existing


def main():
    parser = argparse.ArgumentParser(description="KickEdge historical data pipeline (no ML).")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("ingest", help="Download or verify immutable nflverse originals")
    download.add_argument("--refresh", action="store_true", help="Fetch newer source versions; originals remain intact")
    process = sub.add_parser("build", help="Build and validate historical tables; no network")
    process.add_argument("--manifest", type=Path, help="Pin an immutable source manifest")
    sub.add_parser("validate", help="Rebuild from latest build's frozen inputs and compare output hashes")
    sub.add_parser("audit", help="Replay fixed expectations from manually reviewed real games")
    inspect = sub.add_parser("inspect", help="Trace one label and its PBP evidence")
    inspect.add_argument("--game", required=True)
    inspect.add_argument("--team", required=True)
    inspect.add_argument("--player", required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "ingest":
        ingest(config, args.refresh)
    elif args.command == "build":
        build(config, args.manifest)
    elif args.command == "validate":
        validate_existing(config)
    elif args.command == "inspect":
        inspect_label(config, args.game, args.team, args.player)
    elif args.command == "audit":
        from .audit import audit
        audit(config)


if __name__ == "__main__":
    main()
