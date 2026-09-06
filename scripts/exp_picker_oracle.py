"""exp_picker_oracle -- what if pickers were NEVER a constraint? (upper-bound oracle)

env.pickers_free = True lets an AGV load the instant it reaches the shelf -- a picker is always
present, so picker wait (BOTH travel and contention) is exactly zero. Paired vs the real fleet on
identical day-list seeds. The gap = the entire picker-rendezvous cost, the ceiling above the ratio
lever (which only removed contention). Also reports deliveries + on-time count so we can attribute
the gain: banked more because tasks FINISH SOONER (beat the cliff) and/or MORE tasks get served.

Run: SEEDS=30 python scripts/exp_picker_oracle.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "30"))))


def run(seed, free):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.pickers_free = bool(free)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _Urg8(env)
    onv = deliv = ontime = 0
    onv = 0.0
    t, done = 0, False
    while not done and t < STEPS:
        env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            deliv += 1
            if o.deadline is not None and t <= o.deadline:
                ontime += 1
                onv += o.value
        done = (t >= STEPS)
    return {"onv": onv, "deliv": deliv, "ontime": ontime}


def main():
    real = [run(s, False) for s in SEEDS]
    orac = [run(s, True) for s in SEEDS]
    def arr(rs, k): return np.array([r[k] for r in rs], float)
    ov_r, ov_o = arr(real, "onv"), arr(orac, "onv")
    d = ov_o - ov_r
    se = d.std(ddof=1) / np.sqrt(len(d))
    print(f"PICKER-UNCONSTRAINED ORACLE (pickers always present), {len(SEEDS)} day-list seeds")
    print(f"  real fleet 8x4  on-time value {ov_r.mean():7.1f}")
    print(f"  free pickers    on-time value {ov_o.mean():7.1f}")
    print(f"  GAIN {d.mean():+.1f}  ({100*d.mean()/ov_r.mean():+.1f}%)  SE {se:.1f}  t {d.mean()/se:+.1f}  "
          f"wins {(d>0).sum()}/{len(d)}")
    print(f"  deliveries {arr(real,'deliv').mean():.0f} -> {arr(orac,'deliv').mean():.0f}   "
          f"on-time count {arr(real,'ontime').mean():.0f} -> {arr(orac,'ontime').mean():.0f}")
    # attribution: value/order banked (are we banking more per delivery, or delivering more?)
    print(f"  value per on-time delivery: real {ov_r.sum()/max(1,arr(real,'ontime').sum()):.2f}  "
          f"oracle {ov_o.sum()/max(1,arr(orac,'ontime').sum()):.2f}")


if __name__ == "__main__":
    main()
