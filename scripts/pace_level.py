"""pace_level -- CORRECTED pace test: physics predicts the AVERAGE pace TRAJECTORY, not per task.

Per-task wait is noise (corr ~0) -- that was never the target. The target is the LEVEL: the
day's average delay drifts up in rushes and down in lulls, and the deployed pad tracks it with a
TRAILING EMA of finished tasks (a rearview mirror -- a task finishing now started ~50 steps ago).
Question: does a PHYSICS read of current board contention predict the CURRENT average delay
better than the lagging EMA -- especially where the trajectory is turning?

Method (no planner change): bin each day into WINDOWS. Per window compute
  truth   = mean realized delay of tasks committed in the window
  ema     = the deployed trailing-EMA value in force during the window
  physics = f(mean board contention during the window)   [inflight/pickers, queue, throughput]
Averaging over a window cancels per-task noise, exposing the level. Compare window-level MAE:
lagging EMA vs contemporaneous physics (leave-one-seed-out, so physics is never fit to its own
day). Reports overall + on OPENING windows (cold EMA) + on TURNING windows (pace accelerating).

Run: SEEDS=30 BIN=40 python scripts/pace_level.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from wwm_sim.rollout import nearest_dock_dist, _manhattan
from congestion_policies import _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "30"))))
EXTRA = [int(x) for x in os.environ.get("EXTRA", "").split(",") if x]
BIN = int(os.environ.get("BIN", "40"))
NPICK = 4


class _Tracer(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.tasks = {}
        self.series = {}          # step -> (free_pk, inflight_unloaded, qlen, ema, deliv_rate)

    def act(self):
        out = super().act()
        t = int(self.timestep)
        free_pk = sum(1 for p in self.pickers if p not in self.assigned_pickers)
        inflight = sum(1 for a in self.agvs
                       if (a.busy or a in self.assigned_agvs) and not a.carrying_shelf)
        ema = float(self._delay_ema) if getattr(self, "_delay_inited", False) else 0.0
        rate = sum(1 for _t in getattr(self, "_deliv_times", []) if t - _t <= 40) / 40.0
        self.series[t] = (free_pk, inflight, len(self.env.request_queue), ema, rate)
        return out

    def _on_predict(self, shelf, now, pred_finish):
        agv = getattr(self, "_cur_agv", None)
        if agv is None:
            return
        self.tasks[shelf.id] = {"aid": agv.id, "t0": int(now), "pred": float(pred_finish),
                                "ax": agv.x, "ay": agv.y, "sx": shelf.x, "sy": shelf.y,
                                "t_end": None}


def run_seed(seed):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _Tracer(env)
    t, done = 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        for sid, _a in getattr(env, "deliveries_this_step", []):
            r = ctrl.tasks.get(sid)
            if r is not None and r["t_end"] is None:
                r["t_end"] = t
        done = all(term) or all(trunc)
    # bin tasks by commit window
    nb = STEPS // BIN
    bins = [[] for _ in range(nb)]
    for r in ctrl.tasks.values():
        if r["t_end"] is None:
            continue
        b = min(r["t0"] // BIN, nb - 1)
        bins[b].append((r["t_end"] - r["t0"]) - r["pred"])
    rows = []
    for b in range(nb):
        if not bins[b]:
            continue
        lo, hi = b * BIN, (b + 1) * BIN
        ser = [ctrl.series[t] for t in range(lo, hi) if t in ctrl.series]
        if not ser:
            continue
        arr = np.array(ser, dtype=float)
        rows.append({
            "seed": seed, "bin": b, "n": len(bins[b]),
            "truth": float(np.mean(bins[b])),
            "ema": float(np.mean(arr[:, 3])),
            "free_pk": float(np.mean(arr[:, 0])), "inflight": float(np.mean(arr[:, 1])),
            "qlen": float(np.mean(arr[:, 2])), "rate": float(np.mean(arr[:, 4])),
        })
    return rows


def main():
    allrows = []
    for s in SEEDS + EXTRA:
        r = run_seed(s)
        allrows += r
        print(f"seed {s}: {len(r)} windows, mean truth "
              f"{np.mean([x['truth'] for x in r]):+.1f}", flush=True)
    seeds = sorted({r["seed"] for r in allrows})
    def col(rows, k): return np.array([r[k] for r in rows], dtype=float)
    # feature matrix for physics: contention aggregates (contemporaneous)
    FEATS = ("inflight", "free_pk", "qlen", "rate")
    print(f"\n=== window-level corr with truth ({len(allrows)} windows, BIN={BIN}) ===")
    for k in FEATS + ("ema",):
        print(f"  {k:<9} {np.corrcoef(col(allrows, k), col(allrows,'truth'))[0,1]:+.2f}")
    # leave-one-seed-out physics regression vs the lagging EMA, at window level
    def design(rows):
        return np.c_[np.ones(len(rows)), col(rows, "inflight"), col(rows, "free_pk"),
                     col(rows, "qlen"), col(rows, "rate")]
    phys_err, ema_err, flat_err, truths, orders, emas = [], [], [], [], [], []
    for s in seeds:
        tr = [r for r in allrows if r["seed"] != s]
        te = [r for r in allrows if r["seed"] == s]
        beta, *_ = np.linalg.lstsq(design(tr), col(tr, "truth"), rcond=None)
        gmean = float(np.mean(col(tr, "truth")))
        pred = design(te) @ beta
        for r, p in zip(te, pred):
            phys_err.append(abs(r["truth"] - p))
            ema_err.append(abs(r["truth"] - r["ema"]))
            flat_err.append(abs(r["truth"] - gmean))
            truths.append(r["truth"]); orders.append(r["bin"]); emas.append(r["ema"])
    phys_err, ema_err, flat_err = map(np.array, (phys_err, ema_err, flat_err))
    orders = np.array(orders)
    print(f"\n=== window-level |error| (leave-one-seed-out) ===")
    print(f"  lagging EMA (deployed): {ema_err.mean():6.2f}")
    print(f"  physics (contention)  : {phys_err.mean():6.2f}")
    print(f"  flat global constant  : {flat_err.mean():6.2f}")
    op = orders <= 1
    print(f"\n=== OPENING windows (first 2 = cold EMA, n={int(op.sum())}) ===")
    print(f"  lagging EMA : {ema_err[op].mean():6.2f}   (reads {np.mean(np.array(emas)[op]):.1f}, "
          f"truth {np.mean(np.array(truths)[op]):+.1f})")
    print(f"  physics     : {phys_err[op].mean():6.2f}")
    # turning windows: truth rising vs the EMA (EMA below truth by >5 => pace accelerating)
    turn = (np.array(truths) - np.array(emas)) > 6
    if turn.sum():
        print(f"\n=== ACCELERATING windows (truth outruns EMA by >6, n={int(turn.sum())}) ===")
        print(f"  lagging EMA : {ema_err[turn].mean():6.2f}")
        print(f"  physics     : {phys_err[turn].mean():6.2f}")


if __name__ == "__main__":
    main()
