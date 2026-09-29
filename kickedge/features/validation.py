"""Contract and frozen feature-row checks, without target-dependent filtering."""
import math

from .kicker import FEATURE_NAMES, instant
from .temporal import HISTORICAL_EVENT, POINT_IN_TIME, temporal_evidence_valid
from .context import CALENDAR_CLASS, calendar_field_approved


def validate_contract(contract):
    fields = {f['name']:f for f in contract['fields']}
    if len(fields) != len(contract['fields']):
        raise ValueError('Duplicate contract field')
    for f in fields.values():
        if f['role'] in ('target','audit','identity') and f['predictive_input_allowed']:
            raise ValueError('Forbidden predictive field: '+f['name'])
        if not all(f.get(k) for k in ('definition','planned_source','as_of_requirement','leakage_risk')):
            raise ValueError('Incomplete feature contract')
    for name in FEATURE_NAMES:
        f = fields.get(name, {})
        if not f.get('implemented') or not f.get('predictive_input_allowed') or f.get('role') != 'feature':
            raise ValueError('Unimplemented predictor: '+name)
        if (f.get('temporal_class') != HISTORICAL_EVENT or f.get('publication_timestamp_required') is not False
                or f.get('historical_training_approved') is not True):
            raise ValueError('Invalid Phase 1 temporal classification: '+name)
    for f in fields.values():
        calendar_ok=calendar_field_approved(f,contract)
        if f.get('temporal_class')==CALENDAR_CLASS and not calendar_ok:
            raise ValueError('Invalid calendar temporal classification: '+f['name'])
        if (f.get('group') in ('market', 'injuries_personnel', 'weather', 'game_context')
                or f.get('role') == 'context') and f.get('temporal_class') != POINT_IN_TIME and not calendar_ok:
            raise ValueError('Invalid context temporal classification: '+f['name'])
        if f.get('temporal_class') == POINT_IN_TIME and not f.get('publication_timestamp_required'):
            raise ValueError('Context temporal availability requirement cannot be waived')
    return fields


def validate_rows(rows, contract):
    fields = validate_contract(contract)
    for r in rows:
        if instant(r['prediction_cutoff']) >= instant(r['kickoff']):
            raise ValueError('Invalid cutoff')
        for name in FEATURE_NAMES:
            value = r[name]
            field = fields[name]
            if value is None:
                if not field['nullable']:
                    raise ValueError('Unexpected NULL: '+name)
                continue
            if field['dtype'] == 'boolean':
                valid = type(value) is bool
            elif field['dtype'] == 'integer':
                valid = type(value) is int and value >= 0
            else:
                valid = type(value) in (int,float) and math.isfinite(value) and value >= 0
            if not valid:
                raise ValueError('Invalid feature value: '+name)
            if 'conversion' in name and value > 1:
                raise ValueError('Invalid conversion rate')
        for h in r['feature_provenance']['history']:
            if (h['game_id'] == r['game_id'] or instant(h['kickoff']) >= instant(r['kickoff'])
                    or instant(h['available_at']) > instant(r['prediction_cutoff'])):
                raise ValueError('Feature history leakage')
            if h.get('temporal_class') and not temporal_evidence_valid(h, instant(r['prediction_cutoff'])):
                raise ValueError('Feature temporal evidence invalid')
