"""viz_value_loss -- WHERE does prize money leak? (value lost, not steps late)

Delay != value loss: a task can run 30 steps late and bank full value if it had slack; another can
be 2 steps late and lose everything at the deadline cliff. This autopsies the MONEY, per order.

On day-list every order is visible at t=0, so "unmakeable" is planner-independent: deadline shorter
than the best physically-possible delivery starting at t=0 (geom_completion with robots at start).
Every order that fails to bank falls in exactly one bucket:
  1. DOOMED FROM START  -- unmakeable at t=0 (rush orders too tight). Nothing any planner could do.
  2. MISSED AT THE CLIFF -- makeable at t=0, shelf WAS delivered, but this order's deadline slipped
                            past the delivery moment. Attributed to the task's dominant execution
                            overrun (picker wait / traffic block / dock queue). THE addressable loss.
  3. NEVER SERVED       -- makeable at t=0, shelf never delivered by day-end (capacity / deprioritized).

Output: results/value_loss.png -- three graphs (top-level $ decomposition; cliff-loss by physical
cause, value-weighted; never-served by value tier). 10 day-list seeds, champion+urg8.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from wwm_sim.rollout import nearest_dock_dist, _manhattan
from congestion_policies import _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "10"))))
LOAD_TIME = 5

# validated palette (dataviz default, light): banked green, then loss causes
C_BANK = "#1baf7a"
C_DOOM, C_CLIFF, C_NEVER = "#8a8a82", "#eb6834", "#4a3aa7"   # gray unavoidable / orange / violet
C_PICK, C_BLOCK, C_DOCK = "#2a78d6", "#eb6834", "#eda100"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"


class _Tracer(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.tasks = {}

    def _on_predict(self, shelf, now, pred_finish):
        agv = getattr(self, "_cur_agv", None)
        if agv is None:
            return
        self.tasks.setdefault(shelf.id, {
            "aid": agv.id, "t0": int(now), "pred": float(pred_finish),
            "ax": agv.x, "ay": agv.y, "sx": shelf.x, "sy": shelf.y, "trace": [], "t_end": None})


def best_case_t0(env, sx, sy, agv_xy, pk_xy):
    """Best physically-possible steps-to-deliver starting at t=0 (nearest AGV & picker at start)."""
    tf = min(_manhattan(ax, ay, sx, sy) for (ax, ay) in agv_xy)
    tp = min(_manhattan(px, py, sx, sy) for (px, py) in pk_xy)
    return max(tf, tp) + LOAD_TIME + nearest_dock_dist(env, sx, sy)


def task_segments(env, r):
    """Stationary-time split for a delivered task (same scheme as viz_delay)."""
    prev = (r["ax"], r["ay"])
    loaded = False
    seg = {"drive": 0, "block": 0, "pick": 0, "dockq": 0}
    for (x, y, carry) in r["trace"][: r["t_end"] - r["t0"]]:
        moved = (x, y) != prev
        if not loaded and carry:
            loaded = True
        if moved:
            seg["drive"] += 1
        elif not loaded:
            seg["pick" if (x, y) == (r["sx"], r["sy"]) else "block"] += 1
        else:
            near = min(_manhattan(x, y, gx, gy) for (gx, gy) in env.goals) <= 2
            seg["dockq" if near else "block"] += 1
        prev = (x, y)
    return seg


def dominant_cause(seg):
    m = {"picker wait": seg["pick"], "traffic block": seg["block"], "dock queue": seg["dockq"]}
    return max(m.items(), key=lambda kv: kv[1])[0]


def run_seed(seed):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _Tracer(env)
    by_aid = {a.id: a for a in ctrl.agvs}
    agv_xy = [(a.x, a.y) for a in ctrl.agvs]
    pk_xy = [(p.x, p.y) for p in ctrl.pickers]
    # snapshot every order (all pending at t=0 in day-list)
    orders = []
    for sid, lst in env.demand_model.pending.items():
        for o in lst:
            orders.append({"sid": sid, "sx": o.shelf.x, "sy": o.shelf.y, "value": float(o.value),
                           "deadline": o.deadline, "is_rush": bool(o.is_rush)})
    deliv = {}                                  # sid -> delivery step
    t, done = 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        for r in ctrl.tasks.values():
            if r["t_end"] is None:
                a = by_aid[r["aid"]]
                r["trace"].append((a.x, a.y, bool(a.carrying_shelf)))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            deliv.setdefault(sid, t)
            r = ctrl.tasks.get(sid)
            if r is not None and r["t_end"] is None:
                r["t_end"] = t
        done = all(term) or all(trunc)
    # per-shelf segment cause (for delivered shelves)
    seg_by_sid = {sid: task_segments(env, r) for sid, r in ctrl.tasks.items() if r["t_end"] is not None}
    # bucket every order into value outcomes
    out = {"banked": 0.0, "doomed": 0.0, "never": 0.0,
           "cliff": {"picker wait": 0.0, "traffic block": 0.0, "dock queue": 0.0},
           "never_tiers": {"lo": 0.0, "mid": 0.0, "hi": 0.0}, "potential": 0.0}
    for o in orders:
        out["potential"] += o["value"]
        bc = best_case_t0(env, o["sx"], o["sy"], agv_xy, pk_xy)
        makeable0 = (o["deadline"] is not None) and (o["deadline"] >= bc)
        D = deliv.get(o["sid"])
        if D is not None and o["deadline"] is not None and D <= o["deadline"]:
            out["banked"] += o["value"]
        elif not makeable0:
            out["doomed"] += o["value"]                 # unmakeable from t=0 -> unavoidable
        elif D is not None:                             # delivered, but past this order's deadline
            cause = dominant_cause(seg_by_sid.get(o["sid"], {"pick": 1, "block": 0, "dockq": 0}))
            out["cliff"][cause] += o["value"]
        else:                                           # feasible but shelf never delivered
            out["never"] += o["value"]
            tier = "hi" if o["value"] >= 10 else ("mid" if o["value"] >= 5 else "lo")
            out["never_tiers"][tier] += o["value"]
    return out


def main():
    os.makedirs("results", exist_ok=True)
    accs = [run_seed(s) for s in SEEDS]
    for s, a in zip(SEEDS, accs):
        print(f"seed {s}: potential {a['potential']:.0f}  banked {a['banked']:.0f}  "
              f"doomed {a['doomed']:.0f}  cliff {sum(a['cliff'].values()):.0f}  never {a['never']:.0f}",
              flush=True)
    n = len(accs)
    tot = lambda k: np.mean([a[k] for a in accs])
    pot = tot("potential")
    banked, doomed, never = tot("banked"), tot("doomed"), tot("never")
    cliff = {k: np.mean([a["cliff"][k] for a in accs]) for k in accs[0]["cliff"]}
    cliff_tot = sum(cliff.values())
    tiers = {k: np.mean([a["never_tiers"][k] for a in accs]) for k in accs[0]["never_tiers"]}

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(13.6, 4.7), dpi=115)
    fig.patch.set_facecolor("white")

    # GRAPH 1: where every potential dollar goes (stacked single bar)
    parts = [("banked on time", banked, C_BANK),
             ("doomed from start", doomed, C_DOOM),
             ("missed at the cliff", cliff_tot, C_CLIFF),
             ("never served", never, C_NEVER)]
    left = 0.0
    for lab, v, c in parts:
        ax1.barh(0, v, left=left, height=0.5, color=c, edgecolor="white", linewidth=2)
        if v / pot > 0.03:
            ax1.text(left + v / 2, 0, f"{v/pot*100:.0f}%", ha="center", va="center",
                     color="white", fontsize=10, fontweight="bold")
        left += v
    ax1.set_xlim(0, pot)
    ax1.set_ylim(-0.5, 1.5)
    ax1.set_yticks([])
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in parts]
    ax1.legend(handles, [f"{lab}  ({v:.0f})" for lab, v, _ in parts], loc="upper left",
               frameon=False, fontsize=9, labelcolor=C_INK, ncol=1, bbox_to_anchor=(0, 1.02))
    for sp in ("top", "right", "left"):
        ax1.spines[sp].set_visible(False)
    ax1.spines["bottom"].set_color(C_GRID)
    ax1.tick_params(colors=C_MUT, labelsize=8)
    ax1.set_xlabel("prize value ($/day, avg)", color=C_MUT, fontsize=9)
    loss = doomed + cliff_tot + never
    ax1.set_title(f"Every potential dollar (avg {pot:.0f}/day)\n"
                  f"banked {banked/pot*100:.0f}%  |  lost {loss/pot*100:.0f}%",
                  color=C_INK, fontsize=10.5, loc="left")

    # GRAPH 2: the addressable loss -- cliff misses by physical cause (value-weighted)
    order2 = ["picker wait", "traffic block", "dock queue"]
    vals2 = [cliff[k] for k in order2]
    cols2 = [C_PICK, C_BLOCK, C_DOCK]
    yy = np.arange(len(order2))[::-1]
    ax2.barh(yy, vals2, height=0.55, color=cols2, edgecolor="white", linewidth=2)
    for y, v in zip(yy, vals2):
        ax2.text(v + cliff_tot * 0.02 + 0.3, y, f"{v:.0f}  ({v/max(cliff_tot,1)*100:.0f}%)",
                 va="center", color=C_INK, fontsize=9)
    ax2.set_yticks(yy)
    ax2.set_yticklabels(order2, color=C_INK, fontsize=9)
    ax2.set_xlim(0, max(vals2) * 1.35 + 1)
    for sp in ("top", "right", "left"):
        ax2.spines[sp].set_visible(False)
    ax2.spines["bottom"].set_color(C_GRID)
    ax2.tick_params(colors=C_MUT, labelsize=8)
    ax2.set_xlabel("prize value lost ($/day, avg)", color=C_MUT, fontsize=9)
    ax2.set_title(f"Missed at the cliff: WHY ({cliff_tot:.0f}/day)\n"
                  f"the only planner-addressable slice", color=C_INK, fontsize=10.5, loc="left")

    # GRAPH 3: never-served by value tier -- are we abandoning cheap or dear orders?
    order3 = [("high (>=10)", tiers["hi"], "#e34948"), ("mid (5-10)", tiers["mid"], C_DOCK),
              ("low (<5)", tiers["lo"], C_GRID)]
    yy3 = np.arange(len(order3))[::-1]
    ax3.barh(yy3, [v for _, v, _ in order3], height=0.55,
             color=[c for _, _, c in order3], edgecolor="white", linewidth=2)
    for y, (_, v, _) in zip(yy3, order3):
        ax3.text(v + never * 0.02 + 0.3, y, f"{v:.0f}", va="center", color=C_INK, fontsize=9)
    ax3.set_yticks(yy3)
    ax3.set_yticklabels([lab for lab, _, _ in order3], color=C_INK, fontsize=9)
    ax3.set_xlim(0, max([v for _, v, _ in order3]) * 1.3 + 1)
    for sp in ("top", "right", "left"):
        ax3.spines[sp].set_visible(False)
    ax3.spines["bottom"].set_color(C_GRID)
    ax3.tick_params(colors=C_MUT, labelsize=8)
    ax3.set_xlabel("prize value lost ($/day, avg)", color=C_MUT, fontsize=9)
    ax3.set_title(f"Never served: which orders ({never:.0f}/day)\n"
                  f"capacity limit -- 8 AGVs can't clear all", color=C_INK, fontsize=10.5, loc="left")

    fig.text(0.005, 0.01, f"{n} day-list seeds, champion+urg8  |  value lost != steps late: "
             f"a task delayed but with slack still banks full value.", color=C_MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig("results/value_loss.png", facecolor="white")
    print(f"\nPNG: results/value_loss.png")
    print(f"potential {pot:.0f}  banked {banked:.0f} ({banked/pot*100:.0f}%)  "
          f"doomed {doomed:.0f}  cliff {cliff_tot:.0f}  never {never:.0f}")
    print(f"cliff by cause: " + "  ".join(f"{k} {v:.0f}" for k, v in cliff.items()))


if __name__ == "__main__":
    main()
