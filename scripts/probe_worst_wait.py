"""Anatomy of the worst wait: seed 3, AGV 6, 205 consecutive steps parked at a pod.

For every step of the wait, record what the six pickers were doing and whether ANY of them was
committed to this AGV's rendezvous. That distinguishes:
  * nobody was ever sent          -> dispatch gap
  * one was sent but kept losing  -> it was committed elsewhere and never released (no preemption)
  * one was en route the whole time -> pure travel/congestion
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.warehouse import CollisionLayers, AgentType
from wwm_sim.demand import DemandModel
import congestion_policies as cp

SEED = int(os.environ.get("SEED", "3"))
WATCH = int(os.environ.get("WATCH", "6"))

env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
env.reset(seed=SEED)
env.request_queue = []
dm = DemandModel(env, seed=SEED, exogenous=True, horizon=500, window_index=SEED, n_windows=162,
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

agv = next(a for a in env.agents if a.id == WATCH)
served_by = collections.Counter()
pk_busy = collections.Counter()
wait = 0
start = None
samples = []
for t in range(500):
    env.step(ctrl.act())
    parked = (agv.carrying_shelf is None and not getattr(agv, "path", None)
              and env.grid[CollisionLayers.SHELVES, agv.y, agv.x]
              and not env.grid[CollisionLayers.PICKERS, agv.y, agv.x])
    if not parked:
        wait = 0
        continue
    if wait == 0:
        start = t
    wait += 1
    cell = (agv.x, agv.y)
    ap = getattr(ctrl, "assigned_pickers", {})
    committed = [p.id for p, m in ap.items() if (m.location_x, m.location_y) == cell]
    served_by["picker committed to MY cell" if committed else "NO picker committed to my cell"] += 1
    for p in ctrl.pickers:
        m = ap.get(p)
        pk_busy["picker %d busy elsewhere" % p.id] += 1 if m is not None else 0
    if wait in (1, 25, 50, 100, 150, 200, 205):
        others = []
        for p in ctrl.pickers:
            m = ap.get(p)
            others.append("p%d@%s%s" % (p.id, (p.x, p.y),
                                        ("->%s" % ((m.location_x, m.location_y),)) if m else " FREE"))
        samples.append((t, wait, cell, committed, "  ".join(others)))

print("seed %d, AGV %d -- longest wait started at t=%s" % (SEED, WATCH, start))
print("\nDuring the wait:")
for k, v in served_by.most_common():
    print("  %-36s %d steps" % (k, v))
print("\nSnapshots (t, waited, my cell, pickers committed to me, all pickers):")
for (t, w, cell, comm, others) in samples:
    print("  t=%-4d waited=%-4d cell=%-9s committed_to_me=%s" % (t, w, str(cell), comm or "NONE"))
    print("        %s" % others)
