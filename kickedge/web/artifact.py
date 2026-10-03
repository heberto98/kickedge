"""Install the pinned frozen model release into the runtime model directory.

The approved bytes are versioned in Git under ``models/phase5`` and pinned by
``kickedge/inference/release.json``. Nothing is fitted, repaired or fetched from
an unpinned location: a hash mismatch anywhere fails closed.
"""
import hashlib
import json
import os
from pathlib import Path
import threading

from importlib.resources import files

from kickedge.inference.loader import _canonical_hash, load_model

RUNTIME_DIR = Path('data/models/phase5')
RELEASE_DIR = Path('models/phase5')
_lock = threading.Lock()


def _verified_release(source):
    release = json.loads(files('kickedge.inference').joinpath('release.json').read_text(encoding='utf-8'))
    blob = (source/'model.joblib').read_bytes()
    meta = json.loads((source/'metadata.json').read_text(encoding='utf-8'))
    if (hashlib.sha256(blob).hexdigest() != release['artifact_sha256']
            or _canonical_hash(meta) != release['metadata_canonical_sha256']):
        raise ValueError('Pinned model release does not match the approved SHA-256')
    return blob, (source/'metadata.json').read_bytes()


def ensure_model(root=Path('.')):
    """Return the verified LoadedModel, installing the pinned release if absent.

    An existing runtime artifact is never replaced: if it fails verification the
    service stays not-ready instead of silently swapping bytes.
    """
    root = Path(root)
    target = root/RUNTIME_DIR
    with _lock:
        if not (target/'model.joblib').exists() and not (target/'metadata.json').exists():
            try:
                blob, meta = _verified_release(root/RELEASE_DIR)
            except (OSError, ValueError) as exc:
                raise ValueError('Pinned model release unavailable or invalid; inference unavailable') from exc
            target.mkdir(parents=True, exist_ok=True)
            for name, data in (('metadata.json', meta), ('model.joblib', blob)):
                temp = target/f'{name}.{os.getpid()}.tmp'
                temp.write_bytes(data)
                temp.replace(target/name)
        return load_model(target)

