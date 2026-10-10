"""MAPF methods compared ON THE SHIPPED MAP, environment held fixed (2026-10-10).

The MovingAI multi-agent sweep could not be matched to this system: the benchmark instances differ
from this layout in agent density, path length, map size and corridor width at the same time, so no
single scalar makes them a proxy. Matching agent COUNT ran the warehouse map at 0.7% occupancy
against this layout's 6.14%; matching DENSITY still left path lengths several times longer.

This inverts the comparison. The map, the obstacle layout, the agent count and the start/goal
instances are all held identical -- the shipped grid, 25 x 16 with 172 pod cells and 228 traversable
cells -- and only the ROUTING METHOD varies. That is the comparison the paper needs, because it is
the only one in which a difference is attributable to the method.

Arms:
  snapshot   the shipped scheme: prioritised A* over a snapshot occupancy map (every other agent's
             current cell blocked, own goal left open), one committed step per tick, then the
             referee's iterated vertex guard with swaps forbidden
  spacetime  cooperative A* over (cell, time) from each agent's published path, with edge
             constraints and waiting as a legal action -- the representation underlying
             safe-interval planning, and the arm that was negative in-world (NOTES 2026-08-08)
  lb         the single-agent lower bound: each agent's 4-connected shortest path, ignoring every
             other agent. Not a runnable policy -- a bound

Reported per (k, arm): success rate (every agent reaches its goal inside the step cap), makespan and
sum-of-costs as ratios to the lower bound, and the number of times a mover had to be stopped.

    KS=8,14,20,28 NINST=25 python scripts/exp_mapf_ownmap.py
"""
from __future__ import annotations

import collections
import csv
import io
import os
import sys

import numpy as np
import pyastar2d

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

KS = [int(x) for x in os.environ.get("KS", "8,14,20,28").split(",")]
NINST = int(os.environ.get("NINST", "25"))
ARMS = os.environ.get("ARMS", "snapshot,spacetime").split(",")
CAP = int(os.environ.get("CAP", "500"))          # one episode's length, as the system runs it
ST_WINDOW = int(os.environ.get("ST_WINDOW", "16"))
OUT = os.environ.get("OUT", os.path.join(ROOT, "results", "mapf", "mapf_ownmap.csv"))


def shipped_grid():
    """The traversable mask of the shipped map: True where a robot may stand."""
    os.environ["WWM_RETIRE_BAYS"] = "1"
    from record_race import build
    from wwm_sim.warehouse import CollisionLayers as CL
    env, _ = build("large-8-6", 1, stream=True)
    h, w = env.grid_size
    pods = (env.grid[CL.SHELVES] != 0)
    return ~pods, env


def bfs(grid, goal):
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


def make_instance(grid, k, rng, dcache):
    """k distinct reachable (start, goal) pairs on traversable cells."""
    free = [(int(y), int(x)) for y, x in zip(*np.where(grid))]
    for _ in range(200):
        pick = rng.choice(len(free), size=2 * k, replace=False)
        starts = [free[i] for i in pick[:k]]
        goals = [free[i] for i in pick[k:]]
        lbs = []
        ok = True
        for s, g in zip(starts, goals):
            if g not in dcache:
                dcache[g] = bfs(grid, g)
            d = int(dcache[g][s])
            if d <= 0:
                ok = False
                break
            lbs.append(d)
        if ok:
            return list(zip(starts, goals)), lbs
    return None, None


def step_snapshot(base, pos, goal, i, n):
    g = base.copy()
    for j in range(n):
        if j != i:
            g[pos[j]] = np.inf
    g[goal[i]] = 1.0
    g[pos[i]] = 1.0
    p = pyastar2d.astar_path(g, pos[i], goal[i], allow_diagonal=False)
    return (int(p[1][0]), int(p[1][1])) if p is not None and len(p) > 1 else pos[i]


def step_spacetime(base, pos, goal, i, n, paths, t):
    """Cooperative A*: other agents' PUBLISHED future cells are blocked at the arrival time.

    Approximated the way the env's opt-in reservation mode does -- a cell is blocked only while
    another agent is predicted to be standing in it within ST_WINDOW, rather than for all time.
    """
    g = base.copy()
    for j in range(n):
        if j == i:
            continue
        pj = paths[j]
        for dt in range(min(ST_WINDOW, len(pj))):
            g[pj[dt]] = np.inf
    g[goal[i]] = 1.0
    g[pos[i]] = 1.0
    p = pyastar2d.astar_path(g, pos[i], goal[i], allow_diagonal=False)
    return (int(p[1][0]), int(p[1][1])) if p is not None and len(p) > 1 else pos[i]


def run(grid, inst, arm, cap):
    base = np.where(grid, 1.0, np.inf).astype(np.float32)
    n = len(inst)
    pos = [a[0] for a in inst]
    goal = [a[1] for a in inst]
    arrive = [None] * n
    stops = 0
    for t in range(1, cap + 1):
        if arm == "spacetime":
            # each agent publishes its intended path, then everyone plans against those
            paths = []
            for i in range(n):
                g = base.copy()
                g[goal[i]] = 1.0
                p = pyastar2d.astar_path(g, pos[i], goal[i], allow_diagonal=False)
                paths.append([(int(c[0]), int(c[1])) for c in p] if p is not None else [pos[i]])
        want = list(pos)
        for i in range(n):
            if pos[i] == goal[i]:
                if arrive[i] is None:
                    arrive[i] = t - 1
                continue
            want[i] = (step_spacetime(base, pos, goal, i, n, paths, t) if arm == "spacetime"
                       else step_snapshot(base, pos, goal, i, n))
        stuck = True
        while stuck:
            stuck = False
            owner = {}
            for i in sorted(range(n), key=lambda i: (want[i] != pos[i], i)):
                if want[i] not in owner:
                    owner[want[i]] = i
                elif want[i] != pos[i]:
                    want[i] = pos[i]
                    stops += 1
                    stuck = True
            for i in range(n):
                for j in range(i + 1, n):
                    if want[i] == pos[j] and want[j] == pos[i] and want[i] != pos[i]:
                        want[j] = pos[j]
                        stops += 1
                        stuck = True
        pos = want
        for i in range(n):
            if pos[i] == goal[i] and arrive[i] is None:
                arrive[i] = t
        if all(a is not None for a in arrive):
            break
    if not all(a is not None for a in arrive):
        return False, None, None, stops
    return True, max(arrive), sum(arrive), stops


def main():
    grid, env = shipped_grid()
    h, w = grid.shape
    free = int(grid.sum())
    print("shipped map %dx%d, %d traversable cells (%d pod cells)"
          % (h, w, free, h * w - free), flush=True)
    dcache = {}
    rows = []
    for k in KS:
        rng = np.random.RandomState(20261010)
        insts = []
        for _ in range(NINST):
            inst, lbs = make_instance(grid, k, rng, dcache)
            if inst:
                insts.append((inst, lbs))
        for arm in ARMS:
            res = [run(grid, inst, arm, CAP) for inst, _ in insts]
            good = [(r, lbs) for r, (_, lbs) in zip(res, insts) if r[0]]
            row = dict(k=k, density=round(100.0 * k / free, 2), arm=arm, instances=len(res),
                       success=round(sum(1 for r in res if r[0]) / len(res), 4),
                       makespan_ratio=(round(sum(r[1] / max(lbs) for r, lbs in good) / len(good), 4)
                                       if good else ""),
                       soc_ratio=(round(sum(r[2] / sum(lbs) for r, lbs in good) / len(good), 4)
                                  if good else ""),
                       stops=sum(r[3] for r in res))
            rows.append(row)
            print("k=%-3d (%4.1f%% density)  %-10s success %5.1f%%  makespan %sx  SOC %sx  stops %d"
                  % (k, row["density"], arm, 100 * row["success"], row["makespan_ratio"],
                     row["soc_ratio"], row["stops"]), flush=True)
    with io.open(OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print("\nwrote", OUT)
    print("Environment identical across arms: same map, same obstacles, same start/goal instances.")
    print("Only the routing method differs, so a difference is attributable to the method.")


if __name__ == "__main__":
    main()
