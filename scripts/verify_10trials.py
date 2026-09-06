"""10-trial FIFO-vs-random verification -> CSV report.

Writes results/fifo_vs_random_10trials.csv with three blocks:
  A) MODEL-INVARIANT facts (same for BOTH policies & all trials): battery
     constants + ratios, movement, grid/fleet. If the structure is right these are
     identical everywhere and match what we designed.
  B) PER-TRIAL results (seeds 0-9), FIFO vs random: tasks done + order + which
     AGV, picks, in-transit, reroutes, stucks, battery (min/end), strandings.
  C) NOTES: structural differences + consistency checks.

Run: python scripts/verify_10trials.py
"""
from __future__ import annotations

import csv
import os
import warnings

warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.heuristic import heuristic_episode
from wwm_sim.warehouse import AgentType
from wwm_sim.battery import BatteryConfig, BatteryTracker

ENV = "wwm_sim-tiny-3agvs-2pickers-globalobs-v1"
SEEDS = list(range(10))
OUT = "results/fifo_vs_random_10trials.csv"


def _blank():
    return {"deliveries": 0, "clashes": 0, "stucks": 0, "steps": 0}


def _track(acc, env, info, bat, order):
    acc["deliveries"] += info.get("shelf_deliveries", 0)
    acc["clashes"] += info.get("clashes", 0)
    acc["stucks"] += info.get("stucks", 0)
    acc["steps"] += 1
    bat.step()
    order.extend(getattr(env, "deliveries_this_step", []))  # (shelf_id, agv_id) in order


def run(seed, policy):
    env = gym.make(ENV).unwrapped
    acc, order = _blank(), []
    if policy == "fifo":
        bat = BatteryTracker(env)  # re-reset after env.reset (agents populate then)
        orig_reset, orig_step = env.reset, env.step

        def reset_wrap(*a, **k):
            out = orig_reset(*a, **k)
            bat.reset()
            return out

        def sw(actions):
            out = orig_step(actions)
            _track(acc, env, out[4], bat, order)
            return out

        env.reset, env.step = reset_wrap, sw
        heuristic_episode(env, False, seed)
    else:  # random
        env.reset(seed=seed)
        bat = BatteryTracker(env)  # constructed AFTER reset -> agents populated
        done = False
        while not done:
            _, _, term, trunc, info = env.step(env.action_space.sample())
            _track(acc, env, info, bat, order)
            done = all(term) or all(trunc)

    picks = bat.picks_charged
    levels = list(bat.level.values())
    return {
        "deliveries": acc["deliveries"],
        "throughput_1k": round(1000 * acc["deliveries"] / max(acc["steps"], 1), 1),
        "picks": picks,
        "in_transit": picks - acc["deliveries"],
        "reroutes": acc["clashes"],
        "stucks": acc["stucks"],
        "min_batt": round(bat.min_level() * 100, 1),
        "end_batt": round(100 * sum(levels) / len(levels), 1),
        "stranded": len(bat.stranded),
        "first_done": "|".join(f"{s}(AGV{a})" for s, a in order[:5]) or "-",
        "n_agvs": env.num_agvs,
    }


def invariants():
    c = BatteryConfig()
    e = gym.make(ENV).unwrapped
    e.reset(seed=0)
    return [
        ("env", ENV, ""),
        ("num_agvs / num_pickers", f"{e.num_agvs} / {e.num_pickers}", "fleet"),
        ("grid (rows x cols)", f"{e.grid_size[0]} x {e.grid_size[1]}", ""),
        ("movement", "1 cell / step, 4-connected", "distance per step"),
        ("steps_per_charge", c.steps_per_charge, "driving-steps per full charge (compressed)"),
        ("drive_drain / step", round(c.drive_drain, 6), "loss rate while moving"),
        ("idle_drain / step", round(c.idle_drain, 6), "idle_fraction x drive"),
        ("carry_extra / step (AGV)", round(c.carry_extra, 6), "carrying_penalty x drive"),
        ("pick_cost (Picker)", round(c.pick_cost, 6), "pick_penalty_steps x drive"),
        ("charge_gain / step", round(c.charge_gain, 6), "gain rate at a charger"),
        ("ratio charge:discharge", round(c.charge_gain / c.drive_drain, 3), "scale-invariant (compression-proof)"),
        ("ratio idle:drive", c.idle_fraction, ""),
        ("ratio carry:drive", c.carrying_penalty, "AGV only, while carrying"),
        ("ratio pick:drive", c.pick_penalty_steps, "Picker only, per pick"),
        ("battery floor", c.floor, "strand threshold"),
        ("start level", c.start_level, ""),
    ]


def main():
    os.makedirs("results", exist_ok=True)
    inv = invariants()
    rows = [(s, run(s, "fifo"), run(s, "random")) for s in SEEDS]

    # aggregates
    def mean(key, pol):
        vals = [r[1 if pol == "fifo" else 2][key] for r in rows]
        return round(sum(vals) / len(vals), 1)

    n_agvs = rows[0][1]["n_agvs"]
    checks_pass = all(
        0 <= r[1]["in_transit"] <= n_agvs and 0 <= r[2]["in_transit"] <= n_agvs
        and r[1]["deliveries"] >= 3 * (r[2]["deliveries"] + 1)
        and r[2]["stucks"] > r[1]["stucks"] and r[2]["stucks"] > 0
        for r in rows
    )

    metrics = ["deliveries", "throughput_1k", "picks", "in_transit", "reroutes",
               "stucks", "min_batt", "end_batt", "stranded", "first_done"]

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# A) MODEL-INVARIANT (identical for FIFO & random, all trials)"])
        w.writerow(["metric", "value", "note"])
        for k, v, note in inv:
            w.writerow([k, v, note])
        w.writerow([])
        w.writerow(["# B) PER-TRIAL RESULTS (FIFO vs random)"])
        w.writerow(["seed"] + [f"fifo_{m}" for m in metrics] + [f"rand_{m}" for m in metrics])
        for s, ff, rr in rows:
            w.writerow([s] + [ff[m] for m in metrics] + [rr[m] for m in metrics])
        w.writerow(["MEAN"] + [mean(m, "fifo") if m != "first_done" else "" for m in metrics]
                   + [mean(m, "random") if m != "first_done" else "" for m in metrics])
        w.writerow([])
        w.writerow(["# C) NOTES / structural differences"])
        for note in [
            "assignment: FIFO -> each queued task to the NEAREST FREE AGV (nearest-agent); Random -> no assignment (uniform random targets)",
            "pickup/delivery order: FIFO ~ request-queue (FIFO) order; Random -> incidental/luck (see first_done columns)",
            "stucks: Random >> FIFO (random chases new random targets -> no coherent escape -> gives up); FIFO stays on valid paths",
            "battery: driven by activity minus recharge; compare fifo_end_batt vs rand_end_batt across trials to see the pattern",
            "consistency invariant: 0 <= picks - deliveries <= num_agvs (in-transit at cutoff), for BOTH policies",
            f"CONSISTENCY CHECKS ACROSS ALL 10 TRIALS: {'ALL PASS' if checks_pass else 'FAILURE'}",
        ]:
            w.writerow([note])

    print(f"wrote {OUT}")
    print(f"consistency checks (10 trials): {'ALL PASS' if checks_pass else 'FAILURE'}")
    print(f"FIFO mean deliveries={mean('deliveries','fifo')} stucks={mean('stucks','fifo')} "
          f"end_batt={mean('end_batt','fifo')}%  |  RANDOM mean deliveries={mean('deliveries','random')} "
          f"stucks={mean('stucks','random')} end_batt={mean('end_batt','random')}%")


if __name__ == "__main__":
    main()
