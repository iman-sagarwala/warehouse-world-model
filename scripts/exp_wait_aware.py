"""SUNK-WAIT picker dispatch sweep, OFF-PEAK (where the oracle says there is 3.74% to win).

Picker scoring currently prices only the forecast rendezvous. This arms a multiplicative boost for
rendezvous where an AGV is already parked and waiting, since those steps are sunk robot-time that keeps
accruing. Reports waiting toggles directly -- if the mechanism works, the no-op TOGGLE_LOAD count falls.
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
S0 = int(os.environ.get("S0", "1"))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = [0.0, 0.05, 0.15, 0.4, 1.0]


def one(job):
    w, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, Action
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
    env.free_pod_return = True
    base = cp._SqWidePkRateAdaptive
    C = base if not w else type("_Wait%s" % str(w).replace(".", "_"),
                                (cp._WaitAwarePicker, base), {"WAIT_W": w})
    ctrl = C(env)
    onv, t, done, delivered, twait = 0.0, 0, False, 0, 0
    while not done and t < STEPS:
        pre = {a.id: (a.carrying_shelf is not None) for a in env.agents if a.type == AgentType.AGV}
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        for a in env.agents:
            if a.type == AgentType.AGV and a.req_action == Action.TOGGLE_LOAD \
                    and (a.carrying_shelf is not None) == pre.get(a.id):
                twait += 1
        done = all(term) or all(trunc)
    return (w, seed, round(onv, 1), delivered, twait)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in range(S0, S0 + SEEDS)]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/wait_aware_s%d.csv" % S0, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["wait_w", "seed", "on_time_value", "delivered", "toggle_wait"])
        wr.writerows(rows)
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    TW = {a: 0 for a in ARMS}
    for a, s, v, dl, tw in rows:
        D[a][s] = v
        DL[a] += dl
        TW[a] += tw
    print("seeds %d-%d  (off-peak; oracle headroom here is +3.74%%)" % (S0, S0 + SEEDS - 1))
    print("%-10s %11s %11s %17s %10s" % ("WAIT_W", "mean value", "delivered", "waiting toggles", "t vs 0"))
    for a in ARMS:
        v = [D[a][s] for s in range(S0, S0 + SEEDS)]
        if a == 0.0:
            tt = "-"
        else:
            d = [D[a][s] - D[0.0][s] for s in range(S0, S0 + SEEDS)]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-10s %11.2f %11d %17d %10s" % (a, sum(v) / len(v), DL[a], TW[a], tt))
