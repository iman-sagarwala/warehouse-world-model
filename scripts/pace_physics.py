"""pace_physics -- STEP 1 (offline) of the physics pace model: does mechanics beat the EMA?

The delay autopsies decomposed the ~16-step pad into: picker queueing (dominant, driven by
contention), turning (exact route geometry), small residual congestion. This script asks,
WITHOUT touching the planner: if at commit time we predict each task's delay from
    turns_realized + picker-wait-physics(contention at commit) + constant
how does the prediction error compare to the deployed trailing-EMA pad -- overall, and on the
day's OPENING commits where the EMA reads 0 (the seed-303 cold-open disease)?

Physics wait term: each in-flight unloaded task ahead of me is a claim on the picker pool.
    wait_hat = W0 + W1 * (inflight_unloaded_at_commit / n_pickers)
W0/W1 calibrated ONCE by least squares on the pick-wait segment (they are mechanism constants,
not per-day fits). Turns counted from the driven trace (route-deterministic).

Run: SEEDS=10 EXTRA=303 python scripts/pace_physics.py
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
SEEDS = list(range(int(os.environ.get("SEEDS", "10"))))
EXTRA = [int(x) for x in os.environ.get("EXTRA", "").split(",") if x]


class _Tracer(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.tasks = {}
        self.state_log = {}                 # step -> (n_free_pickers, n_inflight_unloaded, qlen)

    def act(self):
        out = super().act()
        n_free_pk = sum(1 for p in self.pickers if p not in self.assigned_pickers)
        inflight = sum(1 for a in self.agvs
                       if (a.busy or a in self.assigned_agvs) and not a.carrying_shelf)
        self.state_log[int(self.timestep)] = (n_free_pk, inflight, len(self.env.request_queue))
        return out

    def _on_predict(self, shelf, now, pred_finish):
        agv = getattr(self, "_cur_agv", None)
        if agv is None:
            return
        ema = float(self._delay_ema) if getattr(self, "_delay_inited", False) else 0.0
        self.tasks[shelf.id] = {
            "sid": shelf.id, "aid": agv.id, "t0": int(now), "pred": float(pred_finish),
            "ax": agv.x, "ay": agv.y, "sx": shelf.x, "sy": shelf.y,
            "ema_at_commit": ema, "trace": [], "t_end": None,
        }


def run_seed(seed):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _Tracer(env)
    by_aid = {a.id: a for a in ctrl.agvs}
    t, done = 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        for r in ctrl.tasks.values():
            if r["t_end"] is None:
                a = by_aid[r["aid"]]
                r["trace"].append((a.x, a.y, bool(a.carrying_shelf)))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            r = ctrl.tasks.get(sid)
            if r is not None and r["t_end"] is None:
                r["t_end"] = t
        done = all(term) or all(trunc)
    out = []
    for r in ctrl.tasks.values():
        if r["t_end"] is None:
            continue
        st = ctrl.state_log.get(r["t0"]) or (0, 0, 0)
        prev, turns, pick, moved = (r["ax"], r["ay"]), 0, 0, []
        loaded = False
        for (x, y, carry) in r["trace"][: r["t_end"] - r["t0"]]:
            if not loaded and carry:
                loaded = True
            if (x, y) != prev:
                moved.append((x - prev[0], y - prev[1]))
                if len(moved) >= 2 and moved[-1] != moved[-2]:
                    turns += 1
            elif not loaded and (x, y) == (r["sx"], r["sy"]):
                pick += 1
            prev = (x, y)
        mf = _manhattan(r["ax"], r["ay"], r["sx"], r["sy"])
        mh = nearest_dock_dist(env, r["sx"], r["sy"])
        est_wait = max(0.0, r["pred"] - mf - mh)
        arr = ctrl.state_log.get(min(r["t0"] + mf, max(ctrl.state_log) if ctrl.state_log else r["t0"]))
        arr = arr or st
        out.append({
            "seed": seed, "t0": r["t0"], "delay": (r["t_end"] - r["t0"]) - r["pred"],
            "turns": turns, "pick": pick, "est_wait": est_wait,
            "free_pk": st[0], "inflight": st[1], "qlen": st[2],
            "free_pk_arr": arr[0], "inflight_arr": arr[1], "qlen_arr": arr[2],
            "ema": r["ema_at_commit"], "order": None,
        })
    out.sort(key=lambda d: d["t0"])
    for i, d in enumerate(out):
        d["order"] = i                       # commit order within the day (0 = cold open)
    return out


def main():
    tasks = []
    for s in SEEDS + EXTRA:
        rows = run_seed(s)
        tasks += rows
        print(f"seed {s}: {len(rows)} tasks, mean delay "
              f"{np.mean([d['delay'] for d in rows]):+.1f}", flush=True)
    T = {k: np.array([d[k] for d in tasks], dtype=float)
         for k in ("delay", "turns", "pick", "est_wait", "free_pk", "inflight", "qlen",
                   "free_pk_arr", "inflight_arr", "qlen_arr", "ema", "order", "seed")}
    print("\n=== what (if anything) predicts the pick-wait segment? corr with pick ===")
    for k in ("inflight", "free_pk", "qlen", "inflight_arr", "free_pk_arr", "qlen_arr",
              "turns", "est_wait", "t0_"):
        v = T["order"] if k == "t0_" else T.get(k)
        if v is not None:
            print(f"  {k:<13} {np.corrcoef(v, T['pick'])[0, 1]:+.2f}")
    # ---- calibrate the two mechanism constants on the PICK-WAIT segment only ----
    ratio = T["inflight"] / 4.0
    A = np.c_[np.ones(len(ratio)), ratio]
    (W0, W1), *_ = np.linalg.lstsq(A, T["pick"], rcond=None)
    wait_hat = W0 + W1 * ratio
    print(f"\npicker-wait physics: wait_hat = {W0:.1f} + {W1:.1f} * (inflight/4)   "
          f"(corr {np.corrcoef(ratio, T['pick'])[0,1]:+.2f})")
    # ---- physics delay prediction (no per-day fitting): turns + wait beyond allocation + resid ----
    core = T["turns"] + np.maximum(0.0, wait_hat - T["est_wait"])
    resid = float(np.mean(T["delay"] - core))          # one global constant (standoffs etc.)
    phys = core + resid
    print(f"global residual constant: {resid:+.1f} steps (yield/crossing/dock leftovers)")
    ema_err = np.abs(T["delay"] - T["ema"])
    phys_err = np.abs(T["delay"] - phys)
    flat_err = np.abs(T["delay"] - np.mean(T["delay"]))
    print(f"\n=== per-task |error| (steps), {len(tasks)} tasks ===")
    print(f"  deployed trailing EMA : {np.mean(ema_err):6.2f}")
    print(f"  physics (turns+queue) : {np.mean(phys_err):6.2f}")
    print(f"  oracle flat constant  : {np.mean(flat_err):6.2f}   (best possible single pad)")
    op = T["order"] < 3
    print(f"\n=== COLD OPEN (first 3 commits of each day, n={int(op.sum())}) ===")
    print(f"  deployed trailing EMA : {np.mean(ema_err[op]):6.2f}   "
          f"(EMA reads {np.mean(T['ema'][op]):.1f} when truth is {np.mean(T['delay'][op]):+.1f})")
    print(f"  physics (turns+queue) : {np.mean(phys_err[op]):6.2f}")
    for s in EXTRA:
        m = T["seed"] == s
        mo = m & op
        if mo.sum():
            print(f"\n  seed {s} opening: truth {np.mean(T['delay'][mo]):+.1f}  "
                  f"EMA {np.mean(T['ema'][mo]):.1f}  physics {np.mean(phys[mo]):+.1f}")
    # drift: does physics track WITHIN-day movement better than the EMA?
    late = T["order"] >= 10
    if late.sum():
        print(f"\n=== LATE DAY (commit #10+, n={int(late.sum())}) ===")
        print(f"  deployed trailing EMA : {np.mean(ema_err[late]):6.2f}")
        print(f"  physics (turns+queue) : {np.mean(phys_err[late]):6.2f}")


if __name__ == "__main__":
    main()
