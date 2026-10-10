"""Apparent Tardiness Cost dispatching, textbook and adapted (2026-10-09).

Maximising weighted on-time value is minimising the weighted number of tardy jobs -- P|r_j|Sum w_j U_j
in scheduling notation -- so the classical weighted-tardiness dispatching rules apply directly. ATC
(Vepsalainen & Morton 1987; Pinedo, *Scheduling*) is the canonical index for that family:

    pi_j(t) = (w_j / p_j) * exp( -max(0, d_j - t - p_j) / (K * pbar) )

Every term has a counterpart here: w_j is the order value, d_j its deadline, p_j the estimated time
to complete it, pbar the mean completion time, and K a look-ahead parameter. The rule degenerates
gracefully at both ends -- large K approaches weighted-shortest-processing-time, small K approaches
earliest-due-date among the jobs that are still makeable -- which is why K is swept rather than fixed.

Two arms, because the textbook rule and the warehouse differ in one respect:

  atc   TEXTBOOK. p_j is machine-independent, as ATC assumes: the controller's own adaptive
        completion window. The index orders the task queue and the inherited FIFO assignment gives
        each task to its nearest free AGV. This is the rule as published.
  atcx  ADAPTED. In a warehouse p_j is not machine-independent: how long a task takes depends on
        which robot takes it, because the fetch leg differs. Here the index is computed per
        (AGV, task) pair with p_j = travel distance to the pod + the completion window, and each
        free AGV in turn takes its highest-index task. This is the version adjusted to this world.

`rush`, the project's own heuristic, is an ad-hoc member of this same family -- makeable-first
tiering with value-decayed ordering of the doomed tier -- so these arms also establish how much of
its performance is attributable to the family rather than to the specific tiering.

FAIRNESS. K is swept and the best-performing value is reported, because the proposed system tunes
its own parameters on measured performance and handing the baseline an untuned constant would not be
a like-for-like comparison. Like FIFO, both arms run with free energy.

Note on p_j in `atcx`: the completion window measures the whole assign-to-deliver duration, which
already includes a fetch leg, so adding the travel distance double-counts it and makes p_j
conservative. The K sweep partly absorbs this, since K scales the slack term against pbar.
"""
from __future__ import annotations

import math

import numpy as np

from sim_dashboard import FIFOController, Mission, MissionType

BIG = 10_000.0


class _Window:
    """The adaptive completion estimate, identical to PriorityController's.

    `window` is defined on PriorityController, not FIFOController, so an arm inheriting from FIFO
    does not get it. Replicated with the same constants so these arms judge completion time by
    exactly the quantity the other heuristic baselines use.
    """
    _window_fallback = 83
    _window_min_samples = 5

    @property
    def window(self):
        if len(self.durations) >= self._window_min_samples:
            return sum(self.durations) / len(self.durations)
        return self._window_fallback


class ATCController(_Window, FIFOController):
    """Textbook ATC: machine-independent p_j, index orders the queue."""

    K = 2.0

    def _index(self, task, now, p, pbar):
        """pi_j(t). Jobs with no deadline get the ratio term only, with no urgency boost."""
        w = 1.0 if task.value is None else float(task.value)
        if task.deadline is None:
            return (w / max(p, 1e-6)) * math.exp(-1.0 / self.K)
        slack = max(0.0, task.deadline - now - p)
        return (w / max(p, 1e-6)) * math.exp(-slack / max(self.K * pbar, 1e-6))

    def _task_order(self):
        now, p = self.timestep, self.window
        return sorted(self.env.request_queue,
                      key=lambda s: -self._index(s, now, p, p))


class ATCPerRobotController(ATCController):
    """ATC adapted: p_j depends on which AGV takes the task, agent-centric claiming."""

    def _assign_tasks(self):
        env, now, pbar = self.env, self.timestep, self.window
        taken = set(self.assigned_items.values())
        tasks = [t for t in env.request_queue if t.id not in taken]
        free = [a for a in self.agvs
                if not a.busy and not a.carrying_shelf and a not in self.assigned_agvs]
        for agv in free:
            if not tasks:
                return
            # Manhattan screen first: a true path to every open task is ~120 A* calls per robot
            # per tick. The screen is the same one the Hungarian arms use.
            near = sorted(tasks, key=lambda t: abs(t.x - agv.x) + abs(t.y - agv.y))[:20]
            best, best_pi = None, -1.0
            for t in near:
                path = env.find_path((agv.y, agv.x), (t.y, t.x), agv, care_for_agents=False)
                if not path:
                    continue
                p = len(path) + pbar          # fetch leg + the rest of the trip
                pi = self._index(t, now, p, pbar)
                if pi > best_pi:
                    best, best_pi = t, pi
            if best is None:
                continue
            loc_id = self.coords_to_id[(best.y, best.x)]
            self.assigned_agvs[agv] = Mission(MissionType.PICKING, loc_id,
                                              best.x, best.y, self.timestep)
            self.assigned_items[agv] = best.id
            self._assign_step.setdefault(best.id, self.timestep)
            tasks.remove(best)


def _k(cls, k):
    """A runtime subclass pinning K, so the value survives the tuner's deepcopy."""
    return type("%sK%s" % (cls.__name__, str(k).replace(".", "p")), (cls,), {"K": float(k)})


# Arm names: atc/atcx use the default K; atc_k<value> pins one for the sweep.
ARMS = {"atc": ATCController, "atcx": ATCPerRobotController}
for _kv in (0.5, 1.0, 2.0, 3.0, 5.0, 8.0):
    ARMS["atc_k%s" % str(_kv).replace(".", "p")] = _k(ATCController, _kv)
    ARMS["atcx_k%s" % str(_kv).replace(".", "p")] = _k(ATCPerRobotController, _kv)
