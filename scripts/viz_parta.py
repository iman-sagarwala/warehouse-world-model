"""Part A route visualization — chosen route highlighted + all candidate routes.

Runs the Part A funnel and draws two panels at a snapshot step:
  LEFT  "CHOSEN"          : the committed route per AGV (bold, one colour each).
  RIGHT "ALL CANDIDATES"  : every Yen's route generated for each AGV's chosen task
                            (faint), with the chosen one bold on top — so you can SEE
                            the alternatives the funnel weighed and which it picked.

Headless PNG (avoids the live-window hang). Run:
    python scripts/viz_parta.py [--seed S] [--step N] [--out path.png]
"""
from __future__ import annotations

import argparse
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
import numpy as np

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values
from wwm_sim.battery import default_chargers
from sim_dashboard import grid_image, agent_scatter
from sim_priority import PartAController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"


def draw_base(ax, env, title):
    ax.imshow(grid_image(env), interpolation="nearest", zorder=0)
    for (cx, cy) in default_chargers(env):                     # charger bays (gold squares)
        ax.scatter(cx, cy, marker="s", s=70, c="gold", edgecolors="k", linewidths=0.5, zorder=2)
    agv_xy, agv_c, pk_xy = agent_scatter(env)
    if len(agv_xy):
        ax.scatter(agv_xy[:, 0], agv_xy[:, 1], c=agv_c, s=90, edgecolors="k", linewidths=0.6, zorder=4)
    if len(pk_xy):
        ax.scatter(pk_xy[:, 0], pk_xy[:, 1], c=[[0.12, 0.56, 1.0]], marker="D", s=70,
                   edgecolors="k", linewidths=0.6, zorder=4)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--step", type=int, default=25)
    ap.add_argument("--focus", type=int, default=0, help="index of the robot whose funnel to show on the right")
    ap.add_argument("--focus-kind", choices=["agv", "picker"], default="agv",
                    help="show an AGV's task funnel or a PICKER's rendezvous funnel on the right")
    ap.add_argument("--out", default="results/parta_routes.png")
    args = ap.parse_args()

    env = gym.make(ENV).unwrapped
    env.reset(seed=args.seed)
    attach_deadlines(env, load_deadlines("data/deadlines_example.txt"))
    attach_values(env, load_values("data/values_example.txt"))
    ctrl = PartAController(env)
    for _ in range(args.step):
        env.step(ctrl.act())

    agvs = list(ctrl.routes.keys())
    cmap = plt.get_cmap("tab10")
    colour = {a: cmap(i % 10) for i, a in enumerate(agvs)}

    os.makedirs("results", exist_ok=True)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(17, 8))

    pickers = list(getattr(ctrl, "picker_routes", {}).keys())

    # LEFT: chosen routes — AGVs (solid) and PICKERS (dashed) to their rendezvous
    draw_base(axL, env, f"CHOSEN routes: AGV (solid) + Picker (dashed)  (seed {args.seed}, step {args.step})")
    for a in agvs:
        r = ctrl.routes.get(a) or []
        if len(r) < 2:
            continue
        xs = [c[0] for c in r]; ys = [c[1] for c in r]
        axL.plot(xs, ys, "-", lw=2.8, color=colour[a], alpha=0.95, zorder=3)
        axL.scatter([xs[-1]], [ys[-1]], marker="*", s=160, color=colour[a],
                    edgecolors="k", linewidths=0.6, zorder=5)     # the target shelf
    for p in pickers:
        r = ctrl.picker_routes.get(p) or []
        if len(r) < 2:
            continue
        axL.plot([c[0] for c in r], [c[1] for c in r], "--", lw=1.8,
                 color=[0.12, 0.56, 1.0], alpha=0.85, zorder=3)   # picker rendezvous route

    # RIGHT: FOCUS one robot's funnel — AGV task funnel OR picker rendezvous funnel — each
    # candidate weighed, its full Yen's route set, chosen bold. (Robots share candidates, so
    # the all-robot overlay merges; the focus view keeps one robot's choice legible.)
    if args.focus_kind == "picker":
        robots, cand_map, chosen_map, klabel = (
            pickers, getattr(ctrl, "picker_candidate_tasks", {}), ctrl.picker_routes, "Picker")
        def tgt_xy(key):   # key = (gx, gy) rendezvous cell
            return key[0], key[1]
        what = "candidate AGV rendezvous"
    else:
        robots, cand_map, chosen_map, klabel = (agvs, ctrl.candidate_tasks, ctrl.routes, "AGV")
        def tgt_xy(key):   # key = shelf
            return key.x, key.y
        what = "candidate tasks"
    fr = robots[args.focus % len(robots)] if robots else None
    cts = cand_map.get(fr, []) if fr is not None else []
    rid = getattr(fr, "id", "-")
    draw_base(axR, env, f"{klabel}{rid} funnel: {len(cts)} {what} × Yen's routes  — chosen bold")
    if fr is not None:
        axR.scatter([fr.x], [fr.y], s=320, facecolors="none", edgecolors="k",
                    linewidths=2.0, zorder=6)                      # ring the focused robot
    chosen_route = chosen_map.get(fr) or []
    ccmap = plt.get_cmap("cool")
    for i, (key, task_routes) in enumerate(cts):
        tx, ty = tgt_xy(key)
        is_chosen_task = (i == 0)                                 # scored[0] = the committed choice
        col = "crimson" if is_chosen_task else ccmap(i / max(1, len(cts) - 1))
        for r in task_routes:                                     # ALL Yen's routes for this candidate
            if len(r) < 2:
                continue
            is_chosen_route = is_chosen_task and (r == chosen_route)
            axR.plot([c[0] for c in r], [c[1] for c in r], "-",
                     lw=3.4 if is_chosen_route else (2.0 if is_chosen_task else 1.4),
                     color=col,
                     alpha=0.95 if is_chosen_route else (0.75 if is_chosen_task else 0.5),
                     zorder=4 if is_chosen_task else 3)
        axR.scatter([tx], [ty], marker="*", s=230 if is_chosen_task else 95,
                    color=col, edgecolors="k", linewidths=0.6, zorder=5)
        axR.annotate("CHOSEN" if is_chosen_task else f"cand {i + 1}", (tx, ty),
                     textcoords="offset points", xytext=(5, 4), fontsize=7.5,
                     fontweight="bold" if is_chosen_task else "normal", color=col, zorder=7)

    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    legend = [
        Line2D([0], [0], color="k", lw=2.8, label="chosen task+route"),
        Line2D([0], [0], color="k", lw=1.3, alpha=0.35, label="route to another candidate task"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=[1, 0.55, 0], markersize=10,
               markeredgecolor="k", label="AGV"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor=[0.12, 0.56, 1], markersize=9,
               markeredgecolor="k", label="Picker"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="gold", markersize=10,
               markeredgecolor="k", label="charger"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="gray", markersize=13,
               markeredgecolor="k", label="target shelf"),
        Patch(facecolor=[0, 0.5, 0.5], label="requested shelf (task)"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=7, fontsize=9, frameon=False)
    fig.suptitle("Part A: per-robot funnel — cheap screen → Yen's routes → score → commit robot→task→route",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])
    fig.savefig(args.out, dpi=110)
    print(f"wrote {args.out}  ({len(agvs)} AGVs with committed routes)")


if __name__ == "__main__":
    main()
