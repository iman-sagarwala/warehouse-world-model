"""WEIGHTS RE-SWEEP under champion v5 (the user's "redo weights"). One knob away from the shipped
champion per arm, dense map, v5 env stack, 144 paired seeds. The prior sweep ran on the standard map
before the liveness stack existed; the dense map's dynamics (station discipline, re-election,
trajectory clashes) may move the optima.

Arms: champion | URG_W 0/8-everywhere | RATE_ALPHA 4/6 | SEQ_DEPTH 3 | W_SYNC 0.15
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
ARMS = ["champion", "urg0all", "urg8all", "alpha4", "alpha6", "seq3", "wsync015"]


def _cls(arm):
    import congestion_policies as cp
    C = cp._SqWidePkRateAdaptive
    if arm == "champion":
        return C
    if arm == "urg8all":
        return type("_W_urg8", (C,), {"URG_W_DAYLIST": 8.0, "URG_W_STREAM": 8.0})
    if arm == "urg0all":
        return type("_W_urg0", (C,), {"URG_W_DAYLIST": 0.0, "URG_W_STREAM": 0.0})
    if arm == "alpha4":
        return type("_W_a4", (C,), {"RATE_ALPHA": 4.0})
    if arm == "alpha6":
        return type("_W_a6", (C,), {"RATE_ALPHA": 6.0})
    if arm == "seq3":
        return type("_W_s3", (C,), {"SEQ_DEPTH": 3})
    if arm == "wsync015":
        return type("_W_w015", (C,), {"W_SYNC": 0.15})
    raise KeyError(arm)


def one(job):
    arm, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
    from wwm_sim.demand import DemandModel

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
    ctrl = _cls(arm)(env)
    onv = 0.0
    tail = {}
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), frozen)


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    with open("results/weights_v5.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "frozen"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, fr in rows:
        D[a][s] = v
        FR[a] += fr
    print("WEIGHTS RE-SWEEP under v5, 144 paired seeds (one knob away from champion per arm)\n")
    print("%-10s %11s %9s %13s" % ("arm", "mean value", "t vs champ", "frozen AGVs"))
    for a in ARMS:
        v = [D[a][s] for s in SEEDS]
        if a == "champion":
            tt = "-"
        else:
            d = [D[a][s] - D["champion"][s] for s in SEEDS]
            m = sum(d) / len(d)
            sd_ = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd_ / len(d) ** 0.5)) if sd_ else "inf"
        print("%-10s %11.2f %9s %13d" % (a, sum(v) / len(v), tt, FR[a]))
