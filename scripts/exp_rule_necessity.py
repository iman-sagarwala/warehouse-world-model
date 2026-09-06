"""Are the liveness rules still needed now that the ROOT cause is fixed?

`station_headway` (+36.7% when added) and `station_exit_priority` (+3.05%) were both built to stop the
station deadlock. `free_pod_return` has since removed the actual cause of permanent freezes, and those
two rules now hold robots still for 5798 AGV-steps per 24 peak episodes -- 13.1% of all non-moving
time, the largest addressable bucket. A rule that buys liveness we no longer need is pure cost.

Also arms `pickers_free`: the picker oracle, to confirm the pick rendezvous is still the binding
constraint after the unload change (it should be -- picker dwell is 27.9% of non-moves).
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
ARMS = ["standing", "no headway", "no exit prio", "neither", "pickers_free (oracle)"]


def one(job):
    arm, seed = job
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
    env.free_pod_return = True
    env.station_headway = arm not in ("no headway", "neither")
    env.station_exit_priority = arm not in ("no exit prio", "neither")
    if arm.startswith("pickers_free"):
        env.pickers_free = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, delivered = 0.0, 0, False, 0
    hist = {}
    stalled = 0
    while not done and t < STEPS:
        pre = {a.id: (a.x, a.y) for a in env.agents if a.type == AgentType.AGV}
        working = {a.id for a in env.agents
                   if a.type == AgentType.AGV and (a.busy or a.carrying_shelf is not None)}
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        for a in env.agents:
            if a.type == AgentType.AGV and a.id in working and (a.x, a.y) == pre.get(a.id):
                stalled += 1
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id, []).append((a.x, a.y))
        done = all(term) or all(trunc)
    frozen = sum(1 for v in hist.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), stalled, frozen, delivered)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in range(S0, S0 + SEEDS)]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/rule_necessity_s%d.csv" % S0, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "stalled_steps", "frozen_agvs", "delivered"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    SS = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    DE = {a: 0 for a in ARMS}
    DL = {a: 0 for a in ARMS}
    for a, s, v, ss, fr, dl in rows:
        D[a][s] = v
        SS[a] += ss
        FR[a] += fr
        DE[a] += 1 if fr > 0 else 0
        DL[a] += dl
    print("seeds %d-%d  (peak demand, free_pod_return ON in every arm)" % (S0, S0 + SEEDS - 1))
    print("%-23s %10s %14s %12s %14s %10s %9s" % ("arm", "mean value", "stalled-steps", "frozen AGVs",
                                                  "dead episodes", "delivered", "t vs std"))
    for a in ARMS:
        v = [D[a][s] for s in range(S0, S0 + SEEDS)]
        if a == "standing":
            tt = "-"
        else:
            d = [D[a][s] - D["standing"][s] for s in range(S0, S0 + SEEDS)]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-23s %10.2f %14d %12d %9d/%-4d %10d %9s" % (a, sum(v) / len(v), SS[a], FR[a],
                                                            DE[a], SEEDS, DL[a], tt))
