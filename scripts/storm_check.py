"""Does the congestion map still prevent REROUTE STORMS under the demand stream?

The map's original justification (NOTES 2026-07-xx, uniform regime) was NOT a typical-seed gain -- it
was eliminating catastrophic gridlock seeds (parta 4 storms / max 1286 reroutes vs parta_cong 0 / 94).
A mean t-test dilutes a tail effect, so this reports the TAIL: reroute distribution, storm counts, and
low-percentile on-time value.

Run:  DEMAND=1 SEEDS=60 python scripts/storm_check.py
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
from sim_priority import PartAController
from congestion_policies import PartACongestionController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(int(os.environ.get("SEEDS", "60"))))
DEMAND = os.environ.get("DEMAND", "1") == "1"
STORM = 150
BUILD = {"parta": PartAController, "parta_cong": PartACongestionController}
_DL = None if DEMAND else load_deadlines("data/deadlines_example.txt")
_VL = None if DEMAND else load_values("data/values_example.txt")


def run(seed, name):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    if DEMAND:
        env.request_queue = []
        env.demand_model = DemandModel(env, seed=seed)
        env.demand_model.seed_initial(env, n=12)
    else:
        attach_deadlines(env, _DL)
        attach_values(env, _VL)
    ctrl = BUILD[name](env)
    rr = onv = 0.0
    t = 0
    done = False
    while not done and t < 500:
        _, _, term, trunc, info = env.step(ctrl.act())
        t += 1
        rr += int(info.get("clashes", 0))
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
    return rr, onv


def main():
    res = {p: {"rr": [], "otv": []} for p in BUILD}
    for s in SEEDS:
        for p in BUILD:
            rr, onv = run(s, p)
            res[p]["rr"].append(rr)
            res[p]["otv"].append(onv)
        print(f"seed {s}: " + "  ".join(
            f"{p} rr={res[p]['rr'][-1]:5.0f} otv={res[p]['otv'][-1]:5.0f}" for p in BUILD), flush=True)
    print(f"\n--- {'DEMAND' if DEMAND else 'UNIFORM'} regime, {len(SEEDS)} seeds ---")
    for p in BUILD:
        rr = np.array(res[p]["rr"]); otv = np.array(res[p]["otv"])
        print(f"  {p:<12} reroutes mean {rr.mean():7.1f}  med {np.median(rr):6.1f}  p90 {np.percentile(rr,90):7.1f} "
              f"max {rr.max():7.0f}  STORMS>{STORM} {int((rr>STORM).sum())}/{len(rr)}")
        print(f"  {'':<12} otv      mean {otv.mean():7.1f}  med {np.median(otv):6.1f}  p10 {np.percentile(otv,10):6.1f} "
              f"min {otv.min():6.1f}")
    a = np.array(res["parta"]["otv"]); b = np.array(res["parta_cong"]["otv"])
    print(f"\n  cong - parta: mean {(b-a).mean():+6.2f} | median {np.median(b-a):+6.2f} "
          f"| worst-10% seeds {(b-a)[np.argsort(a)[:max(1,len(a)//10)]].mean():+6.2f}")


if __name__ == "__main__":
    main()
