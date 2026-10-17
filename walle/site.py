"""Builds a static showcase site from finished runs: `python -m walle site`."""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVE's Signal</title>
<meta name="description" content="An autonomous WALL-E agent that reasons its way to EVE under a battery and a clock.">
<style>
:root{--ink:#f6ead8;--muted:#c9b59a;--edge:rgba(255,214,160,.16);--amber:#ffb347;--bg:#140c08}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(ellipse at 70% -10%,#7a3a18 0%,#2a150c 45%,var(--bg) 75%) fixed;color:var(--ink);font:15px/1.6 "Inter","Segoe UI",system-ui,sans-serif}
main{max-width:1080px;margin:0 auto;padding:56px 16px 72px}
.eyebrow{letter-spacing:.5em;font-size:11px;color:var(--amber);text-transform:uppercase}
h1{font-size:clamp(44px,9vw,86px);line-height:1;margin:12px 0 14px;font-weight:900;letter-spacing:.06em;background:linear-gradient(180deg,#fff3dc,#ffb347 70%,#c8641e);-webkit-background-clip:text;background-clip:text;color:transparent}
.lede{color:var(--muted);font-size:18px;max-width:640px;margin:0}
.hero{margin:36px 0 0;border-radius:16px;overflow:hidden;border:1px solid var(--edge);box-shadow:0 30px 80px rgba(0,0,0,.5);display:block}
.hero img{width:100%;display:block}
h2{font-size:12px;letter-spacing:.32em;text-transform:uppercase;color:var(--amber);margin:56px 0 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.card{display:block;padding:20px;border-radius:14px;border:1px solid var(--edge);background:rgba(30,18,12,.6);color:inherit;text-decoration:none;transition:transform .2s,border-color .2s}
.card:hover{transform:translateY(-3px);border-color:var(--amber)}
.card h3{margin:0 0 6px;font-size:19px}
.card p{margin:0 0 14px;color:var(--muted);font-size:14px}
.meta{display:flex;flex-wrap:wrap;gap:6px}
.tag{font-size:11px;padding:2px 9px;border-radius:999px;border:1px solid var(--edge);color:var(--muted)}
.tag.ok{color:#5dffb0;border-color:rgba(93,255,176,.4)}
.watch{margin-top:14px;color:var(--amber);font-weight:700;letter-spacing:.08em;font-size:13px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat{padding:16px;border-radius:12px;border:1px solid var(--edge);background:rgba(30,18,12,.5)}
.stat b{display:block;font-size:28px}.stat span{color:var(--muted);font-size:13px}
footer{margin-top:56px;color:var(--muted);font-size:13px}
a{color:var(--amber)}
</style></head><body><main>
<div class="eyebrow">Fourth Wall · Earth, 2805</div>
<h1>EVE'S SIGNAL</h1>
<p class="lede">An autonomous WALL-E agent searches a wasteland for EVE with a noisy beacon, spoofed decoys, a battery and a clock. It keeps a Bayesian belief over where she is and what state she's in, and plans every move around it.</p>
<a class="hero" href="missions/__HERO__.html"><img src="__HERO_IMG__" alt="Cinematic replay: beacon bearing cones triangulating EVE"></a>
<h2>Watch a mission</h2>
<div class="grid">__CARDS__</div>
<h2>Benchmark · hardest tier</h2>
<div class="stats">__STATS__</div>
<footer>Space to play · ←/→ step · T reveals the hidden truth · drag to pan, scroll to zoom. Source on <a href="__REPO__">GitHub</a>.</footer>
</main></body></html>
"""

BLURBS = {
    "sample_mission": "Two decoys out-shout EVE. Pulse timing gives them away and the bearings triangulate her.",
    "decoy_canyon": "A loud decoy sits on the direct route. The agent is pulled toward it, then sees through it.",
    "last_light": "Hardest tier. With time nearly gone, WALL-E gambles on a 90% belief peak instead of going home.",
}


def build_site(runs: Path, out: Path, repo: str, hero: str = "decoy_canyon") -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "missions").mkdir(exist_ok=True)
    cards, built = [], []
    for name in BLURBS:
        run = runs / name
        if not (run / "cinema.html").exists():
            continue
        shutil.copy(run / "cinema.html", out / "missions" / f"{name}.html")
        rep = json.loads((run / "report.json").read_text())
        a = rep["assessment"]
        tags = [f'<span class="tag{" ok" if rep["outcome"] == "rendezvous" else ""}">{html.escape(rep["outcome"])}</span>',
                f'<span class="tag">t {rep["time_used"]}/{rep["time_limit"]}</span>',
                f'<span class="tag">EVE {html.escape(a["status"])}</span>']
        cards.append(f'<a class="card" href="missions/{name}.html"><h3>{name}</h3><p>{html.escape(BLURBS[name])}</p>'
                     f'<div class="meta">{"".join(tags)}</div><div class="watch">▶ WATCH</div></a>')
        built.append(name)
    img = Path(__file__).resolve().parent.parent / "docs" / "triangulation.png"
    if img.exists():
        shutil.copy(img, out / "hero.png")
    stats = ""
    results = runs / "benchmark" / "results.json"
    if results.exists():
        summary = json.loads(results.read_text()).get("summary", {}).get("extreme", {})
        rows = [(f'{summary[k]["success_rate"]:.0%}', f"{k} success") for k in ("belief", "greedy", "random") if k in summary]
        if "belief" in summary:
            rows.append((f'{summary["belief"]["stranded_rate"]:.0%}', "belief agent stranded"))
        stats = "".join(f'<div class="stat"><b>{v}</b><span>{html.escape(l)}</span></div>' for v, l in rows)
    page = (PAGE.replace("__CARDS__", "".join(cards)).replace("__STATS__", stats).replace("__REPO__", repo)
            .replace("__HERO__", hero).replace("__HERO_IMG__", "hero.png"))
    (out / "index.html").write_text(page)
    return built
