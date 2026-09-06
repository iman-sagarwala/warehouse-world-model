"""Route ADHERENCE: make the env keep to Part A's CHOSEN route -- reroute around blockers, but
hug the committed route and rejoin it -- instead of recomputing an independent A* that discards it.

Mechanism (env.prefer_committed=True): Part A attaches its chosen route to the AGV
(agv.committed_cells); find_path then charges OFF-route free cells more than ON-route ones, so
every path (initial AND reroute) prefers the committed route and only detours around a real
blocker. It still reroutes -- it just keeps to my route. All pick/deliver logic untouched.

Policies (10 seeds, 500-cap, same deadlines+values):
  rush         - scalar baseline, env recomputes freely
  parta        - Part A funnel, env recomputes freely (route choice discarded on execution) [control]
  parta_route  - Part A funnel, env.prefer_committed=True (drive + adhere to the chosen route)

Metrics: deliveries, on_time, late, on_time_value, reroutes (env clashes), reroutes_per_deliv, stucks.
Run: python scripts/verify_route_adherence.py     (seeds via SEEDS env, default 10)
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
N_SEEDS = int(os.environ.get("SEEDS", "10"))
SEEDS = list(range(N_SEEDS))
OUT = "results/route_adherence_bakeoff.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def make_ctrl(name, env):
    if name == "rush":
        return RushValueController(env)
    if name in ("parta", "parta_route"):
        if name == "parta_route":
            env.prefer_committed = True     # find_path hugs Part A's committed route
        return PartAController(env)
    raise ValueError(name)


def run(seed, name):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    ctrl = make_ctrl(name, env)
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


POLICIES = ["rush", "parta", "parta_route"]
METRICS = ["deliveries", "on_time", "late", "on_time_value",
           "reroutes", "reroutes_per_deliv", "stucks"]


def main():
    os.makedirs("results", exist_ok=True)
    rows = []
    for s in SEEDS:
        rec = {p: run(s, p) for p in POLICIES}
        rows.append((s, rec))
        print(f"seed {s}: " + "  ".join(
            f"{p} otv={rec[p]['on_time_value']:.0f} rr={rec[p]['reroutes']}" for p in POLICIES),
            flush=True)

    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# route adherence (prefer_committed), {len(SEEDS)} seeds, 500-cap"])
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
