"""Final mission report: evidence, inferred location/status, confidence, next step."""
from __future__ import annotations

from typing import Any

from .world import dist


def _recommend(found: bool, a: dict[str, Any], agent, outcome: str) -> str:
    x, y = a["location"]
    status = a["status"]
    charger_cost = agent.to_charger.get(tuple(a["location"]), None)
    if found:
        return {
            "active": f"EVE is active at ({x}, {y}). Hold position beside her, flash the greeting light and "
                      f"let her lead; nearest charger is {charger_cost} battery away if she wants to travel.",
            "dormant": f"EVE is dormant in directive mode at ({x}, {y}), carrying the plant. Stay with her, "
                       f"shield her from storms and wait for the Axiom recovery ship. Shuttle to the charger "
                       f"({charger_cost} battery) between watches instead of leaving for long.",
            "damaged": f"EVE is damaged at ({x}, {y}). Stabilise her, then tow her to the nearest charger "
                       f"({charger_cost} battery away) and scavenge parts for repairs before the next storm.",
        }[status]
    if outcome == "stranded":
        return (f"WALL-E ran out of battery. Recovery team should retrieve him, then search around ({x}, {y}) "
                f"where the belief peaks.")
    if a["location_confidence"] >= 0.5:
        return (f"EVE not sighted, but {a['location_confidence']:.0%} of the belief lies within 2 cells of "
                f"({x}, {y}). Recharge fully and make a direct run there with an area scan on arrival; she is "
                f"most likely {status}.")
    return (f"Evidence is still inconclusive (90% region spans {a['cells_90']} cells). Recharge, then take "
            f"beacon readings from at least two widely spaced positions toward ({x}, {y}) to triangulate "
            f"before committing to a search sweep.")


def build_report(result: dict[str, Any]) -> dict[str, Any]:
    agent, env, cfg = result["agent"], result["env"], result["cfg"]
    a = agent.assessment()
    found = a["found"]
    truth = env.ground_truth()
    rec = _recommend(found, a, agent, result["outcome"])
    return {
        "mission": cfg.name,
        "seed": cfg.seed,
        "agent": getattr(agent, "name", type(agent).__name__),
        "outcome": result["outcome"],
        "steps": result["steps"],
        "time_used": env.time,
        "time_limit": env.time_limit,
        "battery_left": round(env.battery, 2),
        "battery_capacity": env.capacity,
        "distance_travelled": len(agent.path_history) - 1,
        "assessment": a,
        "recommended_next_step": rec,
        "evidence": agent.evidence,
        "strategy_changes": agent.strategy_changes,
        "ground_truth": truth,
        "evaluation": {
            "location_error_cells": round(dist(tuple(a["location"]), truth["eve_position"]), 2),
            "status_correct": a["status"] == truth["eve_status"],
            "clues_found": sum(c["found"] for c in truth["clues"]),
            "clues_total": len(truth["clues"]),
            "decoys_identified": len(getattr(agent.belief, "known_decoys", [])) if hasattr(agent, "belief") else 0,
            "decoys_total": len(truth["decoys"]),
        },
    }


def _fmt_evidence(e: dict[str, Any]) -> str:
    d = e["detail"]
    if e["kind"] == "initial_signal":
        coords = f", rough fix {tuple(d['coordinates'])} ±{d.get('uncertainty')}" if d.get("coordinates") else ""
        return (f"Initial signal ({d.get('timestamp')}): bearing {d.get('bearing_deg')}°, strength "
                f"{d.get('strength')}{coords}")
    if e["kind"] == "signal":
        if not d:
            return f"Beacon scan at {tuple(e['position'])}: no detection"
        parts = [f"{x['bearing_deg']:.0f}° / {x['strength']:.3f} / {x['pulse_interval_ms']:.0f}ms "
                 f"(P(EVE)={x.get('p_eve', 0):.2f})" for x in d]
        return f"Beacon scan at {tuple(e['position'])}: " + "; ".join(parts)
    if e["kind"] == "clue":
        extra = ", ".join(f"{k}={v}" for k, v in d.items() if k not in ("type", "position", "note"))
        return f"Clue **{d['type']}** at {tuple(d['position'])}: {d.get('note', '')} ({extra})"
    if e["kind"] == "decoy":
        return f"Decoy transmitter at {tuple(e['position'])}: {d}"
    if e["kind"] == "eve_sighting":
        return f"**EVE sighted** at {tuple(d['position'])}: {d['note']}"
    return str(d)


def report_markdown(rep: dict[str, Any], ascii_map: str | None = None) -> str:
    a, ev = rep["assessment"], rep["evaluation"]
    lines = [
        f"# Mission report: {rep['mission']}",
        "",
        f"- **Outcome:** `{rep['outcome']}` after {rep['steps']} actions "
        f"({rep['time_used']}/{rep['time_limit']} time units)",
        f"- **Battery left:** {rep['battery_left']}/{rep['battery_capacity']:.0f}; "
        f"cells travelled: {rep['distance_travelled']}",
        "",
        "## Assessment",
        "",
        f"- **EVE located:** {'yes (direct sighting)' if a['found'] else 'no (inferred)'}",
        f"- **Inferred location:** ({a['location'][0]}, {a['location'][1]}), "
        f"confidence {a['location_confidence']:.0%} within 2 cells; 90% credible region: {a['cells_90']} cells",
        f"- **Inferred status:** {a['status']} ({a['status_confidence']:.0%}); posterior "
        + ", ".join(f"{k} {v:.0%}" for k, v in a["status_posterior"].items()),
        "",
        "## Recommended next step",
        "",
        rep["recommended_next_step"],
        "",
        "## Evidence (in order found)",
        "",
    ]
    lines += [f"{i}. t={e['time']}: {_fmt_evidence(e)}" for i, e in enumerate(rep["evidence"], 1)]
    lines += ["", "## Strategy changes", ""]
    if rep["strategy_changes"]:
        lines += ["| t | at | change | why |", "|---|---|---|---|"]
        for c in rep["strategy_changes"]:
            lines.append(f"| {c['time']} | {tuple(c['position'])} | {c['kind']} → {c['to']} | {c['why']} |")
    else:
        lines.append("None.")
    gt = rep["ground_truth"]
    lines += [
        "",
        "## Evaluation against ground truth",
        "",
        "_Hidden from the agent during the mission._",
        "",
        f"- True EVE position {tuple(gt['eve_position'])}, status {gt['eve_status']}",
        f"- Location error: {ev['location_error_cells']} cells; status correct: {ev['status_correct']}",
        f"- Clues found: {ev['clues_found']}/{ev['clues_total']}; decoys identified: "
        f"{ev['decoys_identified']}/{ev['decoys_total']}",
    ]
    if ascii_map:
        lines += ["", "## Map", "", "```", ascii_map, "```"]
    return "\n".join(lines) + "\n"
