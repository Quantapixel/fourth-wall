"""Simulated wasteland: loads a mission config and returns observations for each action.

Hidden state (EVE's position and status, clue and decoy locations) never leaves this
module except through observations produced by actions.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from .config import STATUSES, MissionConfig
from .world import DIRS, RUBBLE, Cell, Grid, bearing_deg, dist, generate_terrain, parse_grid

# EVE's beacon model per status. The agent is given the same table as its sensor model.
BEACON = {
    "active": {"power": 1.00, "detect_prob": 0.97},
    "dormant": {"power": 0.55, "detect_prob": 0.90},
    "damaged": {"power": 0.75, "detect_prob": 0.50},
}
FALLOFF = 8.0           # strength = power / (1 + (d / FALLOFF)^2)
MIN_DETECTABLE = 0.02
EVE_PULSE_JITTER = 4.0  # ms std of EVE's pulse interval around 1000 ms
DECOY_PULSE_JITTER = 40.0
SIGNATURE = "EVE-PROBE-07"


def expected_strength(power: float, d: float) -> float:
    return power / (1.0 + (d / FALLOFF) ** 2)


@dataclass
class Clue:
    type: str
    position: Cell
    data: dict[str, Any] = field(default_factory=dict)
    found: bool = False


@dataclass
class Decoy:
    position: Cell
    power: float
    found: bool = False


class Environment:
    def __init__(self, cfg: MissionConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        res, m = cfg.resources, cfg["map"]
        costs = res["costs"]

        start = tuple(cfg["start"]) if cfg["start"] else None
        eve_pos = tuple(cfg["eve"]["position"]) if cfg["eve"]["position"] else None
        if "grid" in m:
            rows, chargers, g_start, g_eve = parse_grid(m["grid"])
            start = start or g_start or (0, 0)
            eve_pos = eve_pos or g_eve
        else:
            start = start or (1, 1)
            rows = generate_terrain(
                int(m["width"]), int(m["height"]), float(m["obstacle_density"]),
                float(m["rubble_density"]), self.rng, start,
            )
            chargers = []
        self.grid = Grid(rows, chargers, costs["move"], costs["move_rubble"])
        if not self.grid.passable(start):
            raise ValueError(f"start {start} is not passable")
        self.start: Cell = start
        open_cells = list(self.grid.cells())

        # Base station charger at start, plus extra chargers spread around the map.
        chargers = set(self.grid.chargers) | {start}
        want = int(m.get("chargers", 2)) if "grid" not in m else len(chargers)
        spread = min(self.grid.width, self.grid.height) / 2
        for _ in range(2000):
            if len(chargers) >= min(want, len(open_cells)):
                break
            c = self.rng.choice(open_cells)
            # Prefer well-spread pads; occasionally accept any free cell so this always terminates.
            if c not in chargers and (min(dist(c, o) for o in chargers) >= spread or self.rng.random() < 0.02):
                chargers.add(c)
        self.grid.chargers = sorted(chargers)

        far = [c for c in open_cells if dist(c, start) >= 0.45 * math.hypot(self.grid.width, self.grid.height)]
        self.eve_pos: Cell = eve_pos or self.rng.choice(far or open_cells)
        if not self.grid.passable(self.eve_pos):
            raise ValueError(f"EVE position {self.eve_pos} is not passable")
        self.eve_status: str = cfg["eve"]["status"] or self.rng.choice(STATUSES)

        self.decoys = self._place_decoys(open_cells)
        self.clues = self._place_clues(open_cells)

        self.sensors = cfg.sensors
        self.costs, self.time_costs = costs, res["time_costs"]
        self.capacity = float(res["battery"])
        self.battery = float(res["battery"])
        self.time = 0
        self.time_limit = int(res["time_limit"])
        self.position: Cell = start
        self.done = False
        self.outcome: str | None = None
        self.eve_found = False

    # --- hidden-state generation ---------------------------------------
    def _place_decoys(self, open_cells: list[Cell]) -> list[Decoy]:
        spec = self.cfg["decoys"]
        if spec.get("list"):
            return [Decoy(tuple(d["position"]), float(d.get("power", 1.3))) for d in spec["list"]]
        out = []
        for _ in range(int(spec.get("count", 0))):
            cands = [c for c in open_cells if dist(c, self.eve_pos) > 6 and dist(c, self.start) > 4]
            out.append(Decoy(self.rng.choice(cands or open_cells), round(self.rng.uniform(1.1, 1.5), 2)))
        return out

    def _near(self, center: Cell, lo: float, hi: float, open_cells: list[Cell]) -> Cell:
        cands = [c for c in open_cells if lo <= dist(c, center) <= hi and c != self.eve_pos]
        return self.rng.choice(cands or open_cells)

    def _place_clues(self, open_cells: list[Cell]) -> list[Clue]:
        spec = self.cfg["clues"]
        if spec.get("list"):
            clues = [Clue(c["type"], tuple(c["position"])) for c in spec["list"]]
        else:
            n = int(spec.get("count", 6))
            # Always lay a trail of hover tracks; other clue types depend on EVE's status.
            types = ["hover_tracks", "memory_chip"]
            if self.eve_status == "damaged":
                types.append("debris")
            if self.eve_status in ("dormant", "active"):
                types.append("plant_residue")
            while len(types) < n:  # filler clues carry no status information
                types.append(self.rng.choice(("hover_tracks", "memory_chip", "debris")))
            clues = []
            for t in types[:n]:
                if t == "hover_tracks":
                    pos = self._near(self.eve_pos, 3, 11, open_cells)
                elif t == "debris" and self.eve_status == "damaged" and not any(c.type == "debris" for c in clues):
                    pos = self._near(self.eve_pos, 1, 4, open_cells)
                elif t == "plant_residue" and self.eve_status != "damaged":
                    pos = self._near(self.eve_pos, 1, 3, open_cells)
                else:
                    pos = self.rng.choice(open_cells)
                clues.append(Clue(t, pos))
        for clue in clues:
            clue.data = self._clue_reading(clue)
        return clues

    def _clue_reading(self, clue: Clue) -> dict[str, Any]:
        """What WALL-E learns when he finds the clue (with sensor noise baked in)."""
        if clue.type == "hover_tracks":
            heading = bearing_deg(clue.position, self.eve_pos) + self.rng.gauss(0, 8)
            return {"heading_deg": round(heading % 360, 1),
                    "note": "Scorched sand where EVE's thrusters hovered low."}
        if clue.type == "debris":
            fresh = self.eve_status == "damaged" and dist(clue.position, self.eve_pos) <= 4
            return {"freshness": "fresh" if fresh else "weathered",
                    "note": "White hull fragments, still warm." if fresh else "Old corroded scrap."}
        if clue.type == "plant_residue":
            return {"note": "Soil disturbed around a seedling's root ball."}
        if clue.type == "memory_chip":
            truth = self._quadrant(self.eve_pos)
            quads = ["NW", "NE", "SW", "SE"]
            q = truth if self.rng.random() < 0.85 else self.rng.choice([x for x in quads if x != truth])
            return {"quadrant": q, "note": "Axiom probe log fragment: last known sector."}
        raise ValueError(clue.type)

    def _quadrant(self, c: Cell) -> str:
        ns = "N" if c[1] < self.grid.height / 2 else "S"
        ew = "W" if c[0] < self.grid.width / 2 else "E"
        return ns + ew

    # --- public interface ----------------------------------------------
    def briefing(self) -> dict[str, Any]:
        """Initial observation: public map, resources, sensor spec and first signal reading."""
        sig = dict(self.cfg["initial_signal"])
        if sig.get("bearing_deg") is None or sig.get("strength") is None:
            # Derive a (noisy) first reading from the hidden state if the config omitted one.
            reading = self._signal_detections(self.start)
            eve_like = [d for d in reading if abs(d["pulse_interval_ms"] - 1000) < 10] or reading
            if eve_like:
                best = max(eve_like, key=lambda d: d["strength"])
                for key in ("bearing_deg", "strength", "pulse_interval_ms"):
                    if sig.get(key) is None:
                        sig[key] = best[key]
        return {
            "map": self.grid.render(),
            "width": self.grid.width,
            "height": self.grid.height,
            "start": self.start,
            "chargers": list(self.grid.chargers),
            "battery": self.battery,
            "capacity": self.capacity,
            "time_limit": self.time_limit,
            "recharge_rate": self.cfg.resources["recharge_rate"],
            "costs": dict(self.costs),
            "time_costs": dict(self.time_costs),
            "sensors": dict(self.sensors),
            "initial_signal": sig,
        }

    def _signal_detections(self, pos: Cell) -> list[dict[str, Any]]:
        s = self.sensors
        out = []
        sources = [("eve", self.eve_pos, BEACON[self.eve_status]["power"], BEACON[self.eve_status]["detect_prob"],
                    EVE_PULSE_JITTER)]
        sources += [("decoy", d.position, d.power, 0.99, DECOY_PULSE_JITTER) for d in self.decoys]
        for kind, src, power, pdet, jitter in sources:
            d = dist(pos, src)
            if d > s["signal_range"]:
                continue
            strength = expected_strength(power, d)
            if strength < MIN_DETECTABLE or self.rng.random() > pdet:
                continue
            noisy = max(0.0, strength + self.rng.gauss(0, s["strength_noise"]))
            bearing = (bearing_deg(pos, src) if d > 0 else self.rng.uniform(0, 360)) + self.rng.gauss(0, s["bearing_noise_deg"])
            out.append({
                "bearing_deg": round(bearing % 360, 1),
                "strength": round(noisy, 4),
                "pulse_interval_ms": round(1000 + self.rng.gauss(0, jitter), 1),
                "signature": SIGNATURE,  # decoys spoof EVE's signature; only timing betrays them
            })
        self.rng.shuffle(out)
        return out

    def _spend(self, kind: str) -> None:
        self.battery -= self.costs.get(kind, 0)
        self.time += self.time_costs.get(kind, 1)

    def step(self, action: dict[str, Any]) -> dict[str, Any]:
        if self.done:
            raise RuntimeError("mission already ended")
        kind = action.get("type")
        obs: dict[str, Any] = {"action": kind, "ok": True, "events": []}

        if kind == "move":
            d = action.get("dir")
            if d not in DIRS:
                raise ValueError(f"bad move direction {d!r}")
            nxt = (self.position[0] + DIRS[d][0], self.position[1] + DIRS[d][1])
            if not self.grid.passable(nxt):
                obs["ok"] = False
                obs["events"].append(f"blocked moving {d}")
                self._spend("wait")
            else:
                self._spend("move_rubble" if self.grid.terrain(nxt) == RUBBLE else "move")
                self.position = nxt
                # Driving over a clue reveals it even without a scan.
                for clue in self.clues:
                    if clue.position == nxt and not clue.found:
                        clue.found = True
                        obs.setdefault("clues", []).append(self._clue_obs(clue))
        elif kind == "scan_signal":
            self._spend("scan_signal")
            obs["detections"] = self._signal_detections(self.position)
        elif kind == "scan_area":
            self._spend("scan_area")
            r = self.sensors["scan_radius"]
            obs["radius"] = r
            obs["clues"] = []
            for clue in self.clues:
                if dist(clue.position, self.position) <= r and not clue.found:
                    clue.found = True
                    obs["clues"].append(self._clue_obs(clue))
            obs["decoys"] = []
            for decoy in self.decoys:
                if dist(decoy.position, self.position) <= r:
                    decoy.found = True
                    obs["decoys"].append({"position": decoy.position,
                                          "note": "Jury-rigged transmitter mimicking EVE's beacon."})
            if dist(self.eve_pos, self.position) <= r and self.rng.random() < self.sensors["scan_detect_prob"]:
                self.eve_found = True
                obs["eve"] = {"position": self.eve_pos, "status": self.eve_status,
                              "note": self._eve_note()}
        elif kind == "recharge":
            if self.position in self.grid.chargers:
                gained = min(self.capacity - self.battery, float(self.cfg.resources["recharge_rate"]))
                self.battery += gained
                obs["charged"] = gained
            else:
                obs["ok"] = False
                obs["events"].append("no charger here")
            self._spend("recharge")
        elif kind == "wait":
            self._spend("wait")
        elif kind == "end":
            self.done = True
            self.outcome = action.get("reason", "ended")
        else:
            raise ValueError(f"unknown action {kind!r}")

        if not self.done:
            if self.battery <= 0 and self.position not in self.grid.chargers:
                self.battery = max(self.battery, 0.0)
                self.done, self.outcome = True, "stranded"
                obs["events"].append("battery depleted: WALL-E is stranded")
            elif self.time >= self.time_limit:
                self.done, self.outcome = True, "timeout"
                obs["events"].append("mission time limit reached")

        obs.update(position=self.position, battery=round(self.battery, 2), time=self.time, done=self.done)
        if self.done:
            obs["outcome"] = self.outcome
        return obs

    def _clue_obs(self, clue: Clue) -> dict[str, Any]:
        return {"type": clue.type, "position": clue.position, **clue.data}

    def _eve_note(self) -> str:
        return {
            "active": "EVE is hovering, scanner sweeping. She sees you.",
            "dormant": "EVE is sealed in directive mode, green plant light blinking.",
            "damaged": "EVE is grounded, scorched, beacon flickering.",
        }[self.eve_status]

    def ground_truth(self) -> dict[str, Any]:
        """For evaluation only; never shown to the agent."""
        return {
            "eve_position": self.eve_pos,
            "eve_status": self.eve_status,
            "clues": [{"type": c.type, "position": c.position, "found": c.found} for c in self.clues],
            "decoys": [{"position": d.position, "power": d.power, "found": d.found} for d in self.decoys],
        }
