"""USER RULE: a picker whose next cell is clear moves to its AGV. One boolean, no graph reasoning.

Targets a measured defect: the referee's blanket sweep NOOPs every agent the graph machinery did not
name, and pickers are the usual casualty -- a picker emitted FORWARD -> NOOP on 144 of 183 steps with
its target cell EMPTY on all three collision layers. A silenced picker is stationary next step, which is
exactly what keeps an AGV parked at a pod waiting for it.

Run against the SHIPPED config (space-time off), since that is the known-good 0-deadlock baseline.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

S0 = int(os.environ.get("S0", "1"))
SEEDS = list(range(S0, S0 + int(os.environ.get("SEEDS", "24"))))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = ["off", "committed+final", "cf+both", "CHAMPION"]


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
    if arm != "off":
        env.picker_free_move = "committed"
        env.picker_final_step = True
    if arm in ("cf+both", "CHAMPION"):
        env.station_side_keepout = True
        env.station_divert = True
    if arm == "CHAMPION":
        env.swap_return_drop = True    # + the occupant exemption, which is in the keepout rule itself
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, delivered, podwait = 0.0, 0, 0
    tail = {}
    for t in range(500):
        _, rew, _, _, _ = env.step(ctrl.act())
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
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
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), delivered, podwait, frozen)


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    PW = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, d, pw, fr in rows:
        D[a][s] = v
        DL[a] += d
        PW[a] += pw
        FR[a] += fr
    print("picker-free-move smoke test, %d seeds\n" % len(SEEDS))
    print("%-12s %11s %10s %12s %13s %9s" % ("arm", "mean value", "delivered", "pod-wait",
                                             "frozen AGVs", "t vs off"))
    for a in ARMS:
        v = [D[a][s] for s in SEEDS]
        if a == "off":
            tt = "-"
        else:
            d = [D[a][s] - D["off"][s] for s in SEEDS]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-12s %11.2f %10d %12d %13d %9s" % (a, sum(v) / len(v), DL[a], PW[a], FR[a], tt))
