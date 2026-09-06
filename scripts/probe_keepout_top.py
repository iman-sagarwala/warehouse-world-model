"""Does keepout_top ever FIRE? Count top-cell holds and upward escapes, off-peak and peak seeds."""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


def one(seed):
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import Warehouse, CollisionLayers, AgentType
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
    env.keepout_top = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    # count: steps where any station has BOTH flanks occupied (the precondition), and
    # steps where an AGV's next cell is a station top cell at all
    both_flanks = 0
    top_entries = 0
    for t in range(500):
        env.step(ctrl.act())
        for (gx, gy) in env.goals:
            occ = 0
            for fx in (gx - 1, gx + 1):
                if not (0 <= fx < env.grid_size[1]):
                    occ += 1
                elif (env.grid[CollisionLayers.AGVS, gy, fx]
                        or env.grid[CollisionLayers.PICKERS, gy, fx]):
                    occ += 1
            if occ == 2:
                both_flanks += 1
        for a in env.agents:
            if a.type != AgentType.AGV or not getattr(a, "path", None):
                continue
            nx_, ny_ = a.path[0]
            for (gx, gy) in env.goals:
                if nx_ == gx and ny_ == gy - 1:
                    top_entries += 1
    return (seed, both_flanks, top_entries)


if __name__ == "__main__":
    seeds = list(range(1, 16)) + list(range(73, 88))
    with mp.Pool(8) as pool:
        rows = pool.map(one, seeds)
    op = [r for r in rows if r[0] < 73]
    pk = [r for r in rows if r[0] >= 73]
    for lab, part in (("off-peak (1-15)", op), ("peak (73-87)", pk)):
        print("%s: station-steps with BOTH flanks occupied = %d ; AGV next-cell-is-top steps = %d"
              % (lab, sum(r[1] for r in part), sum(r[2] for r in part)))
