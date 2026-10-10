"""Multi-agent MAPF benchmark on the MovingAI instances (2026-10-10).

The existing MovingAI check (exp_m5_mapf.py) runs the planner on ONE agent at a time, so it
validates single-agent pathfinding on MAPF maps and says nothing about conflict resolution. This
runs the standard multi-agent protocol: take the first k rows of a scenario file as k simultaneous
agents and require every one of them to reach its goal without collisions.

WHAT IS BEING EVALUATED. The shipped router is not an offline MAPF solver -- it replans reactively
every step -- so it is evaluated the way an online/lifelong MAPF executor is, not the way CBS or
EECBS are. Reported per (map, k):

    success      fraction of instances where all k agents reached their goals inside the step cap
    makespan     steps until the last agent arrives, as a ratio to the lower bound
                 (max over agents of the single-agent 4-connected shortest distance)
    SOC          sum of per-agent arrival times, as a ratio to the lower bound
                 (sum of those distances)
    collisions   vertex + swap collisions actually observed

NOT COMPARABLE to CBS/EECBS on solution quality: those solve offline with completeness and
bounded-suboptimality guarantees, this replans online with neither. The comparable axes are
success rate and scalability.

FIDELITY. The harness reproduces the shipped routing SCHEME on a bare grid -- prioritised A* over a
snapshot occupancy map (every other agent's current cell blocked, own goal left open, which is
`find_path(care_for_agents=True)`), one committed step per tick, then the referee's conflict
resolution: non-moving agents hold their cells, moving agents that would collide are stopped, and
the pass is iterated to a fixed point, with swaps forbidden. It is NOT the warehouse environment:
pickers, shelves, highways, stations, battery and the clash-simulation layer are all absent, and
the map is MovingAI's rather than ours. The claim it supports is about the routing scheme, not
about the shipped system as a whole.

    MAPS=warehouse-10-20-10-2-1 KS=10,20,40,60 NSCEN=25 python scripts/exp_mapf_multi.py
"""
from __future__ import annotations

import collections
import csv
import io
import glob
import os
import sys

import numpy as np
import pyastar2d

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "mapf")

MAPS = os.environ.get("MAPS", "warehouse-10-20-10-2-1").split(",")
KS = [int(x) for x in os.environ.get("KS", "10,20,40,60,80,100").split(",")]
NSCEN = int(os.environ.get("NSCEN", "25"))
CAP_MULT = float(os.environ.get("CAP_MULT", "4.0"))   # step cap = CAP_MULT x makespan lower bound
CAP_FLOOR = int(os.environ.get("CAP_FLOOR", "200"))
OUT = os.environ.get("OUT", os.path.join(ROOT, "results", "mapf_multi.csv"))


def load_map(name):
    """MovingAI .map -> bool array, True = passable. Rows are y, columns are x."""
    lines = io.open(os.path.join(DATA, name + ".map"), encoding="utf-8").read().splitlines()
    h = int(next(l for l in lines if l.startswith("height")).split()[1])
    w = int(next(l for l in lines if l.startswith("width")).split()[1])
    body = lines[lines.index("map") + 1:]
    grid = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for x, ch in enumerate(body[y][:w]):
            grid[y, x] = ch in ".G"          # passable terrain in the MovingAI encoding
    return grid


def load_scen(path):
    """-> [((sy,sx),(gy,gx)), ...] in file order. Scenario columns are x then y."""
    out = []
    for line in io.open(path, encoding="utf-8").read().splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 9:
            continue
        sx, sy, gx, gy = int(f[4]), int(f[5]), int(f[6]), int(f[7])
        out.append(((sy, sx), (gy, gx)))
    return out


def bfs_dist(grid, goal):
    """4-connected distance to `goal` from every cell. The single-agent optimum, and the bound."""
    h, w = grid.shape
    d = np.full((h, w), -1, dtype=np.int32)
    d[goal] = 0
    q = collections.deque([goal])
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and grid[ny, nx] and d[ny, nx] < 0:
                d[ny, nx] = d[y, x] + 1
                q.append((ny, nx))
    return d


def plan(base, pos, goal, others):
    """One agent's next cell: A* over the snapshot occupancy map, as find_path does.

    `base` is the static cost grid (1 passable, inf blocked). Other agents' CURRENT cells are
    blocked; the agent's own goal is left open so a robot idling near it cannot seal it.
    """
    g = base.copy()
    for o in others:
        g[o] = np.inf
    g[goal] = 1.0
    g[pos] = 1.0
    path = pyastar2d.astar_path(g, pos, goal, allow_diagonal=False)
    if path is None or len(path) < 2:
        return None
    return (int(path[1][0]), int(path[1][1]))


def run_instance(grid, agents, cap):
    """Online execution. Returns (solved, makespan, soc, vertex_coll, swap_coll)."""
    base = np.where(grid, 1.0, np.inf).astype(np.float32)
    pos = [a[0] for a in agents]
    goal = [a[1] for a in agents]
    arrive = [None] * len(agents)
    vc = sc = 0
    for t in range(1, cap + 1):
        want = list(pos)
        for i in range(len(agents)):
            if pos[i] == goal[i]:
                if arrive[i] is None:
                    arrive[i] = t - 1
                continue
            others = [pos[j] for j in range(len(agents)) if j != i]
            nxt = plan(base, pos[i], goal[i], others)
            want[i] = nxt if nxt is not None else pos[i]

        # REFEREE. Agents that are not moving hold their cells first; a mover whose target is
        # already claimed is stopped. Iterated to a fixed point, exactly as the env's final
        # vertex guard does, and swaps are forbidden.
        stuck = True
        while stuck:
            stuck = False
            owner = {}
            order = sorted(range(len(agents)), key=lambda i: (want[i] != pos[i], i))
            for i in order:
                k = want[i]
                if k not in owner:
                    owner[k] = i
                elif want[i] != pos[i]:
                    want[i] = pos[i]
                    vc += 1
                    stuck = True
            for i in range(len(agents)):
                for j in range(i + 1, len(agents)):
                    if want[i] == pos[j] and want[j] == pos[i] and want[i] != pos[i]:
                        want[j] = pos[j]
                        sc += 1
                        stuck = True
        pos = want
        for i in range(len(agents)):
            if pos[i] == goal[i] and arrive[i] is None:
                arrive[i] = t
        if all(a is not None for a in arrive):
            break
    solved = all(a is not None for a in arrive)
    if not solved:
        return False, None, None, vc, sc
    return True, max(arrive), sum(arrive), vc, sc


def main():
    rows = []
    for mp in MAPS:
        grid = load_map(mp)
        scens = sorted(glob.glob(os.path.join(DATA, "scen-even", mp + "-even-*.scen")))[:NSCEN]
        dist_cache = {}
        for k in KS:
            agg = []
            for sp in scens:
                ag = load_scen(sp)[:k]
                if len(ag) < k:
                    continue
                lbs = []
                ok = True
                for s, g in ag:
                    if g not in dist_cache:
                        dist_cache[g] = bfs_dist(grid, g)
                    d = int(dist_cache[g][s])
                    if d < 0:
                        ok = False
                        break
                    lbs.append(d)
                if not ok:
                    continue
                cap = max(CAP_FLOOR, int(CAP_MULT * max(lbs)))
                solved, mk, soc, vc, sc = run_instance(grid, ag, cap)
                agg.append((solved, mk, soc, sum(lbs), max(lbs), vc, sc))
            if not agg:
                continue
            n = len(agg)
            good = [a for a in agg if a[0]]
            row = dict(map=mp, k=k, instances=n,
                       success=round(len(good) / n, 4),
                       makespan_ratio=(round(sum(a[1] / a[4] for a in good) / len(good), 4)
                                       if good else ""),
                       soc_ratio=(round(sum(a[2] / a[3] for a in good) / len(good), 4)
                                  if good else ""),
                       vertex_stops=sum(a[5] for a in agg),
                       swap_stops=sum(a[6] for a in agg))
            rows.append(row)
            print("%-26s k=%-4d n=%-3d success %5.1f%%  makespan %sx  SOC %sx  stops %d/%d"
                  % (mp, k, n, 100 * row["success"], row["makespan_ratio"], row["soc_ratio"],
                     row["vertex_stops"], row["swap_stops"]), flush=True)
    with io.open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nwrote", OUT)
    print("NOTE: makespan/SOC ratios are over SOLVED instances only, against single-agent")
    print("      4-connected lower bounds. Not comparable to offline optimal solvers.")


if __name__ == "__main__":
    main()
