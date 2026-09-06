"""PROGRESS AGING: rank clash yielding by starvation instead of loop order.

Under the legacy rule `_yields_to` returns True, so whichever robot the loop reaches first yields, and
nothing prevents the SAME robot yielding forever. That is the starvation mechanism behind the path
freeze -- picker 13 (seed 11) held a fixed goal for 139 steps while its distance went
10 -> 20 -> 46 -> 35 -> 21 -> 9 -> 30 -> 18 -> 13 -> 1, moving on 78% of steps, and the AGV it was
committed to waited 138 steps.

`progress_aging` ranks by steps-since-last-improvement on best-ever distance: the longest-starved robot
holds its route and the others go around it. Unlike `require_reroute`, this changes only WHO yields and
never forces a robot into occupied space -- so the hypothesis is that it avoids the peak penalty that
sank the earlier arms (peak t=-2.00).

Also runs it combined with the sidestep rule, since those are orthogonal (who yields vs how they yield).
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
ARMS = ["off", "aging", "aging+step"]


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
        env.progress_aging = True
    if arm == "aging+step":
        env.clash_choose = "step"
        env.require_reroute = True
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
    print("%-14s %11s %10s %13s %12s %9s" % ("arm", "mean value", "delivered", "pod-wait",
                                             "frozen AGVs", "t vs off"))
    for a in ARMS:
        v = [D[a][s] for s in ss]
        if a == "off":
            tt = "-"
        else:
            d = [D[a][s] - D["off"][s] for s in ss]
            m = sum(d) / len(d)
            sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
            tt = "%+.2f" % (m / (sd / len(d) ** 0.5)) if sd else "inf"
        print("%-14s %11.2f %10d %13d %12d %9s" % (a, sum(v) / len(v), DL[a], PW[a], FR[a], tt))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/progress_aging.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "seed", "on_time_value", "delivered", "pod_wait", "frozen"])
        w.writerows(rows)
    report(rows, 1, 72, "OFF-PEAK")
    report(rows, 73, 144, "PEAK")
    report(rows, 1, 144, "POOLED")
