"""STREAM-REGIME MPC (USER DESIGN 2026-08-17): does the self-tuner work when the future is unseen?

Arms (all on the live stream, orders arriving unpredictably, battery at canonical compression):
  fixed   m3 with shipped constants
  mpc_a   self-tuner whose forks contain ONLY the tasks currently visible (no arrivals occur in
          the imagined future -- honest and myopic; this is the fork's natural behaviour, since
          rollouts never call dm.step)
  mpc_b   self-tuner whose forks inject BELIEF arrivals: orders sampled from the demand
          statistics the robots legitimately know (base rate, diurnal curve, hot-pod weights) --
          "future areas of focus", not the actual future.

Same seeds across arms; the real arrival schedule is exogenous and identical under every policy.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = ([int(x) for x in os.environ["SEEDLIST"].split(",")] if os.environ.get("SEEDLIST")
         else list(range(1, 19)) + list(range(73, 91)))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = os.environ.get("ARMS", "fixed,mpc_a,mpc_b").split(",")
CONFIG = os.environ.get("CONFIG", "large-8-6")


def one(job):
    arm, seed = job
    import numpy as np
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
    from wwm_sim.demand import DemandModel
    import importlib.util
    spec = importlib.util.spec_from_file_location("m3b", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
    m3b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3b)
    os.environ["M3SPC"] = "1500"

    _sz, _na, _npk = CONFIG.split("-")
    _geom = _sz if _sz.endswith(("dense", "dual")) else _sz + "dense"
    env = gym.make("wwm_sim-%s-%sagvs-%spickers-globalobs-v1" % (_geom, _na, _npk)).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    m3b.setup_bays(env)
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    dm.shelfs = [s for s in dm.shelfs if s.id not in env._charger_bay_ids]
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_initial(env, n=n)          # STREAM: no seed_day_list -- arrivals come via dm.step
    for k, v in dict(picker_service_steps=8, station_service_steps=6, station_headway=True,
                     station_exit_priority=True, free_pod_return=True, picker_free_move="committed",
                     picker_final_step=True, station_side_keepout=True, keepout_top=True,
                     station_divert=True, swap_return_drop=True, picker_swap=True,
                     picker_swap_squat=True, agv_free_move=True, slot_divert=True,
                     picker_reelect="progress", clash_sim=True, clash_hysteresis=20).items():
        setattr(env, k, v)

    ctrl_arm = "m3" if arm == "fixed" else "m3mpc"
    ctrl, bc = m3b.make_controller(ctrl_arm, env)
    rng = np.random.RandomState(7000 + seed)
    for a in env.agents:
        bc.battery.level[a.id] = float(rng.uniform(0.15, 1.0))

    if arm == "mpc_b":
        # BELIEF FORKS: rollouts inject arrivals sampled from known demand statistics.
        import copy as _copy
        base_rollout = None

        def belief_rollout(self, setting, t0, horizon=100):
            env2, c2 = _copy.deepcopy((self.env, self))
            c2._in_fork = True
            c2._mpc_apply(setting)
            dm2 = env2.demand_model
            brng = np.random.RandomState(90000 + seed * 7 + t0)
            breach0 = {a.id for a in env2.agents
                       if c2.battery.level.get(a.id, 1.0) < 0.10}
            onv = 0.0
            for h in range(horizon):
                lam = dm2.rate * dm2._diurnal(t0 + h)
                for _ in range(int(brng.poisson(max(0.0, lam)))):
                    dm2._inject(env2, t0 + h)
                env2.step(c2.act())
                for o in getattr(env2, "fulfilled_this_step", []):
                    if o.deadline is not None and t0 + h + 1 <= o.deadline:
                        onv += o.value
            dead = sum(1 for a in env2.agents
                       if c2.battery.level.get(a.id, 1.0) <= 0.02)
            newb = sum(1 for a in env2.agents
                       if c2.battery.level.get(a.id, 1.0) < 0.10 and a.id not in breach0)
            return onv - 100.0 * dead - 20.0 * newb - 50.0 * m3b._battery_risk(c2, env2)

        import types
        ctrl._mpc_rollout = types.MethodType(belief_rollout, ctrl)

    onv = 0.0
    tail = {}
    for t in range(500):
        dm.step(env, t)                # the live stream: real arrivals enter here
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    stranded = sum(1 for _, lv in ctrl.battery.level.items() if lv <= 0.02)
    return (arm, seed, round(onv, 1), frozen, stranded)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    FR = {a: 0 for a in ARMS}
    SD = {a: 0 for a in ARMS}
    for a, s, v, fr, sd in rows:
        D[a][s] = v
        FR[a] += fr
        SD[a] += sd
    n_ = len(SEEDS)
    print("STREAM-REGIME MPC, %d seeds (large-8-6, battery SPC=1500, midday levels)\n" % n_)
    print("%-7s %11s %9s %8s %10s" % ("arm", "mean value", "vs fixed", "frozen", "STRANDED"))
    base = sum(D["fixed"].values()) / n_ if "fixed" in D else 0.0
    for a in ARMS:
        v = sum(D[a].values()) / n_
        pc = "-" if a == "fixed" else "%+.2f%%" % (100.0 * (v - base) / base)
        print("%-7s %11.2f %9s %8d %10d" % (a, v, pc, FR[a], SD[a]))
    if "fixed" in D:
        for a in [x for x in ARMS if x != "fixed"]:
            diff = [D[a][s] - D["fixed"][s] for s in SEEDS]
            m = sum(diff) / n_
            sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
            tt = m / (sd_ / n_ ** 0.5) if sd_ else 0.0
            print("%s vs fixed: %+.2f/ep  t=%+.2f" % (a, m, tt))
