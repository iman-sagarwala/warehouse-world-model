"""30-seed bake-off: does a congestion FORECAST (predict where robots go next, route to dodge it)
beat the baselines? Every policy runs the SAME 30 worlds (paired: seed N = identical setup for all).

  fifo             - raw first-come (naive floor)
  rush             - scalar: global window -> value -> nearest robot
  rush_yen         - rush selection + Yen route driven via adherence (Piece B)
  parta            - Part A funnel (per-task finish), env recomputes freely
  parta_congestion - Part A + forecast-aware route selection & reroute + adherence (Pieces A + C)

Metrics: deliveries, on_time, late, on_time_value, reroutes (env clashes), reroutes_per_deliv, stucks.
Run: python scripts/verify_congestion.py     (seeds via SEEDS env, default 30)
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
from congestion_policies import RushYenController, PartACongestionController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
N_SEEDS = int(os.environ.get("SEEDS", "30"))
SEEDS = list(range(N_SEEDS))
OUT = "results/congestion_bakeoff.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")

FACTORY = {
    "fifo": FIFOController,
    "rush": RushValueController,
    "rush_yen": RushYenController,
    "parta": PartAController,
    "parta_congestion": PartACongestionController,
}
POLICIES = ["fifo", "rush", "rush_yen", "parta", "parta_congestion"]
METRICS = ["deliveries", "on_time", "late", "on_time_value",
           "reroutes", "reroutes_per_deliv", "stucks"]


def run(seed, name):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)                 # seed N -> identical world for every policy (paired)
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
    rpd = reroutes / deliv if deliv else 0.0
    return {"deliveries": deliv, "on_time": on, "late": late, "on_time_value": round(onv, 1),
            "reroutes": reroutes, "reroutes_per_deliv": round(rpd, 2), "stucks": stucks}


def main():
    os.makedirs("results", exist_ok=True)
    rows = []
    for s in SEEDS:
        rec = {p: run(s, p) for p in POLICIES}
        rows.append((s, rec))
        print(f"seed {s}: " + "  ".join(
            f"{p} otv={rec[p]['on_time_value']:.0f} rr={rec[p]['reroutes']}" for p in POLICIES),
            flush=True)
        with open(OUT + ".progress", "w") as f:
            f.write(f"done seed {s}\n")

    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# congestion-forecast bake-off, {len(SEEDS)} seeds (paired), 500-cap"])
        w.writerow(["seed"] + [f"{p}_{k}" for p in POLICIES for k in METRICS])
        for s, rec in rows:
            w.writerow([s] + [rec[p][k] for p in POLICIES for k in METRICS])
        w.writerow(["MEAN"] + [mean(p, k) for p in POLICIES for k in METRICS])

    print(f"\n--- MEAN over {len(SEEDS)} seeds ---")
    print(f"  {'policy':<18}" + "".join(f"{k:>13}" for k in METRICS))
    for p in POLICIES:
        print(f"  {p:<18}" + "".join(f"{mean(p, k):>13.1f}" for k in METRICS))
    if os.path.exists(OUT + ".progress"):
        os.remove(OUT + ".progress")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
