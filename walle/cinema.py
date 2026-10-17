"""Cinematic mission player: an isometric, animated, self-contained HTML replay.

The page is rendered entirely with the 2D canvas API (no external libraries, works
offline). It shows the agent's belief as a glowing heatmap, beacon bearings as cones
coloured by P(EVE), area scans, strategy shifts and the reasoning behind every step.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).with_name("cinema_template.html")


def cinema_html(result: dict[str, Any], report: dict[str, Any]) -> str:
    b = result["briefing"]
    heat = result.get("heat", [])
    steps = []
    for k, rec in enumerate(result["trace"].records):
        obs = rec.get("observation", {})
        steps.append({
            "pos": obs.get("position", b["start"]),
            "time": obs.get("time", 0),
            "battery": obs.get("battery", b["battery"]),
            "mode": rec.get("mode"),
            "action": rec.get("action"),
            "reasoning": rec.get("reasoning"),
            "notes": rec.get("notes", []),
            "changes": rec.get("strategy_changes", []),
            "target": (rec.get("decision") or {}).get("target"),
            "clues": obs.get("clues", []),
            "decoys": [d["position"] for d in obs.get("decoys", [])],
            "dets": obs.get("detections"),
            "eve": obs.get("eve"),
            "belief": rec.get("belief"),
            "heat": heat[k] if k < len(heat) else None,
        })
    data = {
        "name": result["cfg"].name, "outcome": result["outcome"], "width": b["width"], "height": b["height"],
        "map": b["map"], "chargers": b["chargers"], "start": b["start"], "capacity": b["capacity"],
        "time_limit": b["time_limit"], "sensors": b["sensors"],
        "initial_bearing": b["initial_signal"].get("bearing_deg"),
        "steps": steps, "truth": result["env"].ground_truth(),
        "assessment": report["assessment"], "recommendation": report["recommended_next_step"],
        "n_changes": len(report["strategy_changes"]),
    }
    payload = json.dumps(data, separators=(",", ":"), default=list).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("__DATA__", payload)
