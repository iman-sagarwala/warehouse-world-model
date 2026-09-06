"""M4 value test, CORRECTED: a PER-CANDIDATE pace head (the roadmap's actual Stage-3 head).

The first value audition trained on fleet-level context only, so the head returned the same
number for every candidate at a given step -- a constant offset that cannot reorder candidates
(45/48 days came back bit-identical). This version uses the champion's own per-candidate
feature diary (ctrl.diary_features, sim_priority.py:687 -- the full assembler `feat` dict that
line 654 actually consumes), so the head can distinguish "this task will run late" from "that
one won't".

Phase 1: collect (per-candidate feat, realized delay) on seeds 1-96.
Phase 2: train LightGBM.
Phase 3: race champion vs champion+head on HELD-OUT seeds 97-144, judged on on-time value.
"""
import os
import pickle
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

TRAIN_SEEDS = list(range(1, 97))
TEST_SEEDS = list(range(97, 145))
MODEL = "results/m4_cand_head.pkl"


def collect(seed):
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    ctrl.DIARY = True                 # class default is False -> without this the diary stays empty
    ctrl.diary_features = {}
    out = []
    pend = {}
    for t in range(500):
        env.step(ctrl.act())
        for sid, (at, feat) in list(getattr(ctrl, "diary_features", {}).items()):
            if sid not in pend:
                pend[sid] = (at, {k: float(v) for k, v in feat.items()
                                  if isinstance(v, (int, float))},
                             float(feat.get("pred_finish", 0.0)))
        for _sid, _a in getattr(env, "deliveries_this_step", []):
            p = pend.pop(_sid, None)
            if p is not None:
                at, feat, pred = p
                out.append((feat, (t - at) - pred))
    return out


def race(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    if arm == "head":
        blob = pickle.load(open(MODEL, "rb"))
        mdl, feats = blob["model"], blob["feats"]

        def head_fn(feat, _m=mdl, _f=feats):
            x = np.array([[float(feat.get(k, 0.0)) for k in _f]])
            return float(_m.predict(x)[0])

        ctrl.delay_head = head_fn
    onv = 0.0
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1))


if __name__ == "__main__":
    import numpy as np
    NP = int(os.environ.get("NPROC", "8"))
    if not os.path.exists(MODEL):
        with mp.Pool(NP) as pool:
            batches = pool.map(collect, TRAIN_SEEDS)
        rows = [r for b in batches for r in b]
        feats = sorted({k for f, _ in rows for k in f})
        X = np.array([[f.get(k, 0.0) for k in feats] for f, _ in rows])
        y = np.array([d for _, d in rows])
        import lightgbm as lgb
        mdl = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=31,
                                min_child_samples=20, verbose=-1)
        mdl.fit(X, y)
        pickle.dump({"model": mdl, "feats": feats}, open(MODEL, "wb"))
        insample = float(np.abs(mdl.predict(X) - y).mean())
        print("collected %d per-candidate rows, %d features (e.g. %s)"
              % (len(rows), len(feats), feats[:8]))
        print("target: realized delay mean %+.1f sd %.1f | in-sample MAE %.2f\n"
              % (y.mean(), y.std(), insample))
    ARMS = ("champion", "head")
    jobs = [(a, s) for a in ARMS for s in TEST_SEEDS]
    with mp.Pool(NP) as pool:
        res = pool.map(race, jobs)
    D = {a: {} for a in ARMS}
    for a, s, v in res:
        D[a][s] = v
    n_ = len(TEST_SEEDS)
    diff = [D["head"][s] - D["champion"][s] for s in TEST_SEEDS]
    m = sum(diff) / n_
    sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
    tt = m / (sd_ / n_ ** 0.5) if sd_ else 0.0
    wins = sum(1 for d in diff if d > 1e-9)
    ties = sum(1 for d in diff if abs(d) <= 1e-9)
    print("M4 VALUE AUDITION v2 -- PER-CANDIDATE head (held-out seeds 97-144)\n")
    print("champion  mean %8.2f" % (sum(D["champion"].values()) / n_))
    print("head      mean %8.2f  vs champion %+7.2f  t=%+.2f" % (sum(D["head"].values()) / n_, m, tt))
    print("per-seed: %d wins / %d ties / %d losses" % (wins, ties, n_ - wins - ties))
    print("\nSHIP RULE (t>=2): %s"
          % ("SHIP" if tt >= 2 else ("HARMFUL" if tt <= -2 else "flat -> stay cut")))
