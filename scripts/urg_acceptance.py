"""Order-level ACCEPTANCE TEST for the urgency bonus: does urg8 collect the RESCUED category
(champion's barely-late orders -> on time) WITHOUT creating new LOST orders (displacing safe work)?

Champion vs urg8, same fixed day-list worlds (seeds 0-4, the oracle-mapped ones):
  FIX-RESCUED : late/never under champion -> ON TIME under urg8   (the intended gain)
  FIX-LOST    : on time under champion -> late/never under urg8   (the feared regression)
Defined in advance: accept if rescued-value >> lost-value and lost stays near zero.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import PartACongestionController, _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500


def episode(seed, factory):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = factory(env)
    deliv = {}
    onv = 0.0
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            on = o.deadline is not None and t <= o.deadline
            deliv[(o.shelf.id, o.t_arrive)] = {"t": t, "v": o.value, "dl": o.deadline, "on": on}
            if on:
                onv += o.value
        done = all(term) or all(trunc)
    return onv, deliv


def main():
    tr = tl = 0.0
    print(f"{'seed':>5}{'champ':>8}{'urg8':>8}{'diff':>7} | {'FIX-RESCUED':>16}{'FIX-LOST':>14}")
    for s in range(5):
        c_onv, c = episode(s, PartACongestionController)
        u_onv, u = episode(s, _Urg8)
        resc = [(k, u[k]) for k in u if u[k]["on"] and not (k in c and c[k]["on"])]
        lost = [(k, c[k]) for k in c if c[k]["on"] and not (k in u and u[k]["on"])]
        rv = sum(x[1]["v"] for x in resc)
        lv = sum(x[1]["v"] for x in lost)
        tr += rv
        tl += lv
        print(f"{s:>5}{c_onv:8.1f}{u_onv:8.1f}{u_onv-c_onv:+7.1f} | "
              f"{len(resc):>4} = {rv:+9.1f}{len(lost):>4} = {lv:-8.1f}")
    print(f"\nTOTALS: fix-rescued {tr:+.1f} vs fix-lost {tl:-.1f}  "
          f"(oracle's rescued category on these seeds was +84.2, lost benchmark ~0)")


if __name__ == "__main__":
    main()
