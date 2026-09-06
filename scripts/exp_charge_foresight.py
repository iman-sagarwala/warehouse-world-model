"""Is there ANY channel where seeing the future pays? Test the one we never tried: CHARGING.

Every previous foresight test asked the future to change WHICH TASK to take -- and lost, because
an order cannot be served before it arrives. Charging is structurally different: "go charge now"
is a PRESENT action whose value depends on what the next few hundred steps demand. Charge during
a lull and the rush finds you full; charge during the rush and you are absent when it matters.

Arms (stress days -- compressed battery + low starts, where charging genuinely binds):
  base    shipped controller, fixed charge threshold
  fore    threshold modulated by the ORACLE preview of arrivals in the next H steps:
          busy ahead -> charge earlier (top up in the lull); quiet ahead -> defer charging
          theta_t = theta * (1 + GAIN * (load_ahead / load_typical - 1)), clipped
Perfect foresight again, so this bounds what any real forecaster could achieve.
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = [int(x) for x in os.environ.get("M5SEEDS", ",".join(str(i) for i in range(1, 49))).split(",")]
HORIZ = int(os.environ.get("HORIZ", "150"))        # how far ahead the oracle looks
GAIN = float(os.environ.get("GAIN", "0.5"))        # how hard the forecast moves the threshold
ARMS = os.environ.get("ARMS", "base,fore,shuf,hi").split(",")
HI = float(os.environ.get("HI_THETA", "0.46"))     # "hi": a CONSTANT higher threshold, no dynamics


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    os.environ["M3SPC"] = "300"                    # stress: battery binds inside the day
    env, ctrl = build("large-8-6", seed, stress=True)
    dm = env.demand_model
    sched = getattr(dm, "_sched", None) or []
    times = np.array([t for (t, *_rest) in sched], dtype=float) if sched else np.zeros(0)
    typical = max(1.0, len(times) * HORIZ / 500.0)   # expected arrivals in a window of this length
    base_theta = float(getattr(ctrl, "_pk_override", 0.40) or 0.40)

    if arm == "hi":
        ctrl._pk_override = HI
    onv = 0.0
    th_sum, th_n = 0.0, 0
    for t in range(500):
        th_sum += float(getattr(ctrl, "_pk_override", base_theta) or base_theta)
        th_n += 1
        # Re-evaluate on a 25-step cadence with a deadband. Mutating the threshold every tick
        # churns robots in and out of CHARGING missions (it corrupted the controller's assignment
        # bookkeeping outright), and no real policy would oscillate per tick either.
        if arm in ("fore", "shuf") and times.size and t % 25 == 0:
            # CONTROL: "shuf" reads the arrival count from a DIFFERENT part of the day (offset by
            # half a period). Same threshold movement, same variance -- but the information is
            # wrong. If fore ~= shuf, the gain is threshold jitter, not foresight.
            t_q = (t + 250) % 500 if arm == "shuf" else t
            ahead = float(((times > t_q) & (times <= t_q + HORIZ)).sum())
            scale = 1.0 + GAIN * (ahead / typical - 1.0)
            want = float(np.clip(base_theta * scale, 0.15, 0.75))
            if abs(want - float(getattr(ctrl, "_pk_override", base_theta) or base_theta)) > 0.03:
                ctrl._pk_override = want
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
    bat = getattr(ctrl, "battery", None)
    dead = sum(1 for a in env.agents if bat and bat.level.get(a.id, 1.0) <= 0.02)
    return (arm, seed, round(onv, 1), dead, th_sum / max(1, th_n))


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ARMS}
    DEAD = {a: 0 for a in ARMS}
    TH = {a: [] for a in ARMS}
    for a, s, v, d, th in rows:
        D[a][s] = v
        DEAD[a] += d
        TH[a].append(th)
    n = len(SEEDS)
    print("CHARGING FORESIGHT on STRESS days (horizon %d, gain %.2f, %d seeds)\n" % (HORIZ, GAIN, n))
    base_mean = sum(D[ARMS[0]].values()) / n
    for a in ARMS:
        diff = [D[a][s] - D[ARMS[0]][s] for s in SEEDS]
        m = sum(diff) / n
        sd = st.pstdev(diff) * (n / (n - 1)) ** 0.5
        tt = m / (sd / n ** 0.5) if (sd and a != ARMS[0]) else 0.0
        w = sum(1 for d in diff if d > 1e-9)
        print("%-6s mean %8.2f  vs base %+7.2f (%+.1f%%)  t=%+.2f  wins %d/%d  stranded %3d  "
              "mean threshold %.3f"
              % (a, sum(D[a].values()) / n, m, 100 * m / base_mean, tt, w, n, DEAD[a],
                 sum(TH[a]) / len(TH[a])))
    print("\nBar: t>=2 to claim foresight pays on the charging channel.")
