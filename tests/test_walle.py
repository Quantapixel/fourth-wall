import json
import tempfile
import unittest
from pathlib import Path

from walle.agent import AgentParams, BeliefAgent
from walle.belief import Belief
from walle.benchmark import TIERS
from walle.cli import main
from walle.config import ConfigError, from_dict, load_config
from walle.env import Environment
from walle.runner import run_mission
from walle.world import Grid, angle_diff, bearing_deg

ROOT = Path(__file__).resolve().parent.parent

TINY = {
    "mission": {"name": "tiny", "seed": 1},
    "map": {"grid": [
        "S....#....",
        ".##..#.~..",
        "....~...#.",
        ".#..##....",
        "......#..E",
        "..C.......",
    ]},
    "eve": {"status": "dormant"},
    "clues": {"list": [{"type": "hover_tracks", "position": [6, 2]}]},
    "decoys": {"list": [{"position": [0, 5], "power": 1.3}]},
}


class WorldTests(unittest.TestCase):
    def test_bearing_convention(self):
        self.assertAlmostEqual(bearing_deg((0, 0), (0, -1)), 0)    # north is up
        self.assertAlmostEqual(bearing_deg((0, 0), (1, 0)), 90)
        self.assertAlmostEqual(bearing_deg((0, 0), (0, 1)), 180)
        self.assertAlmostEqual(angle_diff(10, 350), 20)

    def test_astar_prefers_cheaper_than_rubble(self):
        g = Grid(["...", ".~.", "..."], [(0, 0)], 1, 5)
        path = g.astar((0, 1), (2, 1))
        self.assertNotIn((1, 1), path)
        self.assertEqual(g.path_cost(path), 4)

    def test_cost_to_targets_matches_astar(self):
        env = Environment(from_dict({"mission": {"seed": 5}}))
        g = env.grid
        to_base = g.cost_to_targets([env.start])
        for c in list(g.cells())[::17]:
            self.assertEqual(to_base[c], g.path_cost(g.astar(c, env.start)))


class ConfigTests(unittest.TestCase):
    def test_bad_status_rejected(self):
        with self.assertRaises(ConfigError):
            from_dict({"eve": {"status": "sleepy"}})

    def test_sample_configs_load(self):
        for p in (ROOT / "configs").iterdir():
            cfg = load_config(p)
            Environment(cfg)  # builds without error

    def test_grid_map_parsed(self):
        env = Environment(from_dict(TINY))
        self.assertEqual(env.start, (0, 0))
        self.assertEqual(env.eve_pos, (9, 4))
        self.assertIn((2, 5), env.grid.chargers)


class EnvironmentTests(unittest.TestCase):
    def test_briefing_hides_ground_truth(self):
        env = Environment(from_dict(TINY))
        text = json.dumps(env.briefing())
        self.assertNotIn("eve_pos", text)
        self.assertNotIn("E", "".join(env.briefing()["map"]))

    def test_clues_only_found_by_interaction(self):
        env = Environment(from_dict(TINY))
        obs = env.step({"type": "scan_area"})
        self.assertEqual(obs["clues"], [])
        self.assertFalse(env.clues[0].found)

    def test_decoy_spoofs_signature(self):
        env = Environment(from_dict(TINY))
        obs = env.step({"type": "scan_signal"})
        self.assertTrue(all(d["signature"] == "EVE-PROBE-07" for d in obs["detections"]))

    def test_resources_spent_and_blocked_moves(self):
        env = Environment(from_dict(TINY))
        obs = env.step({"type": "move", "dir": "N"})
        self.assertFalse(obs["ok"])
        before = env.battery
        env.step({"type": "scan_signal"})
        self.assertEqual(env.battery, before - 2)


class BeliefTests(unittest.TestCase):
    def test_two_bearings_triangulate(self):
        env = Environment(from_dict({**TINY, "decoys": {"count": 0}, "sensors": {"bearing_noise_deg": 5}}))
        b = Belief(env.briefing())
        b.add_signal((0, 0), [{"bearing_deg": bearing_deg((0, 0), (9, 4)), "strength": 0.4,
                               "pulse_interval_ms": 1000}])
        b.add_signal((9, 0), [{"bearing_deg": 180.0, "strength": 0.6, "pulse_interval_ms": 1000}])
        (x, y), _ = b.map_cell()
        self.assertLessEqual(abs(x - 9) + abs(y - 4), 2)

    def test_irregular_pulse_is_treated_as_decoy(self):
        b = Belief(Environment(from_dict(TINY)).briefing())
        probs = b.detection_eve_probs((0, 0), [
            {"bearing_deg": 100, "strength": 0.3, "pulse_interval_ms": 1001},
            {"bearing_deg": 200, "strength": 0.6, "pulse_interval_ms": 1060},
        ])
        self.assertGreater(probs[0], 0.5)
        self.assertLess(probs[1], 0.05)

    def test_negative_scan_reduces_local_mass(self):
        b = Belief(Environment(from_dict(TINY)).briefing())
        before = b.mass_within(2)[0, 0]
        b.add_scan((0, 0), 2)
        self.assertLess(b.mass_within(2)[0, 0], before * 0.2)


class AgentTests(unittest.TestCase):
    def test_tiny_mission_rendezvous(self):
        r = run_mission(from_dict(TINY))
        self.assertEqual(r["outcome"], "rendezvous")
        self.assertEqual(r["agent"].assessment()["status"], "dormant")

    def test_never_stranded_on_extreme_missions(self):
        for seed in range(30):
            r = run_mission(from_dict({"mission": {"seed": 2000 + seed}, **TIERS["extreme"]}))
            self.assertNotEqual(r["outcome"], "stranded", f"seed {2000 + seed}")

    def test_final_approach_beats_retreating(self):
        # Extreme seed 1036: EVE is pinned down when the clock forces a turn back.
        cfg = {"mission": {"seed": 1036}, **TIERS["extreme"]}
        r = run_mission(from_dict(cfg))
        self.assertEqual(r["outcome"], "rendezvous")
        modes = [c["to"] for c in r["agent"].strategy_changes if c["kind"] == "mode"]
        self.assertIn("FINAL_APPROACH", modes)
        timid = run_mission(from_dict(cfg), lambda b: BeliefAgent(b, AgentParams(final_approach=False)))
        self.assertNotEqual(timid["outcome"], "rendezvous")

    def test_trace_has_reasoning_for_every_step(self):
        r = run_mission(from_dict(TINY))
        for rec in r["trace"].records[1:]:
            for key in ("action", "observation", "decision", "reasoning", "belief"):
                self.assertIn(key, rec)
            self.assertTrue(rec["reasoning"])


class CliTests(unittest.TestCase):
    def test_run_writes_all_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["run", str(ROOT / "configs/sample_mission.yaml"), "--out", d]), 0)
            for f in ("trace.jsonl", "report.json", "report.md", "map.txt", "path.svg", "replay.html",
                      "cinema.html", "strategy_frames.txt"):
                self.assertTrue((Path(d) / f).stat().st_size > 0, f)
            rep = json.loads((Path(d) / "report.json").read_text())
            for key in ("evidence", "assessment", "recommended_next_step", "strategy_changes"):
                self.assertIn(key, rep)
            cinema = (Path(d) / "cinema.html").read_text()
            self.assertNotIn("__DATA__", cinema)
            self.assertNotIn("<script src", cinema)  # fully self-contained, works offline


if __name__ == "__main__":
    unittest.main()
