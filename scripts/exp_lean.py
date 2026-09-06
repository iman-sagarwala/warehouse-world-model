"""LEAN CHAMPION vs CHAMPION -- does the funnel's tier score do anything, and does dropping it cost time?

Measures BOTH: (a) wall-clock per run, (b) on-time value. Paired by seed, exogenous demand so both arms
face bit-identical orders.
Env: SEEDS, NPROC, OUT.
"""
import csv
import os
import sys
import time
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = int(os.environ.get("SEEDS", "120"))
NPROC = int(os.environ.get("NPROC", "8"))
OUT = os.environ.get("OUT", "results/lean.csv")
FLEETS = [(4, 4), (6, 6), (8, 6), (8, 8), (9, 9)]
REGIMES = ["daylist", "stream"]
ARMS = ["champion", "lean", "mkonly"]


def one(job):
    arm, regime, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp

    cls = {"champion": cp._SqWidePkRateAdaptive, "lean": cp._SqWideLean, "mkonly": cp._SqWideMakeableOnly}[arm]
    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS)
    if regime == "daylist":
        env.demand_model.seed_day_list(env, horizon=STEPS)
    else:
        env.demand_model.seed_initial(env, n=12)
    ctrl = cls(env)
    t0 = time.perf_counter()
    onv, t, done = 0.0, 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return (arm, regime, agv, pk, seed, round(onv, 1), round(time.perf_counter() - t0, 3))


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "regime", "agvs", "pickers", "seed", "on_time_value", "secs"])
        w.writerows(rows)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows, have = [], set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["arm"], r["regime"], int(r["agvs"]), int(r["pickers"]),
                             int(r["seed"]), float(r["on_time_value"]), float(r["secs"])))
                have.add((r["arm"], r["regime"], int(r["agvs"]), int(r["pickers"]), int(r["seed"])))
    jobs = [(a, rg, ag, pk, s) for a in ARMS for rg in REGIMES for (ag, pk) in FLEETS
            for s in range(SEEDS) if (a, rg, ag, pk, s) not in have]
    print(f"lean: {len(jobs)} runs, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 200 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("lean: DONE", flush=True)


if __name__ == "__main__":
    main()

