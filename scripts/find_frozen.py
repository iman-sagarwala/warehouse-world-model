"""Name the frozen AGVs instead of quoting a counter.

The `frozen` figure in the smoke tests is a SUM ACROSS ALL EPISODES, not a per-episode count -- 11 over
144 seeds is about one AGV in every 13 runs, never 11 at once. Reporting it as "11 frozen AGVs" was
misleading. This lists the actual (seed, agv) instances and checks each one is genuinely stuck rather
than an artefact of the metric:

  - is it carrying a pod the whole window?
  - does it hold a task and a path?
  - is it merely in a service dwell (legitimate, not frozen)?
  - is anything actually in its next cell?
  - how many steps did it really sit still, and did it move again before the episode ended?
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, int(os.environ.get("SEEDS", "144")) + 1))


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
    env.agv_free_move = True
    env.picker_swap_squat = True
    env.slot_divert = True
    env.picker_reelect = "progress"
    env.clash_sim = True
    env.clash_hysteresis = 20
    ctrl = cp._SqWidePkRateAdaptive(env)

    tail = {}
    ctx = {}
    for t in range(500):
        env.step(ctrl.act())
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
                    c = ctx.setdefault(a.id, {"svc": 0, "nopath": 0, "blocked": 0, "free": 0, "n": 0})
                    c["n"] += 1
                    sv = getattr(env, "_service_until", {}) or {}
                    if sv.get(a.id, 0) > t:
                        c["svc"] += 1
                    if not getattr(a, "path", None):
                        c["nopath"] += 1
                    else:
                        nx_, ny_ = a.path[0]
                        occ = (env.grid[CollisionLayers.AGVS, ny_, nx_]
                               or env.grid[CollisionLayers.PICKERS, ny_, nx_])
                        if occ and occ != a.id:
                            c["blocked"] += 1
                        else:
                            c["free"] += 1
    out = []
    for aid, v in tail.items():
        if len(v) >= 95 and len(set(v)) == 1:
            c = ctx[aid]
            out.append((seed, aid, v[0], len(v), c["svc"], c["nopath"], c["blocked"], c["free"]))
    return out


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        res = pool.map(one, SEEDS)
    rows = [r for sub in res for r in sub]
    print("FROZEN CARRYING AGVs across %d episodes: %d instances "
          "(= %.2f per episode, ~1 in every %d runs)\n"
          % (len(SEEDS), len(rows), len(rows) / len(SEEDS),
             int(len(SEEDS) / max(1, len(rows)))))
    if not rows:
        print("  none")
    else:
        print("  %-6s %-5s %-9s %-7s %-7s %-8s %-9s %s"
              % ("seed", "agv", "cell", "steps", "in svc", "no path", "blocked", "next cell FREE"))
        for r in sorted(rows):
            print("  %-6d %-5d %-9s %-7d %-7d %-8d %-9d %d" % r)
    with open("results/frozen_instances.txt", "w") as f:
        for r in sorted(rows):
            f.write("%s\n" % (r,))
