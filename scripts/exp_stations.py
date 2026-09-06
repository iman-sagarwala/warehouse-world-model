"""STATION COUNT sweep at peak demand.

The WIP sweep proved deadlock is fleet-saturation driven (cap the fleet, deadlock falls monotonically)
but withholding work costs more value than it saves. That points at the other side of the same
constraint: 3 stations at 6-step service ceiling out near 250 deliveries per 500-step episode, and the
uncapped policy already reaches 199 -- 80% of station capacity. A system run that close to its
bottleneck queues, and queued LOADED AGVs cannot step aside, so jams become permanent.

If deadlock is a capacity shortfall rather than a routing failure, adding stations should cut it AND
raise value -- unlike the WIP cap, which cut it and lowered value.

n_stations was set to 3 during the realism audit for throughput balance; this tests whether that
balance was struck against the wrong quantity (fleet size, not aisle geometry).
"""
import csv
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = int(os.environ.get("SEEDS", "72"))
S0 = int(os.environ.get("S0", "73"))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = [3, 4, 5, 6]


def one(job):
    nst, seed = job
    from wwm_sim.warehouse import Warehouse, RewardType, AgentType
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp

    env = Warehouse(column_height=6, column_width=2, highway_lanes=1, n_stations=nst,
                    shelf_rows=3, shelf_columns=5, num_agvs=8, num_pickers=6,
                    request_queue_size=40, max_inactivity_steps=None, max_steps=STEPS,
                    reward_type=RewardType.INDIVIDUAL, observation_type="global")
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
    return (nst, seed, round(onv, 1), frozen, delivered)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in range(S0, S0 + SEEDS)]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/stations_s%d.csv" % S0, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n_stations", "seed", "on_time_value", "frozen_agvs", "delivered"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    F = {a: 0 for a in ARMS}
    DE = {a: 0 for a in ARMS}
    DL = {a: 0 for a in ARMS}
    for a, s, v, fr, dl in rows:
        D[a][s] = v
        F[a] += fr
        DE[a] += 1 if fr > 0 else 0
        DL[a] += dl
    print("seeds %d-%d  (8 AGVs, 6 pickers, peak demand)" % (S0, S0 + SEEDS - 1))
    print("%-11s %11s %9s %12s %14s %10s %9s" % ("stations", "on-time val", "mean", "frozen AGVs",
                                                 "dead episodes", "delivered", "t vs 3"))
    for a in ARMS:
        v = [D[a][s] for s in range(S0, S0 + SEEDS)]
        if a == 3:
            tt = "-"
        else:
            d = [D[a][s] - D[3][s] for s in range(S0, S0 + SEEDS)]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-11d %11.1f %9.2f %12d %9d/%-4d %10d %9s" % (a, sum(v), sum(v) / len(v), F[a],
                                                             DE[a], SEEDS, DL[a], tt))
