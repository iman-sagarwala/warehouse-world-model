"""Bakeoff under the REALISTIC DEMAND STREAM (wwm_sim/demand.py).

Policies:
  rush        - RushValueController (value-greedy baseline, no routing/congestion)
  parta       - PartAController (full funnel, NO congestion forecast)
  parta_cong  - PartACongestionController (congestion forecast steers routes)

The demand stream is seeded per-seed and its arrival TIMES / VALUES / DEADLINES are policy-independent
(the rng call sequence is identical), so this is a paired comparison. Orders are scored PER ORDER --
one shelf trip may fulfil several orders, each with its own deadline and value.

Run:  python scripts/bakeoff_demand.py          (SEEDS=30 env var to change)
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
from sim_priority import PartAController, RushValueController
from congestion_policies import PartACongestionController, PartACongestionFreeL2Controller

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
N_SEEDS = int(os.environ.get("SEEDS", "30"))
SEEDS = list(range(N_SEEDS))
STEPS = 500
OUT = "results/bakeoff_demand.csv"
POLICIES = ["rush", "parta", "parta_cong", "parta_freel2"]
METRICS = ["deliveries", "on_time", "late", "on_time_value", "arrivals", "q_mean"]

BUILD = {
    "rush": RushValueController,
    "parta": PartAController,
    "parta_cong": PartACongestionController,
    "parta_freel2": PartACongestionFreeL2Controller,   # layer 2 anchored at the FREE-UP dock
}


def run(seed, name):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_initial(env, n=12)
    ctrl = BUILD[name](env)

    deliv = on = late = 0
    onv = 0.0
    qs = []
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _info = env.step(ctrl.act())
        t += 1
        qs.append(len(env.request_queue))
        # score PER ORDER: one shelf trip may fulfil several orders, each with its own deadline/value
        for o in getattr(env, "fulfilled_this_step", []):
            deliv += 1
            if o.deadline is not None and t <= o.deadline:
                on += 1
                onv += o.value
            else:
                late += 1
        done = all(term) or all(trunc)
    return {"deliveries": deliv, "on_time": on, "late": late, "on_time_value": round(onv, 1),
            "arrivals": env.demand_model.arrivals,
            "q_mean": round(float(np.mean(qs)), 1)}


def dump(rows):
    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)
    os.makedirs("results", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# demand-stream bakeoff, {len(rows)} seeds"])
        w.writerow(["seed"] + [f"{p}_{k}" for p in POLICIES for k in METRICS])
        for s, rec in rows:
            w.writerow([s] + [rec[p][k] for p in POLICIES for k in METRICS])
        w.writerow(["MEAN"] + [mean(p, k) for p in POLICIES for k in METRICS])


def main():
    rows = []
    for s in SEEDS:
        rec = {p: run(s, p) for p in POLICIES}
        rows.append((s, rec))
        dump(rows)
        print(f"seed {s}: " + "  ".join(
            f"{p} otv={rec[p]['on_time_value']:.0f}" for p in POLICIES), flush=True)

    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)
    print(f"\n--- MEAN over {len(rows)} seeds (demand stream) ---")
    print(f"  {'policy':<14}" + "".join(f"{k:>15}" for k in METRICS))
    for p in POLICIES:
        print(f"  {p:<14}" + "".join(f"{mean(p, k):>15}" for k in METRICS))


if __name__ == "__main__":
    main()
