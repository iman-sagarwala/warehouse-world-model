"""Longest SINGLE pod-wait, off vs picker-free-move, same 24 seeds as the smoke test.

The smoke test reported total pod-wait steps; this reports the tail -- the worst individual wait, plus
the distribution, since the session's repeated finding is that the mean is trivial and the damage lives
in the tail.
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

S0 = int(os.environ.get("S0", "1"))
SEEDS = list(range(S0, S0 + int(os.environ.get("SEEDS", "24"))))
ARMS = ["off", "pickermove", "committed", "committed+final"]


def one(job):
    arm, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, Action, CollisionLayers
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
    if arm == "pickermove":
        env.picker_free_move = True
    elif arm.startswith("committed"):
        env.picker_free_move = "committed"
        if arm.endswith("+final"):
            env.picker_final_step = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    run, lens = {}, []
    for t in range(500):
        env.step(ctrl.act())
        cur = set()
        for a in env.agents:
            if (a.type == AgentType.AGV and a.carrying_shelf is None
                    and a.req_action == Action.TOGGLE_LOAD
                    and env.grid[CollisionLayers.SHELVES, a.y, a.x]
                    and not env.grid[CollisionLayers.PICKERS, a.y, a.x]):
                cur.add(a.id)
        for i in list(run):
            if i not in cur:
                lens.append(run.pop(i))
        for i in cur:
            run[i] = run.get(i, 0) + 1
    lens.extend(run.values())
    return (arm, lens)


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    agg = {a: [] for a in ARMS}
    for a, lens in rows:
        agg[a].extend(lens)
    print("longest SINGLE pod-wait, %d seeds\n" % len(SEEDS))
    print("%-12s %8s %9s %8s %8s %8s %8s" % ("arm", "n waits", "total", "MAX", "p99", "p90", "median"))
    for a in ARMS:
        L = sorted(agg[a])
        if not L:
            print("%-12s   none" % a)
            continue
        print("%-12s %8d %9d %8d %8d %8d %8d"
              % (a, len(L), sum(L), L[-1], L[int(.99 * (len(L) - 1))],
                 L[int(.90 * (len(L) - 1))], L[len(L) // 2]))
