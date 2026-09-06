"""M2 CODA: the VoPI phase boundary. Where does disturbance information flip from harmful to valuable?

Grid: {blind, informed} x debris_hold_steps {0, 5, 20} x persistence {transient(150-400), day(500)}.
- blind:    belief routing with b_hard=1.1 -> the router never sees debris; robots pay the
            execution cost (recovery holds) when they drive in.
- informed: clairvoyant avoidance (default: find_path routes around ground truth instantly).
VoPI(cell) = informed - blind. At hold=0 debris is planning-only and SS5.16 says VoPI < 0
(pure avoidance overhead). As collision cost and persistence rise, VoPI must cross zero.
Rate fixed at 0.02 (the 10x setting where the old negative was measured). m3 controller,
battery SPC=1500, wave regime, 24 mixed seeds per cell.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = ([int(x) for x in os.environ["SEEDLIST"].split(",")] if os.environ.get("SEEDLIST")
         else list(range(1, 13)) + list(range(73, 85)))
NPROC = int(os.environ.get("NPROC", "8"))
HOLDS = [0, 5, 20]
DURS = {"transient": (150, 400), "day": (500, 501)}
RATE = 0.02


def one(job):
    arm, hold, durkey, seed = job
    import numpy as np
    from record_race import build
    from wwm_sim.rumor_map import BetaRumorMap
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    env.disturb_rate = RATE
    env._disturb_rng = np.random.RandomState(4000 + seed)
    env.disturb_dur = DURS[durkey]
    env.debris_hold_steps = hold
    if arm == "blind":
        env.use_belief_routing = True
        env.rumor_map = BetaRumorMap(env.grid_size)
        env.b_hard = 1.1
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, hold, durkey, seed, round(onv, 1),
            getattr(env, "_debris_hits", 0))


if __name__ == "__main__":
    jobs = [(a, h, d, s) for h in HOLDS for d in DURS for a in ("blind", "informed")
            for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {}
    HITS = {}
    for a, h, d, s, v, hits in rows:
        D.setdefault((h, d, a), {})[s] = v
        HITS[(h, d, a)] = HITS.get((h, d, a), 0) + hits
    n_ = len(SEEDS)
    print("M2 PHASE BOUNDARY (%d seeds/cell, rate=%.3f, large-8-6, m3)\n" % (n_, RATE))
    print("%-10s %-6s %10s %10s %9s %8s %7s" % ("persist", "hold", "blind", "informed",
                                                "VoPI", "t", "hits(b)"))
    for d in DURS:
        for h in HOLDS:
            b = D[(h, d, "blind")]
            i = D[(h, d, "informed")]
            diff = [i[s] - b[s] for s in SEEDS]
            m = sum(diff) / n_
            sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
            tt = m / (sd_ / n_ ** 0.5) if sd_ else 0.0
            print("%-10s %-6d %10.1f %10.1f %+9.1f %+8.2f %7d"
                  % (d, h, sum(b.values()) / n_, sum(i.values()) / n_, m, tt,
                     HITS[(h, d, "blind")]))
