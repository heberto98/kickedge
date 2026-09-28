"""Separate completed event chronology from versioned point-in-time context."""
from datetime import datetime


HISTORICAL_EVENT = 'historical_event_data'
POINT_IN_TIME = 'point_in_time_context_data'
POLICY_VERSION = 'event-context-v1'


def temporal_evidence_valid(evidence, cutoff):
    """No publication requirement for events; never exempt context or unknown data.

    available_at is the existing pipeline's conservative release gate for event
    results, not a claim about when a retrospectively downloaded file appeared.
    """
    def timestamp(value):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError('Timezone required')
        return parsed
    try:
        if not (evidence.get('source_sha256') or evidence.get('sha256')):
            return False
        released = timestamp(evidence['available_at'])
        if released > cutoff:
            return False
        if evidence.get('temporal_class') == HISTORICAL_EVENT:
            start = timestamp(evidence.get('actual_kickoff') or evidence['kickoff'])
            end = timestamp(evidence['last_event'])
            return bool(evidence.get('event_completed') is True and start <= end < cutoff and released >= end)
        if evidence.get('temporal_class') == POINT_IN_TIME:
            return bool(evidence.get('availability_verified') is True and all(
                timestamp(evidence[name]) <= cutoff for name in ('published_at','modified_at') if evidence.get(name)))
        return False
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
