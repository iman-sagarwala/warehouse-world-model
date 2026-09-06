"""Sweep the picker value-vs-distance knob (RATE_ALPHA) to its plateau, paired vs urg8.

RATE_ALPHA in the picker value-rate score `tier + eff_v / Tp^alpha`:
  0   = pure value (distance ignored ~ today's greedy clustering)
  1   = value-rate (value per picker-time)
  >1  = lean harder toward nearby pickers
Runs urg8 (baseline) once and _PkRate at each alpha on the SAME day-list seeds; reports the paired
gain. Find where it plateaus at the highest value. Run: SEEDS=60 python scripts/exp_pkrate_sweep.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import _Urg8, _PkRate

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "60"))))
ALPHAS = [float(x) for x in os.environ.get("ALPHAS", "0.0,0.5,1.0,1.5,2.0,3.0").split(",")]


def run(seed, cls):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = cls(env)
    onv, t = 0.0, 0
    while t < STEPS:
        env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
    return onv


def main():
    base = np.array([run(s, _Urg8) for s in SEEDS])
    print(f"urg8 baseline: {base.mean():.1f}  ({len(SEEDS)} seeds)\n")
    print(f"  {'alpha':>6}{'pkrate':>9}{'d vs urg8':>11}{'SE':>6}{'t':>7}{'W/L':>9}")
    results = []
    for al in ALPHAS:
        _PkRate.RATE_ALPHA = al
        arr = np.array([run(s, _PkRate) for s in SEEDS])
        d = arr - base
        se = d.std(ddof=1) / np.sqrt(len(d))
        w, l = int((d > 0).sum()), int((d < 0).sum())
        results.append((al, arr.mean(), d.mean(), se))
        print(f"  {al:>6.1f}{arr.mean():>9.1f}{d.mean():>+11.2f}{se:>6.2f}{d.mean()/se:>+7.2f}{f'{w}/{l}':>9}",
              flush=True)
    best = max(results, key=lambda r: r[2])
    print(f"\nbest: alpha={best[0]} -> {best[2]:+.2f} vs urg8 (t {best[2]/best[3]:+.2f})")


if __name__ == "__main__":
    main()
