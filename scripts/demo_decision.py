"""Decision demo: how Part A decides, for ONE AGV and ONE picker (uncluttered).

Prints the actual score breakdown the funnel computes - for the AGV's task choice and then
the picker's rendezvous choice - and draws the committed routes. Mirrors the controller's
formulas (valuexdecay + rendezvous sync). Run: python scripts/demo_decision.py
"""
from __future__ import annotations

import os
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value
from wwm_sim import routing as rt, rollout as ro
from sim_dashboard import grid_image
from sim_priority import PartAController

ENV = "wwm_sim-small-1agvs-1pickers-globalobs-v1"
W_SYNC = PartAController.W_SYNC
DECAY_G = PartAController.DECAY_G
LOAD = PartAController.LOAD_TIME


def score_task(env, agv, picker, shelf, Ga, now):
    """Reproduce the AGV funnel's score for one candidate task, returning the breakdown."""
    routes = rt.k_shortest_routes(Ga, (agv.x, agv.y), (shelf.x, shelf.y), k=3)
    if not routes:
        return None
    best = min(routes, key=len)
    my_arrival = len(best) - 1
    p_arr, reason = ro.partner_eta(shelf, now, committed=None, free=[picker], busy=[])
    res = ro.rollout_task(env, shelf, [agv], [], now=now, load_time=LOAD,
                          my_arrival=my_arrival, partner_arrival=p_arr)
    v = task_value(shelf)
    finish = res["finish"]
    dl = shelf.deadline
    if dl is None:
        base = 500.0 + v
        proj = None
    else:
        proj = (now + finish) - dl
        base = (1000.0 + v) if proj <= 0 else v * (DECAY_G ** proj)
    score = base - W_SYNC * res["my_wait"] + 0.01 * len(routes)
    return dict(shelf=shelf, v=v, dl=dl, my_arrival=my_arrival, picker_eta=p_arr,
                my_wait=res["my_wait"], finish=finish, proj=proj,
                makeable=(dl is None or proj <= 0), score=score, route=best, routes=routes)


def main():
    env = gym.make(ENV).unwrapped
    env.reset(seed=0)
    attach_deadlines(env, load_deadlines("data/deadlines_example.txt"))
    attach_values(env, load_values("data/values_example.txt"))
    from wwm_sim.warehouse import AgentType
    agv = [a for a in env.agents if a.type == AgentType.AGV][0]
    picker = [a for a in env.agents if a.type == AgentType.PICKER][0]
    Ga = rt.build_agv_graph(env)
    Gp = rt.build_picker_graph(env)
    now = 0

    print("=" * 78)
    print(f"ONE AGV at (x={agv.x},y={agv.y})   ONE PICKER at (x={picker.x},y={picker.y})")
    print(f"knobs: valuexdecay(g={DECAY_G}) ranking, sync weight W_SYNC={W_SYNC}, load={LOAD}")
    print("=" * 78)

    # --- STEP 1: the AGV chooses a task -------------------------------------------------
    cands = list(env.request_queue)
    finalists = rt.cheap_screen(agv, cands, task_value, keep=8)
    rows = [r for r in (score_task(env, agv, picker, s, Ga, now) for s in finalists) if r]
    rows.sort(key=lambda r: r["score"], reverse=True)
    print("\nAGV's task funnel (cheap screen -> Yen's -> valuexdecay - sync):")
    print(f"  {'shelf':>5} {'value':>5} {'deadline':>8} {'drive':>5} {'pickETA':>7} "
          f"{'myWait':>6} {'finish':>6} {'makeable':>8} {'SCORE':>9}")
    for i, r in enumerate(rows):
        mark = "  <= PICK" if i == 0 else ""
        print(f"  {r['shelf'].id:>5} {r['v']:>5.1f} {str(r['dl']):>8} {r['my_arrival']:>5} "
              f"{r['picker_eta']:>7.1f} {r['my_wait']:>6.1f} {r['finish']:>6.1f} "
              f"{str(r['makeable']):>8} {r['score']:>9.1f}{mark}")
    chosen = rows[0]
    gx, gy = chosen["shelf"].x, chosen["shelf"].y
    print(f"\n=> AGV commits to shelf {chosen['shelf'].id} at (x={gx},y={gy}); it heads there "
          f"(drive {chosen['my_arrival']} steps).")

    # --- STEP 2: the picker chooses which AGV-rendezvous to serve (here: the one AGV) ----
    proutes = rt.k_shortest_routes(Gp, (picker.x, picker.y), (gx, gy), k=3)
    p_best = min(proutes, key=len) if proutes else []
    picker_arrival = len(p_best) - 1 if p_best else 0
    agv_eta = chosen["my_arrival"]                       # AGV's committed ETA to the shelf
    rendez = max(picker_arrival, agv_eta)
    agv_wait = max(0, picker_arrival - agv_eta)          # AGV waits for the picker
    picker_wait = max(0, agv_eta - picker_arrival)       # picker waits for the AGV
    dock = ro.nearest_dock_dist(env, gx, gy)
    finish = rendez + LOAD + dock
    v = chosen["v"]
    base = (1000.0 + v) if (chosen["dl"] is None or (now + finish) <= chosen["dl"]) \
        else v * (DECAY_G ** ((now + finish) - chosen["dl"]))
    pscore = base - W_SYNC * agv_wait - 0.5 * W_SYNC * picker_wait
    print("\nPICKER's rendezvous funnel (same valuexdecay ranking + sync):")
    print(f"  candidate = AGV heading to shelf {chosen['shelf'].id}")
    print(f"    picker drive to rendezvous : {picker_arrival} steps")
    print(f"    AGV committed ETA          : {agv_eta} steps")
    print(f"    rendezvous (both present)  : {rendez} steps  ->  AGV waits {agv_wait}, picker waits {picker_wait}")
    print(f"    finish (rendezvous+load+dock={dock}) : {finish}")
    print(f"    score = base({base:.1f}) - {W_SYNC}*agvWait({agv_wait}) - {0.5*W_SYNC}*pkWait({picker_wait}) = {pscore:.1f}")
    print(f"\n=> Picker goes to meet the AGV at shelf {chosen['shelf'].id}; they sync within "
          f"{abs(agv_eta - picker_arrival)} steps.")

    # --- draw it -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.imshow(grid_image(env), interpolation="nearest", zorder=0)
    ax.scatter([agv.x], [agv.y], c=[[1, 0.55, 0]], s=160, edgecolors="k", zorder=5, label="AGV")
    ax.scatter([picker.x], [picker.y], c=[[0.12, 0.56, 1]], marker="D", s=130,
               edgecolors="k", zorder=5, label="Picker")
    for r in rows[1:]:                                   # other candidate tasks (faint)
        ax.plot([c[0] for c in r["route"]], [c[1] for c in r["route"]], "-",
                color="gray", lw=1.2, alpha=0.35, zorder=2)
        ax.scatter([r["shelf"].x], [r["shelf"].y], marker="*", s=70, color="gray",
                   edgecolors="k", zorder=3)
    ax.plot([c[0] for c in chosen["route"]], [c[1] for c in chosen["route"]], "-",
            color="crimson", lw=3, zorder=4, label="AGV chosen route")
    if p_best:
        ax.plot([c[0] for c in p_best], [c[1] for c in p_best], "--",
                color=[0.12, 0.56, 1], lw=2.2, zorder=4, label="Picker route to rendezvous")
    ax.scatter([gx], [gy], marker="*", s=260, color="crimson", edgecolors="k", zorder=6)
    ax.set_title(f"1 AGV + 1 Picker: AGV picks shelf {chosen['shelf'].id}, picker syncs to meet it",
                 fontsize=11, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(loc="upper right", fontsize=8)
    os.makedirs("results", exist_ok=True)
    fig.tight_layout()
    fig.savefig("results/decision_1agv_1picker.png", dpi=115)
    print("\nwrote results/decision_1agv_1picker.png")


if __name__ == "__main__":
    main()
