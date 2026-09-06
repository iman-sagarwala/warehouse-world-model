"""Style-learning audition: does learning the disturbance SPAWN PROCESS pay?

World: multi-cell spill events (1-3 contiguous cells), until-amnesty holds, timer amnesty
(no janitor -- that regime has no headroom left to measure). Arms:
  blind        router never sees debris
  belief       plain BetaRumorMap (cell-independent, learns only WHERE spills are now)
  style        BetaRumorMap(learn_style=True): learns event size + spatial hazard; spreads
               suspicion to neighbors of fresh sightings, forgets slower in learned hot zones
  clairvoyant  ground truth (upper bound)
Question: how much of the belief->clairvoyant gap does learning the spawn style recover?
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
    if arm != "clairvoyant":
        env.use_belief_routing = True
        env.rumor_map = BetaRumorMap(env.grid_size, learn_style=(arm == "style"))
        env.b_hard = 1.1 if arm == "blind" else 0.5
        env.los_sensing = (arm != "blind")
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1), getattr(env, "_debris_hits", 0))


if __name__ == "__main__":
    ARMS = ("blind", "belief", "style", "clairvoyant")
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    H = {a: 0 for a in ARMS}
    for a, s, v, hits in rows:
        D[a][s] = v
        H[a] += hits
    n_ = len(SEEDS)
    print("STYLE-LEARNING AUDITION (multi-cell events 1-3, until-amnesty, %d seeds)\n" % n_)
    for a in ARMS:
        v = sum(D[a].values()) / n_
        diff = [D[a][s] - D["blind"][s] for s in SEEDS]
        m = sum(diff) / n_
        sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
        tt = m / (sd_ / n_ ** 0.5) if (sd_ and a != "blind") else 0.0
        print("%-12s mean %8.2f  vs blind %+7.2f  t=%+.2f  debris hits %d"
              % (a, v, m, tt, H[a]))
    cl = sum(D["clairvoyant"][s] - D["blind"][s] for s in SEEDS) / n_
    be = sum(D["belief"][s] - D["blind"][s] for s in SEEDS) / n_
    sty = sum(D["style"][s] - D["blind"][s] for s in SEEDS) / n_
    dst = [D["style"][s] - D["belief"][s] for s in SEEDS]
    mst = sum(dst) / n_
    sdst = st.pstdev(dst) * (n_ / (n_ - 1)) ** 0.5
    if cl:
        print("\ncapture of clairvoyant VoPI: belief %.0f%%  style %.0f%%"
              % (100.0 * be / cl, 100.0 * sty / cl))
    print("style vs belief (paired): %+.2f  t=%+.2f" % (mst, mst / (sdst / n_ ** 0.5) if sdst else 0.0))
