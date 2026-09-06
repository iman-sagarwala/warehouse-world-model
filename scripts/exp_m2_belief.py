"""M2 CODA (iii): the belief-map audition, on the VALUABLE side of the phase boundary.

Cell: transient debris, hold=20 (where clairvoyant information is proven valuable, z=+2.83).
Arms:
  blind        b_hard=1.1 -- router never sees debris, pays the recovery holds
  belief       b_hard=0.5 + line-of-sight sensing -- robots route around what the FLEET HAS
               OBSERVED (one robot's pain -> fleet knowledge); imperfect, decaying knowledge.
               Since 2026-08-23 the map uses RESET updates (a look replaces the cell's
               evidence): 99.8% of the sensing ceiling, 83% of clairvoyant VoPI
  clairvoyant  ground-truth avoidance (the upper bound)
Question: how much of the clairvoyant VoPI does honest observation capture?
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = ([int(x) for x in os.environ["SEEDLIST"].split(",")] if os.environ.get("SEEDLIST")
         else list(range(1, 25)) + list(range(73, 97)))
NPROC = int(os.environ.get("NPROC", "8"))
HOLD = int(os.environ.get("M2HOLD", "20"))       # -1 = stuck until amnesty
DUR = ((500, 501) if os.environ.get("M2DUR") == "day" else (150, 400))
RATE = 0.02


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    from wwm_sim.rumor_map import BetaRumorMap
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    env.disturb_rate = RATE
    env._disturb_rng = np.random.RandomState(4000 + seed)
    env.disturb_dur = DUR
    env.debris_hold_steps = HOLD
    if os.environ.get("M2JANITOR") == "1":
        env.janitor = True
    if arm != "clairvoyant":
        env.use_belief_routing = True
        env.rumor_map = BetaRumorMap(env.grid_size, sight_radius=int(os.environ.get("M2RADIUS", "5")))
        env.b_hard = 1.1 if arm == "blind" else 0.5
        env.los_sensing = (arm == "belief")
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1), getattr(env, "_debris_hits", 0))


if __name__ == "__main__":
    ARMS = ("blind", "belief", "clairvoyant")
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    H = {a: 0 for a in ARMS}
    for a, s, v, hits in rows:
        D[a][s] = v
        H[a] += hits
    n_ = len(SEEDS)
    print("M2 BELIEF AUDITION (dur=%s, hold=%d, rate=%.3f, %d seeds)\n" % (os.environ.get("M2DUR","transient"), HOLD, RATE, n_))
    base = sum(D["blind"].values()) / n_
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
    if cl:
        print("\nbelief captures %.0f%% of the clairvoyant VoPI" % (100.0 * be / cl))
