"""The head-to-head that was never actually run: the SHIPPED system against the learner.

The 2026-08-24 evaluation compared the learned dispatcher to the champion with fixed constants.
But the shipped system is the champion PLUS the model-predictive self-tuner -- the layer that makes
this a world model rather than a scoring function, and the thing the project is actually about.
That arm was missing, so the project's own headline comparison has never been made.

Three arms, held-out seeds 97-144, paired:
  marl      the policy-gradient dispatcher, greedy, from results/marl_policy.pt
  champ     hand-written rules, fixed constants
  mpc       hand-written rules + the self-tuner re-deciding its settings every 50 steps  <- shipped

Outputs results/marl_vs_shipped.csv.
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
SEEDS = [int(x) for x in os.environ.get("MVSEEDS",
                                        ",".join(str(i) for i in range(97, 145))).split(",")]
OUT = os.environ.get("OUT", "results/marl_vs_shipped.csv")


def one(job):
    arm, seed = job
    if arm == "marl":
        import torch
        from marl_dispatch import make_net, rollout, MODEL
        net = make_net()
        net.load_state_dict(torch.load(MODEL))
        _s, onv, _d = rollout((seed, net.state_dict(), True, "marl"))
        return dict(arm=arm, seed=seed, onv=onv)

    import m3_mpc as M
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    cur = M.DEFAULT
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
    return dict(arm=arm, seed=seed, onv=round(onv, 1))


if __name__ == "__main__":
    ARMS = os.environ.get("ARMS", "marl,champ,mpc").split(",")
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["arm", "seed", "onv"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    D = {a: {} for a in ARMS}
    for r in rows:
        D[r["arm"]][r["seed"]] = r["onv"]
    n = len(SEEDS)

    def paired(a, b):
        d = [D[a][s] - D[b][s] for s in SEEDS]
        m = sum(d) / n
        sd = st.pstdev(d) * (n / (n - 1)) ** 0.5 if n > 1 else 0.0
        return m, (m / (sd / n ** 0.5) if sd else 0.0), sum(1 for x in d if x > 0)

    print("THE SHIPPED SYSTEM vs THE LEARNER -- held-out seeds 97-144, %d paired days\n" % n)
    for a in ARMS:
        print("  %-6s mean %8.2f" % (a, sum(D[a][s] for s in SEEDS) / n))
    print()
    for a in ARMS:
        if a == "marl":
            continue
        m, t, w = paired(a, "marl")
        base = sum(D["marl"][s] for s in SEEDS) / n
        print("  %-6s beats the learner by %+7.2f  (%+5.1f%%)  t=%+6.2f  wins %d/%d"
              % (a, m, 100 * m / base, t, w, n))
    if "mpc" in D and "champ" in D:
        m, t, w = paired("mpc", "champ")
        print("\n  the self-tuner adds %+.2f over fixed constants (t=%+.2f, wins %d/%d)"
              % (m, t, w, n))
    print("\nwrote", OUT)
