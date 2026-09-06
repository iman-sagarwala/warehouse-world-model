"""SPACE-TIME RESERVATIONS (cooperative A*) vs the snapshot planner.

`care_for_agents=True` marks every currently-occupied cell as blocked, so A* plans as though robots were
shelves. Measured cost (seed 11, picker 13): thrown 30-46 steps away three times while 6-10 steps from
its goal, +90 steps of detour, and the AGV it was committed to waited 138 steps.

With reservations, every robot's published `path` becomes (cell, time) occupancy and the planner asks
"will this cell be busy when I ARRIVE" instead of "is it busy now". Edge reservations forbid two robots
swapping through each other. Waiting is a legal search action; the returned route has waits collapsed
out, since a blocked robot NOOPs on its own.

Sweeps the horizon `st_window`: too short and it degenerates to plain A*, too long and it plans against
predictions that will have gone stale.
"""
import csv
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
NPROC = int(os.environ.get("NPROC", "8"))
SEEDS = list(range(1, 145))
ARMS = ["off", "st8", "st16", "st32"]


def one(job):
    arm, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, Action, CollisionLayers
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp

    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=STEPS)
    dm.seed_initial(env, n=n)
    env.picker_service_steps = 8
    env.station_service_steps = 6
    env.station_headway = True
    env.station_exit_priority = True
    env.free_pod_return = True
    if arm != "off":
        env.spacetime_reservations = True
        env.st_window = int(arm[2:])
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, delivered, podwait = 0.0, 0, False, 0, 0
    hist = {}
    while not done and t < STEPS:
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        for a in env.agents:
            if (a.type == AgentType.AGV and a.carrying_shelf is None
                    and a.req_action == Action.TOGGLE_LOAD
                    and env.grid[CollisionLayers.SHELVES, a.y, a.x]
                    and not env.grid[CollisionLayers.PICKERS, a.y, a.x]):
                podwait += 1
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id, []).append((a.x, a.y))
        done = all(term) or all(trunc)
    frozen = sum(1 for v in hist.values() if len(v) >= 95 and len(set(v)) == 1)
    return (arm, seed, round(onv, 1), delivered, podwait, frozen)


def report(rows, lo, hi, label):
    D = {a: {} for a in ARMS}
    DL = {a: 0 for a in ARMS}
    PW = {a: 0 for a in ARMS}
    FR = {a: 0 for a in ARMS}
    for arm, s, v, dl, pw, fr in rows:
        if not (lo <= s <= hi):
            continue
        D[arm][s] = v
        DL[arm] += dl
        PW[arm] += pw
        FR[arm] += fr
    ss = list(range(lo, hi + 1))
    print("\n=== %s (seeds %d-%d) ===" % (label, lo, hi))
    print("%-8s %11s %10s %12s %12s %10s %9s" % ("arm", "mean value", "delivered", "pod-wait",
                                                 "frozen AGVs", "%% vs off", "t vs off"))
    for a in ARMS:
        v = [D[a][s] for s in ss]
        if a == "off":
            tt, pc = "-", "-"
        else:
            d = [D[a][s] - D["off"][s] for s in ss]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
            base = sum(D["off"][s] for s in ss)
            pc = "%+.2f%%" % (100.0 * sum(d) / base) if base else "-"
        print("%-8s %11.2f %10d %12d %12d %10s %9s" % (a, sum(v) / len(v), DL[a], PW[a], FR[a], pc, tt))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/spacetime.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "delivered", "pod_wait", "frozen"])
        w.writerows(rows)
    report(rows, 1, 72, "OFF-PEAK")
    report(rows, 73, 144, "PEAK")
    report(rows, 1, 144, "POOLED")
