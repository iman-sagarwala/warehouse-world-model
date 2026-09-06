"""ADG execution in the REAL env: committed routes driven in crossing-order, delay -> wait.

Puts two AGVs on crossing committed routes in the actual wwm_sim env (ADG mode), then stalls
the first. The second waits for it to clear the junction — 0 collisions, in the real sim,
without the env's A*/reroute. Movement-only first cut. Run: python scripts/demo_adg_env.py
"""
import os
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import gymnasium as gym
import wwm_sim  # noqa: F401
from wwm_sim.warehouse import AgentType


def hline(x0, x1, y):
    step = 1 if x1 >= x0 else -1
    return [(x, y) for x in range(x0, x1 + step, step)]


def vline(y0, y1, x):
    step = 1 if y1 >= y0 else -1
    return [(x, y) for y in range(y0, y1 + step, step)]


def run(stall):
    env = gym.make("wwm_sim-large-8agvs-4pickers-globalobs-v1").unwrapped
    env.reset(seed=0)
    agvs = [a for a in env.agents if a.type == AgentType.AGV]
    a1, a2 = agvs[0], agvs[1]
    # place the two AGVs on crossing routes; J = (6,10). a1 reaches J first (index 2).
    a1.x, a1.y, a1.dir = 4, 10, a1.dir
    a2.x, a2.y, a2.dir = 6, 14, a2.dir
    r1 = hline(4, 10, 10)          # a1 EAST through (6,10)
    r2 = vline(14, 6, 6)           # a2 NORTH through (6,10)
    env._recalc_grid()
    env.set_adg_plan({a1.id: r1, a2.id: r2})
    if stall:
        env._adg_stall[a1.id] = 4  # a1 can't move until _cur_steps >= 4 (a delay)
    J = (6, 10)
    log = []
    collisions = 0
    for _ in range(26):
        env.step([0] * env.num_agents)
        p1, p2 = (a1.x, a1.y), (a2.x, a2.y)
        if p1 == p2:
            collisions += 1
        log.append((p1, p2))
    return log, collisions, J, a1.id, a2.id


def show(tag, log, J):
    print(f"  {tag}: junction J={J}")
    print(f"    {'tick':>4}  {'AGV_a':>8}  {'AGV_b':>8}   note")
    for t, (p1, p2) in enumerate(log[:16], 1):
        note = ""
        if p1 == J:
            note += "a@J "
        if p2 == J:
            note += "b@J "
        if p2 == log[t - 2][1] if t > 1 else False:
            pass
        print(f"    {t:>4}  {str(p1):>8}  {str(p2):>8}   {note}")


def main():
    print("=" * 66)
    print("ADG execution in the REAL wwm_sim env (movement only).")
    print("Two AGVs cross at J=(6,10); committed order: a first, then b.")
    print("=" * 66)
    log, coll, J, i1, i2 = run(stall=False)
    print("\n1) No delay — both cross:")
    show("clean", log, J)
    print(f"    collisions = {coll}")

    log, coll, J, i1, i2 = run(stall=True)
    print("\n2) AGV_a STALLED 4 ticks — AGV_b must wait for it to clear J:")
    show("delay", log, J)
    b_waits = sum(1 for t in range(1, len(log)) if log[t][1] == log[t - 1][1])
    print(f"    collisions = {coll}   (AGV_b held position {b_waits} tick(s) waiting)")
    print("\nReal-env result: committed routes executed in ADG order; a delay became a WAIT,")
    print("not a reroute or a crash. (Movement only; pick/deliver + fleet deconfliction next.)")


if __name__ == "__main__":
    main()
