"""HOW MUCH of the future is useful? Sweep the FORESIGHT WINDOW.

The true-VoPI test (2026-08-01) was ALL-OR-NOTHING: the rollout either saw every arrival inside its
horizon or none. It came back -11.23 (-3.43%, t=-5.98) -- perfect foresight is HARMFUL. But that does
not distinguish two very different stories:
   (a) ALL foresight is harmful -- acting on any future demand is a bad trade, or
   (b) TOO MUCH foresight is harmful -- a SHORT window is actionable (a robot can genuinely be in the
       right place in 10 steps) while a long one just distorts present decisions with work that
       reactive re-planning would have picked up anyway.
If (b), the curve is non-monotonic: positive for small W, crossing zero, negative for large W -- and
the peak is the "useful prediction horizon", a far more interesting number than a flat null.

W = 0 is the plain champion (no foresight, the control). W = 999 reproduces the full-foresight arm.
Everything runs on EXOGENOUS demand, so every arm faces identical orders and the foresight is genuine.

Env: SEEDS, NPROC, OUT.  CSV: window,agvs,pickers,seed,on_time_value
"""
import csv
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = int(os.environ.get("SEEDS", "120"))
NPROC = int(os.environ.get("NPROC", "8"))
OUT = os.environ.get("OUT", "results/foresight_window.csv")
FLEETS = [(4, 4), (6, 6), (8, 8), (4, 8), (8, 4), (9, 9)]
WINDOWS = [float(w) for w in os.environ.get("WINDOWS", "0,10,25,50,100,999").split(",")]


def one(job):
    w, agv, pk, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    from congestion_policies import _SqWidePkRateAdaptive, _FakeOrder

    class _Win(_SqWidePkRateAdaptive):
        FORESIGHT_W = w

        def _future_arrivals(self, now, horizon):
            if self.FORESIGHT_W <= 0:
                return []                       # W=0 -> exactly the plain champion (control arm)
            dm = getattr(self.env, "demand_model", None)
            if dm is None:
                return []
            cut = min(horizon, now + self.FORESIGHT_W)      # only see this far ahead
            return [(t, _FakeOrder(s.x, s.y, v, dl, -1000 - i))
                    for i, (t, s, v, dl) in enumerate(dm.future_arrivals(now, cut))]

    env = gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS)
    env.demand_model.seed_initial(env, n=12)
    ctrl = _Win(env)
    onv, t, done = 0.0, 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return (w, agv, pk, seed, round(onv, 1))


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["window", "agvs", "pickers", "seed", "on_time_value"])
        wr.writerows(rows)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows, have = [], set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((float(r["window"]), int(r["agvs"]), int(r["pickers"]), int(r["seed"]),
                             float(r["on_time_value"])))
                have.add((float(r["window"]), int(r["agvs"]), int(r["pickers"]), int(r["seed"])))
    jobs = [(w, a, p, s) for w in WINDOWS for (a, p) in FLEETS for s in range(SEEDS)
            if (w, a, p, s) not in have]
    print(f"foresight-window: {len(jobs)} runs, windows={WINDOWS}, nproc={NPROC}", flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k, res in enumerate(pool.imap_unordered(one, jobs, chunksize=4), 1):
                rows.append(res)
                if k % 100 == 0:
                    _write(rows)
                    print(f"  {k}/{len(jobs)}", flush=True)
    _write(rows)
    print("foresight-window: DONE", flush=True)


if __name__ == "__main__":
    main()
