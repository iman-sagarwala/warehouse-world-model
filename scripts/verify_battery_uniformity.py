"""Prove battery constants/ratios are UNIFORM across simulation policies.

Runs a FIFO episode and a random episode, each with its own independently-created
BatteryTracker, then reads the battery config actually used in each and compares
attribute-by-attribute. Writes results/battery_uniformity.csv.

The point: nothing about the policy (FIFO vs random) changes the battery physics —
the constants and ratios are identical. (Per-type differences AGV vs Picker are
role-conditional, not policy-dependent; noted at the bottom.)

Run: python scripts/verify_battery_uniformity.py
"""
from __future__ import annotations

import csv
import os
import warnings

warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.heuristic import heuristic_episode
from wwm_sim.battery import BatteryTracker

ENV = "wwm_sim-tiny-3agvs-2pickers-globalobs-v1"
OUT = "results/battery_uniformity.csv"


def snapshot(cfg) -> dict:
    return {
        "steps_per_charge": cfg.steps_per_charge,
        "drive_drain_per_step": round(cfg.drive_drain, 6),
        "idle_drain_per_step": round(cfg.idle_drain, 6),
        "carry_extra_per_step": round(cfg.carry_extra, 6),
        "pick_cost": round(cfg.pick_cost, 6),
        "charge_steps": cfg.charge_steps,
        "charge_gain_per_step": round(cfg.charge_gain, 6),
        "ratio_charge_to_discharge": round(cfg.charge_gain / cfg.drive_drain, 3),
        "ratio_idle_to_drive": cfg.idle_fraction,
        "ratio_carry_to_drive": cfg.carrying_penalty,
        "ratio_pick_to_drive": cfg.pick_penalty_steps,
        "floor": cfg.floor,
        "start_level": cfg.start_level,
    }


def run_fifo(seed=0):
    env = gym.make(ENV).unwrapped
    bat = BatteryTracker(env)
    orig_reset, orig_step = env.reset, env.step

    def reset_wrap(*a, **k):
        out = orig_reset(*a, **k)
        bat.reset()
        return out

    def sw(actions):
        out = orig_step(actions)
        bat.step()
        return out

    env.reset, env.step = reset_wrap, sw
    heuristic_episode(env, False, seed)
    return bat


def run_random(seed=0):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    bat = BatteryTracker(env)
    done = False
    while not done:
        _, _, term, trunc, _ = env.step(env.action_space.sample())
        bat.step()
        done = all(term) or all(trunc)
    return bat


def main():
    os.makedirs("results", exist_ok=True)
    fifo_bat = run_fifo()
    rand_bat = run_random()
    f, r = snapshot(fifo_bat.cfg), snapshot(rand_bat.cfg)

    all_uniform = True
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["# Battery constants/ratios — uniformity across simulation policies"])
        w.writerow(["# both columns read from independently-created BatteryTrackers in each policy's run"])
        w.writerow(["attribute", "FIFO", "Random", "uniform?"])
        for k in f:
            same = f[k] == r[k]
            all_uniform = all_uniform and same
            w.writerow([k, f[k], r[k], "YES" if same else "NO <-- DIFFERS"])
        w.writerow([])
        w.writerow(["# Per-type application (role-conditional, NOT policy-dependent)"])
        w.writerow(["carrying penalty", "applied to AGVs while carrying a shelf; 0 for Pickers"])
        w.writerow(["pick penalty", "applied to Pickers per pick; 0 for AGVs"])
        w.writerow(["capacity (steps_per_charge)", "SAME for both types (simplification; real RB-VOGUI 720Wh vs RB-KAIROS+ 2.78kWh not modelled)"])
        w.writerow([])
        w.writerow([f"VERDICT: all battery constants/ratios uniform across policies = {'YES' if all_uniform else 'NO'}"])

    print(f"wrote {OUT}")
    print(f"all battery constants/ratios uniform across FIFO vs random: {'YES' if all_uniform else 'NO'}")


if __name__ == "__main__":
    main()
