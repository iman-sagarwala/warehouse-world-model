"""Scout-detour audition + style-v1 ablation (multi-cell events, until-amnesty, 48 seeds).

Style v1 (neighbor bump + slow forgetting) lost -3.15 vs plain belief. Arms here isolate why,
and test the user's weighted-pick scout design (info-gathering priced into A* path costs):
  belief   plain BetaRumorMap routing (baseline that won)
  bump     style learning, neighbor-suspicion ONLY
  slowmem  style learning, hot-zone slow forgetting ONLY
  scout    style learning for the hazard map ONLY (no avoidance changes) + scout_weight=0.3:
           working robots tilt toward corridors that sweep hazard-prone unobserved cells
  clairvoyant  upper bound
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
        rm = BetaRumorMap(env.grid_size, learn_style=(arm not in ("belief", "sightonly")),
                          decay=(0.0 if arm == "sightonly" else 0.99))
        rm.style_bump = (arm == "bump")
        rm.style_slowmem = (arm == "slowmem")
        rm.style_suspect = (arm == "sightgate")
        rm.obs_reset = (arm == "reset")
        env.rumor_map = rm
        env.b_hard = 0.5
        env.los_sensing = True
        if arm == "scout":
            env.scout_weight = 0.3
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1), getattr(env, "_debris_hits", 0))


if __name__ == "__main__":
    ARMS = tuple(os.environ.get("ARMS", "belief,bump,slowmem,scout,clairvoyant").split(","))
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    H = {a: 0 for a in ARMS}
    for a, s, v, hits in rows:
        D[a][s] = v
        H[a] += hits
    n_ = len(SEEDS)
    print("SCOUT AUDITION + STYLE ABLATION (multi-cell 1-3, until-amnesty, %d seeds)\n" % n_)
    for a in ARMS:
        v = sum(D[a].values()) / n_
        diff = [D[a][s] - D["belief"][s] for s in SEEDS]
        m = sum(diff) / n_
        sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
        tt = m / (sd_ / n_ ** 0.5) if (sd_ and a != "belief") else 0.0
        print("%-12s mean %8.2f  vs belief %+7.2f  t=%+.2f  debris hits %d"
              % (a, v, m, tt, H[a]))
