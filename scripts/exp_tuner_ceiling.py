"""Gap 2 of the oracle audit: the self-tuner is the one mechanism we claim a benefit for without
ever measuring its ceiling.

Every other channel has one. For the tuner we only ever knew "tuned beats fixed" -- never "how much
of what a perfect settings-chooser could get does the tuner actually capture?". Without that, +1%/day
is unanchored: it could be 90% of the available headroom or 9% of it.

The ceiling used here is the HINDSIGHT-BEST SINGLE SETTING, per seed. Every one-move neighbour of
the shipped default is held fixed for a whole episode; the oracle is the per-seed maximum over that
set, chosen after seeing the outcome. It upper-bounds any policy that picks one setting per day --
which is what the tuner's own move set can express -- and it is honest about what it is NOT: a tuner
that varies settings WITHIN a day can in principle beat it (the shipped tuner does exactly that), so
the oracle is a reference point rather than a hard bound. Both readings are reported.

  fixed        the shipped default, held all day (the control)
  <move>       each single-move neighbour, held all day -- no forks, so these are cheap
  mpc          the shipped self-tuner, re-deciding every 50 steps
  ORACLE       per-seed max over {fixed} + all neighbours, computed not run

Stress days, where the tuner has a measurable edge at all.
Outputs results/tuner_ceiling.csv.
"""
import csv
import io
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = [int(x) for x in os.environ.get("TCSEEDS",
                                        ",".join(str(i) for i in range(1, 49))).split(",")]
OUT = os.environ.get("OUT", "results/tuner_ceiling.csv")
FIELDS = ["arm", "seed", "onv", "stranded"]


def _arms():
    import m3_mpc as M
    return ["fixed"] + [m for m in M.MOVES if m != "stay"] + ["mpc"]


def one(job):
    arm, seed = job
    import m3_mpc as M
    from record_race import build

    env, ctrl = build("large-8-6", seed, stress=True)
    cur = M.DEFAULT
    if arm not in ("fixed", "mpc"):
        cur = M.apply_move(M.DEFAULT, arm)        # one knob away, held all day
    M.apply_setting(ctrl, cur)
    stats = {mv: [0, 0.0] for mv in M.moves_for(env)}

    onv = 0.0
    for t in range(STEPS):
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
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    bat = getattr(ctrl, "battery", None)
    stranded = sum(1 for a in env.agents if bat and bat.level.get(a.id, 1.0) <= 0.02)
    return dict(arm=arm, seed=seed, onv=round(onv, 1), stranded=stranded)


if __name__ == "__main__":
    ARMS = os.environ.get("ARMS", ",".join(_arms())).split(",")
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    print("tuner ceiling: %d arms x %d seeds = %d runs" % (len(ARMS), len(SEEDS), len(jobs)),
          flush=True)
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    D = {a: {} for a in ARMS}
    for r in rows:
        D[r["arm"]][r["seed"]] = r
    n = len(SEEDS)
    fixed_arms = [a for a in ARMS if a != "mpc"]

    def paired(vals):
        d = [vals[s] - D["fixed"][s]["onv"] for s in SEEDS]
        m = sum(d) / n
        sd = st.pstdev(d) * (n / (n - 1)) ** 0.5 if n > 1 else 0.0
        return m, (m / (sd / n ** 0.5) if sd else 0.0)

    print("\nTUNER CEILING -- stress days, %d paired seeds\n" % n)
    print("%-10s %9s %10s %8s %9s" % ("arm", "value", "vs fixed", "t", "stranded"))
    for a in ARMS:
        m, tt = paired({s: D[a][s]["onv"] for s in SEEDS})
        print("%-10s %9.2f %+10.2f %+8.2f %9d"
              % (a, sum(D[a][s]["onv"] for s in SEEDS) / n, m, tt,
                 sum(D[a][s]["stranded"] for s in SEEDS)))

    # the hindsight oracle: best single fixed setting per seed, chosen after the fact
    orc = {s: max(D[a][s]["onv"] for a in fixed_arms) for s in SEEDS}
    m_o, t_o = paired(orc)
    m_m, t_m = paired({s: D["mpc"][s]["onv"] for s in SEEDS})
    # and the best single setting chosen ONCE for all seeds (a deployable constant, not per-day)
    best_const = max(fixed_arms, key=lambda a: sum(D[a][s]["onv"] for s in SEEDS))
    m_c, t_c = paired({s: D[best_const][s]["onv"] for s in SEEDS})

    print("\n%-34s %+8.2f  (t = %+.2f)" % ("HINDSIGHT ORACLE (best per seed)", m_o, t_o))
    print("%-34s %+8.2f  (t = %+.2f)" % ("best single constant (`%s`)" % best_const, m_c, t_c))
    print("%-34s %+8.2f  (t = %+.2f)" % ("the shipped self-tuner", m_m, t_m))
    if m_o > 0:
        print("\n=> the tuner captures %.0f%% of the hindsight-best-single-setting headroom"
              % (100 * m_m / m_o))
        print("   (and %.0f%% of what the best deployable constant gets)"
              % (100 * m_m / m_c) if m_c else "")
    print("\nNB the oracle picks ONE setting per day with hindsight; the tuner re-decides within the")
    print("day, so it can legitimately exceed 100% -- that would say intra-day variation is the")
    print("thing that pays, which is exactly what the oscillation result (5.25) implies.")
    print("\nwrote", OUT)
