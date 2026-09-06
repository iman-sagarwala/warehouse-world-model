"""Two mechanisms, one harness, 120 seeds each.

A) PICKER-SIDE SEQUENCER (`PK_SEQ_DEPTH` in {0,2,5}). The AGV side screens with a formula then
   re-simulates the finalists; the picker side has only ever had a better score and no rollout. That
   asymmetry points away from the measured bottleneck -- pickers are the binding constraint
   (free-picker ceiling +11..22). Depth 0 is the control and MUST tie the champion exactly.

B) DEFERRED COMMITMENT (`DEFER_W`, `DEFER_M`). Only a robot free RIGHT NOW can be given a task, so a
   badly placed free robot always beats a well-placed one freeing in 3 steps. The rollout already
   knows when everyone frees; the assignment loop just cannot say "wait". Four (W, M) points.

Env: SEEDS, NPROC, OUT, ARMS, REGIMES.  CSV: arm,regime,agvs,pickers,seed,on_time_value
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
OUT = os.environ.get("OUT", "results/pkseq_defer.csv")
FLEETS = [(4, 4), (6, 6), (8, 8), (4, 8), (8, 4), (9, 9)]
REGIMES = os.environ.get("REGIMES", "daylist,stream").split(",")
ARMS = os.environ.get(
    "ARMS", "champion,pkseq0,pkseq2,pkseq5,defer_a,defer_b,defer_c,defer_d").split(",")


def _cls(arm):
    import congestion_policies as cp
    return {"champion": cp._SqWidePkRateAdaptive,
            "pkseq0": cp._SqWidePkSeq0, "pkseq2": cp._SqWidePkSeq2, "pkseq5": cp._SqWidePkSeq5,
            "pkwait5": cp._SqWidePkWait5, "pkwait10": cp._SqWidePkWait10,
            "honestpin": cp._SqWideHonestPin, "claimed": cp._SqWideClaimedPicker,
            "defer_a": cp._SqWideDeferA, "defer_b": cp._SqWideDeferB,
            "defer_c": cp._SqWideDeferC, "defer_d": cp._SqWideDeferD}[arm]


def one(job):
    arm, regime, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel

    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
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
    print(f"pkseq_defer: {len(jobs)} runs, arms={ARMS}, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 100 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("pkseq_defer: DONE", flush=True)


if __name__ == "__main__":
    main()

