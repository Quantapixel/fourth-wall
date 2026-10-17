"""Generalisation benchmark: run each agent on the same random missions across difficulty tiers."""
from __future__ import annotations

import json
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .config import from_dict
from .report import build_report
from .runner import run_mission

TIERS: dict[str, dict[str, Any]] = {
    "easy": {
        "map": {"width": 24, "height": 16, "obstacle_density": 0.10, "rubble_density": 0.08, "chargers": 2},
        "resources": {"battery": 200, "time_limit": 400},
        "sensors": {"bearing_noise_deg": 10, "strength_noise": 0.03},
        "decoys": {"count": 0},
    },
    "medium": {
        "map": {"width": 32, "height": 22, "obstacle_density": 0.13, "rubble_density": 0.10, "chargers": 3},
        "resources": {"battery": 140, "time_limit": 400},
        "sensors": {"bearing_noise_deg": 15, "strength_noise": 0.04},
        "decoys": {"count": 1},
    },
    "hard": {
        "map": {"width": 40, "height": 26, "obstacle_density": 0.15, "rubble_density": 0.12, "chargers": 3},
        "resources": {"battery": 100, "time_limit": 350},
        "sensors": {"bearing_noise_deg": 20, "strength_noise": 0.06},
        "decoys": {"count": 2},
    },
    "extreme": {
        "map": {"width": 48, "height": 32, "obstacle_density": 0.16, "rubble_density": 0.15, "chargers": 3},
        "resources": {"battery": 70, "time_limit": 220},
        "sensors": {"bearing_noise_deg": 25, "strength_noise": 0.07},
        "clues": {"count": 4},
        "decoys": {"count": 3},
    },
}


def _one(job: tuple[str, int, str]) -> dict[str, Any]:
    from .cli import agent_factories

    tier, seed, agent = job
    cfg = from_dict({"mission": {"name": f"{tier}-{seed}", "seed": seed}, **TIERS[tier]})
    result = run_mission(cfg, agent_factories()[agent])
    rep = build_report(result)
    return {
        "tier": tier, "seed": seed, "agent": agent, "outcome": rep["outcome"],
        "success": rep["outcome"] == "rendezvous",
        "time_used": rep["time_used"], "battery_left": rep["battery_left"],
        "location_error": rep["evaluation"]["location_error_cells"],
        "status_correct": rep["evaluation"]["status_correct"],
        "clues_found": rep["evaluation"]["clues_found"],
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r["success"]]
    return {
        "missions": len(rows),
        "success_rate": round(len(ok) / len(rows), 3),
        "stranded_rate": round(sum(r["outcome"] == "stranded" for r in rows) / len(rows), 3),
        "mean_time_success": round(statistics.mean(r["time_used"] for r in ok), 1) if ok else None,
        "median_location_error": round(statistics.median(r["location_error"] for r in rows), 2),
        "status_accuracy": round(sum(r["status_correct"] for r in rows) / len(rows), 3),
        "mean_clues_found": round(statistics.mean(r["clues_found"] for r in rows), 2),
    }


def run_benchmark(n: int, seed: int, agents: list[str], out: Path, factories=None) -> dict[str, Any]:
    jobs = [(tier, seed + i, a) for tier in TIERS for i in range(n) for a in agents]
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(_one, jobs, chunksize=4))
    summary = {tier: {a: _aggregate([r for r in rows if r["tier"] == tier and r["agent"] == a]) for a in agents}
               for tier in TIERS}
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps({"summary": summary, "missions": rows}, indent=2) + "\n")

    lines = [f"# Benchmark: {n} random missions per tier (seeds {seed}..{seed + n - 1})", "",
             "| tier | agent | success | stranded | mean time (success) | median loc. error | status acc. | clues found |",
             "|---|---|---|---|---|---|---|---|"]
    for tier, per in summary.items():
        for a, s in per.items():
            lines.append(f"| {tier} | {a} | {s['success_rate']:.0%} | {s['stranded_rate']:.0%} | "
                         f"{s['mean_time_success'] if s['mean_time_success'] is not None else '-'} | "
                         f"{s['median_location_error']} | {s['status_accuracy']:.0%} | {s['mean_clues_found']} |")
    lines += ["", "Tier settings:", "", "```json", json.dumps(TIERS, indent=2), "```", ""]
    (out / "benchmark.md").write_text("\n".join(lines))
    print("\n".join(lines[:3 + len(TIERS) * len(agents) + 1]))
    return summary
