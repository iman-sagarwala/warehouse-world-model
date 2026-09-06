"""M3b GATE PROBE: does the VoPI ceiling turn positive when demand hotspots DRIFT?

On STATIC demand, perfect foresight is proven harmful (-3.4%, t=-6.0) and every anticipation
estimator was null. M3b (drift-calibrated demand + picker staging) is alive ONLY if a moving
hotspot makes anticipation worth something even for an ORACLE. Drift here is calibrated from
the real Instacart sample (data/instacart/drift_curves.json: 3 zone-groups, 11-17%% share
swings over a day-cycle, produce-morning / snacks-afternoon structure).

Arms: foresight window W=0 (reactive control) / 25 / 999 (full future), exogenous demand,
drift ON, fleet 8x8, paired seeds. GATE: any W>0 beats W=0 at t>=2 -> M3b unlocked; else CUT.
"""
import json
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = ([int(x) for x in os.environ["SEEDLIST"].split(",")] if os.environ.get("SEEDLIST")
         else list(range(1, 49)))
WINDOWS = [float(w) for w in os.environ.get("WINDOWS", "0,25,999").split(",")]


def one(job):
    w, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    from congestion_policies import _SqWidePkRateAdaptive, _FakeOrder

    class _Win(_SqWidePkRateAdaptive):
        FORESIGHT_W = w

        def _future_arrivals(self, now, horizon):
            if self.FORESIGHT_W <= 0:
                return []
            dm = getattr(self.env, "demand_model", None)
            if dm is None:
                return []
            cut = min(horizon, now + self.FORESIGHT_W)
            return [(t, _FakeOrder(s.x, s.y, v, dl, -1000 - i))
                    for i, (t, s, v, dl) in enumerate(dm.future_arrivals(now, cut))]

    drift = json.load(open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "instacart", "drift_curves.json")))
    env = gym.make("wwm_sim-large-8agvs-8pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS,
                                   drift={"curves": drift["curves"], "gain": 1.0})
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
    return (w, seed, round(onv, 1))


if __name__ == "__main__":
    jobs = [(w, s) for w in WINDOWS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    D = {w: {} for w in WINDOWS}
    for w, s, v in rows:
        D[w][s] = v
    n_ = len(SEEDS)
    print("M3b GATE PROBE: VoPI under REAL-CALIBRATED DRIFT (8x8, %d seeds)\n" % n_)
    base = sum(D[0.0].values()) / n_
    print("W=0 (reactive)  mean %8.2f\n" % base)
    for w in WINDOWS[1:]:
        diff = [D[w][s] - D[0.0][s] for s in SEEDS]
        m = sum(diff) / n_
        sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
        tt = m / (sd_ / n_ ** 0.5) if sd_ else 0.0
        verdict = "GATE OPENS (anticipation pays under drift)" if tt >= 2 else (
            "harmful under drift too" if tt <= -2 else "flat -> gate stays shut")
        print("W=%-4g mean %8.2f  vs W0 %+7.2f  t=%+.2f  -> %s"
              % (w, sum(D[w].values()) / n_, m, tt, verdict))
