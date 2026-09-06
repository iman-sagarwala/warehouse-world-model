"""M5 safety metrics, MEASURED (not assumed): collisions and replans-per-disturbance.

The bench table's `collisions` column read a nonexistent env attribute and defaulted to 0 for
every run -- a placeholder, not evidence. This measures the real thing each step:
  vertex collision  two agents occupying the same cell
  swap collision    two agents exchanging cells between consecutive steps (passing through)
  replans/disturb   how many times a robot's committed path is rebuilt per spill event
Arms: fifo / rush / champ / mpc. Disturbances ON so replans have something to count.
"""
import csv
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS = 500
SEEDS = [int(x) for x in os.environ.get("M5SEEDS", ",".join(str(i) for i in range(1, 49))).split(",")]
ARMS = os.environ.get("ARMS", "fifo,rush,champ,mpc").split(",")
OUT = os.environ.get("OUT", "results/m5_safety.csv")
FIELDS = ["arm", "seed", "vertex_collisions", "swap_collisions", "replans", "disturb_events",
          "replans_per_disturb", "steps_stuck"]


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    from wwm_sim.rumor_map import BetaRumorMap
    import m3_mpc as M
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
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
        from sim_dashboard import FIFOController
        from sim_priority import RushValueController
        ctrl = FIFOController(env) if arm == "fifo" else RushValueController(env)
    cur, stats = M.DEFAULT, {mv: [0, 0.0] for mv in M.moves_for(env)}
    vertex = swap = replans = stuck = 0
    prev_pos = {}
    prev_paths = {}
    for t in range(STEPS):
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
        # NB an AGV and a PICKER legally share a cell (that IS the rendezvous). Only SAME-TYPE
        # overlap is a collision -- measured, not assumed: cross-type sharing runs ~1/step.
        pos = {i: ((a.x, a.y), a.type.name) for i, a in enumerate(env.agents)}
        seen = {}
        for i, (p, ty) in pos.items():                # VERTEX: two same-type agents in one cell
            if seen.get((p, ty)) is not None:
                vertex += 1
            seen[(p, ty)] = i
        for i, (p, ty) in pos.items():                # SWAP: same-type pair exchanged cells
            q = prev_pos.get(i, (None, None))[0]
            if q is None:
                continue
            for j, (p2, ty2) in pos.items():
                if j <= i or ty2 != ty:
                    continue
                if p2 == q and prev_pos.get(j, (None, None))[0] == p:
                    swap += 1
        prev_pos = pos
        for i, a in enumerate(env.agents):            # REPLAN: committed path rebuilt
            cells = tuple(getattr(a, "path", ()) or ())
            old = prev_paths.get(i)
            if old and cells and cells != old[1:] and cells != old:
                replans += 1
            prev_paths[i] = cells
        stuck += sum(1 for a in env.agents if getattr(a, "_debris_stuck", False))
    ev = int(getattr(env, "_blockage_events", 0))
    return dict(arm=arm, seed=seed, vertex_collisions=vertex, swap_collisions=swap,
                replans=replans, disturb_events=ev,
                replans_per_disturb=round(replans / max(1, ev), 2), steps_stuck=stuck)


if __name__ == "__main__":
    jobs = [(a, s) for a in ARMS for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, jobs)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print("M5 SAFETY METRICS, measured over %d seeds (disturbances ON)\n" % len(SEEDS))
    print("%-7s %12s %12s %10s %14s %12s" % ("arm", "vertex-coll", "swap-coll", "replans",
                                             "replans/spill", "stuck-steps"))
    for a in ARMS:
        rs = [r for r in rows if r["arm"] == a]
        n = len(rs)
        print("%-7s %12d %12d %10.1f %14.2f %12.1f"
              % (a, sum(r["vertex_collisions"] for r in rs), sum(r["swap_collisions"] for r in rs),
                 sum(r["replans"] for r in rs) / n,
                 sum(r["replans_per_disturb"] for r in rs) / n,
                 sum(r["steps_stuck"] for r in rs) / n))
    print("\n(totals are across all seeds; collisions should be 0 -- the env referee forbids them)")
