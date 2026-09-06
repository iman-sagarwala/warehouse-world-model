"""Definitive max-wait scan: FULL champion stack, all 144 seeds.

The quoted 95-step max was measured under committed+final only (no side-keepout / divert / swap-drop)
and scanned seeds 1-24 (off-peak) only. This runs the complete champion on every seed, including the
peak half where the long waits live, and reports the true worst single pod-wait plus the distribution
and the frozen-AGV audit.

Writes results/maxwait_champion.txt so the answer survives the run.
"""
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
    ctrl = cp._SqWidePkRateAdaptive(env)

    run, lens, tail = {}, [], {}
    worst = (0, None)                       # (length, agv)
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
            if run[i] > worst[0]:
                worst = (run[i], i)
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    lens.extend(run.values())
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (seed, worst[0], worst[1], lens, frozen)


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, SEEDS)
    all_lens = sorted(l for (_s, _w, _a, lens, _f) in rows for l in lens)
    best = max(rows, key=lambda r: r[1])
    frozen = sum(r[4] for r in rows)
    lines = []
    lines.append("MAX-WAIT SCAN -- full champion stack, %d seeds" % len(SEEDS))
    lines.append("")
    lines.append("TRUE MAX WAIT : %d consecutive steps  (seed %d, AGV %s)" % (best[1], best[0], best[2]))
    if all_lens:
        lines.append("distribution  : n=%d  total=%d  p99=%d  p90=%d  median=%d"
                     % (len(all_lens), sum(all_lens), all_lens[int(.99 * (len(all_lens) - 1))],
                        all_lens[int(.90 * (len(all_lens) - 1))], all_lens[len(all_lens) // 2]))
    lines.append("frozen carrying AGVs (audit): %d  (must be 0)" % frozen)
    lines.append("")
    lines.append("top 10 worst episodes:")
    for (s, w, a, _l, _f) in sorted(rows, key=lambda r: -r[1])[:10]:
        lines.append("  seed %-4d  max wait %-4d  (AGV %s)" % (s, w, a))
    out = "\n".join(lines)
    print(out)
    with open("results/maxwait_champion.txt", "w") as f:
        f.write(out + "\n")
