"""Threshold OSCILLATION as a controller mode -- the one measured-but-never-built item.

exp_charge_foresight.py (2026-08-24) found that on stress days a *moving* charge threshold is
worth ~7% and a third of the strandings, and that the movement is the whole mechanism: a
SCRAMBLED forecast beat the true one, and a constant threshold at the same mean was worth
nothing. The cause is an asymmetry -- raising theta CAUSES a charge event, lowering it merely
POSTPONES one -- so oscillation ratchets charge frequency up while keeping the mean LOWER.

That was measured through a forecast-shaped wrapper. This builds the mechanism directly, with no
forecast anywhere, and asks the question that decides whether it belongs in the tuner's move set:

  fixed      shipped constant theta (the control)
  osc<A>     theta alternates base +/- A every OSCP steps -- pure oscillation, zero information
  mpc        the shipped self-tuner, which already owns theta as a LEVEL (th+/th- moves)
  mpc_osc    the self-tuner with oscillation layered on top of whatever level it settles at

If osc beats fixed and mpc_osc beats mpc, oscillation is a genuinely new axis and should become a
tuner move. If mpc already captures it, it should not.

Stress days (M3SPC=300 + low starts), where charging binds and theta is load-bearing.
Outputs results/theta_oscillation.csv + a printed paired table.
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
SEEDS = [int(x) for x in os.environ.get("M5SEEDS", ",".join(str(i) for i in range(1, 49))).split(",")]
ARMS = os.environ.get("ARMS", "fixed,osc0.07,osc0.10,mpc,mpc_osc0.10").split(",")
OSCP = int(os.environ.get("OSCP", "25"))        # half-period, matching the foresight cadence
OUT = os.environ.get("OUT", "results/theta_oscillation.csv")
FIELDS = ["arm", "seed", "onv", "stranded", "charge_trips", "theta_mean"]


def _amp(arm):
    for tag in ("mpc_osc", "osc"):
        if arm.startswith(tag):
            return float(arm[len(tag):])
    return 0.0


def one(job):
    arm, seed = job
    import numpy as np
    import m3_mpc as M
    from record_race import build

    env, ctrl = build("large-8-6", seed, stress=True)
    use_mpc = arm.startswith("mpc")
    amp = _amp(arm)
    cur = M.DEFAULT
    M.apply_setting(ctrl, cur)
    stats = {mv: [0, 0.0] for mv in M.moves_for(env)}

    base_theta = float(getattr(ctrl, "_pk_override", 0.40) or 0.40)
    onv, th_sum = 0.0, 0.0
    charging_prev = set()
    trips = 0
    for t in range(STEPS):
        if use_mpc and t > 0 and t % 50 == 0:
            base = M.rollout_score(env, ctrl, cur, t, 100)
            best_s, best = base, cur
            for mv in M.ucb_pick(stats):
                s_ = M.apply_move(cur, mv)
                if s_ == cur:
                    continue
                sc = M.rollout_score(env, ctrl, s_, t, 100)
                n_, mean = stats[mv]
                stats[mv] = [n_ + 1, mean + (sc - base - mean) / (n_ + 1)]
                if sc > best_s:
                    best_s, best = sc, s_
            if best != cur:
                cur = best
                M.apply_setting(ctrl, cur)
            base_theta = float(getattr(ctrl, "_pk_override", base_theta) or base_theta)

        if amp:
            # pure oscillation around whatever level is current: no forecast, no state read
            sign = 1.0 if (t // OSCP) % 2 == 0 else -1.0
            ctrl._pk_override = float(np.clip(base_theta + sign * amp, 0.15, 0.75))
        th_sum += float(getattr(ctrl, "_pk_override", base_theta) or base_theta)

        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        # a "charge trip" = a robot newly heading for / sitting on a bay
        bat = getattr(ctrl, "battery", None)
        if bat is not None:
            now = {a.id for a in env.agents if bat._at_charger(a)}
            trips += len(now - charging_prev)
            charging_prev = now

    bat = getattr(ctrl, "battery", None)
    stranded = sum(1 for a in env.agents if bat and bat.level.get(a.id, 1.0) <= 0.02)
    return dict(arm=arm, seed=seed, onv=round(onv, 1), stranded=stranded,
                charge_trips=trips, theta_mean=round(th_sum / STEPS, 4))


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

    def paired(arm, ref):
        d = [D[arm][s]["onv"] - D[ref][s]["onv"] for s in SEEDS]
        m = sum(d) / n
        sd = st.pstdev(d) * (n / (n - 1)) ** 0.5 if n > 1 else 0.0
        return m, (m / (sd / n ** 0.5) if sd else 0.0)

    print("THETA OSCILLATION -- stress days, %d paired seeds, half-period %d steps\n" % (n, OSCP))
    print("%-14s %9s %10s %8s %10s %9s %8s"
          % ("arm", "value", "vs fixed", "t", "vs mpc", "stranded", "trips"))
    for a in ARMS:
        vf, tf = paired(a, "fixed")
        vm, tm = (paired(a, "mpc") if "mpc" in D and a != "mpc" else (0.0, 0.0))
        print("%-14s %9.2f %+10.2f %+8.2f %10s %9d %8.1f"
              % (a, sum(D[a][s]["onv"] for s in SEEDS) / n, vf, tf,
                 ("%+.2f" % vm) if a.startswith("mpc_") else "-",
                 sum(D[a][s]["stranded"] for s in SEEDS),
                 sum(D[a][s]["charge_trips"] for s in SEEDS) / n))
    print("\nmean theta actually applied: " + "  ".join(
        "%s %.3f" % (a, sum(D[a][s]["theta_mean"] for s in SEEDS) / n) for a in ARMS))
    print("wrote", OUT)
