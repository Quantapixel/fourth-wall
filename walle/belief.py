"""Bayesian belief over EVE's location and status.

The belief is a joint grid P[status, y, x]. Every piece of evidence is kept in a log so
the posterior can be rebuilt from scratch when the interpretation of old evidence
changes (e.g. after a decoy transmitter is discovered, past signal readings that came
from that bearing are re-weighted).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .config import STATUSES
from .env import BEACON, DECOY_PULSE_JITTER, EVE_PULSE_JITTER, FALLOFF, MIN_DETECTABLE
from .world import Cell

STATUS_PRIOR = np.array([0.35, 0.40, 0.25])  # active, dormant, damaged
POWER = np.array([BEACON[s]["power"] for s in STATUSES])
DETECT = np.array([BEACON[s]["detect_prob"] for s in STATUSES])
DECOY_POWER_RANGE = (1.1, 1.5)
FLOOR = 1e-3


def _gauss(x, mu, sigma):
    return np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi))


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


class Belief:
    def __init__(self, briefing: dict[str, Any]):
        self.W, self.H = briefing["width"], briefing["height"]
        self.sensors = briefing["sensors"]
        self.mask = np.array([[ch != "#" for ch in row] for row in briefing["map"]], dtype=float)
        self.ys, self.xs = np.mgrid[0 : self.H, 0 : self.W]
        self.evidence: list[dict[str, Any]] = []
        self.known_decoys: list[Cell] = []
        self.eve_fix: dict[str, Any] | None = None
        self.P = np.zeros((3, self.H, self.W))

        sig = briefing["initial_signal"]
        if sig.get("bearing_deg") is not None:
            det = {k: sig[k] for k in ("bearing_deg", "strength", "pulse_interval_ms") if sig.get(k) is not None}
            det.setdefault("strength", None)
            self.evidence.append({"kind": "signal", "pos": tuple(briefing["start"]), "detections": [det],
                                  "initial": True})
        if sig.get("coordinates"):
            self.evidence.append({"kind": "fix", "pos": tuple(sig["coordinates"]),
                                  "sigma": float(sig.get("uncertainty") or 6.0)})
        self.recompute()

    # --- geometry helpers ----------------------------------------------
    def _dist(self, p: Cell) -> np.ndarray:
        return np.hypot(self.xs - p[0], self.ys - p[1])

    def _bearing(self, p: Cell) -> np.ndarray:
        return np.degrees(np.arctan2(self.xs - p[0], -(self.ys - p[1]))) % 360.0

    # --- likelihood models ---------------------------------------------
    def _bearing_lik(self, p: Cell, observed: float, sigma: float) -> np.ndarray:
        d = self._dist(p)
        lik = 0.95 * _gauss(_wrap(observed - self._bearing(p)), 0.0, sigma) + 0.05 / 360.0
        return np.where(d < 1.0, 1.0 / 360.0, lik)

    def _decoy_density(self, p: Cell, det: dict[str, Any]) -> float:
        """Density of a detection under 'this came from a decoy'."""
        s_lo, s_hi = 0.0, DECOY_POWER_RANGE[1]
        dens = (1.0 / 360.0) * (1.0 / (s_hi - s_lo))  # decoy somewhere unknown
        sig = self.sensors["bearing_noise_deg"]
        for k in self.known_decoys:
            d = math.hypot(k[0] - p[0], k[1] - p[1])
            brg = math.degrees(math.atan2(k[0] - p[0], -(k[1] - p[1]))) % 360.0
            b = float(_gauss(_wrap(det["bearing_deg"] - brg), 0.0, sig))
            if det.get("strength") is not None:
                mid = sum(DECOY_POWER_RANGE) / 2 / (1 + (d / FALLOFF) ** 2)
                b *= float(_gauss(det["strength"], mid, 0.1 * mid + self.sensors["strength_noise"] + 0.02))
            else:
                b /= s_hi
            dens += 20.0 * b  # a known nearby transmitter dominates the unknown-decoy term
        return dens

    def _pulse_ratio(self, det: dict[str, Any]) -> float:
        pi = det.get("pulse_interval_ms")
        if pi is None:
            return 1.0
        return float(_gauss(pi, 1000.0, EVE_PULSE_JITTER) / _gauss(pi, 1000.0, DECOY_PULSE_JITTER))

    def _signal_terms(self, p: Cell, detections: list[dict[str, Any]]):
        """Returns (pdet[3,H,W], per-detection EVE-likelihood ratios [n,3,H,W])."""
        d = self._dist(p)
        exp_s = POWER[:, None, None] / (1.0 + (d[None] / FALLOFF) ** 2)
        in_range = (exp_s >= MIN_DETECTABLE) & (d[None] <= self.sensors["signal_range"])
        pdet = np.where(in_range, DETECT[:, None, None], 0.0)
        noise = self.sensors["strength_noise"]
        terms = []
        for det in detections:
            lb = self._bearing_lik(p, det["bearing_deg"], self.sensors["bearing_noise_deg"])
            if det.get("strength") is not None:
                sigma = np.sqrt(noise**2 + (0.15 * exp_s) ** 2)
                ls = _gauss(det["strength"], exp_s, sigma)
            else:
                ls = np.ones_like(exp_s)
            ratio = self._pulse_ratio(det) / self._decoy_density(p, det)
            terms.append(lb[None] * ls * ratio)
        return pdet, terms

    def _lik(self, ev: dict[str, Any]) -> np.ndarray:
        k = ev["kind"]
        if k == "signal":
            pdet, terms = self._signal_terms(ev["pos"], ev["detections"])
            lik = 1.0 - pdet
            for t in terms:
                lik = lik + pdet * t
            return lik
        if k == "scan":
            within = self._dist(ev["pos"]) <= ev["radius"]
            return np.broadcast_to(np.where(within, 1.0 - self.sensors["scan_detect_prob"], 1.0), self.P.shape)
        if k == "fix":
            g = np.exp(-0.5 * (self._dist(ev["pos"]) / ev["sigma"]) ** 2)
            return np.broadcast_to(0.05 + g, self.P.shape)
        if k == "clue":
            return self._clue_lik(ev["clue"])
        raise ValueError(k)

    def _clue_lik(self, clue: dict[str, Any]) -> np.ndarray:
        q, t = tuple(clue["position"]), clue["type"]
        d = self._dist(q)
        out = np.ones(self.P.shape)
        if t == "hover_tracks":
            diff = _wrap(clue["heading_deg"] - self._bearing(q))
            lik = 0.08 + np.exp(-0.5 * (diff / 15.0) ** 2) * np.where((d >= 1) & (d <= 13), 1.0, 0.3)
            out[:] = lik
        elif t == "debris":
            if clue.get("freshness") == "fresh":
                out[:] = 0.05
                out[2] = np.where(d <= 5, 1.0, 0.05)
        elif t == "plant_residue":
            near = np.where(d <= 3.5, 1.0, 0.05)
            out[0], out[1], out[2] = near, near, 0.05
        elif t == "memory_chip":
            quad = clue["quadrant"]
            ns = self.ys < self.H / 2 if quad[0] == "N" else self.ys >= self.H / 2
            ew = self.xs < self.W / 2 if quad[1] == "W" else self.xs >= self.W / 2
            out[:] = np.where(ns & ew, 0.85, 0.05)
        return out

    # --- updates ---------------------------------------------------------
    def _normalize(self) -> None:
        self.P *= self.mask[None]
        self.P = np.maximum(self.P, FLOOR * 1e-6) * self.mask[None]
        self.P /= self.P.sum()

    def recompute(self) -> None:
        if self.eve_fix:
            self._apply_fix()
            return
        logp = np.log(STATUS_PRIOR)[:, None, None] + np.zeros((3, self.H, self.W))
        for ev in self.evidence:
            logp += np.log(np.maximum(self._lik(ev), FLOOR * 1e-3))
        logp -= logp.max()
        self.P = np.exp(logp)
        self._normalize()

    def _update(self, ev: dict[str, Any]) -> None:
        self.evidence.append(ev)
        if self.eve_fix:
            return
        self.P = self.P * np.maximum(self._lik(ev), FLOOR * 1e-3)
        self._normalize()

    def add_signal(self, pos: Cell, detections: list[dict[str, Any]]) -> list[float]:
        """Update on a signal scan. Returns P(detection i is EVE) for each detection."""
        probs = self.detection_eve_probs(pos, detections)
        self._update({"kind": "signal", "pos": tuple(pos), "detections": detections})
        return probs

    def detection_eve_probs(self, pos: Cell, detections: list[dict[str, Any]]) -> list[float]:
        if not detections:
            return []
        pdet, terms = self._signal_terms(tuple(pos), detections)
        w0 = float((self.P * (1.0 - pdet)).sum())
        ws = [float((self.P * pdet * t).sum()) for t in terms]
        z = w0 + sum(ws)
        return [w / z for w in ws] if z > 0 else [0.0] * len(ws)

    def add_scan(self, pos: Cell, radius: float) -> None:
        self._update({"kind": "scan", "pos": tuple(pos), "radius": radius})

    def add_clue(self, clue: dict[str, Any]) -> None:
        self._update({"kind": "clue", "clue": clue})

    def add_decoy(self, pos: Cell) -> int:
        """Register a decoy transmitter and rebuild the posterior. Returns readings re-weighted."""
        pos = tuple(pos)
        if pos in self.known_decoys:
            return 0
        self.known_decoys.append(pos)
        self.recompute()
        return sum(len(e["detections"]) for e in self.evidence if e["kind"] == "signal")

    def set_found(self, pos: Cell, status: str) -> None:
        self.eve_fix = {"position": tuple(pos), "status": status}
        self._apply_fix()

    def _apply_fix(self) -> None:
        self.P = np.zeros((3, self.H, self.W))
        x, y = self.eve_fix["position"]
        self.P[STATUSES.index(self.eve_fix["status"]), y, x] = 1.0

    # --- summaries -------------------------------------------------------
    def location(self) -> np.ndarray:
        return self.P.sum(axis=0)

    def status(self) -> dict[str, float]:
        s = self.P.sum(axis=(1, 2))
        return {name: round(float(v), 4) for name, v in zip(STATUSES, s)}

    def map_cell(self) -> tuple[Cell, float]:
        loc = self.location()
        y, x = np.unravel_index(int(np.argmax(loc)), loc.shape)
        return (int(x), int(y)), float(loc[y, x])

    def mass_within(self, radius: float) -> np.ndarray:
        """For every cell c, posterior mass of EVE being within `radius` of c."""
        loc = self.location()
        r = int(math.floor(radius))
        pad = np.pad(loc, r)
        out = np.zeros_like(loc)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= radius * radius:
                    out += pad[r + dy : r + dy + self.H, r + dx : r + dx + self.W]
        return out

    def expected_cell(self) -> tuple[float, float]:
        loc = self.location()
        return float((loc * self.xs).sum()), float((loc * self.ys).sum())

    def entropy_bits(self) -> float:
        p = self.location().ravel()
        p = p[p > 0]
        return float(-(p * np.log2(p)).sum())

    def credible_cells(self, level: float = 0.9) -> int:
        p = np.sort(self.location().ravel())[::-1]
        return int(np.searchsorted(np.cumsum(p), level) + 1)

    def summary(self, top: int = 3) -> dict[str, Any]:
        loc = self.location()
        flat = np.argsort(loc.ravel())[::-1][:top]
        cells = [((int(i % self.W), int(i // self.W)), round(float(loc.ravel()[i]), 4)) for i in flat]
        (mx, my), mp = self.map_cell()
        return {
            "map_cell": [mx, my],
            "map_prob": round(mp, 4),
            "mass_r2_at_map": round(float(self.mass_within(2)[my, mx]), 4),
            "top_cells": [[list(c), p] for c, p in cells],
            "entropy_bits": round(self.entropy_bits(), 3),
            "cells_90": self.credible_cells(0.9),
            "status": self.status(),
            "known_decoys": [list(d) for d in self.known_decoys],
        }
