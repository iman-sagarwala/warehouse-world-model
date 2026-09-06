"""COMPLETION-TIME ORACLE: what is PERFECT knowledge of each task's true finish time worth?

The deadline check is `proj_late = (now + finish) - deadline`, deciding makeable (1000+v) vs doomed
(v*g^late). `finish` is EMPTY-WORLD -- zero delay, ever -- plus a constant pad. That threshold is
proven sensitive to ~4 steps (the LOAD_TIME sweeps: p=0.021 and p=0.009).

Pass 1 records (assign_step, predicted_finish) per task; combined with the actual delivery step that
gives each task's REALIZED delay. Pass 2 replays those delays to the planner via `_finish_delay`, so
every makeable/doomed call is made on TRUE completion time.

No predictor -- learned, rules-based, or a full fleet-rollout world model -- can beat the truth, so
this UPPER-BOUNDS the entire delay direction in one run.
  null  => stop; no delay model is worth building, and rung 3 needs no interference model.
  large => that gap is the prize, and a world model is justified.

Run:  DEMAND=0 SEEDS=30 python scripts/oracle_delay.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value
from congestion_policies import (PartACongestionDelayOracleController,
                                 PartACongestionPredRecordController)

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(int(os.environ.get("SEEDS", "30"))))
STEPS = 500
DEMAND = os.environ.get("DEMAND", "0") == "1"
_DL = None if DEMAND else load_deadlines("data/deadlines_example.txt")
_VL = None if DEMAND else load_values("data/values_example.txt")


def episode(seed, factory):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    if DEMAND:
        env.request_queue = []
        env.demand_model = DemandModel(env, seed=seed)
        env.demand_model.seed_initial(env, n=12)
    else:
        attach_deadlines(env, _DL)
        attach_values(env, _VL)
    ctrl = factory(env)
    onv = 0.0
    delays = {}
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for sid, _a in getattr(env, "deliveries_this_step", []):
            sh = env.shelfs[sid - 1]
            pr = getattr(ctrl, "pred_log", {}).get(sid)
            if pr is not None:                       # realized delay = actual elapsed - predicted
                at, pred = pr
                delays[sid] = (t - at) - pred
            if sh.deadline is not None and t <= sh.deadline:
                onv += task_value(sh)
        done = all(term) or all(trunc)
    return ctrl, onv, delays


def main():
    base, orac = [], []
    hits = misses = 0
    dvals = []
    for s in SEEDS:
        rec, v1, delays = episode(s, PartACongestionPredRecordController)
        oc, v2, _ = episode(s, lambda e: PartACongestionDelayOracleController(e, delay_truth=delays))
        base.append(v1)
        orac.append(v2)
        hits += oc.hits
        misses += oc.misses
        dvals += list(delays.values())
        print(f"seed {s}: champ={v1:.0f}  oracle={v2:.0f}  (tasks with truth: {len(delays)})", flush=True)
    a, b = np.array(base), np.array(orac)
    d = b - a
    se = d.std(ddof=1) / np.sqrt(len(d))
    ties = int((d == 0).sum())
    w = int((d > 0).sum())
    l = int((d < 0).sum())
    from math import comb
    dec = w + l
    p = 2 * sum(comb(dec, k) for k in range(0, min(w, l) + 1)) / 2 ** dec if dec else 1.0
    dv = np.array(dvals)
    print("")
    print(f"--- COMPLETION-TIME ORACLE, {len(d)} seeds, {'DEMAND' if DEMAND else 'UNIFORM'} ---")
    print(f"  champion          {a.mean():7.1f}")
    print(f"  delay-oracle      {b.mean():7.1f}")
    print(f"  effect {d.mean():+6.2f}  SE {se:4.2f}  t {d.mean()/se if se else 0:+5.2f}  "
          f"ties {ties}/{len(d)}  W-L {w}-{l}  sign p={min(p,1.0):.3f}")
    print(f"  realized delay: mean {dv.mean():+.1f}  median {np.median(dv):+.1f}  "
          f"p10 {np.percentile(dv,10):+.1f}  p90 {np.percentile(dv,90):+.1f}  (pad in use = 5)")
    print(f"  oracle lookups: {hits} hit / {misses} miss ({100*hits/max(hits+misses,1):.0f}% had truth)")


if __name__ == "__main__":
    main()
