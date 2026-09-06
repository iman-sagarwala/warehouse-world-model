"""Smoke-test the realistic demand stream (wwm_sim/demand.py).

Runs the champion (PartACongestionController) under a DemandModel instead of the toy uniform-resample,
and verifies the request queue EBBS AND FLOWS (not always-full), that arrivals show diurnal + burst
structure, and that popularity is skewed (a few hot shelves dominate). Prints a compact report and an
ASCII sparkline of queue depth over the episode.

Run:  python scripts/demo_demand.py
"""
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401  (registers env ids)
from wwm_sim.demand import DemandModel
from wwm_sim.values import task_value
from congestion_policies import PartACongestionController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEED = int(os.environ.get("SEED", "0"))


def spark(vals, width=60):
    bars = " .:-=+*#%@"
    if not vals:
        return ""
    # bucket into `width` columns, take mean per bucket
    n = len(vals)
    cols = []
    for c in range(width):
        lo, hi = c * n // width, (c + 1) * n // width
        seg = vals[lo:max(hi, lo + 1)]
        cols.append(sum(seg) / len(seg))
    mx = max(cols) or 1.0
    return "".join(bars[min(len(bars) - 1, int(v / mx * (len(bars) - 1)))] for v in cols)


def main():
    env = gym.make(ENV).unwrapped
    env.reset(seed=SEED)
    # attach the demand stream (overrides value/deadline per order; queue starts from the stream)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=SEED)
    env.demand_model.seed_initial(env, n=12)
    ctrl = PartACongestionController(env)

    qdepth = []                     # request-queue size each step
    arrivals_per_step = []          # new orders each step
    ordered = Counter()             # shelf.id -> times requested
    deliv = on = late = 0
    onv = 0.0
    prev_arrivals = 0

    t = 0
    done = False
    while not done and t < STEPS:
        before = env.demand_model.arrivals
        _, _, term, trunc, info = env.step(ctrl.act())
        t += 1
        new = env.demand_model.arrivals - before
        arrivals_per_step.append(new)
        qdepth.append(len(env.request_queue))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            sh = env.shelfs[sid - 1]
            deliv += 1
            ordered[sid] += 1
            if sh.deadline is not None and t <= sh.deadline:
                on += 1
                onv += task_value(sh)
            else:
                late += 1
        done = all(term) or all(trunc)

    dm = env.demand_model
    q = np.array(qdepth)
    ap = np.array(arrivals_per_step)
    lam = np.array(dm.rate_log)
    base_peak = dm.rate * 1.5       # max of the pure diurnal term (no burst)
    burst = int((lam > base_peak * 1.15).sum())   # steps where a Hawkes burst lifts lambda above diurnal

    print(f"=== Demand-stream smoke test (seed {SEED}, {t} steps) ===\n")
    print(f"  total arrivals          {dm.arrivals}")
    print(f"  deliveries              {deliv}   (on-time {on}, late {late})")
    print(f"  on-time value           {onv:.1f}")
    print()
    print(f"  queue depth  min/mean/max   {q.min()} / {q.mean():.1f} / {q.max()}")
    always_full = (q == q.max()).mean()
    print(f"  frac steps at max depth     {always_full:.2f}   (want << 1.0 => not always-full)")
    print(f"  arrivals/step  mean/max     {ap.mean():.2f} / {ap.max()}")
    print(f"  lambda  base/peak           {dm.rate:.3f} / {lam.max():.3f}")
    print(f"  burst steps (lambda lifted) {burst}")
    print()
    top = ordered.most_common(5)
    tot = sum(ordered.values()) or 1
    print(f"  delivered-order popularity (top 5 of {len(ordered)} distinct shelves):")
    for sid, c in top:
        print(f"    shelf {sid:>4}   {c:>3} orders   {100*c/tot:4.1f}%")
    print()
    print(f"  queue depth over time:  {spark(qdepth)}")
    print(f"  arrival rate lambda(t): {spark(dm.rate_log)}")


if __name__ == "__main__":
    main()
