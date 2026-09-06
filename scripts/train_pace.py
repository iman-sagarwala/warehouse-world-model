"""train_pace -- the PACE MODEL: a state-conditional replacement for the sequencer's flat delay bias.

The sequencer's _sim_delay_bias currently returns ONE lagging scalar (_delay_ema, the fleet-wide
running-average delay). This trains two models that predict the CURRENT pace from live fleet state,
so the bias can ANTICIPATE (diurnal rush) and CONDITION (picker contention) instead of lagging:

  PACE-PICKER   : delay ~ picker-availability state only (free_pk_frac, busy_frac, contention, queue)
  PACE-COMBINED : PICKER + diurnal day-curve (sin_t, cos_t, day_frac) + traffic (delay_ema, deliv_rate,
                  dur_trend, dur_recent) -- the "combined for demand" model.

TARGET = realized delay (actual assign->deliver duration - empty-world pred_finish), same label the
EMA measures. STEP-LEVEL features only (the bias is applied globally, not per task).

HONEST GATE (method rule -- beat the incumbent, not just zero): the offline table reports predict-0,
predict-mean, and PREDICT-EMA (the deployed behavior) alongside the two heads. A head that does not
beat predict-EMA offline cannot help online -- report and stop. Deployment ranking is separate
(ablate_l2, paired seeds).

Run: REGIME=daylist SEEDS=120 python scripts/train_pace.py
"""
from __future__ import annotations

import os
import pickle
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
warnings.filterwarnings("ignore")

import numpy as np
import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
REGIME = os.environ.get("REGIME", "daylist")
SEEDS = list(range(int(os.environ.get("SEEDS", "120"))))
STEPS = 500

PICKER_COLS = ["free_pk_frac", "busy_frac", "n_free_pk", "n_busy_agv", "q_per_agv", "q_size"]
DIURNAL_COLS = ["sin_t", "cos_t", "day_frac"]
TRAFFIC_COLS = ["delay_ema", "deliv_rate", "dur_trend", "dur_recent"]
COMBINED_COLS = PICKER_COLS + DIURNAL_COLS + TRAFFIC_COLS
# DEADLINE-CLUSTERING cols: direct counts of near-due pending tasks (the user's idea -- measure the
# deadline bunching that causes contention, vs the time-of-day proxy the combined model uses).
DLCLUST_COLS = ["dl_soon40", "dl_soon80", "dl_soon160"]
COMBINED_DL_COLS = COMBINED_COLS + DLCLUST_COLS
# CLUSTERING-ONLY (user 2026-07-23): pure demand-timing knowledge, NO fleet physics -- when tasks
# cluster (diurnal) and how near-due they are (dl_soon*). Tests clustering alone vs the EMA.
CLUST_COLS = DIURNAL_COLS + DLCLUST_COLS
# SIM-reconstructable subset: features computable at ANY imagined future time inside _sim_core
# (no real-fleet temporal stats). Powers the per-completion pace-step bias.
SIM_COLS = ["sin_t", "cos_t", "day_frac", "q_size", "q_per_agv", "free_pk_frac"]


def collect():
    rows, labels, ema_at = [], [], []
    for seed in SEEDS:
        env = gym.make(ENV).unwrapped
        env.reset(seed=seed)
        env.request_queue = []
        env.demand_model = DemandModel(env, seed=seed)
        if REGIME == "daylist":
            env.demand_model.seed_day_list(env, horizon=STEPS)
        else:
            env.demand_model.seed_initial(env, n=12)
        ctrl = _Urg8(env)
        ctrl.DIARY = True
        t, done = 0, False
        while not done and t < STEPS:
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
                ema_at.append(feat.get("delay_ema", 0.0))   # the EMA the incumbent WOULD have used
        if seed % 20 == 0 or seed == SEEDS[-1]:
            print(f"  seed {seed}: {len(labels)} rows", flush=True)
    return rows, np.asarray(labels, float), np.asarray(ema_at, float)


def _mae(y, p):
    return float(np.mean(np.abs(y - p)))


def _rmse(y, p):
    return float(np.sqrt(np.mean((y - p) ** 2)))


def train_head(rows, y, cols, test):
    import lightgbm as lgb
    X = np.asarray([[r[c] for c in cols] for r in rows], float)
    Xtr, ytr, Xva = X[~test], y[~test], X[test]
    dtr = lgb.Dataset(Xtr, ytr, feature_name=cols)
    dva = lgb.Dataset(X[test], y[test], reference=dtr)
    params = dict(objective="regression_l1", metric=["l1", "l2"], learning_rate=0.05,
                  num_leaves=31, min_data_in_leaf=30, feature_fraction=0.9,
                  bagging_fraction=0.9, bagging_freq=1, verbose=-1)
    model = lgb.train(params, dtr, num_boost_round=2000, valid_sets=[dva], valid_names=["val"],
                      callbacks=[lgb.early_stopping(80, verbose=False)])
    return model, model.predict(Xva, num_iteration=model.best_iteration)


def main():
    print(f"REGIME={REGIME}  SEEDS={len(SEEDS)}")
    rows, y, ema = collect()
    print(f"\ncollected {len(y)} rows; realized delay mean {y.mean():.1f} std {y.std():.1f} "
          f"[{y.min():.0f}, {y.max():.0f}]")
    n = len(y)
    test = (np.arange(n) % 5 == 0)                     # 20% holdout
    yva = y[test]

    mp, pp = train_head(rows, y, PICKER_COLS, test)
    mc, pc = train_head(rows, y, COMBINED_COLS, test)
    ms, ps = train_head(rows, y, SIM_COLS, test)
    mcd, pcd = train_head(rows, y, COMBINED_DL_COLS, test)
    mcl, pcl = train_head(rows, y, CLUST_COLS, test)

    base0 = np.zeros_like(yva)
    basemean = np.full_like(yva, y[~test].mean())
    baseema = ema[test]                                # THE INCUMBENT: predict the live flat EMA

    def rowfmt(name, p):
        return f"  {name:<22}{_mae(yva, p):>9.2f}{_rmse(yva, p):>9.2f}"

    print("\n--- OFFLINE DELAY PREDICTION (20% holdout) ---")
    print(f"  {'model':<22}{'MAE':>9}{'RMSE':>9}")
    print(rowfmt("predict 0", base0))
    print(rowfmt("predict mean", basemean))
    print(rowfmt("predict EMA (incumbent)", baseema))
    print(rowfmt("PACE-picker", pp))
    print(rowfmt("PACE-combined", pc))
    print(rowfmt("PACE-sim (per-step)", ps))
    print(rowfmt("PACE-comb+DEADLINE-CLUST", pcd))
    print(rowfmt("PACE-clustering-ONLY", pcl))
    imae = _mae(yva, baseema)
    cmae = _mae(yva, pc)
    print(f"\n  vs incumbent EMA (MAE {imae:.2f}):  picker {100*(imae-_mae(yva,pp))/imae:+.1f}%   "
          f"combined {100*(imae-cmae)/imae:+.1f}%   sim {100*(imae-_mae(yva,ps))/imae:+.1f}%   "
          f"comb+dl {100*(imae-_mae(yva,pcd))/imae:+.1f}%")
    print(f"  comb+dl vs comb (does deadline-clustering add over time-of-day?): "
          f"{100*(cmae-_mae(yva,pcd))/cmae:+.2f}% MAE")
    for name, m, cols in (("picker", mp, PICKER_COLS), ("combined", mc, COMBINED_COLS),
                          ("sim", ms, SIM_COLS), ("comb+dl", mcd, COMBINED_DL_COLS)):
        imp = sorted(zip(cols, m.feature_importance(importance_type="gain")), key=lambda t: -t[1])
        tot = sum(v for _, v in imp) or 1.0
        print(f"  {name} top features (gain%): " + ", ".join(f"{c}={100*v/tot:.0f}" for c, v in imp[:6]))

    os.makedirs("results", exist_ok=True)
    with open("results/pace_picker.pkl", "wb") as f:
        pickle.dump({"model": mp, "cols": PICKER_COLS}, f)
    with open("results/pace_combined.pkl", "wb") as f:
        pickle.dump({"model": mc, "cols": COMBINED_COLS}, f)
    with open("results/pace_sim.pkl", "wb") as f:
        pickle.dump({"model": ms, "cols": SIM_COLS}, f)
    with open("results/pace_comb_dl.pkl", "wb") as f:
        pickle.dump({"model": mcd, "cols": COMBINED_DL_COLS}, f)
    with open("results/pace_clust.pkl", "wb") as f:
        pickle.dump({"model": mcl, "cols": CLUST_COLS}, f)
    print("\nwrote pace_picker/combined/sim/comb_dl/clust .pkl")


if __name__ == "__main__":
    main()
