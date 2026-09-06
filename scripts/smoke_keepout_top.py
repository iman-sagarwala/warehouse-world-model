"""SMOKE (30 seeds): champion v6 vs v6 + keepout_top.

USER RULE 2026-08-13: "side cells for stations should include the top side." Audit found the top cell
was NOT policed: headway covers it (hold-back when station occupied), but the side-keepout invariant
(never take the last escape) was flanks-only, and the exit-priority sidestep excluded UP for a reason
that no longer exists (the continuation has been rebuilt from the sidestep cell since 2026-08-08).

`env.keepout_top`: entering a station's TOP cell is held when BOTH flanks are occupied (never take the
last free neighbour), and the occupant's escape sidestep may also go UP.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, int(os.environ.get("SEEDS", "30")) + 1))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = ["v6", "top"]


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
    if arm == "top":
        env.keepout_top = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, d = 0.0, 0
    run, worst, tail = {}, 0, {}
    for t in range(500):
        _, rew, _, _, _ = env.step(ctrl.act())
        d += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        cur = set()
        for a in env.agents:
            if (a.type == AgentType.AGV and a.carrying_shelf is None
                    and a.req_action == Action.TOGGLE_LOAD
                    and env.grid[CollisionLayers.SHELVES, a.y, a.x]
                    and not env.grid[CollisionLayers.PICKERS, a.y, a.x]):
                cur.add(a.id)
        for i in list(run):
            if i not in cur:
                run.pop(i)
        for i in cur:
            run[i] = run.get(i, 0) + 1
            worst = max(worst, run[i])
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    fr = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), d, worst, fr)


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    MX = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, d, mx, fr in rows:
        D[a][s] = v
        DL[a] += d
        MX[a] = max(MX[a], mx)
        FR[a] += fr
    diff = [D["top"][s] - D["v6"][s] for s in SEEDS]
    m = sum(diff) / len(diff)
    sd = st.pstdev(diff) * (len(diff) / (len(diff) - 1)) ** 0.5
    tt = m / (sd / len(diff) ** 0.5) if sd else float("inf")
    n_ = len(SEEDS)
    print("KEEPOUT-TOP smoke, %d seeds (champion v6 vs +top-side rule):" % n_)
    print("  v6   value %.2f  delivered %d  MAX wait %d  frozen %d"
          % (sum(D["v6"].values()) / n_, DL["v6"], MX["v6"], FR["v6"]))
    print("  +top value %.2f  delivered %d  MAX wait %d  frozen %d"
          % (sum(D["top"].values()) / n_, DL["top"], MX["top"], FR["top"]))
    print("  diff %+.2f/ep  t=%+.2f  wins/losses %d/%d"
          % (m, tt, sum(1 for x in diff if x > 0), sum(1 for x in diff if x < 0)))
