"""wwm_sim.routing — Part A route generator (Yen's k-shortest-paths) + cheap screen.

Part A steps 2-3 of the doc: cheaply SCREEN the task list, then GET DIRECTIONS
(3-5 real routes) only for the finalists — the expensive step, run after the screen.

Map model: in this sim AGVs traverse an OPEN grid (racks/shelves do not block AGVs;
only other robots do, dynamically). So the static route graph is the full 4-connected
grid. Yen's then yields alternative SHORTEST-length routes that differ in SHAPE — which
is what later matters for the collision / congestion / rumor filters (step 4).

Yen's algorithm = networkx.shortest_simple_paths (paths in increasing length order).
"""
from __future__ import annotations

from itertools import islice

import networkx as nx

_GRAPH_CACHE = {}


def build_agv_graph(env):
    """4-connected grid graph of all cells (AGVs traverse the open grid). Cached per size.
    Nodes are (x, y) tuples."""
    key = tuple(env.grid_size)
    G = _GRAPH_CACHE.get(key)
    if G is None:
        h, w = env.grid_size            # grid_size = (rows=H, cols=W)
        G = nx.grid_2d_graph(w, h)      # nodes (x, y), 4-connected, unit edges
        _GRAPH_CACHE[key] = G
    return G


def build_picker_graph(env):
    """4-connected graph over HIGHWAY cells (pickers may only travel the aisles), with each
    shelf/target cell connected to its adjacent highway cells (a picker steps onto a shelf
    from the aisle to rendezvous). Cached per size. Nodes are (x, y)."""
    key = ("picker", tuple(env.grid_size))
    G = _GRAPH_CACHE.get(key)
    if G is None:
        h, w = env.grid_size
        hw = env.highways                       # [y, x], 1 = highway
        G = nx.Graph()
        for y in range(h):
            for x in range(w):
                if hw[y, x]:
                    G.add_node((x, y))
        for (x, y) in list(G.nodes):            # highway<->highway edges
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx_, ny_ = x + dx, y + dy
                if 0 <= nx_ < w and 0 <= ny_ < h and hw[ny_, nx_]:
                    G.add_edge((x, y), (nx_, ny_))
        for (yy, xx) in env.action_id_to_coords_map.values():   # shelf targets <-> adjacent aisle
            if hw[yy, xx]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                aX, aY = xx + dx, yy + dy
                if 0 <= aX < w and 0 <= aY < h and hw[aY, aX]:
                    G.add_edge((xx, yy), (aX, aY))
        _GRAPH_CACHE[key] = G
    return G


def k_shortest_routes(graph, start, goal, k=3):
    """Up to `k` shortest loopless routes from start to goal (each a list of (x,y)).
    Yen's algorithm via networkx.shortest_simple_paths. [] if unreachable."""
    if start == goal:
        return [[start]]
    try:
        return list(islice(nx.shortest_simple_paths(graph, start, goal), k))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


def cheap_screen(robot, shelves, task_value_fn, keep=15, dist_discount=0.15):
    """Part A step 2 — the cheap screen. Score each candidate task by a CHEAP version of
    the same value-AND-cost traded off later: value − dist_discount × Manhattan(robot→shelf).
    Returns the top `keep` shelves (highest score first). Screening by value alone keeps
    far shiny tasks; by distance alone keeps nearby junk — so the screen must use both."""
    scored = []
    for s in shelves:
        val = task_value_fn(s)
        d = manhattan(robot.x, robot.y, s.x, s.y)
        scored.append((val - dist_discount * d, s))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in scored[:keep]]
