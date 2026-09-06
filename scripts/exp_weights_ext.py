"""EXTENDED weights sweep under v5: higher/new RATE_ALPHA and SEQ_DEPTH (user directive).

Motivation: the one-knob sweep showed alpha6 +1.39 and seq3 +0.78 — sub-threshold trends, but alpha's
old standard-map peak was 5 with "6 turns down", so a reversal on the dense map is worth settling.
Arms: alpha 5.5 / 6 / 6.5 / 7 / 8 and SEQ_DEPTH 4 / 7 / 9, all one knob away from the shipped champion
(alpha=5, depth=5). Split-half (evens vs odds) reported for any arm with |t| >= 2, per project rule.
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
ARMS = ["champion", "alpha55", "alpha6", "alpha65", "alpha7", "alpha8", "seq4", "seq7", "seq9"]


def _cls(arm):
    import congestion_policies as cp
    C = cp._SqWidePkRateAdaptive
    if arm == "champion":
        return C
    if arm.startswith("alpha"):
        val = float(arm[5:]) / (10.0 if len(arm[5:]) > 1 else 1.0)
        return type("_X_%s" % arm, (C,), {"RATE_ALPHA": val})
    if arm.startswith("seq"):
        return type("_X_%s" % arm, (C,), {"SEQ_DEPTH": int(arm[3:])})
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


def tstat(diffs):
    m = sum(diffs) / len(diffs)
    sd_ = st.pstdev(diffs) * (len(diffs) / (len(diffs) - 1)) ** 0.5
    return m / (sd_ / len(diffs) ** 0.5) if sd_ else float("inf")


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/weights_ext.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "frozen"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, fr in rows:
        D[a][s] = v
        FR[a] += fr
    print("EXTENDED WEIGHTS SWEEP under v5, 144 paired seeds\n")
    print("%-10s %11s %10s %13s %22s" % ("arm", "mean value", "t vs champ", "frozen AGVs",
                                         "split-half t (ev/odd)"))
    for a in ARMS:
        v = [D[a][s] for s in SEEDS]
        if a == "champion":
            tt, sh = "-", ""
        else:
            d = [D[a][s] - D["champion"][s] for s in SEEDS]
            t_all = tstat(d)
            tt = "%+.2f" % t_all
            if abs(t_all) >= 2.0:
                ev = [D[a][s] - D["champion"][s] for s in SEEDS if s % 2 == 0]
                od = [D[a][s] - D["champion"][s] for s in SEEDS if s % 2 == 1]
                sh = "%+.2f / %+.2f" % (tstat(ev), tstat(od))
            else:
                sh = ""
        print("%-10s %11.2f %10s %13d %22s" % (a, sum(v) / len(v), tt, FR[a], sh))
