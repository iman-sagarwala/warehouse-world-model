"""First increment of ROUTE-DRIVEN execution: does driving the committed route (waiting on a
conflict instead of rerouting off it) change Part A's congestion + on-time value vs RUSH?

Part A already ranks task -> ranks route -> commits the SHORTEST route. In the default env that
route is discarded the moment two agents clash (env reroutes via find_path). Here we flip one env
switch, `wait_not_reroute`: on a clash the agent HOLDS its committed route and WAITS for the
blocker to clear (the ADG delay->wait philosophy). All pick/deliver/picker logic is untouched.

Policies (10 seeds, 500-cap, same deadlines+values):
  rush        - scalar baseline, normal env (reroute on clash)
  parta       - Part A funnel, normal env (reroute on clash)      [control]
  parta_adg   - Part A funnel, env.wait_not_reroute=True (drive committed route, wait on clash)

Metrics: deliveries, on_time, late, on_time_value, conflicts (env clashes -> reroutes in normal
mode, WAITS in adg mode), conflicts_per_deliv, and stucks (deadlock proxy: wait-not-reroute can
gridlock -> the env's stuck-recovery restarts them, counted here).
Run: python scripts/verify_adg_exec.py     (seeds via SEEDS env, default 10)
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
OUT = "results/adg_exec_bakeoff.csv"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def make_ctrl(name, env):
    if name == "rush":
        return RushValueController(env)
    if name in ("parta", "parta_adg"):
        c = PartAController(env)
        if name == "parta_adg":
            env.wait_not_reroute = True     # drive committed route, WAIT on clash (no reroute)
        return c
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
    conflicts = stucks = 0
    done = False
    while not done and t < 500:
        _, _, term, trunc, info = env.step(ctrl.act())
        t += 1
        conflicts += int(info.get("clashes", 0))
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
    cpd = conflicts / deliv if deliv else 0.0
    return {"deliveries": deliv, "on_time": on, "late": late, "on_time_value": round(onv, 1),
            "conflicts": conflicts, "conflicts_per_deliv": round(cpd, 2), "stucks": stucks}


POLICIES = ["rush", "parta", "parta_adg"]
METRICS = ["deliveries", "on_time", "late", "on_time_value",
           "conflicts", "conflicts_per_deliv", "stucks"]


def main():
    os.makedirs("results", exist_ok=True)
    rows = []
    for s in SEEDS:
        rec = {p: run(s, p) for p in POLICIES}
        rows.append((s, rec))
        print(f"seed {s}: " + "  ".join(
            f"{p} otv={rec[p]['on_time_value']:.0f} cf={rec[p]['conflicts']} st={rec[p]['stucks']}"
            for p in POLICIES), flush=True)

    def mean(p, k):
        return round(sum(r[1][p][k] for r in rows) / len(rows), 1)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([f"# route-driven (wait-not-reroute) execution, {len(SEEDS)} seeds, 500-cap"])
        w.writerow(["policy"] + METRICS)
        for p in POLICIES:
            w.writerow([p] + [mean(p, k) for k in METRICS])

    print(f"\n--- MEAN over {len(SEEDS)} seeds ---")
    print(f"  {'policy':<12}" + "".join(f"{k:>13}" for k in METRICS))
    for p in POLICIES:
        print(f"  {p:<12}" + "".join(f"{mean(p, k):>13.1f}" for k in METRICS))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
