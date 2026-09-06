"""10-trial: VALUE (sheds doomed) vs RUSH (lateness-decay rush-ordering).

Both use the SAME makeable-first hard tier (so on-time work is never displaced). The
only difference is the DOOMED tier: VALUE orders it by raw value; RUSH orders it by
per-step DECAYED value (value * g**lateness) — rushing barely-late high-value tasks
and skipping hopelessly-late ones.

Decay modes (choose one):
  * GLOBAL (default): one decay rate for every task; the total-decayed-value metric is
    reported at g = 0.97 / 0.98 / 0.99 so the conclusion isn't hostage to one number.
  * WEIGHTED (--weighted): each task decays at its OWN rate (Shelf.hardness, loaded
    from data/hardness_example.txt; falls back to RushValueController.DECAY_G). The
    metric uses each task's own g -> a single weighted total. This is the SLA-aware
    setting (hard orders steep, soft orders gentle).

Metrics (per delivery of shelf S at step t, lateness = max(0, t - deadline)):
  * on-time value  = sum S.value over deliveries with lateness == 0 (late = 0).
  * decay-total(g) = sum S.value * g**lateness over ALL deliveries (on-time = full).

Writes results/rush_vs_value_10trials.csv.
Run: python scripts/verify_rush.py [--weighted] [--seeds N]
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import warnings

sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value
from wwm_sim.hardness import load_hardness, attach_hardness, task_hardness
from sim_priority import ValuePriorityController, RushValueController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
GLOBAL_GS = (0.97, 0.98, 0.99)
DEFAULT_G = RushValueController.DECAY_G
OUT = "results/rush_vs_value_10trials.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")
HD = load_hardness("data/hardness_example.txt")


def run(seed, cls, weighted):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    if weighted:
        attach_hardness(env, HD)          # each task carries its own decay g
    ctrl = cls(env)
    t = 0
    on = late = 0
    onv = 0.0
    dels = []                              # (lateness, value, g_task-or-None)
    done = False
    while not done:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        for sid, _a in getattr(env, "deliveries_this_step", []):
            sh = env.shelfs[sid - 1]
            v = task_value(sh)
            lateness = max(0, t - sh.deadline) if sh.deadline is not None else 0
            g = task_hardness(sh, DEFAULT_G) if weighted else None
            if lateness == 0:
                on += 1
                onv += v
            else:
                late += 1
            dels.append((lateness, v, g))
    r = {"on_time": on, "late": late, "on_time_value": round(onv, 1)}
    if weighted:
        r["decay_weighted"] = round(sum(v * (g ** l) for l, v, g in dels), 1)
    else:
        for gg in GLOBAL_GS:
            r[f"decay_{gg}"] = round(sum(v * (gg ** l) for l, v, _ in dels), 1)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weighted", action="store_true",
                    help="use per-task decay g (Shelf.hardness) instead of a global rate")
    ap.add_argument("--seeds", type=int, default=10)
    args = ap.parse_args()
    weighted = args.weighted
    seeds = list(range(args.seeds))
    decay_keys = ["decay_weighted"] if weighted else [f"decay_{g}" for g in GLOBAL_GS]
    metrics = ["on_time", "late", "on_time_value"] + decay_keys

    os.makedirs("results", exist_ok=True)
    rows = []
    for s in seeds:
        v = run(s, ValuePriorityController, weighted)
        r = run(s, RushValueController, weighted)
        rows.append((s, v, r))

    def mean(k, i):
        return round(sum(row[i][k] for row in rows) / len(rows), 1)

    mode = "WEIGHTED (per-task g = Shelf.hardness)" if weighted else f"GLOBAL g in {GLOBAL_GS}"
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["# VALUE (sheds doomed) vs RUSH (lateness-decay rush-ordering)"])
        w.writerow(["env", ENV])
        w.writerow(["decay mode", mode])
        w.writerow(["shared", "makeable-first hard tier; only the DOOMED ordering differs"])
        w.writerow(["on_time_value", "sum value of deliveries with lateness==0 (late = 0)"])
        w.writerow(["decay", "sum value * g**lateness over ALL deliveries (partial credit for late)"])
        w.writerow([])
        w.writerow(["# PER-TRIAL"])
        w.writerow(["seed"] + [f"value_{k}" for k in metrics] + [f"rush_{k}" for k in metrics])
        for s, v, r in rows:
            w.writerow([s] + [v[k] for k in metrics] + [r[k] for k in metrics])
        w.writerow(["MEAN"] + [mean(k, 1) for k in metrics] + [mean(k, 2) for k in metrics])
        w.writerow([])
        w.writerow(["# RESULT"])
        w.writerow([f"on-time value: VALUE {mean('on_time_value',1)} vs RUSH {mean('on_time_value',2)} (want ~=)"])
        for k in decay_keys:
            w.writerow([f"{k}: VALUE {mean(k,1)} vs RUSH {mean(k,2)} (want RUSH >)"])

    print(f"wrote {OUT}   [mode: {mode}]")
    print(f"on-time value:  VALUE {mean('on_time_value',1)}  vs  RUSH {mean('on_time_value',2)}")
    for k in decay_keys:
        print(f"{k}:  VALUE {mean(k,1)}  vs  RUSH {mean(k,2)}")


if __name__ == "__main__":
    main()
