"""Deadlock arms on top of the standing config (headway + stations-as-resource + station exit priority).

The metric that matters is not "did the fleet freeze" -- pickers keep shuffling during a jam and mask it.
It is: a CARRYING AGV that never changes cell over the last 100 steps. That robot is holding a pod it
will never deliver, and it is never coming back.

  exit          standing config only
  exit+replan   `blocked_replan`      -- any AGV blocked N steps replans AROUND the blocker
  exit+avoid    `stuck_avoid_agents`  -- a stuck-released agent repaths with care_for_agents=True
  exit+both     both
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
ARMS = ["exit", "exit+replan", "exit+avoid", "exit+both"]


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
    if "replan" in arm or "both" in arm:
        env.blocked_replan = True
    if "avoid" in arm or "both" in arm:
        env.stuck_avoid_agents = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, hist = 0.0, 0, False, {}
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id, []).append((a.x, a.y))
        done = all(term) or all(trunc)
    frozen = sum(1 for v in hist.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), frozen, len(getattr(env, "_all_orders", []) or []) or n)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in range(S0, S0 + SEEDS)]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/deadlock_arms.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "frozen_agvs", "orders"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    F = {a: 0 for a in ARMS}
    DE = {a: 0 for a in ARMS}
    for a, s, v, fr, nord in rows:
        D[a][s] = v
        F[a] += fr
        DE[a] += 1 if fr > 0 else 0
    print("%-14s %11s %9s %13s %15s %9s" % ("arm", "on-time val", "mean", "frozen AGVs",
                                            "dead episodes", "t vs exit"))
    for a in ARMS:
        v = [D[a][s] for s in range(S0, S0 + SEEDS)]
        if a == "exit":
            tt = "-"
        else:
            d = [D[a][s] - D["exit"][s] for s in range(S0, S0 + SEEDS)]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-14s %11.1f %9.2f %13d %10d/%-4d %9s" % (a, sum(v), sum(v) / len(v), F[a],
                                                         DE[a], SEEDS, tt))
