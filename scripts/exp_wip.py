"""WIP CAP sweep on the HARD (peak-demand) seed half, where 86% of episodes deadlock.

A loaded AGV cannot step aside -- its pod only goes down at a station -- so once every AGV is carrying
there is no free robot left to break any jam. Cap the number of concurrently-loaded AGVs below fleet
size and see whether keeping 1-3 free agents buys more than the withheld work costs.

Run with S0=73 SEEDS=72 for the peak half, S0=1 for off-peak.
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
ARMS = [0, 7, 6, 5, 4]          # 0 = no cap (8 AGVs)


def one(job):
    lim, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp

    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
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
    C = cp._SqWidePkRateAdaptive if not lim else type(
        "_Wip%d" % lim, (cp._SqWidePkRateAdaptive,), {"WIP_LIMIT": lim})
    ctrl = C(env)
    onv, t, done, hist = 0.0, 0, False, {}
    delivered = 0
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
    return (lim, seed, round(onv, 1), frozen, delivered)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in range(S0, S0 + SEEDS)]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/wip_s%d.csv" % S0, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wip_limit", "seed", "on_time_value", "frozen_agvs", "delivered"])
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
    print("seeds %d-%d" % (S0, S0 + SEEDS - 1))
    print("%-10s %11s %9s %12s %14s %10s %9s" % ("wip cap", "on-time val", "mean", "frozen AGVs",
                                                 "dead episodes", "delivered", "t vs none"))
    for a in ARMS:
        v = [D[a][s] for s in range(S0, S0 + SEEDS)]
        if a == 0:
            tt = "-"
        else:
            d = [D[a][s] - D[0][s] for s in range(S0, S0 + SEEDS)]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-10s %11.1f %9.2f %12d %9d/%-4d %10d %9s" % (
            "none" if a == 0 else str(a), sum(v), sum(v) / len(v), F[a], DE[a], SEEDS, DL[a], tt))
