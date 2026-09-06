"""viz_picker_wait -- WHY does the AGV wait for a picker, beyond "not enough pickers"?

Adding pickers fixes CONTENTION (all pickers busy). But an AGV can also wait while a picker IS free
or IS assigned but still WALKING to the shelf -- travel/positioning, which more pickers does NOT fix.
This decomposes every picker-wait step (AGV parked on the shelf, not yet loaded) into:
  contention  : no free picker AND none assigned to me -> all pickers busy elsewhere (add pickers)
  travel      : a picker IS assigned to my shelf, still en route -> picker had to walk (positioning)
  dispatch gap: a free picker exists but none was sent to me -> assignment/coordination slack
Runs the deployed 8x4 and the ratio-optimal 8x6 so we can see what RESIDUAL wait survives at the
good ratio. Panel A: mean split per config. Panel B: the worst (lowest-banked) seeds' split at 8x6.
Output: results/picker_wait.png
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import _Urg8

STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "12"))))
CONFIGS = [(8, 4), (8, 6)]

C_CONT, C_TRAV, C_DISP = "#eb6834", "#2a78d6", "#eda100"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"


class _PT(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.log = {}

    def _on_predict(self, shelf, now, pred_finish):
        agv = getattr(self, "_cur_agv", None)
        if agv is not None:
            self.log.setdefault(shelf.id, {"aid": agv.id, "sx": shelf.x, "sy": shelf.y,
                                           "w": {"contention": 0, "travel": 0, "dispatch": 0},
                                           "done": False})


def run(seed, n_agv, n_pick):
    env = gym.make(f"wwm_sim-large-{n_agv}agvs-{n_pick}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _PT(env)
    by_aid = {a.id: a for a in ctrl.agvs}
    npick = len(ctrl.pickers)
    onv, t, done = 0.0, 0, False
    while not done and t < STEPS:
        env.step(ctrl.act())
        t += 1
        ap = ctrl.assigned_pickers
        assigned_cells = {(m.location_x, m.location_y) for m in ap.values()}
        n_free = npick - len(ap)
        for r in ctrl.log.values():
            if r["done"]:
                continue
            a = by_aid[r["aid"]]
            if (a.x, a.y) == (r["sx"], r["sy"]) and not a.carrying_shelf:
                if (r["sx"], r["sy"]) in assigned_cells:
                    r["w"]["travel"] += 1                 # a picker is en route to me
                elif n_free == 0:
                    r["w"]["contention"] += 1             # all pickers busy elsewhere
                else:
                    r["w"]["dispatch"] += 1               # free picker exists, not sent to me
        for sid, _a in getattr(env, "deliveries_this_step", []):
            r = ctrl.log.get(sid)
            if r is not None:
                r["done"] = True
            o_env = env
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = (t >= STEPS)
    tasks = [r for r in ctrl.log.values() if any(r["w"].values())]
    agg = {k: float(np.mean([r["w"][k] for r in ctrl.log.values()]) if ctrl.log else 0.0)
           for k in ("contention", "travel", "dispatch")}
    return {"onv": onv, "agg": agg,
            "per_task_wait": np.mean([sum(r["w"].values()) for r in ctrl.log.values()]) if ctrl.log else 0}


def main():
    os.makedirs("results", exist_ok=True)
    data = {c: [run(s, *c) for s in SEEDS] for c in CONFIGS}
    for c in CONFIGS:
        m = {k: np.mean([d["agg"][k] for d in data[c]]) for k in ("contention", "travel", "dispatch")}
        print(f"{c[0]}x{c[1]}: picker-wait/task  contention {m['contention']:.1f}  "
              f"travel {m['travel']:.1f}  dispatch {m['dispatch']:.1f}  (banked {np.mean([d['onv'] for d in data[c]]):.0f})")

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(12.4, 5.0), dpi=115)
    fig.patch.set_facecolor("white")
    # PANEL A: mean split per config
    labels = [f"{a}×{p}\n({'deployed' if p == 4 else 'ratio-optimal'})" for (a, p) in CONFIGS]
    x = np.arange(len(CONFIGS))
    means = {k: [np.mean([d["agg"][k] for d in data[c]]) for c in CONFIGS]
             for k in ("contention", "travel", "dispatch")}
    b0 = np.zeros(len(CONFIGS))
    for k, col, lab in [("contention", C_CONT, "contention (add pickers)"),
                        ("travel", C_TRAV, "travel (positioning)"),
                        ("dispatch", C_DISP, "dispatch gap (assignment)")]:
        axA.bar(x, means[k], 0.55, bottom=b0, color=col, edgecolor="white", linewidth=1.5, label=lab)
        for xi, (v, base) in enumerate(zip(means[k], b0)):
            if v > 0.6:
                axA.text(xi, base + v / 2, f"{v:.1f}", ha="center", va="center", color="white",
                         fontsize=9, fontweight="bold")
        b0 = b0 + np.array(means[k])
    axA.set_xticks(x)
    axA.set_xticklabels(labels, color=C_INK, fontsize=9)
    axA.set_ylabel("picker-wait steps per task", color=C_MUT, fontsize=9.5)
    axA.set_title("What shrinks with more pickers — and what doesn't", color=C_INK, fontsize=10.5, loc="left")
    axA.legend(frameon=False, fontsize=8.5, labelcolor=C_INK, loc="upper right")
    for s in ("top", "right"):
        axA.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        axA.spines[s].set_color(C_GRID)
    axA.tick_params(colors=C_MUT, labelsize=8)

    # PANEL B: worst (lowest-banked) seeds at 8x6 (optimal) -> residual cause breakdown
    opt = data[(8, 6)]
    order = np.argsort([d["onv"] for d in opt])[:6]     # 6 worst-banked seeds
    xb = np.arange(len(order))
    b0 = np.zeros(len(order))
    for k, col in [("contention", C_CONT), ("travel", C_TRAV), ("dispatch", C_DISP)]:
        vals = [opt[i]["agg"][k] for i in order]
        axB.bar(xb, vals, 0.6, bottom=b0, color=col, edgecolor="white", linewidth=1.5)
        b0 = b0 + np.array(vals)
    axB.set_xticks(xb)
    axB.set_xticklabels([f"s{SEEDS[i]}\n{opt[i]['onv']:.0f}" for i in order], color=C_INK, fontsize=8)
    axB.set_ylabel("picker-wait steps per task", color=C_MUT, fontsize=9.5)
    axB.set_xlabel("worst-banked seeds at 8×6 (banked value below)", color=C_MUT, fontsize=9)
    axB.set_title("Failed seeds at the OPTIMAL ratio: what's left is travel", color=C_INK,
                  fontsize=10.5, loc="left")
    for s in ("top", "right"):
        axB.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        axB.spines[s].set_color(C_GRID)
    axB.tick_params(colors=C_MUT, labelsize=8)
    fig.text(0.005, 0.01, f"{len(SEEDS)} day-list seeds, champion+urg8. contention = all pickers busy "
             "(add pickers); travel = picker walking to the shelf (positioning); dispatch = free picker not sent.",
             color=C_MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig("results/picker_wait.png", facecolor="white")
    print("PNG: results/picker_wait.png")


if __name__ == "__main__":
    main()
