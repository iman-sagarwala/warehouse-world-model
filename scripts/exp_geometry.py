"""AISLE GEOMETRY sweep at peak demand -- does the deadlock live in the corridors?

Two measurements bracket the cause:
  * WIP cap    : fewer LOADED robots -> monotonically less deadlock (119 -> 41 frozen AGVs)
  * station    : more STATIONS -> no change at all (119 / 121 / 120 / 122 frozen AGVs)
So the binding constraint is loaded-robot density in the AISLES, not dock capacity. In a 1-cell lane
two loaded AGVs meeting head-on cannot pass, and neither can set its pod down -- there is no third
cell to resolve into. Widening the lane gives every corridor a passing place.

`dual` (highway_lanes=2) was tested once before and called worse, but that was measured with the old
all-agents freeze detector, which missed partial deadlock entirely, and before station exit priority.

Value is NOT comparable across geometries (different grid size -> different travel distances and so a
different achievable ceiling). The deadlock columns are the point; value is reported for context only.
"""
import csv
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = int(os.environ.get("SEEDS", "72"))
S0 = int(os.environ.get("S0", "73"))
NPROC = int(os.environ.get("NPROC", "8"))
# label -> (highway_lanes, column_height, column_width, one_way)
ARMS = {
    "lanes1 (current)": (1, 6, 2, False),
    "lanes2":           (2, 6, 2, False),
    "lanes2 one-way":   (2, 6, 2, True),
    "lanes1 width1":    (1, 6, 1, False),
}


def one(job):
    label, seed = job
    lanes, ch, cw, oneway = ARMS[label]
    from wwm_sim.warehouse import Warehouse, RewardType, AgentType
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp

    env = Warehouse(column_height=ch, column_width=cw, highway_lanes=lanes, n_stations=3,
                    shelf_rows=3, shelf_columns=5, num_agvs=8, num_pickers=6,
                    request_queue_size=40, max_inactivity_steps=None, max_steps=STEPS,
                    reward_type=RewardType.INDIVIDUAL, observation_type="global")
    if oneway:
        env.one_way = True
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=STEPS)
    dm.seed_initial(env, n=n)
    env.picker_service_steps = 8
    env.station_service_steps = 6
    env.station_headway = True
    env.station_exit_priority = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, hist, delivered = 0.0, 0, False, {}, 0
    while not done and t < STEPS:
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id, []).append((a.x, a.y))
        done = all(term) or all(trunc)
    frozen = sum(1 for v in hist.values() if len(v) >= 95 and len(set(v)) == 1)
    return (label, seed, round(onv, 1), frozen, delivered, env.grid_size[0] * env.grid_size[1])


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in range(S0, S0 + SEEDS)]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/geometry_s%d.csv" % S0, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "frozen_agvs", "delivered", "cells"])
        w.writerows(rows)
    V = {a: 0.0 for a in ARMS}
    F = {a: 0 for a in ARMS}
    DE = {a: 0 for a in ARMS}
    DL = {a: 0 for a in ARMS}
    CZ = {a: 0 for a in ARMS}
    for a, s, v, fr, dl, cz in rows:
        V[a] += v
        F[a] += fr
        DE[a] += 1 if fr > 0 else 0
        DL[a] += dl
        CZ[a] = cz
    print("seeds %d-%d  (8 AGVs, 6 pickers, 3 stations, peak demand)" % (S0, S0 + SEEDS - 1))
    print("%-18s %12s %13s %15s %11s %8s" % ("geometry", "mean value", "frozen AGVs",
                                             "dead episodes", "delivered", "cells"))
    for a in ARMS:
        print("%-18s %12.2f %13d %10d/%-4d %11d %8d" % (a, V[a] / SEEDS, F[a], DE[a], SEEDS,
                                                        DL[a], CZ[a]))
