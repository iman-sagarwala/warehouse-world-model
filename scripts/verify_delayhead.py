"""Bake-off: does the trained DELAY HEAD fix Part A's traffic-blindness?

Four policies, 10 seeds, hard 500-step cap, same deadlines + values:
  FIFO        - raw first-come queue order (naive baseline)
  RUSH        - scalar: global adaptive window (traffic-CALIBRATED) then value
  Part A      - per-robot funnel with the traffic-BLIND rollout finish
  Part A+head - identical, but finish_s = finish + delay_head(feat) (traffic-AWARE)

The head is loaded from results/delay_head.pkl and wired into PartAController.delay_head.
If de-biasing the rollout's optimistic finish is what Part A was missing, Part A+head should
move toward / past RUSH on on-time value. Writes results/delayhead_bakeoff.csv.
Run: python scripts/verify_delayhead.py
"""
from __future__ import annotations

import csv
import os
import pickle
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import numpy as np
import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value
from sim_priority import PartAController, RushValueController
from sim_dashboard import FIFOController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(10))
OUT = "results/delayhead_bakeoff.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def load_head():
    with open("results/delay_head.pkl", "rb") as f:
        d = pickle.load(f)
    model, cols, best = d["model"], d["cols"], d.get("best_iteration")

    def head(feat):
        x = np.array([[feat[c] for c in cols]], dtype=float)
        return float(model.predict(x, num_iteration=best)[0])
    return head


HEAD = load_head()


def build(name):
    """name -> factory(env) -> controller."""
    if name == "fifo":
        return lambda env: FIFOController(env)
    if name == "rush":
        return lambda env: RushValueController(env)
    if name == "parta":
        return lambda env: PartAController(env)
    if name == "parta_head":
        def mk(env):
            c = PartAController(env)
            c.delay_head = HEAD
            return c
        return mk
    if name == "parta_window":
        # Part A's routing/sync/value, but Rush's CALIBRATED global window as the
        # makeable/doomed doability filter (instead of per-task rollout finish).
        def mkw(env):
            c = PartAController(env)
            c.USE_GLOBAL_WINDOW = True
            return c
        return mkw
    raise ValueError(name)


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


POLICIES = ["fifo", "rush", "parta", "parta_head", "parta_window"]
METRICS = ["deliveries", "on_time", "late", "on_time_value"]


def main():
    os.makedirs("results", exist_ok=True)
    factories = {p: build(p) for p in POLICIES}
    rows = []          # seed -> {policy: metricdict}
    for s in SEEDS:
        rec = {p: run(s, factories[p]) for p in POLICIES}
        rows.append((s, rec))
        with open(OUT + ".progress", "w") as f:
            f.write(f"done seed {s}\n")
        print(f"seed {s}: " + "  ".join(
            f"{p} otv={rec[p]['on_time_value']:.0f}" for p in POLICIES), flush=True)

    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["# Delay-head bake-off: FIFO / RUSH / Part A / Part A+head, 10 seeds, 500-cap"])
        w.writerow(["env", ENV])
        w.writerow([])
        w.writerow(["seed"] + [f"{p}_{k}" for p in POLICIES for k in METRICS])
        for s, rec in rows:
            w.writerow([s] + [rec[p][k] for p in POLICIES for k in METRICS])
        w.writerow(["MEAN"] + [mean(p, k) for p in POLICIES for k in METRICS])

    print("\n--- MEAN over 10 seeds ---")
    hdr = f"  {'policy':<12}" + "".join(f"{k:>14}" for k in METRICS)
    print(hdr)
    for p in POLICIES:
        print(f"  {p:<12}" + "".join(f"{mean(p, k):>14.1f}" for k in METRICS))
    if os.path.exists(OUT + ".progress"):
        os.remove(OUT + ".progress")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
