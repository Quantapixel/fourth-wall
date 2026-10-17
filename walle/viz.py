"""Visualisation: ASCII maps, a static SVG and a self-contained HTML replay."""
from __future__ import annotations

import html
import json
from typing import Any

import numpy as np

CLUE_CHAR = {"hover_tracks": "t", "debris": "d", "plant_residue": "p", "memory_chip": "m"}
MODE_COLOR = {
    "SEARCH": "#3b82f6", "INVESTIGATE": "#a855f7", "RECHARGE": "#f59e0b",
    "RETURN": "#64748b", "RENDEZVOUS": "#10b981", "FINAL_APPROACH": "#ef4444", "DONE": "#10b981", None: "#3b82f6",
}
SHADES = " .:-=+*%@"


def ascii_map(briefing: dict[str, Any], path: list, clues: list, decoys: list, truth: dict | None = None,
              inferred: list | None = None, heat: np.ndarray | None = None) -> str:
    rows = [list(r) for r in briefing["map"]]
    H, W = len(rows), len(rows[0])
    if heat is not None and heat.max() > 0:
        h = heat / heat.max()
        for y in range(H):
            for x in range(W):
                if rows[y][x] == "." and h[y, x] > 0.02:
                    rows[y][x] = SHADES[min(len(SHADES) - 1, int(h[y, x] * (len(SHADES) - 1)) + 1)]
    for x, y in path:
        if rows[y][x] not in "C":
            rows[y][x] = "*"
    sx, sy = briefing["start"]
    rows[sy][sx] = "S"
    if truth:
        for d in truth["decoys"]:
            x, y = d["position"]
            rows[y][x] = "X" if d["found"] else "x"
        for c in truth["clues"]:
            x, y = c["position"]
            ch = CLUE_CHAR[c["type"]]
            rows[y][x] = ch.upper() if c["found"] else ch
    else:
        for c in clues:
            x, y = c["position"]
            rows[y][x] = CLUE_CHAR[c["type"]].upper()
        for x, y in decoys:
            rows[y][x] = "X"
    if inferred:
        rows[inferred[1]][inferred[0]] = "?"
    if truth:
        x, y = truth["eve_position"]
        rows[y][x] = "E"
    if path:
        x, y = path[-1]
        rows[y][x] = "W"
    border = "+" + "-" * W + "+"
    body = [border] + ["|" + "".join(r) + "|" for r in rows] + [border]
    legend = ("W WALL-E  E EVE  ? inferred  S base  C charger  * path  # wall  ~ rubble  "
              "T/D/P/M clue found (t/d/p/m missed)  X decoy found (x missed)  .:-=+*%@ belief")
    return "\n".join(body + [legend])


def strategy_frames(result: dict[str, Any]) -> str:
    """ASCII snapshots at every strategy change, showing path and belief at that moment."""
    briefing = result["briefing"]
    frames = []
    path: list = [tuple(briefing["start"])]
    clues: list = []
    decoys: list = []
    for rec, heat in zip(result["trace"].records[1:], result.get("heat", [])[1:]):
        pos = tuple(rec["observation"]["position"])
        if path[-1] != pos:
            path.append(pos)
        clues += rec["observation"].get("clues", [])
        decoys += [tuple(d["position"]) for d in rec["observation"].get("decoys", [])]
        if rec["strategy_changes"]:
            head = f"t={rec['observation']['time']} battery={rec['observation']['battery']} mode={rec['mode']}"
            why = "\n".join(f"  - {c['kind']} -> {c['to']}: {c['why']}" for c in rec["strategy_changes"])
            frames.append(head + "\n" + why + "\n" + ascii_map(briefing, path, clues, decoys, heat=_dense(heat, briefing)))
    return "\n\n".join(frames) + "\n"


def _dense(sparse: dict | None, briefing: dict) -> np.ndarray | None:
    if sparse is None:
        return None
    out = np.zeros((briefing["height"], briefing["width"]))
    for i, v in zip(sparse["i"], sparse["v"]):
        out.flat[i] = v / 255.0
    return out


def sparse_heat(loc: np.ndarray) -> dict[str, list[int]]:
    m = loc.max()
    q = np.round(loc / m * 255).astype(int) if m > 0 else np.zeros_like(loc, dtype=int)
    idx = np.flatnonzero(q > 2)
    return {"i": idx.tolist(), "v": q.ravel()[idx].tolist()}


def svg(result: dict[str, Any], cell: int = 18) -> str:
    """Static picture: terrain, final pre-sighting belief, path coloured by mode, clues, decoys, EVE."""
    b, env, agent = result["briefing"], result["env"], result["agent"]
    W, H = b["width"], b["height"]
    truth = env.ground_truth()
    pad, legend_h = 10, 86
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * cell + 2 * pad}" '
           f'height="{H * cell + 2 * pad + legend_h}" font-family="monospace" font-size="11">',
           f'<rect width="100%" height="100%" fill="#0f172a"/>', f'<g transform="translate({pad},{pad})">']
    for y, row in enumerate(b["map"]):
        for x, ch in enumerate(row):
            fill = {"#": "#334155", "~": "#78716c"}.get(ch, "#1e293b")
            out.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}" fill="{fill}" stroke="#0f172a"/>')
    heat = _dense(result.get("heat_before_fix"), b)
    if heat is not None:
        for y in range(H):
            for x in range(W):
                if heat[y, x] > 0.03:
                    out.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}" '
                               f'fill="#f43f5e" fill-opacity="{0.15 + 0.7 * heat[y, x]:.2f}"/>')
    for x, y in b["chargers"]:
        out.append(f'<text x="{x * cell + cell / 2}" y="{y * cell + cell * 0.72}" text-anchor="middle" fill="#facc15" font-weight="bold">C</text>')
    # Path segments coloured by the mode the agent was in.
    recs = result["trace"].records[1:]
    for rec in recs:
        p0, p1 = rec["state"]["position"], rec["observation"]["position"]
        if p0 != p1:
            out.append(f'<line x1="{p0[0] * cell + cell / 2}" y1="{p0[1] * cell + cell / 2}" '
                       f'x2="{p1[0] * cell + cell / 2}" y2="{p1[1] * cell + cell / 2}" '
                       f'stroke="{MODE_COLOR.get(rec["mode"], "#3b82f6")}" stroke-width="3" stroke-linecap="round"/>')
        if rec["action"]["type"] == "scan_signal":
            out.append(f'<circle cx="{p0[0] * cell + cell / 2}" cy="{p0[1] * cell + cell / 2}" r="3" fill="#e2e8f0"/>')
    for i, c in enumerate(agent.strategy_changes):
        x, y = c["position"]
        out.append(f'<rect x="{x * cell + 2}" y="{y * cell + 2}" width="{cell - 4}" height="{cell - 4}" fill="none" '
                   f'stroke="#fbbf24" stroke-width="1.5"><title>t={c["time"]} {html.escape(c["kind"])} -> '
                   f'{html.escape(str(c["to"]))}: {html.escape(c["why"])}</title></rect>')
    for c in truth["clues"]:
        x, y = c["position"]
        ch = CLUE_CHAR[c["type"]]
        out.append(f'<text x="{x * cell + cell / 2}" y="{y * cell + cell * 0.72}" text-anchor="middle" '
                   f'fill="{"#22d3ee" if c["found"] else "#475569"}" font-weight="bold">{ch.upper() if c["found"] else ch}'
                   f'<title>{c["type"]}{" (found)" if c["found"] else " (missed)"}</title></text>')
    for d in truth["decoys"]:
        x, y = d["position"]
        out.append(f'<text x="{x * cell + cell / 2}" y="{y * cell + cell * 0.72}" text-anchor="middle" '
                   f'fill="{"#fb923c" if d["found"] else "#9a3412"}" font-weight="bold">X<title>decoy</title></text>')
    sx, sy = b["start"]
    out.append(f'<text x="{sx * cell + cell / 2}" y="{sy * cell + cell * 0.72}" text-anchor="middle" fill="#f8fafc" font-weight="bold">S</text>')
    ex, ey = truth["eve_position"]
    out.append(f'<circle cx="{ex * cell + cell / 2}" cy="{ey * cell + cell / 2}" r="{cell * 0.42}" fill="none" stroke="#f8fafc" stroke-width="2"/>')
    out.append(f'<text x="{ex * cell + cell / 2}" y="{ey * cell + cell * 0.72}" text-anchor="middle" fill="#f8fafc" font-weight="bold">E</text>')
    inf = agent.assessment()["location"]
    if tuple(inf) != tuple(truth["eve_position"]):
        out.append(f'<text x="{inf[0] * cell + cell / 2}" y="{inf[1] * cell + cell * 0.72}" text-anchor="middle" fill="#f472b6" font-weight="bold">?</text>')
    wx, wy = agent.path_history[-1]
    out.append(f'<circle cx="{wx * cell + cell / 2}" cy="{wy * cell + cell / 2}" r="{cell * 0.3}" fill="#facc15"/>')
    out.append("</g>")
    ly = H * cell + 2 * pad + 14
    items = [(MODE_COLOR[m], m) for m in ("SEARCH", "INVESTIGATE", "RECHARGE", "RETURN", "RENDEZVOUS")]
    for i, (col, label) in enumerate(items):
        out.append(f'<rect x="{pad + i * 110}" y="{ly - 9}" width="14" height="4" fill="{col}"/>'
                   f'<text x="{pad + i * 110 + 18}" y="{ly - 4}" fill="#cbd5e1">{label}</text>')
    out.append(f'<text x="{pad}" y="{ly + 16}" fill="#cbd5e1">dots: beacon scans  amber boxes: strategy changes  '
               f'red: belief before sighting</text>')
    out.append(f'<text x="{pad}" y="{ly + 32}" fill="#cbd5e1">T/D/P/M clues (grey = missed)  X decoy  E EVE  '
               f'? inferred  C charger  S base</text>')
    out.append(f'<text x="{pad}" y="{ly + 50}" fill="#94a3b8">{html.escape(result["cfg"].name)}: outcome '
               f'{result["outcome"]}, t={env.time}, battery {env.battery:.0f}/{env.capacity:.0f}</text>')
    out.append("</svg>")
    return "\n".join(out)


REPLAY_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WALL-E Mission Replay</title>
<style>
:root{--bg:#f8fafc;--fg:#0f172a;--muted:#64748b;--panel:#ffffff;--line:#e2e8f0;--floor:#e2e8f0;--wall:#475569;--rubble:#a8a29e;--heat:244,63,94}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f172a;--fg:#e2e8f0;--muted:#94a3b8;--panel:#111c33;--line:#1e293b;--floor:#1e293b;--wall:#334155;--rubble:#57534e}}
:root[data-theme="dark"]{--bg:#0f172a;--fg:#e2e8f0;--muted:#94a3b8;--panel:#111c33;--line:#1e293b;--floor:#1e293b;--wall:#334155;--rubble:#57534e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;padding:16px}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--muted);margin-bottom:12px}
.wrap{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:16px}@media(max-width:860px){.wrap{grid-template-columns:1fr}}
canvas{width:100%;height:auto;border-radius:8px;background:var(--floor);display:block}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;max-height:80vh}
.controls{display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap}input[type=range]{flex:1;min-width:120px}
button{background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
.k{color:var(--muted)}.mode{font-weight:600}.chg{border-left:3px solid #f59e0b;padding-left:8px;margin:6px 0}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden}.bar>div{height:100%;background:#10b981}
ul{padding-left:18px;margin:4px 0}code{font-size:12px}
</style></head><body>
<h1>WALL-E Mission Replay</h1><div class="sub" id="sub"></div>
<div class="wrap"><div><canvas id="cv"></canvas>
<div class="controls"><button id="play">Play</button><button id="prev">&lt;</button><button id="next">&gt;</button>
<input type="range" id="slider" min="0" value="0"><span id="stepno" class="k"></span>
<label class="k"><input type="checkbox" id="truth"> show hidden truth</label></div></div>
<div class="panel" id="info"></div></div>
<script>
const D = __DATA__;
const cv=document.getElementById('cv'),ctx=cv.getContext('2d'),S=24;cv.width=D.width*S;cv.height=D.height*S;
const slider=document.getElementById('slider');slider.max=D.steps.length-1;
const MODE=__MODES__;let i=0,timer=null;
document.getElementById('sub').textContent=D.name+' — outcome: '+D.outcome+' · '+D.steps.length+' steps';
function css(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim()}
function cellText(x,y,t,c){ctx.fillStyle=c;ctx.font='bold 14px monospace';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(t,x*S+S/2,y*S+S/2+1)}
function draw(){
 const st=D.steps[i];ctx.clearRect(0,0,cv.width,cv.height);
 for(let y=0;y<D.height;y++)for(let x=0;x<D.width;x++){const ch=D.map[y][x];ctx.fillStyle=ch==='#'?css('--wall'):ch==='~'?css('--rubble'):css('--floor');ctx.fillRect(x*S,y*S,S-1,S-1)}
 const h=st.heat;if(h)for(let k=0;k<h.i.length;k++){const x=h.i[k]%D.width,y=Math.floor(h.i[k]/D.width);ctx.fillStyle='rgba('+css('--heat')+','+(0.12+0.75*h.v[k]/255).toFixed(3)+')';ctx.fillRect(x*S,y*S,S-1,S-1)}
 for(const c of D.chargers)cellText(c[0],c[1],'C','#eab308');
 ctx.lineWidth=4;ctx.lineCap='round';
 for(let k=1;k<=i;k++){const a=D.steps[k-1].pos,b=D.steps[k].pos;if(a[0]===b[0]&&a[1]===b[1])continue;ctx.strokeStyle=MODE[D.steps[k].mode]||'#3b82f6';ctx.beginPath();ctx.moveTo(a[0]*S+S/2,a[1]*S+S/2);ctx.lineTo(b[0]*S+S/2,b[1]*S+S/2);ctx.stroke()}
 for(let k=0;k<=i;k++){for(const c of D.steps[k].clues)cellText(c.position[0],c.position[1],c.type[0].toUpperCase(),'#0891b2');for(const d of D.steps[k].decoys)cellText(d[0],d[1],'X','#ea580c')}
 cellText(D.start[0],D.start[1],'S',css('--fg'));
 if(document.getElementById('truth').checked){const e=D.truth.eve_position;ctx.strokeStyle=css('--fg');ctx.lineWidth=2;ctx.beginPath();ctx.arc(e[0]*S+S/2,e[1]*S+S/2,S*0.42,0,7);ctx.stroke();cellText(e[0],e[1],'E',css('--fg'));for(const d of D.truth.decoys)cellText(d.position[0],d.position[1],'x','#9a3412')}
 if(st.target){ctx.strokeStyle='#a855f7';ctx.lineWidth=2;ctx.setLineDash([4,3]);ctx.strokeRect(st.target[0]*S+2,st.target[1]*S+2,S-5,S-5);ctx.setLineDash([])}
 ctx.fillStyle='#facc15';ctx.beginPath();ctx.arc(st.pos[0]*S+S/2,st.pos[1]*S+S/2,S*0.32,0,7);ctx.fill();
 slider.value=i;document.getElementById('stepno').textContent='step '+i+'/'+(D.steps.length-1);
 const b=st.belief||{};const pct=v=>(100*v).toFixed(0)+'%';
 let html='<div><span class="mode" style="color:'+(MODE[st.mode]||'inherit')+'">'+(st.mode||'BRIEFING')+'</span> · t='+st.time+'</div>';
 html+='<div class="k">battery '+st.battery.toFixed(0)+'/'+D.capacity+'</div><div class="bar"><div style="width:'+(100*st.battery/D.capacity)+'%"></div></div>';
 if(st.action)html+='<p><b>Action</b> <code>'+JSON.stringify(st.action)+'</code></p>';
 if(st.reasoning)html+='<p><b>Reasoning</b> '+esc(st.reasoning)+'</p>';
 if(st.notes&&st.notes.length)html+='<p><b>Observed</b></p><ul>'+st.notes.map(n=>'<li>'+esc(n)+'</li>').join('')+'</ul>';
 for(const c of st.changes||[])html+='<div class="chg"><b>Strategy change</b>: '+esc(c.kind+' → '+JSON.stringify(c.to))+'<br><span class="k">'+esc(c.why)+'</span></div>';
 if(b.map_cell)html+='<p><b>Belief</b> peak ('+b.map_cell+') '+pct(b.mass_r2_at_map)+' within 2 cells · 90% region '+b.cells_90+' cells<br><span class="k">status: '+Object.entries(b.status).map(([k,v])=>k+' '+pct(v)).join(', ')+'</span></p>';
 if(i===D.steps.length-1)html+='<p><b>Recommended next step</b><br>'+esc(D.recommendation)+'</p>';
 document.getElementById('info').innerHTML=html}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
slider.oninput=()=>{i=+slider.value;draw()};
document.getElementById('next').onclick=()=>{i=Math.min(i+1,D.steps.length-1);draw()};
document.getElementById('prev').onclick=()=>{i=Math.max(i-1,0);draw()};
document.getElementById('truth').onchange=draw;
document.getElementById('play').onclick=e=>{if(timer){clearInterval(timer);timer=null;e.target.textContent='Play';return}
 e.target.textContent='Pause';timer=setInterval(()=>{if(i>=D.steps.length-1){clearInterval(timer);timer=null;e.target.textContent='Play';return}i++;draw()},180)};
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
draw();
</script></body></html>
"""


def replay_html(result: dict[str, Any], report: dict[str, Any]) -> str:
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
            "belief": rec.get("belief"),
            "heat": heat[k] if k < len(heat) else None,
        })
    data = {
        "name": result["cfg"].name, "outcome": result["outcome"], "width": b["width"], "height": b["height"],
        "map": b["map"], "chargers": b["chargers"], "start": b["start"], "capacity": b["capacity"],
        "steps": steps, "truth": result["env"].ground_truth(), "recommendation": report["recommended_next_step"],
    }
    modes = {k: v for k, v in MODE_COLOR.items() if k}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return REPLAY_TEMPLATE.replace("__DATA__", payload).replace("__MODES__", json.dumps(modes))
