"""Feature contract and builder interface only; no features are computed yet."""
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
import json
from typing import Mapping, Protocol


def load_contract() -> dict:
    return json.loads(files(__package__).joinpath('contract.json').read_text(encoding='utf-8'))


@dataclass(frozen=True)
class FeatureContext:
    game_id: str
    team: str
    opponent: str
    kicker_id: str
    kickoff: datetime
    cutoff: datetime

    def __post_init__(self):
        if any(t.utcoffset() is None for t in (self.kickoff, self.cutoff)):
            raise ValueError('kickoff and cutoff require explicit timezones')
        if self.cutoff >= self.kickoff:
            raise ValueError('Feature cutoff must precede target-game kickoff')


class FeatureBuilder(Protocol):
    """Future implementations must enforce contract as-of and source provenance."""

    def build(self, context: FeatureContext) -> Mapping[str, object]:
        ...
