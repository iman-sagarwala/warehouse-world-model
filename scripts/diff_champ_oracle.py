"""DIFF the champion's day against the hindsight-best explorer schedule, order by order.

The day-list oracle proved best-of-120 random schedules beat the champion by ~+5.6% on FIXED worlds.
This reproduces the exact winning rollout per seed (deterministic policy RNG) and itemises WHERE the
value difference comes from:
  RESCUED   - orders the best schedule banked on time that the champion delivered LATE
  CAPTURED  - orders the best schedule banked that the champion NEVER delivered
  LOST      - the reverse (champion banked, best schedule missed) -- the price paid
  TIMING    - shared on-time orders delivered earlier/later (no value change, shows the slack)
Run:  python scripts/diff_champ_oracle.py
"""
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import PartACongestionController, PartACongestionExploreController, _Sq5

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = [int(x) for x in os.environ.get("SEEDS_LIST", "0,1,2,3,4").split(",")]
DETAIL = int(os.environ.get("DETAIL", "3"))          # seed to print the full pick-list for
BASE = _Sq5 if os.environ.get("BASELINE", "") == "sq5" else PartACongestionController


def episode(seed, factory):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = factory(env)
    deliv = {}                                        # (shelf_id, t_arrive) -> dict
    onv = 0.0
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            key = (o.shelf.id, o.t_arrive)
            on = o.deadline is not None and t <= o.deadline
            deliv[key] = {"t": t, "v": o.value, "dl": o.deadline, "on": on}
            if on:
                onv += o.value
        done = all(term) or all(trunc)
    return onv, deliv


def best_rollout_params(seed):
    """Parse the oracle log for the winning rollout index; reproduce its exact config."""
    path = f"results/oa_dl_seed{seed}.out"
    m_best = None
    for line in open(path):
        mm = re.match(rf"seed {seed} rollout\s+(\d+): new best", line)
        if mm:
            m_best = int(mm.group(1))
    assert m_best is not None, f"no best rollout found in {path}"
    k = [2, 2, 3, 3, 4][m_best % 5]
    return m_best, k, (m_best % 2 == 1)


def main():
    print(f"{'seed':>5}{'champ':>8}{'best':>8}{'gap':>7} | {'rescued':>14}{'captured':>14}{'lost':>13}")
    details = None
    for s in SEEDS:
        c_onv, c = episode(s, BASE)
        m, k, sh = best_rollout_params(s)
        b_onv, b = episode(s, lambda e: PartACongestionExploreController(
            e, rng_seed=1000 * s + m, top_k=k, shuffle_order=sh))
        rescued = [(key, b[key], c[key]) for key in b if b[key]["on"] and key in c and not c[key]["on"]]
        captured = [(key, b[key]) for key in b if b[key]["on"] and key not in c]
        lost = [(key, c[key]) for key in c if c[key]["on"] and not (key in b and b[key]["on"])]
        rv = sum(r[1]["v"] for r in rescued)
        cv = sum(r[1]["v"] for r in captured)
        lv = sum(r[1]["v"] for r in lost)
        print(f"{s:>5}{c_onv:8.1f}{b_onv:8.1f}{b_onv-c_onv:+7.1f} | "
              f"{len(rescued):>3} = {rv:+8.1f}{len(captured):>4} = {cv:+8.1f}{len(lost):>4} = {lv:-8.1f}")
        if s == DETAIL:
            details = (s, c, b, rescued, captured, lost)

    if details:
        s, c, b, rescued, captured, lost = details
        print(f"\n===== SEED {s} PICK-LIST (every point of difference) =====")
        print("RESCUED (best banked on time; champion was LATE):")
        for (key, bb, cc) in sorted(rescued, key=lambda r: -r[1]["v"]):
            print(f"  shelf {key[0]:>3} arr t={key[1]:<3} v={bb['v']:5.1f} dl={bb['dl']:<4} | "
                  f"champ delivered t={cc['t']} ({cc['t']-cc['dl']:+d} late) | best t={bb['t']} "
                  f"({bb['dl']-bb['t']:+d} spare)")
        print("CAPTURED (best banked; champion never delivered):")
        for (key, bb) in sorted(captured, key=lambda r: -r[1]["v"]):
            print(f"  shelf {key[0]:>3} arr t={key[1]:<3} v={bb['v']:5.1f} dl={bb['dl']:<4} | "
                  f"best t={bb['t']} ({bb['dl']-bb['t']:+d} spare) | champ: NEVER")
        print("LOST (champion banked; best schedule missed) -- the price paid:")
        for (key, cc) in sorted(lost, key=lambda r: -r[1]["v"]):
            got = b.get(key)
            how = f"late t={got['t']}" if got else "never"
            print(f"  shelf {key[0]:>3} arr t={key[1]:<3} v={cc['v']:5.1f} dl={cc['dl']:<4} | "
                  f"champ t={cc['t']} | best: {how}")
        near = [(key, cc) for key, cc in c.items() if not cc["on"] and cc["dl"] and 0 < cc["t"]-cc["dl"] <= 10]
        print(f"NEAR-MISSES by champion (late by <=10 steps): {len(near)} orders, "
              f"value {sum(x[1]['v'] for x in near):.1f} -- the cheapest money on the table")


if __name__ == "__main__":
    main()
