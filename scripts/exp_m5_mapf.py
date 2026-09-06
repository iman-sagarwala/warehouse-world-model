"""M5: MovingAI MAPF inner-loop sanity check (plumbing validation, target >=98% solved).

Runs OUR path planner (pyastar2d, the same call the warehouse env makes in find_path) on the
standard MovingAI benchmark maps + scenario files, including the warehouse map that matches our
domain. Two checks:
  SOLVED    a path is returned for a scenario whose start/goal are both traversable
  OPTIMAL   the path length equals the 4-connected shortest path (BFS ground truth computed here)
MovingAI's own `optimal_length` column is 8-connected octile, so it is reported for reference but
NOT used as the bar -- our planner is 4-connected by construction (no diagonal moves in the
warehouse).

Data: data/mapf/ (maps + scen-even scenarios from movingai.com/benchmarks/mapf).
"""
import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pyastar2d

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "mapf")
MAPS = ["warehouse-10-20-10-2-1", "random-32-32-20", "empty-32-32"]
PER_MAP = int(os.environ.get("PER_MAP", "400"))     # scenario rows per map


def load_map(name):
    lines = open(os.path.join(DATA, name + ".map")).read().splitlines()
    h = int(lines[1].split()[1])
    w = int(lines[2].split()[1])
    grid = np.ones((h, w), dtype=np.float32)         # 1 = traversable cost
    for y in range(h):
        row = lines[4 + y]
        for x in range(w):
            if row[x] not in ".G":                   # T/@/O/S/W = blocked
                grid[y, x] = np.inf
    return grid


def load_scen(name):
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, "scen-even", name + "-even-*.scen"))):
        for ln in open(f).read().splitlines()[1:]:
            p = ln.split("\t")
            if len(p) < 9:
                continue
            # columns: bucket map w h sx sy gx gy optimal
            out.append((int(p[4]), int(p[5]), int(p[6]), int(p[7]), float(p[8])))
    return out


def bfs_len(grid, s, g):
    """4-connected shortest path length (ground truth for our non-diagonal planner)."""
    h, w = grid.shape
    if s == g:
        return 0
    seen = {s}
    q = collections.deque([(s, 0)])
    while q:
        (y, x), d = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and grid[ny, nx] == 1.0 and (ny, nx) not in seen:
                if (ny, nx) == g:
                    return d + 1
                seen.add((ny, nx))
                q.append(((ny, nx), d + 1))
    return None


if __name__ == "__main__":
    print("MovingAI MAPF inner-loop sanity: our planner on the standard benchmarks\n")
    print("%-26s %8s %9s %9s %10s %s"
          % ("map", "cases", "solved", "optimal", "unreachable", "note"))
    tot_c = tot_s = tot_o = 0
    for name in MAPS:
        grid = load_map(name)
        scen = load_scen(name)[:PER_MAP]
        solved = optimal = unreachable = cases = 0
        for sx, sy, gx, gy, _opt in scen:
            s, g = (sy, sx), (gy, gx)                # scen files are (col,row) = (x,y)
            if grid[s] != 1.0 or grid[g] != 1.0:
                continue                             # not a planner failure: blocked endpoint
            truth = bfs_len(grid, s, g)
            if truth is None:
                unreachable += 1
                continue
            cases += 1
            path = pyastar2d.astar_path(grid, s, g, allow_diagonal=False)
            if path is not None and len(path) > 0:
                solved += 1
                if len(path) - 1 == truth:
                    optimal += 1
        tot_c += cases
        tot_s += solved
        tot_o += optimal
        print("%-26s %8d %8.1f%% %8.1f%% %10d %s"
              % (name, cases, 100.0 * solved / max(1, cases), 100.0 * optimal / max(1, cases),
                 unreachable, "<- our domain" if name.startswith("warehouse") else ""))
    print("\nTOTAL %d cases: solved %.2f%%  optimal %.2f%%" %
          (tot_c, 100.0 * tot_s / max(1, tot_c), 100.0 * tot_o / max(1, tot_c)))
    print("BAR: >=98%% solved -> %s" % ("PASS" if tot_s / max(1, tot_c) >= 0.98 else "FAIL"))
