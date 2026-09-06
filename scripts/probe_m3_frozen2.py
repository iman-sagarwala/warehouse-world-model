"""Second-stage trace of the 12 residual m3 frozen carriers: for each, record its OWN mission
state (type, busy, path length, standing-on-destination?, battery level, on-charger?) and, when
blocked, whether the blocking cell is the carrier's destination. Distinguishes:
  A) dead-zone: RETURNING to own cell, busy=False, path=[] -> never toggles (my pod-drop picking
     the robot's current cell would manufacture exactly this)
  B) charger-wall: blocker parked on a charger that lies on/at the carrier's route/destination
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

FAIL_SEEDS = [91]


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
    for t in range(500):
        env.step(ctrl.act())
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    out = []
    charger_cells = set(bc.battery.chargers)
    for aid, v in tail.items():
        if len(v) >= 95 and len(set(v)) == 1:
            a = env.agents[aid - 1]
            m = ctrl.assigned_agvs.get(a)
            mt = m.mission_type.name if m else "NONE"
            dest = (m.location_x, m.location_y) if m else None
            at_dest = dest == (a.x, a.y) if dest else False
            plen = len(getattr(a, "path", []) or [])
            lvl = bc.battery.level.get(a.id, 1.0)
            blk = ""
            if plen:
                nx_, ny_ = a.path[0]
                occ = (env.grid[CollisionLayers.AGVS, ny_, nx_]
                       or env.grid[CollisionLayers.PICKERS, ny_, nx_])
                if occ and occ != a.id:
                    o = env.agents[occ - 1]
                    olvl = bc.battery.level.get(o.id, 1.0)
                    blk = ("blocker=%s@(%d,%d) lvl=%.2f oncharger=%s cell-is-my-dest=%s"
                           % (("AGV" if o.type == AgentType.AGV else "PK") + str(occ),
                              o.x, o.y, olvl, (o.x, o.y) in charger_cells,
                              dest == (nx_, ny_)))
            shelf_here = bool(env.grid[CollisionLayers.SHELVES, a.y, a.x])
            out.append((seed, aid, (a.x, a.y), mt, dest, at_dest, plen,
                        getattr(a, "busy", None), round(lvl, 3),
                        (a.x, a.y) in charger_cells, shelf_here, blk))
    return out


if __name__ == "__main__":
    with mp.Pool(6) as pool:
        res = pool.map(one, FAIL_SEEDS)
    rows = [r for sub in res for r in sub]
    print("RESIDUAL FROZEN TRACE, %d seeds: %d instances\n" % (len(FAIL_SEEDS), len(rows)))
    for (s, aid, cell, mt, dest, at_dest, plen, busy, lvl, on_chg, shelf_here, blk) in rows:
        print("  seed %-4d agv %-2d @%-9s mission=%-9s dest=%-9s AT-DEST=%-5s path=%-3d "
              "busy=%-5s lvl=%-6s on-charger=%-5s shelf-under=%-5s %s"
              % (s, aid, str(cell), mt, str(dest), at_dest, plen, busy, lvl,
                 on_chg, shelf_here, blk))
