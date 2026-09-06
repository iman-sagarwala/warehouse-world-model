"""PLANNING LATENCY — the cost axis (reviewer point: real-time performance matters for deployment).

Every result so far measures VALUE. None measures COST. This measures per-decision wall-clock for the
champion, swept over SEQ_DEPTH -- the knob the rollout's cost actually scales with.

WHY IT MATTERS RIGHT NOW: SEQ_DEPTH is provably INERT on the stream (depths 3/5/8 give bit-identical
results, because the imagined queue empties before the horizon binds) but LOAD-BEARING on day-list
(depth 1 -> 5 is worth +9.8). If depth also costs real time, the stream can run a much cheaper planner
for exactly the same value -- a free latency win that only shows up once you measure cost.

Reports mean / p50 / p95 per-decision latency and the value obtained, so cost and value sit together.
Env: SEEDS, OUT.  CSV: regime,agvs,pickers,seq_depth,seed,on_time_value,n_decisions,ms_mean,ms_p50,ms_p95
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.demand import DemandModel
from congestion_policies import _SqWidePkRateAdaptive

STEPS = 500
SEEDS = int(os.environ.get("SEEDS", "10"))
OUT = os.environ.get("OUT", "results/latency.csv")
FLEETS = [(4, 4), (8, 8), (9, 9)]
DEPTHS = [1, 2, 3, 5]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def run(regime, agv, pk, depth, seed):
    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS)
    env.demand_model = dm
    if regime == "daylist":
        dm.seed_day_list(env, horizon=STEPS)
    else:
        dm.seed_initial(env, n=12)
    cls = type(f"_D{depth}", (_SqWidePkRateAdaptive,), {"SEQ_DEPTH": depth})
    ctrl = cls(env)
    lat, onv, t, done = [], 0.0, 0, False
    while not done and t < STEPS:
        t0 = time.perf_counter()
        a = ctrl.act()                       # ONE full planning decision for the whole fleet
        lat.append((time.perf_counter() - t0) * 1000.0)
        _, _, term, trunc, _i = env.step(a)
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return (regime, agv, pk, depth, seed, round(onv, 1), len(lat),
            round(sum(lat) / len(lat), 3), round(pct(lat, 0.5), 3), round(pct(lat, 0.95), 3))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows = []
    for regime in ("daylist", "stream"):
        for (agv, pk) in FLEETS:
            for d in DEPTHS:
                for s in range(SEEDS):
                    rows.append(run(regime, agv, pk, d, s))
                r = [x for x in rows if x[:4] == (regime, agv, pk, d)]
                print(f"  {regime:8} {agv}x{pk} depth {d}: "
                      f"{sum(x[7] for x in r)/len(r):7.2f} ms/decision   value {sum(x[5] for x in r)/len(r):6.1f}",
                      flush=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["regime", "agvs", "pickers", "seq_depth", "seed", "on_time_value",
                    "n_decisions", "ms_mean", "ms_p50", "ms_p95"])
        w.writerows(rows)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
