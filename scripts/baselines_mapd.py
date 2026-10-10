"""Established task-assignment baselines: Token Passing and Hungarian assignment (2026-10-09).

Written because the benchmark's only outside baseline was the simulator's own FIFO dispatcher; the
other two arms (`rush`, `marl`) are ours, so "better than published work" was never actually tested.
These three are the standard comparisons from the MAPD and MRTA literature, implemented against the
SAME execution layer as FIFO -- identical routing, picker dispatch, mission state machine, docks --
so the only thing that differs between an arm and FIFO is which free AGV gets which task.

  tp      TOKEN PASSING (Ma et al. 2017, "Lifelong MAPF for Online Pickup and Delivery Tasks").
          The canonical MAPD rule: agent-centric, one agent claims at a time, each taking the task
          whose pickup is nearest to it. Deadline-blind by construction -- MAPD optimises service
          time and makespan, not on-time value.
  hung    HUNGARIAN / CENTRAL. Optimal myopic assignment: minimise TOTAL travel cost over the
          (free AGV x unassigned task) matrix, solved exactly per tick. Also deadline-blind. This
          is the strongest myopic travel-cost assignment that exists -- no heuristic can beat it on
          its own objective -- so it bounds what better myopic matching can buy.
  hungv   HUNGARIAN ON THE PAPER'S OBJECTIVE. The same exact solver, but the cost matrix is
          projected on-time value: an (agv, task) pair is worth the task's value if the travel
          estimate lands inside the deadline and 0 if it does not. This is the scientifically
          important arm -- it is optimal, myopic, and it optimises the thing we are measuring, so
          `mpc` beating it isolates the value of LOOKING AHEAD from the value of the objective.

Deadline-blind arms are reported as-is rather than quietly repaired: the point is partly that
methods built for throughput do not transfer to a deadline objective, and `hungv` is the control
that separates that effect from the assignment rule itself.

Like `fifo` and `rush`, these run with free energy (no battery constraint), which is an advantage
to them over champ/mpc.

Cost matrices use a two-stage screen -- Manhattan to pick the nearest TASK_CAP tasks per tick, then
true shortest-path distance within that set -- because an unscreened matrix is ~960 A* calls/tick.
Every arm here shares the screen, so it cannot favour one of them.
"""
from __future__ import annotations

import numpy as np

from sim_dashboard import FIFOController, Mission, MissionType

TASK_CAP = 20            # tasks scored with true path cost per tick (Manhattan-screened)
BIG = 10_000.0           # stand-in for "unreachable" in a cost matrix
TIE_EPS = 1e-3           # distance weight in the value matrix: breaks ties, never outranks value


class _AdaptiveWindow:
    """The heuristic baselines' completion estimate, verbatim.

    `window` is a property of PriorityController, not of FIFOController, so an arm inheriting from
    FIFO does not get it. Replicated here with the same constants so `hungv` judges makeability by
    exactly the quantity ValuePriorityController and RushValueController use -- it must not be
    handed a sharper finish estimate than the baselines it is compared against.
    """
    _window_fallback = 83
    _window_min_samples = 5
    _window_safety = 1.0

    @property
    def window(self):
        if len(self.durations) >= self._window_min_samples:
            return (sum(self.durations) / len(self.durations)) * self._window_safety
        return self._window_fallback


def _free_agvs(ctrl):
    return [a for a in ctrl.agvs
            if not a.busy and not a.carrying_shelf and a not in ctrl.assigned_agvs]


def _open_tasks(ctrl):
    taken = set(ctrl.assigned_items.values())
    return [t for t in ctrl.env.request_queue if t.id not in taken]


def _screen(agvs, tasks):
    """Nearest TASK_CAP tasks by Manhattan distance to the closest free AGV."""
    if len(tasks) <= TASK_CAP:
        return tasks
    def h(t):
        return min(abs(t.x - a.x) + abs(t.y - a.y) for a in agvs)
    return sorted(tasks, key=h)[:TASK_CAP]


def _dist(ctrl, agv, task):
    p = ctrl.env.find_path((agv.y, agv.x), (task.y, task.x), agv, care_for_agents=False)
    return BIG if not p else float(len(p))


def _commit(ctrl, agv, task):
    loc_id = ctrl.coords_to_id[(task.y, task.x)]
    ctrl.assigned_agvs[agv] = Mission(MissionType.PICKING, loc_id, task.x, task.y, ctrl.timestep)
    ctrl.assigned_items[agv] = task.id
    ctrl._assign_step.setdefault(task.id, ctrl.timestep)


class TokenPassingController(FIFOController):
    """Token Passing: each free agent in turn takes its own nearest open task.

    The difference from FIFO is the direction of the greedy choice. FIFO is task-centric (walk the
    queue in arrival order, give each task to its nearest free AGV); TP is agent-centric (walk the
    free agents, give each the task nearest to IT). Ma et al.'s token is what serialises the claims
    so two agents cannot take the same task -- here the token is just the loop order, which is the
    same thing in a single-threaded controller.
    """

    def _assign_tasks(self):
        tasks = _open_tasks(self)
        for agv in _free_agvs(self):
            if not tasks:
                return
            cand = _screen([agv], tasks)
            costs = [_dist(self, agv, t) for t in cand]
            j = int(np.argmin(costs))
            if costs[j] >= BIG:
                continue
            pick = cand[j]
            _commit(self, agv, pick)
            tasks.remove(pick)


class HungarianController(FIFOController):
    """Optimal myopic assignment minimising total travel cost (the CENTRAL baseline)."""

    def _cost(self, agvs, tasks):
        """Rows = free AGVs, cols = tasks. Lower is better."""
        return np.array([[_dist(self, a, t) for t in tasks] for a in agvs], dtype=float)

    def _assign_tasks(self):
        from scipy.optimize import linear_sum_assignment
        agvs = _free_agvs(self)
        if not agvs:
            return
        tasks = _open_tasks(self)
        if not tasks:
            return
        tasks = _screen(agvs, tasks)
        C = self._cost(agvs, tasks)
        rows, cols = linear_sum_assignment(C)
        for r, c in zip(rows, cols):
            if C[r, c] >= BIG:          # unreachable, or a padding cell: leave the AGV free
                continue
            _commit(self, agvs[r], tasks[c])


class HungarianValueController(_AdaptiveWindow, HungarianController):
    """Same solver, but the matrix is projected ON-TIME VALUE rather than travel cost.

    Cost = -value when the pair's travel estimate lands inside the deadline, 0 when it does not.
    The estimate is the true path length to the pickup plus `self.window`, the controller's own
    standing allowance for the rest of the trip (load, haul to a station, service) -- the same
    quantity ValuePriorityController uses for its makeable/doomed split, so this arm is not handed
    a better finish estimate than the heuristic baselines get.

    A pair worth 0 still costs 0, so the solver is indifferent between doomed assignments; that is
    correct under the objective (a late delivery banks nothing) and matches the paper's Eq. 2.
    """

    def _cost(self, agvs, tasks):
        now, w = self.timestep, self.window
        out = np.zeros((len(agvs), len(tasks)), dtype=float)
        for i, a in enumerate(agvs):
            for j, t in enumerate(tasks):
                d = _dist(self, a, t)
                if d >= BIG:
                    out[i, j] = BIG
                    continue
                v = 1.0 if t.value is None else float(t.value)
                if t.deadline is None:
                    base = -v * 0.5             # no deadline: real but unurgent value
                elif now + d + w <= t.deadline:
                    base = -v                   # makeable -> banks the full value
                else:
                    base = 0.0                  # doomed -> banks nothing
                out[i, j] = base + TIE_EPS * d
        return out


class HungarianValueSlackController(HungarianValueController):
    """hungv with the baselines' EXACT makeability test, to answer the handicap objection.

    `hungv` projects finish as now + d + window, where d is the fetch leg and window is the full
    assign->deliver duration -- so the fetch is counted twice and the test is conservative, marking
    tasks doomed that the heuristic arms would call makeable. That could understate the baseline.

    Here makeability is `deadline - now >= window`, character-for-character the test in
    FeasiblePriorityController and ValuePriorityController, with distance kept only as the
    tie-break. This arm is therefore the Hungarian form of ValuePriorityController: optimal
    matching among the tasks the heuristics themselves consider feasible. If it still loses to the
    planner, the loss is not an artefact of a conservative estimate.
    """

    def _cost(self, agvs, tasks):
        now, w = self.timestep, self.window
        out = np.zeros((len(agvs), len(tasks)), dtype=float)
        for i, a in enumerate(agvs):
            for j, t in enumerate(tasks):
                d = _dist(self, a, t)
                if d >= BIG:
                    out[i, j] = BIG
                    continue
                v = 1.0 if t.value is None else float(t.value)
                if t.deadline is None:
                    base = -v * 0.5
                elif (t.deadline - now) >= w:
                    base = -v
                else:
                    base = 0.0
                out[i, j] = base + TIE_EPS * d
        return out


ARMS = {"tp": TokenPassingController,
        "hung": HungarianController,
        "hungv": HungarianValueController,
        "hungv2": HungarianValueSlackController}
