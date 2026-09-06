"""STREAM ladder + route-algorithm test, dense map, v6 stack, 144 paired seeds.

(a) FIFO vs rush vs champion on the STREAM regime (arrivals over time, seed_initial(n=12), no
    day-list) -- the M1 closeout run: every liveness-era number so far is day-list.
(b) champion-Yen (the ladder arm) vs champion-A*shortest (K_ROUTES=1).
    SHIP RULE (user, pre-stated): K_ROUTES=1 ships for BOTH regimes if stream t >= 2, OR pooled
    day+stream t >= 2 (day-list side: mean diff +5.35, sd 38.44, n 144, from results of the
    2026-08-10 day-list run).
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
ARMS = ["fifo", "rush", "champion", "champ_astar1"]

DAY_MEAN, DAY_SD, DAY_N = 5.35, 38.44, 144   # day-list A*-minus-Yen diffs, 2026-08-10 run


def one(job):
    arm, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, Action, CollisionLayers
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    import sim_dashboard as sd
    import sim_priority as sp

    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    env.demand_model = dm
    dm.seed_initial(env, n=12)          # STREAM: no day-list; arrivals flow over the episode
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
    if arm == "fifo":
        ctrl = sd.FIFOController(env)
    elif arm == "rush":
        ctrl = sp.RushValueController(env)
    elif arm == "champ_astar1":
        ctrl = type("_K1", (cp._SqWidePkRateAdaptive,), {"K_ROUTES": 1})(env)
    else:
        ctrl = cp._SqWidePkRateAdaptive(env)
    onv, delivered = 0.0, 0
    tail = {}
    for t in range(500):
        _, rew, _, _, _ = env.step(ctrl.act())
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), delivered, frozen)


def tstat(diffs):
    m = sum(diffs) / len(diffs)
    sd_ = st.pstdev(diffs) * (len(diffs) / (len(diffs) - 1)) ** 0.5
    return m / (sd_ / len(diffs) ** 0.5) if sd_ else float("inf")


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    with open("results/stream_ladder.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "delivered", "frozen"])
        w.writerows(rows)
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for a, s, v, dl, fr in rows:
        D[a][s] = v
        DL[a] += dl
        FR[a] += fr
    print("STREAM LADDER (dense map, v6 stack), 144 paired seeds\n")
    print("%-14s %11s %9s %10s %13s %10s" % ("arm", "mean value", "vs FIFO", "delivered",
                                             "frozen AGVs", "t vs rush"))
    fifo = sum(D["fifo"].values())
    for a in ("fifo", "rush", "champion"):
        v = [D[a][s] for s in SEEDS]
        pc = "-" if a == "fifo" else "%+.1f%%" % (100.0 * (sum(v) - fifo) / fifo)
        if a == "rush":
            tt = "-"
        else:
            d = [D[a][s] - D["rush"][s] for s in SEEDS]
            tt = "%+.2f" % tstat(d)
        print("%-14s %11.2f %9s %10d %13d %10s" % (a, sum(v) / len(v), pc, DL[a], FR[a], tt))

    d_s = [D["champ_astar1"][s] - D["champion"][s] for s in SEEDS]
    t_s = tstat(d_s)
    m_s = sum(d_s) / len(d_s)
    sd_s = st.pstdev(d_s) * (len(d_s) / (len(d_s) - 1)) ** 0.5
    # pooled day+stream from summary stats (day per-seed diffs not retained)
    n_p = DAY_N + len(d_s)
    m_p = (DAY_MEAN * DAY_N + m_s * len(d_s)) / n_p
    var_p = ((DAY_N - 1) * DAY_SD ** 2 + (len(d_s) - 1) * sd_s ** 2
             + DAY_N * (DAY_MEAN - m_p) ** 2 + len(d_s) * (m_s - m_p) ** 2) / (n_p - 1)
    t_p = m_p / ((var_p ** 0.5) / n_p ** 0.5)
    print("\nROUTE TEST -- A*-shortest (K_ROUTES=1) minus Yen's (k=3), champion stack:")
    print("  stream: diff %+.2f (%+.2f%%)  t=%+.2f   frozen yen %d / astar %d"
          % (m_s, 100.0 * sum(d_s) / sum(D["champion"].values()), t_s,
             FR["champion"], FR["champ_astar1"]))
    print("  day-list (prior run): diff +5.35  t=+1.67")
    print("  POOLED day+stream (288): diff %+.2f  t=%+.2f" % (m_p, t_p))
    ship = (t_s >= 2) or (t_p >= 2)
    print("  SHIP RULE (stream t>=2 OR pooled t>=2): %s"
          % ("SHIP K_ROUTES=1 for both regimes" if ship else "KEEP Yen's k=3"))
