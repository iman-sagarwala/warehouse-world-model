"""Two open questions from the stall decomposition.

Q1. The pickers_free oracle is worth only +1.4% at PEAK, where the queue drains by deadline expiry
    rather than delivery, so nothing helps much. Is it worth more OFF-PEAK, where value is still
    winnable? That number, not the peak one, decides whether picker-side work is worth doing.

Q2. The decomposition filed 31.5% of non-moving AGV-time under "load/unload (real action)". But an AGV
    waiting at a pod re-requests TOGGLE_LOAD every step and `_execute_load` silently no-ops while no
    picker is present, so an unknown share of that bucket is WAITING, not acting. Split it by checking
    whether the toggle actually changed carrying state.

Arms: baseline vs pickers_free, run on both demand halves.
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


def one(job):
    oracle, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType, Action
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
    if oracle:
        env.pickers_free = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, delivered = 0.0, 0, False, 0
    toggle_real, toggle_waste = 0, 0
    while not done and t < STEPS:
        pre_carry = {a.id: (a.carrying_shelf is not None) for a in env.agents
                     if a.type == AgentType.AGV}
        pre_act = {a.id: None for a in env.agents if a.type == AgentType.AGV}
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        for a in env.agents:
            if a.type != AgentType.AGV or a.req_action != Action.TOGGLE_LOAD:
                continue
            # did the toggle actually do anything? carrying state flips on a real load/unload
            if (a.carrying_shelf is not None) != pre_carry.get(a.id):
                toggle_real += 1
            else:
                toggle_waste += 1
        done = all(term) or all(trunc)
    return (oracle, seed, round(onv, 1), delivered, toggle_real, toggle_waste)


def report(rows, lo, hi, label):
    D = {False: {}, True: {}}
    TR = {False: 0, True: 0}
    TW = {False: 0, True: 0}
    DL = {False: 0, True: 0}
    for orc, s, v, dl, tr, tw in rows:
        if not (lo <= s <= hi):
            continue
        D[orc][s] = v
        TR[orc] += tr
        TW[orc] += tw
        DL[orc] += dl
    ss = list(range(lo, hi + 1))
    print("\n=== %s (seeds %d-%d) ===" % (label, lo, hi))
    print("%-22s %10s %10s %14s %16s" % ("arm", "mean value", "delivered",
                                         "toggles: real", "toggles: no-op wait"))
    for orc, nm in ((False, "baseline"), (True, "pickers_free (oracle)")):
        v = [D[orc][s] for s in ss]
        print("%-22s %10.2f %10d %14d %16d" % (nm, sum(v) / len(v), DL[orc], TR[orc], TW[orc]))
    d = [D[True][s] - D[False][s] for s in ss]
    m = sum(d) / len(d)
    sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
    tt = m / (sd / len(d) ** 0.5) if sd else float("inf")
    base = sum(D[False][s] for s in ss)
    print("oracle headroom: %+.2f/episode  t=%+.2f  -> %+.2f%%" % (m, tt, 100 * sum(d) / base if base else 0))
    tot = TR[False] + TW[False]
    if tot:
        print("baseline TOGGLE_LOAD steps: %d real / %d wasted waiting (%.1f%% of the bucket is WAITING)"
              % (TR[False], TW[False], 100.0 * TW[False] / tot))


if __name__ == "__main__":
    jobs = [(o, s) for o in (False, True) for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/picker_headroom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pickers_free", "seed", "on_time_value", "delivered", "toggle_real", "toggle_wait"])
        w.writerows(rows)
    report(rows, 1, 72, "OFF-PEAK")
    report(rows, 73, 144, "PEAK")
