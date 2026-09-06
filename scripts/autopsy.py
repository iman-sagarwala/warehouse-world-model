"""CRATER AUTOPSY: on seeds where the hi-fi sequencer lost >=40 to urg8, replay both deterministically,
log every commit and delivery, and report: where the schedules first diverged, what the sequencer chose
differently, and exactly which orders paid for it. Goal: a shared failure signature -> a targeted guard."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import _Urg8, _Sq5

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = [int(x) for x in os.environ.get("CRATERS", "250,234,206,273").split(",")]


def episode(seed, factory):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = factory(env)
    commits = []
    orig = ctrl._on_predict

    def hook(shelf, now, pf):
        commits.append((int(now), int(shelf.id)))
        return orig(shelf, now, pf)
    ctrl._on_predict = hook
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
    return onv, commits, deliv


def main():
    agg = {"seeds": 0, "lost_orders": 0, "lost_batched": 0, "lost_v": 0.0, "lost_batched_v": 0.0,
           "late": 0, "never": 0, "div0": 0}
    for s in SEEDS:
        u_onv, u_com, u_del = episode(s, _Urg8)
        q_onv, q_com, q_del = episode(s, _Sq5)
        div = None
        for i in range(min(len(u_com), len(q_com))):
            if u_com[i] != q_com[i]:
                div = i
                break
        lost = [(k, u_del[k]) for k in u_del if u_del[k]["on"] and not (k in q_del and q_del[k]["on"])]
        gained = [(k, q_del[k]) for k in q_del if q_del[k]["on"] and not (k in u_del and u_del[k]["on"])]
        print(f"=== SEED {s}: urg8 {u_onv:.1f} vs sq5 {q_onv:.1f}  ({q_onv-u_onv:+.1f}) ===")
        if div is not None:
            print(f"  first divergence at commit #{div}: urg8 t={u_com[div][0]} shelf {u_com[div][1]}"
                  f"  |  sq5 t={q_com[div][0]} shelf {q_com[div][1]}"
                  f"  (of {len(u_com)}/{len(q_com)} commits)")
        print(f"  ORDERS LOST by sq5 ({len(lost)}, value {sum(x[1]['v'] for x in lost):.1f}):")
        for (k, r) in sorted(lost, key=lambda x: -x[1]["v"])[:6]:
            got = q_del.get(k)
            how = f"late t={got['t']} ({got['t']-got['dl']:+d})" if got else "NEVER delivered"
            print(f"    shelf {k[0]:>3} v={r['v']:5.1f} dl={r['dl']:<4} urg8 t={r['t']}  | sq5: {how}")
        print(f"  orders gained by sq5: {len(gained)}, value {sum(x[1]['v'] for x in gained):.1f}")
        print()
        agg["seeds"] += 1
        if div == 0:
            agg["div0"] += 1
        from collections import Counter
        shelf_counts = Counter(k[0] for k in u_del)          # orders per shelf in this world
        for (k, r) in lost:
            agg["lost_orders"] += 1
            agg["lost_v"] += r["v"]
            if shelf_counts[k[0]] > 1:
                agg["lost_batched"] += 1
                agg["lost_batched_v"] += r["v"]
            got = q_del.get(k)
            agg["late" if got else "never"] += 1
    print("===== AGGREGATE SIGNATURE =====")
    print(f"  seeds {agg['seeds']} | diverged at commit #0: {agg['div0']}")
    print(f"  lost orders {agg['lost_orders']} (value {agg['lost_v']:.1f})")
    print(f"  on BATCHED shelves: {agg['lost_batched']} ({agg['lost_batched_v']:.1f} value, "
          f"{100*agg['lost_batched_v']/max(agg['lost_v'],1e-9):.0f}% of lost value)")
    print(f"  delivered LATE: {agg['late']} | NEVER delivered: {agg['never']}")


if __name__ == "__main__":
    main()
