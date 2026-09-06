"""M4 GATE: three pace predictors, one bar. Predict each task's realized DELAY at assignment.

  ema      the shipped formula: live EMA of recent realized delays (the incumbent)
  learned  LightGBM on the state-assembler's fleet features (the roadmap's Stage-3 head)
  simpace  the user's MPC-style arm: fork the warehouse every 50 steps, run 50 imagined steps,
           read the fork's EMA at the end -- "measure the pace in imagination", no training
GATE (pre-committed): a challenger ships only if test-MAE beats the EMA by >=15% AND its
calibration slope is sane (0.7-1.3). Wave regime, champion stack, 24 collect seeds.
"""
import copy
import csv
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = ([int(x) for x in os.environ["SEEDLIST"].split(",")] if os.environ.get("SEEDLIST")
         else list(range(1, 17)) + list(range(73, 81)))
TEST = (set(int(x) for x in os.environ["TESTSEEDS"].split(","))
        if os.environ.get("TESTSEEDS") else set(range(73, 81)))
FORKS = os.environ.get("FORKS", "1") == "1"
OUT = os.environ.get("OUT", "results/m4_pace_data.csv")


def one(seed):
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    rows = []
    recorded = {}
    simpace, simpace_ok = 0.0, False
    for t in range(500):
        if FORKS and t > 0 and t % 50 == 0:
            env2, c2 = copy.deepcopy((env, ctrl))
            for _h in range(50):
                env2.step(c2.act())
            if getattr(c2, "_delay_inited", False):
                simpace, simpace_ok = float(c2._delay_ema), True
        env.step(ctrl.act())
        for sid, at_pred in list(getattr(ctrl, "_pred_by_sid", {}).items()):
            if sid not in recorded:
                ctx = dict(getattr(ctrl, "_pace_ctx", {}) or {})
                recorded[sid] = dict(
                    at=at_pred[0], pred=at_pred[1],
                    ema=(float(ctrl._delay_ema) if getattr(ctrl, "_delay_inited", False) else 0.0),
                    sim=(simpace if simpace_ok else 0.0),
                    ctx={k: float(v) for k, v in ctx.items()
                         if isinstance(v, (int, float))})
        for _sid, _a in getattr(env, "deliveries_this_step", []):
            r = recorded.get(_sid)
            if r is not None and "y" not in r:
                r["y"] = (t - r["at"]) - r["pred"]
    for sid, r in recorded.items():
        if "y" in r:
            row = dict(seed=seed, ema=r["ema"], sim=r["sim"], y=r["y"])
            row.update({("f_" + k): v for k, v in r["ctx"].items()})
            rows.append(row)
    return rows


if __name__ == "__main__":
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        all_rows = [r for rr in pool.map(one, SEEDS) for r in rr]
    keys = sorted({k for r in all_rows for k in r})
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(all_rows)
    print("collected %d completed-task rows -> %s\n" % (len(all_rows), OUT))

    import numpy as np
    feats = [k for k in keys if k.startswith("f_")]
    tr = [r for r in all_rows if r["seed"] not in TEST]
    te = [r for r in all_rows if r["seed"] in TEST]
    ytr = np.array([r["y"] for r in tr]); yte = np.array([r["y"] for r in te])
    Xtr = np.array([[r.get(f, 0.0) for f in feats] for r in tr])
    Xte = np.array([[r.get(f, 0.0) for f in feats] for r in te])
    try:
        import lightgbm as lgb
        mdl = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                                min_child_samples=20, verbose=-1)
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        mdl = HistGradientBoostingRegressor(max_iter=300)
    mdl.fit(Xtr, ytr)
    preds = {
        "zero (no correction)": np.zeros(len(te)),
        "ema (shipped)": np.array([r["ema"] for r in te]),
        "learned head": mdl.predict(Xte),
    }
    if FORKS:                      # never score the sim arm when forks were disabled (all zeros)
        preds["simpace (fork)"] = np.array([r["sim"] for r in te])
    else:
        print("(forks OFF this run -- sim-pace arm not evaluated)")
    print("test rows: %d   realized delay: mean %+.1f  sd %.1f\n" % (len(te), yte.mean(), yte.std()))
    base_mae = float(np.abs(preds["ema (shipped)"] - yte).mean())
    print("%-22s %-8s %-10s %s" % ("predictor", "MAE", "vs EMA", "calibration slope"))
    for name, p in preds.items():
        mae = float(np.abs(p - yte).mean())
        sl = float(np.polyfit(p, yte, 1)[0]) if p.std() > 1e-9 else float("nan")
        imp = 100.0 * (base_mae - mae) / base_mae
        print("%-22s %-8.2f %+8.1f%%  %.2f" % (name, mae, imp, sl))
    print("\nGATE: challenger ships only if >=15%% better MAE than EMA AND slope in 0.7-1.3.")
