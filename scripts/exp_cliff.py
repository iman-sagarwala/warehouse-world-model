"""Two experiments on the step-5/6 constants, both aimed at the same question: WHY are they needed?

A) TIER_GAP -- the makeable/doomed cliff, hardcoded at 1000 and NEVER SWEPT. It is applied at three
   sites (funnel score, `_sim_core`'s imagined task choice, picker tier), so it does not merely order
   the shortlist -- it decides what each IMAGINED robot picks up, and therefore shapes the whole
   trajectory the sequencer ranks by. Smaller gap => a rich DOOMED task can outrank a cheap makeable
   one; larger => never. This is plausibly the most consequential single constant in the system.

B) ADAPTIVE PAD -- replace the constant LOAD_TIME pad in the FUNNEL's deadline check with the live
   delay-EMA. Prior is weak: the 2026-07-22 sweep showed HAVING a pad matters (-3.27, p=0.021 when
   removed) but its SIZE is irrelevant 3..15, and an adaptive pad varies inside that range. Kept honest
   by only touching `_finish_delay` (the funnel), NOT LOAD_TIME itself -- LOAD_TIME is consumed at four
   sites and a previous attempt to split it was invalid because the hook reached only one.

Env: SEEDS, NPROC, OUT.
"""
import csv
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = int(os.environ.get("SEEDS", "120"))
NPROC = int(os.environ.get("NPROC", "8"))
OUT = os.environ.get("OUT", "results/cliff2.csv")
FLEETS = [(4, 4), (6, 6), (8, 6), (8, 8), (9, 9)]
REGIMES = ["daylist", "stream"]
ARMS = ["champion", "gap_0", "gap_3", "gap_6", "gap_10", "gap_15"]


def _cls(arm):
    import congestion_policies as cp
    C = cp._SqWidePkRateAdaptive
    if arm == "champion":
        return C
    if arm.startswith("gap_"):
        return type("_Cliff_%s" % arm, (C,), {"TIER_GAP": float(arm.split("_")[1])})

    if arm == "emapad":
        class _EmaPad(C):
            """STEP 5 ONLY: the funnel's deadline check gets the live delay-EMA. Step 6 already has it
            (`_sim_core` applies `_sim_step_bias` to every imagined completion); step 5 has nothing but
            the constant LOAD_TIME pad, so the makeable/doomed call is made on raw geometry.

            CAREFUL -- `_finish_delay` is consumed at TWO sites: the funnel score AND `fov`, the pinned
            first move handed to the sim. Since `_sim_core` then adds its own `_sim_step_bias` on top of
            `fov`, a naive override gives the first move the EMA TWICE. `_simulate_branch` is therefore
            overridden to drop `_finish_delay` from `fov`, so the change is isolated to step 5.
            (This ADDS an adaptive component alongside the constant pad rather than replacing it --
            replacing would mean touching all four LOAD_TIME sites, which is exactly the mistake that
            invalidated the 2026-07-22 rename.)"""
            def _finish_delay(self, best_r):
                return float(self._sim_delay_bias())

            def _simulate_branch(self, tup):
                _score, first_shelf, _route, _all_routes, feat = tup
                me = self._cur_agv
                self._sim_pin_agents = {me.id}
                try:                       # NB: no _finish_delay here -- the sim adds its own bias
                    fov = float(self.timestep) + float(feat["pred_finish"])
                    return self._sim_core([(me.x, me.y, first_shelf, fov)])
                finally:
                    self._sim_pin_agents = None
        return _EmaPad
    raise KeyError(arm)


def one(job):
    arm, regime, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel

    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS)
    if regime == "daylist":
        env.demand_model.seed_day_list(env, horizon=STEPS)
    else:
        env.demand_model.seed_initial(env, n=12)
    ctrl = _cls(arm)(env)
    onv, t, done = 0.0, 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return (arm, regime, agv, pk, seed, round(onv, 1))


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "regime", "agvs", "pickers", "seed", "on_time_value"])
        w.writerows(rows)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows, have = [], set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["arm"], r["regime"], int(r["agvs"]), int(r["pickers"]),
                             int(r["seed"]), float(r["on_time_value"])))
                have.add((r["arm"], r["regime"], int(r["agvs"]), int(r["pickers"]), int(r["seed"])))
    jobs = [(a, rg, ag, pk, s) for a in ARMS for rg in REGIMES for (ag, pk) in FLEETS
            for s in range(SEEDS) if (a, rg, ag, pk, s) not in have]
    print(f"cliff: {len(jobs)} runs, arms={ARMS}, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 200 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("cliff: DONE", flush=True)


if __name__ == "__main__":
    main()

