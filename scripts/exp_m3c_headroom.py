"""M3c GATE PROBE: headroom for idle-AGV pre-positioning on the stream.

Accounting, not policy: for each pickup, walk back the AGV's trace. If it idled before this
task (stationary >=3 steps, not carrying), the steps from leaving that idle spot to the pickup
are IDLE-APPROACH travel -- the only thing pre-positioning could ever eliminate (perfect
placement = the task spawns at your wheels). Sum it and bound the prize.

GATE: idle-approach as % of total AGV step-budget < ~3% (the ship bar) -> M3c CUT.
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 25))


def one(seed):
    import numpy as np
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed, stream=True)
    dm = env.demand_model
    agv_ids = [i for i, a in enumerate(env.agents) if a.type.name == "AGV"]
    trace = {i: [] for i in agv_ids}          # (x, y, carrying)
    onv = 0.0
    for t in range(500):
        dm.step(env, t)
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        for i in agv_ids:
            a = env.agents[i]
            trace[i].append((a.x, a.y, getattr(a, "carrying_shelf", None) is not None))
    idle_approach = 0
    pickups = idle_pickups = 0
    total_steps = len(agv_ids) * 500
    moving_steps = 0
    for i in agv_ids:
        tr = trace[i]
        moving_steps += sum(1 for k in range(1, len(tr)) if tr[k][:2] != tr[k - 1][:2])
        for k in range(1, len(tr)):
            if tr[k][2] and not tr[k - 1][2]:            # pickup at step k
                pickups += 1
                # walk back to the most recent idle block before this pickup
                j = k - 1
                while j > 0 and not tr[j][2]:
                    # idle block = stationary for >=3 consecutive steps
                    if j >= 3 and tr[j][:2] == tr[j - 1][:2] == tr[j - 2][:2]:
                        idle_pickups += 1
                        # approach = steps from leaving the idle spot to the pickup
                        idle_approach += sum(1 for m in range(j, k)
                                             if tr[m][:2] != tr[m + 1][:2] if m + 1 <= k - 1) + 1
                        break
                    j -= 1
    return (seed, round(onv, 1), pickups, idle_pickups, idle_approach, moving_steps, total_steps)


if __name__ == "__main__":
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        rows = pool.map(one, SEEDS)
    n = len(rows)
    P = sum(r[2] for r in rows); IP = sum(r[3] for r in rows)
    IA = sum(r[4] for r in rows); MV = sum(r[5] for r in rows); TS = sum(r[6] for r in rows)
    V = sum(r[1] for r in rows) / n
    print("M3c HEADROOM: idle-AGV pre-positioning on the stream (%d seeds)\n" % n)
    print("mean day value             %8.1f" % V)
    print("pickups                    %8d   (%.1f/day)" % (P, P / n))
    print("pickups preceded by idle   %8d   (%.0f%% of pickups)" % (IP, 100 * IP / max(1, P)))
    print("idle-approach steps        %8d   (%.1f/day)" % (IA, IA / n))
    print("as %% of AGV step-budget    %7.2f%%" % (100 * IA / TS))
    print("as %% of AGV moving steps   %7.2f%%" % (100 * IA / max(1, MV)))
    pct = 100 * IA / TS
    print("\nGATE: perfect pre-positioning can recover AT MOST ~%.1f%% of AGV time -> %s"
          % (pct, "worth building" if pct >= 3.0 else "CUT (below the 3%% ship bar)"))
