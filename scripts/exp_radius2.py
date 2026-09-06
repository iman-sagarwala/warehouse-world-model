"""Sight-radius under the CURRENT stack (reset map, sight=certainty, multi-cell events).

User proposal: radius should be ~1 cell around the robot. Arms r1 / r2 / r3 belief-only;
anchors recorded on the identical world+seeds: blind 800.56 (hits 364), belief r5 850.05 (80),
clairvoyant 855.84 (22).
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 25)) + list(range(73, 97))
RADII = [1, 2, 3]


def one(job):
    r, seed = job
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
    env.use_belief_routing = True
    env.rumor_map = BetaRumorMap(env.grid_size, sight_radius=r)
    env.b_hard = 0.5
    env.los_sensing = True
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (r, seed, round(onv, 1), getattr(env, "_debris_hits", 0))


if __name__ == "__main__":
    jobs = [(r, s) for r in RADII for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    D = {r: {} for r in RADII}
    H = {r: 0 for r in RADII}
    for r, s, v, hits in rows:
        D[r][s] = v
        H[r] += hits
    n_ = len(SEEDS)
    BLIND, R5, CLAIR = 800.56, 850.05, 855.84
    print("SIGHT RADIUS, CURRENT STACK (reset map, multi-cell 1-3, until-amnesty, %d seeds)" % n_)
    print("anchors: blind %.2f (hits 364) | r5 shipped %.2f (80) | clairvoyant %.2f (22)\n"
          % (BLIND, R5, CLAIR))
    for r in RADII:
        v = sum(D[r].values()) / n_
        cap = 100.0 * (v - BLIND) / (CLAIR - BLIND)
        print("r=%d  mean %8.2f  vs r5 %+7.2f  capture %5.1f%%  debris hits %d"
              % (r, v, v - R5, cap, H[r]))
