"""Characterize CHAMPION v6 (RATE_ALPHA=7) on the canonical 144 seeds: full reference numbers."""
import csv
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 145))
NPROC = int(os.environ.get("NPROC", "8"))


def one(seed):
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
    env.clash_hysteesis = None  # noqa - kept out; real flag below
    env.clash_hysteresis = 20
    ctrl = cp._SqWidePkRateAdaptive(env)   # RATE_ALPHA=7 is now the class default
    onv, delivered = 0.0, 0
    run, worst, tail = {}, 0, {}
    podwait = 0
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
                podwait += 1
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
    return (seed, round(onv, 1), delivered, podwait, worst, frozen)


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, SEEDS)
    with open("results/v6_reference.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed", "on_time_value", "delivered", "pod_wait", "max_wait", "frozen"])
        w.writerows(rows)
    vals = [r[1] for r in rows]
    print("CHAMPION v6 (RATE_ALPHA=7) reference, 144 seeds:")
    print("  value %.2f   delivered %d   pod-wait %d   MAX wait %d   frozen %d"
          % (sum(vals) / len(vals), sum(r[2] for r in rows), sum(r[3] for r in rows),
             max(r[4] for r in rows), sum(r[5] for r in rows)))
