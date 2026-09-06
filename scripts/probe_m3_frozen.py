"""Why does the M3 battery arm freeze carriers? Find frozen instances and name their blockers.

For every carrying AGV motionless over the last 100 steps: what is its next cell, who occupies it,
and what is that occupant doing (charging on a charger cell? for how long?). Confirms or kills the
hypothesis that charger-parked robots are walls on the AGV road network (chargers = shelf cells,
and AGVs drive THROUGH shelf cells).
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

S0 = int(os.environ.get("S0", "1"))
SEEDS = list(range(S0, S0 + int(os.environ.get("SEEDS", "36"))))
NPROC = int(os.environ.get("NPROC", "8"))


def one(seed):
    import numpy as _np
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, CollisionLayers
    from wwm_sim.demand import DemandModel
    import importlib.util
    spec = importlib.util.spec_from_file_location("m3b", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
    m3b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3b)

    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    m3b.setup_bays(env)
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    dm.shelfs = [s_ for s_ in dm.shelfs if s_.id not in env._charger_bay_ids]
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    for k, v in dict(picker_service_steps=8, station_service_steps=6, station_headway=True,
                     station_exit_priority=True, free_pod_return=True, picker_free_move="committed",
                     picker_final_step=True, station_side_keepout=True, keepout_top=True,
                     station_divert=True, swap_return_drop=True, picker_swap=True,
                     picker_swap_squat=True, agv_free_move=True, slot_divert=True,
                     picker_reelect="progress", clash_sim=True, clash_hysteresis=20).items():
        setattr(env, k, v)
    os.environ["M3SPC"] = "1500"
    ctrl, bc = m3b.make_controller("m3", env)
    rng = _np.random.RandomState(7000 + seed)
    for a in env.agents:
        bc.battery.level[a.id] = float(rng.uniform(0.15, 1.0))

    tail = {}
    ctx = {}
    charger_cells = set(bc.battery.chargers)
    for t in range(500):
        env.step(ctrl.act())
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
                    c = ctx.setdefault(a.id, {"blk": {}, "n": 0})
                    c["n"] += 1
                    if getattr(a, "path", None):
                        nx_, ny_ = a.path[0]
                        oa = env.grid[CollisionLayers.AGVS, ny_, nx_]
                        op = env.grid[CollisionLayers.PICKERS, ny_, nx_]
                        occ = oa or op
                        if occ and occ != a.id:
                            o = env.agents[occ - 1]
                            om = None
                            for d in (ctrl.assigned_agvs, ctrl.assigned_pickers):
                                if o in d:
                                    om = d[o].mission_type.name
                            key = ("%s%s" % ("AGV" if o.type == AgentType.AGV else "PK", occ),
                                   om or "none",
                                   "ON-CHARGER" if (o.x, o.y) in charger_cells else "elsewhere")
                            c["blk"][key] = c["blk"].get(key, 0) + 1
    out = []
    for aid, v in tail.items():
        if len(v) >= 95 and len(set(v)) == 1:
            c = ctx[aid]
            top = sorted(c["blk"].items(), key=lambda kv: -kv[1])[:1]
            out.append((seed, aid, v[0], top[0] if top else None))
    return out


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        res = pool.map(one, SEEDS)
    rows = [r for sub in res for r in sub]
    print("FROZEN CARRIERS in m3@1500+midday, %d seeds: %d instances\n" % (len(SEEDS), len(rows)))
    from collections import Counter
    kinds = Counter()
    for (s, aid, cell, top) in rows:
        if top:
            (who, mission, where), cnt = top
            kinds["blocked by %s on %s (mission %s)" % (who[:2], where, mission)] += 1
            print("  seed %-4d agv %-3d @%-9s blocked %3d/100 by %-6s mission=%-9s %s"
                  % (s, aid, str(cell), cnt, who, mission, where))
        else:
            kinds["no blocker recorded (pathless or free)"] += 1
            print("  seed %-4d agv %-3d @%-9s NO blocker recorded" % (s, aid, str(cell)))
    print()
    for k, v in kinds.most_common():
        print("  %-52s %d" % (k, v))
