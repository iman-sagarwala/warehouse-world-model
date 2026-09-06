"""Where does completion NOISE come from? Driving is predictable; the WAITS are not.

A committed route fixes the DISTANCE, so the driving part of a completion barely varies from the
straight-line estimate. All the noise is in WAITING -- for a picker, to yield to traffic, at a dock --
because those are set by the other 15 agents in real time, not by your path. This plots the per-task
distribution of each component so the spread is visible: 'driving vs distance' clusters tight near 0
(predictable), while picker wait / traffic yield are wide (the noise). Output: results/noise_sources.png
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
from wwm_sim.rollout import nearest_dock_dist, _manhattan
from viz_value_loss import _Tracer, task_segments

STEPS = 500
C_PRED, C_NOISE, C_INK, C_MUT, C_GRID = "#1baf7a", "#e34948", "#40403e", "#8a8a82", "#d6d5cd"


def collect():
    comps = {"driving\n(vs distance)": [], "picker wait": [], "traffic yield": [], "dock queue": []}
    for sd in range(int(os.environ.get("NSEED", "12"))):
        env = gym.make("wwm_sim-large-8agvs-4pickers-globalobs-v1").unwrapped
        env.reset(seed=sd)
        env.request_queue = []
        env.demand_model = DemandModel(env, seed=sd)
        env.demand_model.seed_day_list(env, horizon=STEPS)
        ctrl = _Tracer(env)
        by_aid = {a.id: a for a in ctrl.agvs}
        t = 0
        while t < STEPS:
            env.step(ctrl.act())
            t += 1
            for r in ctrl.tasks.values():
                if r["t_end"] is None:
                    a = by_aid[r["aid"]]
                    r["trace"].append((a.x, a.y, bool(a.carrying_shelf)))
            for sid, _a in getattr(env, "deliveries_this_step", []):
                r = ctrl.tasks.get(sid)
                if r is not None and r["t_end"] is None:
                    r["t_end"] = t
        for r in ctrl.tasks.values():
            if r["t_end"] is None:
                continue
            seg = task_segments(env, r)
            mf = _manhattan(r["ax"], r["ay"], r["sx"], r["sy"])
            mh = nearest_dock_dist(env, r["sx"], r["sy"])
            comps["driving\n(vs distance)"].append(seg["drive"] - (mf + mh))
            comps["picker wait"].append(seg["pick"])
            comps["traffic yield"].append(seg["block"])
            comps["dock queue"].append(seg["dockq"])
    return {k: np.array(v, float) for k, v in comps.items()}


def main():
    os.makedirs("results", exist_ok=True)
    comps = collect()
    names = list(comps)
    fig, ax = plt.subplots(figsize=(10.4, 5.2), dpi=115)
    fig.patch.set_facecolor("white")
    rng = np.random.RandomState(0)
    ys = np.arange(len(names))[::-1]
    for y, nm in zip(ys, names):
        v = comps[nm]
        predictable = v.std() < 4.0
        col = C_PRED if predictable else C_NOISE
        jit = y + rng.uniform(-0.16, 0.16, size=len(v))
        ax.scatter(v, jit, s=10, color=col, alpha=0.28, edgecolors="none", zorder=2)
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        ax.plot([q1, q3], [y, y], color=col, lw=8, alpha=0.5, solid_capstyle="round", zorder=3)
        ax.plot([med, med], [y - 0.22, y + 0.22], color=col, lw=2.5, zorder=4)
        ax.text(v.max() + 1.5, y, f"mean {v.mean():+.1f}  ±{v.std():.0f}", va="center",
                color=C_INK, fontsize=9.5, fontweight="bold")
    ax.axvline(0, color=C_GRID, lw=1.2, zorder=1)
    ax.set_yticks(ys)
    ax.set_yticklabels(names, color=C_INK, fontsize=10)
    ax.set_xlim(-8, 62)
    ax.set_ylim(-0.6, len(names) - 0.3)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8.5)
    ax.set_xlabel("extra steps added to a task (0 = as the estimate expected)", color=C_MUT, fontsize=10)
    ax.set_title("Why completions are noisy: driving is predictable, the WAITS are not",
                 color=C_INK, fontsize=12.5, loc="left", fontweight="bold")
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0], [0], marker="o", color="w", markerfacecolor=C_PRED, markersize=9,
                              label="predictable (tight)"),
                       Line2D([0], [0], marker="o", color="w", markerfacecolor=C_NOISE, markersize=9,
                              label="noisy (wide) = set by other agents")],
              loc="lower right", frameon=False, fontsize=9, labelcolor=C_INK)
    fig.text(0.06, 0.02, f"{len(comps['picker wait'])} real tasks, day-list. Driving hugs the distance "
             "estimate; picker wait & traffic yield are wide because they depend on the other 15 agents "
             "in real time.", color=C_MUT, fontsize=8)
    fig.subplots_adjust(bottom=0.14, top=0.9, left=0.13, right=0.97)
    fig.savefig("results/noise_sources.png", facecolor="white")
    print("PNG: results/noise_sources.png")
    for nm in names:
        print(f"  {nm.splitlines()[0]:16} mean {comps[nm].mean():+5.1f}  std {comps[nm].std():4.1f}")


if __name__ == "__main__":
    main()
