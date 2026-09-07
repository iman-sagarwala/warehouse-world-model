"""Point (c) of the phantom-block limitation, measured instead of predicted.

Phantom hard-blocks (the router refusing a clear cell) come from stale sightings. Until today the
belief map could not clear one at all: decay relaxed alpha and beta toward 1.0 each, i.e. toward a
belief of exactly 0.5, which IS `b_hard` -- so a stale belief approached the routing threshold from
above and never crossed it. A cell seen dirty once stayed blocked forever unless somebody looked
again.

`rest_prior` now sets what an unrefreshed belief decays toward (0.5 reproduces the old behaviour
bit-for-bit). Lowering it lets stale beliefs lapse, which should cut phantoms -- and should also
make the map forget REAL unrefreshed spills, which costs sensitivity. That is the trade-off the
limitation asserts from the mechanism. This measures it.

  phantom episodes / 1,000 steps   the criterion (target <= 1)
  event sensitivity                share of spawned spills ever detected (the proposal's >= 90%)
  on-time value                    whether any of it matters to the warehouse
  debris hits                      whether forgetting real spills actually costs collisions

If a rest_prior exists where phantoms fall under 1 while sensitivity stays over 90% and value does
not move, the criterion is reachable and the "unreachable" reading was wrong. If sensitivity falls
off a cliff first, the trade-off is real and the limitation stands as written.

Outputs results/rest_prior.csv.
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
SEEDS = [int(x) for x in os.environ.get("RPSEEDS",
                                        ",".join(str(i) for i in range(1, 25))).split(",")]
PRIORS = [float(x) for x in os.environ.get("PRIORS", "0.5,0.35,0.2,0.1").split(",")]
OUT = os.environ.get("OUT", "results/rest_prior.csv")
FIELDS = ["prior", "seed", "onv", "ph_episodes", "ph_cellsteps", "events", "detected", "hits"]


def one(job):
    prior, seed = job
    import numpy as np
    from record_race import build
    from wwm_sim.rumor_map import BetaRumorMap
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    env.disturb_rate = 0.02
    env._disturb_rng = np.random.RandomState(4000 + seed)
    env.disturb_dur = (150, 400)
    env.disturb_event_cells = (1, 3)
    env.debris_hold_steps = -1
    rm = BetaRumorMap(env.grid_size, rest_prior=prior)
    rm.obs_reset = True
    env.rumor_map = rm
    env.use_belief_routing = True
    env.b_hard = 0.5
    env.los_sensing = True

    onv = 0.0
    ph_cs, ph_ep = 0, 0
    was = set()
    spawn_t, det_t = {}, {}
    prev = set()
    for t in range(STEPS):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        truth = set(env.disturbed)
        for c in truth - prev:
            spawn_t.setdefault(c, t)
        prev = set(truth)
        blocked = rm.believed_blocked(env.b_hard)
        for c in truth:
            if c in blocked and c not in det_t and c in spawn_t:
                det_t[c] = t
        ph = {c for c in blocked if c not in truth}
        ph_cs += len(ph)
        ph_ep += len(ph - was)
        was = ph
    return dict(prior=prior, seed=seed, onv=round(onv, 1), ph_episodes=ph_ep,
                ph_cellsteps=ph_cs, events=len(spawn_t), detected=len(det_t),
                hits=int(getattr(env, "_debris_hits", 0)))


if __name__ == "__main__":
    jobs = [(p, s) for p in PRIORS for s in SEEDS]
    print("rest-prior sweep: %d priors x %d seeds" % (len(PRIORS), len(SEEDS)), flush=True)
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    D = {p: {} for p in PRIORS}
    for r in rows:
        D[r["prior"]][r["seed"]] = r
    n = len(SEEDS)
    steps = n * STEPS
    base = PRIORS[0]

    print("\nWHAT A STALE BELIEF DECAYS TOWARD -- %d paired seeds, %d step-observations\n"
          % (n, steps))
    print("%-9s %11s %11s %13s %10s %8s %8s"
          % ("rest", "phantoms", "criterion", "sensitivity", "value", "vs base", "hits"))
    print("%-9s %11s %11s %13s %10s %8s %8s"
          % ("prior", "/1,000", "(<= 1)", "(>= 90%)", "", "t", ""))
    for p in PRIORS:
        ep = sum(D[p][s]["ph_episodes"] for s in SEEDS)
        ev = sum(D[p][s]["events"] for s in SEEDS)
        de = sum(D[p][s]["detected"] for s in SEEDS)
        rate = 1000.0 * ep / steps
        sens = 100.0 * de / max(1, ev)
        val = sum(D[p][s]["onv"] for s in SEEDS) / n
        d = [D[p][s]["onv"] - D[base][s]["onv"] for s in SEEDS]
        m = sum(d) / n
        sd = st.pstdev(d) * (n / (n - 1)) ** 0.5 if n > 1 else 0.0
        tt = m / (sd / n ** 0.5) if (sd and p != base) else 0.0
        print("%-9.2f %11.1f %11s %12.1f%% %10.1f %+8.2f %8d"
              % (p, rate, "PASS" if rate <= 1 else "FAIL", sens, val, tt,
                 sum(D[p][s]["hits"] for s in SEEDS)))
    print("\n(0.50 is the shipped map: decay toward exactly b_hard, so a phantom never lapses)")
    print("wrote", OUT)
