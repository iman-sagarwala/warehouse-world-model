"""Demo: the Stage-0 battery model running under the FIFO heuristic on wwm_sim.

Reuses wwm_sim's own (validated) FIFO heuristic and attaches a BatteryTracker by
wrapping env.step/reset — so the battery updates on every real step without
duplicating any control logic. Prints battery levels over time and any strandings.

Usage:
    python scripts/battery_demo.py --seed 0
    python scripts/battery_demo.py --steps-per-charge 200 --seed 3
"""
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # registers wwm_sim-* ids
from wwm_sim.heuristic import heuristic_episode
from wwm_sim.warehouse import AgentType
from wwm_sim.battery import BatteryConfig, BatteryTracker


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Battery model demo on wwm_sim (FIFO).",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--env", default="wwm_sim-tiny-3agvs-2pickers-globalobs-v1")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--steps-per-charge", type=float, default=300.0,
                   help="Driving-steps a full battery lasts (lower = battery binds sooner).")
    p.add_argument("--every", type=int, default=100, help="Print battery levels every N steps.")
    return p.parse_args()


def fmt_levels(bat: BatteryTracker) -> str:
    parts = []
    for a in bat.env.agents:
        tag = "AGV" if a.type == AgentType.AGV else "PCK"
        lvl = bat.level[a.id]
        mark = "!" if a.id in bat.stranded else ("*" if (a.x, a.y) in bat.chargers else " ")
        parts.append(f"{tag}{a.id}:{lvl*100:5.1f}%{mark}")
    return "  ".join(parts)


def main() -> None:
    args = parse_args()
    env = gym.make(args.env).unwrapped

    cfg = BatteryConfig(steps_per_charge=args.steps_per_charge)
    bat = BatteryTracker(env, cfg)

    # Attach the tracker by wrapping reset/step (heuristic_episode calls both).
    orig_reset, orig_step = env.reset, env.step

    def reset_wrap(*a, **k):
        out = orig_reset(*a, **k)
        bat.reset()
        return out

    def step_wrap(actions):
        out = orig_step(actions)
        bat.step()
        if bat.t % args.every == 0:
            print(f"  step {bat.t:4d} | {fmt_levels(bat)}")
        return out

    env.reset, env.step = reset_wrap, step_wrap

    print(f"env: {args.env} | seed {args.seed}")
    print("battery grounding: Robotnik RB-VOGUI (AGV) + RB-KAIROS+ (Picker), compressed")
    print(f"  steps_per_charge={cfg.steps_per_charge:.0f}  drive_drain={cfg.drive_drain*100:.3f}%/step  "
          f"carry=+{cfg.carrying_penalty*100:.0f}%  pick={cfg.pick_cost*100:.3f}%  "
          f"idle={cfg.idle_drain*100:.3f}%/step  charge=+{cfg.charge_gain*100:.2f}%/step  floor={cfg.floor*100:.0f}%")
    print(f"  chargers (provisional = delivery docks): {sorted(bat.chargers)}")
    print("  legend: * = on charger, ! = stranded (<= floor away from charger)")
    print("-" * 78)

    heuristic_episode(env, False, args.seed)

    print("-" * 78)
    agv, pick = bat.levels_by_type()
    print(f"end levels  | AGVs: {[f'{x*100:.0f}%' for x in agv]}  Pickers: {[f'{x*100:.0f}%' for x in pick]}")
    print(f"min battery reached: {bat.min_level()*100:.1f}%")
    print(f"picks charged to pickers: {bat.picks_charged}")
    print(f"stranded robots (hit floor away from charger): {len(bat.stranded)} -> ids {sorted(bat.stranded)}")


if __name__ == "__main__":
    main()
