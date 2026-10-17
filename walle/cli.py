"""Command line: `python -m walle run <config>` and `python -m walle bench`."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cinema import cinema_html
from .config import load_config
from .report import build_report, report_markdown
from .runner import run_mission
from .viz import ascii_map, replay_html, strategy_frames, svg


def agent_factories():
    from .agent import BeliefAgent
    from .baselines import GreedySignalAgent, RandomAgent
    return {"belief": BeliefAgent, "greedy": GreedySignalAgent, "random": RandomAgent}


def write_outputs(result: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rep = build_report(result)
    agent, env = result["agent"], result["env"]
    truth = env.ground_truth()
    final_map = ascii_map(result["briefing"], agent.path_history, [], [], truth=truth,
                          inferred=rep["assessment"]["location"])
    result["trace"].write_jsonl(out / "trace.jsonl")
    (out / "report.json").write_text(json.dumps(rep, indent=2, default=list) + "\n")
    (out / "report.md").write_text(report_markdown(rep, final_map))
    (out / "map.txt").write_text(final_map + "\n")
    if result.get("heat") and result["heat"][0] is not None:
        (out / "strategy_frames.txt").write_text(strategy_frames(result))
    (out / "path.svg").write_text(svg(result))
    (out / "replay.html").write_text(replay_html(result, rep))
    (out / "cinema.html").write_text(cinema_html(result, rep))
    return rep


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    result = run_mission(cfg, agent_factories()[args.agent])
    out = Path(args.out or f"runs/{cfg.name}")
    rep = write_outputs(result, out)
    a = rep["assessment"]
    print(f"[{cfg.name}] outcome={rep['outcome']} time={rep['time_used']}/{rep['time_limit']} "
          f"battery={rep['battery_left']:.0f}/{rep['battery_capacity']:.0f}")
    print(f"  EVE {'found' if a['found'] else 'inferred'} at {tuple(a['location'])} "
          f"({a['location_confidence']:.0%}), status {a['status']} ({a['status_confidence']:.0%})")
    print(f"  next step: {rep['recommended_next_step']}")
    if args.ascii:
        print((out / "map.txt").read_text())
    print(f"  outputs written to {out}/  (open cinema.html for the animated replay)")
    if args.open:
        import webbrowser
        webbrowser.open((out / "cinema.html").resolve().as_uri())
    return 0


def cmd_bench(args) -> int:
    from .benchmark import run_benchmark
    run_benchmark(n=args.n, seed=args.seed, agents=args.agents.split(","), out=Path(args.out),
                  factories=agent_factories())
    return 0


def cmd_site(args) -> int:
    from .site import build_site
    built = build_site(Path(args.runs), Path(args.out), args.repo)
    print(f"site with {len(built)} missions written to {args.out}/")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="walle", description="WALL-E and EVE's Signal: autonomous search agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one mission from a JSON/YAML config")
    r.add_argument("config")
    r.add_argument("--out", help="output directory (default runs/<mission name>)")
    r.add_argument("--agent", default="belief", choices=["belief", "greedy", "random"])
    r.add_argument("--ascii", action="store_true", help="print the final ASCII map")
    r.add_argument("--open", action="store_true", help="open the cinematic replay in a browser")
    r.set_defaults(func=cmd_run)
    b = sub.add_parser("bench", help="generalisation benchmark across random missions")
    b.add_argument("--n", type=int, default=60, help="missions per difficulty tier")
    b.add_argument("--seed", type=int, default=1000)
    b.add_argument("--agents", default="belief,greedy,random")
    b.add_argument("--out", default="runs/benchmark")
    b.set_defaults(func=cmd_bench)
    s = sub.add_parser("site", help="build a static showcase site from runs/")
    s.add_argument("--runs", default="runs")
    s.add_argument("--out", default="site")
    s.add_argument("--repo", default="https://github.com/Quantapixel/fourth-wall")
    s.set_defaults(func=cmd_site)
    args = ap.parse_args(argv)
    return args.func(args)
