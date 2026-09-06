"""Retest the priority-ordered commit resolver on the REPAIRED world.

2279 AGV-steps per 24 peak episodes are robots that asked to move FORWARD into a cell that was FREE on
every collision layer, and were silenced anyway -- the legacy resolver commits only graph cycles plus
one dag_longest_path per component and NOOPs everything else. `env.commit_priority` replaces that with
a fixpoint walk in priority order, committing any mover whose target is free or is being vacated.

It measured negative before (starvation), but that was on a world with two live deadlock mechanisms
and a blind freeze detector. Both are fixed now, so the measurement is worth repeating.

Modes: 'arbitrary' (id order), 'value' (task value first), 'deadline' (EDF first).
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
ARMS = ["legacy", "arbitrary", "value", "deadline"]


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
    env.station_headway = True
    env.station_exit_priority = True
    env.free_pod_return = True
    if arm != "legacy":
        env.commit_priority = arm
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, delivered, stalled = 0.0, 0, False, 0, 0
    hist = {}
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
    with open("results/commit_priority_s%d.csv" % S0, "w", newline="") as f:
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
    print("seeds %d-%d  (peak demand, standing config)" % (S0, S0 + SEEDS - 1))
    print("%-12s %10s %14s %12s %14s %10s %9s" % ("commit", "mean value", "stalled-steps",
                                                  "frozen AGVs", "dead episodes", "delivered", "t vs legacy"))
    for a in ARMS:
        v = [D[a][s] for s in range(S0, S0 + SEEDS)]
        if a == "legacy":
            tt = "-"
        else:
            d = [D[a][s] - D["legacy"][s] for s in range(S0, S0 + SEEDS)]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-12s %10.2f %14d %12d %9d/%-4d %10d %9s" % (a, sum(v) / len(v), SS[a], FR[a],
                                                            DE[a], SEEDS, DL[a], tt))
