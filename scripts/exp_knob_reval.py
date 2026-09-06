"""M1's last deferred item: knob revalidation with disturbances AND battery on (post-M2/M3).

Do the champion's dispatch constants still hold in the FULL world (standard-compression battery
+ multi-cell spills + reset-mode belief routing)? Champion vs a +/- bracket on each of the four
dispatch knobs, everything else at shipped constants. 24 paired seeds; verdict per knob: the
constant HOLDS unless a bracket side beats it at |t|>=2 (the ship bar).
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 13)) + list(range(73, 85))
# (label, field index in the 9-field MPC setting, value)
ARMS = [("champion", None, None),
        ("alpha5", 3, 5.0), ("alpha9", 3, 9.0),
        ("depth3", 4, 3), ("depth7", 4, 7),
        ("urg2", 5, 2.0),
        ("hyst10", 6, 10), ("hyst30", 6, 30)]


def one(job):
    label, idx, val = job[0]
    seed = job[1]
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
    env.b_hard = 0.5
    env.los_sensing = True
    s = list(M.DEFAULT)
    if idx is not None:
        s[idx] = val
    M.apply_setting(ctrl, tuple(s))
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (label, seed, round(onv, 1))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    D = {a[0]: {} for a in ARMS}
    for label, seed, v in rows:
        D[label][seed] = v
    n_ = len(SEEDS)
    print("KNOB REVALIDATION, FULL WORLD: battery + disturbances + belief (%d seeds)\n" % n_)
    base = sum(D["champion"].values()) / n_
    print("champion (shipped constants)  mean %8.2f\n" % base)
    for label, idx, val in ARMS[1:]:
        diff = [D[label][s] - D["champion"][s] for s in SEEDS]
        m = sum(diff) / n_
        sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
        tt = m / (sd_ / n_ ** 0.5) if sd_ else 0.0
        verdict = "CHALLENGES the constant" if tt >= 2 else (
            "worse (constant confirmed)" if tt <= -2 else "flat (constant holds)")
        print("%-8s mean %8.2f  vs champion %+7.2f  t=%+.2f  -> %s"
              % (label, sum(D[label].values()) / n_, m, tt, verdict))
