"""Tune Part A's sync penalty W_SYNC against ON-TIME VALUE (the policy objective).

Isolation test for the Part A < RUSH gap. Base = parta_window (PartAController with RUSH's
CALIBRATED global window as the makeable/doomed filter), so the ONLY thing left that differs
from RUSH among doable tasks is the scoring. Part A's makeable score is 1000+value MINUS
W_SYNC*picker_wait. At W_SYNC=0 the makeable ranking is PURE value = identical to RUSH's; as
W_SYNC grows Part A trades value for fast cycles (throughput). Sweep W_SYNC, watch on-time value.

We optimise ON-TIME VALUE (max), NOT MAE/RMSE -- those measure the delay head's regression error,
a different thing entirely. A grid (not Optuna) because it's a single dial and we want the whole
curve, not a sampler's guessed argmax. 10 seeds, 500-cap. Writes results/wsync_sweep.csv.
Run: python scripts/tune_wsync.py
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
GRID = [0.0, 0.1, 0.2, 0.3, 0.5]        # W_SYNC values (0.3 = current default)
OUT = "results/wsync_sweep.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def run(seed, factory):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    ctrl = factory(env)
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


def parta_window(w):
    def mk(env):
        c = PartAController(env)
        c.USE_GLOBAL_WINDOW = True     # RUSH's calibrated doability filter
        c.W_SYNC = w
        return c
    return mk


METRICS = ["deliveries", "on_time", "late", "on_time_value"]


def mean_over_seeds(factory):
    recs = [run(s, factory) for s in SEEDS]
    return {k: round(sum(r[k] for r in recs) / len(recs), 1) for k in METRICS}


def main():
    os.makedirs("results", exist_ok=True)

    print("reference: RUSH")
    rush = mean_over_seeds(lambda env: RushValueController(env))
    print(f"  RUSH  on_time_value={rush['on_time_value']}  on_time={rush['on_time']}  "
          f"deliveries={rush['deliveries']}  late={rush['late']}", flush=True)

    results = []
    for w in GRID:
        m = mean_over_seeds(parta_window(w))
        results.append((w, m))
        print(f"  W_SYNC={w:<4} on_time_value={m['on_time_value']}  on_time={m['on_time']}  "
              f"deliveries={m['deliveries']}  late={m['late']}", flush=True)
        with open(OUT + ".progress", "w") as f:
            f.write(f"done W_SYNC {w}\n")

    best_w, best_m = max(results, key=lambda x: x[1]["on_time_value"])

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["# W_SYNC sweep on parta_window (RUSH filter); objective = on_time_value; 10 seeds"])
        wr.writerow(["policy"] + METRICS)
        wr.writerow(["RUSH"] + [rush[k] for k in METRICS])
        for w, m in results:
            wr.writerow([f"parta_window W_SYNC={w}"] + [m[k] for k in METRICS])
        wr.writerow([])
        wr.writerow([f"# BEST W_SYNC = {best_w} -> on_time_value {best_m['on_time_value']} "
                     f"(RUSH {rush['on_time_value']})"])

    print("\n--- SWEEP RESULT (objective: max on_time_value) ---")
    print(f"  {'policy':<26}{'deliv':>8}{'on_time':>9}{'late':>7}{'on_time_val':>13}")
    print(f"  {'RUSH (reference)':<26}{rush['deliveries']:>8}{rush['on_time']:>9}"
          f"{rush['late']:>7}{rush['on_time_value']:>13}")
    for w, m in results:
        star = "  <- best" if w == best_w else ""
        print(f"  {'parta_window W_SYNC='+str(w):<26}{m['deliveries']:>8}{m['on_time']:>9}"
              f"{m['late']:>7}{m['on_time_value']:>13}{star}")
    if os.path.exists(OUT + ".progress"):
        os.remove(OUT + ".progress")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
