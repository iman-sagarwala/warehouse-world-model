"""FREE POD RETURN -- paired A/B across the whole seed range (off-peak 1-72, peak 73-144).

Upstream TA-RWARE requires a picker to be standing on the cell before an AGV may put a pod back into
storage. When no picker is dispatched to that return rendezvous the AGV requests TOGGLE_LOAD forever
and holds the pod for the rest of the episode. With the flag, a drive unit lowers its own pod; the
picker is still required for the PICK.

Reports the two halves separately -- deadlock is strongly load-dependent (62/72 dead episodes at peak
vs 5/72 off-peak) so a pooled number would hide the effect where it matters.
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
    fpr, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
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
    env.free_pod_return = fpr
    ctrl = cp._SqWidePkRateAdaptive(env)
    onv, t, done, hist, delivered = 0.0, 0, False, {}, 0
    while not done and t < STEPS:
        _, rew, term, trunc, _i = env.step(ctrl.act())
        t += 1
        delivered += int(sum(rew))
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id, []).append((a.x, a.y))
        done = all(term) or all(trunc)
    frozen = sum(1 for v in hist.values() if len(v) >= 95 and len(set(v)) == 1)
    return (fpr, seed, round(onv, 1), frozen, delivered)


def report(rows, lo, hi, label):
    D = {False: {}, True: {}}
    F = {False: 0, True: 0}
    DE = {False: 0, True: 0}
    DL = {False: 0, True: 0}
    for fpr, s, v, fr, dl in rows:
        if not (lo <= s <= hi):
            continue
        D[fpr][s] = v
        F[fpr] += fr
        DE[fpr] += 1 if fr > 0 else 0
        DL[fpr] += dl
    ss = [s for s in range(lo, hi + 1)]
    print("\n=== %s (seeds %d-%d) ===" % (label, lo, hi))
    print("%-22s %11s %9s %13s %15s %10s" % ("arm", "on-time val", "mean", "frozen AGVs",
                                             "dead episodes", "delivered"))
    for fpr, nm in ((False, "baseline"), (True, "+ FREE POD RETURN")):
        v = [D[fpr][s] for s in ss]
        print("%-22s %11.1f %9.2f %13d %10d/%-4d %10d" % (nm, sum(v), sum(v) / len(v), F[fpr],
                                                          DE[fpr], len(ss), DL[fpr]))
    d = [D[True][s] - D[False][s] for s in ss]
    m = sum(d) / len(d)
    sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
    tt = m / (sd / len(d) ** 0.5) if sd else float("inf")
    base = sum(D[False][s] for s in ss)
    print("paired: %+.2f/episode  t=%+.2f  -> %+.2f%%   wins %d / losses %d / ties %d"
          % (m, tt, 100 * sum(d) / base if base else 0,
             sum(1 for x in d if x > 0), sum(1 for x in d if x < 0), sum(1 for x in d if x == 0)))


if __name__ == "__main__":
    jobs = [(f, s) for f in (False, True) for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    with open("results/free_pod_return.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["free_pod_return", "seed", "on_time_value", "frozen_agvs", "delivered"])
        w.writerows(rows)
    report(rows, 1, 72, "OFF-PEAK")
    report(rows, 73, 144, "PEAK")
    report(rows, 1, 144, "POOLED")
