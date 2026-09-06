"""PRE-REGISTERED CONFIRMATION: champion (RATE_ALPHA=5) vs RATE_ALPHA=7, 288 paired seeds.

The extended sweep showed a monotone alpha climb (5.5/6/6.5/7/8 all positive, peak ~7, +0.9%) with
both split-halves positive from 6.5 up — but pooled t=+2.56 is below the |t|>=3 bar. Ship rule,
stated before this run: ALPHA=7 BECOMES CHAMPION IFF pooled t >= 3 AND both split-halves positive AND
frozen = 0. Otherwise the shipped alpha=5 stands and the trend is recorded as sub-threshold.

Seeds 145-288 wrap the diurnal window index (n_windows=162) but draw fresh arrivals/values — new data,
same day-shape coverage.
"""
import csv
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 289))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = ["champion", "alpha7"]


def one(job):
    arm, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
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
    C = cp._SqWidePkRateAdaptive
    if arm == "alpha7":
        C = type("_A7", (C,), {"RATE_ALPHA": 7.0})
    ctrl = C(env)
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
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    with open("results/alpha7_confirm.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "frozen"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, fr in rows:
        D[a][s] = v
        FR[a] += fr
    d = [D["alpha7"][s] - D["champion"][s] for s in SEEDS]
    ev = [x for s, x in zip(SEEDS, d) if s % 2 == 0]
    od = [x for s, x in zip(SEEDS, d) if s % 2 == 1]
    base = sum(D["champion"].values())
    print("ALPHA=7 CONFIRMATION, 288 paired seeds (pre-registered: ship iff t>=3, halves>0, frozen 0)")
    print("  champion mean %.2f   alpha7 mean %.2f   (%+.2f%%)"
          % (sum(D["champion"].values()) / len(SEEDS), sum(D["alpha7"].values()) / len(SEEDS),
             100.0 * sum(d) / base))
    print("  pooled t = %+.2f    split-half t = %+.2f / %+.2f" % (tstat(d), tstat(ev), tstat(od)))
    print("  frozen: champion %d, alpha7 %d" % (FR["champion"], FR["alpha7"]))
    ship = tstat(d) >= 3 and tstat(ev) > 0 and tstat(od) > 0 and FR["alpha7"] == 0
    print("  VERDICT: %s" % ("SHIP alpha=7" if ship else "alpha=5 STANDS (trend sub-threshold)"))
