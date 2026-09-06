"""M4 decisive test: does the learned pace head improve VALUE, not just prediction error?

The head beat the EMA's MAE by 13.5% but failed calibration. Accuracy is not the currency --
on-time value is. This wires the trained head into the champion's deadline-feasibility estimate
(ctrl.delay_head, consumed at sim_priority.py:654) and races it against the shipped controller
on identical days.

  champion   shipped stack (live delay-EMA only)
  head       same + LightGBM pace head added to the finish estimate
Trained on seeds 1-96 (results/m4_pace_full.csv); raced on HELD-OUT seeds 97-144.
Ship rule: value gain with t>=2 (the project's standing bar).
"""
import os
import pickle
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(97, 145))                 # held out from the head's training set
MODEL = "results/m4_pace_head.pkl"


def train_head():
    import csv
    import numpy as np
    import lightgbm as lgb
    rows = list(csv.DictReader(open("results/m4_pace_full.csv")))
    for r in rows:
        for k in r:
            r[k] = float(r[k]) if r[k] not in ("", None) else 0.0
    tr = [r for r in rows if r["seed"] < 97]
    feats = sorted(k for k in rows[0] if k.startswith("f_"))
    X = np.array([[r[f] for f in feats] for r in tr])
    y = np.array([r["y"] for r in tr])
    mdl = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                            min_child_samples=20, verbose=-1)
    mdl.fit(X, y)
    with open(MODEL, "wb") as fh:
        pickle.dump({"model": mdl, "feats": feats}, fh)
    print("trained head on %d rows (seeds 1-96), %d features -> %s" % (len(tr), len(feats), MODEL))


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    if arm == "head":
        with open(MODEL, "rb") as fh:
            blob = pickle.load(fh)
        mdl, feats = blob["model"], blob["feats"]

        def head_fn(feat, _m=mdl, _f=feats):
            # the head was trained on the assembler's fleet-context keys (f_<name>)
            x = np.array([[float(feat.get(k[2:], 0.0)) for k in _f]])
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
    if not os.path.exists(MODEL):
        train_head()
    ARMS = ("champion", "head")
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    for a, s, v in rows:
        D[a][s] = v
    n_ = len(SEEDS)
    print("\nM4 VALUE AUDITION: learned pace head in the loop (held-out seeds 97-144)\n")
    base = sum(D["champion"].values()) / n_
    print("champion (EMA only)  mean %8.2f" % base)
    diff = [D["head"][s] - D["champion"][s] for s in SEEDS]
    m = sum(diff) / n_
    sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
    tt = m / (sd_ / n_ ** 0.5) if sd_ else 0.0
    wins = sum(1 for d in diff if d > 0)
    ties = sum(1 for d in diff if abs(d) < 1e-9)
    losses = sum(1 for d in diff if d < 0)
    import csv as _csv
    with open("results/m4_value_perseed.csv", "w", newline="") as _fh:
        _w = _csv.writer(_fh); _w.writerow(["seed", "champion", "head", "diff"])
        for _s in SEEDS:
            _w.writerow([_s, D["champion"][_s], D["head"][_s], round(D["head"][_s] - D["champion"][_s], 1)])
    print("per-seed: %d wins / %d ties / %d losses  (sign test on non-ties: p=%.2g)"
          % (wins, ties, losses,
             (0.5 ** (wins + losses) * 2) if (wins + losses) else 1.0))
    print("head (EMA + head)    mean %8.2f  vs champion %+7.2f  t=%+.2f  wins %d/%d"
          % (sum(D["head"].values()) / n_, m, tt, wins, n_))
    print("\nSHIP RULE: value gain at t>=2 -> %s"
          % ("SHIP the head" if tt >= 2 else ("HARMFUL, stay cut" if tt <= -2 else "flat -> stay cut")))
