"""STALL REDUCTION on the standing config (headway + exit priority + free_pod_return + SIM_DOCK_RES).

Permanent deadlock is now 0/144, so the remaining target is TEMPORARY stalls: runs of consecutive steps
where an AGV that has work (busy or carrying) does not change cell. Those are pure lost robot-time.

Reported per episode:
  stalled-steps  total AGV-steps spent not moving while holding work  (the headline cost)
  max stall      longest single stall in the episode
  long stalls    number of stalls >= 20 steps (the ones a dispatcher would notice)

Arms retest the two routing rules that measured inert while deadlock dominated -- with the strandings
gone, a blocked robot is now genuinely blocked, so rerouting it may finally pay.
Run at PEAK (S0=73) where stalls are worst; deadlock/stalls are strongly load-dependent.
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
ARMS = ["standing", "replan8", "replan4", "avoid", "replan4+avoid"]


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
    if arm.startswith("replan"):
        env.blocked_replan = True
        env.blocked_patience = 8 if "8" in arm else 4
    if "avoid" in arm:
        env.stuck_avoid_agents = True
        if "replan" in arm:
            env.blocked_replan = True
            env.blocked_patience = 4
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done = 0.0, 0, False
    run = {}          # agv id -> current stall length
    stalls = []       # completed stall lengths
    prev = {}
    while not done and t < STEPS:
        pre = {a.id: (a.x, a.y) for a in env.agents if a.type == AgentType.AGV}
        working = {a.id for a in env.agents
                   if a.type == AgentType.AGV and (a.busy or a.carrying_shelf is not None)}
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        for a in env.agents:
            if a.type != AgentType.AGV:
                continue
            moved = (a.x, a.y) != pre.get(a.id)
            if a.id in working and not moved:
                run[a.id] = run.get(a.id, 0) + 1
            else:
                if run.get(a.id, 0):
                    stalls.append(run[a.id])
                run[a.id] = 0
        done = all(term) or all(trunc)
    stalls.extend(v for v in run.values() if v)
    return (arm, seed, round(onv, 1), sum(stalls), max(stalls) if stalls else 0,
            sum(1 for v in stalls if v >= 20), len(stalls))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in range(S0, S0 + SEEDS)]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/stalls_s%d.csv" % S0, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "stalled_steps", "max_stall", "long_stalls", "n_stalls"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    SS = {a: 0 for a in ARMS}
    MX = {a: 0 for a in ARMS}
    LG = {a: 0 for a in ARMS}
    NS = {a: 0 for a in ARMS}
    for a, s, v, ss, mx, lg, ns in rows:
        D[a][s] = v
        SS[a] += ss
        MX[a] = max(MX[a], mx)
        LG[a] += lg
        NS[a] += ns
    print("seeds %d-%d  (standing config, deadlock already 0)" % (S0, S0 + SEEDS - 1))
    print("%-15s %10s %14s %11s %13s %9s %9s" % ("arm", "mean value", "stalled-steps", "max stall",
                                                 "long stalls", "stalls", "t vs base"))
    for a in ARMS:
        v = [D[a][s] for s in range(S0, S0 + SEEDS)]
        if a == "standing":
            tt = "-"
        else:
            d = [D[a][s] - D["standing"][s] for s in range(S0, S0 + SEEDS)]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-15s %10.2f %14d %11d %13d %9d %9s" % (a, sum(v) / len(v), SS[a], MX[a], LG[a],
                                                       NS[a], tt))
