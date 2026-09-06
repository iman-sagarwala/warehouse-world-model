"""Per-seed value comparison nobat vs m3 on chosen seeds (env SEEDLIST=comma-separated)."""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDLIST = [int(x) for x in os.environ.get("SEEDLIST", "86,93,121,126").split(",")]


def one(job):
    arm, seed = job
    os.environ["M3SPC"] = "1500"
    import gymnasium as gym
    import wwm_sim  # noqa
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
    ctrl, bc = m3b.make_controller(arm, env)
    if bc is not None:
        import numpy as np
        rng = np.random.RandomState(7000 + seed)
        for a in env.agents:
            bc.battery.level[a.id] = float(rng.uniform(0.15, 1.0))
    onv, d = 0.0, 0
    for t in range(500):
        _, rew, _, _, _ = env.step(ctrl.act())
        d += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    return (arm, seed, round(onv, 1), d)


if __name__ == "__main__":
    jobs = [(a, s) for a in ("nobat", "m3") for s in SEEDLIST]
    with mp.Pool(min(8, len(jobs))) as pool:
        rows = pool.map(one, jobs)
    R = {}
    for a, s, v, d in rows:
        R[(a, s)] = (v, d)
    for s in SEEDLIST:
        nv, nd = R[("nobat", s)]
        mv, md = R[("m3", s)]
        pc = 100 * (mv - nv) / nv if nv else 0.0
        print("seed %-4d nobat value=%-8s del=%-3d | m3 value=%-8s del=%-3d  (%+.0f%%)"
              % (s, nv, nd, mv, md, pc))
