"""FREEZE CHECK -- re-validate every shipped M1 knob decision under EXOGENOUS demand, then lock the table.

WHY: the knob sweeps ran before the endogenous-demand bug was found. Two policies on one seed shared
arrival counts, times and value draws, but ~78% of orders landed on DIFFERENT shelves, so comparisons
were only PARTIALLY paired and the reported error bars are slightly optimistic. The effects at stake
(t=-16.7, t=-30.6) are far too large for that to flip them -- this run is to confirm, not to correct,
and to let the paper say the table was verified under fully-paired demand.

Each arm changes ONE knob away from the shipped champion; the shipped value should win (or tie) each time.
  urg8all / urg0all : does the REGIME RULE (0 daylist / 8 stream) still beat a single global value?
  alpha4 / alpha6   : is RATE_ALPHA=5 still the peak?
  seq3              : is SEQ_DEPTH=5 still better than 3?
  wsync015          : is W_SYNC=0.3 still >= its closest rival?

Env: SEEDS, NPROC, OUT.  CSV: arm,regime,agvs,pickers,seed,on_time_value
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
OUT = os.environ.get("OUT", "results/freeze_check.csv")
FLEETS = [(4, 4), (6, 6), (8, 8)]
REGIMES = ["daylist", "stream"]
ARMS = ["champion", "urg8all", "urg0all", "alpha4", "alpha6", "seq3", "wsync015"]


def _cls(arm):
    import congestion_policies as cp
    C = cp._SqWidePkRateAdaptive
    if arm == "champion":
        return C
    if arm == "urg8all":
        return type("_Frz_urg8", (C,), {"URG_W_DAYLIST": 8.0, "URG_W_STREAM": 8.0})
    if arm == "urg0all":
        return type("_Frz_urg0", (C,), {"URG_W_DAYLIST": 0.0, "URG_W_STREAM": 0.0})
    if arm == "alpha4":
        return type("_Frz_a4", (C,), {"RATE_ALPHA": 4.0})
    if arm == "alpha6":
        return type("_Frz_a6", (C,), {"RATE_ALPHA": 6.0})
    if arm == "seq3":
        return type("_Frz_s3", (C,), {"SEQ_DEPTH": 3})
    if arm == "wsync015":
        return type("_Frz_w015", (C,), {"W_SYNC": 0.15})
    raise KeyError(arm)


def one(job):
    arm, regime, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel

    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    # EXOGENOUS: the arrival schedule is fixed by the seed, so every arm faces BIT-IDENTICAL demand.
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
    print(f"freeze_check: {len(jobs)} runs, arms={ARMS}, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 200 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("freeze_check: DONE", flush=True)


if __name__ == "__main__":
    main()
