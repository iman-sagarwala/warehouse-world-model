"""Single-simulator dashboard with PRIORITY (deadline) task assignment.

Our strategy (not FIFO): tasks are assigned to the nearest free AGV in order of
DEADLINE URGENCY (soonest deadline first), re-sorted every step so a newly-arrived
urgent task always jumps ahead. The task panel lists tasks ranked by deadline so
you can SEE whether the ordering is working (the soonest-deadline tasks should be
the ones being done).

Priority = deadline distance for now (deadline - current step). Tasks with no
deadline sort last. Assignment is non-preemptive (a robot keeps its current task;
free robots pick the most-urgent unassigned task) — preemption is a later option.

    python scripts/sim_priority.py --fps 3 --seed 0
    python scripts/sim_priority.py --snapshot out.png --snapshot-step 60
"""
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.warehouse import AgentType
from wwm_sim.battery import BatteryConfig, BatteryTracker
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value

from collections import Counter, deque
from sim_dashboard import (FIFOController, Mission, MissionType, grid_image,
                           agent_scatter, throughput_1k, accumulate, C_AGV,
                           C_AGV_LOADED, C_PICKER, C_SHELF, C_SHELF_REQ, C_GOAL)

C_CHARGER = (1.0, 0.85, 0.0)  # gold — charger cells (also the delivery docks, for now)


class PriorityController(FIFOController):
    """FIFO controller, but tasks + pickers dispatched by DEADLINE urgency.

    Two overrides vs the base:
      * _task_order: assign AGVs to tasks in deadline order (soonest first).
      * _dispatch_pickers: send the NEAREST free picker to the most-urgent AGV
        that's waiting for a load/unload (instead of zone-locked, first-come).
        This is the fix for AGVs sitting idle at shelves waiting for a picker.
    """

    def _task_order(self):
        big = float("inf")
        return sorted(
            self.env.request_queue,
            key=lambda s: (s.deadline is None, s.deadline if s.deadline is not None else big),
        )

    def _agv_urgency(self, agv):
        sid = self.assigned_items.get(agv)
        dl = self.env.shelfs[sid - 1].deadline if sid is not None else None
        return (dl is None, dl if dl is not None else float("inf"))

    def _dispatch_pickers(self):
        aa, ap = self.assigned_agvs, self.assigned_pickers
        # AGVs that need a picker rendezvous right now, most-urgent first.
        needing = [agv for agv in aa
                   if aa[agv].mission_type in (MissionType.PICKING, MissionType.RETURNING)]
        needing.sort(key=self._agv_urgency)
        need_targets = {(aa[agv].location_x, aa[agv].location_y) for agv in needing}
        # release pickers whose rendezvous cell is no longer needed (AGV loaded/moved on)
        for p in list(ap):
            if (ap[p].location_x, ap[p].location_y) not in need_targets:
                ap.pop(p)
        taken = {(m.location_x, m.location_y) for m in ap.values()}
        free = [p for p in self.pickers if p not in ap]
        # assign nearest free picker to each urgent waiting AGV (one picker per cell)
        for agv in needing:
            if not free:
                break
            m = aa[agv]
            tgt = (m.location_x, m.location_y)
            if tgt in taken:
                continue
            nearest = min(free, key=lambda p: abs(p.x - m.location_x) + abs(p.y - m.location_y))
            ap[nearest] = Mission(MissionType.PICKING, m.location_id, m.location_x, m.location_y, self.timestep)
            free.remove(nearest)
            taken.add(tgt)


class FeasiblePriorityController(PriorityController):
    """Slack-aware priority (Moore-Hodgson-style): shed what you can't finish in
    time, do the rest earliest-deadline-first.

    A task is MAKEABLE if deadline - now >= `window` (enough time left to complete
    it, where `window` ~= avg task-completion time). Tiers (best first), EDF within:
      0. MAKEABLE   — reachable before its deadline -> prioritise, soonest first.
      1. DOOMED     — deadline - now < window (can't finish in time, even starting
                      now) -> shoved to the BOTTOM: a guaranteed miss, so don't
                      waste robots on it.
      2. NO DEADLINE.
    This beats naive earliest-deadline-first (which chases doomed urgent tasks) and
    FIFO on on-time deliveries under overload. NOTE: with equal task values this
    maximises on-time COUNT; add task values later for a true value x P(on-time)
    score (Part A).
    """

    # Adaptive doomed-cutoff: `window` ~= average time to COMPLETE a task from
    # assignment (fetch -> rendezvous -> carry -> deliver). Instead of a fixed 83, it
    # is the running mean of the ACTUAL assign->deliver durations the sim has just
    # observed (self.durations, tracked in the base controller), so it self-calibrates
    # to the current fleet + congestion over time (12 AGVs / 8 pickers included).
    _window_fallback = 83     # used until enough tasks have completed to measure
    _window_min_samples = 5   # need this many completions before trusting the mean
    _window_safety = 1.0      # multiply the mean by this (>1 = shed more conservatively)

    @property
    def window(self):
        if len(self.durations) >= self._window_min_samples:
            return (sum(self.durations) / len(self.durations)) * self._window_safety
        return self._window_fallback

    def _task_order(self):
        now = self.timestep
        w = self.window

        def key(s):
            if s.deadline is None:
                return (2, 0)
            doomed = (s.deadline - now) < w   # can't finish before deadline
            return (1 if doomed else 0, s.deadline)
        return sorted(self.env.request_queue, key=key)


class ValuePriorityController(FeasiblePriorityController):
    """Value + feasibility priority — approximates value x P(on-time).

    Among MAKEABLE tasks (deadline - now >= window), do the HIGHEST-VALUE first
    (deadline as tie-break, so equal-value tasks go urgent-first). DOOMED tasks
    (can't finish in time) still shoved to the bottom. This maximises the total
    VALUE delivered on time, not just the count.
    Task value defaults to 1.0 when unset. P(on-time) is the hard makeable/doomed
    cutoff for now; a smooth probability is the next refinement (Part A).
    """

    def _task_order(self):
        now = self.timestep
        w = self.window

        def key(s):
            if s.deadline is None:
                return (2, 0.0, 0)
            doomed = (s.deadline - now) < w
            v = 1.0 if s.value is None else s.value
            return (1 if doomed else 0, -v, s.deadline)  # makeable: highest value first
        return sorted(self.env.request_queue, key=key)


class RushValueController(ValuePriorityController):
    """Value priority with LATENESS-DECAY rush-ordering of doomed tasks.

    Objective shift: on-time value is all-or-nothing (late = 0). Here a LATE delivery
    still yields value, decayed per step overdue: value x DECAY_G ** lateness (barely
    late ~= full value; very late ~= little). Under that objective, shedding doomed
    tasks throws away recoverable value — but chasing them would displace on-time work.

    This gets the best of both by keeping the MAKEABLE-first HARD TIER (tier 0), so
    on-time work is NEVER displaced (on-time value preserved), and only reordering the
    DOOMED tier (tier 1) that idle robots pick up anyway:
      tier 0 MAKEABLE (proj. on-time): highest value first, deadline tie-break.
      tier 1 DOOMED   (proj. late)   : highest DECAYED value first — i.e. RUSH the
              barely-late high-value tasks (recover most value), skip the hopelessly-
              late ones. proj_lateness = (now + window) - deadline.
      tier 2 NO DEADLINE.
    Verified (8/4): ~= on-time value of the shedding policy but higher TOTAL decayed
    value at every decay rate — the gain comes from reordering doomed work idle robots
    were already doing, not from displacing makeable work. See docs/NOTES 2026-07-09.
    A per-step decay is the metric-honest task value; DECAY_G is tunable (should equal
    the real business late-decay). NOTE: proj_lateness uses the global `window` as the
    completion estimate — a per-task rollout estimate is the eventual refinement.
    """

    DECAY_G = 0.98   # value retained per step late (tunable; = true business decay)

    def _task_order(self):
        now = self.timestep
        w = self.window

        def key(s):
            if s.deadline is None:
                return (2, 0.0, 0)
            v = 1.0 if s.value is None else s.value
            proj_late = (now + w) - s.deadline
            if proj_late <= 0:                                   # makeable -> on-time
                return (0, -v, s.deadline)
            g = self.DECAY_G if s.hardness is None else s.hardness  # per-task SLA hardness
            return (1, -(v * (g ** proj_late)), s.deadline)      # doomed -> rush decayed value
        return sorted(self.env.request_queue, key=key)


class PartAController(RushValueController):
    """Part A (doc's per-FREE-ROBOT funnel): cheap screen -> Yen's k-routes -> delete
    illegal -> score -> best-route rank -> commit robot->task->route.

    Stage-0 version: real cheap screen (value - discounted Manhattan) + real Yen's route
    generation; battery-floor / b_hard / collision / risk filters are PLACEHOLDERS (clear)
    until the Beta rumor map + battery tracker are wired. The step-5 utility reuses RUSH's
    value+lateness-decay (makeable-first, doomed rush by decayed value) as the "one number",
    now computed per robot from its best route's rollout finish. Unlike the scalar
    controllers (order the whole queue + nearest AGV), this is per-robot and route-aware,
    and outputs a committed ROUTE per assignment (self.routes)."""

    SCREEN_KEEP = 15      # step 2: keep top ~15 finalists
    K_ROUTES = 3          # step 3: Yen's routes per finalist
    LOAD_TIME = 5
    SCREEN_DISCOUNT = 0.15  # distance discount in the cheap-screen SHORTLIST. 0.0 = pure-value shortlist.
    W_SYNC = 0.3          # weight on rendezvous sync-up wait in the utility (tunable)
    TIER_GAP = 1000.0     # the makeable/doomed CLIFF. Never swept until 2026-08-05. It is not just a
                          # score constant: `_sim_core` uses it to choose what each IMAGINED robot picks
                          # up next, so it shapes the whole simulated trajectory the sequencer ranks by.
                          # Smaller -> a rich DOOMED task can outrank a cheap makeable one; larger ->
                          # never. Applied at all three sites (funnel score, imagined selection, picker
                          # tier) so a sweep changes the split consistently.
    STALL_BONUS = 0.0     # bonus for a partner ALREADY PARKED AND WAITING at the rendezvous cell.
                          # 0.0 = legacy behaviour. WHY it matters: an AGV already waiting has
                          # agv_eta=0, so the old agv_wait term charged it the picker's FULL travel
                          # distance -- the maximum possible penalty -- while an AGV arriving at the
                          # same moment was charged nothing, despite an identical finish time. The
                          # sync term degenerated into a disguised distance penalty in exactly the
                          # case sync-up exists for, so a far-away STALLED robot lost to a near
                          # not-yet-ready one. Setting this > 0 zeroes that sunk wait and pays a
                          # bonus for unblocking a stalled partner. Applies to BOTH sides.
    # makeable/doomed split source: False = per-task rollout FINISH (default); True = RUSH's
    # GLOBAL adaptive window (deadline-availability) — the SAME Moore-Hodgson split RUSH uses.
    USE_GLOBAL_WINDOW = False
    DIARY = False        # log (pred finish + congestion features) per committed task, for the
                         # delay head's training data (predicted vs actual finish = the delay).
    delay_head = None    # optional trained delay model: features dict -> predicted extra steps
    # step 4 collision filter: OFF. It cannot take effect on this substrate — the env drives
    # its OWN A* to the target (reroutes), ignoring our committed route, so route choice only
    # affects the DECISION, not execution. Hard-delete tanked throughput (dropped tasks ->
    # idle AGVs); soft-prefer was a no-op. The reservation-table machinery is kept (correct +
    # reusable for Part D combo-crash deletion and for ADG execution, which WILL drive our
    # routes). Re-enable once ADG execution lands. See NOTES 2026-07-11.
    COLLISION_FILTER = False
    COLLISION_HORIZON = 8     # only near-term committed conflicts are trustworthy

    def _partner_groups(self, shelf):
        """Partner (picker) state for one shelf, for rollout.partner_eta's 4 scenarios."""
        ap = self.assigned_pickers
        now = self.timestep
        committed = next((p for p in ap
                          if ap[p].location_x == shelf.x and ap[p].location_y == shelf.y), None)
        free = [p for p in self.pickers if p not in ap]
        busy = [(p, now + len(getattr(p, "path", None) or []), ap[p].location_x, ap[p].location_y)
                for p in ap if not (ap[p].location_x == shelf.x and ap[p].location_y == shelf.y)]
        return committed, free, busy

    # --- Part A step 4: collision filter (reservation table of committed paths) ---------
    def _build_reservation(self, exclude_ids):
        """Space-time occupancy of every committed path (busy robots): vertex set {(x,y,t)}
        and directed-move set {((x,y),(x,y),t)} for edge-swap detection. A robot's cell at
        step t = pos (t=0) then path[t-1]. Excludes the robots being (re)assigned this step."""
        vertex, moves = set(), set()
        for a in self.agents:
            if a.id in exclude_ids:
                continue
            cells = [(a.x, a.y)] + list(getattr(a, "path", None) or [])
            for t, c in enumerate(cells):
                vertex.add((c[0], c[1], t))
                if t + 1 < len(cells):
                    moves.add((c, cells[t + 1], t))
        return vertex, moves

    @staticmethod
    def _route_clash(route, vertex, moves, horizon=None):
        """True if `route` hits a committed vertex (same cell/time) or an edge-swap within
        `horizon` steps. Far-future 'conflicts' are noise (both robots reroute long before),
        so only the NEAR horizon is trustworthy."""
        h = len(route) if horizon is None else min(horizon + 1, len(route))
        for t in range(h):
            c = route[t]
            if (c[0], c[1], t) in vertex:
                return True
            if t + 1 < len(route) and (route[t + 1], c, t) in moves:
                return True
        return False

    @staticmethod
    def _add_route_to_reservation(route, vertex, moves):
        """Commit a newly-assigned route into the reservation so later robots avoid it."""
        for t, c in enumerate(route):
            vertex.add((c[0], c[1], t))
            if t + 1 < len(route):
                moves.add((c, route[t + 1], t))

    # --- route/forecast hooks: default = plain Part A; PartACongestionController overrides them ---
    def _pre_dispatch(self, free_agvs, G):
        """Build any state needed before dispatching this step (e.g. the congestion forecast)."""
        return None

    def _order_free_agvs(self, free_agvs):
        """Order in which free AGVs are assigned (prioritized planning overrides this)."""
        return free_agvs

    def _pick_route(self, routes, shelf, now):
        """Choose which of the k Yen routes to commit. Default: the shortest. Overrides may rank by
        forecast congestion (champion) or by deadline-conditional delay risk (updated dl_cong)."""
        return min(routes, key=len)

    def _on_commit(self, agv, route):
        """Called after an AGV commits to `route` (congestion planner stamps it into the map)."""
        return None

    def _task_score_adjust(self, shelf, best_r):
        """Score delta for a candidate task (congestion planner penalizes jammed tasks). Default 0."""
        return 0.0

    def _finish_delay(self, best_r):
        """Extra steps added to the empty-world finish BEFORE the deadline check (congestion planner
        estimates traffic delay along the route -> makeable/doomed becomes traffic-aware). Default 0."""
        return 0.0

    def _pick_picker_winner(self, scored, picker):
        """Which (score, gx, gy, best_route, all_routes) the PICKER commits to, from the DESCENDING
        list. Default: the argmax (greedy funnel). The picker sequencer overrides this."""
        return scored[0]

    def _defer_commit(self, agv, shelf, feat, route):
        """Return True to LEAVE this task unassigned this round rather than give it to `agv`.
        Default False. Only a robot free RIGHT NOW can ever be assigned, so without this hook a
        well-placed robot freeing in a few steps can never win a task off a badly-placed free one."""
        return False

    def _chargers(self):
        """Charger cells for the rollout's REACHABILITY reserve, or None to use the legacy fixed
        floor. Default None: the base Part A funnel has no battery tracker at all, so the step-4
        battery filter has always been inert (bcfg/blevel are None -> battery_feasible() -> True)."""
        bat = getattr(self, "battery", None)
        return sorted(bat.chargers) if bat is not None else None

    def _pick_winner(self, scored):
        """Which (score, shelf, route, ...) tuple the robot commits to, given the DESCENDING-sorted
        list. Default: the argmax. The hindsight-oracle explorer overrides this to sample among the
        top-K, so best-of-many rollouts lower-bounds the hindsight-optimal assignment schedule."""
        return scored[0]

    def _on_predict(self, shelf, now, pred_finish):
        """Fired when a task is committed with its predicted finish. Default no-op; the oracle
        recorder uses it to log (assign_step, prediction) so realized delay can be computed."""
        return None

    def _pick_picker_route(self, routes):
        """Which of the picker's k Yen routes to drive. Default: shortest. The AGV side has had a
        congestion-aware override since the champion; the picker side never did."""
        return min(routes, key=len)

    def _picker_task_adjust(self, gx, gy, best_r):
        """Score delta for a candidate picker rendezvous (congestion planner penalizes a jammed
        approach). Default 0 -- the picker funnel scored value+deadline+sync but never traffic."""
        return 0.0

    def _deadline_score(self, v, proj_late, shelf, best_r):
        """Deadline component of a task's score. Default = HARD makeable/doomed tier (makeable 1000+v;
        doomed value*decay^lateness). The soft-P(on-time) controller overrides this with a smooth cut."""
        if proj_late <= 0:
            return 1000.0 + v                            # makeable: above doomed, ranked by value
        g = self.DECAY_G if shelf.hardness is None else shelf.hardness
        return v * (g ** proj_late)                      # doomed: rush by decayed value

    def _assign_tasks(self):
        from wwm_sim import routing as _rt, rollout as _ro
        env = self.env
        now = self.timestep
        # SWAP-DROP (opt-in `env.swap_return_drop`, 2026-08-08). Two carrying AGVs on their final
        # step can be CROSS-ASSIGNED: each is standing on the other's empty drop slot, each needs the
        # other's cell, and a physical swap is impossible -- the referee correctly forbids it forever.
        # Measured (seed 83): AGVs 5 and 8 at (5,2)/(4,2), each with plen=1 targeting the other's
        # cell, mutually NOOPed for the last 99 steps of the episode.
        # The absurdity is the fix: each robot is ALREADY standing on a valid empty slot -- the
        # other's. Swap the two missions and both drop where they stand, zero movement required.
        # Emptying `path` makes attribute_macro_actions request TOGGLE_LOAD next tick, and the
        # swapped mission location now equals each robot's own cell, so completion bookkeeping fires
        # naturally.
        if getattr(env, "swap_return_drop", False):
            from wwm_sim.warehouse import CollisionLayers as _CL
            _aa = self.assigned_agvs
            # REPAIR IMPOSSIBLE RETURNS (2026-08-09). A RETURNING mission whose slot already holds a
            # shelf is unfulfillable, and when that slot is the robot's OWN cell the failure is silent
            # and permanent: find_path(own cell -> own cell) returns empty, the agent never becomes
            # busy, and nothing ever revisits the mission. Measured (seed 29): AGV 2 carrying at
            # (7,17), mission RETURNING to (7,17), shelf already stored there, busy=False, req=NOOP
            # for the last 100 steps of the episode. The original swap below CREATED that state by
            # swapping without checking the cells were still shelf-free -- my bug.
            # Repair: any carrying AGV whose return slot now holds a shelf gets the nearest genuinely
            # free slot instead.
            _goalset = {tuple(g) for g in env.goals}
            for _a in list(_aa):
                _m = _aa[_a]
                if (getattr(_a, "carrying_shelf", None) is None
                        or _m.mission_type != MissionType.RETURNING):
                    continue
                # DEAD-ZONE NUDGE (seed 2, 2026-08-09): mission = the robot's OWN cell, cell
                # SHELF-FREE (the drop is legal), but path=[] and busy=False. The not-busy branch
                # needs a non-empty path to set busy (find_path own->own returns []), and the
                # TOGGLE_LOAD branch only runs when busy -- so the robot stands on its own valid
                # drop slot, NOOPing forever. Setting busy=True routes it into the path==[] branch,
                # which requests TOGGLE_LOAD and drops the pod where it stands.
                if ((_m.location_x, _m.location_y) == (_a.x, _a.y)
                        and not getattr(_a, "path", None) and not getattr(_a, "busy", False)
                        and not env.grid[_CL.SHELVES, _a.y, _a.x]):
                    _a.busy = True
                    continue
                if not env.grid[_CL.SHELVES, _m.location_y, _m.location_x]:
                    continue
                _best, _bd = None, 1 << 30
                # CHARGER KEEPOUT (M3, 2026-08-14): with a battery tracker attached, a bare
                # charger cell is NOT a drop slot -- robots park there to charge and the "free"
                # cell becomes an occupied wall by the time the carrier arrives (measured: 3 of 4
                # residual frozen carriers were RETURNING to a charger cell). No battery -> empty
                # set -> champion behavior unchanged.
                _chgko = set(getattr(getattr(self, "battery", None), "chargers", ()) or ())
                for (_yy, _xx) in env.action_id_to_coords_map.values():
                    if (_xx, _yy) in _goalset or (_xx, _yy) in _chgko:
                        continue
                    if env.grid[_CL.SHELVES, _yy, _xx]:
                        continue
                    if env.grid[_CL.AGVS, _yy, _xx] and (_xx, _yy) != (_a.x, _a.y):
                        continue
                    _d = abs(_a.x - _xx) + abs(_a.y - _yy)
                    if _d < _bd:
                        _best, _bd = (_xx, _yy), _d
                if _best is not None:
                    _aa[_a] = Mission(MissionType.RETURNING,
                                      self.coords_to_id[(_best[1], _best[0])],
                                      _best[0], _best[1], self.timestep)
                    _a.path = []
                    _a.busy = False
            _cand = [a for a in _aa if getattr(a, "carrying_shelf", None) is not None
                     and len(getattr(a, "path", None) or []) <= 1]
            for _i in range(len(_cand)):
                for _j in range(_i + 1, len(_cand)):
                    _a, _b = _cand[_i], _cand[_j]
                    _ma, _mb = _aa[_a], _aa[_b]
                    if ((_ma.location_x, _ma.location_y) == (_b.x, _b.y)
                            and (_mb.location_x, _mb.location_y) == (_a.x, _a.y)
                            # both landing cells must still be shelf-free, or the swap manufactures
                            # exactly the impossible-return state repaired above
                            and not env.grid[_CL.SHELVES, _a.y, _a.x]
                            and not env.grid[_CL.SHELVES, _b.y, _b.x]):
                        _aa[_a], _aa[_b] = _mb, _ma
                        _a.path = []
                        _b.path = []
        if getattr(self, "_agv_graph", None) is None:   # AGV graph is the static map topology ->
            self._agv_graph = _rt.build_agv_graph(env)  # build once, reuse every step (big speedup)
        G = self._agv_graph
        if not hasattr(self, "routes"):
            self.routes = {}
            self.candidate_routes = {}   # agv -> all Yen's routes for its CHOSEN task (viz)
            self.candidate_tasks = {}    # agv -> [(shelf, best_route) for top-N finalist TASKS]
            self.diary_features = {}     # shelf.id -> (assign_step, feature dict) for the delay head
            # --- live congestion trackers (VARIANCE head): continuously updated as the sim
            #     runs, so the head can SEE traffic piling up regardless of map/fleet size ---
            self._pred_by_sid = {}       # sid -> (assign_step, pred_finish) for realized-delay calc
            self._delay_ema = 0.0        # EMA of realized delay = live "how bad is traffic now"
            self._delay_inited = False
            self._deliv_times = deque(maxlen=400)   # recent delivery timesteps -> throughput rate
        # LIVE UPDATE: fold last step's deliveries into the congestion trackers (causal —
        # deliveries_this_step is from the previous env.step, pred was logged at commit).
        for _sid, _a in getattr(env, "deliveries_this_step", []):
            self._deliv_times.append(now)
            _pr = self._pred_by_sid.pop(_sid, None)
            if _pr is not None:
                _at, _pred = _pr
                _delay = (now - _at) - _pred
                if not self._delay_inited:
                    self._delay_ema, self._delay_inited = _delay, True
                else:
                    self._delay_ema = 0.8 * self._delay_ema + 0.2 * _delay
        # ROUTE ADHERENCE: our committed route only covers the FETCH leg (agv->shelf). Once the AGV
        # has picked up (carrying) or is no longer on an assignment, drop the committed cells so the
        # env path-plans the deliver/return legs normally. (Inert unless env.prefer_committed=True.)
        for a in self.agvs:
            if getattr(a, "committed_cells", None) and (a.carrying_shelf or a not in self.assigned_agvs):
                a.committed_cells = None
        bat = getattr(self, "battery", None)     # optional battery tracker (charge-detour)
        free_agvs = [a for a in self.agvs if not a.busy and not a.carrying_shelf
                     and a not in self.assigned_agvs]
        # WIP CAP (opt-in `WIP_LIMIT`, 2026-08-08). At peak demand (seeds 73-144) 62 of 72 episodes
        # end with at least one carrying AGV permanently frozen, and mean on-time value halves
        # (955 -> 500) against the same policy off-peak. The mechanism is structural, not a routing
        # bug: a LOADED AGV cannot step aside, because its pod can only go down at a station. Once
        # every AGV is carrying, no free robot exists anywhere to open a gap, so any jam that forms
        # is permanent by construction. Routing fixes cannot reach it -- `blocked_replan` and
        # `stuck_avoid_agents` both measured inert here (frozen AGVs 119 -> 118 / 113, t = -1.39/+0.01).
        # So stop releasing fetch work once `WIP_LIMIT` AGVs are already loaded, keeping a few robots
        # unloaded as free agents. This is the CONWIP argument: releasing more work than the
        # bottleneck can absorb buys queue, not throughput. The bottleneck is 3 stations, not 8 robots.
        # Count RELEASED work, not just loaded robots: an AGV already on its fetch leg is committed
        # to becoming a loaded robot, so capping on `carrying` alone lets all 8 arrive and load anyway
        # (measured: WIP_LIMIT=4 still reached 8 concurrent carriers).

        # step-level congestion features (delay head inputs): how crowded / how scarce pickers
        n_busy_agv = sum(1 for a in self.agvs if a.busy or a.carrying_shelf or a in self.assigned_agvs)
        n_free_pk = sum(1 for p in self.pickers if p not in self.assigned_pickers)
        q_size = len(env.request_queue)
        # VARIANCE-head congestion scalars: NORMALIZED (fractions/ratios, so they transfer across
        # fleet/map/charger size) + TEMPORAL (recent completion time + trend + throughput = the
        # sim's live traffic state, updating every step).
        n_agv = max(1, len(self.agvs))
        n_pk = max(1, len(self.pickers))
        n_all = max(1, len(self.agents))
        _durs = list(self.durations)
        dur_recent = (sum(_durs[-10:]) / len(_durs[-10:])) if _durs else float(self._window_fallback)
        dur_trend = dur_recent - self.window            # >0 = completions slowing down (piling up)
        _W_RATE = 40
        deliv_rate = sum(1 for _t in self._deliv_times if now - _t <= _W_RATE) / _W_RATE
        delay_ema = self._delay_ema if self._delay_inited else 0.0
        # diurnal phase of the demand day-curve (pace model): sin/cos so periodicity is explicit
        _P = float(getattr(getattr(env, "demand_model", None), "period", 250) or 250)
        _dsin = float(np.sin(2.0 * np.pi * now / _P))
        _dcos = float(np.cos(2.0 * np.pi * now / _P))
        # DEADLINE CLUSTERING (user 2026-07-23): how many pending tasks have close-by deadlines RIGHT
        # NOW -> directly measures the deadline bunching that causes contention, not a time-of-day proxy.
        _dls = [sh.deadline - now for sh in env.request_queue if getattr(sh, "deadline", None) is not None]
        dl_soon40 = float(sum(1 for d in _dls if 0 <= d <= 40))
        dl_soon80 = float(sum(1 for d in _dls if 0 <= d <= 80))
        dl_soon160 = float(sum(1 for d in _dls if 0 <= d <= 160))
        busy_frac = n_busy_agv / n_agv
        # PACE MODEL context: stash the step-level fleet scalars so a state-conditional delay-bias
        # (_sim_delay_bias override) can replace the flat EMA with a picker/diurnal/traffic estimate.
        self._pace_ctx = {
            "free_pk_frac": n_free_pk / n_pk, "busy_frac": busy_frac,
            "n_free_pk": float(n_free_pk), "n_busy_agv": float(n_busy_agv),
            "q_per_agv": q_size / n_agv, "q_size": float(q_size),
            "sin_t": _dsin, "cos_t": _dcos, "day_frac": now / 500.0,
            "delay_ema": delay_ema, "deliv_rate": deliv_rate,
            "dur_trend": dur_trend, "dur_recent": dur_recent,
            "dl_soon40": dl_soon40, "dl_soon80": dl_soon80, "dl_soon160": dl_soon160}
        free_pk_frac = n_free_pk / n_pk
        q_per_agv = q_size / n_agv
        # STEP 4 setup: reservation table of committed paths (exclude the AGVs being assigned)
        resv, resm = self._build_reservation({a.id for a in free_agvs}) if self.COLLISION_FILTER \
            else (set(), set())
        self._pre_dispatch(free_agvs, G)       # hook: build the congestion forecast (subclass)
        _order = self._order_free_agvs(free_agvs)
        # Enforce the cap ON THE ORDERED LIST, per assignment. Checking it once per step is useless:
        # the very first call dispatches the WHOLE fleet in one pass (measured: wip 0 -> 8 at t=1),
        # so the limit is already exceeded before it is ever consulted again. `_order` is sorted by
        # best available task value, so truncating keeps the most valuable work and defers the rest.
        _wl = getattr(self, "WIP_LIMIT", None)
        if _wl:
            _wip = sum(1 for a in self.agvs
                       if getattr(a, "carrying_shelf", None) is not None
                       or a in self.assigned_agvs)
            _order = _order[:max(0, int(_wl) - _wip)]
        for _i, agv in enumerate(_order):
            taken = set(self.assigned_items.values())
            # LOOKAHEAD CONTEXT: the robots that will pick AFTER this one, for depth>1 opportunity
            # cost ("what's left for them if I take this task"). Empty tuple => greedy, as before.
            self._look_ctx = (_order[_i + 1:], taken)
            self._cur_agv = agv                       # for rollout-based winner re-ranking
            self._look_seq = getattr(self, "_look_seq", 0) + 1   # cache token for lookahead tables
            # STEP 1 cross off the impossible: still requested, not taken (AGV type implicit)
            cands = [s for s in env.request_queue if s.id not in taken]
            if not cands:
                break
            # STEP 2 cheap screen -> top ~15 finalists
            finalists = _rt.cheap_screen(agv, cands, task_value, keep=self.SCREEN_KEEP,
                                         dist_discount=self.SCREEN_DISCOUNT)
            # battery inputs for the step-4 battery-floor FILTER (only if a tracker attached)
            blevel = bcfg = None
            if bat is not None:
                blevel = bat.level.get(agv.id, 1.0)
                bcfg = bat.cfg
            scored = []                                     # (score, shelf, best_route, all_routes)
            for shelf in finalists:
                # STEP 3 Yen's k-shortest routes on the real map
                routes = _rt.k_shortest_routes(G, (agv.x, agv.y), (shelf.x, shelf.y),
                                               k=self.K_ROUTES)
                if not routes:
                    continue
                survivors = list(routes)                    # never drop the task (env reroutes)
                # STEP 4 (soft): among the k routes PREFER one clash-free in the near horizon
                # (hard-deleting any space-time overlap tanks throughput — collisions are cheap
                #  reroutes here, dropped tasks are expensive; see NOTES 2026-07-11).
                if self.COLLISION_FILTER:
                    clean = [r for r in routes
                             if not self._route_clash(r, resv, resm, self.COLLISION_HORIZON)]
                    # HARD COLLISION GUARANTEE (2026-08-07, opt-in `COLLISION_HARD`).
                    # The soft form below takes a CLASHING route when no clean one exists
                    # (`clean or routes`), so "avoid collisions" was best-effort. Under the hard form a
                    # task with no conflict-free route is DROPPED from this robot's candidates entirely
                    # -- it is not a task this robot can legally do right now -- rather than committed
                    # and hoped for. Every robot publishes its trajectory as space-time (cell, t) plus a
                    # directed-move set for edge swaps (`_build_reservation`), and newly committed routes
                    # are added so later robots see them, so "known potential collision" is exactly what
                    # the reservation encodes.
                    # COST: a robot with no legal route idles this tick instead of proceeding. That is
                    # the price of the guarantee and it is measured, not assumed.
                    if not clean and getattr(self, "COLLISION_HARD", False):
                        continue                      # drop this task; try the next candidate
                    best_r = min(clean or routes, key=len)  # shortest clean route, else shortest
                else:
                    best_r = self._pick_route(routes, shelf, now)  # default shortest; override: congestion/deadline
                my_arrival = len(best_r) - 1
                # STEP 5 score via the rollout: sync-up + charge-detour + return-to-free
                committed, free, busy = self._partner_groups(shelf)
                p_arr, reason = _ro.partner_eta(shelf, now, committed=committed, free=free, busy=busy)
                res = _ro.rollout_task(env, shelf, [agv], [], now=now, load_time=self.LOAD_TIME,
                                       my_arrival=my_arrival, partner_arrival=p_arr,
                                       battery_cfg=bcfg, battery=blevel,
                                       chargers=self._chargers())
                # STEP 4 (hard): delete a route that would strand the robot below the floor.
                # (Deciding to CHARGE first = support-then-task = Part B/C, not Part A.)
                # M3 PESSIMISM (BAT_PESSIMISM >= 1.0): the rollout prices a CLEAN trip; real trips
                # pay congestion detours, pod-waits and idle drain the estimate never sees, so at
                # heavy compression the optimistic estimate passes tasks that reality strands
                # (measured: 40 deletions yet 48 strandings at 300 steps/charge). Deadlines stay
                # optimistic (a late task banks less); battery must be pessimistic (a stranded
                # robot is gone). Feasible iff battery >= reserve + P * estimated_use.
                _bp = float(getattr(self, "BAT_PESSIMISM", 1.0))
                _infeasible = not _ro.battery_feasible(res)
                if (not _infeasible and _bp > 1.0
                        and res.get("battery_margin") is not None):
                    _infeasible = res["battery_margin"] < (_bp - 1.0) * res["battery_used"]
                if _infeasible:
                    self._bat_del = getattr(self, "_bat_del", 0) + 1
                    continue
                finish = res["finish"]                       # empty-world (traffic-blind) estimate
                v = task_value(shelf)
                # per-task congestion: agents crowding THIS shelf, and how much the route had
                # to detour vs straight-line (both normalized -> size-agnostic).
                local_density = sum(1 for a in self.agents
                                    if abs(a.x - shelf.x) + abs(a.y - shelf.y) <= 8) / n_all
                _md = abs(agv.x - shelf.x) + abs(agv.y - shelf.y)
                path_stretch = my_arrival / max(1, _md)
                feat = {"pred_finish": finish, "my_arrival": my_arrival,
                        "dock": _ro.nearest_dock_dist(env, shelf.x, shelf.y),
                        "picker_eta": p_arr, "my_wait": res["my_wait"],
                        "n_busy_agv": n_busy_agv, "n_free_pk": n_free_pk, "q_size": q_size,
                        "value": v, "dl_slack": (shelf.deadline - now) if shelf.deadline is not None else 999,
                        # --- VARIANCE-head congestion features (temporal + normalized) ---
                        "delay_ema": delay_ema, "dur_recent": dur_recent, "dur_trend": dur_trend,
                        "deliv_rate": deliv_rate, "busy_frac": busy_frac,
                        "free_pk_frac": free_pk_frac, "q_per_agv": q_per_agv,
                        "local_density": local_density, "path_stretch": path_stretch,
                        # --- diurnal phase (pace model): the demand day-curve position, so the
                        #     pace estimate can ANTICIPATE the rush slowdown the lagging EMA misses ---
                        "sin_t": _dsin, "cos_t": _dcos, "day_frac": now / 500.0,
                        # --- deadline clustering: direct count of near-due pending tasks ---
                        "dl_soon40": dl_soon40, "dl_soon80": dl_soon80, "dl_soon160": dl_soon160}
                # traffic-AWARE finish for the deadline check: empty-world finish + learned delay
                # head (if any) + congestion-derived delay (rules-based; congestion planner fills it)
                self._score_shelf = shelf     # so _finish_delay overrides can key on the candidate task
                finish_s = finish + (max(0.0, self.delay_head(feat)) if self.delay_head else 0.0) \
                    + self._finish_delay(best_r)
                # Moore-Hodgson split source: global window (RUSH-style) or per-task finish
                completion = self.window if self.USE_GLOBAL_WINDOW else finish_s
                if shelf.deadline is None:
                    score = 500.0 + v
                else:
                    proj_late = (now + completion) - shelf.deadline
                    score = self._deadline_score(v, proj_late, shelf, best_r)
                score -= self.W_SYNC * res["my_wait"]       # sync-up penalty (feature 1)
                if self.STALL_BONUS and reason == "committed" and p_arr <= 0:
                    score += self.STALL_BONUS               # picker already parked here -> unblock it
                score += self._task_score_adjust(shelf, best_r)  # hook: congestion-aware TASK choice
                if reason == "unserviceable":
                    score -= 1e6                            # case 4: nobody can meet me
                score += 0.01 * len(survivors)              # STEP 6 feasibility-ratio bonus
                scored.append((score, shelf, best_r, routes, feat))
            if not scored:
                continue
            # STEP 6/7 rank tasks by their best route, commit the winner robot->task->route
            scored.sort(key=lambda x: x[0], reverse=True)
            _, shelf, route, all_routes, feat = self._pick_winner(scored)
            # HOOK: DEFERRED COMMITMENT -- decline to hand this task to a robot that is free NOW when a
            # robot freeing shortly would do it materially better. Default False (commit immediately).
            if self._defer_commit(agv, shelf, feat, route):
                continue
            loc_id = self.coords_to_id[(shelf.y, shelf.x)]
            self.assigned_agvs[agv] = Mission(MissionType.PICKING, loc_id, shelf.x, shelf.y, now)
            self.assigned_items[agv] = shelf.id
            self._assign_step.setdefault(shelf.id, now)
            self._pred_by_sid[shelf.id] = (now, feat["pred_finish"])  # always-on: live delay EMA
            self._on_predict(shelf, now, feat["pred_finish"])          # hook: oracle recorder
            if self.DIARY:               # log pred finish + features for the delay head
                self.diary_features[shelf.id] = (now, feat)
            self.routes[agv] = route
            # attach the chosen route to the AGV so the env's find_path hugs it (drive MY route,
            # reroute around blockers but rejoin). route cells are (x,y); grid indexing is (y,x).
            agv.committed_cells = {(cy, cx) for (cx, cy) in route}
            self._on_commit(agv, route)          # hook: stamp this route into the forecast (subclass)
            self.candidate_routes[agv] = all_routes                        # chosen task's k routes
            # top-5 TASKS considered, EACH with its full Yen's route set (shelf, [routes])
            self.candidate_tasks[agv] = [(s[1], s[3]) for s in scored[:5]]
            if self.COLLISION_FILTER:      # later free AGVs avoid this newly-committed route
                self._add_route_to_reservation(route, resv, resm)

    def _picker_score(self, sh, gx, gy, rendezvous, agv_wait, picker_wait, now):
        """DEFAULT picker serve-score: parent-task value tier minus sync penalties (AGV-wait full,
        picker-wait half). Overridable -- the value-rate variant swaps this for value / picker-time."""
        from wwm_sim import rollout as _ro
        env = self.env
        finish = rendezvous + self.LOAD_TIME + _ro.nearest_dock_dist(env, gx, gy)
        v = task_value(sh) if sh else 1.0
        if sh is None or sh.deadline is None:
            base = 500.0 + v
        else:
            proj_late = (now + finish) - sh.deadline
            if proj_late <= 0:
                base = 1000.0 + v                       # makeable: above doomed, by value
            else:
                g = self.DECAY_G if sh.hardness is None else sh.hardness
                base = v * (g ** proj_late)             # doomed: rush by decayed value
        return base - self.W_SYNC * agv_wait - 0.5 * self.W_SYNC * picker_wait

    def _swap_locked_pickers(self):
        """PICKER RENDEZVOUS SWAP (opt-in `env.picker_swap`, USER RULE 2026-08-09): fires ONLY on an
        UNREMOVABLE lock -- no routine reshuffling.

        The lock it targets (seed 144, measured): two pickers in a one-wide lane, each assigned a pod
        whose single doorway lies PAST the other picker. A swap of positions is physically impossible,
        the clash replan has no alternative route because there is none, and both robots NOOP forever
        -- 448 steps, while an AGV waited at one of the pods. Which picker serves which pod is a
        dispatch choice, not physics, so uncrossing the errands dissolves the lock at zero cost: each
        picker's new pod is on ITS OWN side of the lane. Identical in spirit to `swap_return_drop`,
        which resolved the AGV version (seed 83) and holds at 0/144.

        GATE (both must hold, per user directive "only in the case of an unremovable lock"):
          1. both pickers have not moved for `picker_swap_patience` consecutive steps (default 10)
          2. their errands CROSS: each is strictly closer (Manhattan) to the OTHER's rendezvous
             than to its own -- the geometric signature of the impossible pass
        A picker merely queueing or travelling never satisfies both, so ordinary traffic is untouched.
        """
        env = self.env
        hist = getattr(self, "_pk_still", None)
        if hist is None:
            hist = self._pk_still = {}
        for pk in self.pickers:
            prev = hist.get(pk.id)
            if prev and prev[0] == (pk.x, pk.y):
                hist[pk.id] = ((pk.x, pk.y), prev[1] + 1)
            else:
                hist[pk.id] = ((pk.x, pk.y), 0)
        K = int(getattr(env, "picker_swap_patience", 10))
        ap = self.assigned_pickers
        stuck = [pk for pk in list(ap) if hist.get(pk.id, ((0, 0), -1))[1] >= K]
        for i in range(len(stuck)):
            for j in range(i + 1, len(stuck)):
                p, q = stuck[i], stuck[j]
                mp, mq = ap.get(p), ap.get(q)
                if mp is None or mq is None:
                    continue
                d_p_own = abs(p.x - mp.location_x) + abs(p.y - mp.location_y)
                d_p_other = abs(p.x - mq.location_x) + abs(p.y - mq.location_y)
                d_q_own = abs(q.x - mq.location_x) + abs(q.y - mq.location_y)
                d_q_other = abs(q.x - mp.location_x) + abs(q.y - mp.location_y)
                # Two lock shapes fire the swap (both still require BOTH robots stuck >= K):
                #   CROSSED: each strictly closer to the other's pod -- the impossible pass (seed 144)
                #   SQUAT:   one is STANDING ON the other's rendezvous while the other blocks its exit
                #            (seed 48: p11 on p10's pod at (2,10), its only exit through p10's cell;
                #            p10 one step from a door that can never open). Swapping makes the
                #            squatter serve the pod it occupies, and sends the other around the block
                #            to the far doorway -- the USER's loop-around, done by the right robot.
                crossed = d_p_other < d_p_own and d_q_other < d_q_own
                # SQUAT gate is EXPERIMENTAL (env.picker_swap_squat, default OFF). It fixes the
                # seed-48 shape (119 -> 51) but entered cascade territory: every 144-seed sweep with
                # it on produced exactly ONE new frozen instance of a different shape (seed 3, then
                # seed 2 after that was patched) for a max-wait gain of only 119 -> 114. The
                # crossed-only champion is verified 0/144 at higher value. Kept for future work.
                squat = (getattr(env, "picker_swap_squat", False)
                         and (d_p_other == 0 or d_q_other == 0))
                if crossed or squat:
                    ap[p], ap[q] = mq, mp
                    p.path = []
                    q.path = []
                    if hasattr(self, "picker_routes"):
                        self.picker_routes.pop(p, None)
                        self.picker_routes.pop(q, None)
                    hist[p.id] = ((p.x, p.y), 0)
                    hist[q.id] = ((q.x, q.y), 0)

    def _reelect_stalled_rendezvous(self):
        """RENDEZVOUS RE-ELECTION (opt-in `env.picker_reelect`, USER RULE 2026-08-09: "if pickers are
        leaving an AGV waiting and all stuck, choose based on (a) proximity and (b) ability to
        legally move in").

        The swap rules handle two specific lock SHAPES (crossed errands, squatting). This is the
        general form: when an AGV is parked at its rendezvous pod and the committed picker has made no
        progress for `picker_reelect_patience` steps, RE-ELECT the server among ALL pickers:
          (a) proximity  = actual route length, not Manhattan
          (b) legality   = env.find_path with robots as obstacles must return a route NOW; a picker
                           that cannot legally reach the pod is not a candidate, however close.
        The winner takes the mission. If the winner had a mission of its own, the two missions SWAP
        (coverage is conserved); if it was free, the stalled picker is simply released and the
        controller re-tasks it next act. Fires only on measured stalls, so ordinary traffic never
        re-shuffles.
        """
        env = self.env
        from wwm_sim.warehouse import CollisionLayers as _CL, AgentType as _AT
        K = int(getattr(env, "picker_reelect_patience", 12))
        # stillness history is normally maintained by _swap_locked_pickers; keep it ourselves when
        # re-election runs without the swap rule, or the patience gate would never open
        hist = getattr(self, "_pk_still", None)
        if hist is None:
            hist = self._pk_still = {}
        if not getattr(env, "picker_swap", False):
            for _pk2 in self.pickers:
                _prev = hist.get(_pk2.id)
                if _prev and _prev[0] == (_pk2.x, _pk2.y):
                    hist[_pk2.id] = ((_pk2.x, _pk2.y), _prev[1] + 1)
                else:
                    hist[_pk2.id] = ((_pk2.x, _pk2.y), 0)
        ap = self.assigned_pickers
        # PROGRESS MODE (`env.picker_reelect = "progress"`, 2026-08-10): trigger on NO-PROGRESS
        # instead of no-motion. The stillness gate misses the orbit livelock entirely -- seed 134's
        # picker was displaced back out four times while MOVING every tick, so its stillness counter
        # never left zero while the AGV waited 92 steps. Progress = best-ever route distance to the
        # CURRENT mission; orbiting and parking both fail to improve it.
        _prog_mode = (getattr(env, "picker_reelect", False) == "progress")
        if _prog_mode:
            pr = getattr(self, "_pk_prog", None)
            if pr is None:
                pr = self._pk_prog = {}
            for pk in self.pickers:
                m = ap.get(pk)
                if m is None:
                    pr.pop(pk.id, None)
                    continue
                loc = (m.location_x, m.location_y)
                d = abs(pk.x - loc[0]) + abs(pk.y - loc[1])
                rec = pr.get(pk.id)
                if rec is None or rec[0] != loc:
                    pr[pk.id] = (loc, d, 0)
                elif d < rec[1]:
                    pr[pk.id] = (loc, d, 0)
                else:
                    pr[pk.id] = (loc, rec[1], rec[2] + 1)
        for pk in list(ap):
            m = ap.get(pk)
            if m is None:
                continue
            gx, gy = m.location_x, m.location_y
            aid = env.grid[_CL.AGVS, gy, gx]
            if not aid:
                continue                                   # no AGV waiting at the pod yet
            a = env.agents[aid - 1]
            if a.type != _AT.AGV or a.carrying_shelf is not None:
                continue
            if _prog_mode:
                if getattr(self, "_pk_prog", {}).get(pk.id, ((0, 0), 0, 0))[2] < K:
                    continue                               # still making PROGRESS toward the pod
            elif hist.get(pk.id, ((0, 0), 0))[1] < K:
                continue                                   # committed picker still making progress
            if (pk.x, pk.y) == (gx, gy):
                continue                                   # already there
            best, best_len, best_path = None, 1 << 30, None
            for cand in self.pickers:
                if cand is pk:
                    continue
                pth = env.find_path((cand.y, cand.x), (gy, gx), cand)          # (b) legal route NOW
                if not pth:
                    continue
                if len(pth) < best_len:                                         # (a) proximity
                    best, best_len, best_path = cand, len(pth), pth
            # the incumbent keeps the job unless someone can actually do it better RIGHT NOW
            cur = env.find_path((pk.y, pk.x), (gy, gx), pk)
            if best is None or (cur and len(cur) <= best_len):
                continue
            mb = ap.get(best)
            if mb is not None:
                ap[pk], ap[best] = mb, m                   # swap: coverage conserved
            else:
                ap.pop(pk, None)
                ap[best] = m                               # free winner takes over; loser re-tasked
            for r in (pk, best):
                r.path = []
                if hasattr(self, "picker_routes"):
                    self.picker_routes.pop(r, None)
                if r.id in hist:
                    hist[r.id] = ((r.x, r.y), 0)

    def _dispatch_pickers(self):
        """Part A funnel for PICKERS (symmetric to the AGV funnel): each free picker chooses
        which AGV-rendezvous to serve — screened by the AGV's task value, routed on the
        HIGHWAY graph (Yen's), and synced against the AGV's committed AVAILABILITY (partner =
        the AGV heading to the shelf; its ETA = len(path)). Penalises making the AGV wait
        (delays a valuable task) most, and the picker's own idle wait a little."""
        from wwm_sim import routing as _rt, rollout as _ro
        env = self.env
        now = self.timestep
        if getattr(env, "picker_swap", False):
            self._swap_locked_pickers()
        if getattr(env, "picker_reelect", False):
            self._reelect_stalled_rendezvous()
        Gp = _rt.build_picker_graph(env)
        if not hasattr(self, "picker_routes"):
            self.picker_routes = {}
            self.picker_candidate_tasks = {}          # picker -> [((gx,gy), [routes])]
        aa, ap = self.assigned_agvs, self.assigned_pickers
        needing = [a for a in aa
                   if aa[a].mission_type in (MissionType.PICKING, MissionType.RETURNING)]
        need_cells = {(aa[a].location_x, aa[a].location_y) for a in needing}
        for p in list(ap):                            # release pickers no longer needed
            if (ap[p].location_x, ap[p].location_y) not in need_cells:
                ap.pop(p)
        taken = {(m.location_x, m.location_y) for m in ap.values()}
        for p in [pk for pk in self.pickers if pk not in ap]:
            cands = [a for a in needing if (aa[a].location_x, aa[a].location_y) not in taken]
            if not cands:
                break
            scored = []                               # (score, gx, gy, best_route, all_routes)
            for a in cands:
                gx, gy = aa[a].location_x, aa[a].location_y
                routes = _rt.k_shortest_routes(Gp, (p.x, p.y), (gx, gy), k=self.K_ROUTES)
                if not routes:
                    continue
                best_r = self._pick_picker_route(routes)        # hook: default shortest; may use congestion
                picker_arrival = len(best_r) - 1
                agv_eta = len(getattr(a, "path", None) or [])   # AGV availability (committed ETA)
                rendezvous = max(picker_arrival, agv_eta)
                agv_wait = max(0, picker_arrival - agv_eta)     # AGV waits for me -> delays task
                picker_wait = max(0, agv_eta - picker_arrival)  # I wait for the AGV -> wasted time
                # ALREADY PARKED AND WAITING: no path left AND standing on the rendezvous cell.
                # Its agv_wait above is just the picker's travel distance (agv_eta=0), i.e. the
                # maximum penalty, for a robot that is stalled RIGHT NOW. Treat that wait as sunk.
                stalled = (self.STALL_BONUS and agv_eta == 0 and (a.x, a.y) == (gx, gy))
                if stalled:
                    agv_wait = 0
                # One task = AGV subtask + PICKER subtask; rank the picker subtask by the SAME
                # parent-task utility the AGV funnel uses (value x lateness-decay, makeable-
                # first). Computed from the rendezvous-aware finish, so arriving late -> later
                # finish -> lower score AUTOMATICALLY captures the AGV-wait (no ad-hoc penalty).
                sid = self.assigned_items.get(a)
                sh = env.shelfs[sid - 1] if sid else None
                score = self._picker_score(sh, gx, gy, rendezvous, agv_wait, picker_wait, now)
                score += self._picker_task_adjust(gx, gy, best_r)   # hook: congestion-aware rendezvous
                if stalled:
                    score += self.STALL_BONUS                       # unblock the stalled AGV
                scored.append((score, gx, gy, best_r, routes))
            if not scored:
                continue
            scored.sort(key=lambda x: x[0], reverse=True)
            # HOOK (symmetric to the AGV funnel's _pick_winner): default is the greedy argmax; the
            # picker SEQUENCER overrides this to re-simulate the top-K and rank by banked value.
            _win = self._pick_picker_winner(scored, p)
            if _win is None:
                continue                      # picker declines to commit this round (WAIT branch won)
            _, gx, gy, best_r, routes = _win
            ap[p] = Mission(MissionType.PICKING, self.coords_to_id[(gy, gx)], gx, gy, now)
            taken.add((gx, gy))
            self.picker_routes[p] = best_r
            self.picker_candidate_tasks[p] = [((s[1], s[2]), s[4]) for s in scored[:5]]


class BatteryAwareController(RushValueController):
    """RUSH + planner-level battery handling — finishes the battery model.

    - CHARGE DECISION: a FREE robot below `GO_CHARGE` is sent to its nearest dedicated
      charger (a CHARGING mission) and held until `FULL`, then released. Stage-0
      emergency-charge rule (precursor to Part B's charge support action); keeps
      strandings near zero without interrupting a robot mid-task.
    - MOVEMENT GATE: a robot at/below the battery floor away from a charger is STRANDED
      and gated to no-op (it stops) — the safety backstop.
    Battery drains/charges via BatteryTracker on dedicated chargers reachable by BOTH
    robot types (see wwm_sim.battery.default_chargers). Pass a BatteryConfig to compress
    `steps_per_charge` so battery actually binds within an episode."""

    GO_CHARGE = 0.35     # a free robot below this heads to a charger
    FULL = 0.95          # released from the charger once topped up to here

    def __init__(self, env, battery_config=None):
        super().__init__(env)
        self.battery = BatteryTracker(env, battery_config)

    def act(self):
        self.battery.step()              # apply last step's drain/charge from movement
        self._manage_charging()
        actions = super().act()          # RUSH assigns tasks to the remaining free robots
        for i, a in enumerate(self.agents):
            if self.battery.is_flat(a):  # planner-level movement gate: stranded -> stop
                actions[i] = 0
        return actions

    def _manage_charging(self):
        bat, aa, ap = self.battery, self.assigned_agvs, self.assigned_pickers
        for a in list(aa):               # release AGVs done charging
            if aa[a].mission_type == MissionType.CHARGING and bat.is_full(a):
                aa.pop(a)
                self.assigned_items.pop(a, None)
        for p in list(ap):               # release pickers done charging
            if ap[p].mission_type == MissionType.CHARGING and bat.is_full(p):
                ap.pop(p)
        for a in self.agvs:              # send low free AGVs to charge (never mid-carry)
            if a not in aa and not a.carrying_shelf and bat.needs_charge(a, self.GO_CHARGE):
                self._send_to_charger(a, aa)
        for p in self.pickers:           # send low free pickers to charge
            if p not in ap and bat.needs_charge(p, self.GO_CHARGE):
                self._send_to_charger(p, ap)

    def _send_to_charger(self, robot, assign_dict):
        c = self.battery.nearest_charger(robot)
        if c is None:
            return
        loc_id = self.coords_to_id.get((c[1], c[0]))     # chargers are (x,y); key is (y,x)
        if loc_id is not None:
            assign_dict[robot] = Mission(MissionType.CHARGING, loc_id, c[0], c[1], self.timestep)


CONTROLLERS = {"priority": PriorityController,
               "feasible": FeasiblePriorityController,
               "value": ValuePriorityController,
               "rush": RushValueController,
               "parta": PartAController,
               "battery": BatteryAwareController}
# NOTE: a per-task doomed-window variant using wwm_sim.rollout (RolloutRushController)
# was tested and LOST to the global adaptive window (on-time 202-204 vs 206; total ~tied)
# — completion time here is congestion/picker-wait dominated, not geometry-dominated, so a
# distance-based per-task estimate is noisier than the empirical mean. The rollout ENGINE
# is kept (wwm_sim/rollout.py) for its real use: Part A plan SCORING (arrival/finish/
# battery/margins). See docs/NOTES.md 2026-07-09.


class PriorityDashboard:
    def __init__(self, env_id, seed, deadlines_source, steps_per_charge=300.0,
                 controller="rush", values_source=None):
        import matplotlib.pyplot as plt

        self.plt = plt
        self.env = gym.make(env_id).unwrapped
        self.env.reset(seed=seed)
        self.n_attached = attach_deadlines(self.env, load_deadlines(deadlines_source))
        if values_source:
            attach_values(self.env, load_values(values_source))
        self.ctrl = CONTROLLERS[controller](self.env)
        self.controller_name = controller
        self.bat = BatteryTracker(self.env, BatteryConfig(steps_per_charge=steps_per_charge))
        self.rr: Counter = Counter()
        self.completed = []  # shelf ids delivered, in order
        self.on_time = 0            # on-time delivery count
        self.on_time_value = 0.0    # total value delivered on time
        self.cum = {"deliveries": 0, "clashes": 0, "stucks": 0, "steps": 0}
        self.max_steps = 500
        self.done = False

        self.fig = plt.figure(figsize=(16, 10.5))
        self.fig.suptitle(f"{controller.capitalize()}-priority sim  |  {env_id}  |  seed {seed}",
                          fontsize=13, fontweight="bold", y=0.985)
        gs = self.fig.add_gridspec(3, 2, width_ratios=[1.25, 1],
                                   height_ratios=[2.8, 1.05, 1.25], hspace=0.4, wspace=0.14,
                                   top=0.92, bottom=0.05)
        self.ax_grid = self.fig.add_subplot(gs[0:2, 0])
        self.ax_tasks = self.fig.add_subplot(gs[0, 1])
        self.ax_stats = self.fig.add_subplot(gs[1, 1])
        self.ax_batt = self.fig.add_subplot(gs[2, 0])
        self.ax_rr = self.fig.add_subplot(gs[2, 1])

    # ------------------------------------------------------------------ step
    def _step(self):
        if self.done or self.cum["steps"] >= self.max_steps:
            return
        actions = self.ctrl.act()
        _, _, term, trunc, info = self.env.step(actions)
        self.bat.step()
        for a, b in getattr(self.env, "clash_pairs_this_step", []):
            self.rr[tuple(sorted((a, b)))] += 1
        for sid, _a in getattr(self.env, "deliveries_this_step", []):
            self.completed.append(sid)
            sh = self.env.shelfs[sid - 1]
            if sh.deadline is not None and (self.cum["steps"] + 1) <= sh.deadline:
                self.on_time += 1
                self.on_time_value += task_value(sh)
        accumulate(self.cum, info)
        self.done = all(term) or all(trunc)

    # ------------------------------------------------------------------ draw
    # short words for the two subtasks
    _AGV_WORD = {"PICKING": "fetch", "DELIVERING": "carry", "RETURNING": "return"}

    def _assignment_map(self):
        """shelf_id -> (AGV label, short AGV subtask word)."""
        m = {}
        for agv in self.ctrl.agvs:
            if agv in self.ctrl.assigned_agvs:
                sid = self.ctrl.assigned_items.get(agv)
                if sid is not None:
                    state = self.ctrl.assigned_agvs[agv].mission_type.name
                    m[sid] = (f"AGV{agv.id}", self._AGV_WORD.get(state, state.lower()))
        return m

    def _picker_map(self):
        """(shelf x, y) -> (Picker label, short Picker subtask word)."""
        m = {}
        for pk in self.ctrl.pickers:
            mission = self.ctrl.assigned_pickers.get(pk)
            if mission is not None:
                arrived = (pk.x == mission.location_x and pk.y == mission.location_y)
                m[(mission.location_x, mission.location_y)] = (
                    f"PCK{pk.id}", "loading" if arrived else "coming")
        return m

    def _draw_grid(self):
        ax = self.ax_grid
        ax.clear()
        img = grid_image(self.env)
        for (cx, cy) in self.bat.chargers:          # highlight charger cells in gold
            img[cy, cx] = C_CHARGER
        ax.imshow(img, origin="upper", interpolation="nearest")
        # marker size scales with grid so it fits any env (large grid -> smaller markers)
        span = max(self.env.grid_size)
        s_agv, s_pk = int(4500 / span), int(2600 / span)
        agv_xy, agv_c, pk_xy = agent_scatter(self.env)
        if len(agv_xy):
            ax.scatter(agv_xy[:, 0], agv_xy[:, 1], marker="H", s=s_agv, c=agv_c,
                       edgecolors="k", linewidths=1.0, zorder=3)
        if len(pk_xy):
            ax.scatter(pk_xy[:, 0], pk_xy[:, 1], marker="D", s=s_pk, c=[C_PICKER],
                       edgecolors="k", linewidths=1.0, zorder=3)
        ax.set_xticks([]); ax.set_yticks([])
        # compact colour key (incl. gold charger)
        ax.text(0.0, -0.02,
                "orange=AGV  red=AGV carrying  blue=picker  teal=task shelf  "
                "purple=idle shelf  grey=dock  gold=charger",
                fontsize=7.5, va="top", ha="left", transform=ax.transAxes)

    def _draw_tasks(self):
        ax = self.ax_tasks
        ax.clear(); ax.axis("off")
        now = self.cum["steps"]
        agv_map, pk_map = self._assignment_map(), self._picker_map()
        ranked = self.ctrl._task_order()  # the controller's ACTUAL priority order
        window = getattr(self.ctrl, "window", 0)
        title = "TASKS BY PRIORITY  (each task = AGV subtask + Picker subtask)"
        if self.controller_name == "rush":
            title += (f"\n(value-first among makeable; late tasks rush-ordered by "
                      f"DECAYED value; window ~{window} steps*)")
        elif self.controller_name in ("feasible", "value"):
            lead = "value-first among makeable; " if self.controller_name == "value" else ""
            title += f"\n({lead}tasks that can't finish in ~{window} steps* shoved to bottom)"
        ax.text(0.0, 1.0, title, fontsize=9, fontweight="bold", va="top", transform=ax.transAxes)
        header = f"  {'shelf':<6} {'deadline':<9} {'value':<6} {'AGV subtask':<12} {'Picker'}"
        lines = [header]
        for s in ranked[:10]:
            if s.deadline is None:
                due = "none"
            elif s.deadline - now < window:
                due = f"{s.deadline}*"            # can't finish before deadline
            else:
                due = str(s.deadline)
            val = f"{task_value(s):.0f}"
            agv = f"{agv_map[s.id][0]} {agv_map[s.id][1]}" if s.id in agv_map else "-- waiting"
            pk = f"{pk_map[(s.x, s.y)][0]} {pk_map[(s.x, s.y)][1]}" if (s.x, s.y) in pk_map else "-- none"
            lines.append(f"  {s.id:<6} {due:<9} {val:<6} {agv:<12} {pk}")
        if len(ranked) > 10:
            lines.append(f"  (+{len(ranked) - 10} more tasks)")
        ax.text(0.0, 0.86, "\n".join(lines), fontsize=8, family="monospace",
                va="top", ha="left", transform=ax.transAxes)

        # completed tasks
        recent = ", ".join(str(x) for x in self.completed[-14:]) or "-"
        ax.text(0.0, 0.20, f"COMPLETED TASKS  ({len(self.completed)} total)\n  * = can't finish before its deadline (deprioritised)\n  recent shelves: {recent}",
                fontsize=8, family="monospace", va="top", ha="left", transform=ax.transAxes)

    def _draw_stats(self):
        ax = self.ax_stats
        ax.clear(); ax.axis("off")
        rows = [
            ["Step", str(self.cum["steps"])],
            ["Deliveries", str(self.cum["deliveries"])],
            ["On-time deliveries", str(self.on_time)],
            ["On-time VALUE", f"{self.on_time_value:.0f}"],
            ["Reroutes", str(self.cum["clashes"])],
            ["Stucks", str(self.cum["stucks"])],
        ]
        # table constrained to the lower 84% so the title above never overlaps it
        t = ax.table(cellText=rows, colLabels=["Metric", "value"], cellLoc="center",
                     colWidths=[0.6, 0.4], bbox=[0.0, 0.0, 1.0, 0.84])
        t.auto_set_font_size(False); t.set_fontsize(9)
        for c in range(2):
            t[0, c].set_facecolor("#333333"); t[0, c].set_text_props(color="w", fontweight="bold")
        ax.text(0.5, 0.97, "Running totals", ha="center", va="top",
                fontsize=10, fontweight="bold", transform=ax.transAxes)

    def _draw_battery(self):
        ax = self.ax_batt
        ax.clear()
        agents = self.env.agents
        labels, vals, colors = [], [], []
        for a in agents:
            labels.append(("AGV" if a.type == AgentType.AGV else "PCK") + str(a.id))
            lvl = self.bat.level[a.id] * 100
            vals.append(lvl)
            colors.append((0.55, 0.55, 0.55) if a.id in self.bat.stranded
                          else (0.85, 0.1, 0.1) if lvl <= 20
                          else (0.95, 0.75, 0.1) if lvl <= 50 else (0.15, 0.65, 0.2))
        y = list(range(len(labels)))
        ax.barh(y, vals, color=colors, edgecolor="k", height=0.72)
        ax.axvline(self.bat.cfg.floor * 100, color="red", ls="--", lw=1)
        fs = 6 if len(labels) > 8 else 7
        for yi, v in enumerate(vals):
            ax.text(2, yi, f"{v:.0f}%", va="center", fontsize=fs,
                    color="white" if v > 25 else "black")
        ax.set_xlim(0, 100); ax.set_ylim(-0.6, len(labels) - 0.4); ax.invert_yaxis()
        ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=fs)
        ax.set_xticks([0, 50, 100]); ax.tick_params(labelsize=6)
        ax.set_title("Battery", fontsize=10, fontweight="bold")

    def _draw_reroutes(self):
        ax = self.ax_rr
        ax.clear(); ax.axis("off")
        ax.text(0.0, 1.0, "Reroute pairs", fontsize=10, fontweight="bold",
                va="top", transform=ax.transAxes)

        def lbl(i):
            a = self.env.agents[i - 1]
            return ("AGV" if a.type == AgentType.AGV else "PCK") + str(i)

        if not self.rr:
            ax.text(0.0, 0.72, "  (none yet)", fontsize=9, family="monospace",
                    va="top", transform=ax.transAxes)
            return
        lines = [f"  {lbl(a)} <-> {lbl(b)} : {n}" for (a, b), n in self.rr.most_common(5)]
        lines.append(f"  total: {sum(self.rr.values())}")
        ax.text(0.0, 0.74, "\n".join(lines), fontsize=9, family="monospace",
                va="top", transform=ax.transAxes)

    def render_current(self):
        self._draw_grid(); self._draw_tasks(); self._draw_stats()
        self._draw_battery(); self._draw_reroutes()

    def run_live(self, fps):
        from matplotlib.animation import FuncAnimation
        interval = max(1, int(1000 / fps)) if fps > 0 else 200

        def update(_):
            self._step(); self.render_current()

        self._anim = FuncAnimation(self.fig, update, interval=interval, cache_frame_data=False)
        self.plt.show()

    def snapshot(self, path, step):
        for _ in range(step):
            if self.done:
                break
            self._step()
        self.render_current()
        self.fig.savefig(path, dpi=110, bbox_inches="tight")
        print(f"saved snapshot after {self.cum['steps']} steps -> {path}")


def parse_args():
    p = argparse.ArgumentParser(description="Single priority-assignment warehouse dashboard.")
    p.add_argument("--env", default="wwm_sim-large-8agvs-4pickers-globalobs-v1")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--deadlines", default="data/deadlines_example.txt")
    p.add_argument("--values", default="data/values_example.txt")
    p.add_argument("--fps", type=float, default=3.0)
    p.add_argument("--steps-per-charge", type=float, default=300.0)
    p.add_argument("--controller", choices=["rush", "value", "feasible", "priority", "parta"], default="rush",
                   help="'parta' = per-robot Part A funnel (cheap screen -> Yen's k-routes -> "
                        "filter -> score -> best-route rank -> commit robot->task->route); "
                        "'rush' = value x feasibility PLUS lateness-decay rush-ordering of "
                        "doomed tasks (per-task hardness g); DEFAULT; "
                        "'value' = value x feasibility (value-first among makeable); "
                        "'feasible' = slack-aware (value-blind); "
                        "'priority' = naive earliest-deadline-first.")
    p.add_argument("--snapshot", default=None)
    p.add_argument("--snapshot-step", type=int, default=60)
    return p.parse_args()


def main():
    args = parse_args()
    if args.snapshot:
        import matplotlib
        matplotlib.use("Agg")
    dash = PriorityDashboard(args.env, args.seed, args.deadlines, args.steps_per_charge,
                             args.controller, args.values)
    if args.snapshot:
        dash.snapshot(args.snapshot, args.snapshot_step)
    else:
        print(f"Priority sim: {args.env} | seed {args.seed} | {args.fps} steps/s")
        print("Close the window to stop.")
        dash.run_live(args.fps)


if __name__ == "__main__":
    main()
