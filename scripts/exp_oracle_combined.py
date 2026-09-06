"""Gaps 3 and 4 of the oracle audit: do the information channels INTERACT, and do the oracle
numbers still hold on current code?

Every value-of-information result in this project tested one channel at a time. The strongest
surviving objection to the anticipation null is therefore that information is COMPLEMENTARY --
knowing future orders may only pay if you also know where the floor will be blocked, and vice
versa, so testing them separately would find nothing either way. This runs them together.

It also re-measures both channels on the CURRENT stack. The published oracle numbers were taken on
harnesses that predate the liveness flags, the charging bays, the battery layer and (for the demand
oracle) the realism audit's exogenous scheduler; the 2026-09-06 benchmark re-measurement showed the
live-stream regime has since moved materially.

  champ    the shipped controller: belief-map routing, no foresight            (control)
  demand   + the rollout sees every future arrival for the rest of the day
  spills   + the router reads GROUND-TRUTH debris instead of its belief map
  both     + both at once

The question is whether `both` beats `demand + spills`. If it does, information is complementary
and the one-at-a-time nulls were underpowered by construction. If it does not, the null composes.

Live-stream days (the only regime where demand foresight is not trivially available, since a wave
day is fully seeded at t=0) with disturbances active. Outputs results/oracle_combined.csv.
"""
import csv
import io
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = [int(x) for x in os.environ.get("ORSEEDS",
                                        ",".join(str(i) for i in range(1, 49))).split(",")]
ARMS = os.environ.get("ARMS", "champ,demand,spills,both").split(",")
OUT = os.environ.get("OUT", "results/oracle_combined.csv")
FIELDS = ["arm", "seed", "onv", "delivered", "debris_hits"]


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    from wwm_sim.rumor_map import BetaRumorMap
    from congestion_policies import _FakeOrder

    see_demand = arm in ("demand", "both")
    see_spills = arm in ("spills", "both")

    env, ctrl = build("large-8-6", seed, stream=True)

    # --- disturbance process, identical across arms (same RNG stream, same seed offset) --------
    env.disturb_rate = 0.02
    env._disturb_rng = np.random.RandomState(4000 + seed)
    env.disturb_dur = (150, 400)
    env.disturb_event_cells = (1, 3)
    env.debris_hold_steps = -1

    if see_spills:
        # clairvoyant: no belief map at all, so find_path reads the true disturbed set
        env.use_belief_routing = False
    else:
        rm = BetaRumorMap(env.grid_size)
        rm.obs_reset = True                       # the shipped update rule
        env.rumor_map = rm
        env.use_belief_routing = True
        env.b_hard = 0.5
        env.los_sensing = True

    if see_demand:
        # the rollout is handed every arrival for the rest of the day, exactly as the VoPI arm did
        dm_ = env.demand_model

        def _oracle_arrivals(self, now, horizon):
            return [(t, _FakeOrder(s.x, s.y, v, dl, -1000 - i))
                    for i, (t, s, v, dl) in enumerate(dm_.future_arrivals(now, horizon))]
        ctrl._future_arrivals = _oracle_arrivals.__get__(ctrl, type(ctrl))

    dm = env.demand_model
    onv, delivered = 0.0, 0
    for t in range(STEPS):
        dm.step(env, t)
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        delivered += len(getattr(env, "deliveries_this_step", []))
    return dict(arm=arm, seed=seed, onv=round(onv, 1), delivered=delivered,
                debris_hits=int(getattr(env, "_debris_hits", 0)))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    D = {a: {} for a in ARMS}
    for r in rows:
        D[r["arm"]][r["seed"]] = r
    n = len(SEEDS)

    def paired(arm, ref="champ"):
        d = [D[arm][s]["onv"] - D[ref][s]["onv"] for s in SEEDS]
        m = sum(d) / n
        sd = st.pstdev(d) * (n / (n - 1)) ** 0.5 if n > 1 else 0.0
        return m, (m / (sd / n ** 0.5) if sd else 0.0)

    print("COMBINED INFORMATION ORACLE -- live-stream days with spills, %d paired seeds\n" % n)
    print("%-8s %9s %10s %8s %10s %9s" % ("arm", "value", "vs champ", "t", "delivered", "hits"))
    eff = {}
    for a in ARMS:
        m, tt = paired(a)
        eff[a] = m
        print("%-8s %9.2f %+10.2f %+8.2f %10.1f %9d"
              % (a, sum(D[a][s]["onv"] for s in SEEDS) / n, m, tt,
                 sum(D[a][s]["delivered"] for s in SEEDS) / n,
                 sum(D[a][s]["debris_hits"] for s in SEEDS)))

    if {"demand", "spills", "both"} <= set(eff):
        add = eff["demand"] + eff["spills"]
        inter = eff["both"] - add
        d = [D["both"][s]["onv"] - D["demand"][s]["onv"] - D["spills"][s]["onv"]
             + D["champ"][s]["onv"] for s in SEEDS]
        m = sum(d) / n
        sd = st.pstdev(d) * (n / (n - 1)) ** 0.5 if n > 1 else 0.0
        t_i = m / (sd / n ** 0.5) if sd else 0.0
        print("\nINTERACTION: both %+.2f  vs  demand+spills %+.2f  ->  %+.2f (t = %+.2f)"
              % (eff["both"], add, inter, t_i))
        print("  a positive, significant interaction means the channels are COMPLEMENTARY and the")
        print("  one-at-a-time nulls were underpowered; ~0 means the null composes.")
    print("\nwrote", OUT)
