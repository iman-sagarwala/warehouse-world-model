"""SMOKE (USER, 30 seeds): replace Yen's k-loopless candidate routes with the single A*-shortest path
(K_ROUTES=1) at BOTH funnel sites -- the only places Yen's runs on the champion path. Decision rule,
stated in advance: notably negative -> stop and keep Yen's; null or positive -> Yen's diversity was
doing nothing and we note it."""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 145))
ARMS = ["yen", "astar1"]


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
    env.picker_free_move = "committed"
    env.picker_final_step = True
    env.station_side_keepout = True
    env.station_divert = True
    env.swap_return_drop = True
    env.picker_swap = True
    env.picker_swap_squat = True
    env.agv_free_move = True
    env.slot_divert = True
    env.picker_reelect = "progress"
    env.clash_sim = True
    env.clash_hysteresis = 20
    C = cp._SqWidePkRateAdaptive
    if arm == "astar1":
        C = type("_K1", (C,), {"K_ROUTES": 1})
    ctrl = C(env)
    onv = 0.0
    tail = {}
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), frozen)


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    D = {a: {} for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, fr in rows:
        D[a][s] = v
        FR[a] += fr
    d = [D["astar1"][s] - D["yen"][s] for s in SEEDS]
    m = sum(d) / len(d)
    sd_ = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
    tt = m / (sd_ / len(d) ** 0.5) if sd_ else float("inf")
    base = sum(D["yen"].values())
    n_ = len(SEEDS)
    ev = [D["astar1"][s] - D["yen"][s] for s in SEEDS if s % 2 == 0]
    od = [D["astar1"][s] - D["yen"][s] for s in SEEDS if s % 2 == 1]
    def _t(x):
        mm = sum(x) / len(x)
        ss = st.pstdev(x) * (len(x) / (len(x) - 1)) ** 0.5
        return mm / (ss / len(x) ** 0.5) if ss else float("inf")
    print("YEN'S (k=3) vs A*-SHORTEST (k=1), %d seeds  (SHIP RULE: t >= 2 -> ship k=1):" % n_)
    print("  yen    mean %.2f   frozen %d" % (sum(D["yen"].values()) / n_, FR["yen"]))
    print("  astar1 mean %.2f   frozen %d" % (sum(D["astar1"].values()) / n_, FR["astar1"]))
    print("  split-half t = %+.2f / %+.2f" % (_t(ev), _t(od)))
    print("  diff %+.2f/episode (%+.2f%%)   t=%+.2f   wins/losses %d/%d"
          % (m, 100.0 * sum(d) / base, tt,
             sum(1 for x in d if x > 0), sum(1 for x in d if x < 0)))
