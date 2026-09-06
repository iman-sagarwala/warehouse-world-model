"""VERIFY the 'no choice on the stream' mechanism: measure how many AGVs are simultaneously PARKED
waiting for a picker, per step, under the deployed controller (sqwidepr), in day-list vs stream.

If day-list runs several-deep and stream ~1, the picker rarely faces a choice on the stream -> that
is why value-rate/urgency (choose-the-best-of-a-queue rules) stop paying off there.

Run:  python scripts/diag_queue_depth.py        (SEEDS env, default 8)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.demand import DemandModel
from congestion_policies import _SqWidePkRate, _SqWide
from sim_priority import MissionType

ENV = os.environ.get("ENVID", "wwm_sim-large-8agvs-4pickers-globalobs-v1")
SEEDS = int(os.environ.get("SEEDS", "8"))
STEPS = 500


def waiting_count(ctrl):
    """AGVs parked at their PICKING shelf, arrived and not yet loaded -> waiting for a picker."""
    aa = ctrl.assigned_agvs
    n = 0
    for a in aa:
        m = aa[a]
        if m.mission_type != MissionType.PICKING:
            continue
        arrived = (a.x == m.location_x and a.y == m.location_y and not getattr(a, "path", None))
        not_loaded = not getattr(a, "carrying_shelf", None)
        if arrived and not_loaded:
            n += 1
    return n


def run(seed, regime, ctrl_cls):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    if regime == "daylist":
        env.demand_model.seed_day_list(env, horizon=STEPS)
    else:
        env.demand_model.seed_initial(env, n=12)
    ctrl = ctrl_cls(env)
    depths = []
    t = 0
    done = False
    while not done and t < STEPS:
        act = ctrl.act()
        depths.append(waiting_count(ctrl))
        _, _, term, trunc, _i = env.step(act)
        t += 1
        done = all(term) or all(trunc)
    return np.array(depths)


def main():
    for regime in ("daylist", "stream"):
        for name, cls in [("stupid ", _SqWide), ("valrate", _SqWidePkRate)]:
            alld = np.concatenate([run(s, regime, cls) for s in range(SEEDS)])
            share_ge2 = float((alld >= 2).mean())
            print(f"{regime:8} {name}  mean waiting AGVs/step {alld.mean():.2f}  max {alld.max():.0f}  "
                  f"P(>=2, a CHOICE) {share_ge2:.2f}")
    print("\nIf value-rate cuts waiting depth on day-list but NOT on stream -> it only bites with a backlog.")


if __name__ == "__main__":
    main()
