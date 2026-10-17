"""Terrain grid, procedural map generation and path planning."""
from __future__ import annotations

import heapq
import math
import random
from collections import deque
from typing import Iterable

Cell = tuple[int, int]

OPEN, WALL, RUBBLE = ".", "#", "~"
DIRS: dict[str, Cell] = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def bearing_deg(src: Cell | tuple[float, float], dst: Cell | tuple[float, float]) -> float:
    """Compass bearing from src to dst: 0 = North (up, -y), clockwise."""
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def angle_diff(a: float, b: float) -> float:
    """Signed smallest difference a - b in degrees, in (-180, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def dist(a: Cell, b: Cell) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Grid:
    def __init__(self, rows: list[str], chargers: Iterable[Cell], move_cost: int = 1, rubble_cost: int = 3):
        self.rows = [list(r) for r in rows]
        self.height = len(rows)
        self.width = len(rows[0])
        self.chargers = sorted(set(chargers))
        self.move_cost = move_cost
        self.rubble_cost = rubble_cost

    # --- basic queries -------------------------------------------------
    def in_bounds(self, c: Cell) -> bool:
        return 0 <= c[0] < self.width and 0 <= c[1] < self.height

    def terrain(self, c: Cell) -> str:
        return self.rows[c[1]][c[0]]

    def passable(self, c: Cell) -> bool:
        return self.in_bounds(c) and self.terrain(c) != WALL

    def enter_cost(self, c: Cell) -> int:
        """Battery cost of moving *into* cell c."""
        return self.rubble_cost if self.terrain(c) == RUBBLE else self.move_cost

    def neighbors(self, c: Cell) -> Iterable[tuple[str, Cell]]:
        for name, (dx, dy) in DIRS.items():
            n = (c[0] + dx, c[1] + dy)
            if self.passable(n):
                yield name, n

    def cells(self) -> Iterable[Cell]:
        for y in range(self.height):
            for x in range(self.width):
                if self.passable((x, y)):
                    yield (x, y)

    # --- path planning -------------------------------------------------
    def dijkstra(self, src: Cell) -> dict[Cell, int]:
        """Battery cost from src to every reachable cell."""
        best = {src: 0}
        pq = [(0, src)]
        while pq:
            d, c = heapq.heappop(pq)
            if d > best[c]:
                continue
            for _, n in self.neighbors(c):
                nd = d + self.enter_cost(n)
                if nd < best.get(n, 1 << 30):
                    best[n] = nd
                    heapq.heappush(pq, (nd, n))
        return best

    def cost_to_targets(self, targets: Iterable[Cell]) -> dict[Cell, int]:
        """Battery cost from every cell to the nearest of `targets` (reverse Dijkstra)."""
        best: dict[Cell, int] = {}
        pq = []
        for t in targets:
            best[t] = 0
            pq.append((0, t))
        heapq.heapify(pq)
        while pq:
            d, c = heapq.heappop(pq)
            if d > best[c]:
                continue
            step = self.enter_cost(c)  # cost paid when a neighbor steps into c
            for _, n in self.neighbors(c):
                nd = d + step
                if nd < best.get(n, 1 << 30):
                    best[n] = nd
                    heapq.heappush(pq, (nd, n))
        return best

    def astar(self, src: Cell, dst: Cell) -> list[Cell] | None:
        """Cheapest path src -> dst (inclusive), or None if unreachable."""
        if src == dst:
            return [src]
        if not self.passable(dst):
            return None
        h = lambda c: (abs(c[0] - dst[0]) + abs(c[1] - dst[1])) * self.move_cost
        g = {src: 0}
        parent: dict[Cell, Cell] = {}
        pq = [(h(src), 0, src)]
        while pq:
            _, d, c = heapq.heappop(pq)
            if c == dst:
                path = [c]
                while c in parent:
                    c = parent[c]
                    path.append(c)
                return path[::-1]
            if d > g[c]:
                continue
            for _, n in self.neighbors(c):
                nd = d + self.enter_cost(n)
                if nd < g.get(n, 1 << 30):
                    g[n] = nd
                    parent[n] = c
                    heapq.heappush(pq, (nd + h(n), nd, n))
        return None

    def path_cost(self, path: list[Cell]) -> int:
        return sum(self.enter_cost(c) for c in path[1:])

    def step_dir(self, a: Cell, b: Cell) -> str:
        delta = (b[0] - a[0], b[1] - a[1])
        for name, d in DIRS.items():
            if d == delta:
                return name
        raise ValueError(f"{a} -> {b} is not a single step")

    def render(self) -> list[str]:
        out = []
        for y, row in enumerate(self.rows):
            line = list(row)
            for cx, cy in self.chargers:
                if cy == y:
                    line[cx] = "C"
            out.append("".join(line))
        return out


def _reachable(rows: list[list[str]], start: Cell) -> set[Cell]:
    h, w = len(rows), len(rows[0])
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS.values():
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in seen and rows[n[1]][n[0]] != WALL:
                seen.add(n)
                q.append(n)
    return seen


def parse_grid(grid: list[str]) -> tuple[list[str], list[Cell], Cell | None, Cell | None]:
    """Parse an explicit ASCII map. Returns (terrain rows, chargers, start, eve)."""
    rows, chargers, start, eve = [], [], None, None
    for y, line in enumerate(grid):
        row = []
        for x, ch in enumerate(line):
            if ch == "C":
                chargers.append((x, y))
            elif ch == "S":
                start = (x, y)
            elif ch == "E":
                eve = (x, y)
            row.append(ch if ch in (WALL, RUBBLE) else OPEN)
        rows.append("".join(row))
    return rows, chargers, start, eve


def generate_terrain(
    width: int, height: int, obstacle_density: float, rubble_density: float, rng: random.Random, start: Cell
) -> list[str]:
    """Random terrain with wall clusters (trash piles) and rubble, fully connected from start."""
    rows = [[OPEN] * width for _ in range(height)]
    # Grow walls as small clusters so the map has corridors rather than salt-and-pepper noise.
    target_walls = int(width * height * obstacle_density)
    placed = 0
    while placed < target_walls:
        x, y = rng.randrange(width), rng.randrange(height)
        for _ in range(rng.randint(2, 6)):
            if 0 <= x < width and 0 <= y < height and rows[y][x] == OPEN and (x, y) != start:
                rows[y][x] = WALL
                placed += 1
            dx, dy = rng.choice(list(DIRS.values()))
            x, y = x + dx, y + dy
    for _ in range(int(width * height * rubble_density)):
        x, y = rng.randrange(width), rng.randrange(height)
        if rows[y][x] == OPEN and (x, y) != start:
            rows[y][x] = RUBBLE
    # Wall off pockets that are unreachable from the start.
    reach = _reachable(rows, start)
    for y in range(height):
        for x in range(width):
            if rows[y][x] != WALL and (x, y) not in reach:
                rows[y][x] = WALL
    return ["".join(r) for r in rows]
