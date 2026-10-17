"""Baseline agents used for comparison in the benchmark.

* GreedySignalAgent – follows the strongest beacon reading, trusting it blindly (no
  decoy reasoning, no belief), with a fixed 35% battery recharge rule.
* RandomAgent – random walk with periodic area scans and the same recharge rule.
"""
from __future__ import annotations

import math
import random
from typing import Any

from .world import Cell, Grid, dist, parse_grid


class _Simple:
    name = "simple"
    recharge_at = 0.35

    def __init__(self, briefing: dict[str, Any]):
        rows, chargers, _, _ = parse_grid(briefing["map"])
        c = briefing["costs"]
        self.grid = Grid(rows, chargers, c["move"], c["move_rubble"])
        self.to_charger = self.grid.cost_to_targets(self.grid.chargers)
        self.pos: Cell = tuple(briefing["start"])
        self.battery = float(briefing["battery"])
        self.capacity = float(briefing["capacity"])
        self.time = 0
        self.mode = "SEARCH"
        self.path_history: list[Cell] = [self.pos]
        self.evidence: list[dict[str, Any]] = [{"time": 0, "kind": "initial_signal", "detail": briefing["initial_signal"]}]
        self.strategy_changes: list[dict[str, Any]] = []
        self.eve: dict[str, Any] | None = None
        self.guess: Cell = self.pos
        self.charging = False
        self.end_reason = None

    def _set_mode(self, m: str, why: str) -> None:
        if m != self.mode:
            self.strategy_changes.append({"time": self.time, "position": list(self.pos), "kind": "mode",
                                          "to": m, "why": why})
            self.mode = m

    def observe(self, action, obs) -> list[str]:
        self.pos, self.battery, self.time = tuple(obs["position"]), float(obs["battery"]), int(obs["time"])
        if self.path_history[-1] != self.pos:
            self.path_history.append(self.pos)
        if obs.get("eve"):
            self.eve = obs["eve"]
            self.evidence.append({"time": self.time, "kind": "eve_sighting", "position": list(self.eve["position"]),
                                  "detail": self.eve})
        for c in obs.get("clues", []):
            self.evidence.append({"time": self.time, "kind": "clue", "position": list(c["position"]), "detail": c})
        if "detections" in obs:
            self.evidence.append({"time": self.time, "kind": "signal", "position": list(self.pos),
                                  "detail": obs["detections"]})
            self._on_signal(obs["detections"])
        return list(obs.get("events", []))

    def _on_signal(self, dets) -> None:
        pass

    def _toward(self, goal: Cell):
        path = self.grid.astar(self.pos, goal)
        if path and len(path) > 1:
            return {"type": "move", "dir": self.grid.step_dir(path[0], path[1])}
        return None

    def _common(self):
        """Rendezvous and naive recharge rule shared by baselines."""
        if self.eve:
            e = tuple(self.eve["position"])
            if dist(self.pos, e) <= 1:
                self._set_mode("DONE", "reached EVE")
                return {"type": "end", "reason": "rendezvous"}, "Reached EVE."
            self._set_mode("RENDEZVOUS", "EVE seen")
            step = self._toward(e)
            if step:
                return step, "Driving to EVE."
        if self.charging:
            if self.pos in self.grid.chargers and self.battery < self.capacity - 1:
                return {"type": "recharge"}, "Recharging to full."
            if self.pos in self.grid.chargers:
                self.charging = False
                self._set_mode("SEARCH", "battery full")
        if self.battery < self.recharge_at * self.capacity and not self.charging:
            self.charging = True
            self._set_mode("RECHARGE", f"battery below {self.recharge_at:.0%}")
        if self.charging:
            costs = self.grid.dijkstra(self.pos)
            goal = min(self.grid.chargers, key=lambda c: costs.get(c, 1 << 30))
            if goal == self.pos:
                return {"type": "recharge"}, "Recharging."
            return self._toward(goal), "Heading to charger."
        return None

    def take_changes(self):
        return []

    def assessment(self) -> dict[str, Any]:
        found = self.eve is not None
        loc = tuple(self.eve["position"]) if found else self.guess
        return {"found": found, "location": list(loc), "location_confidence": 1.0 if found else 0.0,
                "status": self.eve["status"] if found else "active", "status_confidence": 1.0 if found else 0.0,
                "status_posterior": {}, "cells_90": 1 if found else -1, "entropy_bits": -1}


class GreedySignalAgent(_Simple):
    name = "greedy"

    def __init__(self, briefing):
        super().__init__(briefing)
        self.since_scan = 99
        self.target: Cell | None = None
        sig = briefing["initial_signal"]
        if sig.get("bearing_deg") is not None and sig.get("strength"):
            self._aim(sig["bearing_deg"], sig["strength"])

    def _aim(self, bearing: float, strength: float) -> None:
        d = 8.0 * math.sqrt(max(1.0 / max(strength, 1e-3) - 1.0, 0.0))  # invert falloff assuming full power
        rad = math.radians(bearing)
        x = round(self.pos[0] + d * math.sin(rad))
        y = round(self.pos[1] - d * math.cos(rad))
        x = min(max(x, 0), self.grid.width - 1)
        y = min(max(y, 0), self.grid.height - 1)
        self.target = min(self.grid.cells(), key=lambda c: dist(c, (x, y)))
        self.guess = self.target

    def _on_signal(self, dets) -> None:
        self.since_scan = 0
        if dets:
            best = max(dets, key=lambda d: d["strength"])
            self._aim(best["bearing_deg"], best["strength"])

    def decide(self):
        c = self._common()
        if c:
            return c[0], c[1], {}
        if self.since_scan >= 5:
            return {"type": "scan_signal"}, "Periodic beacon scan.", {}
        if self.target is None or self.pos == self.target:
            self.since_scan = 99
            self.target = None
            return {"type": "scan_area"}, "At target; scanning area.", {}
        step = self._toward(self.target)
        self.since_scan += 1
        if step is None:
            self.target = None
            return {"type": "scan_area"}, "Target unreachable.", {}
        return step, f"Following strongest bearing to {self.target}.", {"target": list(self.target)}


class RandomAgent(_Simple):
    name = "random"

    def __init__(self, briefing, seed: int = 0):
        super().__init__(briefing)
        self.rng = random.Random(seed)
        self.n = 0

    def decide(self):
        c = self._common()
        if c:
            return c[0], c[1], {}
        self.n += 1
        if self.n % 4 == 0:
            return {"type": "scan_area"}, "Periodic area scan.", {}
        opts = [d for d, _ in self.grid.neighbors(self.pos)]
        return {"type": "move", "dir": self.rng.choice(opts)}, "Random walk.", {}
