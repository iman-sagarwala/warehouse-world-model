"""M2 letter gap: CALIBRATION (spec: +/-10%). Is belief=p right p% of the time?

Reliability curve: bin every (highway cell, step) sample by the map's stated belief, and compare
each bin's stated probability to the observed dirty fraction. Reset-mode map, active shipped
routing, multi-cell events, until-amnesty, 24 seeds.
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 13)) + list(range(73, 85))
BINS = [0.0, 0.1, 0.2, 0.3, 0.45, 0.499, 0.501, 0.55, 0.7, 0.9, 1.0]


def one(seed):
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
    env.rumor_map = BetaRumorMap(env.grid_size)
    env.b_hard = 0.5
    env.los_sensing = True
    H, W = env.grid_size
    hwmask = env.highways.astype(bool)
    nb = len(BINS) - 1
    cnt = np.zeros(nb)
    dirty = np.zeros(nb)
    psum = np.zeros(nb)
    for t in range(500):
        env.step(ctrl.act())
        b = env.rumor_map.belief()[hwmask]
        truth = np.zeros((H, W), dtype=bool)
        for (y, x) in env.disturbed:
            truth[y, x] = True
        tr = truth[hwmask]
        idx = np.clip(np.digitize(b, BINS) - 1, 0, nb - 1)
        for k in range(nb):
            m = idx == k
            n = int(m.sum())
            if n:
                cnt[k] += n
                dirty[k] += int(tr[m].sum())
                psum[k] += float(b[m].sum())
    return cnt, dirty, psum


if __name__ == "__main__":
    import numpy as np
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, SEEDS)
    cnt = sum(r[0] for r in rows)
    dirty = sum(r[1] for r in rows)
    psum = sum(r[2] for r in rows)
    print("CALIBRATION / RELIABILITY CURVE (reset map, %d seeds; spec: +/-10%%)\n" % len(SEEDS))
    print("%-16s %-14s %-14s %-14s %s" % ("belief bin", "stated mean", "observed dirty",
                                          "gap", "samples"))
    for k in range(len(BINS) - 1):
        if cnt[k] == 0:
            print("%-16s (empty)" % ("[%.3g, %.3g)" % (BINS[k], BINS[k + 1])))
            continue
        stated = psum[k] / cnt[k]
        obs = dirty[k] / cnt[k]
        print("%-16s %6.1f%%        %6.2f%%        %+6.1fpp      %d"
              % ("[%.3g, %.3g)" % (BINS[k], BINS[k + 1]),
                 100 * stated, 100 * obs, 100 * (obs - stated), int(cnt[k])))
