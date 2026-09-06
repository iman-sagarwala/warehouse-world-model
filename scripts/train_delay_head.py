"""Train the DELAY HEAD (Stage 3, learned): predict the congestion delay the rollout is blind to.

Pipeline:
  1. Run Part A with DIARY on over many seeds. At each COMMIT we logged the empty-world
     predicted finish + congestion features; at each DELIVERY we now know the ACTUAL finish.
     label = actual_finish - pred_finish = the delay the traffic-blind rollout missed.
  2. Train a LightGBM regressor: features -> delay. Boost UNTIL THE VALIDATION ERROR PLATEAUS
     (early stopping), not a fixed round count, so we stop when MAE/RMSE stop improving.
  3. Report validation MAE *and* RMSE vs the baselines it must beat:
       * "formula" = predict delay 0 (what the rollout implicitly assumes),
       * "mean"    = predict the average delay (a constant — beating THIS proves the FEATURES help).
     Ship gate (plan): >= 15% better than the formula AND uses features (beats mean).
  4. Save the model to results/delay_head.pkl for wiring into Part A.
Run: python scripts/train_delay_head.py
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
SEEDS = list(range(30))
COLS = ["pred_finish", "my_arrival", "dock", "picker_eta", "my_wait",
        "n_busy_agv", "n_free_pk", "q_size", "value", "dl_slack"]
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
                actual_finish = t - assign_step
                delay = actual_finish - feat["pred_finish"]   # what the rollout missed
                rows.append([feat[c] for c in COLS])
                labels.append(delay)
        print(f"  seed {seed}: {len(labels)} rows so far", flush=True)
    return np.array(rows, dtype=float), np.array(labels, dtype=float)


def _mae(y, p):
    return float(np.mean(np.abs(y - p)))


def _rmse(y, p):
    return float(np.sqrt(np.mean((y - p) ** 2)))


def main():
    import lightgbm as lgb

    X, y = collect()
    print(f"\ncollected {len(y)} (task) rows; delay mean {y.mean():.1f} std {y.std():.1f} "
          f"min {y.min():.0f} max {y.max():.0f}")

    n = len(y)
    idx = np.arange(n)
    # deterministic split (no RNG needed): every 5th row -> validation/test
    test = idx % 5 == 0
    Xtr, ytr, Xva, yva = X[~test], y[~test], X[test], y[test]

    # Train until the validation error PLATEAUS. objective=L1 optimises MAE directly; we
    # record both L1 (MAE) and L2 -> RMSE each round and early-stop when val L1 stops
    # improving for `stopping_rounds`. best_iteration = where the plateau began.
    dtr = lgb.Dataset(Xtr, ytr, feature_name=COLS)
    dva = lgb.Dataset(Xva, yva, reference=dtr)
    params = dict(objective="regression_l1", metric=["l1", "l2"], learning_rate=0.05,
                  num_leaves=31, min_data_in_leaf=20, feature_fraction=0.9,
                  bagging_fraction=0.9, bagging_freq=1, verbose=-1)
    evals = {}
    model = lgb.train(
        params, dtr, num_boost_round=3000, valid_sets=[dtr, dva],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(80, verbose=False), lgb.record_evaluation(evals)],
    )
    best = model.best_iteration
    pred = model.predict(Xva, num_iteration=best)

    # --- plateau curve: val MAE at checkpoints, to SHOW it flattened ---
    val_l1 = evals["val"]["l1"]
    val_l2 = evals["val"]["l2"]
    print(f"\n--- training curve (val MAE / RMSE by round; early-stopped at {best}) ---")
    marks = [r for r in (1, 10, 25, 50, 100, 150, 200, 300, 500, best)
             if r <= len(val_l1)]
    seen = set()
    for r in marks:
        if r in seen:
            continue
        seen.add(r)
        tag = "  <- plateau (best)" if r == best else ""
        print(f"  round {r:>4}: MAE {val_l1[r - 1]:.2f}  RMSE {np.sqrt(val_l2[r - 1]):.2f}{tag}")

    mae_head, rmse_head = _mae(yva, pred), _rmse(yva, pred)
    mae_formula, rmse_formula = _mae(yva, 0.0), _rmse(yva, 0.0)     # rollout's implicit "delay=0"
    mae_mean, rmse_mean = _mae(yva, ytr.mean()), _rmse(yva, ytr.mean())  # constant avg delay

    print("\n--- DELAY HEAD accuracy (validation set) ---")
    print(f"  {'model':<26}{'MAE':>8}{'RMSE':>8}")
    print(f"  {'formula (predict 0 delay)':<26}{mae_formula:>8.2f}{rmse_formula:>8.2f}")
    print(f"  {'mean (predict avg delay)':<26}{mae_mean:>8.2f}{rmse_mean:>8.2f}")
    print(f"  {'HEAD (LightGBM)':<26}{mae_head:>8.2f}{rmse_head:>8.2f}")
    print(f"\n  head beats formula: MAE {100*(mae_formula-mae_head)/mae_formula:+.1f}%  "
          f"RMSE {100*(rmse_formula-rmse_head)/rmse_formula:+.1f}%   (ship gate: >= 15%)")
    print(f"  head beats mean   : MAE {100*(mae_mean-mae_head)/mae_mean:+.1f}%  "
          f"RMSE {100*(rmse_mean-rmse_head)/rmse_mean:+.1f}%   (proves it uses the features)")

    imp = sorted(zip(COLS, model.feature_importance(importance_type="gain")),
                 key=lambda t: -t[1])
    tot = sum(v for _, v in imp) or 1.0
    print("  top features (gain%):",
          ", ".join(f"{c}={100*v/tot:.0f}" for c, v in imp[:5]))

    os.makedirs("results", exist_ok=True)
    with open("results/delay_head.pkl", "wb") as f:
        pickle.dump({"model": model, "cols": COLS, "best_iteration": best}, f)
    print("\nwrote results/delay_head.pkl")


if __name__ == "__main__":
    main()
