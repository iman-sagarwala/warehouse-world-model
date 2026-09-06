"""30-seed check: congestion for the DEADLINE ONLY vs congestion for ROUTING vs neither.
Smoke test showed the deadline-only variant is STORM-PROOF via TASK-level avoidance (won't commit
to tasks whose routes are jammed) -- with NO route steering. Confirms: EITHER congestion mechanism
alone prevents storms; combining them is the double-count redundancy.

  plain_parta       - Part A, NO congestion anywhere (baseline; identical to dl_cong minus the term)
  dl_cong           - congestion -> DEADLINE only (shortest routes, no score term)  <- the new idea
  parta_congestion  - congestion -> ROUTING only (the current champion)
  parta_head        - reference

No disturbances (clean isolation). Run: python scripts/verify_dl_cong.py   (SEEDS env, default 30)
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
from sim_priority import PartAController
from congestion_policies import (PartABaselineHeadController, PartACongestionController,
                                  PartADeadlineCongController)

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
N_SEEDS = int(os.environ.get("SEEDS", "30"))
SEEDS = list(range(N_SEEDS))
OUT = "results/dl_cong_bakeoff.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")

FACTORY = {
    "plain_parta": PartAController,
    "dl_cong": PartADeadlineCongController,
    "parta_congestion": PartACongestionController,
    "parta_head": PartABaselineHeadController,
}
POLICIES = ["plain_parta", "dl_cong", "parta_congestion", "parta_head"]
METRICS = ["deliveries", "on_time", "late", "on_time_value", "reroutes", "stucks"]


def run(seed, name):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    ctrl = FACTORY[name](env)
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
            "reroutes": reroutes, "stucks": stucks}


def dump(rows):
    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# congestion-for-deadline-only vs routing vs neither, {len(rows)} seeds"])
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
    print(f"\n--- MEAN over {len(SEEDS)} seeds (no disturbances) ---")
    print(f"  {'policy':<18}" + "".join(f"{k:>13}" for k in METRICS))
    for p in POLICIES:
        print(f"  {p:<18}" + "".join(f"{mean(p, k):>13.1f}" for k in METRICS))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
