"""With vs WITHOUT prediction at the sensor-poor radius (r=1, near-contact sensing).

  sightonly  dodge only what is in someone's 1-cell view RIGHT NOW (decay=0: no memory)
  pred       full prediction: remember what was encountered, believe it until seen clean
Anchors on identical seeds/world: blind 800.56 (hits 364), r5 full 850.05 (80), clair 855.84.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 25)) + list(range(73, 97))


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
    env.use_belief_routing = True
    env.rumor_map = BetaRumorMap(env.grid_size, sight_radius=1,
                                 decay=(0.0 if arm == "sightonly" else 0.99))
    env.b_hard = 0.5
    env.los_sensing = True
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1), getattr(env, "_debris_hits", 0))


if __name__ == "__main__":
    ARMS = ("sightonly", "pred")
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    H = {a: 0 for a in ARMS}
    for a, s, v, hits in rows:
        D[a][s] = v
        H[a] += hits
    n_ = len(SEEDS)
    print("PREDICTION ABLATION AT r=1 (near-contact sensing, %d seeds)\n" % n_)
    print("anchors: blind 800.56 (hits 364) | r5 full map 850.05 (80) | clairvoyant 855.84\n")
    for a in ARMS:
        v = sum(D[a].values()) / n_
        print("%-10s mean %8.2f  debris hits %d" % (a, v, H[a]))
    diff = [D["pred"][s] - D["sightonly"][s] for s in SEEDS]
    m = sum(diff) / n_
    sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
    print("\nprediction is worth %+0.2f at r=1 (t=%+.2f)"
          % (m, m / (sd_ / n_ ** 0.5) if sd_ else 0.0))
