"""When an AGV is parked at a pod waiting, WHY is no picker there?

Two possibilities with opposite fixes:
  A. a picker IS committed to this shelf and is still travelling  -> waiting is picker TRAVEL time.
     Fix = sync (hold the AGV back so it arrives with the picker) or more picker capacity.
  B. NO picker is assigned to this shelf at all                   -> a dispatch GAP.
     Fix = dispatch/preemption; re-scoring cannot help because `_picker_score` runs only ~94x per
     episode, all at task-creation time, and never again while the AGV sits there.

Also records how long the AGV ends up waiting in each case, since a short travel wait is unavoidable
and a long dispatch gap is pure loss.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.warehouse import CollisionLayers, AgentType, Action
from wwm_sim.demand import DemandModel
import congestion_policies as cp

KIND = collections.Counter()
WAITLEN = collections.defaultdict(list)

for seed in range(1, 25):
    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed, n_windows=162,
                     value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    env.picker_service_steps = 8
    env.station_service_steps = 6
    env.station_headway = True
    env.station_exit_priority = True
    env.free_pod_return = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    run = {}      # agv id -> [steps waited, kind at start]
    for t in range(500):
        env.step(ctrl.act())
        # which shelves have a picker committed (assigned or heading there)?
        committed = set()
        for p, m in getattr(ctrl, "assigned_pickers", {}).items():
            committed.add((m.location_x, m.location_y))
        for p in ctrl.pickers:
            if getattr(p, "path", None):
                committed.add(tuple(p.path[-1]))
        for a in env.agents:
            if a.type != AgentType.AGV:
                continue
            # CORRECTED: the robot must actually be ASKING to load. The old test (not carrying +
            # no path + on a shelf cell) also counted robots with NO TASK parked on a shelf cell, which
            # is what produced the retracted 205-step "wait" on seed 3.
            waiting = (a.carrying_shelf is None and a.req_action == Action.TOGGLE_LOAD
                       and env.grid[CollisionLayers.SHELVES, a.y, a.x])
            if not waiting:
                if a.id in run:
                    n_, k_ = run.pop(a.id)
                    WAITLEN[k_].append(n_)
                continue
            here = (a.x, a.y)
            pk_here = env.grid[CollisionLayers.PICKERS, a.y, a.x]
            if pk_here:
                continue                       # picker present, this is service not waiting
            kind = "A: picker committed, travelling" if here in committed else "B: NO picker assigned"
            if a.id not in run:
                run[a.id] = [0, kind]
            run[a.id][0] += 1
            KIND[kind] += 1
    for a_id, (n_, k_) in run.items():
        WAITLEN[k_].append(n_)

tot = sum(KIND.values())
print("AGV-steps parked at a pod with no picker present (24 off-peak episodes)")
print("  total %d\n" % tot)
print("  %-36s %9s %7s %10s %9s %9s" % ("kind", "steps", "share", "n waits", "median", "MEAN"))
for k, v in KIND.most_common():
    ls = sorted(WAITLEN[k])
    med = ls[len(ls) // 2] if ls else 0
    mean = sum(ls) / len(ls) if ls else 0
    print("  %-36s %9d %6.1f%% %10d %9d %9.1f" % (k, v, 100.0 * v / tot, len(ls), med, mean))
for k in WAITLEN:
    ls = sorted(WAITLEN[k])
    if ls:
        print("\n  %s: n=%d  max=%d  p90=%d" % (k, len(ls), ls[-1], ls[int(0.9 * len(ls))]))
