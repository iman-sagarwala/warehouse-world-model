"""Why does a committed picker never arrive?

Seed 11: picker 13 is committed to (1,13) for 166 straight steps while AGV 2 waits there. Over the
first 100 steps of that wait it goes (12,7) -> (6,2) -> (3,0) -> (6,21), i.e. it ends FURTHER away than
it started and on the far side of the map. 13 cells to cover, 100 steps to do it, never arrives.

Trace it per step: position, distance to its committed target, path length, requested action, and
whether its target changed. Distinguishes:
  * target keeps changing            -> assignment thrash
  * path keeps being rebuilt         -> replan thrash
  * moves but distance not shrinking -> routing/oscillation
  * silenced (NOOP) most steps       -> referee starvation
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

SEED = int(os.environ.get("SEED", "11"))
PICKER = int(os.environ.get("PICKER", "13"))
T0, T1 = int(os.environ.get("T0", "352")), int(os.environ.get("T1", "490"))

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

pk = next(p for p in env.agents if p.id == PICKER)
stats = collections.Counter()
prev_tgt = None
prev_path = None
rows = []
for t in range(500):
    env.step(ctrl.act())
    if not (T0 <= t <= T1):
        continue
    m = ctrl.assigned_pickers.get(pk)
    tgt = (m.location_x, m.location_y) if m else None
    d = (abs(pk.x - tgt[0]) + abs(pk.y - tgt[1])) if tgt else None
    path = list(pk.path or [])
    stats["steps"] += 1
    if tgt != prev_tgt:
        stats["target CHANGED"] += 1
    if tgt is None:
        stats["no target"] += 1
    # A genuine REROUTE, not normal consumption. Walking pops the first cell, so `path != prev_path`
    # is true on every moving step and measures nothing. The route is unchanged iff the new path is
    # exactly the tail of the old one (moved) or identical to it (did not move).
    if prev_path is not None and path != prev_path[1:] and path != prev_path:
        stats["route REROUTED (not mere consumption)"] += 1
    if prev_path is not None and path == prev_path[1:]:
        stats["walked its existing route"] += 1
    stats["req %s" % str(pk.req_action).split(".")[-1]] += 1
    if not path:
        stats["path EMPTY (nothing to walk)"] += 1
    if t % 10 == 0 or t < T0 + 6:
        rows.append((t, (pk.x, pk.y), tgt, d, len(path), str(pk.req_action).split(".")[-1],
                     bool(getattr(pk, "busy", False))))
    prev_tgt, prev_path = tgt, path

print("seed %d, picker %d, steps %d-%d" % (SEED, PICKER, T0, T1))
print("  %-6s %-9s %-9s %-6s %-6s %-12s %s" % ("t", "pos", "target", "dist", "plen", "req_action", "busy"))
for r in rows:
    print("  %-6d %-9s %-9s %-6s %-6d %-12s %s" % (r[0], str(r[1]), str(r[2]), str(r[3]), r[4], r[5], r[6]))
print("\nover %d steps:" % stats["steps"])
for k, v in stats.most_common():
    if k == "steps":
        continue
    print("  %-34s %5d  (%.0f%%)" % (k, v, 100.0 * v / stats["steps"]))
