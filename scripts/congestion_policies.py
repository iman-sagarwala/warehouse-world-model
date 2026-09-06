"""Congestion-forecast policies built on the Part A / Rush controllers.

RushYenController        - Rush's task/robot selection UNCHANGED, but after the robot->task pair is
                           locked it picks a Yen route and drives it (adherence). Tests whether
                           route-awareness alone helps Rush.
PartACongestionController - Part A, but routes are chosen to DODGE a congestion FORECAST:
    The forecast (a per-cell traffic grid) is built each step from three sources, then robots are
    assigned one-at-a-time (prioritized), each avoiding what's stamped so far:
      1. KNOWN     : busy robots' remaining paths.
      2. FINISHING : busy robots about to finish -> predict their NEXT task (same cheap-screen
                     scoring) and route from where they'll finish. This is the future-aware part:
                     robots free up one at a time, so we predict who's about to move next.
      3. FRESH     : each free robot's committed route is stamped as it commits (prioritized).
    Route selection (Piece A): among the k Yen routes, pick the one minimising length + LAMBDA*
    congestion-it-crosses. Reroute (Piece C): the env's find_path adds the same forecast to cell
    costs (env.congestion_grid/weight), so detours also dodge predicted traffic. Adherence drives
    the chosen route.
"""
from __future__ import annotations

import math
import pickle

import numpy as np

from wwm_sim import rollout as _ro
from wwm_sim import routing as _rt
from wwm_sim.values import task_value
from sim_priority import PartAController, RushValueController
from sim_dashboard import Mission, MissionType


class _Pt:
    """Minimal robot-like point for cheap_screen (needs .x/.y)."""
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


def _clear_fetch_cells(ctrl):
    """Drop committed cells once an AGV leaves the fetch leg (carrying / unassigned)."""
    for a in ctrl.agvs:
        if getattr(a, "committed_cells", None) and (a.carrying_shelf or a not in ctrl.assigned_agvs):
            a.committed_cells = None


class RushYenController(RushValueController):
    """Rush selection + Yen route for the chosen pair, driven via adherence."""

    def __init__(self, env):
        super().__init__(env)
        env.prefer_committed = True

    def _assign_tasks(self):
        env = self.env
        G = _rt.build_agv_graph(env)
        _clear_fetch_cells(self)
        for item in self._task_order():
            if item.id in self.assigned_items.values():
                continue
            available = [a for a in self.agvs if not a.busy and not a.carrying_shelf
                         and a not in self.assigned_agvs]
            if not available:
                continue
            paths = [env.find_path((a.y, a.x), (item.y, item.x), a, care_for_agents=False)
                     for a in available]
            closest = available[int(np.argmin([len(p) for p in paths]))]
            loc_id = self.coords_to_id[(item.y, item.x)]
            self.assigned_agvs[closest] = Mission(MissionType.PICKING, loc_id, item.x, item.y,
                                                  self.timestep)
            self.assigned_items[closest] = item.id
            routes = _rt.k_shortest_routes(G, (closest.x, closest.y), (item.x, item.y), k=3)
            if routes:
                r = min(routes, key=len)
                closest.committed_cells = {(cy, cx) for (cx, cy) in r}


class PartACongestionController(PartAController):
    """Part A with a congestion forecast steering route selection AND reroutes."""

    CONG_LAMBDA = 0.3      # weight of forecast congestion in the controller's route ranking
    CONG_WEIGHT = 0.3      # weight of forecast congestion in the env's find_path (reroute/adhere)
    FINISH_HORIZON = 40    # a busy robot within this many steps of its target counts as "finishing"
    FUTURE_WEIGHT = 0.5    # predicted (uncertain) routes stamped lighter than known ones

    def __init__(self, env):
        super().__init__(env)
        env.prefer_committed = True
        env.congestion_weight = self.CONG_WEIGHT
        env.disturb_drop_adherence = True    # DEFAULT ON: a disturbance on the committed route
        self._cong = None                    # releases adherence -> shortest detour (Pareto win, 100 seeds)

    # --- forecast construction -------------------------------------------------
    def _pre_dispatch(self, free_agvs, G):
        env = self.env
        H, W = env.grid_size
        cong = np.zeros((H, W), dtype=np.float32)
        taken = set(self.assigned_items.values())

        def stamp(cells, w):
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w

        for a in self.agvs:
            path = getattr(a, "path", None)
            if a.busy and path:
                stamp(path, 1.0)                                   # 1. KNOWN remaining path
                if len(path) <= self.FINISH_HORIZON:              # 2. FINISHING -> predict next
                    finish = path[-1]                             # where it's headed / will free up
                    nt = self._predict_next(finish, taken)
                    if nt is not None:
                        taken.add(nt.id)
                        r = self._shortest(G, finish, (nt.x, nt.y))
                        stamp(r, self.FUTURE_WEIGHT)
        self._cong = cong
        env.congestion_grid = cong        # find_path (reroute + adherence) reads this same grid

    def _predict_next(self, finish_xy, taken):
        cands = [s for s in self.env.request_queue if s.id not in taken]
        if not cands:
            return None
        top = _rt.cheap_screen(_Pt(*finish_xy), cands, task_value, keep=1)
        return top[0] if top else None

    @staticmethod
    def _shortest(G, start_xy, goal_xy):
        rs = _rt.k_shortest_routes(G, start_xy, goal_xy, k=1)
        return rs[0] if rs else []

    # --- prioritized dispatch: high-value robots plan first ---------------------
    def _order_free_agvs(self, free_agvs):
        taken = set(self.assigned_items.values())

        def keyf(a):
            cands = [s for s in self.env.request_queue if s.id not in taken]
            top = _rt.cheap_screen(a, cands, task_value, keep=1)
            return -(task_value(top[0]) if top else 0.0)
        return sorted(free_agvs, key=keyf)

    # --- congestion-aware route pick + stamp -----------------------------------
    def _pick_route(self, routes, shelf, now):
        cong = self._cong
        if cong is None:
            return min(routes, key=len)
        H, W = cong.shape
        lam = self.CONG_LAMBDA

        def cost(r):
            c = float(len(r))
            for (x, y) in r:
                if 0 <= y < H and 0 <= x < W:
                    c += lam * cong[y, x]
            return c
        return min(routes, key=cost)

    def _on_commit(self, agv, route):
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        for (x, y) in route:                # 3. FRESH: next robot avoids this one (prioritized)
            if 0 <= y < H and 0 <= x < W:
                cong[y, x] += 1.0


# ============================================================================
# Shared congestion-forecast helpers (used by RushCongestionController; the
# PartACongestionController above keeps its own inline copy that already works).
# ============================================================================
def _predict_next(env, finish_xy, taken):
    cands = [s for s in env.request_queue if s.id not in taken]
    if not cands:
        return None
    top = _rt.cheap_screen(_Pt(*finish_xy), cands, task_value, keep=1)
    return top[0] if top else None


def _shortest(G, a, b):
    rs = _rt.k_shortest_routes(G, a, b, k=1)
    return rs[0] if rs else []


def _build_forecast(ctrl, G, H, W, horizon=40, future_w=0.5):
    cong = np.zeros((H, W), dtype=np.float32)
    taken = set(ctrl.assigned_items.values())

    def stamp(cells, w):
        for (x, y) in cells:
            if 0 <= y < H and 0 <= x < W:
                cong[y, x] += w

    for a in ctrl.agvs:
        path = getattr(a, "path", None)
        if a.busy and path:
            stamp(path, 1.0)
            if len(path) <= horizon:
                nt = _predict_next(ctrl.env, path[-1], taken)
                if nt is not None:
                    taken.add(nt.id)
                    stamp(_shortest(G, path[-1], (nt.x, nt.y)), future_w)
    return cong


def _cong_route(cong, routes, lam):
    if cong is None:
        return min(routes, key=len)
    H, W = cong.shape

    def cost(r):
        c = float(len(r))
        for (x, y) in r:
            if 0 <= y < H and 0 <= x < W:
                c += lam * cong[y, x]
        return c
    return min(routes, key=cost)


def _stamp_route(cong, route):
    H, W = cong.shape
    for (x, y) in route:
        if 0 <= y < H and 0 <= x < W:
            cong[y, x] += 1.0


class RushCongestionController(RushValueController):
    """Rush's task/robot selection, but routes chosen to DODGE the congestion forecast
    (and driven via adherence). Same forecast machinery as PartACongestion, on Rush's picker."""

    CONG_LAMBDA = 0.3
    CONG_WEIGHT = 0.3

    def __init__(self, env):
        super().__init__(env)
        env.prefer_committed = True
        env.congestion_weight = self.CONG_WEIGHT
        self._agv_graph = None

    def _assign_tasks(self):
        env = self.env
        if self._agv_graph is None:
            self._agv_graph = _rt.build_agv_graph(env)
        G = self._agv_graph
        _clear_fetch_cells(self)
        H, W = env.grid_size
        cong = _build_forecast(self, G, H, W)
        env.congestion_grid = cong                 # reroute (find_path) dodges the same map
        for item in self._task_order():
            if item.id in self.assigned_items.values():
                continue
            available = [a for a in self.agvs if not a.busy and not a.carrying_shelf
                         and a not in self.assigned_agvs]
            if not available:
                continue
            paths = [env.find_path((a.y, a.x), (item.y, item.x), a, care_for_agents=False)
                     for a in available]
            closest = available[int(np.argmin([len(p) for p in paths]))]
            loc_id = self.coords_to_id[(item.y, item.x)]
            self.assigned_agvs[closest] = Mission(MissionType.PICKING, loc_id, item.x, item.y,
                                                  self.timestep)
            self.assigned_items[closest] = item.id
            routes = _rt.k_shortest_routes(G, (closest.x, closest.y), (item.x, item.y), k=3)
            if routes:
                r = _cong_route(cong, routes, self.CONG_LAMBDA)
                closest.committed_cells = {(cy, cx) for (cx, cy) in r}
                _stamp_route(cong, r)              # prioritized: next assignment avoids this one


# ============================================================================
# Delay-head-as-policy controllers: wire a trained head into Part A's finish estimate.
# ============================================================================
def _make_head(path):
    with open(path, "rb") as f:
        d = pickle.load(f)
    model, cols, best = d["model"], d["cols"], d.get("best_iteration")

    def head(feat):
        x = np.array([[feat[c] for c in cols]], dtype=float)
        return float(model.predict(x, num_iteration=best)[0])
    return head


class PartABaselineHeadController(PartAController):
    """Part A with the ORIGINAL (baseline, static-feature) delay head wired into the finish."""

    def __init__(self, env):
        super().__init__(env)
        self.delay_head = _make_head("results/delay_head.pkl")


class PartAVarHeadController(PartAController):
    """Part A with the VARIANCE (congestion-feature) delay head wired into the finish."""

    def __init__(self, env):
        super().__init__(env)
        self.delay_head = _make_head("results/delay_head_var.pkl")


class PartACongestionTaskController(PartACongestionController):
    """Part A congestion, but the TASK choice is congestion-aware too: a task whose best route
    runs through forecast traffic is penalized, so the robot prefers value AND a clear path
    (not just a clear path to a jammed high-value task). Route pick + soft reroute unchanged."""

    CONG_TASK_LAMBDA = 0.3     # weight of best-route congestion in the TASK score

    def _task_score_adjust(self, shelf, best_r):
        cong = self._cong
        if cong is None:
            return 0.0
        H, W = cong.shape
        c = 0.0
        for (x, y) in best_r:
            if 0 <= y < H and 0 <= x < W:
                c += cong[y, x]
        return -self.CONG_TASK_LAMBDA * c


class RushCongestionFullController(PartACongestionTaskController):
    """The variant: RUSH's self-updating window as the doability cutoff (its good part), plus the
    FULL congestion machinery -- congestion-aware TASK choice, congestion-aware ROUTE choice, and
    soft congestion reroute. = Part A's congestion funnel driven by Rush's aggregate time estimate
    instead of Part A's traffic-blind per-task finish."""

    USE_GLOBAL_WINDOW = True     # makeable/doomed split via Rush's live running-mean window


class PartACongestionFinishController(PartACongestionController):
    """parta_congestion, but the makeable/doomed FINISH is congestion-aware too. Adds an expected
    traffic delay (forecast congestion along the chosen route x FINISH_CONG_K) to the empty-world
    finish BEFORE the deadline check -> 'will I make it on time?' now accounts for jams. This is the
    delay head's job done by RULES (computed from the map) instead of a learned constant."""

    FINISH_CONG_K = 0.2      # expected extra steps per unit of route congestion (tunable)

    def _finish_delay(self, best_r):
        cong = self._cong
        if cong is None:
            return 0.0
        H, W = cong.shape
        c = 0.0
        for (x, y) in best_r:
            if 0 <= y < H and 0 <= x < W:
                c += cong[y, x]
        return self.FINISH_CONG_K * c


class PartACongestionSoftController(PartACongestionController):
    """parta_congestion, but the makeable/doomed HARD cliff is replaced by a SOFT P(on-time) weight:
    score = 1000 * P(on-time) + value, where P(on-time) = sigmoid(margin / sigma) and the uncertainty
    sigma WIDENS with the route's forecast congestion. So a noisy-but-honest ETA degrades gracefully
    (a jammed task gets down-weighted, not violently flipped). This is the SOFT version of the
    congestion-aware deadline -- the one lever the HARD finish-adjustment couldn't make work."""

    SOFT_SIGMA = 8.0     # base ETA uncertainty (steps) -> softness of the on-time transition
    SOFT_K = 0.3         # extra uncertainty per unit of route congestion

    def _deadline_score(self, v, proj_late, shelf, best_r):
        import math
        margin = -proj_late                              # >0 = ahead of deadline
        cong = 0.0
        if self._cong is not None:
            H, W = self._cong.shape
            for (x, y) in best_r:
                if 0 <= y < H and 0 <= x < W:
                    cong += self._cong[y, x]
        sigma = self.SOFT_SIGMA + self.SOFT_K * cong
        p_on = 1.0 / (1.0 + math.exp(-margin / max(1e-6, sigma)))
        return 1000.0 * p_on + v                         # soft tier: ~makeable(1000+v) .. doomed(v)


class PartACongestionProbController(PartACongestionController):
    """Q1's improvement: the finishing-robot forecast is PROBABILISTIC. Instead of stamping one
    top-1 predicted next task, spread the (uncertain) future over its top-K likely next tasks,
    rank-weighted -- so the map is a distribution of POSSIBLE futures, not a committed guess. Same
    total future mass, just dispersed. Everything else identical to the champion."""

    RANK_W = [0.5, 0.3, 0.2]      # weight over the top-K likely next tasks (dispersed, sums to 1)

    def _pre_dispatch(self, free_agvs, G):
        env = self.env
        H, W = env.grid_size
        cong = np.zeros((H, W), dtype=np.float32)
        taken = set(self.assigned_items.values())

        def stamp(cells, w):
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w

        for a in self.agvs:
            path = getattr(a, "path", None)
            if a.busy and path:
                stamp(path, 1.0)                                   # KNOWN remaining path
                if len(path) <= self.FINISH_HORIZON:              # FINISHING -> DISTRIBUTION of nexts
                    finish = path[-1]
                    cands = [s for s in env.request_queue if s.id not in taken]
                    top = _rt.cheap_screen(_Pt(*finish), cands, task_value, keep=len(self.RANK_W))
                    if top:
                        ws = self.RANK_W[:len(top)]
                        Z = sum(ws)
                        for s, w in zip(top, ws):
                            r = self._shortest(G, finish, (s.x, s.y))
                            stamp(r, self.FUTURE_WEIGHT * w / Z)  # spread future mass, weighted
                        taken.add(top[0].id)                      # light dedup on the most-likely
        self._cong = cong
        env.congestion_grid = cong


class PartADeadlineCongController(PartACongestionController):
    """Congestion used for the DEADLINE ONLY -- NOT proactive route steering, NOT a score term.
    Routes = plain shortest (reactive rerouting around real blockers still happens via the env, as
    always); the score has NO separate congestion variable. The forecast map is built solely to
    estimate the DELAY that inflates the finish for the makeable/doomed check. Isolates 'does
    congestion help the deadline when it is NOT double-counted with routing?'"""

    CONG_LAMBDA = 0.0        # (unused: _pick_route overridden to shortest)
    FINISH_CONG_K = 1.0      # congestion along the shortest route -> deadline delay estimate

    def __init__(self, env):
        PartAController.__init__(self, env)     # base init WITHOUT prefer_committed / congestion_weight
        self._cong = None

    def _pre_dispatch(self, free_agvs, G):
        super()._pre_dispatch(free_agvs, G)     # build self._cong (also sets env.congestion_grid)
        self.env.congestion_grid = None         # do NOT PROACTIVELY steer by forecast (reactive stays)

    def _route_cong(self, r):
        cong = self._cong
        if cong is None:
            return 0.0
        H, W = cong.shape
        return sum(cong[y, x] for (x, y) in r if 0 <= y < H and 0 <= x < W)

    def _pick_route(self, routes, shelf, now):
        """DEADLINE-CONDITIONAL route selection: estimate each route's delay (congestion), then pick
        the SHORTEST route that still makes the deadline; only escalate to the least-delayed route
        when the shortest would miss. Congestion matters ONLY when the deadline is threatened -- with
        deadline slack, take the shortest (don't waste time detouring). No proactive route steering."""
        if self._cong is None or shelf.deadline is None:
            return min(routes, key=len)
        K = self.FINISH_CONG_K
        shortest = min(routes, key=len)
        slack = shelf.deadline - now - self.window          # deadline room beyond nominal completion
        if K * self._route_cong(shortest) <= max(0.0, slack):
            return shortest                                 # not threatened -> shortest
        return min(routes, key=lambda r: len(r) + K * self._route_cong(r))  # threatened -> least-delayed

    def _finish_delay(self, best_r):            # congestion's ONLY use: the deadline delay estimate
        return self.FINISH_CONG_K * self._route_cong(best_r)


class PartACongestionQueueController(PartACongestionController):
    """Champion + a QUEUE layer in the congestion forecast.

    WHY: the demand stream made the request queue ebb (it is no longer always-full), which thins out
    forecast layer 2 -- that layer only guesses the next task for robots within FINISH_HORIZON of
    finishing, so unclaimed BACKLOG contributes nothing to the map, and during a lull the future part
    of the forecast can vanish entirely.

    This is NOT demand prediction (that is Part C): every order used here ALREADY EXISTS in the queue.
    We use the one piece of a pending order that is robot-INDEPENDENT -- whoever eventually takes it
    must haul that shelf to a workstation, so the shelf->goal leg will be traversed regardless of who
    wins the task. Unclaimed pending orders stamp that leg lightly, decayed by rank (the tasks most
    likely to be served next carry the most weight).
    """

    QUEUE_WEIGHT = 0.25    # lighter than FUTURE_WEIGHT: further out in time, and the robot is unknown
    QUEUE_TOP_K = 6        # only the orders plausibly served soon

    def _pre_dispatch(self, free_agvs, G):
        self._predicted = set()
        super()._pre_dispatch(free_agvs, G)        # layers 1-3 (+ sets self._cong / env.congestion_grid)
        env = self.env
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        claimed = set(self.assigned_items.values()) | self._predicted
        pend = [s for s in env.request_queue if s.id not in claimed]
        if not pend:
            return
        # rank by value: the funnel prefers high-value work, so those get served soonest
        pend.sort(key=lambda s: -task_value(s))
        pend = pend[:self.QUEUE_TOP_K]
        goals = [(gx, gy) for (gx, gy) in env.goals]     # env.goals already holds (x, y) (cf. rollout.py:36)
        n = len(pend)
        for i, s in enumerate(pend):
            w = self.QUEUE_WEIGHT * (1.0 - i / n)        # rank decay
            g = min(goals, key=lambda g: abs(g[0] - s.x) + abs(g[1] - s.y))
            for (x, y) in self._shortest(G, (s.x, s.y), g):
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w

    def _predict_next(self, finish_xy, taken):
        nt = super()._predict_next(finish_xy, taken)
        if nt is not None:
            self._predicted.add(nt.id)               # so layer 4 skips orders already spoken for
        return nt


class PartACongestionFreeL2Controller(PartACongestionController):
    """Champion, with layer 2 rebuilt around TIME-TO-FREE and the FREE-UP LOCATION.

    The original layer 2 anchored its next-task prediction at path[-1] and gated on
    len(path) <= FINISH_HORIZON(40). Measured (docs/NOTES 2026-07-18):
      (a) the gate never excludes anyone -- max observed remaining path is 41, 0.1% exceed 40,
          so "FINISHING" was really "every busy robot";
      (b) path[-1] is the robot's OWN SHELF for 36.9% of busy AGVs (100% of fetching ones). Those
          robots are not finishing at all -- they still have the whole haul ahead -- so the next-task
          route was drawn from a cell they merely drive through;
      (c) len(path) underestimates true time-to-free by ~2.5x (11.7 vs measured 27.1 steps).

    Fix: estimate time-to-free as len(path) + load + dist(path_end -> nearest dock) (best of three
    estimators measured against ground truth: MAE 13.8 / r 0.50, vs 15.2 / 0.45 for len(path)), anchor
    the prediction at THAT DOCK -- where the robot actually becomes free and would start its next
    fetch -- and decay the stamp weight linearly with time-to-free, so a robot about to free up stamps
    near FUTURE_WEIGHT and a distant one stamps ~0. Time-to-free is noisy (MAE ~14 on a mean of 27),
    which is exactly why the weight decays rather than a hard tag deciding in/out.
    """

    FREE_HORIZON = 30      # beyond this the prediction is worthless (weight would be ~0 anyway)

    def _nearest_dock(self, xy):
        x, y = xy
        return min(self.env.goals, key=lambda g: abs(g[0] - x) + abs(g[1] - y))

    def _pre_dispatch(self, free_agvs, G):
        env = self.env
        H, W = env.grid_size
        cong = np.zeros((H, W), dtype=np.float32)
        taken = set(self.assigned_items.values())
        self._l2_stats = getattr(self, "_l2_stats", {"tagged": 0, "rounds": 0, "mass": 0.0})
        self._l2_stats["rounds"] += 1

        def stamp(cells, w):
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w

        for a in self.agvs:
            path = getattr(a, "path", None)
            if not (a.busy and path):
                continue
            stamp(path, 1.0)                                    # 1. KNOWN remaining path
            end = path[-1]
            dock = self._nearest_dock(end)
            t_free = (len(path) + _ro.DEFAULT_LOAD_TIME
                      + abs(end[0] - dock[0]) + abs(end[1] - dock[1]))
            if t_free >= self.FREE_HORIZON:
                continue
            nt = self._predict_next(dock, taken)                # 2. anchored where it FREES UP
            if nt is None:
                continue
            taken.add(nt.id)
            w = self.FUTURE_WEIGHT * (1.0 - t_free / self.FREE_HORIZON)
            r = self._shortest(G, dock, (nt.x, nt.y))
            stamp(r, w)
            self._l2_stats["tagged"] += 1
            self._l2_stats["mass"] += w * len(r)

        self._cong = cong
        env.congestion_grid = cong


class PartACongestionNoL2Controller(PartACongestionController):
    """ABLATION: champion with layer 2 (predicted next-task routes) switched OFF.

    Rebuilding layer 2 correctly (PartACongestionFreeL2Controller) moved on-time value by +0.15 over 30
    paired seeds (t=0.04) despite changing the map a lot -- so this asks the prior question: does layer 2
    contribute anything at all, or is it mass without leverage?
    """

    FUTURE_WEIGHT = 0.0


class PartACongestionDockController(PartACongestionController):
    """Champion + CONGESTION-AWARE DOCK CHOICE (option A).

    At pickup the controller already re-evaluates all 10 workstations (sim_dashboard.py, MissionType
    PICKING -> DELIVERING) -- the right moment to decide the haul, since conditions have moved on since
    assignment. But it ranked them by `argmin len(path)`: RAW cell count, congestion-blind, even though
    the very same find_path call had already priced congestion into the path it returned. Every AGV
    therefore piles toward whichever dock is physically nearest, which is how dock queues form.

    This ranks docks by len + DOCK_LAMBDA * congestion-crossed, the same objective _pick_route uses for
    the fetch leg. Unlike a smeared demand prior, this is a SHARP 10-way discrete choice with real
    spread between options -- the kind that can actually flip an argmin.
    """

    DOCK_LAMBDA = 0.3      # same weight as CONG_LAMBDA on the fetch leg

    def _pick_dock(self, agv, goal_paths):
        cong = self._cong
        if cong is None:
            return super()._pick_dock(agv, goal_paths)
        H, W = cong.shape

        def cost(p):
            if not p:
                return float("inf")            # unreachable dock (default hook scores these 0 = best)
            c = float(len(p))
            for (x, y) in p:                   # find_path returns (x, y) cells (verified)
                if 0 <= y < H and 0 <= x < W:
                    c += self.DOCK_LAMBDA * cong[y, x]
            return c
        return int(np.argmin([cost(p) for p in goal_paths]))


class PartACongestionRecordController(PartACongestionController):
    """PASS 1 of the oracle test: champion, but records every commit it makes.

    Log entry: (timestep, agv_id, shelf_id, route). Pass 2 replays this as layer 2's "prediction",
    so layer 2 becomes never-wrong about what each robot does next.
    """

    def __init__(self, env):
        super().__init__(env)
        self.commit_log = []

    def _on_commit(self, agv, route):
        super()._on_commit(agv, route)
        self.commit_log.append((int(self.timestep), int(agv.id), list(route)))


class PartACongestionOracleController(PartACongestionController):
    """PASS 2 of the oracle test: layer 2 replaced by RECORDED GROUND TRUTH.

    Instead of guessing which task a robot takes next (cheap_screen top-1 from an anchor), we look up
    what that robot ACTUALLY committed to next, in a recorded run of the same episode, and stamp that
    real route. This is better information than any predictor -- heuristic, policy-rollout or learned --
    could ever obtain, so it UPPER-BOUNDS what prediction is worth here.

    Honest caveat: stamping the true future changes behaviour, so pass 2 drifts from the recording and
    the "truth" degrades over the episode. That asymmetry is fine for the decision we want: a NULL under
    near-oracle information is strong evidence prediction is not the lever; a large WIN is an upper
    bound, not a promise.
    """

    ORACLE_HORIZON = None      # None = stamp the next trip whenever it starts (ORIGINAL, badly timed)

    def __init__(self, env, commit_log=None, horizon=None):
        super().__init__(env)
        if horizon is not None:
            self.ORACLE_HORIZON = horizon
        self.set_log(commit_log or [])

    def set_log(self, commit_log):
        self._by_agv = {}
        for (t, aid, route) in commit_log:
            self._by_agv.setdefault(aid, []).append((t, route))
        for v in self._by_agv.values():
            v.sort(key=lambda r: r[0])
        self.oracle_hits = self.oracle_miss = self.oracle_late = 0

    def _next_route(self, agv_id, now):
        """The route this robot ACTUALLY committed to next, strictly after `now`.

        With ORACLE_HORIZON set, only return it if that trip STARTS within the horizon -- i.e. it
        overlaps in TIME with the journey currently being planned (~11 steps, p95 27). Layer 2's whole
        purpose is robots that free up AND start within that window; stamping a trip that begins after
        your trip has finished marks the right road at the wrong time.
        """
        H = self.ORACLE_HORIZON
        for (t, route) in self._by_agv.get(agv_id, ()):
            if t > now:
                if H is not None and (t - now) > H:
                    self.oracle_late += 1
                    return None
                return route
        return None

    def _pre_dispatch(self, free_agvs, G):
        env = self.env
        H, W = env.grid_size
        cong = np.zeros((H, W), dtype=np.float32)
        now = int(self.timestep)

        def stamp(cells, w):
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w

        for a in self.agvs:
            path = getattr(a, "path", None)
            if not (a.busy and path):
                continue
            stamp(path, 1.0)                                  # 1. KNOWN remaining path (unchanged)
            r = self._next_route(int(a.id), now)              # 2. ORACLE: what it really does next
            if r:
                stamp(r, self.FUTURE_WEIGHT)
                self.oracle_hits += 1
            else:
                self.oracle_miss += 1
        self._cong = cong
        env.congestion_grid = cong


class PartACongestionPerRouteOracleController(PartACongestionOracleController):
    """Oracle layer 2 with the horizon set PER DECISION, not by a constant.

    There is no single correct horizon: the window is the length of the SPECIFIC journey being scored.
    A robot choosing a 6-step route and one choosing a 25-step route care about different future trips.
    A pre-summed grid cannot express that (it is built once per round, before any route is chosen), so
    future trips are kept as a LIST of (start_delay, cells) and folded in at scoring time -- a trip
    counts against a candidate route only if it STARTS before that route ENDS.

    Certain mass (layer 1 remaining paths + layer 3 fresh commits) stays in the grid, since it is
    already in play now and is what env.find_path reads for reroute/adherence.
    """

    def _next_entry(self, agv_id, now):
        """(start_timestep, route) of this robot's actual next commit -- unfiltered."""
        for (t, route) in self._by_agv.get(agv_id, ()):
            if t > now:
                return t, route
        return None

    def _pre_dispatch(self, free_agvs, G):
        env = self.env
        H, W = env.grid_size
        cong = np.zeros((H, W), dtype=np.float32)
        now = int(self.timestep)
        self._future = []                     # [(start_delay, {cells})] -- filtered per route later

        for a in self.agvs:
            path = getattr(a, "path", None)
            if not (a.busy and path):
                continue
            for (x, y) in path:               # 1. KNOWN remaining path (certain -> grid)
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += 1.0
            entry = self._next_entry(int(a.id), now)
            if entry is not None:
                t, route = entry
                self._future.append((t - now, {(x, y) for (x, y) in route}))
                self.oracle_hits += 1
            else:
                self.oracle_miss += 1

        self._cong = cong
        env.congestion_grid = cong            # find_path sees only CERTAIN mass

    def _pick_route(self, routes, shelf, now):
        cong = self._cong
        if cong is None:
            return min(routes, key=len)
        H, W = cong.shape
        lam, fw = self.CONG_LAMBDA, self.FUTURE_WEIGHT

        def cost(r):
            L = len(r)                        # <-- THIS journey's own horizon
            c = float(L)
            for (x, y) in r:
                if 0 <= y < H and 0 <= x < W:
                    c += lam * cong[y, x]
            rs = set(r)
            for (delay, cells) in self._future:
                if delay < L:                 # starts before this journey ends -> can actually collide
                    c += lam * fw * len(rs & cells)
                else:
                    self.oracle_late += 1
            return c
        return min(routes, key=cost)


class PartACongestionPickerController(PartACongestionController):
    """Champion + the PICKER side wired in: pickers as TRAFFIC, and pickers as congestion-aware DECIDERS.

    Three gaps this closes (all measured/audited 2026-07-18):
      1. PICKERS AS TRAFFIC. The forecast loop was `for a in self.agvs`, so picker paths were never
         stamped -- 37.7% of all moving-robot cells were invisible. Pickers READ the grid (find_path
         adds env.congestion_grid for any agent) but never WROTE to it. They are real obstacles: the
         picker collision layer is added to the AGV cost grid. This is CERTAIN, CURRENT information, so
         it passes the avoidance-points-backwards rule that future-task marks failed.
      2. PICKER ROUTE CHOICE was `min(routes, key=len)` -- pure length, blind to the forecast the AGV
         side has used since the champion.
      3. PICKER TASK CHOICE scored value + deadline + sync but never congestion.
    Plus STALL_BONUS on BOTH sides (see PartAController.STALL_BONUS): a partner already parked and
    waiting was charged the maximum sync penalty, so a far-away STALLED robot lost to a near
    not-yet-ready one despite an identical finish time.
    """

    STALL_BONUS = 5.0            # reorders within a deadline tier (v spread ~1-15), never across one
    PICKER_WEIGHT = 1.0          # pickers are as solid as AGVs -> same stamp weight as layer 1
    PICKER_CONG_LAMBDA = 0.3     # congestion weight in the picker's ROUTE pick (mirrors CONG_LAMBDA)
    PICKER_TASK_LAMBDA = 0.3     # congestion weight in the picker's RENDEZVOUS choice

    def _pre_dispatch(self, free_agvs, G):
        super()._pre_dispatch(free_agvs, G)          # layers 1-3 over AGVs
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        for p in self.pickers:                       # 1. PICKERS AS TRAFFIC (certain, current)
            path = getattr(p, "path", None)
            if not path:
                continue
            for (x, y) in path:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += self.PICKER_WEIGHT

    def _route_cong(self, route, lam):
        cong = self._cong
        if cong is None or not route:
            return 0.0
        H, W = cong.shape
        return lam * sum(float(cong[y, x]) for (x, y) in route if 0 <= y < H and 0 <= x < W)

    def _pick_picker_route(self, routes):            # 2. congestion-aware picker ROUTE
        if self._cong is None:
            return min(routes, key=len)
        return min(routes, key=lambda r: len(r) + self._route_cong(r, self.PICKER_CONG_LAMBDA))

    def _picker_task_adjust(self, gx, gy, best_r):   # 3. congestion-aware RENDEZVOUS choice
        return -self._route_cong(best_r, self.PICKER_TASK_LAMBDA)


class PartACongestionPickerTrafficController(PartACongestionController):
    """Champion + PICKERS AS TRAFFIC ONLY. No sync-up changes (no stall bonus, no picker-side
    congestion in route or rendezvous choice) -- so a result here is attributable to one thing.

    The forecast loop was `for a in self.agvs`, so picker paths were never stamped: 37.7% of all
    moving-robot cells were invisible. Pickers READ the grid (find_path adds env.congestion_grid for
    any agent) but never WROTE to it, and they are real obstacles -- the picker collision layer is
    added to the AGV cost grid. Certain, current information; passes the avoidance-points-backwards
    rule that future-task marks failed.
    """

    PICKER_WEIGHT = 1.0          # as solid as an AGV -> same stamp weight as layer 1

    def _pre_dispatch(self, free_agvs, G):
        super()._pre_dispatch(free_agvs, G)
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        for p in self.pickers:
            path = getattr(p, "path", None)
            if not path:
                continue
            for (x, y) in path:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += self.PICKER_WEIGHT


class PartACongestionLoadTimeController(PartACongestionController):
    """Champion with LOAD_TIME corrected from 5 to 1 -- the only surviving item of the rollout audit.

    The rollout adds LOAD_TIME steps for the AGV+picker transfer at the shelf. The SIMULATOR has no
    such delay: `_execute_load` (warehouse.py) sets `carrying_shelf` in the same step the two robots
    share a cell. The only real cost is that loading is issued as a TOGGLE_LOAD micro-action, so the
    AGV spends ONE step not moving. Waiting for the picker is separate and already modelled (my_wait).

    So finish carried ~4 fictitious steps. Being constant it cannot reorder tasks -- but it lands on a
    HARD threshold: proj_late = (now + finish) - deadline decides makeable (1000+v) vs doomed
    (v*g^late). Every task looked 4 steps later than it is, so tasks within 4 steps of their deadline
    were classed DOOMED when they were actually MAKEABLE. This is the one place a constant bias bites
    (and precisely why the delay head's constant did nothing -- it never crossed a cliff).

    NOTE the other two audit items were MEASURED AND REJECTED, not implemented:
      - "A* instead of Manhattan for the haul": Manhattan IS the shortest path (AGVs drive under
        shelves, so build_agv_graph is obstacle-free). Measured diff = exactly -1 on 60/60 shelves,
        i.e. the endpoint convention.
      - "return leg goes to nearest empty storage, not back to origin": true, but the proxy is
        accurate -- actual 16.4 mean / 15 median vs assumed 15.5 / 15.
    """

    LOAD_TIME = 1


class PartACongestionBatteryController(PartACongestionController):
    """Champion + a LIVE battery model using a REACHABILITY reserve instead of a fixed floor.

    Two things were broken, both silent:
      1. NO PART A CONTROLLER HAD A BATTERY TRACKER. `battery_feasible()` sits in the Part A funnel,
         but bcfg/blevel are None there, so it returned True unconditionally -- the step-4 filter has
         never once fired. The only controller WITH a battery (BatteryAwareController) is Rush-derived
         and never enters that funnel. The checklist records this as done and "wired into rollout".
      2. The constraint itself was the wrong shape: a flat 10% floor. Holding an arbitrary reserve is
         not the goal -- being able to REACH a charger is. `charger_reserve` replaces it: the reserve
         is the energy needed to get from where the task ENDS to the nearest charger, so a robot
         finishing beside a charger is allowed to run much lower than one finishing far away.
    """

    GO_CHARGE = 0.35     # a free robot below this heads to a charger (same as BatteryAwareController)

    def __init__(self, env):
        super().__init__(env)
        from wwm_sim.battery import BatteryTracker, BatteryConfig
        self.battery = BatteryTracker(env, BatteryConfig(floor=0.0))   # floor 0: reachability governs

    def act(self):
        # Without these the tracker is decoration: step() applies drain, _manage_charging() recharges.
        # Attaching a tracker alone would leave every level pinned at 1.0 and the filter inert again.
        self.battery.step()
        self._manage_charging()
        actions = super().act()
        for i, a in enumerate(self.agents):
            if self.battery.is_flat(a):
                actions[i] = 0                      # stranded -> movement gate
        return actions

    def _manage_charging(self):
        bat, aa, ap = self.battery, self.assigned_agvs, self.assigned_pickers
        for a in list(aa):
            if aa[a].mission_type == MissionType.CHARGING and bat.is_full(a):
                aa.pop(a)
                self.assigned_items.pop(a, None)
        for p in list(ap):
            if ap[p].mission_type == MissionType.CHARGING and bat.is_full(p):
                ap.pop(p)
        for a in self.agvs:
            if a not in aa and not a.carrying_shelf and bat.needs_charge(a, self.GO_CHARGE):
                self._send_to_charger(a, aa)
        for p in self.pickers:
            if p not in ap and bat.needs_charge(p, self.GO_CHARGE):
                self._send_to_charger(p, ap)

    def _send_to_charger(self, robot, assign_dict):
        c = self.battery.nearest_charger(robot)
        if c is None:
            return
        loc_id = self.coords_to_id.get((c[1], c[0]))
        if loc_id is not None:
            assign_dict[robot] = Mission(MissionType.CHARGING, loc_id, c[0], c[1], self.timestep)


class PartACongestionCalibController(PartACongestionController):
    """LOAD_TIME at its TRUE physical value (1) + an EXPLICIT, named DELAY ALLOWANCE.

    Correcting LOAD_TIME 5->1 measurably HURT (-2.9, 20 of 26 decided seeds, sign-test p=0.009), which
    exposed what it was really doing: the rollout's `finish` is EMPTY-WORLD -- it models zero delay,
    ever -- so it is systematically optimistic, and the 4 fictitious loading steps were acting as an
    accidental safety pad on the makeable/doomed cutoff. (`per_task_window()`, the function written to
    calibrate geometry against observed durations, is dead code -- never called anywhere.)

    So instead of a wrong physical story we name the thing: DELAY_ALLOWANCE is padding for un-modelled
    delay, applied via the existing `_finish_delay` hook BEFORE the deadline check. Total pad =
    LOAD_TIME + DELAY_ALLOWANCE, so allowance 4 reproduces the champion's effective 5 and is the
    sanity-check arm of the sweep.

    NOTE this is NOT the per-task delay ESTIMATE that failed three times (delay head, variance head,
    congestion-finish). Those tried to predict how late THIS task would be. This is one global constant
    for everything -- which is exactly the shape the LOAD_TIME evidence says works.
    """

    LOAD_TIME = 1
    DELAY_ALLOWANCE = 4.0

    def _finish_delay(self, best_r):
        return self.DELAY_ALLOWANCE


class _Cal0(PartACongestionCalibController):
    DELAY_ALLOWANCE = 0.0


class _Cal2(PartACongestionCalibController):
    DELAY_ALLOWANCE = 2.0


class _Cal4(PartACongestionCalibController):
    DELAY_ALLOWANCE = 4.0


class _Cal7(PartACongestionCalibController):
    DELAY_ALLOWANCE = 7.0


class _Cal10(PartACongestionCalibController):
    DELAY_ALLOWANCE = 10.0


class _Cal14(PartACongestionCalibController):
    DELAY_ALLOWANCE = 14.0


# --- LOAD_TIME as the calibration knob -------------------------------------------------------
# The _finish_delay-hook version (PartACongestionCalibController) was INVALID: LOAD_TIME is consumed
# in THREE places -- the AGV rollout finish, the PICKER funnel's own finish, and free_again (which
# feeds other robots' partner_eta case-3 estimates) -- but the hook only reaches the first. The
# sanity arm (pad 5, which should have equalled the champion exactly) differed on 9/30 seeds and
# caught it. Sweeping LOAD_TIME directly touches all three sites, so lt5 MUST be a perfect tie with
# the champion; if it is not, the harness is wrong again.
class _LT1(PartACongestionController):
    LOAD_TIME = 1        # the true physical value (TOGGLE_LOAD costs one step)


class _LT3(PartACongestionController):
    LOAD_TIME = 3


class _LT5(PartACongestionController):
    LOAD_TIME = 5        # == champion. SANITY ARM: must be 30/30 ties.


class _LT8(PartACongestionController):
    LOAD_TIME = 8


class _LT11(PartACongestionController):
    LOAD_TIME = 11


class _LT15(PartACongestionController):
    LOAD_TIME = 15


class PartACongestionPredRecordController(PartACongestionController):
    """PASS 1 of the COMPLETION-TIME oracle: champion + a log of (shelf -> assign_step, predicted finish).
    Combined with the actual delivery step this yields the REALIZED delay per task."""

    def __init__(self, env):
        super().__init__(env)
        self.pred_log = {}                 # shelf_id -> (assign_step, predicted_finish)

    def _on_predict(self, shelf, now, pred_finish):
        self.pred_log[shelf.id] = (int(now), float(pred_finish))


class PartACongestionDelayOracleController(PartACongestionController):
    """PASS 2: the planner is handed each task's REALIZED delay instead of guessing it.

    The deadline check is `proj_late = (now + finish) - deadline`, where `finish` is EMPTY-WORLD (zero
    delay) plus a constant pad. That decides makeable (1000+v) vs doomed (v*g^late) -- a hard cliff we
    proved is sensitive to ~4 steps (LOAD_TIME, p=0.021 and p=0.009 in two runs).

    Here `_finish_delay` returns the delay that task ACTUALLY suffered in a recorded run of the same
    episode, so every makeable/doomed call is made on true completion time. No predictor -- learned,
    rules-based, or a full fleet-rollout world model -- can beat the truth, so this UPPER-BOUNDS the
    entire delay direction. Null => stop; large => that gap is the prize and a world model is justified.

    Caveat (same as the layer-2 oracle): acting on truth changes behaviour, so the recording drifts.
    Near-oracle, not perfect -- which cuts the reassuring way for a null result.
    """

    def __init__(self, env, delay_truth=None, fallback=None):
        super().__init__(env)
        self.delay_truth = delay_truth or {}
        self.fallback = fallback           # None => 0.0 extra (LOAD_TIME already in finish)
        self.hits = self.misses = 0

    def _finish_delay(self, best_r):
        sh = getattr(self, "_score_shelf", None)
        if sh is not None and sh.id in self.delay_truth:
            self.hits += 1
            return self.delay_truth[sh.id]
        self.misses += 1
        return 0.0 if self.fallback is None else self.fallback


class PartACongestionDepthController(PartACongestionController):
    """Champion + a LOOKAHEAD DEPTH knob on task choice: "what's left for the next robots?"

    The funnel is GREEDY -- each robot in turn takes the task with the best score for ITSELF, marks it
    taken, and the next robot picks from the leftovers. That maximises per-robot value, not TOTAL value:
    a robot can grab a task that was the only good option for the robot behind it, when its own second
    choice was nearly as good.

    This adds the opportunity cost. When scoring candidate task X for me, simulate the next
    (DEPTH-1) robots greedily taking their best remaining task from a pool WITHOUT X, and add the value
    they collect. Taking a contested task lowers that sum, so a contested task has to be worth MORE to
    me than the damage it does behind me.

      DEPTH = 1  -> the term is identically 0 -> EXACTLY the current champion (sanity arm).
      DEPTH = 2  -> account for the next robot. DEPTH = 3 -> the next two. Etc.

    COST: the lookahead uses the CHEAP screen (value - 0.15*distance), not the full funnel (Yen routes +
    rollout), so it is ~(DEPTH-1) * |queue| cheap evaluations per candidate -- affordable. The full
    score is still what picks the winner; the lookahead only adjusts it.

    SCALE NOTE: makeable scores are 1000+v and doomed are v*g^late (~0-15), while this term is a sum of
    task values (~15 each). So it reorders WITHIN the makeable tier as intended, but it is large relative
    to doomed scores -- doomed ordering may shift on others' value. Tunable via LOOKAHEAD_W.
    """

    LOOKAHEAD_DEPTH = 2      # 1 == greedy (current champion). 2 = consider the next robot.
    LOOKAHEAD_W = 1.0        # weight on value left for the others
    FREE_HORIZON = 0         # 0 = only CURRENTLY-free robots. >0 = also count busy robots expected to
                             # free up within this many steps, so a task can be left for a robot that is
                             # about to become available and better placed. SEPARATE KNOB because it
                             # carries a risk the robot-breadth knob does not: holding a task for a
                             # robot whose free-time we mis-estimate leaves the task idle, and
                             # time-to-free is noisy (measured MAE ~14 on a mean of 27).
                             # NOT layer 2: we are CO-DECIDING that robot's assignment, not predicting
                             # what it would independently choose.

    def _soon_free(self):
        """Busy AGVs expected to free up within FREE_HORIZON, anchored at where they will free up.

        time-to-free = len(path) + LOAD_TIME + dist(path_end -> nearest dock); measured best of three
        estimators (MAE 13.8 / r 0.50) vs len(path) alone (15.2 / 0.45). The anchor is the DOCK, not
        path[-1] -- path[-1] is the robot's own SHELF for 37% of busy AGVs, a cell it merely passes
        through, which is the mistake the original layer 2 made.
        """
        h = self.FREE_HORIZON
        if h <= 0:
            return []
        out = []
        for a in self.agvs:
            path = getattr(a, "path", None)
            if not (a.busy and path):
                continue
            ex, ey = path[-1]
            dx, dy = min(self.env.goals, key=lambda g: abs(g[0] - ex) + abs(g[1] - ey))
            t_free = len(path) + self.LOAD_TIME + abs(ex - dx) + abs(ey - dy)
            if t_free <= h:
                out.append((t_free, _Pt(dx, dy)))       # anchored where it becomes free
        return sorted(out, key=lambda r: r[0])

    def _task_score_adjust(self, shelf, best_r):
        """Opportunity cost of taking `shelf`: value it denies the robots behind me.

        The two knobs get SEPARATE budgets -- they used to share one truncated list, which made the
        horizon knob's reach depend on the depth knob (it only fired when free robots ran out, 48% of
        calls). Now:
          DEPTH-1   CURRENTLY-FREE robots, counted at FULL weight (certain, available now)
          ALL       SOON-FREE robots within FREE_HORIZON, DISCOUNTED by (1 - t_free/H)
        The discount replaces a hard cutoff: a robot freeing in 3 steps competes almost fully for the
        same tasks; one freeing in 40 barely does, because the queue will have turned over by then. A
        hard cutoff has to count it either fully or not at all, and both are wrong.
        """
        if self.LOOKAHEAD_W == 0.0:
            return 0.0
        if self.LOOKAHEAD_DEPTH <= 1 and self.FREE_HORIZON <= 0:
            return 0.0                                   # exactly the champion (sanity arm)
        ctx = getattr(self, "_look_ctx", None)
        if not ctx:
            return 0.0
        others, taken = ctx
        used = {shelf.id}
        total = 0.0

        def _best(anchor):
            cands = [c for c in self.env.request_queue
                     if c.id not in taken and c.id not in used]
            if not cands:
                return None
            top = _rt.cheap_screen(anchor, cands, task_value, keep=1)
            return top[0] if top else None

        for a in list(others)[:max(0, self.LOOKAHEAD_DEPTH - 1)]:   # certain + immediate
            nxt = _best(a)
            if nxt is None:
                break
            used.add(nxt.id)
            total += task_value(nxt)

        h = float(self.FREE_HORIZON)
        if h > 0:
            for (t_free, anchor) in self._soon_free():              # uncertain + later -> discounted
                nxt = _best(anchor)
                if nxt is None:
                    break
                used.add(nxt.id)
                total += max(0.0, 1.0 - t_free / h) * task_value(nxt)
        return self.LOOKAHEAD_W * total


class _Depth1(PartACongestionDepthController):
    LOOKAHEAD_DEPTH = 1      # SANITY ARM: must be 30/30 ties with the champion


class _Depth2(PartACongestionDepthController):
    LOOKAHEAD_DEPTH = 2


class _Depth3(PartACongestionDepthController):
    LOOKAHEAD_DEPTH = 3


class _Depth5(PartACongestionDepthController):
    LOOKAHEAD_DEPTH = 5


class _D2H0(PartACongestionDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 2, 0


class _D2H20(PartACongestionDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 2, 20


class _D3H0(PartACongestionDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 3, 0


class _D3H20(PartACongestionDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 3, 20


class PartACongestionTrueDepthController(PartACongestionDepthController):
    """Lookahead using the REAL funnel score for the other robots, not the cheap-screen proxy.

    The proxy version (PartACongestionDepthController) came back NEGATIVE across the whole grid
    (d2h0 -5.07 p=0.022 ... d3h20 -5.17). But it guessed what other robots want with
    `value - 0.15*distance`, which is the SHORTLISTING heuristic, not the thing the funnel actually
    maximises. So that result may indict the proxy rather than the idea.

    Here each other robot's value is its TRUE funnel score: Yen k-routes -> congestion-aware route pick
    -> rollout (partner ETA, sync wait) -> makeable/doomed deadline tier. Identical to what that robot
    would compute for itself.

    AFFORDABILITY: another robot's scores do not depend on WHICH task I take -- only on that task being
    removed from its pool. So the table is built ONCE per dispatch turn (TOP_K candidates x the next
    DEPTH-1 robots) and every one of my candidates just re-maxes over it with one task excluded. Cost is
    ~(DEPTH-1)*TOP_K real evaluations per turn instead of per candidate.

    RECURSION: _true_score deliberately omits _task_score_adjust -- otherwise scoring another robot
    would re-enter this lookahead forever.
    """

    TOP_K = 5                # candidates per other robot to score for real

    def _true_score(self, agv, shelf, now, G):
        routes = _rt.k_shortest_routes(G, (agv.x, agv.y), (shelf.x, shelf.y), k=self.K_ROUTES)
        if not routes:
            return None
        best_r = self._pick_route(routes, shelf, now)
        my_arrival = len(best_r) - 1
        committed, free, busy = self._partner_groups(shelf)
        p_arr, reason = _ro.partner_eta(shelf, now, committed=committed, free=free, busy=busy)
        res = _ro.rollout_task(self.env, shelf, [agv], [], now=now, load_time=self.LOAD_TIME,
                               my_arrival=my_arrival, partner_arrival=p_arr)
        v = task_value(shelf)
        if shelf.deadline is None:
            score = 500.0 + v
        else:
            proj_late = (now + res["finish"]) - shelf.deadline
            score = self._deadline_score(v, proj_late, shelf, best_r)
        score -= self.W_SYNC * res["my_wait"]
        if reason == "unserviceable":
            score -= 1e6
        return score

    def _lookahead_table(self):
        """[(anchor_weight, [(shelf_id, true_score), ...]), ...] for the robots behind me."""
        seq = getattr(self, "_look_seq", 0)
        if getattr(self, "_lk_seq", None) == seq:
            return self._lk_table
        ctx = getattr(self, "_look_ctx", None)
        table = []
        if ctx:
            others, taken = ctx
            now = self.timestep
            G = _rt.build_agv_graph(self.env)
            pool = [s for s in self.env.request_queue if s.id not in taken]
            entries = [(1.0, a) for a in list(others)[:max(0, self.LOOKAHEAD_DEPTH - 1)]]
            h = float(self.FREE_HORIZON)
            if h > 0:
                for (t_free, anchor) in self._soon_free():
                    entries.append((max(0.0, 1.0 - t_free / h), anchor))
            for (w, a) in entries:
                short = _rt.cheap_screen(a, pool, task_value, keep=self.TOP_K)
                scored = []
                for sh in short:
                    sc = self._true_score(a, sh, now, G)
                    if sc is not None:
                        scored.append((sh.id, sc))
                if scored:
                    table.append((w, scored))
        self._lk_seq, self._lk_table = seq, table
        return table

    def _task_score_adjust(self, shelf, best_r):
        if self.LOOKAHEAD_W == 0.0:
            return 0.0
        if self.LOOKAHEAD_DEPTH <= 1 and self.FREE_HORIZON <= 0:
            return 0.0                                   # exactly the champion (sanity arm)
        used = {shelf.id}
        total = 0.0
        for (w, scored) in self._lookahead_table():
            avail = [(sid, sc) for (sid, sc) in scored if sid not in used]
            if not avail:
                continue
            sid, sc = max(avail, key=lambda r: r[1])
            used.add(sid)
            total += w * sc
        return self.LOOKAHEAD_W * total


class _T1(PartACongestionTrueDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 1, 0     # SANITY: must tie champion 30/30


class _T2H0(PartACongestionTrueDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 2, 0


class _T3H0(PartACongestionTrueDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 3, 0


class _T2H20(PartACongestionTrueDepthController):
    LOOKAHEAD_DEPTH, FREE_HORIZON = 2, 20


class PartACongestionExploreController(PartACongestionController):
    """HINDSIGHT-ORACLE explorer: the champion with RANDOMIZED assignment decisions.

    Purpose (scripts/oracle_assign.py): run MANY rollouts of the SAME seed, each perturbing WHICH task
    each robot commits to (uniform among the top-K scored candidates) and optionally the ORDER robots
    pick in, then take the BEST rollout. That best is a LOWER BOUND on the hindsight-optimal assignment
    schedule for that seed -- the ceiling on what ANY assignment policy (greedy, matching, learned,
    AlphaZero-style search) could achieve within this funnel's structure. If best-of-hundreds barely
    clears the champion, the assignment ceiling is close and the direction is settled cheaply.

    Everything else -- routes, congestion map, deadline tiers, sync, adherence -- is untouched, so the
    perturbation isolates the ASSIGNMENT layer. Policy RNG is separate from the env's.
    """

    def __init__(self, env, rng_seed=0, top_k=3, shuffle_order=False):
        super().__init__(env)
        self._xrng = np.random.RandomState(rng_seed)
        self._top_k = max(1, int(top_k))
        self._shuffle = bool(shuffle_order)

    def _pick_winner(self, scored):
        k = min(self._top_k, len(scored))
        return scored[int(self._xrng.randint(k))]

    def _order_free_agvs(self, free_agvs):
        order = super()._order_free_agvs(free_agvs)
        if self._shuffle:
            order = list(order)
            self._xrng.shuffle(order)
        return order


class PartACongestionRateController(PartACongestionController):
    """Champion, but the MAKEABLE tier ranks by VALUE RATE (value per step of robot time), not raw value.

    User's hypothesis, supported by the assignment oracle (+25.8 uniform / large residual under
    day-list) and the wage argument: the scorer maximises value per PICK while the scarce resource is
    robot-MINUTES. A v=12 task 40 steps away beat a v=11 task 10 steps away every time, though the near
    one pays 4x more per step.

    Change (ONE method): makeable score = 1000 + RATE_SCALE * v / completion, where completion is the
    task's own traffic-aware finish estimate (recovered exactly from proj_late + deadline - now, i.e.
    finish_s -- includes fetch route length, picker wait, dock leg, LOAD_TIME pad, _finish_delay).
    RATE_SCALE ~= mean completion, so a task of average duration scores ~its raw value; quicker tasks
    boosted, slower penalised. Doomed tier, tiers themselves, sync, routes: unchanged.
    """

    RATE_SCALE = 40.0

    def _deadline_score(self, v, proj_late, shelf, best_r):
        if proj_late <= 0:
            completion = max(1.0, proj_late + (shelf.deadline - self.timestep))   # == finish_s
            return 1000.0 + self.RATE_SCALE * v / completion
        g = self.DECAY_G if shelf.hardness is None else shelf.hardness
        return v * (g ** proj_late)


class _Rate20(PartACongestionRateController):
    RATE_SCALE = 20.0


class _Rate40(PartACongestionRateController):
    RATE_SCALE = 40.0


class _Rate80(PartACongestionRateController):
    RATE_SCALE = 80.0


class PartACongestionBlendController(PartACongestionRateController):
    """VALUE + VALUE-RATE blend in the makeable tier: score = 1000 + v + S*v/completion = v*(1 + S/c).

    Pure rate (v*S/c) lets time dominate value without bound -- a v=3 task in 6 steps outranks a v=15
    task in 40. The blend keeps absolute value on the ticket: time contributes a BOUNDED multiplier
    (at S=40, roughly x1.7 for slow tasks to x2.6 for quick ones). S=0 is exactly the champion;
    S->inf approaches pure rate. Tuned on seeds 0-29, VERDICT ONLY on held-out seeds (100-129).
    """

    BLEND_S = 40.0

    def _deadline_score(self, v, proj_late, shelf, best_r):
        if proj_late <= 0:
            completion = max(1.0, proj_late + (shelf.deadline - self.timestep))
            return 1000.0 + v + self.BLEND_S * v / completion
        g = self.DECAY_G if shelf.hardness is None else shelf.hardness
        return v * (g ** proj_late)


class _Blend10(PartACongestionBlendController):
    BLEND_S = 10.0


class _Blend20(PartACongestionBlendController):
    BLEND_S = 20.0


class _Blend40(PartACongestionBlendController):
    BLEND_S = 40.0


class _Blend80(PartACongestionBlendController):
    BLEND_S = 80.0


class _Rate160(PartACongestionRateController):
    RATE_SCALE = 160.0


class _R80Explore(PartACongestionExploreController):
    """Explorer (random top-K assignment) ON TOP OF rate80 scoring — for re-running the day-list
    assignment oracle against the NEW baseline. Measures how much of the +5.6% assignment ceiling
    the value-rate fix captured: gap(rate80 -> its own best-of-120) vs the old gap(value -> best)."""
    RATE_SCALE = 80.0
    _deadline_score = PartACongestionRateController._deadline_score


class PartACongestionAdaptiveRateController(PartACongestionRateController):
    """LOAD-ADAPTIVE pricing: rate when overloaded, value when the queue thins.

    Measured 2026-07-22: rate80 +10.78 (t=4.36) in the always-full uniform regime, but a WASH on
    day-list (-1.0%). Hypothesis: rate is the currency of OVERLOAD (speed converts into extra tasks
    collected), value the currency of UNDERLOAD (speed you don't need buys value thrown away). The
    weight follows live backlog:  w = min(1, queue_len / (ADAPT_K * n_AGVs));
    score = 1000 + (1-w)*v + w*RATE_SCALE*v/completion.  K->0 = rate80, K->inf = pure value.
    """

    ADAPT_K = 2.0

    def _deadline_score(self, v, proj_late, shelf, best_r):
        if proj_late <= 0:
            completion = max(1.0, proj_late + (shelf.deadline - self.timestep))
            w = min(1.0, len(self.env.request_queue) / (self.ADAPT_K * max(1, len(self.agvs))))
            return 1000.0 + (1.0 - w) * v + w * self.RATE_SCALE * v / completion
        g = self.DECAY_G if shelf.hardness is None else shelf.hardness
        return v * (g ** proj_late)


class _Adapt2(PartACongestionAdaptiveRateController):
    ADAPT_K = 2.0


class _Adapt4(PartACongestionAdaptiveRateController):
    ADAPT_K = 4.0


class _ExploreArm(PartACongestionExploreController):
    """The explorer AS A POLICY (not an oracle): random uniform pick among top-3 scored candidates,
    robot order shuffled, fixed policy RNG. Baseline showing what raw perturbation is worth on
    average -- the oracle's best-of-120 is NOT this; this is one rollout's expected behaviour."""

    def __init__(self, env):
        super().__init__(env, rng_seed=12345, top_k=3, shuffle_order=True)


class _VScreen(PartACongestionController):
    """'Value on both ends': PURE-VALUE shortlist (no distance discount) + value final rank. The one
    untested cell of the matrix -- every other arm kept the 0.15-distance screen, which excludes the
    #1-value task 60.8% of the time but is also the ONLY place distance enters task choice."""
    SCREEN_DISCOUNT = 0.0


class _VSRate80(_Rate80):
    """Pure-value SCREEN + rate80 final rank."""
    SCREEN_DISCOUNT = 0.0


class _VSBlend40(_Blend40):
    """Pure-value SCREEN + blend40 final rank (the day-list micro-winner)."""
    SCREEN_DISCOUNT = 0.0


class PartACongestionUrgencyController(PartACongestionController):
    """BOUNDED urgency bonus WITHIN the makeable tier -- targets the oracle's RESCUED category
    (+84 of the +113 gap: valuable orders delivered 2-10 steps late because within-tier ranking is
    value-only and deadline is a mere tie-break).

    NOT EDF: the hard makeable/doomed fence runs FIRST -- only tasks the rollout certifies as
    achievable enter this competition; hopeless-urgent tasks are in the doomed tier, unchanged.
    NOT a re-sort: the bonus is CAPPED at URG_W (~ inside the 1-15 value spread) and ramps in only
    when projected spare < URG_S0. A tight v=14 can now beat a loose v=15 (the seed-3 two-step miss);
    a tight v=3 still cannot jump a loose v=12. Guard against boundary optimism (estimates are
    empty-world, ~16 steps optimistic): a capped bonus caps the damage; acceptance test is
    rescued-up with LOST~=0 via the differ.
    """

    URG_W = 4.0
    URG_S0 = 40.0

    def _deadline_score(self, v, proj_late, shelf, best_r):
        if proj_late <= 0:
            spare = -proj_late
            return 1000.0 + v + self.URG_W * max(0.0, 1.0 - spare / self.URG_S0)
        g = self.DECAY_G if shelf.hardness is None else shelf.hardness
        return v * (g ** proj_late)


class _Urg2(PartACongestionUrgencyController):
    URG_W = 2.0


class _Urg4(PartACongestionUrgencyController):
    URG_W = 4.0


class _Urg8(PartACongestionUrgencyController):
    URG_W = 8.0


class PartACongestionProxController(PartACongestionUrgencyController):
    """CAPTURED-category fix: flat, capped PROXIMITY bonus on top of urg8.

    The differ showed +59 of the day-list oracle gap = low-value orders the champion NEVER delivers
    (starved by the value auction until their deadlines die), which the oracle sweeps EARLY when a
    robot is nearby (shelf 97: v=4.7, dl=418, oracle t=163). Urgency cannot catch these (ramp wakes in
    the last 40 steps of slack -- too late, and where estimates are most optimistic; seed-3 acceptance:
    zero captured collected). Aging cannot either (day-list orders all age identically from t=0).
    The real differentiator is FETCH COST BY POSITION: a 6-step errand for v=4.7 is a fine wage.

    NOT rate80 back from the dead: rate re-priced everything multiplicatively and drowned value
    (-9 on day-list). This is the urg8 pattern -- a FLAT bonus, capped at PROX_W, waking only within
    PROX_D0 steps: v=5 next door can beat v=8 across the floor, never v=12.
    """

    PROX_W = 4.0
    PROX_D0 = 15.0

    def _deadline_score(self, v, proj_late, shelf, best_r):
        base = super()._deadline_score(v, proj_late, shelf, best_r)
        if proj_late <= 0 and best_r:
            fetch = max(0, len(best_r) - 1)
            base += self.PROX_W * max(0.0, 1.0 - fetch / self.PROX_D0)
        return base


class _U8P2(PartACongestionProxController):
    URG_W, PROX_W = 8.0, 2.0


class _U8P4(PartACongestionProxController):
    URG_W, PROX_W = 8.0, 4.0


class _U8P8(PartACongestionProxController):
    URG_W, PROX_W = 8.0, 8.0


class _P4(PartACongestionProxController):
    URG_W, PROX_W = 0.0, 4.0     # prox alone, for attribution


class PartACongestionSeqController(PartACongestionUrgencyController):
    """SEQUENCER v0: rollout re-ranking of the top-K first moves (Bertsekas-style rollout).

    The champion pipeline runs unchanged (tiers, urgency, congestion, sync) and produces its ranked
    candidates; then the TOP-K first moves are re-ranked by SIMULATING THE FLEET FORWARD and taking
    total banked on-time value. The simulation advances state -- queue consumed, deadlines ticked,
    robots re-freed at estimated times/positions, day-end capped -- so 'what can I chain into' is
    evaluated under FUTURE conditions, not today's (the chaining-bonus error), and other robots'
    future picks are CO-DECIDED inside the branch, not predicted (the lookahead error). The tail is
    never executed: only the first move commits (receding horizon); estimate error (+-14/task,
    compounding) stays in the ranking, never in the actions.

    SEQ_DEPTH = simulation horizon in avg-task units (75 steps each). 0 = champion exactly (sanity).
    """

    URG_W = 8.0                 # build on the confirmed day-list champion
    SEQ_DEPTH = 3
    SEQ_TOPK = 5
    TASK_SPAN = 75              # horizon unit ~ one task's span

    DEV_MARGIN = 0.0        # THROUGHPUT gate: an alternative must beat the incumbent's simulated
                            # banked value by this much before the sim may overrule Part A. Filters
                            # sim noise (sq5's deviations were 15-15 coin flips at margin 0).
    SCORE_TOL = float("inf")  # UTILITY gate: only alternatives within this much of the incumbent's
                            # own funnel score (tier+value+urgency-sync) are considered at all.
                            # Any finite value forbids crossing the ~1000-point deadline-tier gap.

    def _pick_winner(self, scored):
        if self.SEQ_DEPTH <= 0 or len(scored) < 2:
            return scored[0]
        incumbent = scored[0]
        inc_score = incumbent[0]
        inc_v = self._simulate_branch(incumbent)
        best, bestv = incumbent, inc_v
        for tup in scored[1:self.SEQ_TOPK]:
            if inc_score - tup[0] > self.SCORE_TOL:
                continue                            # utility sacrifice too large -> not a candidate
            v = self._simulate_branch(tup)
            if v > bestv:
                best, bestv = tup, v
        if best is not incumbent and bestv < inc_v + self.DEV_MARGIN:
            return incumbent                        # throughput advantage too small -> stick with Part A
        return best

    # ---- forward simulation under analytic estimates --------------------------------
    def _sim_choose_picker(self, arr, sh, pickers, pending):
        """Which picker serves this imagined task -> (index, ready_time). Default: the SOONEST that can
        physically get there. Hook so a subclass can ask the sharper question -- would that picker
        actually CHOOSE this task, or is it off serving something richer?"""
        bestj, bestready = -1, 1e18
        for j, (pf, px, py) in enumerate(pickers):
            ready = max(arr, pf + abs(px - sh.x) + abs(py - sh.y))
            if ready < bestready:
                bestj, bestready = j, ready
        return bestj, bestready

    def _sim_completion(self, x, y, sh):
        fetch = abs(x - sh.x) + abs(y - sh.y)
        return fetch + self.LOAD_TIME + _ro.nearest_dock_dist(self.env, sh.x, sh.y)

    SIM_BIAS = True         # fix 3: live measured pace bias in the sim clock
    SIM_DECAY_CREDIT = False  # pay decayed credit for LATE orders in the sim (shaping experiment)
    BIAS_PRIOR = 0.0        # sim clock bias before the live EMA initializes (0 = legacy fantasy time)
    SIM_PICKERS = True      # fix 1: pickers as resources (False = instant loading, old behaviour)
    SIM_FREEDPOS = True     # fix 2: re-enter at real storage slot (False = at the dock, old behaviour)

    def _sim_bank(self, sh, fin):
        """PER-ORDER banking (crater fix, 2026-07-22 autopsy): a batched shelf's sim value was
        all-or-nothing against its EARLIEST deadline -- miss it by one step, credit ZERO for the whole
        batch -- while reality pays each stacked order against its OWN deadline. The sim therefore
        deferred slightly-tight batches forever (all 4 crater seeds: a fat batch deferred from commit
        #0 until dead). Now the sim banks exactly as the world pays."""
        if fin > 500:
            return 0.0
        g = sh.hardness if getattr(sh, "hardness", None) is not None else self.DECAY_G
        dm = getattr(self.env, "demand_model", None)
        if dm is not None:
            lst = dm.pending.get(getattr(sh, "id", None))
            if lst:
                tot = 0.0
                for o in lst:
                    if fin <= o.deadline:
                        tot += o.value
                    elif self.SIM_DECAY_CREDIT:
                        # SHAPING (user experiment): pay DECAYED credit for late orders inside the
                        # imagination, even though the real metric pays 0 -- "slightly late" branches
                        # rank above "abandoned" branches. Risk: chasing phantom value. Under test.
                        tot += o.value * (g ** (fin - o.deadline))
                return tot
        if sh.deadline is not None and fin <= sh.deadline:
            return task_value(sh)
        if self.SIM_DECAY_CREDIT and sh.deadline is not None:
            return task_value(sh) * (g ** (fin - sh.deadline))
        return 0.0

    def _sim_delay_bias(self):
        """FIX 3: live calibration -- the fleet's measured bias between predicted and realized
        finishes (_delay_ema, computed on every delivery, previously unused). Applied to every
        simulated completion so the sim's clock tracks today's ACTUAL pace."""
        if not self.SIM_BIAS:
            return 0.0
        if getattr(self, "_delay_inited", False):
            return float(self._delay_ema)
        return float(self.BIAS_PRIOR)   # WARM-START: before any delivery exists to calibrate the clock,
                                        # use the measured historical pace bias (~+15.8). All 8 worst
                                        # error seeds diverged at t=0 when bias was 0 = fantasy time.

    def _sim_step_bias(self, t, npending, pickers):
        """Per-completion delay bias inside the imagined day. DEFAULT = the flat scalar (_const_bias),
        so every existing arm is bit-identical. The pace-step override makes it STATE-CONDITIONAL on
        the imagined fleet state at imagined time t (diurnal phase + queue pressure + free pickers),
        so makeable/doomed calls track the imagined rush across the whole horizon, not just now."""
        return self._const_bias

    def _sim_pickers_init(self):
        """FIX 1: pickers as RESOURCES inside the sim -- (free_time, x, y) each. Busy pickers enter
        at their estimated load moment at their target cell."""
        out = []
        now = float(self.timestep)
        for p in self.pickers:
            path = getattr(p, "path", None)
            if path:
                ex, ey = path[-1]
                out.append([now + len(path) + self.LOAD_TIME, ex, ey])
            else:
                out.append([now, p.x, p.y])
        return out

    def _sim_docks_init(self):
        """STATIONS AS A CONSUMED RESOURCE (2026-08-08, opt-in `SIM_DOCK_RES`).

        The rollout modelled a delivery as `rendezvous + LOAD_TIME + nearest_dock_dist`, i.e. arriving
        at a station cost DISTANCE ONLY. Pickers were already tracked as resources with per-picker ready
        times, but stations were not: in the imagination all docks are infinitely parallel, so eight
        AGVs can deliver to the same cell in the same instant for free.

        That is exactly the quantity that jams the fleet. Measured on seed 13: all 8 AGVs loaded and
        converging, the fleet frozen for 108 steps with two of three stations standing EMPTY. The
        planner could not see the queue it was creating, because in its model arriving is free -- so no
        routing or geometry fix can reach it. Docks now carry a ready time like pickers do, and a branch
        that would queue behind others shows a later finish and loses to one that picks a free dock.

        Returns [free_time, x, y] per station; a dock currently occupied by a carrying AGV enters at
        that robot's estimated service completion rather than now."""
        env = self.env
        now = float(self.timestep)
        svc = float(getattr(env, "station_service_steps", 0.0)) or 1.0
        occupied = {}
        for a in getattr(env, "agents", []):
            if getattr(a, "carrying_shelf", None) is not None:
                occupied[(a.x, a.y)] = now + svc
        return [[occupied.get((gx, gy), now), gx, gy] for (gx, gy) in env.goals]

    def _sim_pick_dock(self, arrive_ready, sh, docks):
        """Soonest-available dock for a shelf: travel there, then wait for it to free.
        Falls back to plain nearest-dock distance when the resource model is off."""
        env = self.env
        best_j, best_fin = -1, 1e18
        for j, (df, dx, dy) in enumerate(docks):
            travel = abs(sh.x - dx) + abs(sh.y - dy)
            fin = max(arrive_ready + travel, df)
            if fin < best_fin:
                best_j, best_fin = j, fin
        return best_j, best_fin

    def _sim_freed(self, sh):
        """FIX 2: where and when a robot ACTUALLY becomes free after delivering `sh`: it hauls the
        shelf from the dock to the nearest empty storage slot (real re-entry geography), not the dock."""
        env = self.env
        dx, dy = _ro.nearest_dock(env, sh.x, sh.y)
        if not self.SIM_FREEDPOS:
            return _ro.nearest_dock_dist(env, sh.x, sh.y), dx, dy    # old behaviour: dock re-entry
        sx, sy = _ro.nearest_empty_storage(env, dx, dy)
        return abs(dx - sx) + abs(dy - sy), sx, sy      # (return_dist, slot_x, slot_y)

    def _sim_core(self, pins, extra_taken=(), probe_delay=None, include_free=False, trace=None):
        """Forward simulation shared by single and joint branches. pins = [(rx, ry, shelf,
        fin_override)] -- first moves fixed; fin_override (the funnel's own picker-aware estimate)
        used when provided, else the picker-aware completion is computed here."""
        import heapq
        env = self.env
        now = float(self.timestep)
        horizon = min(now + self.SEQ_DEPTH * self.TASK_SPAN, 500.0)
        bias = self._sim_delay_bias()
        self._const_bias = bias          # default (flat) bias; _sim_step_bias may override per-completion
        pickers = self._sim_pickers_init()
        docks = self._sim_docks_init() if getattr(self, "SIM_DOCK_RES", False) else None
        taken = set(self.assigned_items.values()) | {_p[2].id for _p in pins} | set(extra_taken)
        pending = [sh for sh in env.request_queue if sh.id not in taken]
        heap, idx, banked = [], 0, 0.0
        owners = {}

        def rendezvous(t, x, y, sh):
            """Picker-aware completion: pick the picker that can meet the AGV soonest; returns
            (finish_time, picker_index, ready_time)."""
            arr = t + abs(x - sh.x) + abs(y - sh.y)
            b = self._sim_step_bias(t, len(pending), pickers)   # per-completion (flat by default)
            if not self.SIM_PICKERS:
                if docks is not None:
                    _dj, _dfin = self._sim_pick_dock(arr + self.LOAD_TIME, sh, docks)
                    return _dfin + b, None, arr
                return arr + self.LOAD_TIME + _ro.nearest_dock_dist(env, sh.x, sh.y) + b, None, arr
            bestj, bestready = self._sim_choose_picker(arr, sh, pickers, pending)
            if docks is not None:
                _dj, _dfin = self._sim_pick_dock(bestready + self.LOAD_TIME, sh, docks)
                docks[_dj][0] = _dfin + float(getattr(env, "station_service_steps", 0.0) or 0.0)
                fin = _dfin + b
            else:
                fin = bestready + self.LOAD_TIME + _ro.nearest_dock_dist(env, sh.x, sh.y) + b
            return fin, bestj, bestready

        for _k, _pin in enumerate(pins):
            rx, ry, sh, fov = _pin[0], _pin[1], _pin[2], _pin[3]
            # OPTIONAL 5th element = the time this pinned robot actually becomes free. Needed for JOINT
            # branches, where the partner is still busy and must not be evaluated as if free at `now`
            # (a few steps of optimism straddles the 1000-pt makeable/doomed cliff). Defaults to `now`,
            # so every existing single-pin caller is unchanged.
            _t0 = _pin[4] if len(_pin) > 4 else now
            if fov is not None:
                fin = fov + self._sim_step_bias(now, len(pending), pickers)
                jj = None
            else:
                fin, jj, ready = rendezvous(_t0, rx, ry, sh)
            if jj is not None:
                pickers[jj] = [ready + self.LOAD_TIME, sh.x, sh.y]
            _b = self._sim_bank(sh, fin)
            banked += _b
            _own = getattr(self, "_pin_owner_ids", None)
            owners[idx] = _own[_k] if _own else -1
            if trace is not None:
                trace.append((fin, sh.id, _b, owners[idx]))
            ret, sx, sy = self._sim_freed(sh)
            heapq.heappush(heap, (fin + ret, idx, sx, sy)); idx += 1
        pinned_ids = set()
        for _p in pins:                      # pins may carry an optional 5th element (free time)
            pinned_ids.add(_p[2].id)
        pin_robots = {id(r) for r in ()}
        for a in self.agvs:
            if getattr(self, "_sim_pin_agents", None) and a.id in self._sim_pin_agents:
                continue
            extra = probe_delay[1] if (probe_delay and (probe_delay[0] == a.id or probe_delay[0] == -1)) else 0.0
            path = getattr(a, "path", None)
            if a.busy and path:
                ex, ey = path[-1]
                gx, gy = _ro.nearest_dock(env, ex, ey)
                owners[idx] = a.id
                heapq.heappush(heap, (now + len(path) + self.LOAD_TIME + abs(ex - gx) + abs(ey - gy)
                                      + self._sim_step_bias(now, len(pending), pickers) + extra,
                                      idx, gx, gy)); idx += 1
            elif include_free and not a.busy:
                owners[idx] = a.id
                heapq.heappush(heap, (now + extra, idx, a.x, a.y)); idx += 1
        g = self.DECAY_G
        arrivals = self._future_arrivals(now, horizon)
        ai = 0
        while heap and (pending or ai < len(arrivals)):
            t, i, x, y = heapq.heappop(heap)
            if t > horizon:
                break
            while ai < len(arrivals) and arrivals[ai][0] <= t:
                pending.append(arrivals[ai][1]); ai += 1
            if not pending:
                heapq.heappush(heap, (t + 5.0, i, x, y)); continue
            best_s, best_sc, best_fin, best_j, best_ready = None, -1e18, 0.0, -1, 0.0
            for sh in pending:
                fin2, jj, ready = rendezvous(t, x, y, sh)
                if sh.deadline is None:
                    sc = 500.0 + task_value(sh)
                elif fin2 <= sh.deadline:
                    sc = self.TIER_GAP + task_value(sh) + self.URG_W * max(0.0, 1.0 - (sh.deadline - fin2) / self.URG_S0)
                else:
                    sc = task_value(sh) * (g ** (fin2 - sh.deadline))
                if sc > best_sc:
                    best_s, best_sc, best_fin, best_j, best_ready = sh, sc, fin2, jj, ready
            if best_s is None:
                break
            if best_j is not None:
                pickers[best_j] = [best_ready + self.LOAD_TIME, best_s.x, best_s.y]
            _b = self._sim_bank(best_s, best_fin)
            banked += _b
            if trace is not None:
                trace.append((best_fin, best_s.id, _b, owners.get(i, -1)))
            pending.remove(best_s)
            ret, sx, sy = self._sim_freed(best_s)
            heapq.heappush(heap, (best_fin + ret, i, sx, sy))
        return banked

    def _simulate_branch(self, tup):
        _sc, first_shelf, _route, _routes, feat = tup
        me = self._cur_agv
        self._sim_pin_agents = {me.id}
        fov = float(self.timestep) + float(feat["pred_finish"]) + self._finish_delay(_route)
        v = self._sim_core([(me.x, me.y, first_shelf, fov)])
        self._sim_pin_agents = None
        return v

class _Sq0(PartACongestionSeqController):
    SEQ_DEPTH = 0        # SANITY: must tie urg8 exactly


class _Sq1(PartACongestionSeqController):
    SEQ_DEPTH = 1


class _Sq2(PartACongestionSeqController):
    SEQ_DEPTH = 2


class _Sq3(PartACongestionSeqController):
    SEQ_DEPTH = 3


class _Sq5(PartACongestionSeqController):
    SEQ_DEPTH = 5


class _Sq8(PartACongestionSeqController):
    SEQ_DEPTH = 8


class _S5M2(PartACongestionSeqController):
    SEQ_DEPTH, DEV_MARGIN = 5, 2.0


class _S5M5(PartACongestionSeqController):
    SEQ_DEPTH, DEV_MARGIN = 5, 5.0


class _S5M10(PartACongestionSeqController):
    SEQ_DEPTH, DEV_MARGIN = 5, 10.0


class _S5T2(PartACongestionSeqController):
    SEQ_DEPTH, SCORE_TOL = 5, 2.0


class _S5T5(PartACongestionSeqController):
    SEQ_DEPTH, SCORE_TOL = 5, 5.0


class _S5T10(PartACongestionSeqController):
    SEQ_DEPTH, SCORE_TOL = 5, 10.0


    # (default: no future arrivals -- correct for day-list, where the whole day is known at t=0)


def _default_future_arrivals(self, now, horizon):
    return []


PartACongestionSeqController._future_arrivals = _default_future_arrivals


class _FakeOrder:
    __slots__ = ("x", "y", "value", "deadline", "id", "hardness")

    def __init__(self, x, y, v, dl, oid):
        self.x, self.y, self.value, self.deadline, self.id, self.hardness = x, y, v, dl, oid, None


class _Sq5S(PartACongestionSeqController):
    """Sequencer depth 5 for the STREAM: base policy = plain champion (URG_W=0 -- urgency is
    day-list-only), NO arrivals in the horizon. The frozen-arrival CONTROL arm."""
    URG_W, SEQ_DEPTH = 0.0, 5


class _SA5(_Sq5S):
    """Sequencer depth 5 + SYNTHETIC ARRIVALS inside the horizon, drawn from the demand model's
    statistical shape (rate*diurnal, popularity weights, rush/std value-deadline mix). The imagined
    future is generated ONCE PER DISPATCH ROUND (cached, fixed rng per round) and SHARED across all
    branches, so rankings compare like against like. INFO FLAG: reads the true model parameters --
    deployment would estimate these online; this is the does-it-help-at-all test."""

    def _future_arrivals(self, now, horizon):
        key = int(self.timestep)
        if getattr(self, "_arr_key", None) == key:
            return self._arr_cache
        dm = getattr(self.env, "demand_model", None)
        out = []
        if dm is not None and getattr(dm, "mode", "stream") == "stream":
            rng = np.random.RandomState(100000 + key)
            ids = list(dm.wt.keys())
            w = np.array([dm.wt[i] for i in ids], dtype=float)
            w /= w.sum()
            sh_by_id = {sh.id: sh for sh in dm.shelfs}
            oid = -1
            t = float(now)
            while t < horizon:
                lam = dm.rate * dm._diurnal(t)
                if rng.random() < lam:
                    sid = ids[int(rng.choice(len(ids), p=w))]
                    src = sh_by_id[sid]
                    rush = rng.random() < dm.rush_frac
                    lo, hi = dm.rush_slack if rush else dm.std_slack
                    v = float(rng.uniform(dm.value_lo, dm.value_hi)) * (dm.rush_value_mult if rush else 1.0)
                    out.append((t, _FakeOrder(src.x, src.y, v, t + rng.randint(lo, hi), oid)))
                    oid -= 1
                t += 1.0
        self._arr_key, self._arr_cache = key, out
        return out


class PartACongestionPreemptController(PartACongestionController):
    """FETCH-LEG RE-DECISION on new arrivals (user's rule): a robot may be released from its
    assignment ONLY while still traveling to the shelf -- never when carrying, delivering, or already
    at the rendezvous -- and only when a NEWLY-ARRIVED task beats its current one (cheap-screen score
    from the robot's CURRENT position) by SWITCH_MARGIN. Release makes it eligible; the full funnel
    re-decides (and may re-pick the same task). Margin guards against ping-ponging."""

    SWITCH_MARGIN = 3.0

    def _assign_tasks(self):
        env = self.env
        cur_ids = {sh.id for sh in env.request_queue}
        new_ids = cur_ids - getattr(self, "_known_ids", cur_ids)
        self._known_ids = cur_ids
        if new_ids:
            news = [sh for sh in env.request_queue if sh.id in new_ids]
            aa, ai = self.assigned_agvs, self.assigned_items
            for a in list(aa):
                m = aa[a]
                if (m.mission_type != MissionType.PICKING or a.carrying_shelf
                        or getattr(m, "at_location", False)):
                    continue                                  # fetch leg only
                sid = ai.get(a)
                if sid is None:
                    continue
                curp = env.shelfs[sid - 1]
                cur_sc = task_value(curp) - 0.15 * (abs(a.x - curp.x) + abs(a.y - curp.y))
                best_new = max(task_value(sh) - 0.15 * (abs(a.x - sh.x) + abs(a.y - sh.y)) for sh in news)
                if best_new > cur_sc + self.SWITCH_MARGIN:
                    aa.pop(a, None)
                    ai.pop(a, None)
                    a.committed_cells = None
                    a.busy = False                            # env-side release: stop the old walk
                    a.path = []
                    self._pre_released = getattr(self, "_pre_released", 0) + 1
        super()._assign_tasks()


class _Pre0(PartACongestionPreemptController):
    SWITCH_MARGIN = 0.0


class _Pre3(PartACongestionPreemptController):
    SWITCH_MARGIN = 3.0


class _Pre6(PartACongestionPreemptController):
    SWITCH_MARGIN = 6.0


class PartACongestionJointController(PartACongestionSeqController):
    """JOINT first-moves: when k>=2 robots are free in the same round, enumerate conflict-free combos
    of their top-JOINT_TOPK candidates (candidates scored with the TRUE funnel score), evaluate each
    combo with the SAME sim core (all k firsts pinned, everyone else base policy inside the sim,
    receding horizon beyond), then steer each robot's _pick_winner to honor the winning combo.
    k=1 rounds and robots outside the plan fall through to plain sq5 behaviour (strict superset).
    SANITY LIMIT (honest): a bit-identical tie arm is impossible for k>=2 -- predicting others'
    candidate lists can differ from what the sequential funnel would pick for them -- so sanity =
    JOINT_ON=False must tie sq5 exactly, plus mechanism counters."""

    URG_W = 8.0
    SEQ_DEPTH = 5
    JOINT_TOPK = 3
    JOINT_BEAM = 16
    JOINT_ON = True
    _true_score = PartACongestionTrueDepthController._true_score

    def _joint_plan(self):
        key = int(self.timestep)
        if getattr(self, "_jp_key", None) == key:
            return self._jp
        self._jp_key, self._jp = key, {}
        if not self.JOINT_ON:
            return self._jp
        free = [a for a in self.agvs if not a.busy and not a.carrying_shelf
                and a not in self.assigned_agvs]
        if len(free) < 2:
            return self._jp
        env = self.env
        now = self.timestep
        G = _rt.build_agv_graph(env)
        taken = set(self.assigned_items.values())
        pool = [s for s in env.request_queue if s.id not in taken]
        if len(pool) < 2:
            return self._jp
        # per-robot candidate lists, WIDE (overlap means favourites get taken by earlier robots)
        cand = {}
        for a in free:
            short = _rt.cheap_screen(a, pool, task_value, keep=self.JOINT_TOPK + len(free))
            sc = [(self._true_score(a, sh, now, G), sh) for sh in short]
            sc = sorted([x for x in sc if x[0] is not None], key=lambda r: -r[0])
            if not sc:
                return self._jp
            cand[a] = sc                                    # [(true_score, shelf)] descending
        self._joint_rounds = getattr(self, "_joint_rounds", 0) + 1
        # BEAM SEARCH over robots: naive product self-destructs when favourites overlap (all combos
        # conflict). Extend partial assignments robot-by-robot with each robot's top-JOINT_TOPK
        # *unused* tasks, keep the best JOINT_BEAM partials by true-score sum, then SIMULATE the
        # surviving complete combos and pick by simulated banked value.
        beams = [([], set(), 0.0)]                          # (assignments, used_ids, score_sum)
        for a in free:
            nxt = []
            for (asg, used, ssum) in beams:
                added = 0
                for (tsc, sh) in cand[a]:
                    if sh.id in used:
                        continue
                    nxt.append((asg + [sh], used | {sh.id}, ssum + tsc))
                    added += 1
                    if added >= self.JOINT_TOPK:
                        break
            if not nxt:
                return self._jp                             # more robots than distinct tasks
            nxt.sort(key=lambda b: -b[2])
            beams = nxt[:self.JOINT_BEAM]
        best, bestv = None, -1e18
        for (asg, _u, _s) in beams:
            v = self._simulate_joint(free, asg)
            if v > bestv:
                best, bestv = asg, v
        self._joint_combos = getattr(self, "_joint_combos", 0) + len(beams)
        if best is not None:
            self._jp = {a.id: sh.id for a, sh in zip(free, best)}
        return self._jp

    def _simulate_joint(self, robots, combo):
        self._sim_pin_agents = {a.id for a in robots}
        v = self._sim_core([(a.x, a.y, sh, None) for a, sh in zip(robots, combo)])
        self._sim_pin_agents = None
        return v

    def _pick_winner(self, scored):
        jp = self._joint_plan()
        me = getattr(self, "_cur_agv", None)
        if me is not None and me.id in jp:
            want = jp[me.id]
            for tup in scored:
                if tup[1].id == want:
                    self._joint_honored = getattr(self, "_joint_honored", 0) + 1
                    return tup
            self._joint_missed = getattr(self, "_joint_missed", 0) + 1
        return super()._pick_winner(scored)


class _JOff(PartACongestionJointController):
    JOINT_ON = False        # SANITY: must tie sq5 exactly


class _J2(PartACongestionJointController):
    JOINT_TOPK = 2


class _J3(PartACongestionJointController):
    JOINT_TOPK = 3


class _SqNB(PartACongestionSeqController):
    SEQ_DEPTH, SIM_BIAS = 5, False        # full hi-fi MINUS live bias


class _SqNP(PartACongestionSeqController):
    SEQ_DEPTH, SIM_PICKERS = 5, False     # full hi-fi MINUS pickers


class _SqNF(PartACongestionSeqController):
    SEQ_DEPTH, SIM_FREEDPOS = 5, False    # full hi-fi MINUS freed-position


class _StackExplore(PartACongestionUrgencyController):
    """Explorer over the NEW stack's scoring (urg8): random uniform pick among top-K scored
    candidates, shuffled order -- for re-measuring the hindsight ceiling ABOVE the upgraded baseline."""
    URG_W = 8.0

    def __init__(self, env, rng_seed=0, top_k=3, shuffle_order=False):
        super().__init__(env)
        self._xrng = np.random.RandomState(rng_seed)
        self._top_k = max(1, int(top_k))
        self._shuffle = bool(shuffle_order)

    def _pick_winner(self, scored):
        k = min(self._top_k, len(scored))
        return scored[int(self._xrng.randint(k))]

    def _order_free_agvs(self, free_agvs):
        order = super()._order_free_agvs(free_agvs)
        if self._shuffle:
            order = list(order)
            self._xrng.shuffle(order)
        return order


class _SqDC(PartACongestionSeqController):
    SEQ_DEPTH, SIM_DECAY_CREDIT = 5, True


class _SqP15(PartACongestionSeqController):
    SEQ_DEPTH, BIAS_PRIOR = 5, 15.0


class _SqWide(PartACongestionSeqController):
    """Simulate ALL 15 screened finalists as first moves (not just the funnel's top 5)."""
    SEQ_DEPTH, SEQ_TOPK = 5, 99


class _SqAll(PartACongestionSeqController):
    """No Manhattan screening at all + simulate EVERY candidate: the screen passes everything
    (SCREEN_KEEP huge), and every scored candidate gets its own imagined rest-of-day."""
    SEQ_DEPTH, SEQ_TOPK = 5, 99
    SCREEN_KEEP = 999


class _W8(PartACongestionSeqController):
    SEQ_DEPTH, SEQ_TOPK = 5, 8


class _W12(PartACongestionSeqController):
    SEQ_DEPTH, SEQ_TOPK = 5, 12


class _W20(PartACongestionSeqController):
    SEQ_DEPTH, SEQ_TOPK, SCREEN_KEEP = 5, 20, 20


class _W25(PartACongestionSeqController):
    SEQ_DEPTH, SEQ_TOPK, SCREEN_KEEP = 5, 25, 25


class _OpenLoop(_SqWide):
    """OPEN-LOOP execution (the clean commit-the-whole-branch test): at each forced planning moment,
    compute the winning branch as usual, then EXTRACT its full per-robot schedule and follow it
    without re-scoring. A robot triggers a fresh global plan only when its scripted next task is
    unavailable or its script is exhausted. Isolates the re-planning benefit: closed-loop (sqwide)
    minus this = the measured value of re-imagining at every decision."""

    def __init__(self, env):
        super().__init__(env)
        self._plan = {}
        self._follows = 0
        self._replans = 0
        self._misses = 0

    def _pick_winner(self, scored):
        me = self._cur_agv
        seq = self._plan.get(me.id)
        while seq:
            want = seq.pop(0)
            tup = next((t for t in scored if t[1].id == want), None)
            if tup is not None:
                self._follows += 1
                return tup
            self._misses += 1                      # planned shelf gone / outside this round's finalists
        self._replans += 1
        best, bestv, besttr = None, -1e18, None
        for tup in scored[:self.SEQ_TOPK]:
            tr = []
            self._pin_owner_ids = [me.id]
            self._sim_pin_agents = {me.id}
            fov = float(self.timestep) + float(tup[4]["pred_finish"]) + self._finish_delay(tup[2])
            v = self._sim_core([(me.x, me.y, tup[1], fov)], trace=tr)
            self._sim_pin_agents = None
            self._pin_owner_ids = None
            if v > bestv:
                best, bestv, besttr = tup, v, tr
        plan = {}
        for (fin, sid, bank, owner) in sorted(besttr or []):
            plan.setdefault(owner, []).append(sid)
        if best is not None and plan.get(me.id) and plan[me.id][0] == best[1].id:
            plan[me.id] = plan[me.id][1:]
        self._plan = plan
        return best if best is not None else scored[0]


class _NoMap(_SqWide):
    """ABLATION (user question 2026-07-23): the full deployed stack MINUS the congestion map.
    No traffic forecast, no congestion-weighted route pick or reroute, and no route-sticking
    (adherence without the map was measured harmful long ago -- rush_yen 190.2 vs rush 197.9).
    Tests whether the map still earns its keep underneath the sequencer, where its value has
    never been measured."""

    def __init__(self, env):
        super().__init__(env)
        env.prefer_committed = False
        env.congestion_weight = 0.0
        env.congestion_grid = None

    def _pre_dispatch(self, free_agvs, G):
        self._cong = None
        self.env.congestion_grid = None


_PACE_CACHE = {}


def _load_pace(path):
    """Lazy-load a pace model bundle {'model', 'cols'}; cached; None if missing."""
    if path not in _PACE_CACHE:
        import pickle
        try:
            with open(path, "rb") as f:
                _PACE_CACHE[path] = pickle.load(f)
        except FileNotFoundError:
            _PACE_CACHE[path] = None
    return _PACE_CACHE[path]


class _PaceMixin:
    """Replace the sequencer's flat-EMA delay bias with a STATE-CONDITIONAL pace prediction.

    _sim_delay_bias normally returns _delay_ema (one lagging fleet-average scalar). Here it feeds the
    current step's fleet state (self._pace_ctx, stashed by the funnel) to a trained pace model, so the
    sim clock ANTICIPATES the diurnal rush and CONDITIONS on picker contention. Falls back to the EMA
    if the model or the context is unavailable. Clipped to a sane band so a bad row can't warp the
    clock more than the observed delay range."""
    PACE_PATH = None

    def _sim_delay_bias(self):
        if not self.SIM_BIAS:
            return 0.0
        bundle = _load_pace(self.PACE_PATH)
        ctx = getattr(self, "_pace_ctx", None)
        if bundle is None or ctx is None:
            return super()._sim_delay_bias()
        import numpy as _np
        row = _np.asarray([[float(ctx.get(c, 0.0)) for c in bundle["cols"]]], float)
        pred = float(bundle["model"].predict(row)[0])
        return float(min(50.0, max(-5.0, pred)))


class _SqPacePick(_PaceMixin, _SqWide):
    """Deployed stack + PACE-PICKER bias (picker-availability state only)."""
    PACE_PATH = "results/pace_picker.pkl"


class _SqPaceComb(_PaceMixin, _SqWide):
    """Deployed stack + PACE-COMBINED bias (picker + diurnal day-curve + traffic)."""
    PACE_PATH = "results/pace_combined.pkl"


class _SqPaceCombDL(_PaceMixin, _SqWide):
    """PACE-COMBINED + DEADLINE-CLUSTERING: combined features PLUS direct counts of near-due pending
    tasks (dl_soon40/80/160). Tests whether measuring deadline bunching directly beats the time-of-day
    proxy for predicting delay -> value."""
    PACE_PATH = "results/pace_comb_dl.pkl"


class _SqPaceClust(_PaceMixin, _SqWide):
    """PACE-CLUSTERING-ONLY: bias from pure demand-timing knowledge (diurnal + deadline clustering),
    NO fleet physics. Tests whether clustering alone beats the EMA."""
    PACE_PATH = "results/pace_clust.pkl"


class _PkCommit(_Urg8):
    """Champion+urg8 (no pace), but pickers COMMIT to their chosen route -- soft adherence like AGVs,
    so a dispatched picker actually drives to its AGV instead of being loosely re-pathed and drifting."""

    def __init__(self, env):
        super().__init__(env)
        env.prefer_committed = True

    def _dispatch_pickers(self):
        super()._dispatch_pickers()
        assigned = set(self.assigned_pickers)
        routes = getattr(self, "picker_routes", {})
        for p in self.pickers:
            r = routes.get(p)
            p.committed_cells = {(cy, cx) for (cx, cy) in r} if (p in assigned and r) else None


class _VRPicker:
    """VALUE-RATE picker scoring mixin: serve-score = tier + eff_v / Tp^RATE_ALPHA. RATE_ALPHA=3 is the
    120-seed swept best. Distance-weighting -> emergent Voronoi zoning + shorter, tighter picker waits.
    Tp = rendezvous + LOAD absorbs both sync waits, so the explicit penalties are dropped. Marginal via
    the taken-set. Drops on ANY base (champion or sequencer)."""
    RATE_ALPHA = 7.0    # CHAMPION v6 (USER DECISION 2026-08-10, ship bar t>=2): monotone climb
                        # 5->5.5->6->6.5->7 on the v5 dense map (peak 7-8), pre-registered 288-seed
                        # confirmation +0.61% t=+2.71, split-halves +1.37/+2.52, frozen 0/288.
                        # The OLD standard-map sweep peaked at 5 with "6 turns down" -- the v5 picker
                        # layer is far more efficient, so sharper distance-discounting now pays.

    def _picker_score(self, sh, gx, gy, rendezvous, agv_wait, picker_wait, now):
        import wwm_sim.rollout as _ro
        env = self.env
        Tp = rendezvous + self.LOAD_TIME                 # picker is free after the load (no haul)
        finish = Tp + _ro.nearest_dock_dist(env, gx, gy)
        v = task_value(sh) if sh else 1.0
        if sh is None or sh.deadline is None:
            eff_v, tier = v, 500.0
        else:
            proj_late = (now + finish) - sh.deadline
            if proj_late <= 0:
                eff_v, tier = v, self.TIER_GAP            # makeable gate: any makeable > any doomed
            else:
                g = self.DECAY_G if sh.hardness is None else sh.hardness
                eff_v, tier = v * (g ** proj_late), 0.0
        return tier + eff_v / (max(1.0, Tp) ** self.RATE_ALPHA)


class _WaitAwarePicker:
    """SUNK-WAIT picker dispatch (opt-in `WAIT_W`, 2026-08-08).

    MEASURED: 91.2% of all TOGGLE_LOAD steps are an AGV parked at a pod re-requesting a load that
    silently no-ops because no picker is present. That is ~29% of ALL non-moving AGV-time -- the single
    largest addressable stall cause. The pickers_free oracle bounds the prize at +3.74% off-peak
    (t=+4.22); at peak it is only +1.44% because the queue drains by deadline expiry anyway.

    `_VRPicker._picker_score` prices the FORECAST rendezvous (Tp = rendezvous + LOAD) and explicitly
    drops the sync-wait penalties. So it knows how far a picker must travel, but not that an AGV has
    ALREADY been standing at that pod for 40 steps. Those steps are sunk robot-time and they keep
    accruing until a picker arrives, so a rendezvous with a waiting AGV is strictly more urgent than an
    identical one without.

    Boost is multiplicative on eff_v so the makeable/doomed TIER gate still dominates: waiting reorders
    within a tier, it never promotes a doomed task over a makeable one.
    """
    WAIT_W = 0.0            # 0 = inert, exactly _VRPicker

    def _waited_at(self, sh):
        """Steps an AGV has been parked at `sh` with nothing to do but wait for a picker.
        An AGV that has arrived and is not carrying has no path left -- that is the waiting state."""
        if sh is None or not self.WAIT_W:
            return 0
        from wwm_sim.warehouse import CollisionLayers
        env = self.env
        now = int(self.timestep)
        if getattr(self, "_wait_key", None) != now:
            self._wait_key = now
            tbl = getattr(self, "_wait_tbl", {})
            seen = set()
            for a in self.agvs:
                if a.carrying_shelf is not None or getattr(a, "path", None):
                    continue                      # still travelling, or already loaded
                sid = env.grid[CollisionLayers.SHELVES, a.y, a.x]
                if sid:
                    tbl[sid] = tbl.get(sid, 0) + 1
                    seen.add(sid)
            for k in list(tbl):
                if k not in seen:
                    tbl[k] = 0                    # nobody waiting there any more
            self._wait_tbl = tbl
        return self._wait_tbl.get(sh.id, 0)

    def _picker_score(self, sh, gx, gy, rendezvous, agv_wait, picker_wait, now):
        base = _VRPicker._picker_score(self, sh, gx, gy, rendezvous, agv_wait, picker_wait, now)
        w = self._waited_at(sh)
        if not w:
            return base
        import wwm_sim.rollout as _ro
        env = self.env
        Tp = rendezvous + self.LOAD_TIME
        v = task_value(sh) if sh else 1.0
        if sh is None or sh.deadline is None:
            eff_v, tier = v, 500.0
        else:
            proj_late = (now + Tp + _ro.nearest_dock_dist(env, gx, gy)) - sh.deadline
            if proj_late <= 0:
                eff_v, tier = v, self.TIER_GAP
            else:
                g = self.DECAY_G if sh.hardness is None else sh.hardness
                eff_v, tier = v * (g ** proj_late), 0.0
        return tier + (eff_v * (1.0 + self.WAIT_W * w)) / (max(1.0, Tp) ** self.RATE_ALPHA)


class _PickerPreempt:
    """PICKER PREEMPTION (opt-in `PREEMPT_AFTER`, 2026-08-08).

    `_dispatch_pickers` only lets FREE pickers choose (`for p in pickers if p not in ap`). Once a picker
    is committed it is locked until it reaches the rendezvous, so a picker walking toward an AGV that
    has not even arrived yet cannot be diverted to an AGV that is already parked and burning steps.

    MEASURED (24 off-peak episodes, 13494 AGV-steps genuinely parked at pods with no picker):
        A: a picker IS committed and travelling   13316  98.7%  n=1106  median 3  mean 11  p90 30  max 138
        B: NO picker assigned at all                178   1.3%  n=30    median 34  mean 41  p90 75  max 135
    (An earlier version of this docstring cited 92.9/7.1 from a "waiting" test that also counted robots
    with NO TASK parked on a shelf cell; ~18% of that total was idle robots. Corrected 2026-08-08.)

    VERDICT: NOT WORTH BUILDING. Case B -- the gap this mixin exists to close -- is 1.3% of pod-waiting
    and 30 occurrences across 24 episodes, inside a prize already capped at +3.74% off-peak by the
    pickers_free oracle. Case A is picker TRAVEL and no dispatch policy can remove it. Left at
    PREEMPT_AFTER=0 (inert) as a record of the measurement, not as a candidate.

    Note the existing STALL_BONUS already zeroes the wait penalty for a parked AGV and boosts its
    score, so a FREE picker will prefer it. The missing half is releasing a picker to become free:
    if my AGV is still `PREEMPT_AFTER` steps from arriving and another robot is stalled right now with
    nobody coming, I should go there instead. Releasing returns the picker to the pool, where the
    existing STALL_BONUS routes it to the stalled AGV -- no second scoring path to keep in sync.
    """
    PREEMPT_AFTER = 0        # 0 = off; else min remaining AGV path length to consider divertible

    def _dispatch_pickers(self):
        if self.PREEMPT_AFTER:
            self._maybe_preempt()
        return super()._dispatch_pickers()

    def _maybe_preempt(self):
        aa, ap = self.assigned_agvs, self.assigned_pickers
        stalled = set()
        for a, m in aa.items():
            if m.mission_type not in (MissionType.PICKING, MissionType.RETURNING):
                continue
            if (a.carrying_shelf is None and not getattr(a, "path", None)
                    and (a.x, a.y) == (m.location_x, m.location_y)):
                stalled.add((m.location_x, m.location_y))
        if not stalled:
            return
        served = {(m.location_x, m.location_y) for m in ap.values()}
        unserved = stalled - served
        if not unserved:
            return                                   # every stalled AGV already has a picker coming
        owner_eta = {}
        for a, am in aa.items():
            owner_eta[(am.location_x, am.location_y)] = len(getattr(a, "path", None) or [])
        # release the picker whose own AGV is FURTHEST from arriving -- it is the one whose diversion
        # costs least, since its rendezvous could not have happened soon anyway
        divertible = []
        for pk in list(ap):
            tgt = (ap[pk].location_x, ap[pk].location_y)
            if tgt in stalled:
                continue                             # already serving a stalled robot; leave it
            eta = owner_eta.get(tgt)
            if eta is not None and eta >= int(self.PREEMPT_AFTER):
                divertible.append((eta, pk))
        divertible.sort(reverse=True, key=lambda r: r[0])
        for _eta, pk in divertible[:len(unserved)]:
            ap.pop(pk, None)


class _PkRate(_VRPicker, _PkCommit):
    """Champion+urg8 + committed picker paths + value-rate scoring (the confirmed +6.7 arm)."""


class _PkRate3(_PkRate):
    """Value-rate pickers at the OLD alpha=3 (for the before/after comparison vs the swept alpha=5)."""
    RATE_ALPHA = 3.0


class _PkCovMixin:
    """Picker COVERAGE/SPREAD term (USER IDEA): penalize a rendezvous close to an ALREADY-COMMITTED
    picker's rendezvous this step. Marginal + prioritized (pickers commit one-by-one, so a later
    picker sees where earlier ones went) -> L3-style anti-contention + spread. NOT traffic/speed: the
    value-rate score already handles distance; this is coverage-as-SIGNAL. It de-emphasizes a crowded
    high-value cluster so two pickers split off it, and a chronically-deprioritized far/low-value
    stray becomes RELATIVELY more competitive. Tail term (COV_W ~ STALL_BONUS) so value still leads."""
    COV_W = 3.0          # spread weight; ~STALL_BONUS so it only reorders WITHIN the makeable tier
    COV_R = 6.0          # manhattan radius over which a committed picker "covers" nearby cells

    def _picker_task_adjust(self, gx, gy, best_r):
        dens = 0.0
        for m in self.assigned_pickers.values():
            d = abs(m.location_x - gx) + abs(m.location_y - gy)
            if d < self.COV_R:
                dens += 1.0 - d / self.COV_R          # 1 at same cell -> 0 at radius
        return -self.COV_W * dens


class _PkRateCov(_PkCovMixin, _PkRate):
    """Champion + value-rate pickers (alpha=5) + coverage/spread term. Tests whether spreading pickers
    off crowded clusters (and relatively rescuing parked strays) beats pure value-rate."""


class _PkRateCov1(_PkRateCov):
    COV_W = 1.5          # lighter tail


class _PkRateCov6(_PkRateCov):
    COV_W = 6.0          # heavier spread


class _PkUrgMixin:
    """Picker URGENCY term (USER: the picker score has NO deadline urgency, unlike the AGV's urg8, so a
    task NEAR its deadline loses to a comfortable close one and gets parked until it dooms). Within the
    makeable tier add URG_W*max(0,1-spare/URG_S0), spare = deadline-(now+finish). Mirrors the AGV's
    PartACongestionUrgencyController (urg8: URG_W=8, URG_S0=40). Rescues far/stray AGVs value-rate drops."""
    PK_URG_W = 8.0
    PK_URG_S0 = 40.0

    def _picker_score(self, sh, gx, gy, rendezvous, agv_wait, picker_wait, now):
        base = super()._picker_score(sh, gx, gy, rendezvous, agv_wait, picker_wait, now)
        if sh is None or sh.deadline is None:
            return base
        import wwm_sim.rollout as _ro
        Tp = rendezvous + self.LOAD_TIME
        finish = Tp + _ro.nearest_dock_dist(self.env, gx, gy)
        spare = sh.deadline - (now + finish)
        if spare < 0:
            return base                                      # doomed (tier 0): urgency doesn't apply
        return base + self.PK_URG_W * max(0.0, 1.0 - spare / self.PK_URG_S0)


class _PkRateUrg(_PkUrgMixin, _PkRate):
    """Champion + value-rate pickers + deadline URGENCY in the picker score (the missing urg8 mirror)."""


class _PkRateCovUrg(_PkCovMixin, _PkUrgMixin, _PkRate):
    """Champion + value-rate pickers + BOTH coverage/spread AND urgency. Do they add or overlap?"""


class _UrgFreePk(_Urg8):
    """Champion-base picker-optimal ceiling: pickers never a constraint (zero picker wait)."""
    def __init__(self, env):
        super().__init__(env)
        env.pickers_free = True


class _PkRateNoSync(_PkRate):
    """USER HYPOTHESIS: with value-rate pickers already accommodating (coming to the nearest AGV), the
    AGV-side sync penalty (-W_SYNC*my_wait, avoid tasks where I'd wait for a picker) is DOUBLE-COUNTING.
    Drop it (W_SYNC=0) and trust the pickers to co-locate. Does removing the redundant accommodation
    free the AGV to grab more value, or does the AGV then pick tasks no picker can cover fast?"""
    W_SYNC = 0.0


class _SqWidePkRate(_VRPicker, _SqWide):
    """STACKING TEST: deployed sequencer (AGV task choice) + value-rate pickers (alpha=3). Does the
    picker win survive on top of the sequencer?"""


class _SqWidePkRateAdaptive(_SqWidePkRate):
    # STANDING CONFIG (2026-08-08): stations are a consumed resource in the rollout. Paired with
    # `env.station_headway` in the runner. Kept on even though its measured effect is ~0 (+0.9 value)
    # because the modelling gap it closes is real -- the rollout otherwise treats all docks as
    # infinitely parallel -- and it costs nothing.
    SIM_DOCK_RES = True

    """DEPLOYED CHAMPION with REGIME-CONDITIONAL deadline weight (M1 2026-07-28 result across the ratio
    grid): URG_W=0 on day-list (full-foresight rollout -> urgency redundant/harmful), URG_W=8 on stream
    (rollout blind to future arrivals -> urgency patches it). Recovers ~1% on day-list, stream unchanged.
    Base URG_W stays 8 for sweeps; this class overrides the deadline score to pick by regime."""
    URG_W_DAYLIST = 0.0
    URG_W_STREAM = 8.0

    def _deadline_score(self, v, proj_late, shelf, best_r):
        if proj_late <= 0:
            spare = -proj_late
            mode = getattr(getattr(self.env, "demand_model", None), "mode", "stream")
            uw = self.URG_W_DAYLIST if mode == "daylist" else self.URG_W_STREAM
            return self.TIER_GAP + v + uw * max(0.0, 1.0 - spare / self.URG_S0)
        g = self.DECAY_G if shelf.hardness is None else shelf.hardness
        return v * (g ** proj_late)


class _PkSeqMixin:
    """PICKER-SIDE SEQUENCER -- the AGV sequencer's machinery pointed at the picker funnel.

    WHY: the AGV side screens with a formula then RE-SIMULATES the finalists and ranks by banked
    value (worth -24.05, -7.2%, when switched off -- the largest mechanism in the system). The picker
    side has only ever had a better SCORE (`_VRPicker`, +6.7) and no rollout at all. That asymmetry
    points the wrong way: PICKERS ARE THE BINDING CONSTRAINT (free-picker ceiling +11..22; "the
    binding limit is picker headcount"). So: keep `_picker_score` as the cheap screen, re-simulate the
    top PK_SEQ_TOPK rendezvous with THIS picker pinned to each, and take the best banked value.

    PK_SEQ_DEPTH = 0 -> exactly the greedy funnel (control arm). 2 -> ~150 imagined steps. 5 -> matches
    the AGV sequencer's horizon.
    """

    PK_SEQ_DEPTH = 2
    PK_SEQ_TOPK = 3

    PK_WAIT = 0.0        # >0 adds a WAIT branch: stay idle this many steps instead of committing

    def _pick_picker_winner(self, scored, picker):
        if self.PK_SEQ_DEPTH <= 0:
            return scored[0]
        if len(scored) < 2 and self.PK_WAIT <= 0:
            return scored[0]                  # nothing to choose between and waiting is disabled
        try:
            idx = list(self.pickers).index(picker)
        except ValueError:
            return scored[0]
        best, bestv = scored[0], None
        for tup in scored[:self.PK_SEQ_TOPK]:
            v = self._simulate_picker_branch(idx, tup)
            if v is None:
                continue
            if bestv is None or v > bestv:
                best, bestv = tup, v
        # WAIT BRANCH (user's framing): rather than "is A better than B", ask "is committing to the best
        # thing available NOW better than staying free for PK_WAIT steps and taking whatever the extra
        # time opens up -- judged over the SAME horizon". No tuned margin: the simulated banked value
        # decides. Modelled by pinning this picker as busy-in-place until now + PK_WAIT.
        if self.PK_WAIT > 0 and bestv is not None:
            w = self._simulate_picker_wait(idx, picker)
            if w is not None and w > bestv:
                return None                   # decline; the funnel leaves this picker free this round
        return best

    def _simulate_picker_wait(self, pidx, picker):
        """Value if this picker stays idle for PK_WAIT steps instead of committing now."""
        saved_depth, saved_init = self.SEQ_DEPTH, self._sim_pickers_init
        try:
            self.SEQ_DEPTH = self.PK_SEQ_DEPTH

            def _waiting():
                tbl = saved_init()
                if 0 <= pidx < len(tbl):
                    tbl[pidx] = [float(self.timestep) + self.PK_WAIT, picker.x, picker.y]
                return tbl

            self._sim_pickers_init = _waiting
            return self._sim_core([])
        except Exception:
            return None
        finally:
            self.SEQ_DEPTH, self._sim_pickers_init = saved_depth, saved_init

    def _simulate_picker_branch(self, pidx, tup):
        """Pin picker `pidx` to this rendezvous, then simulate the fleet forward and bank the value."""
        _score, gx, gy, best_r, _routes = tup
        arrival = float(self.timestep) + max(0, len(best_r) - 1)
        saved_depth, saved_init = self.SEQ_DEPTH, self._sim_pickers_init
        try:
            self.SEQ_DEPTH = self.PK_SEQ_DEPTH        # picker branches use their own (cheaper) horizon

            def _pinned():
                tbl = saved_init()
                if 0 <= pidx < len(tbl):
                    tbl[pidx] = [arrival + self.LOAD_TIME, gx, gy]   # this picker is committed HERE
                return tbl

            self._sim_pickers_init = _pinned
            return self._sim_core([])
        except Exception:
            return None
        finally:
            self.SEQ_DEPTH, self._sim_pickers_init = saved_depth, saved_init


class _SqWidePkSeq0(_PkSeqMixin, _SqWidePkRateAdaptive):
    PK_SEQ_DEPTH = 0        # CONTROL: must tie the champion exactly


class _SqWidePkSeq2(_PkSeqMixin, _SqWidePkRateAdaptive):
    PK_SEQ_DEPTH = 2


class _SqWidePkSeq5(_PkSeqMixin, _SqWidePkRateAdaptive):
    PK_SEQ_DEPTH = 5


class _SqWideMakeableOnly(_SqWidePkRateAdaptive):
    """Use the prelim score as a FILTER, not a ranker: simulate only the MAKEABLE candidates.

    MEASURED (2026-08-04): `_pick_winner` simulates ~9.8 branches per call, and 48.6% of calls end in a
    TIE for the max, with a mean tie size of 5.09. Banked value is a sum of discrete task values, so
    different first moves that finish the same set by the horizon score identically -- the simulator
    genuinely cannot separate them.
    A DOOMED first move banks ~nothing from that task (it misses its own deadline) while still tying the
    robot up, so it should essentially never win. Simulating those branches is wasted compute AND it
    pads the tie pool, handing more decisions to the tie-break.
    So: keep every makeable candidate, drop the doomed ones, fall back to the full list when nothing is
    makeable (someone still has to take a task). The score decides ONLY the hard question -- "can this
    still make its deadline?" -- which is the one thing it is actually qualified to answer.
    """

    def _pick_winner(self, scored):
        if self.SEQ_DEPTH <= 0 or len(scored) < 2:
            return scored[0]
        keep = [t for t in scored if t[0] >= 1000.0]      # makeable tier (1000 + value + urgency)
        return super()._pick_winner(keep if len(keep) >= 2 else scored)


class _SqWideLean(_SqWidePkRateAdaptive):
    """LEAN CHAMPION -- strip step 5's tier arithmetic and let the simulator be the only ranker.

    RATIONALE (user, 2026-08-04). `_pick_winner` is already a pure argmax over SIMULATED banked value:
    SEQ_TOPK=99 (all 15 finalists simulated), SCORE_TOL=inf (nothing filtered by score), DEV_MARGIN=0
    (never falls back). So the funnel's `1000 + value + URG_W*urgency` cannot override the simulation by
    a single point -- it only ORDERS the shortlist and breaks exact ties. Two deadline estimates for one
    decision is confusing, not useful.

    WHAT IS KEPT, because these are NOT the score:
      * the rollout's `pred_finish` -- it is what the live delay-EMA is calibrated against
        (`_pred_by_sid`), and the EMA is what gives the sequencer its honest clock (+6.9).
      * the `unserviceable` exclusion (-1e6) -- a hard "the world says this can never work" filter.
      * the committed route from Yen's + the congestion-aware pick.
    WHAT IS DROPPED: the makeable/doomed tier, the value term and the urgency term IN THE FUNNEL ONLY.
    The simulator still tiers every imagined task against its own deadline internally -- deadlines are
    priced ONCE, where the decision is actually made.

    EXPECTATION ON RECORD: near-identical behaviour (only exact ties can move) and near-identical
    runtime (the tier arithmetic is trivial next to Yen's k-routes and the forward simulation). If that
    holds it is not a speed win -- it is EVIDENCE that the score is vestigial, which is a cleaner story
    for the paper than carrying a second ranker that never ranks.
    """

    def _deadline_score(self, v, proj_late, shelf, best_r):
        return 1000.0        # constant: ordering only. The simulator does the real tiering.


class _ChampExplore(_SqWidePkRateAdaptive):
    """Hindsight-oracle EXPLORER over the CURRENT champion, exploring AROUND the sequencer rather than
    replacing it.

    v1 WAS INVALID and its numbers are discarded: it overrode `_pick_winner` outright, which IS the
    sequencer, and sampled uniformly among the top 2-4 by FUNNEL score -- while the champion simulates
    all 15 (SEQ_TOPK=99) and takes argmax by BANKED VALUE. Its search space was a strict SUBSET of the
    baseline's, so it could not bound it; several seeds came back with the champion beating best-of-M,
    which looked like a tight ceiling but was just an explorer that could not reach where the champion
    already goes.

    v2: run the sequencer normally, then DEVIATE with probability `explore_p` to a random one of the
    top-K simulated branches. Every rollout is therefore a competent policy with perturbations, and
    best-of-M explores the NEIGHBOURHOOD ABOVE the champion -- which is what an assignment ceiling
    means. Still a LOWER bound (random search will not find adversarial schedules).
    """

    def __init__(self, env, rng_seed=0, top_k=3, shuffle_order=False, explore_p=0.25):
        super().__init__(env)
        self._xrng = np.random.RandomState(rng_seed)
        self._top_k = max(2, int(top_k))
        self._shuffle = bool(shuffle_order)
        self._explore_p = float(explore_p)

    def _pick_winner(self, scored):
        best = super()._pick_winner(scored)                  # the sequencer's real choice
        if len(scored) < 2 or self._xrng.random_sample() >= self._explore_p:
            return best
        pool = [t for t in scored[:self._top_k] if t is not best] or list(scored[:self._top_k])
        return pool[int(self._xrng.randint(len(pool)))]

    def _order_free_agvs(self, free_agvs):
        order = list(super()._order_free_agvs(free_agvs))
        if self._shuffle:
            self._xrng.shuffle(order)
        return order


class _SqWideClaimedPicker(_SqWidePkRateAdaptive):
    """The imagination hands each task its SOONEST picker. Reality is that the soonest picker may be off
    serving something richer -- pickers choose by VALUE-RATE, not by proximity.

    MEASURED (931 picker decisions that had a choice): the value-rate winner differs from the soonest
    winner **33.5%** of the time, the real rule accepts a median 4 (p90 15, max 36) extra steps of
    travel to get there, and **51.9% of those disagreements cross the makeable/doomed tier**. So the
    sim systematically assumes a partner that will not actually come, and its finish estimate is early.

    FIX: walk pickers in arrival order and take the first one for which THIS task is its best option by
    value-rate among the tasks currently pending in the branch. Not a constant offset -- a claim check.
    Falls back to soonest if nobody claims it (someone has to do it eventually).
    CLAIM_K caps how many pickers/tasks are examined so the inner loop stays affordable.
    """

    CLAIM_K = 4

    def _claim_score(self, pf, px, py, s, a):
        """The AGV's model of how a picker at (px,py), free at pf, would rank task `s` -- MIRRORING
        `_VRPicker._picker_score`: `tier + eff_v / Tp^alpha`, tier = 1000 makeable / 500 no-deadline /
        0 doomed.

        v2 FIX: v1 compared only the value-rate part and omitted the TIER. The tier is worth 1000
        against value-rate differences of fractions, so a real picker ALWAYS takes a makeable task over
        a doomed one however rich the doomed one is. Without it the AGV imagined pickers abandoning it
        for fat doomed tasks that no picker would ever take -- pushing finishes late for no reason and
        classing makeable work as doomed. The wrong theory was the AGV's, not the picker's.
        """
        travel = abs(px - s.x) + abs(py - s.y)
        Tp = max(1.0, travel + self.LOAD_TIME)
        fin = pf + travel + self.LOAD_TIME + _ro.nearest_dock_dist(self.env, s.x, s.y)
        v = task_value(s)
        dl = getattr(s, "deadline", None)
        if dl is None:
            return 500.0 + v / Tp ** a
        late = fin - dl
        if late <= 0:
            return 1000.0 + v / Tp ** a
        g = self.DECAY_G if getattr(s, "hardness", None) is None else s.hardness
        return (v * (g ** late)) / Tp ** a

    def _sim_choose_picker(self, arr, sh, pickers, pending):
        order = sorted(range(len(pickers)),
                       key=lambda j: max(arr, pickers[j][0] + abs(pickers[j][1] - sh.x)
                                         + abs(pickers[j][2] - sh.y)))[:self.CLAIM_K]
        if not order:
            return -1, 1e18
        rivals = pending[:self.CLAIM_K] if pending else []
        a = self.RATE_ALPHA
        for j in order:
            pf, px, py = pickers[j]
            ready = max(arr, pf + abs(px - sh.x) + abs(py - sh.y))
            mine = self._claim_score(pf, px, py, sh, a)
            claims = True
            for r in rivals:
                if r is sh:
                    continue
                if self._claim_score(pf, px, py, r, a) > mine:
                    claims = False           # this picker prefers that task -> it is not coming here
                    break
            if claims:
                return j, ready
        j = order[0]                          # nobody claims it; somebody has to serve it eventually
        pf, px, py = pickers[j]
        return j, max(arr, pf + abs(px - sh.x) + abs(py - sh.y))


class _SqWideHonestPin(_SqWidePkRateAdaptive):
    """FIX THE ONE EXEMPT DECISION: make the pinned FIRST MOVE go through the same picker assignment
    as every imagined task after it.

    Today `_simulate_branch` passes `fov` (the funnel's heuristic `partner_eta` finish) as an override,
    so `_sim_core` takes the `fov` path: `jj = None`, no picker is chosen and NO PICKER IS CONSUMED.
    Every imagined task in the tail therefore believes all pickers are still free -- the imagination is
    optimistic by exactly one picker, for the whole horizon, in every branch, on the resource that is
    the measured bottleneck (free-picker ceiling +11..22).
    Measured consequence of the same heuristic elsewhere: 26.1% of the rendezvous a picker actually
    evaluates are DOOMED, i.e. the AGV's "makeable" verdict -- computed against an AVERAGE picker --
    was wrong about a quarter of the time.
    Passing fov=None routes the first move through `rendezvous()`: the soonest ACTUAL simulated picker
    is chosen, its finish is contention-aware, and it is marked busy so the tail sees one fewer picker.
    """

    def _simulate_branch(self, tup):
        _score, first_shelf, _route, _all_routes, feat = tup
        me = self._cur_agv
        self._sim_pin_agents = {me.id}
        try:
            return self._sim_core([(me.x, me.y, first_shelf, None)])   # None -> real rendezvous()
        finally:
            self._sim_pin_agents = None


class _SqWidePkWait5(_PkSeqMixin, _SqWidePkRateAdaptive):
    PK_SEQ_DEPTH, PK_WAIT = 2, 5.0      # commit now vs stay free 5 steps, judged over the same horizon


class _SqWidePkWait10(_PkSeqMixin, _SqWidePkRateAdaptive):
    PK_SEQ_DEPTH, PK_WAIT = 2, 10.0


class _DeferMixin:
    """DEFERRED COMMITMENT -- leave a task unassigned when a robot freeing SOON would do it much better.

    Only a robot free RIGHT NOW can ever be given a task (`available = [not busy ...]`), so a badly
    placed free robot always beats a well-placed one that frees in 3 steps. The ROLLOUT already knows
    when every busy robot frees (they are seeded into its event heap) -- the ASSIGNMENT loop just
    cannot express "wait". This hook lets it.

    RULE (user's spec): defer only when BOTH hold --
      * a robot freeing within DEFER_W steps scores more than DEFER_M better on this task, and
      * that robot is genuinely within the window (its estimated free time - now <= DEFER_W).
    Scores use the same tier formula as the funnel, so a DEFER_M near 1000 means "only defer to flip a
    task from doomed to makeable"; small values also defer on ordinary value gains.
    NOTE the risk this trades against: a deferred task is idle capacity now for a better fit later --
    the same shape as the Part D window, which went negative as the window widened.
    """

    DEFER_W = 10.0
    DEFER_M = 250.0

    def _defer_commit(self, agv, shelf, feat, route):
        if self.DEFER_M <= 0 or self.DEFER_W <= 0 or shelf.deadline is None:
            return False
        now = float(self.timestep)
        mine = self._deadline_score(task_value(shelf),
                                    (now + float(feat["pred_finish"])) - shelf.deadline, shelf, route)
        dock = _ro.nearest_dock_dist(self.env, shelf.x, shelf.y)
        for a in self.agvs:
            if a is agv or not a.busy:
                continue
            path = getattr(a, "path", None)
            if not path:
                continue
            ex, ey = path[-1]
            gx, gy = _ro.nearest_dock(self.env, ex, ey)
            t_free = len(path) + self.LOAD_TIME + abs(ex - gx) + abs(ey - gy)
            if t_free > self.DEFER_W:                       # not within the window -> not a reason to wait
                continue
            fin = t_free + abs(gx - shelf.x) + abs(gy - shelf.y) + self.LOAD_TIME + dock
            theirs = self._deadline_score(task_value(shelf),
                                          (now + fin) - shelf.deadline, shelf, route)
            if theirs - mine > self.DEFER_M:
                return True                                  # hold the task for them
        return False


# WINDOWS CALIBRATED TO MEASURED t_free (2026-08-02, 12 runs): a busy AGV's estimated free time has a
# FLOOR of ~6 and a median of 28 (LOAD_TIME + the haul to a dock is already ~20 before any travel).
# So the first draft's W=10 could only ever see 8.8% of busy robots and W=30 sees 54.9% -- the same
# mistake as Part D's W=5, which was below the minimum achievable gap and could never fire.
#   within W=10 -> 8.8% | W=20 -> 31.1% | W=30 -> 54.9% | W=45 -> 81.5% | W=60 -> 96.5%
class _SqWideDeferA(_DeferMixin, _SqWidePkRateAdaptive):
    DEFER_W, DEFER_M = 30.0, 50.0        # eager: defer on ordinary value gains


class _SqWideDeferB(_DeferMixin, _SqWidePkRateAdaptive):
    DEFER_W, DEFER_M = 30.0, 250.0


class _SqWideDeferC(_DeferMixin, _SqWidePkRateAdaptive):
    DEFER_W, DEFER_M = 60.0, 250.0       # wider window, same threshold


class _SqWideDeferD(_DeferMixin, _SqWidePkRateAdaptive):
    DEFER_W, DEFER_M = 60.0, 1000.0      # conservative: essentially only a doomed->makeable flip


class _SqWidePkRateUrg(_PkUrgMixin, _SqWidePkRate):
    """Deployed stack + picker-side deadline URGENCY. Tests whether the live-urgency correction (which
    was ~flat on day-list) helps on the STREAM, where slack pressure differs. _PkUrgMixin.super() ->
    _VRPicker score, so urgency rides on top of value-rate."""


class _SqWidePkRateSA(_SqWidePkRate):
    """USER PART-C IDEA: deployed stack + SYNTHETIC future arrivals inside the rollout horizon. The
    sequencer imagines estimated future orders (AREA via popularity weights, VALUE via the value dist,
    timing via rate*diurnal) so its task choices anticipate incoming demand on the STREAM. Upper-bound
    test: reads the true demand-model params (deployment would estimate them online). Reuses _SA5's
    generator on top of the value-rate+sequencer champion."""
    _future_arrivals = _SA5._future_arrivals


class _SqWidePkRateEV(_SqWidePkRate):
    """USER #2 + TRUST KNOB: deployed stack + DETERMINISTIC EXPECTED future-demand in the rollout.
    No random draw (kills SA5's variance): emit phantom orders at the EXPECTED inflow rate to the top
    hot cells, value = E[value]*EV_TRUST, deadline = t + E[slack]. EV_TRUST (beta) = how much the
    rollout trusts the forecast: 0 = ignore future (== champion, sanity), 1 = full expected value."""
    EV_TRUST = 1.0

    def _future_arrivals(self, now, horizon):
        key = int(self.timestep)
        if getattr(self, "_arr_key", None) == key:
            return self._arr_cache
        dm = getattr(self.env, "demand_model", None)
        out = []
        beta = self.EV_TRUST
        if dm is not None and getattr(dm, "mode", "stream") == "stream" and beta > 0:
            ids = sorted(dm.wt, key=lambda i: dm.wt[i], reverse=True)[:3]      # top-3 hot shelves
            sh_by_id = {sh.id: sh for sh in dm.shelfs}
            Ev = 0.5 * (dm.value_lo + dm.value_hi) * (1.0 + dm.rush_frac * (dm.rush_value_mult - 1.0))
            rlo, rhi = dm.rush_slack
            slo, shi = dm.std_slack
            Eslack = int(dm.rush_frac * 0.5 * (rlo + rhi) + (1.0 - dm.rush_frac) * 0.5 * (slo + shi))
            credit = 0.0
            ci = -1
            oid = -1
            t = float(now)
            while t < horizon:
                credit += dm.rate * dm._diurnal(t)               # expected orders this step
                if credit >= 1.0:                                # emit one when a full order accrues
                    credit -= 1.0
                    ci += 1
                    src = sh_by_id[ids[ci % len(ids)]]           # round-robin the hot cells
                    out.append((t, _FakeOrder(src.x, src.y, beta * Ev, t + Eslack, oid)))
                    oid -= 1
                t += 1.0
        self._arr_key, self._arr_cache = key, out
        return out


class _KSampleMixin:
    """ACTUAL MCTS-style chance nodes: score each candidate first-move by the AVERAGE simulated value
    over K independently-sampled future-arrival scenarios (Sample-Average Approximation), instead of
    one deterministic sim. K futures are shared across candidates within a decision (like-for-like) and
    seeded per (timestep, sample). As K grows this estimates the true EXPECTED value under demand
    uncertainty AND captures distribution effects (burst hedging) the mean-field EV cannot. Cost = K x
    the rollout. K=1 ~ SA5 (one noisy sample)."""
    K_SAMPLES = 4

    def _simulate_branch(self, tup):
        tot = 0.0
        for k in range(self.K_SAMPLES):
            self._sample_k = k
            tot += super()._simulate_branch(tup)
        return tot / self.K_SAMPLES

    def _future_arrivals(self, now, horizon):
        ts = int(self.timestep)
        sk = getattr(self, "_sample_k", 0)
        if getattr(self, "_arr_tskey", None) != ts:
            self._arr_tskey = ts
            self._arr_cache = {}
        if sk in self._arr_cache:
            return self._arr_cache[sk]
        dm = getattr(self.env, "demand_model", None)
        out = []
        if dm is not None and getattr(dm, "mode", "stream") == "stream":
            rng = np.random.RandomState(100003 + ts * 31 + sk)      # distinct scenario per (t, sample)
            ids = list(dm.wt.keys())
            w = np.array([dm.wt[i] for i in ids], dtype=float); w /= w.sum()
            sh_by_id = {sh.id: sh for sh in dm.shelfs}
            oid = -1
            t = float(now)
            while t < horizon:
                if rng.random() < dm.rate * dm._diurnal(t):
                    src = sh_by_id[ids[int(rng.choice(len(ids), p=w))]]
                    rush = rng.random() < dm.rush_frac
                    lo, hi = dm.rush_slack if rush else dm.std_slack
                    v = float(rng.uniform(dm.value_lo, dm.value_hi)) * (dm.rush_value_mult if rush else 1.0)
                    out.append((t, _FakeOrder(src.x, src.y, v, t + rng.randint(lo, hi), oid)))
                    oid -= 1
                t += 1.0
        self._arr_cache[sk] = out
        return out


class _SqWidePkRateK1(_KSampleMixin, _SqWidePkRate):
    K_SAMPLES = 1        # ~ SA5 (one noisy sample), baseline for the K sweep


class _SqWidePkRateK2(_KSampleMixin, _SqWidePkRate):
    K_SAMPLES = 2


class _SqWidePkRateK4(_KSampleMixin, _SqWidePkRate):
    K_SAMPLES = 4


class _SqWidePkRateK8(_KSampleMixin, _SqWidePkRate):
    K_SAMPLES = 8


class _SqWidePkRateK2U0(_SqWidePkRateK2):
    """MCTS (K=2 futures) + NO deadline urgency -- pure value ranking under future sims."""
    URG_W = 0.0


class _SqWidePkRateK2U16(_SqWidePkRateK2):
    """MCTS (K=2 futures) + STRONG deadline urgency -- does harder deadline ranking help when the
    future-order amount varies across samples? (user hypothesis)."""
    URG_W = 16.0


class _SqWidePkRateEV0(_SqWidePkRateEV):
    EV_TRUST = 0.0        # SANITY ARM: no future demand -> must tie champion


class _SqWidePkRateEV25(_SqWidePkRateEV):
    EV_TRUST = 0.25


class _SqWidePkRateEV35(_SqWidePkRateEV):
    EV_TRUST = 0.35


class _SqWidePkRateEV50(_SqWidePkRateEV):
    EV_TRUST = 0.5


class _SqWidePkRateMap(_SqWidePkRate):
    """DEPLOYED stack + PICKERS AS TRAFFIC in the congestion map. The AGV forecast (super) stamps only
    AGV paths; here we also stamp every picker's remaining path, so find_path (real execution) routes
    AGVs physically AROUND picker cells -> fewer blocks at shelves/rendezvous -> earlier finishes.
    Ports the champion screen's +3.4 (cong_pktraffic, 30 seeds: sign 17W/4L p~.007, t=1.84 marginal).
    TRAFFIC-STAMP ONLY: the champion screen showed picker-side route/rendezvous dodging adds nothing
    (cong_picker was NOT > cong_pktraffic), so the lever is purely 'pickers visible to AGVs'."""

    PICKER_WEIGHT = 1.0          # as solid as an AGV -> same stamp weight as layer 1

    def _pre_dispatch(self, free_agvs, G):
        super()._pre_dispatch(free_agvs, G)          # AGV forecast (layers 1-3) + sets self._cong / grid
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        for p in self.pickers:
            path = getattr(p, "path", None)
            if not path:
                continue
            for (x, y) in path:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += self.PICKER_WEIGHT


class _SqWideFreePk(_SqWide):
    """PICKER-OPTIMAL CEILING on the sequencer: pickers never a constraint (env.pickers_free -> AGV
    loads instantly, zero picker wait). Upper bound; better than any real assignment of 4 pickers.
    Gap to _SqWidePkRate = the picker problem REMAINING after the value-rate fix."""

    def __init__(self, env):
        super().__init__(env)
        env.pickers_free = True


class _SqWidePkRateNP(_VRPicker, _SqWide):
    """FIDELITY CHECK: sequencer + value-rate pickers, but the IMAGINATION models NO pickers
    (SIM_PICKERS off -> relies on the live EMA alone). Compared to _SqWidePkRate (picker model on),
    the gap = how much the imagination's picker model still adds under value-rate pickers. Note the
    picker SELECTION is already value-rate-optimal (soonest = best value-rate per task), so this
    bounds the remaining fidelity headroom rather than testing a mis-aligned model."""
    SIM_PICKERS = False


class _SqWideNB(_SqWide):
    """Wide sequencer with NO delay bias (fantasy time) -- the 'original without proper delay',
    matched to _SqWide in width so the 3-way (no-delay / flat-EMA / per-step) isolates the bias."""
    SIM_BIAS = False


class _PaceStepMixin:
    """PER-COMPLETION state-conditional bias: instead of one scalar per imagined day, evaluate the
    pace at EACH imagined completion from the imagined fleet state at imagined time t (diurnal phase,
    queue pressure, free pickers). This is the version where a clustering->delay signal is NOT
    redundant even on day-list: the rollout's cheap clock does not otherwise slow completions during
    an imagined rush. Uses a compact sim-reconstructable model (pace_sim.pkl). Memoized by
    (t-bucket, queue, free-pickers) so the inner candidate loop doesn't re-predict."""
    PACE_PATH = "results/pace_sim.pkl"

    def _sim_step_bias(self, t, npending, pickers):
        bundle = _load_pace(self.PACE_PATH)
        if bundle is None:
            return self._const_bias
        import numpy as _np
        n_free = sum(1 for pk in pickers if pk[0] <= t)
        key = (int(t) // 6, int(npending), n_free)
        memo = self.__dict__.setdefault("_pace_memo", {})
        hit = memo.get(key)
        if hit is not None:
            return hit
        n_pk = max(1, len(pickers))
        n_agv = max(1, len(self.agvs))
        P = float(getattr(getattr(self.env, "demand_model", None), "period", 250) or 250)
        f = {"sin_t": float(_np.sin(2 * _np.pi * t / P)), "cos_t": float(_np.cos(2 * _np.pi * t / P)),
             "day_frac": t / 500.0, "q_size": float(npending),
             "q_per_agv": npending / n_agv, "free_pk_frac": n_free / n_pk}
        row = _np.asarray([[f[c] for c in bundle["cols"]]], float)
        b = float(min(50.0, max(-5.0, bundle["model"].predict(row)[0])))
        memo[key] = b
        return b


class _SqPaceStep(_PaceStepMixin, _SqWide):
    """Deployed stack + PER-COMPLETION pace bias (the time-varying, split-all-the-way version)."""
    PACE_PATH = "results/pace_sim.pkl"
