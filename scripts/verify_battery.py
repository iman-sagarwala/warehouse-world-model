"""Battery model verification: charge decision + gating keep strandings at zero.

Compresses the battery (steps_per_charge) so it BINDS within a 500-step episode, then
compares:
  * RUSH with a battery tracker OBSERVING only (no charge rule)  -> robots drain + strand.
  * BatteryAwareController (charge decision + movement gate)     -> strandings = 0.
Also reports the minimum battery per robot type (both must stay >= floor) to confirm BOTH
AGVs and Pickers recharge at the dedicated chargers.

At mild-but-binding compression (spc~400) the Stage-0 charge rule alone achieves
strandings=0. Under harsher compression a residual remains until the Part A battery
FILTER (don't start a task you can't finish above the floor) + Part B EMERGENCY tier
land — that is where the plan's "strandings=0 by construction" guarantee completes.

Run: python scripts/verify_battery.py
"""
from __future__ import annotations

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
from wwm_sim.values import load_values, attach_values
from wwm_sim.battery import BatteryConfig, BatteryTracker
from sim_priority import BatteryAwareController, RushValueController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(5))
SPC = 400.0          # compressed steps-per-charge (battery binds within 500 steps)
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def _make(seed):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    return env


def run_aware(seed):
    env = _make(seed)
    ctrl = BatteryAwareController(env, BatteryConfig(steps_per_charge=SPC))
    t = 0
    done = False
    deliv = 0
    while not done and t < 500:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        deliv += len(getattr(env, "deliveries_this_step", []))
        done = all(term) or all(trunc)
    agv, pk = ctrl.battery.levels_by_type()
    return {"strand": len(ctrl.battery.stranded), "min_agv": round(min(agv), 2),
            "min_pick": round(min(pk), 2), "deliv": deliv}


def run_rush_observed(seed):
    env = _make(seed)
    ctrl = RushValueController(env)
    bat = BatteryTracker(env, BatteryConfig(steps_per_charge=SPC))
    t = 0
    done = False
    while not done and t < 500:
        _, _, term, trunc, _ = env.step(ctrl.act())
        bat.step()
        t += 1
        done = all(term) or all(trunc)
    return {"strand": len(bat.stranded)}


def main():
    aware = [run_aware(s) for s in SEEDS]
    rush = [run_rush_observed(s) for s in SEEDS]
    n = len(SEEDS)
    a_strand = sum(r["strand"] for r in aware) / n
    r_strand = sum(r["strand"] for r in rush) / n
    min_agv = min(r["min_agv"] for r in aware)
    min_pick = min(r["min_pick"] for r in aware)
    deliv = sum(r["deliv"] for r in aware) / n
    print(f"steps_per_charge = {SPC} (battery binds), {n} seeds, floor = 0.10")
    print(f"  RUSH, no charge rule (observed):  strandings = {r_strand:.1f} / 12")
    print(f"  BatteryAware (charge + gate):      strandings = {a_strand:.1f} / 12")
    print(f"  BatteryAware min battery: AGV {min_agv}, Picker {min_pick} (both must be >= floor)")
    print(f"  BatteryAware deliveries: {deliv:.0f}")
    ok = a_strand == 0 and min_agv >= 0.10 and min_pick >= 0.10
    print(f"  RESULT: {'PASS - charge rule holds strandings at 0, both types recharge' if ok else 'residual strandings (needs Part A filter + Part B emergency tier)'}")


if __name__ == "__main__":
    main()
