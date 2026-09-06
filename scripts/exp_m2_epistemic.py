"""PURE EPISTEMIC ACCURACY: how well does the belief map track the TRUE disturbed set?

No value scoring -- per-step precision/recall of believed-blocked vs ground truth, plus
detection latency, measured on the shipped active belief arm. Compared against the SENSING
CEILING computed on the same run: a perfect-memory oracle fed the identical line-of-sight
stream (any cell a robot's LOS covers resolves instantly and is never forgotten until seen
again). The gap belief->ceiling is fixable software; the gap ceiling->100% is physics (cells
nobody's sight has reached).

Arms = map variants (routing active, shipped b_hard=0.5): decay 0.99 (shipped) / 0.995 /
0.999 / 1.0. World: multi-cell events 1-3, until-amnesty holds, timer amnesty, 24 seeds.
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 13)) + list(range(73, 85))
DECAYS = [(0.98, 1.0), (0.96, 1.0), (0.98, -1.0), (0.99, -1.0)]   # gain -1 => obs_reset mode


def one(job):
    (decay, gain), seed = job
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
    rm = BetaRumorMap(env.grid_size, decay=decay)
    if gain < 0:
        rm.obs_reset = True
    else:
        rm.obs_reset = False          # incremental-vote arms (legacy update rule)
        rm.obs_gain = gain
    env.rumor_map = rm
    env.b_hard = 0.5
    env.los_sensing = True
    H, W = env.grid_size
    hw = env.highways
    los = rm._los_table()

    oracle = {}                  # cell -> last observed state (True=dirty); perfect memory
    spawn_t, det_t = {}, {}      # per-cell spawn step / first believed step
    prev = set()
    rec_n = rec_d = prec_n = prec_d = 0
    orec_n = 0
    for t in range(500):
        env.step(ctrl.act())
        dist = set(env.disturbed)
        for c in dist - prev:
            spawn_t.setdefault(c, t)
        prev = set(dist)
        # the exact LOS stream every observer (real map AND oracle) receives this step
        seen = set()
        for a in env.agents:
            ay, ax = a.y, a.x
            seen.add((ay, ax))
            for (dy, dx), between in los:
                y, x = ay + dy, ax + dx
                if not (0 <= y < H and 0 <= x < W):
                    continue
                if any(0 <= ay + by < H and 0 <= ax + bx < W and not hw[ay + by, ax + bx]
                       for (by, bx) in between):
                    continue
                seen.add((y, x))
        for c in seen:
            oracle[c] = c in dist
        B = rm.believed_blocked(0.5)
        Bo = {c for c, dirty in oracle.items() if dirty}
        for c in dist:
            if c in B and c not in det_t and c in spawn_t:
                det_t[c] = t
        if dist:
            rec_d += len(dist)
            rec_n += len(dist & B)
            orec_n += len(dist & Bo)
        if B:
            prec_d += len(B)
            prec_n += len(dist & B)
    lat = [det_t[c] - spawn_t[c] for c in det_t]
    n_ev = len(spawn_t)
    return ((decay, gain), seed,
            rec_n / max(1, rec_d), orec_n / max(1, rec_d), prec_n / max(1, prec_d),
            (sum(lat) / len(lat)) if lat else -1.0, len(det_t), n_ev)


if __name__ == "__main__":
    jobs = [(d, s) for d in DECAYS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    agg = {d: [] for d in DECAYS}
    for r in rows:
        agg[r[0]].append(r[1:])
    print("EPISTEMIC ACCURACY vs SENSING CEILING (multi-cell 1-3, until-amnesty, %d seeds)\n"
          % len(SEEDS))
    print("%-14s %-14s %-14s %-11s %-12s %s" % ("variant", "recall", "ceiling-recall",
                                               "precision", "latency", "events detected"))
    for d in DECAYS:
        rs = agg[d]
        n = len(rs)
        rec = sum(x[1] for x in rs) / n
        cei = sum(x[2] for x in rs) / n
        pre = sum(x[3] for x in rs) / n
        lat = sum(x[4] for x in rs if x[4] >= 0) / max(1, sum(1 for x in rs if x[4] >= 0))
        det = sum(x[5] for x in rs)
        tot = sum(x[6] for x in rs)
        print("%-14s %5.1f%%         %5.1f%%         %5.1f%%      %5.1f steps  %d/%d"
              % (("d=%g g=%g" % d), 100 * rec, 100 * cei, 100 * pre, lat, det, tot))
