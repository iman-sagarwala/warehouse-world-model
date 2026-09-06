"""Per-route-horizon ORACLE: a future trip counts only if it starts before THIS route ends.

No fixed horizon -- the window is the length of the specific journey being scored. Compares:
  champion              - layer 2 as shipped (guess, gate never bites)
  oracle_perroute       - true next trips, each counted only against routes it could actually overlap

Run:  DEMAND=0 SEEDS=120 python scripts/oracle_perroute.py
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
from congestion_policies import (PartACongestionPerRouteOracleController,
                                 PartACongestionRecordController)

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(int(os.environ.get("SEEDS", "120"))))
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
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        if DEMAND:
            for o in getattr(env, "fulfilled_this_step", []):
                if o.deadline is not None and t <= o.deadline:
                    onv += o.value
        else:
            for sid, _a in getattr(env, "deliveries_this_step", []):
                sh = env.shelfs[sid - 1]
                if sh.deadline is not None and t <= sh.deadline:
                    onv += task_value(sh)
        done = all(term) or all(trunc)
    return ctrl, onv


def main():
    base, per = [], []
    kept = dropped = 0
    for s in SEEDS:
        rec, v1 = episode(s, PartACongestionRecordController)
        log = rec.commit_log
        oc, v2 = episode(s, lambda e: PartACongestionPerRouteOracleController(e, log))
        base.append(v1)
        per.append(v2)
        kept += oc.oracle_hits
        dropped += oc.oracle_late
        print(f"seed {s}: champ={v1:.0f}  perroute={v2:.0f}", flush=True)
    a, b = np.array(base), np.array(per)
    d = b - a
    se = d.std(ddof=1) / np.sqrt(len(d))
    print("")
    print(f"--- PER-ROUTE ORACLE, {len(d)} seeds, {'DEMAND' if DEMAND else 'UNIFORM'} ---")
    print(f"  champion          {a.mean():7.1f}")
    print(f"  per-route oracle  {b.mean():7.1f}")
    print(f"  effect {d.mean():+6.2f}  SE {se:4.2f}  t {d.mean()/se:+5.2f} "
          f"CI [{d.mean()-1.96*se:+.1f},{d.mean()+1.96*se:+.1f}]  wins {int((d>0).sum())}/{len(d)}")
    tot = kept + dropped
    print(f"  future trips scored: {kept} counted / {dropped} dropped as too-late "
          f"({100.0*kept/max(tot,1):.0f}% counted)")


if __name__ == "__main__":
    main()
