"""WALL-E's autonomous search agent.

A classical, belief-driven planner:

* **Belief** – joint Bayesian grid over EVE's (position, status), see `belief.py`.
* **Modes** – SEARCH (belief diffuse), INVESTIGATE (belief concentrated), RECHARGE,
  RETURN (turn back to base), RENDEZVOUS (EVE located), DONE.
* **Targeting** – picks the cell that maximises expected discovery mass per unit of
  travel cost, subject to a hard energy constraint: after reaching the target and
  scanning, WALL-E must still be able to reach a charger with a safety margin.
* **Triangulation** – re-scans the beacon after moving a baseline distance, since
  bearings from different positions intersect at EVE (and disagree for decoys).
* **Final approach** – when the clock says "turn back", WALL-E weighs going home against
  a last run at the belief peak. If P(sighting) from one more area scan clears a threshold
  and the trip fits the remaining time and battery, he commits instead of retreating.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .belief import Belief
from .world import Cell, Grid, dist, parse_grid

SEARCH, INVESTIGATE, RECHARGE, RETURN, RENDEZVOUS, DONE, FINAL = (
    "SEARCH", "INVESTIGATE", "RECHARGE", "RETURN", "RENDEZVOUS", "DONE", "FINAL_APPROACH")


@dataclass
class AgentParams:
    safety_margin: float = 6.0          # battery kept in reserve on top of path-to-charger cost
    time_margin: int = 4
    baseline: float = 4.0               # cells moved before re-scanning the beacon
    investigate_baseline: float = 7.0
    investigate_mass: float = 0.35      # target mass that flips SEARCH -> INVESTIGATE
    travel_scale: float = 12.0          # score = mass / (1 + cost / travel_scale)
    explore_bonus: float = 0.01         # small pull towards unscanned ground (clues)
    switch_ratio: float = 1.35          # hysteresis for changing targets
    final_approach: bool = True         # gamble on the belief peak instead of retreating when time runs out
    commit_prob: float = 0.25           # minimum P(sighting) to commit to a final approach


class BeliefAgent:
    name = "belief"

    def __init__(self, briefing: dict[str, Any], params: AgentParams | None = None):
        self.p = params or AgentParams()
        rows, chargers, _, _ = parse_grid(briefing["map"])
        costs, tcosts = briefing["costs"], briefing["time_costs"]
        self.costs, self.tcosts = costs, tcosts
        self.grid = Grid(rows, chargers, costs["move"], costs["move_rubble"])
        self.tgrid = Grid(rows, chargers, tcosts["move"], tcosts["move_rubble"])
        self.start: Cell = tuple(briefing["start"])
        self.pos: Cell = self.start
        self.battery = float(briefing["battery"])
        self.capacity = float(briefing["capacity"])
        self.time = 0
        self.time_limit = int(briefing["time_limit"])
        self.radius = briefing["sensors"]["scan_radius"]
        self.belief = Belief(briefing)

        self.to_charger = self.grid.cost_to_targets(self.grid.chargers)
        self.time_to_base = self.tgrid.cost_to_targets([self.start])
        self.to_base = self.grid.cost_to_targets([self.start])
        self.scanned = np.zeros((self.grid.height, self.grid.width), dtype=bool)
        self.mode = SEARCH
        self.target: Cell | None = None
        self.last_signal_pos: Cell | None = None
        self.resume_mode = SEARCH
        self.evidence: list[dict[str, Any]] = []
        self.strategy_changes: list[dict[str, Any]] = []
        self.path_history: list[Cell] = [self.pos]
        self.end_reason: str | None = None
        self._pending_changes: list[dict[str, Any]] = []

        sig = briefing["initial_signal"]
        self.evidence.append({"time": 0, "kind": "initial_signal", "detail": sig})

    # --- bookkeeping -----------------------------------------------------
    def _change(self, kind: str, new: Any, why: str) -> None:
        entry = {"time": self.time, "position": list(self.pos), "kind": kind, "to": new, "why": why}
        self.strategy_changes.append(entry)
        self._pending_changes.append(entry)

    def _set_mode(self, mode: str, why: str) -> None:
        if mode != self.mode:
            old, self.mode = self.mode, mode
            self._change("mode", mode, f"{old} -> {mode}: {why}")

    def _mark_scanned(self, pos: Cell) -> None:
        ys, xs = np.mgrid[0 : self.grid.height, 0 : self.grid.width]
        self.scanned |= np.hypot(xs - pos[0], ys - pos[1]) <= self.radius

    def take_changes(self) -> list[dict[str, Any]]:
        out, self._pending_changes = self._pending_changes, []
        return out

    # --- perception ------------------------------------------------------
    def observe(self, action: dict[str, Any], obs: dict[str, Any]) -> list[str]:
        """Fold an observation into the belief. Returns human-readable notes for the trace."""
        notes = []
        self.pos = tuple(obs["position"])
        self.battery = float(obs["battery"])
        self.time = int(obs["time"])
        if self.path_history[-1] != self.pos:
            self.path_history.append(self.pos)

        if "detections" in obs:
            dets = obs["detections"]
            probs = self.belief.add_signal(self.pos, dets)
            self.last_signal_pos = self.pos
            for det, pe in zip(dets, probs):
                det["p_eve"] = round(pe, 3)
            if dets:
                notes.append("beacon: " + "; ".join(
                    f"bearing {d['bearing_deg']:.0f}°, strength {d['strength']:.3f}, pulse {d['pulse_interval_ms']:.0f}ms"
                    f" -> P(EVE)={d['p_eve']:.2f}" for d in dets))
            else:
                notes.append("beacon: nothing detected (negative evidence near me)")
            self.evidence.append({"time": self.time, "kind": "signal", "position": list(self.pos), "detail": dets})

        if action["type"] == "scan_area":
            self._mark_scanned(self.pos)
            for decoy in obs.get("decoys", []):
                n = self.belief.add_decoy(decoy["position"])
                if n:
                    notes.append(f"found decoy transmitter at {tuple(decoy['position'])}; re-weighted {n} past beacon readings")
                    self.evidence.append({"time": self.time, "kind": "decoy", "position": list(decoy["position"]),
                                          "detail": decoy["note"]})
                    self._change("belief_rebuild", list(decoy["position"]),
                                 "decoy discovered; past readings toward it are now explained away")
                    self.target = None
            if obs.get("eve"):
                eve = obs["eve"]
                self.belief.set_found(eve["position"], eve["status"])
                notes.append(f"EVE located at {tuple(eve['position'])}, status {eve['status']}: {eve['note']}")
                self.evidence.append({"time": self.time, "kind": "eve_sighting", "position": list(eve["position"]),
                                      "detail": eve})
            else:
                self.belief.add_scan(self.pos, self.radius)
        for clue in obs.get("clues", []):
            self.belief.add_clue(clue)
            notes.append(f"clue {clue['type']} at {tuple(clue['position'])}: "
                         + ", ".join(f"{k}={v}" for k, v in clue.items() if k not in ("type", "position")))
            self.evidence.append({"time": self.time, "kind": "clue", "position": list(clue["position"]),
                                  "detail": clue})
        for e in obs.get("events", []):
            notes.append(e)
        return notes

    # --- planning helpers --------------------------------------------------
    def _step_toward(self, goal: Cell) -> dict[str, Any] | None:
        path = self.grid.astar(self.pos, goal)
        if not path or len(path) < 2:
            return None
        return {"type": "move", "dir": self.grid.step_dir(path[0], path[1])}

    def _nearest_charger(self) -> Cell:
        costs = self.grid.dijkstra(self.pos)
        return min(self.grid.chargers, key=lambda c: costs.get(c, 1 << 30))

    def _max_action_cost(self) -> float:
        return max(self.costs["move_rubble"], self.costs["scan_area"], self.costs["scan_signal"])

    def _choose_target(self) -> tuple[Cell | None, float, dict[str, Any]]:
        b = self.belief
        mass = b.mass_within(self.radius)
        unscanned = (~self.scanned).astype(float)
        value = mass + self.p.explore_bonus * unscanned
        costs = self.grid.dijkstra(self.pos)
        best, best_score, info = None, -1.0, {}
        cur_score = None
        reserve = self.costs["scan_area"] + self.p.safety_margin
        for c, travel in costs.items():
            if travel + self.to_charger.get(c, 1 << 30) + reserve > self.battery:
                continue  # can't get there, scan, and still make it to a charger
            v = float(value[c[1], c[0]])
            if self.scanned[c[1], c[0]] and mass[c[1], c[0]] < 0.02:
                v *= 0.2
            score = v / (1.0 + travel / self.p.travel_scale)
            if c == self.target:
                cur_score = score
            if score > best_score:
                best, best_score = c, score
                info = {"mass": round(float(mass[c[1], c[0]]), 4), "travel_cost": travel, "score": round(score, 5)}
        if self.target is not None and cur_score is not None and best_score < self.p.switch_ratio * cur_score:
            t = self.target
            return t, cur_score, {"mass": round(float(mass[t[1], t[0]]), 4), "travel_cost": costs[t],
                                  "score": round(cur_score, 5), "kept": True}
        return best, best_score, info

    def _should_scan_signal(self) -> bool:
        if self.last_signal_pos is None:
            return True
        need = self.p.investigate_baseline if self.mode == INVESTIGATE else self.p.baseline
        return dist(self.pos, self.last_signal_pos) >= need

    # --- policy ------------------------------------------------------------
    def decide(self) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """Return (action, reasoning, decision details)."""
        b = self.belief
        battery_home = self.to_charger.get(self.pos, 0)
        time_left = self.time_limit - self.time
        decision: dict[str, Any] = {"battery_to_charger": battery_home, "time_left": time_left}

        # 1. EVE located: go to her.
        if b.eve_fix:
            eve = b.eve_fix["position"]
            if dist(self.pos, eve) <= 1:
                self._set_mode(DONE, "reached EVE")
                self.end_reason = "rendezvous"
                return {"type": "end", "reason": "rendezvous"}, "Next to EVE. Mission objective met.", decision
            path = self.grid.astar(self.pos, eve)
            # Reaching EVE is the goal itself, so only the trip there has to be affordable.
            if path and self.grid.path_cost(path) < self.battery:
                self._set_mode(RENDEZVOUS, f"EVE confirmed at {eve}")
                step = {"type": "move", "dir": self.grid.step_dir(path[0], path[1])}
                return step, f"Driving to EVE at {eve} ({self.grid.path_cost(path)} battery away).", decision

        # 2. Recharging: stay on the pad until (nearly) full or time runs short.
        if self.mode == RECHARGE:
            if self.pos in self.grid.chargers:
                full = self.battery >= self.capacity - 1
                time_needed = self.time_to_base.get(self.pos, 0) + self.p.time_margin
                if not full and time_left > time_needed + 2:
                    return {"type": "recharge"}, f"On charger, battery {self.battery:.0f}/{self.capacity:.0f}.", decision
                self._set_mode(self.resume_mode, "battery restored" if full else "time is short, leaving charger")
            else:
                goal = self._nearest_charger()
                step = self._step_toward(goal)
                if step:
                    return step, f"Heading to charger {goal} ({battery_home} battery needed, have {self.battery:.0f}).", decision

        # 3. Turn back when the clock says so -- unless a final approach on the belief peak is worth more.
        turn_back = time_left <= self.time_to_base.get(self.pos, 0) + self.p.time_margin
        dash = None
        if self.mode not in (RETURN, FINAL, RECHARGE) and self.p.final_approach:
            dash = self._final_approach()
            # Last call: the peak is only just reachable before the deadline, so go now or never.
            if dash and dash[2]["slack"] <= self.p.time_margin + 2:
                turn_back = True
        if self.mode not in (RETURN, FINAL) and turn_back:
            self.resume_mode = self.mode
            if dash:
                self.target, p_find, info = dash
                self._set_mode(FINAL, f"{time_left} time left, base is {self.time_to_base.get(self.pos)} away; "
                                      f"a run to {self.target} finds EVE with P={p_find:.0%} "
                                      f"(travel {info['time']} time / {info['battery']} battery), retreating finds her with P=0")
            else:
                self._set_mode(RETURN, f"{time_left} time left, base is {self.time_to_base.get(self.pos)} away")
        if self.mode == FINAL:
            step = self._final_step(decision)
            if step:
                return step[0], step[1], decision
            self._set_mode(RETURN, "final approach found nothing and no other peak is reachable in time")
        if self.mode == RETURN:
            if self.pos == self.start:
                self._set_mode(DONE, "back at base")
                self.end_reason = "returned_to_base"
                return {"type": "end", "reason": "returned_to_base"}, "Back at base with the report.", decision
            to_base = self.to_base.get(self.pos, 1 << 30)
            if self.battery >= to_base + 1:
                step = self._step_toward(self.start)
                if step:
                    return step, f"Out of time for searching; returning to base ({to_base} battery away).", decision
            elif self.pos in self.grid.chargers:
                # Can't make it home on this charge. Top up if the clock allows, otherwise shelter here.
                if time_left > self.time_to_base.get(self.pos, 0) + 1 and self.battery < self.capacity - 1:
                    return {"type": "recharge"}, f"Need {to_base} battery to reach base; recharging first.", decision
                self._set_mode(DONE, "cannot reach base in time; sheltering at charger")
                self.end_reason = "sheltering_at_charger"
                return ({"type": "end", "reason": "sheltering_at_charger"},
                        "Base is out of reach on this charge and clock; sheltering on the charger.", decision)
            else:
                goal = self._nearest_charger()
                step = self._step_toward(goal)
                if step:
                    return step, f"Base is {to_base} battery away, have {self.battery:.0f}; diverting to charger {goal}.", decision

        # 4. Energy guard: never take an action that could leave us unable to reach a charger.
        if self.battery - self._max_action_cost() < battery_home + self.p.safety_margin:
            self.resume_mode = self.mode if self.mode not in (RECHARGE, RETURN) else SEARCH
            self._set_mode(RECHARGE, f"battery {self.battery:.0f} vs {battery_home} needed to reach a charger + margin")
            if self.pos in self.grid.chargers:
                return {"type": "recharge"}, "Battery low; recharging here.", decision
            goal = self._nearest_charger()
            step = self._step_toward(goal)
            if step:
                return step, f"Battery low; heading to charger {goal}.", decision

        # 5. Beacon triangulation.
        if self._should_scan_signal():
            moved = dist(self.pos, self.last_signal_pos) if self.last_signal_pos else None
            why = "first beacon reading" if moved is None else f"moved {moved:.1f} cells since last reading; new bearing will triangulate"
            return {"type": "scan_signal"}, f"Scanning beacon: {why}.", decision

        # 6. Choose where to search.
        target, score, info = self._choose_target()
        decision["target"] = list(target) if target else None
        decision["target_info"] = info
        if target is None:
            if self.pos in self.grid.chargers and self.battery < self.capacity - 1:
                self.resume_mode = SEARCH
                self._set_mode(RECHARGE, "no reachable target within the energy budget")
                return {"type": "recharge"}, "No target is affordable; topping up.", decision
            self.resume_mode = SEARCH
            self._set_mode(RETURN, "no reachable target left")
            return {"type": "wait"}, "Nothing worth searching is reachable; turning back.", decision

        want = INVESTIGATE if info.get("mass", 0) >= self.p.investigate_mass else SEARCH
        self._set_mode(want, f"best target holds {info.get('mass', 0):.0%} of the belief within scan radius")
        if target != self.target:
            self._change("target", list(target), f"mass {info.get('mass')} at travel cost {info.get('travel_cost')}")
            self.target = target

        here_mass = float(b.mass_within(self.radius)[self.pos[1], self.pos[0]])
        if self.pos == target or (not self.scanned[self.pos[1], self.pos[0]] and here_mass >= max(0.05, 0.6 * info.get("mass", 1))):
            self.target = None if self.pos == target else self.target
            return ({"type": "scan_area"},
                    f"Scanning area: {here_mass:.0%} of belief within {self.radius} cells of me.", decision)
        step = self._step_toward(target)
        if step is None:
            return {"type": "scan_area"}, "Target unreachable; scanning here.", decision
        return step, f"Moving to {target} ({info.get('mass', 0):.0%} belief mass, cost {info.get('travel_cost')}).", decision

    def _final_approach(self) -> tuple[Cell, float, dict[str, Any]] | None:
        """Best last-chance target: (cell, P(sighting), costs), or None if nothing clears commit_prob.

        Only the trip out, one area scan and two closing moves have to fit: the mission ends at
        EVE, and a failed run still leaves WALL-E with battery (he just doesn't get home in time).
        """
        time_left = self.time_limit - self.time
        mass = self.belief.mass_within(self.radius)
        detect = self.belief.sensors["scan_detect_prob"]
        need_t = self.tcosts["scan_area"] + 2 * self.tcosts["move_rubble"]
        need_b = self.costs["scan_area"] + 2 * self.costs["move_rubble"] + 1
        bcost = self.grid.dijkstra(self.pos)
        cands = sorted(bcost, key=lambda c: -mass[c[1], c[0]] / (1.0 + bcost[c] / self.p.travel_scale))
        for c in cands[:40]:
            p_find = float(mass[c[1], c[0]]) * detect
            if p_find < self.p.commit_prob:
                break
            path = self.grid.astar(self.pos, c) if c != self.pos else [c]
            if not path:
                continue
            t, b = self.tgrid.path_cost(path), self.grid.path_cost(path)
            if t + need_t < time_left and b + need_b <= self.battery:
                return c, p_find, {"time": t, "battery": b, "slack": time_left - t - need_t}
        return None

    def _final_step(self, decision: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
        if self.target is None:
            dash = self._final_approach()
            if dash is None:
                return None
            self.target = dash[0]
            self._change("target", list(self.target), f"next final-approach peak, P(sighting)={dash[1]:.0%}")
        decision["target"] = list(self.target)
        if self.pos == self.target:
            self.target = None
            return {"type": "scan_area"}, "Final approach: scanning the belief peak."
        step = self._step_toward(self.target)
        return (step, f"Final approach to {self.target}: no time to get home, so this run is the best shot.") if step else None

    # --- final assessment ----------------------------------------------------
    def assessment(self) -> dict[str, Any]:
        b = self.belief
        summary = b.summary()
        status = summary["status"]
        best_status = max(status, key=status.get)
        found = b.eve_fix is not None
        cell = tuple(b.eve_fix["position"]) if found else tuple(summary["map_cell"])
        conf_loc = 1.0 if found else float(b.mass_within(2)[cell[1], cell[0]])
        return {
            "found": found,
            "location": list(cell),
            "location_confidence": round(conf_loc, 3),
            "status": best_status,
            "status_confidence": round(status[best_status], 3),
            "status_posterior": status,
            "cells_90": summary["cells_90"],
            "entropy_bits": summary["entropy_bits"],
        }
