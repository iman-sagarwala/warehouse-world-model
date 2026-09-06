"""MPC-OVER-PARAMETERS (USER DESIGN 2026-08-14): the sim's own physics as the world model.

Every REPLAN real steps, fork the live (env, controller) state with deepcopy, roll each of ~7
candidate settings forward HORIZON steps in the fork, score each future by on-time value minus
stranding penalties, and adopt the winning setting in the real warehouse. Parameters tuned:
AGV battery pessimism, picker charge threshold, charge concurrency cap. Precedent: clash_sim
(guessed model t=-1.76 -> simulated model +0.76, shipped).

In the day-list regime the fork's demand foresight is legitimate: the day's arrivals are known.

CONFIG env var: "<size>-<A>agvs-<P>pickers" (dense geometry implied), e.g. "large-8-6".
Arms: fixed (m3 as shipped) vs mpc (same controller + forward-simulation tuning).
Appends one CSV row per arm to results/mpc_campaign.csv.
"""
import copy
import os
import sys
import time
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

CONFIG = os.environ.get("CONFIG", "large-8-6")          # size-agvs-pickers
SPC = float(os.environ.get("M3SPC", "1500"))
REPLAN = int(os.environ.get("REPLAN", "50"))
HORIZON = int(os.environ.get("HORIZON", "100"))
NPROC = int(os.environ.get("NPROC", "8"))
TIMING = os.environ.get("TIMING", "0") == "1"
# mixed halves: window_index=seed makes 73+ the peak half -- batches must see both regimes
SEEDS = ([int(x) for x in os.environ["SEEDLIST"].split(",")] if os.environ.get("SEEDLIST")
         else list(range(1, 19)) + list(range(73, 91)))
CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "results", "mpc_campaign.csv")

_size, _agvs, _pk = CONFIG.split("-")
# size may carry an explicit geometry suffix ("largedual"); bare sizes get dense geometry
_geom = _size if _size.endswith(("dense", "dual")) else _size + "dense"
ENV_ID = "wwm_sim-%s-%sagvs-%spickers-globalobs-v1" % (_geom, _agvs, _pk)
# bays are FLOOR infrastructure (fixed per map, independent of fleet) -- m3_battery.floor_bays


def build_world(seed):
    import gymnasium as gym
    import numpy as np
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import importlib.util
    spec = importlib.util.spec_from_file_location("m3b", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
    m3b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3b)
    os.environ["M3SPC"] = str(SPC)
    env = gym.make(ENV_ID).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    m3b.setup_bays(env)
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    dm.shelfs = [s for s in dm.shelfs if s.id not in env._charger_bay_ids]
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    for k, v in dict(picker_service_steps=8, station_service_steps=6, station_headway=True,
                     station_exit_priority=True, free_pod_return=True, picker_free_move="committed",
                     picker_final_step=True, station_side_keepout=True, keepout_top=True,
                     station_divert=True, swap_return_drop=True, picker_swap=True,
                     picker_swap_squat=True, agv_free_move=True, slot_divert=True,
                     picker_reelect="progress", clash_sim=True, clash_hysteresis=20).items():
        setattr(env, k, v)
    ctrl, bc = m3b.make_controller("m3", env)
    rng = np.random.RandomState(7000 + seed)
    for a in env.agents:
        bc.battery.level[a.id] = float(rng.uniform(0.15, 1.0))
    return env, ctrl


def apply_setting(ctrl, s):
    ctrl.BAT_PESSIMISM = s[0]
    ctrl._pk_override = s[1]
    ctrl._cap_override = s[2]
    ctrl.RATE_ALPHA = s[3]
    ctrl.SEQ_DEPTH = s[4]
    ctrl.URG_W_DAYLIST = s[5]
    ctrl.env.clash_hysteresis = s[6]
    if len(s) > 7 and getattr(ctrl.env, "rumor_map", None) is not None:
        ctrl.env.b_hard = s[7]
        ctrl.env.rumor_map.decay = s[8]



def _battery_risk(ctrl, env):
    """Projected strandings BEYOND the horizon: level minus pessimistic trip-to-bay cost
    leaves the robot under the floor -> it is already committed to stranding even though
    the fork ended. Catches the slow drains a 100-step horizon cannot see."""
    bat = ctrl.battery
    cfg_ = bat.cfg if hasattr(bat, "cfg") else None
    drain = (1.0 / getattr(cfg_, "steps_per_charge", 1500.0)) if cfg_ else 1.0 / 1500.0
    floor = getattr(cfg_, "floor", 0.10) if cfg_ else 0.10
    risk = 0
    for a in env.agents:
        lvl = bat.level.get(a.id, 1.0)
        if lvl <= 0.02:
            continue                      # already counted as dead
        c = bat.nearest_charger(a)
        trip = (abs(c[0] - a.x) + abs(c[1] - a.y)) * drain * 1.2 if c else 0.0
        if lvl - trip < 0.02:
            risk += 2                     # committed to death: near-full penalty
        elif lvl - trip < floor * 0.5:
            risk += 1                     # deep in the reserve with a long walk home
    return risk

def rollout_score(env, ctrl, setting, t0, horizon):
    """Fork the world, apply the setting, roll forward, score the future."""
    env2, ctrl2 = copy.deepcopy((env, ctrl))
    # HONEST FORKS (2026-08-23): a deepcopy carries the disturbance RNG state, so an imagined
    # rollout would replay the TRUE future spill spawns -- clairvoyance inside the imagination.
    # Reseed the fork's RNG so imagined futures SAMPLE the spawn process instead of reading it.
    if getattr(env2, "_disturb_rng", None) is not None:
        import numpy as _np
        env2._disturb_rng = _np.random.RandomState(env2._disturb_rng.randint(0, 2**31 - 1))
    apply_setting(ctrl2, setting)
    onv = 0.0
    breach0 = {a.id for a in env2.agents
               if ctrl2.battery.level.get(a.id, 1.0) < 0.10}
    for h in range(horizon):
        env2.step(ctrl2.act())
        for o in getattr(env2, "fulfilled_this_step", []):
            if o.deadline is not None and t0 + h + 1 <= o.deadline:
                onv += o.value
    dead = sum(1 for a in env2.agents
               if ctrl2.battery.level.get(a.id, 1.0) <= 0.02)
    newbreach = sum(1 for a in env2.agents
                    if ctrl2.battery.level.get(a.id, 1.0) < 0.10
                    and a.id not in breach0)
    return onv - 100.0 * dead - 20.0 * newbreach - 50.0 * _battery_risk(ctrl2, env2)


# TUNER v2 (USER 2026-08-16: champion decision weights "shouldn't be fixed constants -- it's like
# a slider on agvs, on pickers, on dimension" -- M1's flatness was measured on ONE map): the
# candidate space now includes RATE_ALPHA, SEQ_DEPTH, the day-list urgency weight, and
# clash_hysteresis, all with conservative moves and clamps around the shipped champion values.
MOVES = ("stay", "P+", "P-", "th+", "th-", "cap-", "cap+",
         "a+", "a-", "d+", "d-", "u+", "u-", "h+", "h-")

# BELIEF TRUST KNOBS (user 2026-08-23): the belief map's weights are tunable by the SAME
# principle as everything else -- constant by default (0.5 trust threshold, 0.99 memory decay),
# context-independent (NOT scaled by fleet/floor), changed only when a fork proves a change
# better: if beliefs have often been wrong, imagined futures under adjusted trust score higher
# and the tuner adopts. Moves exist only in worlds that HAVE a rumor map (moves_for()).
BELIEF_MOVES = ("bt+", "bt-", "bm+", "bm-")

def moves_for(env):
    return MOVES + (BELIEF_MOVES if getattr(env, "rumor_map", None) is not None else ())

DEFAULT = (1.5, 0.40, 2, 7.0, 5, 0.0, 20, 0.5, 0.99)
# P, theta, cap, RATE_ALPHA, SEQ_DEPTH, URG_W, hyst, BELIEF_TRUST (b_hard), BELIEF_MEMORY (decay)


def apply_move(cur, mv):
    if len(cur) == 7:
        cur = cur + (0.5, 0.99)      # old 7-field tuples (replay CSVs) get the constants
    P, th, cap, al, dp, ur, hy, bt, bm = cur
    tail = (bt, bm)
    out = {
        "stay": cur,
        "P+":   (min(3.0, P + 0.3), th, cap, al, dp, ur, hy) + tail,
        "P-":   (max(1.0, P - 0.2), th, cap, al, dp, ur, hy) + tail,
        "th+":  (P, min(0.6, th + 0.10), cap, al, dp, ur, hy) + tail,
        "th-":  (P, max(0.10, th - 0.07), cap, al, dp, ur, hy) + tail,
        "cap-": (P, th, max(1, cap - 1), al, dp, ur, hy) + tail,
        "cap+": (P, th, cap + 1, al, dp, ur, hy) + tail,
        "a+":   (P, th, cap, min(15.0, al + 2.0), dp, ur, hy) + tail,
        "a-":   (P, th, cap, max(1.0, al - 2.0), dp, ur, hy) + tail,
        "d+":   (P, th, cap, al, min(8, dp + 1), ur, hy) + tail,
        "d-":   (P, th, cap, al, max(0, dp - 1), ur, hy) + tail,
        "u+":   (P, th, cap, al, dp, min(12.0, ur + 2.0), hy) + tail,
        "u-":   (P, th, cap, al, dp, max(0.0, ur - 2.0), hy) + tail,
        "bt+":  (P, th, cap, al, dp, ur, hy, min(0.9, bt + 0.15), bm),
        "bt-":  (P, th, cap, al, dp, ur, hy, max(0.2, bt - 0.15), bm),
        "bm+":  (P, th, cap, al, dp, ur, hy, bt, min(0.999, bm + 0.007)),
        "bm-":  (P, th, cap, al, dp, ur, hy, bt, max(0.95, bm - 0.02)),
        "h+":   (P, th, cap, al, dp, ur, min(40, hy + 10)) + tail,
        "h-":   (P, th, cap, al, dp, ur, max(0, hy - 10)) + tail,
    }
    return out[mv]


def ucb_pick(stats, k=3, c=25.0):
    """UCB1 over parameter MOVES (Pinductor-style guided proposal instead of brute
    enumeration): rank non-stay moves by mean observed improvement over 'stay' plus an
    exploration bonus; untried moves rank first. Returns the k moves to simulate."""
    import math
    N = sum(n for n, _ in stats.values()) + 1
    scored = []
    for mv in stats:                   # the caller's move set (moves_for(env)), not the constant
        if mv == "stay":
            continue
        n, mean = stats[mv]
        bonus = float("inf") if n == 0 else c * math.sqrt(math.log(N) / n)
        scored.append((mean + bonus, mv))
    scored.sort(key=lambda x: -x[0])
    return [mv for _, mv in scored[:k]]


def one(job):
    arm, seed = job
    from wwm_sim.warehouse import AgentType
    env, ctrl = build_world(seed)
    cur = DEFAULT                             # shipped m3 + champion constants
    apply_setting(ctrl, cur)
    onv = 0.0
    tail = {}
    adopted = []
    replay = []                       # (t, P, th, cap, score, adopted?) -> mpc_replay.csv
    stats = {mv: [0, 0.0] for mv in MOVES}   # per-episode UCB over moves
    t_fork = 0.0
    for t in range(500):
        if arm == "mpc" and t > 0 and t % REPLAN == 0:
            t1 = time.time()
            base = rollout_score(env, ctrl, cur, t, HORIZON)
            best_s, best_set, best_mv = base, cur, "stay"
            for mv in ucb_pick(stats):
                s_ = apply_move(cur, mv)
                if s_ == cur:
                    continue
                sc = rollout_score(env, ctrl, s_, t, HORIZON)
                n, mean = stats[mv]
                stats[mv] = [n + 1, mean + (sc - base - mean) / (n + 1)]
                replay.append((t,) + s_ + (round(sc, 1), 0))
                if sc > best_s:
                    best_s, best_set, best_mv = sc, s_, mv
            t_fork += time.time() - t1
            cur = best_set
            apply_setting(ctrl, cur)
            adopted.append(cur)
            replay.append((t,) + cur + (round(best_s, 1), 1))
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    stranded = sum(1 for _, lv in ctrl.battery.level.items() if lv <= 0.02)
    trips = ctrl.n_charge_trips
    mP = sum(a[0] for a in adopted) / len(adopted) if adopted else cur[0]
    mth = sum(a[1] for a in adopted) / len(adopted) if adopted else cur[1]
    mcap = sum(a[2] for a in adopted) / len(adopted) if adopted else cur[2]
    return (arm, seed, round(onv, 1), frozen, stranded, trips,
            round(mP, 3), round(mth, 3), round(mcap, 2), round(t_fork, 1), replay)


if __name__ == "__main__":
    if TIMING:
        t0 = time.time()
        env, ctrl = build_world(1)
        for t in range(60):
            env.step(ctrl.act())
        t1 = time.time()
        s = rollout_score(env, ctrl, (1.5, 0.40, 2), 60, HORIZON)
        t2 = time.time()
        print("60 real steps %.2fs | one %d-step fork+rollout %.2fs | score %.1f"
              % (t1 - t0, HORIZON, t2 - t1, s))
        sys.exit(0)
    jobs = [(a, s) for a in ("fixed", "mpc") for s in SEEDS]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, jobs)
    D = {a: {} for a in ("fixed", "mpc")}
    AGG = {a: [0, 0, 0, [], [], [], 0.0] for a in ("fixed", "mpc")}
    REPLAY_CSV = CSV.replace("mpc_campaign.csv", "mpc_replay.csv")
    with open(REPLAY_CSV, "a", encoding="utf-8") as rf:
        if rf.tell() == 0:
            rf.write("config,seed,t,P,theta,cap,score,adopted\n")
        for a, s, v, fr, sd, tr, mP, mth, mcap, tf, rep in rows:
            # v2 rows carry the full setting (t,P,theta,cap,alpha,depth,urgw,hyst,score,adopted)
            # as extra trailing fields; DictReader restkey keeps old rows parseable.
            for r_ in rep:
                rf.write("%s,%d," % (CONFIG, s)
                         + ",".join(str(x) for x in r_) + "\n")
    rows = [r[:-1] for r in rows]
    for a, s, v, fr, sd, tr, mP, mth, mcap, tf in rows:
        D[a][s] = v
        AGG[a][0] += fr
        AGG[a][1] += sd
        AGG[a][2] += tr
        AGG[a][3].append(mP)
        AGG[a][4].append(mth)
        AGG[a][5].append(mcap)
        AGG[a][6] += tf
    n_ = len(SEEDS)
    diff = [D["mpc"][s] - D["fixed"][s] for s in SEEDS]
    m = sum(diff) / n_
    sd_ = st.pstdev(diff) * (n_ / (n_ - 1)) ** 0.5
    tt = m / (sd_ / n_ ** 0.5) if sd_ else 0.0
    base = sum(D["fixed"].values()) / n_
    print("MPC-OVER-PARAMETERS  config=%s  (%d seeds, mixed halves; replan %d, horizon %d)\n"
          % (CONFIG, n_, REPLAN, HORIZON))
    print("%-6s %11s %8s %10s %9s %7s %7s %7s" % ("arm", "mean value", "frozen",
                                                  "STRANDED", "trips", "P", "theta", "cap"))
    for a in ("fixed", "mpc"):
        v = sum(D[a].values()) / n_
        L = AGG[a]
        print("%-6s %11.2f %8d %10d %9d %7.2f %7.2f %7.2f"
              % (a, v, L[0], L[1], L[2],
                 sum(L[3]) / n_, sum(L[4]) / n_, sum(L[5]) / n_))
    print("\nmpc vs fixed: %+.2f/ep (%+.2f%%)  t=%+.2f   fork compute %.0fs total"
          % (m, 100 * m / base if base else 0.0, tt, AGG["mpc"][6]))
    hdr = ("config,arm,n_seeds,mean_value,vs_fixed_pct,t_stat,frozen,stranded,trips,"
           "mean_P,mean_theta,mean_cap\n")
    newfile = not os.path.exists(CSV)
    with open(CSV, "a", encoding="utf-8") as f:
        if newfile:
            f.write(hdr)
        for a in ("fixed", "mpc"):
            v = sum(D[a].values()) / n_
            L = AGG[a]
            pc = 0.0 if a == "fixed" else (100 * m / base if base else 0.0)
            f.write("%s,%s,%d,%.2f,%.2f,%.2f,%d,%d,%d,%.2f,%.2f,%.2f\n"
                    % (CONFIG, a, n_, v, pc, (tt if a == "mpc" else 0.0),
                       L[0], L[1], L[2], sum(L[3]) / n_, sum(L[4]) / n_, sum(L[5]) / n_))
