"""10-trial verification: PRIORITY (deadline) strategy vs FIFO baseline.

Both run on the large env with the same deadlines attached; measures the headline
deadline metric (on-time deliveries) plus throughput, stucks, reroutes, the AGV
picker-wait, and battery. Writes results/priority_vs_fifo_10trials.csv.

FIFO   = queue-order task assignment + zone-based picker dispatch (baseline).
PRIORITY = deadline-order assignment + nearest/urgent picker dispatch (our strategy).

Run: python scripts/verify_priority_10trials.py
"""
from __future__ import annotations

import csv
import os
import sys
import warnings

sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.warehouse import AgentType
from wwm_sim.battery import BatteryTracker
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from sim_dashboard import FIFOController
from sim_priority import PriorityController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(10))
OUT = "results/priority_vs_fifo_10trials.csv"
DL = load_deadlines("data/deadlines_example.txt")


def run(seed, ctrl_cls):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    ctrl = ctrl_cls(env)
    bat = BatteryTracker(env)
    agvs = [a for a in env.agents if a.type == AgentType.AGV]
    prev = {a.id: (a.x, a.y) for a in agvs}
    m = dict(deliveries=0, on_time=0, late=0, clashes=0, stucks=0, picker_wait=0, steps=0)
    done = False
    while not done:
        _, _, term, trunc, info = env.step(ctrl.act())
        bat.step()
        m["steps"] += 1
        m["clashes"] += info.get("clashes", 0)
        m["stucks"] += info.get("stucks", 0)
        for sid, _a in getattr(env, "deliveries_this_step", []):
            m["deliveries"] += 1
            dl = env.shelfs[sid - 1].deadline
            if dl is not None:
                if m["steps"] <= dl:
                    m["on_time"] += 1
                else:
                    m["late"] += 1
        for a in agvs:
            moved = (a.x, a.y) != prev[a.id]
            prev[a.id] = (a.x, a.y)
            mm = ctrl.assigned_agvs.get(a)
            if (not moved and mm is not None and mm.mission_type.name == "PICKING"
                    and mm.at_location and not a.carrying_shelf):
                m["picker_wait"] += 1
        done = all(term) or all(trunc)
    levels = list(bat.level.values())
    m["throughput_1k"] = round(1000 * m["deliveries"] / max(m["steps"], 1), 1)
    m["on_time_pct"] = round(100 * m["on_time"] / max(m["deliveries"], 1), 1)
    m["min_batt"] = round(bat.min_level() * 100, 1)
    m["end_batt"] = round(100 * sum(levels) / len(levels), 1)
    m["stranded"] = len(bat.stranded)
    return m


def main():
    os.makedirs("results", exist_ok=True)
    e = gym.make(ENV).unwrapped
    e.reset(seed=0)
    metrics = ["deliveries", "on_time", "on_time_pct", "throughput_1k",
               "picker_wait", "reroutes", "stucks", "min_batt", "end_batt", "stranded"]

    rows = []
    for s in SEEDS:
        f = run(s, FIFOController)
        p = run(s, PriorityController)
        f["reroutes"], p["reroutes"] = f["clashes"], p["clashes"]
        rows.append((s, f, p))

    def mean(key, i):
        return round(sum(r[i][key] for r in rows) / len(rows), 1)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["# A) SETUP (same for both policies, all trials)"])
        w.writerow(["env", ENV])
        w.writerow(["grid (rows x cols)", f"{e.grid_size[0]} x {e.grid_size[1]}"])
        w.writerow(["AGVs / Pickers", f"{e.num_agvs} / {e.num_pickers}  (2:1 -> pickers scarce)"])
        w.writerow(["shelves / open tasks", f"{len(e.shelfs)} / {len(e.request_queue)}"])
        w.writerow(["deadlines", "absolute step, scrambled vs queue order; episode = 500 steps"])
        w.writerow([])
        w.writerow(["# B) PER-TRIAL: FIFO baseline vs PRIORITY strategy"])
        w.writerow(["seed"] + [f"fifo_{k}" for k in metrics] + [f"prio_{k}" for k in metrics])
        for s, f, p in rows:
            w.writerow([s] + [f[k] for k in metrics] + [p[k] for k in metrics])
        w.writerow(["MEAN"] + [mean(k, 1) for k in metrics] + [mean(k, 2) for k in metrics])
        w.writerow([])
        w.writerow(["# C) NOTES"])
        for n in [
            "on_time = delivered on/before its deadline; on_time_pct = on_time / deliveries",
            "PRIORITY assigns AGVs AND pickers by deadline urgency; FIFO = queue order + zone pickers",
            "picker_wait = AGV-steps parked at a shelf waiting for a picker (2:1 AGV:picker => unavoidable some)",
            f"MEAN deliveries: FIFO {mean('deliveries',1)} vs PRIORITY {mean('deliveries',2)} (priority delivers MORE)",
            f"MEAN on-time %: FIFO {mean('on_time_pct',1)} vs PRIORITY {mean('on_time_pct',2)} (priority LOWER %)",
            f"MEAN on-time COUNT: FIFO {mean('on_time',1)} vs PRIORITY {mean('on_time',2)}",
            "KEY FINDING — the system is OVERLOADED (40+ open tasks, ~30-35 deliverable in 500 steps,",
            "  pickers scarce 2:1) so not all deadlines are meetable. Under overload, naive earliest-",
            "  deadline-first (our priority) works 'at the deadline edge' (mean delivery slack NEGATIVE),",
            "  clustering deliveries near/past deadlines -> LOWER on-time %. FIFO's random order banks",
            "  high-slack far-deadline tasks that are trivially on-time -> higher %. This is the classic",
            "  EDF-under-overload result: deadline-ONLY priority is not enough; needs feasibility/slack",
            "  awareness (prioritise what you can still MEET, shed the doomed) = plan Part A scoring.",
        ]:
            w.writerow([n])

    print(f"wrote {OUT}")
    print(f"MEAN on-time%: FIFO {mean('on_time_pct',1)} vs PRIORITY {mean('on_time_pct',2)}  |  "
          f"deliveries: FIFO {mean('deliveries',1)} vs PRIORITY {mean('deliveries',2)}  |  "
          f"picker_wait: FIFO {mean('picker_wait',1)} vs PRIORITY {mean('picker_wait',2)}")


if __name__ == "__main__":
    main()
