"""M1 CLOSE-OUT: the three items still open.

A) DEFERRED DEADLINE KNOBS
   URG_S0   -- the slack SCALE of the AGV deadline term: 1000 + v + URG_W*max(0, 1 - spare/URG_S0).
               Only matters where URG_W > 0, i.e. STREAM ONLY (the champion runs URG_W=0 on day-list),
               which halves the work for free.
   PK_URG_W / PK_URG_S0 -- the PICKER-side mirror (`_PkUrgMixin`), never swept at all. Default 8 / 40.
               Note the champion does NOT currently carry picker urgency, so PK_URG_W=0 is the control
               and anything above it is a MECHANISM ADDITION, not a re-tune.

B) SCALE / GENERALISATION -- the "size-agnostic" claim. Every M1 number comes from ONE map (`large`).
   Re-run champion vs the previous champion (`cong_l2on`) on `medium` and `extralarge`.

Env: PART (a|b), SEEDS, NPROC, OUT.
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
PART = os.environ.get("PART", "a")
OUT = os.environ.get("OUT", "results/m1_close_%s.csv" % PART)

# ---- part A: deferred knobs (stream only for URG_S0; both regimes for the picker knobs) ----
A_FLEETS = [(4, 4), (6, 6), (8, 6), (8, 8), (9, 9)]
A_ARMS = ["champion",
          "s0_20", "s0_80",                      # URG_S0 either side of the shipped 40
          "pkurg_4", "pkurg_8", "pkurg_16",      # picker urgency weight (0 = champion = control)
          "pks0_20", "pks0_80"]                  # picker slack scale, at PK_URG_W=8

# ---- part B: scale / generalisation ----
B_MAPS = ["medium", "extralarge"]
B_FLEETS = [(6, 4), (8, 6), (10, 8)]
B_ARMS = ["champion", "cong_l2on"]


def _cls(arm):
    import congestion_policies as cp
    C = cp._SqWidePkRateAdaptive
    if arm == "champion":
        return C
    if arm.startswith("s0_"):
        return type("_M1_%s" % arm, (C,), {"URG_S0": float(arm.split("_")[1])})
    if arm.startswith("pkurg_"):
        return type("_M1_%s" % arm, (cp._PkUrgMixin, C),
                    {"PK_URG_W": float(arm.split("_")[1]), "PK_URG_S0": 40.0})
    if arm.startswith("pks0_"):
        return type("_M1_%s" % arm, (cp._PkUrgMixin, C),
                    {"PK_URG_W": 8.0, "PK_URG_S0": float(arm.split("_")[1])})
    if arm == "cong_l2on":
        return cp.PartACongestionController          # the previous champion
    raise KeyError(arm)


def one(job):
    arm, regime, mapname, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel

    env = gym.make(f"wwm_sim-{mapname}-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
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
    return (arm, regime, mapname, agv, pk, seed, round(onv, 1))


def jobs_a(have):
    out = []
    for a in A_ARMS:
        regs = ["stream"] if a.startswith("s0_") else ["daylist", "stream"]
        for rg in regs:
            for (ag, pk) in A_FLEETS:
                for s in range(SEEDS):
                    if (a, rg, "large", ag, pk, s) not in have:
                        out.append((a, rg, "large", ag, pk, s))
    return out


def jobs_b(have):
    return [(a, rg, m, ag, pk, s) for a in B_ARMS for rg in ("daylist", "stream")
            for m in B_MAPS for (ag, pk) in B_FLEETS for s in range(SEEDS)
            if (a, rg, m, ag, pk, s) not in have]


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "regime", "map", "agvs", "pickers", "seed", "on_time_value"])
        w.writerows(rows)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows, have = [], set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["arm"], r["regime"], r["map"], int(r["agvs"]), int(r["pickers"]),
                             int(r["seed"]), float(r["on_time_value"])))
                have.add((r["arm"], r["regime"], r["map"], int(r["agvs"]), int(r["pickers"]),
                          int(r["seed"])))
    jobs = jobs_a(have) if PART == "a" else jobs_b(have)
    print(f"m1_close part {PART}: {len(jobs)} runs, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 200 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("m1_close: DONE", flush=True)


if __name__ == "__main__":
    main()
