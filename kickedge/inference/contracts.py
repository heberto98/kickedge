"""Strict feature-only envelopes for the frozen offline predictor contract."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path

import pandas as pd

from kickedge.features import load_contract
from kickedge.modeling.dataset import predictor_columns

_REQUIRED = ('kicker', 'team', 'opponent')
_OPTIONAL = ('kicker_id', 'game_id', 'event_id', 'kickoff', 'cutoff')
_PROVENANCE = ('source', 'snapshot_id', 'demo', 'kind', 'build_id', 'source_sha256')


def _object(value, label, allowed):
    if not isinstance(value, Mapping):
        raise ValueError(f'{label} must be an object')
    if any(key not in allowed for key in value):
        raise ValueError(f'{label} contains unapproved fields')
    return dict(value)


def _string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a nonempty string')


def _timestamp(value, field):
    _string(value, field)
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{field} must be an ISO timestamp with timezone') from None
    if result.utcoffset() is None:
        raise ValueError(f'{field} must include a timezone')
    return result


@dataclass
class FeatureSnapshot:
    """Validated features, identities and provenance kept in separate namespaces."""

    features: dict
    metadata: dict
    provenance: dict
    nullable_features: list[str]
    warnings: list[str]

    @classmethod
    def from_mapping(cls, payload):
        envelope = _object(payload, 'snapshot', ('features', 'metadata', 'provenance'))
        if 'features' not in envelope or 'metadata' not in envelope:
            raise ValueError('snapshot requires features and metadata')
        columns = predictor_columns()
        features = _object(envelope['features'], 'features', columns)
        missing = [name for name in columns if name not in features]
        if missing:
            raise ValueError('Missing predictors: ' + ', '.join(missing))
        fields = {f['name']: f for f in load_contract()['fields']}
        nulls, warnings = [], []
        normalized = {}
        for name in columns:
            value, spec = features[name], fields[name]
            if value is None:
                if not spec['nullable']:
                    raise ValueError(f'{name} does not allow null')
                nulls.append(name)
            elif spec['dtype'] == 'string':
                _string(value, name)
                if name == 'game_type' and value not in ('REG', 'WC', 'DIV', 'CON', 'SB'):
                    warnings.append('game_type is an unfamiliar category; fitted encoder handling applies')
            elif spec['dtype'] == 'boolean':
                if type(value) not in (bool, int, float) or value not in (0, 1):
                    raise ValueError(f'{name} must be boolean or numeric 0/1')
                value = int(value)
            else:
                if type(value) not in (int, float):
                    raise ValueError(f'{name} must be a finite number')
                try:
                    finite = math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError(f'{name} must be a finite number')
                if spec['dtype'] == 'integer':
                    if value != int(value):
                        raise ValueError(f'{name} must be an integer')
                    value = int(value)
            normalized[name] = value
        metadata = _object(envelope['metadata'], 'metadata', (*_REQUIRED, *_OPTIONAL))
        for name in _REQUIRED:
            _string(metadata.get(name), name)
        if metadata['team'].strip().casefold() == metadata['opponent'].strip().casefold():
            raise ValueError('team and opponent must differ')
        dates = {}
        for name in _OPTIONAL:
            if name not in metadata:
                warnings.append(f'Optional metadata {name} is missing')
            elif name in ('kickoff', 'cutoff'):
                dates[name] = _timestamp(metadata[name], name)
            else:
                _string(metadata[name], name)
        if len(dates) == 2 and dates['cutoff'] >= dates['kickoff']:
            raise ValueError('cutoff must precede kickoff')
        provenance = _object(envelope.get('provenance', {}), 'provenance', _PROVENANCE)
        for name, value in provenance.items():
            if name == 'demo':
                if type(value) is not bool:
                    raise ValueError('demo must be boolean')
            else:
                _string(value, name)
        if provenance.get('demo') or provenance.get('kind') == 'DEMO / TEST FIXTURE':
            warnings.append('DEMO / TEST FIXTURE: demonstration input, not a current forecast')
        if nulls:
            warnings.append('Nullable predictors will use the frozen imputer: ' + ', '.join(nulls))
        warnings.append('Snapshot metadata does not certify pregame source availability')
        return cls(normalized, metadata, provenance, nulls, warnings)

    def to_frame(self):
        """Return exactly the approved ordered predictors, without identity columns."""
        return pd.DataFrame([self.features], columns=predictor_columns())


def read_snapshot(path: str | Path):
    """Read strict JSON, rejecting duplicate keys and non-JSON numeric constants."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Snapshot JSON contains duplicate object keys')
            result[key] = value
        return result

    def constant(_):
        raise ValueError('Snapshot JSON contains a nonfinite numeric constant')

    try:
        text = Path(path).read_text(encoding='utf-8')
        payload = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError('Snapshot must be a readable valid JSON file') from None
    return FeatureSnapshot.from_mapping(payload)
