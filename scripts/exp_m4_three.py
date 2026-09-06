"""M4 three-way (plus formula) VALUE race: how should the deadline check estimate traffic delay?

DISCOVERY (2026-08-24): the shipped champion applies NO pace correction -- _finish_delay() == 0
and delay_head is None. The EMA is tracked and exposed as a feature but never enters the
feasibility test. So the real question is what, if anything, should fill that slot:

  champion  nothing (shipped)                      finish += 0
  emapad    the live EMA as a flat pad (formula)   finish += max(0, delay_ema)
  simpace   fork-measured pace (user's MPC arm)    finish += max(0, pace read in a 50-step fork)
  head      per-candidate LightGBM (Stage-3 head)  finish += max(0, head(feat))

Same warehouses, same held-out days (97-144, never seen by the head's training). Judged on
on-time value; standing ship bar t>=2 against the champion.
"""
import copy
import os
import pickle
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

TEST_SEEDS = list(range(97, 145))
MODEL = "results/m4_cand_head.pkl"
ARMS = ("champion", "emapad", "simpace", "head")


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    cls = type(ctrl)

    if arm == "emapad":
        def fd(self, best_r):
            return max(0.0, float(getattr(self, "_delay_ema", 0.0))
                       if getattr(self, "_delay_inited", False) else 0.0)
        cls._finish_delay = fd
    elif arm == "simpace":
        def fd(self, best_r):
            return max(0.0, float(getattr(self, "_simpace", 0.0)))
        cls._finish_delay = fd
    elif arm == "head":
        blob = pickle.load(open(MODEL, "rb"))
        mdl, feats = blob["model"], blob["feats"]

        def head_fn(feat, _m=mdl, _f=feats):
            x = np.array([[float(feat.get(k, 0.0)) for k in _f]])
            return float(_m.predict(x)[0])
        ctrl.delay_head = head_fn

    onv = 0.0
    for t in range(500):
        if arm == "simpace" and t > 0 and t % 50 == 0:
            env2, c2 = copy.deepcopy((env, ctrl))
            c2.delay_head = None                      # the fork must not recurse into a head
            for _h in range(50):
                env2.step(c2.act())
            if getattr(c2, "_delay_inited", False):
                ctrl._simpace = float(c2._delay_ema)
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    # restore the class default so sibling arms in this worker are unaffected
    if arm in ("emapad", "simpace"):
        from sim_priority import PartAController
        cls._finish_delay = PartAController._finish_delay
    return (arm, seed, round(onv, 1))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in TEST_SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        res = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    for a, s, v in res:
        D[a][s] = v
    n_ = len(TEST_SEEDS)
    print("M4 VALUE RACE: what fills the empty pace slot? (held-out seeds 97-144, %d days)\n" % n_)
    base = sum(D["champion"].values()) / n_
    print("%-10s %-10s %-9s %-8s %s" % ("arm", "mean", "vs champ", "t", "W/T/L"))
    for a in ARMS:
        diff = [D[a][s] - D["champion"][s] for s in TEST_SEEDS]
        m = sum(diff) / n_
        sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
        tt = m / (sd_ / n_ ** 0.5) if (sd_ and a != "champion") else 0.0
        w = sum(1 for d in diff if d > 1e-9)
        ti = sum(1 for d in diff if abs(d) <= 1e-9)
        print("%-10s %-10.2f %+9.2f %+8.2f  %d/%d/%d"
              % (a, sum(D[a].values()) / n_, m, tt, w, ti, n_ - w - ti))
    print("\nship bar: t>=2 vs champion")
