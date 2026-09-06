"""Janitor pre-positioning: the one agent where WHERE-prediction should pay.

Robot routing on the learned hazard map lost (zone-granularity avoidance costs more than hits).
The janitor has ZERO opportunity cost while idle -- so waiting at the learned hotspot instead of
the fixed base converts the same prediction into pure response time. Janitor world (until-amnesty,
no timers), multi-cell events, 48 seeds:
  base     belief routing + janitor waits at its fixed base (goals[0])
  prepos   same + learn_style (stats only; bump/slowmem OFF) + janitor waits at learned hotspot
Metrics: on-time value (paired t), debris hits, spills cleaned.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 25)) + list(range(73, 97))
NPROC = int(os.environ.get("NPROC", "8"))


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    from wwm_sim.rumor_map import BetaRumorMap
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    env.disturb_rate = 0.02
    env._disturb_rng = np.random.RandomState(4000 + seed)
    env.disturb_dur = (150, 400)
    env.disturb_event_cells = (1, 3)
    env.debris_hold_steps = -1
    env.janitor = True
    env.use_belief_routing = True
    rm = BetaRumorMap(env.grid_size, learn_style=(arm == "prepos"))
    rm.style_bump = rm.style_slowmem = False
    env.rumor_map = rm
    env.b_hard = 0.5
    env.los_sensing = True
    if arm == "prepos":
        env.janitor_preposition = True
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1), getattr(env, "_debris_hits", 0),
            env._jan["cleaned"] if getattr(env, "_jan", None) else 0)


if __name__ == "__main__":
    ARMS = ("base", "prepos")
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    H = {a: 0 for a in ARMS}
    C = {a: 0 for a in ARMS}
    for a, s, v, hits, cleaned in rows:
        D[a][s] = v
        H[a] += hits
        C[a] += cleaned
    n_ = len(SEEDS)
    print("JANITOR PRE-POSITIONING (janitor world, multi-cell 1-3, until-amnesty, %d seeds)\n" % n_)
    for a in ARMS:
        v = sum(D[a].values()) / n_
        diff = [D[a][s] - D["base"][s] for s in SEEDS]
        m = sum(diff) / n_
        sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
        tt = m / (sd_ / n_ ** 0.5) if (sd_ and a != "base") else 0.0
        print("%-8s mean %8.2f  vs base %+7.2f  t=%+.2f  debris hits %d  cleaned %d"
              % (a, v, m, tt, H[a], C[a]))
