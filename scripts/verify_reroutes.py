"""Compare policies on REROUTES (congestion churn), not just on-time value.

The env counts a "clash" (info["clashes"]) whenever an agent's next cell is blocked by another
agent that isn't clearing out -> it stops, starts a fix timer, and calls find_path to route
AROUND the obstacle (warehouse.py:474-479; the code itself labels clash_pairs "for each reroute
this step"). So SUM of clashes over an episode = total congestion-induced reroute events. A policy
that packs robots into conflict generates more; one that spreads them out generates fewer.

Reports per policy (mean over seeds): deliveries, on_time, on_time_value, late, reroutes (total
clashes), and reroutes-per-delivery (normalized churn = how much fighting per useful task).
Run: python scripts/verify_reroutes.py     (seeds via SEEDS env, default 20)
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
from sim_dashboard import FIFOController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
N_SEEDS = int(os.environ.get("SEEDS", "20"))
SEEDS = list(range(N_SEEDS))
OUT = "results/reroutes_bakeoff.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def build(name):
    if name == "fifo":
        return lambda env: FIFOController(env)
    if name == "rush":
        return lambda env: RushValueController(env)
    if name == "parta":
        return lambda env: PartAController(env)
    if name == "parta_window":
        def mk(env):
            c = PartAController(env)
            c.USE_GLOBAL_WINDOW = True
            return c
        return mk
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
    reroutes = 0
    done = False
    while not done and t < 500:
        _, _, term, trunc, info = env.step(ctrl.act())
        t += 1
        reroutes += int(info.get("clashes", 0))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            sh = env.shelfs[sid - 1]
            deliv += 1
            if sh.deadline is not None and t <= sh.deadline:
                on += 1
                onv += task_value(sh)
            else:
                late += 1
        done = all(term) or all(trunc)
    rpd = reroutes / deliv if deliv else 0.0
    return {"deliveries": deliv, "on_time": on, "late": late, "on_time_value": round(onv, 1),
            "reroutes": reroutes, "reroutes_per_deliv": round(rpd, 2)}


POLICIES = ["fifo", "rush", "parta", "parta_window"]
METRICS = ["deliveries", "on_time", "late", "on_time_value", "reroutes", "reroutes_per_deliv"]


def main():
    os.makedirs("results", exist_ok=True)
    factories = {p: build(p) for p in POLICIES}
    rows = []
    for s in SEEDS:
        rec = {p: run(s, factories[p]) for p in POLICIES}
        rows.append((s, rec))
        print(f"seed {s}: " + "  ".join(
            f"{p} rr={rec[p]['reroutes']} otv={rec[p]['on_time_value']:.0f}" for p in POLICIES),
            flush=True)

    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# reroutes bake-off, {len(SEEDS)} seeds, 500-cap"])
        w.writerow(["policy"] + METRICS)
        for p in POLICIES:
            w.writerow([p] + [mean(p, k) for k in METRICS])

    print(f"\n--- MEAN over {len(SEEDS)} seeds ---")
    print(f"  {'policy':<14}" + "".join(f"{k:>13}" for k in METRICS))
    for p in POLICIES:
        print(f"  {p:<14}" + "".join(f"{mean(p, k):>13.1f}" for k in METRICS))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
