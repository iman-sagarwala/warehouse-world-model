"""10-trial bake-off: Part A (per-robot funnel, AGV + picker) vs RUSH (scalar baseline).

Both get deadlines + values; hard 500-step cap. Part A = cheap screen -> Yen's k-routes ->
filter -> value×decay + rendezvous-sync score -> commit robot->task->route, for BOTH AGVs
and pickers. RUSH = scalar queue ranking + nearest-picker dispatch.
Metric: on-time deliveries and on-time value. Writes results/parta_vs_rush_10trials.csv.
Run: python scripts/verify_parta.py
"""
from __future__ import annotations

import csv
import os
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value
from sim_priority import PartAController, RushValueController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(10))
OUT = "results/parta_vs_rush_10trials.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def run(seed, cls):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    ctrl = cls(env)
    t = 0
    deliv = on = late = 0
    onv = 0.0
    done = False
    while not done and t < 500:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        for sid, _a in getattr(env, "deliveries_this_step", []):
            sh = env.shelfs[sid - 1]
            deliv += 1
            if sh.deadline is not None and t <= sh.deadline:
                on += 1
                onv += task_value(sh)
            else:
                late += 1
        done = all(term) or all(trunc)
    return {"deliveries": deliv, "on_time": on, "late": late, "on_time_value": round(onv, 1)}


def main():
    os.makedirs("results", exist_ok=True)
    metrics = ["deliveries", "on_time", "late", "on_time_value"]
    rows = []
    for s in SEEDS:
        rows.append((s, run(s, RushValueController), run(s, PartAController)))
        with open(OUT + ".progress", "w") as f:
            f.write(f"done seed {s}\n")

    def mean(k, i):
        return round(sum(r[i][k] for r in rows) / len(rows), 1)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["# Part A (AGV+picker funnel) vs RUSH (scalar), 10 seeds, hard 500-cap"])
        w.writerow(["env", ENV])
        w.writerow([])
        w.writerow(["seed"] + [f"rush_{k}" for k in metrics] + [f"parta_{k}" for k in metrics])
        for s, ru, pa in rows:
            w.writerow([s] + [ru[k] for k in metrics] + [pa[k] for k in metrics])
        w.writerow(["MEAN"] + [mean(k, 1) for k in metrics] + [mean(k, 2) for k in metrics])
        w.writerow([])
        w.writerow(["# RESULT"])
        w.writerow([f"on-time:       RUSH {mean('on_time',1)}  vs  Part A {mean('on_time',2)}"])
        w.writerow([f"on-time value: RUSH {mean('on_time_value',1)}  vs  Part A {mean('on_time_value',2)}"])
        w.writerow([f"deliveries:    RUSH {mean('deliveries',1)}  vs  Part A {mean('deliveries',2)}"])

    print(f"wrote {OUT}")
    print(f"on-time:       RUSH {mean('on_time',1)}  vs  Part A {mean('on_time',2)}")
    print(f"on-time value: RUSH {mean('on_time_value',1)}  vs  Part A {mean('on_time_value',2)}")
    print(f"deliveries:    RUSH {mean('deliveries',1)}  vs  Part A {mean('deliveries',2)}")
    if os.path.exists(OUT + ".progress"):
        os.remove(OUT + ".progress")


if __name__ == "__main__":
    main()
