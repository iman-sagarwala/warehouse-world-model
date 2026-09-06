"""5-MINUTE SMOKE TEST: does a priority ordering kill the all-wait fixed point?

Bar to clear, in order:
  1. frozen carrying AGVs back to 0   (deadlock-free is the standing requirement)
  2. longest standstill of any robot back to something sane (was 488/500 unordered)
  3. value not worse than space-time off

Arms: off | unordered | EDF | value-rate. Small seed count on purpose -- this is a smoke test, not a
shipping measurement.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, int(os.environ.get("SEEDS", "12")) + 1))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = ["off", "unordered", "deadline", "valuerate"]


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
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    env.picker_service_steps = 8
    env.station_service_steps = 6
    env.station_headway = True
    env.station_exit_priority = True
    env.free_pod_return = True
    if arm != "off":
        env.spacetime_reservations = True
        env.st_window = 16
        if arm == "unordered":
            env.st_priority = "none"          # unknown mode -> EDF key; emulate old behaviour below
        else:
            env.st_priority = arm
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, delivered = 0.0, 0
    run, longest, tail = {}, 0, {}
    for t in range(500):
        pre = {a.id: (a.x, a.y) for a in env.agents}
        _, rew, _, _, _ = env.step(ctrl.act())
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        for a in env.agents:
            if (a.x, a.y) == pre[a.id]:
                run[a.id] = run.get(a.id, 0) + 1
                longest = max(longest, run[a.id])
            else:
                run.pop(a.id, None)
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), delivered, longest, frozen)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    LG = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for arm, s, v, dl, lg, fr in rows:
        D[arm][s] = v
        DL[arm] += dl
        LG[arm] = max(LG[arm], lg)
        FR[arm] += fr
    print("smoke test, %d seeds\n" % len(SEEDS))
    print("%-12s %11s %10s %20s %14s %9s" % ("arm", "mean value", "delivered",
                                             "longest standstill", "frozen AGVs", "t vs off"))
    for a in ARMS:
        v = [D[a][s] for s in SEEDS]
        if a == "off":
            tt = "-"
        else:
            d = [D[a][s] - D["off"][s] for s in SEEDS]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-12s %11.2f %10d %20d %14d %9s" % (a, sum(v) / len(v), DL[a], LG[a], FR[a], tt))
