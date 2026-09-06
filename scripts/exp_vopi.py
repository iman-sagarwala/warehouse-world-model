"""CLEAN VoPI (value of perfect demand information) — day-list minus stream, WORKLOAD-MATCHED.

THE PROBLEM (found 2026-07-30): `seed_day_list()`'s docstring bills day-list minus stream as the
perfect-foresight bound on what any demand predictor could ever buy. But the two regimes are NOT
workload-matched: stream calls `seed_initial(n=12)` (a warm start so robots aren't idle on a cold
start) and day-list never does. Verified: `daylist == stream(warm=0)` generates BIT-IDENTICAL order
sets, so the arrival process and every deadline agree -- the sole difference is those 12 extra orders
(+25% orders, +33% value on seed 0). The quoted VoPI therefore mixes INFORMATION with LOAD.

THE FIX — four arms, so the two effects separate:
    daylist_w0  vs stream_w0   -> CLEAN VoPI (bit-identical orders, only VISIBILITY differs)
    daylist_w12 vs stream_w12  -> CLEAN VoPI at the higher workload (matched warm start)
    daylist_w0  vs stream_w12  -> the CONTAMINATED number currently in the docs
Difference between the clean and contaminated figures = how much of the claimed foresight value was
really just a workload gap.

Env: FLEETS, SEEDS, NPROC, OUT.  Writes long-format CSV (arm,agvs,pickers,seed,on_time_value).
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
OUT = os.environ.get("OUT", "results/vopi_clean.csv")
FLEETS = [(4, 4), (6, 6), (8, 8), (8, 4), (4, 8), (9, 9)]
ARMS = ["daylist_w0", "daylist_w12", "stream_w0", "stream_w12"]


def one(job):
    arm, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    from congestion_policies import _SqWidePkRateAdaptive

    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed)
    env.demand_model = dm
    warm = 12 if arm.endswith("w12") else 0
    if warm:
        dm.seed_initial(env, n=warm)            # SAME warm start on both sides -> matched workload
    if arm.startswith("daylist"):
        dm.seed_day_list(env, horizon=STEPS)    # whole day visible at t=0; step() is a no-op after
    ctrl = _SqWidePkRateAdaptive(env)
    onv, t, done = 0.0, 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return (arm, agv, pk, seed, round(onv, 1))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    have = set()
    rows = []
    if os.path.exists(OUT):                      # seed-level resume
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["arm"], int(r["agvs"]), int(r["pickers"]), int(r["seed"]),
                             float(r["on_time_value"])))
                have.add((r["arm"], int(r["agvs"]), int(r["pickers"]), int(r["seed"])))
    jobs = [(a, agv, pk, s) for a in ARMS for (agv, pk) in FLEETS for s in range(SEEDS)
            if (a, agv, pk, s) not in have]
    print(f"vopi: {len(jobs)} runs to do ({len(have)} already banked), nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 50 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("vopi: DONE", flush=True)


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "agvs", "pickers", "seed", "on_time_value"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
