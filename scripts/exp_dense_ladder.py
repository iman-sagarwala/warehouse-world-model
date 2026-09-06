"""DENSE-MAP LADDER: FIFO vs rush vs champion v5, 144 paired seeds.

Next-step #1 from the paper: every liveness number so far is champion-config vs champion-config; the
controller ladder has never been run on the dense map with the v5 stack. All three controllers get the
SAME env stack (the liveness flags are execution-layer physics, not part of the decision layer being
compared), so this isolates the DECISION layer's worth on a warehouse that cannot deadlock.
"""
import csv
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 145))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = ["fifo", "rush", "champion"]


def one(job):
    arm, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, Action, CollisionLayers
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    import sim_dashboard as sd
    import sim_priority as sp

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
    if arm == "fifo":
        ctrl = sd.FIFOController(env)
    elif arm == "rush":
        ctrl = sp.RushValueController(env)
    else:
        ctrl = cp._SqWidePkRateAdaptive(env)
    onv, delivered = 0.0, 0
    run, worst, tail = {}, 0, {}
    for t in range(500):
        _, rew, _, _, _ = env.step(ctrl.act())
        delivered += int(sum(rew))
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
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), delivered, worst, frozen)


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    with open("results/dense_ladder.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "delivered", "max_wait", "frozen"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    MX = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, dl, mx, fr in rows:
        D[a][s] = v
        DL[a] += dl
        MX[a] = max(MX[a], mx)
        FR[a] += fr
    print("DENSE-MAP LADDER, 144 paired seeds, v5 env stack for every arm\n")
    print("%-10s %11s %8s %10s %10s %13s %10s" % ("arm", "mean value", "vs FIFO", "delivered",
                                                  "MAX wait", "frozen AGVs", "t vs rush"))
    fifo = [D["fifo"][s] for s in SEEDS]
    rush = [D["rush"][s] for s in SEEDS]
    for a in ARMS:
        v = [D[a][s] for s in SEEDS]
        pc = "-" if a == "fifo" else "%+.1f%%" % (100.0 * (sum(v) - sum(fifo)) / sum(fifo))
        if a == "rush":
            tt = "-"
        else:
            d = [D[a][s] - D["rush"][s] for s in SEEDS]
            m = sum(d) / len(d)
            sd_ = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd_ / len(d) ** 0.5)) if sd_ else "inf"
        print("%-10s %11.2f %8s %10d %10d %13d %10s" % (a, sum(v) / len(v), pc, DL[a],
                                                        MX[a], FR[a], tt))
