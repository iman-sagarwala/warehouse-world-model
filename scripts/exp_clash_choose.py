"""WAIT-vs-REROUTE ranked by value rate, on both demand halves.

The clash handler currently always reroutes, with care_for_agents=True treating transient robots as
permanent walls. Measured on seed 11: a picker 6-10 steps from a waiting AGV was thrown 30-46 steps
away, three times, +90 steps of detour, while the AGV sat for 138 steps.

`clash_choose` ranks the two options by v/T and takes the faster route to the value:
    T_reroute = len(new route);  T_wait = (blocker clearance estimate) + len(existing route)

`clash_wait_est` is the pessimistic clearance for a blocker that is parked with no service timer --
sweeping it shows how sensitive the rule is to that one guess.
"""
import csv
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
NPROC = int(os.environ.get("NPROC", "8"))
SEEDS = list(range(1, 145))
ARMS = [None, 'near', 'near+req', 'step+req']   # None = off (always reroute)


def one(job):
    est, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, Action, CollisionLayers
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
    if est is not None:
        env.clash_choose = est.split("+")[0]
        if est.endswith("+req"):
            # The waiter holds, so the OTHER robot must be guaranteed to move -- otherwise its
            # find_path can return [] and it holds too, which is the standoff that put 8-10 frozen
            # AGVs back. `require_reroute` drops the already-fixing gate and falls back to an
            # agent-blind replan so the designated yielder ALWAYS produces a route.
            env.require_reroute = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, delivered, podwait = 0.0, 0, False, 0, 0
    hist = {}
    while not done and t < STEPS:
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        for a in env.agents:
            if (a.type == AgentType.AGV and a.carrying_shelf is None
                    and a.req_action == Action.TOGGLE_LOAD
                    and env.grid[CollisionLayers.SHELVES, a.y, a.x]
                    and not env.grid[CollisionLayers.PICKERS, a.y, a.x]):
                podwait += 1
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id, []).append((a.x, a.y))
        done = all(term) or all(trunc)
    frozen = sum(1 for v in hist.values() if len(v) >= 95 and len(set(v)) == 1)
    return (est, seed, round(onv, 1), delivered, podwait, frozen)


def report(rows, lo, hi, label):
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    PW = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for est, s, v, dl, pw, fr in rows:
        if not (lo <= s <= hi):
            continue
        D[est][s] = v
        DL[est] += dl
        PW[est] += pw
        FR[est] += fr
    ss = list(range(lo, hi + 1))
    print("\n=== %s (seeds %d-%d) ===" % (label, lo, hi))
    print("%-16s %11s %10s %14s %12s %9s" % ("one-waiter rule", "mean value", "delivered",
                                             "pod-wait steps", "frozen AGVs", "t vs off"))
    for a in ARMS:
        v = [D[a][s] for s in ss]
        if a is None:
            tt = "-"
        else:
            d = [D[a][s] - D[None][s] for s in ss]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-16s %11.2f %10d %14d %12d %9s" % ("off (always reroute)" if a is None else {"near":"closer HOLDS","near+req":"HOLDS + req_reroute","step+req":"STEPS + req_reroute"}[a],
                                                   sum(v) / len(v), DL[a], PW[a], FR[a], tt))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/clash_choose.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["one-waiter rule", "seed", "on_time_value", "delivered", "pod_wait", "frozen"])
        w.writerows(rows)
    report(rows, 1, 72, "OFF-PEAK")
    report(rows, 73, 144, "PEAK")
    report(rows, 1, 144, "POOLED")
