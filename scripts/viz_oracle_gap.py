"""Value-loss causes vs the picker oracle: what each fix recovers, and what's left.

Runs the per-order value-loss autopsy for three arms on the same day-list seeds:
  current  = champion+urg8 (today)
  pkrate   = + value-rate picker scoring (our fix)
  oracle   = pickers never absent (env.pickers_free) -> zero picker wait (the ceiling)
Plots the loss causes (picker wait / traffic / never-served / doomed) side by side, so you see the
picker-wait slice: barely dented by pkrate, erased by the oracle -> the gap = the picker prize still
on the table. Output: results/oracle_gap.png
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
from wwm_sim.rollout import _manhattan, nearest_dock_dist
from viz_value_loss import task_segments, best_case_t0, dominant_cause
from congestion_policies import _Urg8, _PkRate

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "16"))))

C_PICK, C_TRAF, C_NEVER, C_DOOM, C_BANK = "#2a78d6", "#eb6834", "#4a3aa7", "#8a8a82", "#1baf7a"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"


def make_tracer(base):
    class _T(base):
        def __init__(self, env):
            super().__init__(env)
            self.tasks = {}

        def _on_predict(self, shelf, now, pred_finish):
            agv = getattr(self, "_cur_agv", None)
            if agv is not None:
                self.tasks.setdefault(shelf.id, {
                    "aid": agv.id, "ax": agv.x, "ay": agv.y, "sx": shelf.x, "sy": shelf.y,
                    "t0": int(now), "trace": [], "t_end": None})
    return _T


def run_seed(seed, base, free):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.pickers_free = bool(free)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = make_tracer(base)(env)
    by_aid = {a.id: a for a in ctrl.agvs}
    agv_xy = [(a.x, a.y) for a in ctrl.agvs]
    pk_xy = [(p.x, p.y) for p in ctrl.pickers]
    orders = []
    for sid, lst in env.demand_model.pending.items():
        for o in lst:
            orders.append({"sid": sid, "sx": o.shelf.x, "sy": o.shelf.y,
                           "value": float(o.value), "deadline": o.deadline})
    deliv = {}
    t = 0
    while t < STEPS:
        env.step(ctrl.act())
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
        done = (t >= STEPS)
    seg_by = {sid: task_segments(env, r) for sid, r in ctrl.tasks.items() if r["t_end"] is not None}
    out = {"banked": 0.0, "doomed": 0.0, "never": 0.0, "pick": 0.0, "block": 0.0, "dock": 0.0}
    for o in orders:
        bc = best_case_t0(env, o["sx"], o["sy"], agv_xy, pk_xy)
        makeable0 = (o["deadline"] is not None) and (o["deadline"] >= bc)
        D = deliv.get(o["sid"])
        if D is not None and o["deadline"] is not None and D <= o["deadline"]:
            out["banked"] += o["value"]
        elif not makeable0:
            out["doomed"] += o["value"]
        elif D is not None:
            cause = dominant_cause(seg_by.get(o["sid"], {"pick": 1, "block": 0, "dockq": 0}))
            out[{"picker wait": "pick", "traffic block": "block", "dock queue": "dock"}[cause]] += o["value"]
        else:
            out["never"] += o["value"]
    return out


def main():
    os.makedirs("results", exist_ok=True)
    arms = [("current", _Urg8, False), ("pkrate\n(value-rate)", _PkRate, False),
            ("oracle\n(free pickers)", _Urg8, True)]
    agg = {}
    for name, base, free in arms:
        rs = [run_seed(s, base, free) for s in SEEDS]
        agg[name] = {k: np.mean([r[k] for r in rs]) for k in rs[0]}
        a = agg[name]
        print(f"{name.splitlines()[0]:10} banked {a['banked']:.0f}  picker {a['pick']:.0f}  "
              f"traffic {a['block']:.0f}  never {a['never']:.0f}  doomed {a['doomed']:.0f}", flush=True)

    names = [a[0] for a in arms]
    fig, ax = plt.subplots(figsize=(9.6, 5.4), dpi=115)
    fig.patch.set_facecolor("white")
    x = np.arange(len(names))
    b0 = np.zeros(len(names))
    for key, col, lab in [("pick", C_PICK, "picker wait"), ("block", C_TRAF, "traffic"),
                          ("never", C_NEVER, "never served"), ("doom", C_DOOM, "doomed")]:
        kk = "doomed" if key == "doom" else key
        vals = [agg[n][kk] for n in names]
        ax.bar(x, vals, 0.55, bottom=b0, color=col, edgecolor="white", linewidth=1.5, label=lab)
        for xi, (v, base) in enumerate(zip(vals, b0)):
            if v > 1.5:
                ax.text(xi, base + v / 2, f"{v:.0f}", ha="center", va="center", color="white",
                        fontsize=9, fontweight="bold")
        b0 = b0 + np.array(vals)
    for xi, n in enumerate(names):
        ax.text(xi, b0[xi] + 1, f"lost {b0[xi]:.0f}\nbanked {agg[n]['banked']:.0f}", ha="center",
                va="bottom", color=C_INK, fontsize=9, fontweight="bold")
    # annotate the picker-prize gap between pkrate and oracle
    pk_pkrate, pk_oracle = agg[names[1]]["pick"], agg[names[2]]["pick"]
    ax.annotate("", xy=(2, pk_oracle + 0.5), xytext=(1, pk_pkrate / 2),
                arrowprops=dict(arrowstyle="->", color=C_INK, lw=1.6))
    ax.text(1.5, pk_pkrate * 0.7 + 6, f"picker prize\nstill on the table\n(~{pk_pkrate:.0f}/day)",
            ha="center", color=C_PICK, fontsize=9.5, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(names, color=C_INK, fontsize=10)
    ax.set_ylim(0, b0.max() * 1.45)
    ax.set_ylabel("value LOST ($/day, avg)", color=C_MUT, fontsize=10)
    ax.set_title("Value-loss causes vs the picker oracle: what each fix recovers",
                 color=C_INK, fontsize=12, loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=9, labelcolor=C_INK, loc="upper right", ncol=2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8.5)
    fig.text(0.06, 0.02, f"{len(SEEDS)} day-list seeds. Oracle = pickers never absent (zero picker "
             "wait). pkrate dents the picker-wait slice; the oracle erases it — the gap is unclaimed.",
             color=C_MUT, fontsize=8)
    fig.subplots_adjust(bottom=0.13, top=0.9, left=0.09, right=0.97)
    fig.savefig("results/oracle_gap.png", facecolor="white")
    print("PNG: results/oracle_gap.png")


if __name__ == "__main__":
    main()
