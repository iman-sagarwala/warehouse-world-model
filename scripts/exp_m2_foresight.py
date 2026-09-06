"""Does physics-based foresight pay IN THE DISTURBANCE WORLD?

fixed-m3 vs m3-MPC (embedded forward-simulation tuner, honest forks: disturbance RNG reseeded so
imagined futures SAMPLE spills rather than replay the true ones), both on reset-mode belief
routing. Multi-cell events 1-3, until-amnesty, 48 paired seeds.
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
    import m3_mpc as M
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
    env.rumor_map = BetaRumorMap(env.grid_size)
    if os.environ.get("OLDMAP") == "1":
        env.rumor_map.obs_reset = False      # legacy incremental-vote map (pre-2026-08-23)
    env.b_hard = 0.5
    env.los_sensing = True
    cur = M.DEFAULT
    M.apply_setting(ctrl, cur)
    stats = {mv: [0, 0.0] for mv in M.moves_for(env)}
    onv = 0.0
    adoptions = 0
    for t in range(500):
        if arm == "mpc" and t > 0 and t % 50 == 0:
            base = M.rollout_score(env, ctrl, cur, t, 100)
            best_s, best = base, cur
            for mv in M.ucb_pick(stats):
                s_ = M.apply_move(cur, mv)
                if s_ == cur:
                    continue
                sc = M.rollout_score(env, ctrl, s_, t, 100)
                n_, mean = stats[mv]
                stats[mv] = [n_ + 1, mean + (sc - base - mean) / (n_ + 1)]
                if sc > best_s:
                    best_s, best = sc, s_
            if best != cur:
                cur = best
                M.apply_setting(ctrl, cur)
                adoptions += 1
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1), getattr(env, "_debris_hits", 0), adoptions)


if __name__ == "__main__":
    ARMS = tuple(os.environ.get("ARMS", "fixed,mpc").split(","))
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    H = {a: 0 for a in ARMS}
    A = {a: 0 for a in ARMS}
    for a, s, v, hits, ad in rows:
        D[a][s] = v
        H[a] += hits
        A[a] += ad
    n_ = len(SEEDS)
    print("PHYSICS FORESIGHT IN THE DISTURBANCE WORLD (multi-cell 1-3, until-amnesty, "
          "reset map, %d seeds)\n" % n_)
    for a in ARMS:
        v = sum(D[a].values()) / n_
        base_arm = ARMS[0]
        diff = [D[a][s] - D[base_arm][s] for s in SEEDS]
        m = sum(diff) / n_
        sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
        tt = m / (sd_ / n_ ** 0.5) if (sd_ and a != base_arm) else 0.0
        print("%-6s mean %8.2f  vs fixed %+7.2f  t=%+.2f  debris hits %d  adoptions %d"
              % (a, v, m, tt, H[a], A[a]))
