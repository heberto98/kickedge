from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Config:
    root: Path
    start_season: int
    end_season: int
    target_start_season: int
    game_types: tuple[str, ...]
    population: str
    data_dir: Path
    reports_dir: Path
    timeout_seconds: int = 180
    retries: int = 3

    @property
    def seasons(self):
        return range(self.start_season, self.end_season + 1)


def load_config(path: Path) -> Config:
    path = path.resolve()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    d, p = raw["dataset"], raw["paths"]
    if not 2015 <= d["start_season"] <= d["end_season"]:
        raise ValueError("This stage supports the modern PAT era (2015+).")
    if not d['start_season'] <= d['target_start_season'] <= d['end_season']:
        raise ValueError('Target start season must be inside the configured period.')
    if not d['game_types'] or not set(d['game_types']) <= {'REG','WC','DIV','CON','SB'}:
        raise ValueError('Only regular season and postseason game types are supported.')
    if raw.get('download',{}).get('retries',3)<1:
        raise ValueError('At least one download attempt is required.')
    return Config(
        root=path.parent,
        start_season=d["start_season"], end_season=d["end_season"],
        target_start_season=d["target_start_season"],
        game_types=tuple(d["game_types"]), population=d["population"],
        data_dir=path.parent / p["data_dir"],
        reports_dir=path.parent / p["reports_dir"],
        **raw.get("download", {}),
    )
