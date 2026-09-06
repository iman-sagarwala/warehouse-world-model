"""Record paired fixed-vs-MPC episodes as compact JSON for the sandbox's side-by-side race view.

For each (config, seed): run both arms on the identical world and log per step every agent's
position + carrying flag, battery levels, cumulative on-time value, and hard-dead count; for the
MPC arm also the adopted-settings timeline. Output: results/races.json.
"""
import json
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

RACES = [(c, s) for c in ("large-12-8", "extralarge-16-9") for s in (77, 90, 93, 121, 133, 140)]
STEPS = 500
SPC = 1500.0


def build(config, seed, stress=False, stream=False):
    import gymnasium as gym
    import numpy as np
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import importlib.util
    spec = importlib.util.spec_from_file_location("m3b", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
    m3b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3b)
    # stress day: COMPRESSED battery (dies within one day) + low start levels -- the regime
    # where charging policy genuinely swings outcomes (m3 vs stage0 = -6% there)
    os.environ["M3SPC"] = "300" if stress else str(SPC)
    size, agvs, pk = config.split("-")
    geom = size if size.endswith(("dense", "dual")) else size + "dense"
    env = gym.make("wwm_sim-%s-%sagvs-%spickers-globalobs-v1" % (geom, agvs, pk)).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    m3b.setup_bays(env)
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    dm.shelfs = [s for s in dm.shelfs if s.id not in env._charger_bay_ids]
    env.demand_model = dm
    n = dm.warm_start_n()
    if not stream:
        dm.seed_day_list(env, horizon=500)   # wave regime: whole day visible from t=0
    dm.seed_initial(env, n=n)
    for k, v in dict(picker_service_steps=8, station_service_steps=6, station_headway=True,
                     station_exit_priority=True, free_pod_return=True, picker_free_move="committed",
                     picker_final_step=True, station_side_keepout=True, keepout_top=True,
                     station_divert=True, swap_return_drop=True, picker_swap=True,
                     picker_swap_squat=True, agv_free_move=True, slot_divert=True,
                     picker_reelect="progress", clash_sim=True, clash_hysteresis=20).items():
        setattr(env, k, v)
    ctrl, bc = m3b.make_controller("m3", env)
    rng = np.random.RandomState(7000 + seed)
    lo, hi = (0.05, 0.50) if stress else (0.15, 1.0)   # stress day: fleet starts low
    for a in env.agents:
        bc.battery.level[a.id] = float(rng.uniform(lo, hi))
    return env, ctrl


def one(job):
    config, seed, arm = job[:3]
    stress = bool(job[3]) if len(job) > 3 else False
    stream = bool(job[4]) if len(job) > 4 else False
    import m3_mpc as M              # config-independent helpers: apply_setting/moves/rollout
    from wwm_sim.warehouse import AgentType
    env, ctrl = build(config, seed, stress, stream)
    cur = M.DEFAULT
    M.apply_setting(ctrl, cur)
    stats = {mv: [0, 0.0] for mv in M.moves_for(env)}
    onv = 0.0
    pos, carry, lvl, val, dead = [], [], [], [], []
    adopted = []
    dm_ = env.demand_model
    for t in range(STEPS):
        if stream:
            dm_.step(env, t)             # live arrivals; rollout forks stay visible-only
        if arm == "mpc" and t > 0 and t % 50 == 0:
            base = M.rollout_score(env, ctrl, cur, t, 100)
            best_s, best = base, cur
            for mv in M.ucb_pick(stats):
                s_ = M.apply_move(cur, mv)
                if s_ == cur:
                    continue
                sc = M.rollout_score(env, ctrl, s_, t, 100)
                n_, mean = stats[mv]
                stats[mv] = [n_ + 1, mean + (sc - base - mean) / (n_ + 1)]
                if sc > best_s:
                    best_s, best = sc, s_
            if best != cur:
                cur = best
                M.apply_setting(ctrl, cur)
                adopted.append([t] + [round(x, 2) for x in cur])
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        step_pos, cbits = [], 0
        for i, a in enumerate(env.agents):
            step_pos.extend((a.x, a.y))
            if getattr(a, "carrying_shelf", None) is not None:
                cbits |= (1 << i)
        pos.append(step_pos)
        carry.append(cbits)
        lvl.append([int(round(100 * ctrl.battery.level.get(a.id, 1.0))) for a in env.agents])
        val.append(int(round(onv)))
        dead.append(sum(1 for a in env.agents
                        if ctrl.battery.level.get(a.id, 1.0) <= 0.02))
    while len(pos) < 500:      # fast/smoke runs pad to the viewer's fixed 500-step timeline
        pos.append(pos[-1]); carry.append(carry[-1]); lvl.append(lvl[-1])
        val.append(val[-1]); dead.append(dead[-1])
    types = [0 if a.type == AgentType.AGV else 1 for a in env.agents]
    meta = dict(W=env.grid_size[1], H=env.grid_size[0],
                cells=[list(c) for c in sorted(
                    (x, y) for (y, x) in env.action_id_to_coords_map.values()
                    if (x, y) not in {tuple(g) for g in env.goals})],
                goals=[list(g) for g in env.goals],
                bays=[list(b) for b in sorted(env._charger_bays)],
                types=types)
    return (config, seed, arm,
            dict(pos=pos, carry=carry, lvl=lvl, val=val, dead=dead, adopted=adopted), meta)


if __name__ == "__main__":
    jobs = [(c, s, a) for (c, s) in RACES for a in ("fixed", "mpc")]
    with mp.Pool(int(os.environ.get("NPROC", "4"))) as pool:
        res = pool.map(one, jobs)
    out = {}
    for config, seed, arm, arm_data, meta in res:
        key = "%s@%d" % (config, seed)
        if key not in out:
            out[key] = dict(config=config, seed=seed, **meta, arms={})
        out[key]["arms"][arm] = arm_data
    path = os.path.join("results", "races.json")
    json.dump(out, open(path, "w"), separators=(",", ":"), default=int)
    print("saved", path, os.path.getsize(path), "bytes")
    for k, v in out.items():
        f, m = v["arms"]["fixed"], v["arms"]["mpc"]
        print("  %-24s fixed=%d mpc=%d (%+d) dead f/m=%d/%d adoptions=%d"
              % (k, f["val"][-1], m["val"][-1], m["val"][-1] - f["val"][-1],
                 f["dead"][-1], m["dead"][-1], len(m["adopted"])))
