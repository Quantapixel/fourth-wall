"""Runs one mission: environment <-> agent loop with full trace logging."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .agent import BeliefAgent
from .config import MissionConfig
from .env import Environment
from .viz import sparse_heat


def _jsonable(o: Any) -> Any:
    if isinstance(o, tuple):
        return list(o)
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    return o


class Trace:
    """Step-by-step record of actions, observations, decisions and reasoning."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def log(self, record: dict[str, Any]) -> None:
        self.records.append(_jsonable(record))

    def write_jsonl(self, path: Path) -> None:
        with open(path, "w") as f:
            for r in self.records:
                f.write(json.dumps(r) + "\n")


def run_mission(cfg: MissionConfig, agent_factory: Callable[[dict], Any] = BeliefAgent,
                max_steps: int = 5000) -> dict[str, Any]:
    env = Environment(cfg)
    briefing = env.briefing()
    agent = agent_factory(briefing)
    trace = Trace()
    has_belief = hasattr(agent, "belief")
    trace.log({"step": 0, "event": "briefing", "briefing": briefing,
               "belief": agent.belief.summary() if has_belief else None})
    heat = [sparse_heat(agent.belief.location()) if has_belief else None]
    heat_before_fix = heat[0]

    step = 0
    while not env.done and step < max_steps:
        step += 1
        before = {"position": env.position, "battery": round(env.battery, 2), "time": env.time}
        action, reasoning, decision = agent.decide()
        mode = getattr(agent, "mode", None)
        obs = env.step(action)
        notes = agent.observe(action, obs)
        changes = agent.take_changes() if hasattr(agent, "take_changes") else []
        trace.log({
            "step": step,
            "state": before,
            "mode": mode,
            "action": action,
            "reasoning": reasoning,
            "decision": decision,
            "observation": obs,
            "notes": notes,
            "strategy_changes": changes,
            "belief": agent.belief.summary() if has_belief else None,
        })
        heat.append(sparse_heat(agent.belief.location()) if has_belief else None)
        if has_belief and not agent.belief.eve_fix:
            heat_before_fix = heat[-1]
    if not env.done:  # safety net, should not happen
        env.step({"type": "end", "reason": "step_limit"})

    return {"cfg": cfg, "env": env, "agent": agent, "trace": trace, "briefing": briefing,
            "outcome": env.outcome, "steps": step,
            "heat": heat, "heat_before_fix": heat_before_fix}
