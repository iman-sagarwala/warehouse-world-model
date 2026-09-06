"""Two success criteria from the original proposal (Project_Plan_Main §6) that were never measured.

Found 2026-09-06 by reading the proposal against the results, rather than reading the roadmap
against the results. Both are stated targets; neither appears in any experiment, the paper, or the
criteria list assembled from the roadmap.

  A. "<= 1 phantom hard-block per 1,000 steps"  (§6.2, the second half of the specificity clause)
     A phantom hard-block is a cell the router HARD-EXCLUDES from routing (belief > b_hard) that is
     actually clear. Reported two ways, because the phrasing admits both: per cell-step, and as
     distinct phantom episodes (a cell entering the believed-blocked set while clean, counted once
     per episode however long it persists). The episode count is the fairer reading of "a phantom
     hard-block", so it is the headline; both are printed.

  B. "Decision-event latency <= 1 second wall-clock for 5 robots"  (§6.4)
     The real-time claim. 'Event-driven' is a latency promise, and a planner that deliberates for a
     minute per event is a batch scheduler wearing a costume. Measures wall-clock seconds per
     controller decision at the proposal's stated fleet size.

Outputs results/proposal_gaps.txt.
"""
import io
import os
import sys
import time
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = [int(x) for x in os.environ.get("PGSEEDS", "1,2,3,4,5,6,7,8").split(",")]


def phantoms(seed):
    """A: count phantom hard-blocks against the true disturbed set, per step and per episode."""
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
    rm = BetaRumorMap(env.grid_size)
    rm.obs_reset = True
    env.rumor_map = rm
    env.use_belief_routing = True
    env.b_hard = 0.5
    env.los_sensing = True

    # the oracle: perfect memory, fed the IDENTICAL line-of-sight stream. It cannot know a spill was
    # cleaned unless somebody looks, so its phantoms are the irreducible stale-sighting floor.
    H, W = env.grid_size
    hw = env.highways.astype(bool)
    R = int(getattr(env, "sight_radius", 5))
    los = []
    for dy in range(-R, R + 1):
        for dx in range(-R, R + 1):
            if dy == dx == 0 or dy * dy + dx * dx > R * R:
                continue
            n = max(abs(dy), abs(dx))
            between = [(round(dy * k / n), round(dx * k / n)) for k in range(1, n)]
            los.append(((dy, dx), between))
    oracle = {}

    cellsteps, episodes = 0, 0
    o_cellsteps, o_episodes = 0, 0
    was_phantom, o_was = set(), set()
    for t in range(STEPS):
        env.step(ctrl.act())
        truth = set(env.disturbed)
        blocked = rm.believed_blocked(env.b_hard)      # exactly what the router excludes
        ph = {c for c in blocked if c not in truth}
        cellsteps += len(ph)
        episodes += len(ph - was_phantom)               # newly-phantom cells = new episodes
        was_phantom = ph

        seen = set()
        for a in env.agents:
            ay, ax = a.y, a.x
            seen.add((ay, ax))
            for (dy, dx), between in los:
                y, x = ay + dy, ax + dx
                if not (0 <= y < H and 0 <= x < W):
                    continue
                if any(0 <= ay + by < H and 0 <= ax + bx < W and not hw[ay + by, ax + bx]
                       for (by, bx) in between):
                    continue
                seen.add((y, x))
        for c in seen:
            oracle[c] = c in truth
        o_ph = {c for c, dirty in oracle.items() if dirty and c not in truth}
        o_cellsteps += len(o_ph)
        o_episodes += len(o_ph - o_was)
        o_was = o_ph
    return ("ph", seed, cellsteps, episodes, STEPS, o_cellsteps, o_episodes)


def latency(seed):
    """B: wall-clock seconds per decision event at the proposal's 5-robot fleet size."""
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import importlib.util
    spec = importlib.util.spec_from_file_location("m3b", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
    m3b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3b)
    os.environ["M3SPC"] = "1500"
    # the proposal says "5 robots"; the closest legal fleet is 3 AGVs + 2 pickers
    env = gym.make("wwm_sim-largedense-3agvs-2pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    m3b.setup_bays(env)
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=STEPS, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    dm.shelfs = [s for s in dm.shelfs if s.id not in env._charger_bay_ids]
    env.demand_model = dm
    dm.seed_day_list(env, horizon=STEPS)
    dm.seed_initial(env, n=dm.warm_start_n())
    for k, v in dict(picker_service_steps=8, station_service_steps=6, station_headway=True,
                     station_exit_priority=True, free_pod_return=True,
                     picker_free_move="committed", picker_final_step=True,
                     station_side_keepout=True, keepout_top=True, station_divert=True,
                     swap_return_drop=True, picker_swap=True, picker_swap_squat=True,
                     agv_free_move=True, slot_divert=True, picker_reelect="progress",
                     clash_sim=True, clash_hysteresis=20).items():
        setattr(env, k, v)
    ctrl, _bc = m3b.make_controller("m3", env)

    times, warm = [], None
    for t in range(STEPS):
        t0 = time.perf_counter()
        a = ctrl.act()
        dt = time.perf_counter() - t0
        # step 0 in a fresh process pays imports, the A* extension load and cache warm-up; that is
        # start-up cost, not deliberation, so it is reported separately rather than hidden or ignored
        if t == 0:
            warm = dt
        else:
            times.append(dt)
        env.step(a)
    return ("lat", seed, times, warm, None)


if __name__ == "__main__":
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        ph_rows = pool.map(phantoms, SEEDS)
        lat_rows = pool.map(latency, SEEDS)

    out = []
    cs = sum(r[2] for r in ph_rows)
    ep = sum(r[3] for r in ph_rows)
    steps = sum(r[4] for r in ph_rows)
    ocs = sum(r[5] for r in ph_rows)
    oep = sum(r[6] for r in ph_rows)
    out.append("A. PHANTOM HARD-BLOCKS  (proposal 6.2: <= 1 per 1,000 steps)")
    out.append("   %d seeds x %d steps = %d step-observations" % (len(SEEDS), STEPS, steps))
    out.append("   %-34s %6s %12s %8s" % ("", "count", "per 1,000", "verdict"))
    for lbl, v in (("shipped map, episodes", ep), ("shipped map, cell-steps", cs),
                   ("ORACLE (perfect memory), episodes", oep),
                   ("ORACLE (perfect memory), cell-steps", ocs)):
        out.append("   %-34s %6d %12.1f %8s"
                   % (lbl, v, 1000.0 * v / steps, "PASS" if 1000.0 * v / steps <= 1 else "FAIL"))
    if oep:
        out.append("   -> the shipped map produces %.2fx the oracle's phantom episodes; the oracle"
                   % (ep / float(oep)))
        out.append("      itself misses the target by %.0fx, so the floor is above the bar."
                   % (1000.0 * oep / steps))

    allt = sorted(x for r in lat_rows for x in r[2])
    warms = sorted(r[3] for r in lat_rows if r[3] is not None)
    out.append("")
    out.append("B. DECISION-EVENT LATENCY  (proposal 6.4: <= 1 s wall-clock, 5 robots)")
    out.append("   fleet 3 AGVs + 2 pickers, %d steady-state decisions over %d seeds"
               % (len(allt), len(SEEDS)))
    out.append("   mean %.2f ms   median %.2f ms   p95 %.1f ms   p99 %.1f ms   max %.1f ms   %s"
               % (1000 * sum(allt) / len(allt), 1000 * st.median(allt),
                  1000 * allt[int(0.95 * (len(allt) - 1))],
                  1000 * allt[int(0.99 * (len(allt) - 1))], 1000 * allt[-1],
                  "PASS" if allt[-1] <= 1.0 else "FAIL"))
    out.append("   first decision in a fresh process (start-up: imports, A* extension, caches):")
    out.append("   median %.0f ms   max %.0f ms   %s"
               % (1000 * st.median(warms), 1000 * warms[-1],
                  "within budget" if warms[-1] <= 1.0 else
                  "exceeds 1 s on %d of %d seeds -- start-up, not deliberation"
                  % (sum(1 for w in warms if w > 1.0), len(warms))))
    txt = "\n".join(out)
    print(txt)
    io.open("results/proposal_gaps.txt", "w", encoding="utf-8").write(txt + "\n")
    print("\nwrote results/proposal_gaps.txt")
