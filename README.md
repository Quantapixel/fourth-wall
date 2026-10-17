# Fourth Wall: WALL-E and EVE's Signal

An autonomous agent that explores a simulated wasteland, gathers clues and manages a limited battery and clock to find EVE, work out her status, and decide WALL-E's next move.

The agent is a **classical, belief-driven planner**. It keeps a Bayesian posterior over EVE's *position × status*, plans with an energy-constrained utility function, and switches between search, investigate, recharge, return and rendezvous modes. Every step is logged with its action, observation, decision and reasoning, and each mission ends with a report and visualizations.

```
python -m walle run configs/sample_mission.yaml --ascii
```

```
[sample_mission] outcome=rendezvous time=58/450 battery=40/110
  EVE found at (27, 20) (100%), status active (100%)
  next step: EVE is active at (27, 20). Hold position beside her, flash the greeting light and let her lead; ...
```

## Contents

| Path | What it is |
|---|---|
| `walle/config.py` | Loads JSON/YAML mission configs, applies defaults and validates them |
| `walle/world.py` | Terrain grid, procedural map generator, A*/Dijkstra path planning |
| `walle/env.py` | The simulator: hidden state, noisy beacon, decoys, clues, resource accounting |
| `walle/belief.py` | Bayesian grid filter over EVE's (x, y, status) with decoy-aware signal model |
| `walle/agent.py` | The autonomous agent: modes, energy guard, target selection, triangulation |
| `walle/baselines.py` | Greedy signal-follower and random-walk agents for comparison |
| `walle/runner.py` | Environment ↔ agent loop and the action trace |
| `walle/report.py` | Final mission report (JSON + Markdown) |
| `walle/viz.py` | ASCII map, strategy-change frames, SVG path image, interactive HTML replay |
| `walle/benchmark.py` | Generalization benchmark across random missions and difficulty tiers |
| `configs/` | Sample missions (procedural YAML and hand-drawn JSON) |
| `runs/` | Committed outputs for both sample missions and the benchmark |
| `tests/` | Unit tests |

## Running it

Requires Python 3.10+ with `numpy` and `PyYAML`.

```bash
pip install -r requirements.txt

# Run one mission (outputs go to runs/<mission name>/ by default)
python -m walle run configs/sample_mission.yaml
python -m walle run configs/decoy_canyon.json --ascii
python -m walle run configs/sample_mission.yaml --agent greedy --out runs/greedy_try

# Generalization benchmark: belief vs greedy vs random on the same seeded missions
python -m walle bench --n 100

# Tests
python -m unittest discover -s tests -t .
```

Each run writes:

| File | Contents |
|---|---|
| `trace.jsonl` | One JSON record per step: state before, mode, action, reasoning, decision details (target, its belief mass, travel cost, battery needed to reach a charger, time left), raw observation, interpreted notes, strategy changes, and a belief summary (MAP cell, top cells, entropy, 90% region size, status posterior, known decoys). Step 0 is the briefing. |
| `report.json` / `report.md` | Final mission report (see below) |
| `map.txt` | Final ASCII map with path, clues, decoys, EVE and the inferred location |
| `strategy_frames.txt` | ASCII snapshot (path plus belief heatmap) at every strategy change |
| `path.svg` | Static picture: path colored by mode, beacon-scan points, strategy-change markers, belief before the sighting |
| `replay.html` | Self-contained interactive replay: step slider, play button, live belief heatmap, reasoning panel, and a toggle to reveal hidden ground truth |

## Environment design

The world is a 4-connected grid:

| Glyph | Terrain | Effect |
|---|---|---|
| `.` | open ground | move costs 1 battery, 1 time |
| `~` | rubble | move costs 3 battery, 2 time (configurable) |
| `#` | trash pile | impassable |
| `C` | charger | `recharge` restores `recharge_rate` battery per action |
| `S` | base | WALL-E's start, always a charger |

**What the agent knows up front (the briefing):** the terrain map and charger locations (an "orbital map"), the resource budget, action costs, sensor specs, and the initial signal reading.

**What it must discover by interacting:** EVE's position and status, clue locations and contents, and decoy transmitters. None of this appears in the briefing (a unit test enforces it).

### Actions

| Action | Effect |
|---|---|
| `move` N/E/S/W | Moves one cell; blocked moves still cost time. Driving onto a clue reveals it. |
| `scan_signal` | Returns every beacon detection in range: bearing, strength, pulse interval and signature |
| `scan_area` | Reveals clues, decoy transmitters and EVE (with `scan_detect_prob`) within `scan_radius` |
| `recharge` | Only works on a charger |
| `wait` | Spends time |
| `end` | The agent ends the mission (`rendezvous`, `returned_to_base`, `sheltering_at_charger`) |

The simulator ends the mission itself if WALL-E runs out of battery away from a charger (`stranded`) or the clock runs out (`timeout`).

### Sensors and hidden state

- **EVE's beacon.** Strength is `power / (1 + (d/8)²)` plus Gaussian noise, and bearing noise is Gaussian. Status changes the signal:

  | Status | Power | Detection probability |
  |---|---|---|
  | active | 1.00 | 0.97 |
  | dormant | 0.55 | 0.90 |
  | damaged | 0.75 | 0.50 (flickers) |

  So the strength pattern and missed detections carry status information.
- **Decoys (spoofed signals).** These are transmitters that copy EVE's signature exactly and usually transmit *louder*. The only tell is timing: EVE pulses every 1000 ± 4 ms, while decoys jitter by ± 40 ms. An area scan next to a decoy exposes it physically.
- **Clues.** Each clue carries different evidence:

  | Clue | Where it's placed | Evidence |
  |---|---|---|
  | `hover_tracks` | 3–11 cells from EVE | A noisy heading toward her |
  | `debris` | Within 4 cells if she's damaged (fresh); anywhere otherwise (weathered) | Location and status |
  | `plant_residue` | Within 3 cells if she's active or dormant | Location and status |
  | `memory_chip` | Anywhere | Her map quadrant, 85% reliable |

## Agent design

### Belief

`Belief` holds `P[status, y, x]`. Each piece of evidence multiplies in a likelihood:

- **Beacon scans** use a mixture model. For each detection *i* the hypotheses are "*i* is EVE, the rest are decoys" and "EVE wasn't detected, all are decoys":

  `L(c, s) = (1 − p_det(d,s)) + Σᵢ p_det(d,s) · L_bearing,i(c) · L_strength,i(c,s) · [p_pulse,EVE / (p_pulse,decoy · D_i)]`

  Here `D_i` is the decoy density, which is diffuse for unknown decoys and peaked for known ones. As a result, a scan that detects nothing lowers the probability of nearby cells, and the agent reports P(EVE) for every detection.
- **Area scans with no sighting** multiply cells within the scan radius by `1 − scan_detect_prob`.
- **Clues** apply the likelihoods from the table above, including the status-specific ones.
- **Initial signal**: the briefing reading counts as a beacon detection from the base, and the optional rough fix counts as a Gaussian.

The full evidence log is kept. When a decoy transmitter is discovered, the posterior is **rebuilt from scratch**: past readings that came from that bearing get explained away, and this is logged as a `belief_rebuild` strategy change.

### Planning

At each step `BeliefAgent.decide()` runs these checks in priority order:

1. **Rendezvous**: if EVE has been sighted and the trip there is affordable, drive to her and end the mission next to her.
2. **Recharge**: while in RECHARGE mode, sit on the pad until nearly full, unless the clock says leave.
3. **Turn back**: when the time left is no more than the time to base plus a margin, switch to RETURN. RETURN checks the battery cost to base. If the trip is unaffordable it diverts to a charger, tops up there, or shelters there if time is out.
4. **Energy guard**: never take an action that would leave less than (cost to nearest charger + safety margin). Costs come from a reverse-Dijkstra map that includes rubble.
5. **Triangulate**: re-scan the beacon after moving a baseline distance (4 cells in SEARCH, 7 in INVESTIGATE), because bearings from separate points intersect at EVE.
6. **Target selection**: maximize `mass_within_scan_radius(c) / (1 + travel_cost(c)/12)` over cells where `travel + scan + cost(c → charger) + margin ≤ battery`. There is a small bonus for unscanned ground (clues) and hysteresis so the agent doesn't dither between targets. When the best target holds at least 35% of the belief, the mode flips SEARCH → INVESTIGATE. The agent scans the area when it reaches the target, or earlier if it passes through a dense patch of belief.

Every mode change, target change and belief rebuild is recorded with its reason. These records appear in the trace, the report, the strategy frames, and as amber markers in the SVG and replay.

### Final report

The report includes:
- outcome, time and battery used, distance travelled
- all evidence, in order found
- the inferred location, with confidence (posterior mass within 2 cells) and the size of the 90% credible region
- the status posterior
- a **recommended next step**: it depends on status if EVE was found (stay and guard her when dormant, tow her to a charger when damaged); otherwise it is a targeted search or more triangulation
- the full strategy-change table
- an evaluation against the hidden ground truth, clearly marked as hidden from the agent

## Config format

Any key can be omitted; defaults are in `walle/config.py`. YAML and JSON are both accepted.

```yaml
mission: {name: my_mission, seed: 42}       # seed drives map, hidden state and sensor noise

map:                                        # either procedural...
  width: 40
  height: 26
  obstacle_density: 0.15
  rubble_density: 0.12
  chargers: 3                               # including the base
  # ...or hand-drawn (glyphs . # ~ C S E):
  # grid: ["S....#", ".~..C.", "....#E"]

start: [1, 1]                               # optional; or 'S' in grid

eve:
  position: null                            # null = seeded (far from base); or 'E' in grid
  status: null                              # active | dormant | damaged | null = seeded

initial_signal:
  bearing_deg: 118                          # null = simulator derives a noisy first reading
  strength: 0.09
  timestamp: "2805-07-04T05:40:00Z"
  coordinates: [22, 11]                     # optional rough fix
  uncertainty: 7                            # cells (std of the fix)

resources:
  battery: 110
  time_limit: 450
  recharge_rate: 30
  costs:      {move: 1, move_rubble: 3, scan_signal: 2, scan_area: 3, recharge: 0, wait: 0}
  time_costs: {move: 1, move_rubble: 2, scan_signal: 1, scan_area: 2, recharge: 1, wait: 1}

sensors:
  signal_range: 40
  bearing_noise_deg: 18
  strength_noise: 0.05
  scan_radius: 2
  scan_detect_prob: 0.95

clues:
  count: 6                                  # seeded placement, or explicit:
  # list: [{type: hover_tracks, position: [21, 9]}, {type: memory_chip, position: [10, 6]}]

decoys:
  count: 2                                  # seeded placement, or explicit:
  # list: [{position: [14, 11], power: 1.4}]
```

## Sample missions

| Config | Setup | Result |
|---|---|---|
| [`configs/sample_mission.yaml`](configs/sample_mission.yaml) | Procedural 40×26 map, 2 seeded decoys, noisy sensors, 110 battery | Rendezvous at t=58. Every beacon scan saw 2–3 detections, and the agent scored the decoys at P(EVE)≈0 from pulse timing. It triangulated over 9 scans, switched to INVESTIGATE at t=44, and identified EVE as active. [report](runs/sample_mission/report.md) · [trace](runs/sample_mission/trace.jsonl) · [frames](runs/sample_mission/strategy_frames.txt) |
| [`configs/decoy_canyon.json`](configs/decoy_canyon.json) | Hand-drawn 30×16 map, a loud decoy on the direct route plus a second decoy, damaged EVE, 110 time limit | Briefly targeted the decoy area, then moved past it as timing evidence built up. Reached the damaged EVE at t=60/110 and recommended towing her to the charger 11 battery away. [report](runs/decoy_canyon/report.md) · [trace](runs/decoy_canyon/trace.jsonl) |

Open `runs/<mission>/replay.html` in a browser to step through a mission.

## Benchmark

`python -m walle bench --n 100` runs all three agents on the same 100 seeded missions in each of four tiers. Full results are in [`runs/benchmark/benchmark.md`](runs/benchmark/benchmark.md).

| tier | agent | success | stranded | mean time (success) | status acc. |
|---|---|---|---|---|---|
| easy | **belief** | **100%** | 0% | 30.9 | 100% |
| easy | greedy | 69% | 0% | 77.5 | 69% |
| easy | random | 3% | 0% | 241 | 33% |
| medium | **belief** | **100%** | 0% | 48.5 | 100% |
| medium | greedy | 13% | 0% | 93.2 | 30% |
| hard | **belief** | **100%** | 0% | 77.4 | 100% |
| hard | greedy | 10% | 0% | 109.4 | 29% |
| extreme | **belief** | **46%** | **0%** | 93.3 | 85% |
| extreme | greedy | 5% | 16% | 88.8 | 34% |

- **Greedy** trusts the strongest reading, so decoys pull it off course, and it strands itself 16% of the time on extreme missions with its fixed "recharge at 35%" rule.
- **The belief agent never strands.** When the extreme tier's 70-unit battery and 220-unit clock don't allow a sighting, it returns to base (or shelters at a charger) with an inferred location and status instead.

## Extensions implemented

Of the listed stretch and advanced goals, this project implements:
- path, clue and strategy-change visualization (ASCII, SVG and an interactive HTML UI)
- decoy/spoofed signals
- noisy sensors
- a generalization benchmark across random missions, with classical baselines

It does not include multi-agent coordination, an LLM-planner comparison, or a physics simulator.
