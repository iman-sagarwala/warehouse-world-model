"""The last open liveness defect: the floor has ZERO spare storage slots.

Diagnosed 2026-08-24. The layout puts a pod on every non-highway cell and setup_bays then
strips exactly the charger cells and marks them keepout -- so usable drop slots == pods. An
AGV holding a pod can find every legal slot occupied and wedge. It bites on one live-stream
day (seed 125: two carriers frozen for the last 100 steps, 574 of 576 benchmark runs clean).

This sweeps the amount of slack. The world-constant change is cheap; the question is whether
it costs value, because emptying slots also removes pods from the demand universe.

  arms: spare fraction 0% (control, the shipped floor) / 2% / 5%
  seeds: 97-144 live-stream (the held-out block, which contains the failing seed 125)

Outputs results/spare_slots.csv + a printed paired table.
"""
import csv
import io
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = [int(x) for x in os.environ.get("SEEDS", ",".join(str(i) for i in range(97, 145))).split(",")]
# -1.0 = legacy floor (pre-bug-fix control); 0.0 = bays genuinely pod-free; >0 = extra slack
FRACS = [float(x) for x in os.environ.get("FRACS", "-1.0,0.0,0.02,0.05").split(",")]
REGIME = os.environ.get("REGIME", "stream")
OUT = os.environ.get("OUT", "results/spare_slots.csv")
FIELDS = ["frac", "seed", "onv", "delivered", "frozen", "stranded", "spare_cells"]


def one(job):
    frac, seed = job
    import gymnasium as gym
    import numpy as np
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import importlib.util
    spec = importlib.util.spec_from_file_location("m3b", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
    m3b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3b)

    os.environ["M3SPC"] = "1500"
    stream = (REGIME == "stream")
    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    m3b.setup_bays(env)
    if frac < 0:
        # LEGACY control: reproduce the pre-2026-09-06 world, in which _recalc_grid restored the
        # bay pods on step 1, so the floor carried 180 pods for 175 legal drop cells.
        env._removed_shelf_ids = set()
        spare = set()
    else:
        spare = m3b.setup_spare_slots(env, frac)          # <- the only difference between arms
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    drop = set(env._charger_bay_ids) | set(getattr(env, "_spare_slot_ids", ()))
    dm.shelfs = [s for s in dm.shelfs if s.id not in drop]
    env.demand_model = dm
    n = dm.warm_start_n()
    if not stream:
        dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    for k, v in dict(picker_service_steps=8, station_service_steps=6, station_headway=True,
                     station_exit_priority=True, free_pod_return=True, picker_free_move="committed",
                     picker_final_step=True, station_side_keepout=True, keepout_top=True,
                     station_divert=True, swap_return_drop=True, picker_swap=True,
                     picker_swap_squat=True, agv_free_move=True, slot_divert=True,
                     picker_reelect="progress", clash_sim=True, clash_hysteresis=20).items():
        setattr(env, k, v)
    ctrl, bc = m3b.make_controller("m3", env)
    rng = np.random.RandomState(7000 + seed)
    for a in env.agents:
        bc.battery.level[a.id] = float(rng.uniform(0.15, 1.0))

    onv, delivered, hist = 0.0, 0, []
    for t in range(STEPS):
        if stream:
            dm.step(env, t)
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        delivered += len(getattr(env, "deliveries_this_step", []))
        if t >= STEPS - 100:
            hist.append([((a.x, a.y), getattr(a, "carrying_shelf", None) is not None)
                         for a in env.agents])
    frozen = 0                    # same audit definition as exp_m5_bench
    if len(hist) >= 100:
        for i in range(len(env.agents)):
            if all(h[i][1] for h in hist) and len({h[i][0] for h in hist}) == 1:
                frozen += 1
    bat = bc.battery
    stranded = sum(1 for a in env.agents if bat.level.get(a.id, 1.0) <= 0.02)
    return dict(frac=frac, seed=seed, onv=round(onv, 1), delivered=delivered,
                frozen=frozen, stranded=stranded, spare_cells=len(spare))


if __name__ == "__main__":
    jobs = [(f, s) for f in FRACS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    D = {f: {} for f in FRACS}
    for r in rows:
        D[r["frac"]][r["seed"]] = r
    n = len(SEEDS)
    base = FRACS[0]
    print("SPARE STORAGE SLOTS -- %s days, %d paired seeds\n" % (REGIME, n))
    print("%-8s %9s %9s %10s %8s %9s %9s"
          % ("spare", "cells", "value", "vs base", "t", "frozen", "stranded"))
    for f in FRACS:
        vals = [D[f][s]["onv"] for s in SEEDS]
        diff = [D[f][s]["onv"] - D[base][s]["onv"] for s in SEEDS]
        m = sum(diff) / n
        sd = st.pstdev(diff) * (n / (n - 1)) ** 0.5 if n > 1 else 0.0
        tt = m / (sd / n ** 0.5) if (sd and f != base) else 0.0
        name = "legacy" if f < 0 else "%.0f%%" % (100 * f)
        print("%-8s %9d %9.2f %+10.2f %+8.2f %9d %9d"
              % (name, D[f][SEEDS[0]]["spare_cells"], sum(vals) / n, m, tt,
                 sum(D[f][s]["frozen"] for s in SEEDS),
                 sum(D[f][s]["stranded"] for s in SEEDS)))
    bad = sorted({s for f in FRACS for s in SEEDS if D[f][s]["frozen"]})
    print("\nseeds with a frozen carrier in ANY arm: %s" % (bad or "none"))
    for s in bad:
        print("  seed %-4d " % s + "  ".join(
            "%s->%d frozen" % ("legacy" if f < 0 else "%.0f%%" % (100 * f), D[f][s]["frozen"])
            for f in FRACS))
    print("\nwrote", OUT)
