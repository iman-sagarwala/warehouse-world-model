"""TRUE VoPI — the value of PERFECT DEMAND INFORMATION, with stream's physics held fixed.

WHY THIS EXISTS. `day-list minus stream` is NOT an information bound. `seed_day_list()` puts every
order in the queue at t=0 while its deadline stays `t_arrive + slack`, so day-list can SERVE work
before it arrives -- each task gets the full 500 steps instead of `500 - t_arrive`. That gap is
CAPACITY, not knowledge, and no predictor can grant it. (Measured 2026-08-01: workload-matched
day-list - stream = +142.9, 54.9%, t=60.8 -- and flat at 49-63% across six fleets, which is itself
the signature of a structural effect rather than an informational one.)

THIS arm isolates information: orders become SERVABLE at `t_arrive` exactly as in stream, but the
sequencer's rollout is handed the TRUE upcoming arrivals instead of `[]`. The gap vs plain stream is
the real ceiling on any demand predictor -- the number the SA5/EV/MCTS nulls should be judged against.

v2 (2026-08-01) -- SINGLE PASS, EXACT. The v1 two-pass design was INVALID and its -11.39 result is
retracted: `DemandModel._inject` chose among shelves NOT in transit, so demand was endogenous to the
policy and the "known future" recorded under the no-foresight run was ~78% wrong under the foresight
run (measured overlap 0.222). It measured stale information, not perfect information.
FIXED by `DemandModel(exogenous=True)`, which pre-draws the whole arrival schedule from the seed alone.
Verified: two different controllers now see BIT-IDENTICAL arrival streams, `future_arrivals()` matches
what actually lands 100%, and the legacy path reproduces previously-banked values exactly.
So both arms below run on the SAME demand, and the foresight arm is handed the GENUINE future.

Env: SEEDS, NPROC, OUT.  CSV: arm,agvs,pickers,seed,on_time_value
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
OUT = os.environ.get("OUT", "results/vopi_true.csv")
FLEETS = [(4, 4), (6, 6), (8, 8), (8, 4), (4, 8), (9, 9)]


def _build(agv, pk, seed):
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    # EXOGENOUS: the arrival schedule is fixed by the seed, so both arms face identical demand and the
    # foresight arm's "future" is the real one. This is what makes the comparison valid at all.
    env.demand_model = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS)
    env.demand_model.seed_initial(env, n=12)
    return env


def _run(env, ctrl):
    onv, t, done = 0.0, 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return round(onv, 1)


def one(job):
    agv, pk, seed = job
    from congestion_policies import _SqWidePkRateAdaptive, _FakeOrder

    class _Foresight(_SqWidePkRateAdaptive):
        """Champion, but the rollout is handed the GENUINE upcoming orders instead of []."""
        def _future_arrivals(self, now, horizon):
            dm = getattr(self.env, "demand_model", None)
            if dm is None:
                return []
            return [(t, _FakeOrder(s.x, s.y, v, dl, -1000 - i))
                    for i, (t, s, v, dl) in enumerate(dm.future_arrivals(now, horizon))]

    env = _build(agv, pk, seed)
    base = _run(env, _SqWidePkRateAdaptive(env))
    env2 = _build(agv, pk, seed)                 # identical demand, guaranteed by exogenous=True
    fore = _run(env2, _Foresight(env2))
    return [("stream_plain", agv, pk, seed, base), ("stream_perfect_info", agv, pk, seed, fore)]


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "agvs", "pickers", "seed", "on_time_value"])
        w.writerows(rows)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows, have = [], set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["arm"], int(r["agvs"]), int(r["pickers"]), int(r["seed"]),
                             float(r["on_time_value"])))
                have.add((int(r["agvs"]), int(r["pickers"]), int(r["seed"])))
    jobs = [(a, p, s) for (a, p) in FLEETS for s in range(SEEDS) if (a, p, s) not in have]
    print(f"true-vopi: {len(jobs)} paired runs to do, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=2), 1):
                rows.extend(res)
                if k % 25 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("true-vopi: DONE", flush=True)


if __name__ == "__main__":
    main()
