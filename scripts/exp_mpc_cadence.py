"""The tune-later item: is the MPC's 50-step cadence / 100-step horizon actually right?

Both numbers were DESIGNED, never swept: 50 because forking the whole warehouse is the expensive
part, 100 because it is long enough to contain a charge round-trip. This sweeps them on STRESS
days (where the tuner's edge is visible at all) against the fixed-constant control.

cells: (cadence, horizon) -- 25/50, 25/100, 50/100 (shipped), 50/200, 100/200
Cost note: work per day ~ (500/cadence) x horizon x moves, so 25/100 costs 2x the shipped setting
and 50/200 likewise -- the sweep reports value, not compute, so read them together.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = [int(x) for x in os.environ.get("M5SEEDS", ",".join(str(i) for i in range(1, 49))).split(",")]
CELLS = [tuple(int(v) for v in c.split("/")) for c in
         os.environ.get("CELLS", "0/0,25/50,25/100,50/100,50/200,100/200").split(",")]
STRESS = os.environ.get("STRESS", "1") == "1"      # 1 = stress days, 0 = ordinary days
REGIME = os.environ.get("REGIME", "wave")          # wave | stream


def one(job):
    (cad, hor), seed = job
    import m3_mpc as M
    from record_race import build
    os.environ["M3SPC"] = "300" if STRESS else "1500"
    env, ctrl = build("large-8-6", seed, stress=STRESS, stream=(REGIME == "stream"))
    dm = env.demand_model
    cur = M.DEFAULT
    M.apply_setting(ctrl, cur)
    stats = {mv: [0, 0.0] for mv in M.moves_for(env)}
    onv, adopts, forks = 0.0, 0, 0
    for t in range(500):
        if REGIME == "stream":
            dm.step(env, t)
        if cad and t > 0 and t % cad == 0:
            base = M.rollout_score(env, ctrl, cur, t, hor)
            forks += 1
            best_s, best = base, cur
            for mv in M.ucb_pick(stats):
                s_ = M.apply_move(cur, mv)
                if s_ == cur:
                    continue
                sc = M.rollout_score(env, ctrl, s_, t, hor)
                forks += 1
                n_, mean = stats[mv]
                stats[mv] = [n_ + 1, mean + (sc - base - mean) / (n_ + 1)]
                if sc > best_s:
                    best_s, best = sc, s_
            if best != cur:
                cur = best
                M.apply_setting(ctrl, cur)
                adopts += 1
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    bat = getattr(ctrl, "battery", None)
    dead = sum(1 for a in env.agents if bat and bat.level.get(a.id, 1.0) <= 0.02)
    return ((cad, hor), seed, round(onv, 1), adopts, forks * hor, dead)


if __name__ == "__main__":
    jobs = [(c, s) for c in CELLS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    D = {c: {} for c in CELLS}
    AD = {c: 0 for c in CELLS}
    IM = {c: 0 for c in CELLS}
    DE = {c: 0 for c in CELLS}
    for c, s, v, ad, im, de in rows:
        D[c][s] = v
        AD[c] += ad
        IM[c] += im
        DE[c] += de
    n = len(SEEDS)
    ctrl_cell = (0, 0)
    base = sum(D[ctrl_cell].values()) / n
    print("MPC CADENCE / HORIZON SWEEP -- %s, %s days (%d paired seeds)\n"
          % (REGIME, "stress" if STRESS else "ordinary", n))
    print("%-14s %9s %10s %8s %10s %12s %9s"
          % ("cadence/horiz", "value", "vs fixed", "t", "adoptions", "imagined steps", "stranded"))
    for c in CELLS:
        diff = [D[c][s] - D[ctrl_cell][s] for s in SEEDS]
        m = sum(diff) / n
        sd = st.pstdev(diff) * (n / (n - 1)) ** 0.5
        tt = m / (sd / n ** 0.5) if (sd and c != ctrl_cell) else 0.0
        lbl = "fixed (no MPC)" if c == ctrl_cell else "%d / %d%s" % (
            c[0], c[1], "  <- shipped" if c == (50, 100) else "")
        print("%-14s %9.2f %+10.2f %+8.2f %10d %12d %9d"
              % (lbl, sum(D[c].values()) / n, m, tt, AD[c], IM[c] // max(1, n), DE[c]))
    print("\n(imagined steps = simulated steps per day, the compute price of each setting)")
