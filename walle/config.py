"""Mission config loading and validation (JSON or YAML)."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATUSES = ("active", "dormant", "damaged")
CLUE_TYPES = ("hover_tracks", "debris", "plant_residue", "memory_chip")

DEFAULTS: dict[str, Any] = {
    "mission": {"name": "unnamed-mission", "seed": 0},
    "map": {
        "width": 24,
        "height": 16,
        "obstacle_density": 0.12,
        "rubble_density": 0.10,
        "chargers": 2,
    },
    "start": None,
    "eve": {"position": None, "status": None},
    "initial_signal": {
        "bearing_deg": None,
        "strength": None,
        "timestamp": "2805-07-04T06:00:00Z",
        "coordinates": None,
        "uncertainty": 6.0,
    },
    "resources": {
        "battery": 250,
        "time_limit": 400,
        "recharge_rate": 30,
        "costs": {
            "move": 1,
            "move_rubble": 3,
            "scan_signal": 2,
            "scan_area": 3,
            "recharge": 0,
            "wait": 0,
        },
        "time_costs": {
            "move": 1,
            "move_rubble": 2,
            "scan_signal": 1,
            "scan_area": 2,
            "recharge": 1,
            "wait": 1,
        },
    },
    "sensors": {
        "signal_range": 40.0,
        "bearing_noise_deg": 12.0,
        "strength_noise": 0.03,
        "scan_radius": 2,
        "scan_detect_prob": 0.95,
    },
    "clues": {"count": 6},
    "decoys": {"count": 0},
}


class ConfigError(ValueError):
    pass


@dataclass
class MissionConfig:
    raw: dict[str, Any]
    source: str = "<dict>"
    name: str = field(init=False)
    seed: int = field(init=False)

    def __post_init__(self) -> None:
        self.name = str(self.raw["mission"]["name"])
        self.seed = int(self.raw["mission"]["seed"])

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    @property
    def resources(self) -> dict[str, Any]:
        return self.raw["resources"]

    @property
    def sensors(self) -> dict[str, Any]:
        return self.raw["sensors"]


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _check_xy(value: Any, what: str) -> None:
    if value is None:
        return
    if not (isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, int) for v in value)):
        raise ConfigError(f"{what} must be [x, y] integers, got {value!r}")


def validate(raw: dict[str, Any]) -> None:
    m = raw["map"]
    if "grid" in m:
        grid = m["grid"]
        if not grid or len({len(row) for row in grid}) != 1:
            raise ConfigError("map.grid must be a non-empty list of equal-length strings")
        bad = set("".join(grid)) - set(".#~CSE")
        if bad:
            raise ConfigError(f"map.grid has unknown characters: {sorted(bad)}")
    else:
        for k in ("width", "height"):
            if int(m[k]) < 6:
                raise ConfigError(f"map.{k} must be >= 6")
        if not 0 <= float(m["obstacle_density"]) + float(m["rubble_density"]) < 0.6:
            raise ConfigError("obstacle_density + rubble_density must be in [0, 0.6)")
    _check_xy(raw["start"], "start")
    _check_xy(raw["eve"]["position"], "eve.position")
    status = raw["eve"]["status"]
    if status is not None and status not in STATUSES:
        raise ConfigError(f"eve.status must be one of {STATUSES}")
    _check_xy(raw["initial_signal"].get("coordinates"), "initial_signal.coordinates")
    res = raw["resources"]
    if res["battery"] <= 0 or res["time_limit"] <= 0:
        raise ConfigError("resources.battery and resources.time_limit must be positive")
    clues = raw["clues"]
    for clue in clues.get("list", []) or []:
        if clue.get("type") not in CLUE_TYPES:
            raise ConfigError(f"clue type must be one of {CLUE_TYPES}, got {clue.get('type')!r}")
        _check_xy(clue.get("position"), "clue.position")
    for decoy in raw["decoys"].get("list", []) or []:
        _check_xy(decoy.get("position"), "decoy.position")


def from_dict(data: dict[str, Any], source: str = "<dict>") -> MissionConfig:
    raw = _merge(DEFAULTS, data)
    validate(raw)
    return MissionConfig(raw=raw, source=source)


def load_config(path: str | Path) -> MissionConfig:
    path = Path(path)
    text = path.read_text()
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise ConfigError("PyYAML is required for YAML configs (pip install pyyaml)") from exc
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    return from_dict(data, source=str(path))
