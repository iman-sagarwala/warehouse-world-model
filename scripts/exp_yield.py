"""Priority-ordered deadlock yielding (user's design, 2026-08-05).

When two robots clash, the base simulator makes whoever the nested clash loop reaches FIRST do the
rerouting (`if other.fixing_clash == 0`). That is arbitrary and can flip between steps, so both robots
reroute, re-collide, and dance. FIX: rank the pair; the higher-priority robot gets first choice of
route, the loser reroutes around it (`Warehouse._yields_to`).

ARMS
  champion   legacy iteration-order yielding (baseline)
  arbitrary  deterministic rank by agent id      <- CONTROL: isolates "stable winner" from "right winner"
  value      rank by task value  (higher value keeps its route)
  deadline   rank by task deadline (earlier deadline keeps its route)

The `arbitrary` control is essential: without it a win by `value`/`deadline` cannot be distinguished
from the mere fact that yielding became deterministic.
Env: SEEDS, NPROC, OUT.
"""
import csv, os, sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = int(os.environ.get("SEEDS", "120"))
NPROC = int(os.environ.get("NPROC", "8"))
OUT = os.environ.get("OUT", "results/yield.csv")
FLEETS = [(4, 4), (6, 6), (8, 6), (8, 8), (9, 9)]
REGIMES = ["daylist", "stream"]
ARMS = ["champion", "arbitrary", "value", "deadline"]


def one(job):
    arm, regime, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    from congestion_policies import _SqWidePkRateAdaptive as C

    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS)
    if regime == "daylist":
        env.demand_model.seed_day_list(env, horizon=STEPS)
    else:
        env.demand_model.seed_initial(env, n=12)
    if arm != "champion":
        env.commit_priority = arm
    ctrl = C(env)
    onv, t, done, coll = 0.0, 0, False, 0
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        seen = {}
        for a in env.agents:                    # collision invariant, checked every step
            k = (a.type, a.x, a.y)
            coll += 1 if k in seen else 0
            seen[k] = a.id
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return (arm, regime, agv, pk, seed, round(onv, 1), coll)


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "regime", "agvs", "pickers", "seed", "on_time_value", "collisions"])
        w.writerows(rows)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows, have = [], set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["arm"], r["regime"], int(r["agvs"]), int(r["pickers"]),
                             int(r["seed"]), float(r["on_time_value"]), int(r["collisions"])))
                have.add((r["arm"], r["regime"], int(r["agvs"]), int(r["pickers"]), int(r["seed"])))
    jobs = [(a, rg, ag, pk, s) for a in ARMS for rg in REGIMES for (ag, pk) in FLEETS
            for s in range(SEEDS) if (a, rg, ag, pk, s) not in have]
    print(f"yield: {len(jobs)} runs, arms={ARMS}, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 200 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("yield: DONE", flush=True)


if __name__ == "__main__":
    main()
