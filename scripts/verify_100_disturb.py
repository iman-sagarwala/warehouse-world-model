"""100-seed comparison WITH disturbances (rate 0.1) to settle the high-variance question:
under disturbances, is parta_head really better than the champion, or a fluke?

  champ_rigid    - parta_congestion, no adherence-release on disturbance
  champ_release  - parta_congestion + disturbance-aware adherence release (validated tweak)
  parta_head     - Part A + baseline delay head (no congestion machinery)
  dl_cong        - congestion -> DEADLINE only, DEADLINE-CONDITIONAL route ranking (updated version)

All get disturb_drop_adherence=True for parity (no-op where there's no adherence). Paired disturbance
schedule per seed. CSV rewritten each seed. Run: python scripts/verify_100_disturb.py  (SEEDS env, 100)
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

import numpy as np
import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value
from congestion_policies import (PartABaselineHeadController, PartACongestionController,
                                  PartADeadlineCongController)

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
N_SEEDS = int(os.environ.get("SEEDS", "100"))
SEEDS = list(range(N_SEEDS))
DIST_RATE = 0.1
OUT = "results/disturb_100.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")

POLICIES = ["champ_rigid", "champ_release", "parta_head", "dl_cong"]
METRICS = ["deliveries", "on_time", "late", "on_time_value", "reroutes", "stucks", "disturb_reroutes"]


def make(name, env):
    if name == "parta_head":
        ctrl = PartABaselineHeadController(env)
    elif name == "dl_cong":
        ctrl = PartADeadlineCongController(env)
    else:
        ctrl = PartACongestionController(env)
    env.disturb_drop_adherence = (name != "champ_rigid")     # release on for all except rigid
    return ctrl


def run(seed, name):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    env.disturb_rate = DIST_RATE
    env._disturb_rng = np.random.RandomState(seed)
    ctrl = make(name, env)
    t = 0
    deliv = on = late = 0
    onv = 0.0
    reroutes = stucks = 0
    done = False
    while not done and t < 500:
        _, _, term, trunc, info = env.step(ctrl.act())
        t += 1
        reroutes += int(info.get("clashes", 0))
        stucks += int(info.get("stucks", 0))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            sh = env.shelfs[sid - 1]
            deliv += 1
            if sh.deadline is not None and t <= sh.deadline:
                on += 1
                onv += task_value(sh)
            else:
                late += 1
        done = all(term) or all(trunc)
    return {"deliveries": deliv, "on_time": on, "late": late, "on_time_value": round(onv, 1),
            "reroutes": reroutes, "stucks": stucks,
            "disturb_reroutes": int(getattr(env, "_disturb_reroutes", 0))}


def dump(rows):
    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# 100-seed disturbance comparison (rate {DIST_RATE}), {len(rows)} seeds done"])
        w.writerow(["seed"] + [f"{p}_{k}" for p in POLICIES for k in METRICS])
        for s, rec in rows:
            w.writerow([s] + [rec[p][k] for p in POLICIES for k in METRICS])
        w.writerow(["MEAN"] + [mean(p, k) for p in POLICIES for k in METRICS])


def main():
    os.makedirs("results", exist_ok=True)
    rows = []
    for s in SEEDS:
        rec = {p: run(s, p) for p in POLICIES}
        rows.append((s, rec))
        dump(rows)
        print(f"seed {s}: " + "  ".join(
            f"{p} otv={rec[p]['on_time_value']:.0f} rr={rec[p]['reroutes']}" for p in POLICIES),
            flush=True)

    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)
    print(f"\n--- MEAN over {len(SEEDS)} seeds (disturbances) ---")
    print(f"  {'policy':<16}" + "".join(f"{k:>13}" for k in METRICS))
    for p in POLICIES:
        print(f"  {p:<16}" + "".join(f"{mean(p, k):>13.1f}" for k in METRICS))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
