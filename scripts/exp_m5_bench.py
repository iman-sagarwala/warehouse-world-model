"""M5: the full benchmark table. Every controller, both regimes, the whole metric suite.

Arms (identical worlds, identical days, exogenous demand so every arm faces the same orders):
  fifo      the vendored FIFO heuristic (the simulator's own baseline)
  rush      RushValue: value priority + lateness-decay rush ordering (no Part A rollout)
  champ     the shipped champion stack, fixed constants (board rollout + battery management)
  mpc       champion + the forward-simulating tuner (self-tuning settings)
Regimes: wave (whole day visible at t=0) and stream (orders arrive live).

Metrics per run (the roadmap's §5 suite): on-time value, throughput (delivered), deadline hit
rate, tardiness mean + p95 over LATE tasks, energy per task, strandings, frozen, collisions.
Resumable: every finished run is appended to results/m5_bench.csv and skipped on restart.
"""
import csv
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
# NB: the env var is M5SEEDS -- plain SEEDS is already claimed by m3_battery.py (it int()s it)
SEEDS = [int(x) for x in os.environ.get("M5SEEDS", ",".join(str(i) for i in range(1, 145))).split(",")]
ARMS = os.environ.get("ARMS", "fifo,rush,champ,mpc").split(",")
REGIMES = os.environ.get("REGIMES", "wave,stream").split(",")
CONFIG = os.environ.get("CONFIG", "large-8-6")
DISTURB = os.environ.get("DISTURB") == "1"      # spills on: the roadmap's head-to-head condition
OUT = os.environ.get("OUT", "results/m5_bench.csv")
FIELDS = ["arm", "regime", "seed", "onv", "delivered", "hit_rate", "tard_mean", "tard_p95",
          "energy_per_task", "stranded", "frozen", "collisions"]


def one(job):
    arm, regime, seed = job
    import numpy as np
    from record_race import build
    import m3_mpc as M
    os.environ["M3SPC"] = "1500"
    stream = (regime == "stream")
    env, ctrl = build(CONFIG, seed, stream=stream)     # champion stack + battery + bays
    bat = getattr(ctrl, "battery", None)
    if DISTURB:
        # the roadmap's head-to-head condition: "target +10% UNDER DISTURBANCES". Same spill
        # physics as M2 (multi-cell events, stuck-until-cleaned) + the shipped belief map, so
        # every arm sees identical hazards on identical days.
        from wwm_sim.rumor_map import BetaRumorMap
        env.disturb_rate = 0.02
        env._disturb_rng = np.random.RandomState(4000 + seed)
        env.disturb_dur = (150, 400)
        env.disturb_event_cells = (1, 3)
        env.debris_hold_steps = -1
        env.use_belief_routing = True
        env.rumor_map = BetaRumorMap(env.grid_size)
        env.b_hard = 0.5
        env.los_sensing = True

    if arm in ("fifo", "rush"):
        # baselines run on the SAME world; swap the decision layer only
        from sim_dashboard import FIFOController
        from sim_priority import RushValueController
        ctrl2 = (FIFOController(env) if arm == "fifo" else RushValueController(env))
        ctrl = ctrl2
        bat = None
    elif arm == "mpc":
        M.apply_setting(ctrl, M.DEFAULT)

    cur = M.DEFAULT
    stats = {mv: [0, 0.0] for mv in M.moves_for(env)}
    dm = env.demand_model
    onv = 0.0
    delivered = 0
    lateness = []
    n_orders_done = 0
    hist = []                     # (pos, carrying) per agent, last 100 steps -> FROZEN audit
    for t in range(STEPS):
        if stream:
            dm.step(env, t)
        if arm == "mpc" and t > 0 and t % 50 == 0:
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
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            n_orders_done += 1
            if o.deadline is not None:
                late = (t + 1) - o.deadline
                if late <= 0:
                    onv += o.value
                else:
                    lateness.append(late)
        delivered += len(getattr(env, "deliveries_this_step", []))
        if t >= STEPS - 100:      # frozen audit window: carrying a pod and never moving
            hist.append([((a.x, a.y), getattr(a, "carrying_shelf", None) is not None)
                         for a in env.agents])
    n_agv = sum(1 for a in env.agents if a.type.name == "AGV")
    if bat is not None:
        lvls = [bat.level.get(a.id, 1.0) for a in env.agents]
        stranded = sum(1 for a in env.agents if bat.level.get(a.id, 1.0) <= 0.02)
        energy = (n_agv * 1.0 - sum(lvls[:n_agv])) / max(1, n_orders_done)
    else:
        stranded, energy = 0, float("nan")
    frozen = 0                    # AUDIT definition: held a pod AND never moved for 100 steps
    if len(hist) >= 100:
        for i in range(len(env.agents)):
            if all(h[i][1] for h in hist) and len({h[i][0] for h in hist}) == 1:
                frozen += 1
    hit = (n_orders_done - len(lateness)) / max(1, n_orders_done)
    return dict(arm=arm, regime=regime, seed=seed, onv=round(onv, 1), delivered=delivered,
                hit_rate=round(hit, 4),
                tard_mean=round(sum(lateness) / len(lateness), 2) if lateness else 0.0,
                tard_p95=(sorted(lateness)[int(0.95 * (len(lateness) - 1))] if lateness else 0),
                energy_per_task=(round(energy, 5) if energy == energy else ""),
                stranded=stranded, frozen=frozen,
                collisions=int(getattr(env, "_collisions", 0)))


def load_done():
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                done.add((r["arm"], r["regime"], int(r["seed"])))
    return done


if __name__ == "__main__":
    done = load_done()
    jobs = [(a, g, s) for a in ARMS for g in REGIMES for s in SEEDS if (a, g, s) not in done]
    print("M5 bench: %d runs to do (%d already on disk) -> %s" % (len(jobs), len(done), OUT),
          flush=True)
    new = not os.path.exists(OUT)
    with open(OUT, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
            for k, row in enumerate(pool.imap_unordered(one, jobs, chunksize=1), 1):
                w.writerow(row)
                fh.flush()
                if k % 25 == 0:
                    print("  %d/%d" % (k, len(jobs)), flush=True)
    # ---- summary table ----
    rows = list(csv.DictReader(open(OUT)))
    print("\nNOTE: fifo/rush run WITHOUT battery physics (free energy) -- an advantage to the"
          "\n      baselines; champ/mpc pay the full charging cost, so beating them is conservative.")
    print("\n%-7s %-7s %8s %8s %8s %9s %9s %8s %8s"
          % ("regime", "arm", "value", "deliv", "hit%", "tardMean", "tardP95", "strand", "frozen"))
    for g in REGIMES:
        base = {}
        for a in ARMS:
            rs = [r for r in rows if r["arm"] == a and r["regime"] == g]
            if not rs:
                continue
            n = len(rs)
            val = sum(float(r["onv"]) for r in rs) / n
            base.setdefault("champ", None)
            print("%-7s %-7s %8.1f %8.1f %7.1f%% %9.1f %9.1f %8d %8d"
                  % (g, a, val,
                     sum(float(r["delivered"]) for r in rs) / n,
                     100 * sum(float(r["hit_rate"]) for r in rs) / n,
                     sum(float(r["tard_mean"]) for r in rs) / n,
                     sum(float(r["tard_p95"]) for r in rs) / n,
                     sum(int(r["stranded"]) for r in rs),
                     sum(int(r["frozen"]) for r in rs)))
        # paired deltas vs champ
        ch = {int(r["seed"]): float(r["onv"]) for r in rows
              if r["arm"] == "champ" and r["regime"] == g}
        for a in ARMS:
            if a == "champ":
                continue
            d = [float(r["onv"]) - ch[int(r["seed"])] for r in rows
                 if r["arm"] == a and r["regime"] == g and int(r["seed"]) in ch]
            if len(d) > 2:
                m = sum(d) / len(d)
                sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** 0.5
                print("   %-6s vs champ: %+8.2f  (%+.1f%%)  t=%+.2f  n=%d"
                      % (a, m, 100 * m / (sum(ch.values()) / len(ch)),
                         m / (sd / len(d) ** 0.5) if sd else 0.0, len(d)))
