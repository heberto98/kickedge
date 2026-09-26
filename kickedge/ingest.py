"""Immutable, content-addressed copies of public nflverse release assets."""
import json
from pathlib import Path
import time
import urllib.request
import uuid

from .config import Config
from .io import parquet_info, sha256_file, utc_now, write_json

BASE = "https://github.com/nflverse/nflverse-data/releases/download"


def sources(config: Config) -> list[dict]:
    result = [
        {"dataset": "schedules", "season": None, "filename": "games.parquet", "tag": "schedules"},
        {"dataset": "players", "season": None, "filename": "players.parquet", "tag": "players"},
    ]
    for season in config.seasons:
        result.extend([
            {"dataset": "pbp", "season": season, "filename": f"play_by_play_{season}.parquet", "tag": "pbp"},
            {"dataset": "player_stats", "season": season, "filename": f"stats_player_week_{season}.parquet", "tag": "stats_player"},
        ])
    for source in result:
        source["url"] = f"{BASE}/{source['tag']}/{source['filename']}"
    return result


def verify_source(config: Config, record: dict) -> Path:
    path = (config.root / record["path"]).resolve()
    if not path.is_relative_to(config.data_dir.resolve()):
        raise ValueError(f"Source outside data directory: {path}")
    if sha256_file(path) != record["sha256"]:
        raise ValueError(f"Original changed or corrupt: {path}")
    return path


def download(config: Config, source: dict) -> dict:
    temporary = config.data_dir / "_staging" / f"{uuid.uuid4().hex}.part"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(config.retries):
        try:
            request = urllib.request.Request(source["url"], headers={"User-Agent": "KickEdge/0.1 historical research"})
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                headers = dict(response.headers.items())
                with temporary.open("wb") as target:
                    while chunk := response.read(1024 * 1024):
                        target.write(chunk)
            break
        except (OSError, TimeoutError):
            temporary.unlink(missing_ok=True)
            if attempt + 1 == config.retries:
                raise
            time.sleep(2 ** attempt)
    digest = sha256_file(temporary)
    info = parquet_info(temporary)  # reject HTML/error responses before publication
    directory = config.data_dir / "raw" / source["dataset"] / str(source["season"] or "all") / digest
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / source["filename"]
    metadata = directory / "source.json"
    if target.exists():
        if sha256_file(target) != digest:
            raise ValueError(f"Corrupt immutable original: {target}")
        temporary.unlink()
        return json.loads(metadata.read_text(encoding="utf-8"))
    record = {
        **source, "provider": "nflverse/nflverse-data", "downloaded_at": utc_now(),
        "sha256": digest, "size_bytes": temporary.stat().st_size,
        "path": target.relative_to(config.root).as_posix(),
        "http_headers": {k: v for k, v in headers.items() if k.lower() in {"etag", "last-modified", "content-type", "content-length"}},
        "availability_note": "Downloaded retrospectively; publication before historical kickoff is NOT asserted.",
        **info,
    }
    temporary.replace(target)
    write_json(metadata, record)
    return record


def ingest(config: Config, refresh: bool = False) -> Path:
    manifest_path = config.data_dir / "manifests" / "sources.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"sources": []}
    cache = {(r["dataset"], r["season"]): r for r in previous["sources"]}
    manifest = {"manifest_version": 1, "created_at": utc_now(), "sources": []}
    for source in sources(config):
        key = source["dataset"], source["season"]
        if key in cache and not refresh:
            verify_source(config, cache[key])
            record = cache[key]
            print(f"Verified cache: {source['filename']}", flush=True)
        else:
            print(f"Downloading: {source['filename']}", flush=True)
            record = download(config, source)
        manifest["sources"].append(record)
        # A resumable checkpoint; immutable snapshot below is the reproducibility lock.
        write_json(manifest_path, manifest)
    snapshot = manifest_path.with_name("sources-" + manifest["created_at"].replace(":", "").replace("+", "_") + ".json")
    write_json(snapshot, manifest)
    print(f"Source lock: {snapshot}", flush=True)
    return snapshot
