"""M2 GATE under CHAMPION v6 -- the bounding pair only (user directive: just these two first).

  clairvoyant  router reads GROUND-TRUTH debris the tick it spawns (perfect information, given free)
  ignore       router is blind to debris (b_hard=1.1 belief routing); robots discover it by collision

The gap clairvoyant-minus-ignore IS the value of perfect disturbance information. The standing M2
negative (gap ~ 0 even at 10x debris) was measured on pre-liveness dynamics with slack everywhere.
v6's warehouse has 43% less waiting and disciplined one-wide-lane queues -- if a blocked cell is ever
going to cost something, it is now. If the gap is still ~0 at 10x, the gate is shut and M2 closes as
a strengthened negative; the belief map only auditions if the gap exists.

Day-list, 8x6, 144 paired seeds, rates 0.002 (calibrated) and 0.037 (10x).
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
ARMS = ["clairvoyant", "ignore"]
RATES = [0.002, 0.037]


def one(job):
    arm, rate, seed = job
    import numpy as np
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
    from wwm_sim.demand import DemandModel
    from wwm_sim.rumor_map import BetaRumorMap
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
    env.disturb_rate = rate
    env.disturb_amnesty_rate = 0.037
    env._disturb_rng = np.random.RandomState(10_000 + seed)
    env.rumor_map = BetaRumorMap(env.grid_size)
    env.los_sensing = True
    if arm == "ignore":
        env.use_belief_routing = True
        env.b_hard = 1.1                 # threshold above any belief -> router never sees debris
    ctrl = cp._SqWidePkRateAdaptive(env)
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
    return (arm, rate, seed, round(onv, 1), frozen)


def tstat(diffs):
    m = sum(diffs) / len(diffs)
    sd_ = st.pstdev(diffs) * (len(diffs) / (len(diffs) - 1)) ** 0.5
    return m / (sd_ / len(diffs) ** 0.5) if sd_ else float("inf")


if __name__ == "__main__":
    jobs = [(a, r, s) for a in ARMS for r in RATES for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/m2_gate_v6.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "rate", "seed", "on_time_value", "frozen"])
        w.writerows(rows)
    print("M2 GATE under v6 -- value of PERFECT disturbance information (clairvoyant minus ignore)\n")
    for rate in RATES:
        D = {a: {} for a in ARMS}
        FR = {a: 0 for a in ARMS}
        for a, r, s, v, fr in rows:
            if r == rate:
                D[a][s] = v
                FR[a] += fr
        d = [D["clairvoyant"][s] - D["ignore"][s] for s in SEEDS]
        base = sum(D["ignore"].values())
        print("  rate %.3f (%s):  clairvoyant %.2f   ignore %.2f   VoPI %+0.2f/ep (%+.2f%%)  t=%+.2f"
              % (rate, "calibrated" if rate < 0.01 else "10x",
                 sum(D["clairvoyant"].values()) / len(SEEDS),
                 sum(D["ignore"].values()) / len(SEEDS),
                 sum(d) / len(d), 100.0 * sum(d) / base, tstat(d)))
        print("      frozen: clairvoyant %d, ignore %d" % (FR["clairvoyant"], FR["ignore"]))
