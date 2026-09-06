"""Train TWO delay heads from one collection and compare them.

  BASELINE head  (delay_head.pkl)     -> the existing static-snapshot features. Already accurate
                                          on AVERAGE (de-biases the rollout's optimistic finish).
  VARIANCE head  (delay_head_var.pkl) -> baseline features PLUS live congestion features:
      temporal (updating every step): delay_ema, dur_recent, dur_trend, deliv_rate
      normalized (size/charger-agnostic): busy_frac, free_pk_frac, q_per_agv, local_density, path_stretch
    The point is to capture PER-TASK VARIANCE -- which task is about to hit a jam -- by watching
    congestion PILE UP in this specific sim, not just the population-average delay.

Target = delay (actual_finish - pred_finish). Both heads trained to plateau (early stopping).
Compare on MAE, RMSE (variance-sensitive), and TAIL-RMSE (rows with delay > median = the jams).
If the variance head beats the baseline on RMSE/tail, the congestion features carry the tail signal.
Run: python scripts/train_variance_head.py     (seeds via SEEDS env, default 100)
"""
from __future__ import annotations

import os
import pickle
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import numpy as np
import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values
from sim_priority import PartAController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
N_SEEDS = int(os.environ.get("SEEDS", "100"))
SEEDS = list(range(N_SEEDS))

BASE_COLS = ["pred_finish", "my_arrival", "dock", "picker_eta", "my_wait",
             "n_busy_agv", "n_free_pk", "q_size", "value", "dl_slack"]
CONG_COLS = ["delay_ema", "dur_recent", "dur_trend", "deliv_rate", "busy_frac",
             "free_pk_frac", "q_per_agv", "local_density", "path_stretch"]
VAR_COLS = BASE_COLS + CONG_COLS

DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def collect():
    rows, labels = [], []
    for seed in SEEDS:
        env = gym.make(ENV).unwrapped
        env.reset(seed=seed)
        attach_deadlines(env, DL)
        attach_values(env, VL)
        ctrl = PartAController(env)
        ctrl.DIARY = True
        t = 0
        done = False
        while not done and t < 500:
            env.step(ctrl.act())
            t += 1
            for sid, _a in getattr(env, "deliveries_this_step", []):
                entry = ctrl.diary_features.pop(sid, None)
                if entry is None:
                    continue
                assign_step, feat = entry
                delay = (t - assign_step) - feat["pred_finish"]
                rows.append(feat)
                labels.append(delay)
        if seed % 10 == 0 or seed == SEEDS[-1]:
            print(f"  seed {seed}: {len(labels)} rows so far", flush=True)
    return rows, np.array(labels, dtype=float)


def _mae(y, p):
    return float(np.mean(np.abs(y - p)))


def _rmse(y, p):
    return float(np.sqrt(np.mean((y - p) ** 2)))


def train_head(X, y, cols, test):
    import lightgbm as lgb
    Xtr, ytr, Xva, yva = X[~test], y[~test], X[test], y[test]
    dtr = lgb.Dataset(Xtr, ytr, feature_name=cols)
    dva = lgb.Dataset(Xva, yva, reference=dtr)
    params = dict(objective="regression_l1", metric=["l1", "l2"], learning_rate=0.05,
                  num_leaves=31, min_data_in_leaf=20, feature_fraction=0.9,
                  bagging_fraction=0.9, bagging_freq=1, verbose=-1)
    model = lgb.train(params, dtr, num_boost_round=3000, valid_sets=[dva],
                      valid_names=["val"],
                      callbacks=[lgb.early_stopping(80, verbose=False)])
    best = model.best_iteration
    pred = model.predict(Xva, num_iteration=best)
    return model, best, pred, yva


def main():
    rows, y = collect()
    print(f"\ncollected {len(y)} rows over {len(SEEDS)} seeds; "
          f"delay mean {y.mean():.1f} std {y.std():.1f} min {y.min():.0f} max {y.max():.0f}")

    Xb = np.array([[r[c] for c in BASE_COLS] for r in rows], dtype=float)
    Xv = np.array([[r[c] for c in VAR_COLS] for r in rows], dtype=float)
    n = len(y)
    test = (np.arange(n) % 5 == 0)
    med = float(np.median(y[test]))          # median delay on the test set -> tail split

    mb, bb, pb, yva = train_head(Xb, y, BASE_COLS, test)
    mv, bv, pv, _ = train_head(Xv, y, VAR_COLS, test)

    tail = yva > med
    formula = np.zeros_like(yva)
    mean_pred = np.full_like(yva, y[~test].mean())

    def row(name, pred):
        return (name, _mae(yva, pred), _rmse(yva, pred), _rmse(yva[tail], pred[tail]))

    table = [row("formula (predict 0)", formula),
             row("mean (predict avg)", mean_pred),
             row("BASELINE head", pb),
             row("VARIANCE head", pv)]

    print("\n--- HEAD COMPARISON (validation set) ---")
    print(f"  {'model':<24}{'MAE':>9}{'RMSE':>9}{'tail-RMSE':>11}")
    for name, mae, rmse, trmse in table:
        print(f"  {name:<24}{mae:>9.2f}{rmse:>9.2f}{trmse:>11.2f}")
    print(f"\n  variance vs baseline:  MAE {100*(table[2][1]-table[3][1])/table[2][1]:+.1f}%   "
          f"RMSE {100*(table[2][2]-table[3][2])/table[2][2]:+.1f}%   "
          f"tail-RMSE {100*(table[2][3]-table[3][3])/table[2][3]:+.1f}%")
    print(f"  (plateau: baseline={bb} rounds, variance={bv} rounds; tail split at delay>{med:.0f})")

    import lightgbm as lgb  # noqa: F401  (for gain importances)
    imp = sorted(zip(VAR_COLS, mv.feature_importance(importance_type="gain")), key=lambda t: -t[1])
    tot = sum(v for _, v in imp) or 1.0
    print("  variance-head top features (gain%):",
          ", ".join(f"{c}={100*v/tot:.0f}" for c, v in imp[:7]))

    os.makedirs("results", exist_ok=True)
    with open("results/delay_head.pkl", "wb") as f:
        pickle.dump({"model": mb, "cols": BASE_COLS, "best_iteration": bb}, f)
    with open("results/delay_head_var.pkl", "wb") as f:
        pickle.dump({"model": mv, "cols": VAR_COLS, "best_iteration": bv}, f)
    print("\nwrote results/delay_head.pkl (baseline) and results/delay_head_var.pkl (variance)")


if __name__ == "__main__":
    main()
