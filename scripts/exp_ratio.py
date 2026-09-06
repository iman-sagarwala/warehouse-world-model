"""exp_ratio -- AGV:picker ratio sweep. Is picker availability really the binding constraint?

Runs the value-loss autopsy (viz_value_loss machinery) across robot-count configs, 30 day-list
seeds each, and reports what happens to each loss cause. Two sweeps:
  PICKER sweep (fixed 8 AGV): 8x2 8x4 8x6 8x8   -- if picker-bound, banked rises + picker-wait loss
                                                   falls sharply as pickers are added
  AGV sweep   (fixed 4 pk):   4x4 6x4 8x4 10x4   -- if picker-bound, adding AGVs past ~8 does little
                                                   (or makes picker-wait WORSE: more AGVs, same pickers)

One config per invocation for easy parallelism:  CFG=8x2 SEEDS=30 python scripts/exp_ratio.py
Writes results/ratio_<cfg>.csv with per-seed buckets.
"""
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from viz_value_loss import _Tracer, best_case_t0, task_segments, dominant_cause

STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "30"))))
CFG = os.environ.get("CFG", "8x4")
N_AGV, N_PICK = (int(x) for x in CFG.split("x"))
ENV = f"wwm_sim-large-{N_AGV}agvs-{N_PICK}pickers-globalobs-v1"


def run_seed(seed):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _Tracer(env)
    by_aid = {a.id: a for a in ctrl.agvs}
    agv_xy = [(a.x, a.y) for a in ctrl.agvs]
    pk_xy = [(p.x, p.y) for p in ctrl.pickers]
    orders = []
    for sid, lst in env.demand_model.pending.items():
        for o in lst:
            orders.append({"sid": sid, "sx": o.shelf.x, "sy": o.shelf.y,
                           "value": float(o.value), "deadline": o.deadline})
    deliv = {}
    t, done = 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        for r in ctrl.tasks.values():
            if r["t_end"] is None:
                a = by_aid[r["aid"]]
                r["trace"].append((a.x, a.y, bool(a.carrying_shelf)))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            deliv.setdefault(sid, t)
            r = ctrl.tasks.get(sid)
            if r is not None and r["t_end"] is None:
                r["t_end"] = t
        done = all(term) or all(trunc)
    seg_by_sid = {sid: task_segments(env, r) for sid, r in ctrl.tasks.items() if r["t_end"] is not None}
    out = {"potential": 0.0, "banked": 0.0, "doomed": 0.0, "never": 0.0,
           "pick": 0.0, "block": 0.0, "dock": 0.0}
    for o in orders:
        out["potential"] += o["value"]
        bc = best_case_t0(env, o["sx"], o["sy"], agv_xy, pk_xy)
        makeable0 = (o["deadline"] is not None) and (o["deadline"] >= bc)
        D = deliv.get(o["sid"])
        if D is not None and o["deadline"] is not None and D <= o["deadline"]:
            out["banked"] += o["value"]
        elif not makeable0:
            out["doomed"] += o["value"]
        elif D is not None:
            cause = dominant_cause(seg_by_sid.get(o["sid"], {"pick": 1, "block": 0, "dockq": 0}))
            out[{"picker wait": "pick", "traffic block": "block", "dock queue": "dock"}[cause]] += o["value"]
        else:
            out["never"] += o["value"]
    return out


def main():
    os.makedirs("results", exist_ok=True)
    rows = [run_seed(s) for s in SEEDS]
    keys = ["potential", "banked", "doomed", "never", "pick", "block", "dock"]
    with open(f"results/ratio_{CFG}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["seed"] + keys)
        for s, r in zip(SEEDS, rows):
            w.writerow([s] + [round(r[k], 2) for k in keys])
    m = {k: np.mean([r[k] for r in rows]) for k in keys}
    print(f"{CFG} ({N_AGV} AGV / {N_PICK} pick), {len(rows)} seeds:")
    print(f"  potential {m['potential']:.0f}  banked {m['banked']:.0f} "
          f"({m['banked']/m['potential']*100:.0f}%)")
    print(f"  LOSS  picker-wait {m['pick']:.0f}  traffic {m['block']:.0f}  dock {m['dock']:.0f}  "
          f"never-served {m['never']:.0f}  doomed {m['doomed']:.0f}")


if __name__ == "__main__":
    main()
