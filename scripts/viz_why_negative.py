"""viz_why_negative -- why sharpening the delay bias is ~0 (and can go negative) on day-list.

The delay bias changes a decision ONLY by flipping a task makeable<->doomed at the deadline cliff.
A task flips only if its slack (deadline - empty-world finish) is close to the bias b. So:
  - tasks with big slack are makeable for ANY reasonable b   (bias irrelevant)
  - tasks with big negative slack are doomed for any b        (bias irrelevant)
  - only the SLIVER with slack ~ b can flip -- and that sliver is a MIX of truly on-time (green) and
    truly late (red), so no bias value cleanly sorts it. Sharpening b just reshuffles the sliver -> ~0.
    Pushing b too high sweeps genuinely-on-time (green) tasks into 'doomed' -> abandons them -> LOSS.

Real committed+delivered tasks, pooled over day-list seeds; slack on x, dot color = the task's TRUE
on-time outcome. A bias line sweeps right; the shaded band is the only zone that can flip.
Output: results/why_negative.gif
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
FLIP_W = 5.0     # a task within +-FLIP_W of the bias line is "in the flip sliver"

C_ON, C_LATE, C_BAND, C_BIAS = "#1baf7a", "#e34948", "#eda100", "#40403e"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"


class _T(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.log = {}

    def _on_predict(self, shelf, now, pred_finish):
        from wwm_sim.values import task_value
        if shelf.deadline is not None:
            self.log.setdefault(shelf.id, {"t0": int(now), "pred": float(pred_finish),
                                           "dl_rel": float(shelf.deadline - now),
                                           "value": float(task_value(shelf))})


def collect():
    allt = []
    for sd in range(int(os.environ.get("NSEED", "16"))):
        env = gym.make(ENV).unwrapped
        env.reset(seed=sd)
        env.request_queue = []
        env.demand_model = DemandModel(env, seed=sd)
        env.demand_model.seed_day_list(env, horizon=STEPS)
        ctrl = _T(env)
        t = 0
        while t < STEPS:
            env.step(ctrl.act())
            t += 1
            for sid, _a in getattr(env, "deliveries_this_step", []):
                r = ctrl.log.get(sid)
                if r is not None and "true" not in r:
                    r["true"] = float(t - r["t0"])
        for r in ctrl.log.values():
            if "true" in r:
                allt.append(r)
        ctrl.log = {}
    return allt


def frame(tasks, b, ys):
    fig, ax = plt.subplots(figsize=(10.2, 5.4), dpi=115)
    fig.patch.set_facecolor("white")
    slack = np.array([r["dl_rel"] - r["pred"] for r in tasks])
    ont = np.array([r["true"] <= r["dl_rel"] for r in tasks])
    # flip sliver band around b
    ax.axvspan(b - FLIP_W, b + FLIP_W, color=C_BAND, alpha=0.22, zorder=0)
    ax.axvline(b, color=C_BIAS, lw=2.2, zorder=4)
    # dots: green truly on-time, red truly late
    ax.scatter(slack[ont], ys[ont], s=26, color=C_ON, alpha=0.75, edgecolors="none", zorder=2)
    ax.scatter(slack[~ont], ys[~ont], s=26, color=C_LATE, alpha=0.8, edgecolors="none", zorder=2)
    # counts
    in_band = np.abs(slack - b) <= FLIP_W
    swept = (slack < b - FLIP_W)                       # firmly doomed by this bias
    abandoned = int((ont & (slack < b)).sum())         # truly on-time but bias marks doomed
    n_on = int((ont & in_band).sum()); n_late = int((~ont & in_band).sum())
    ax.set_xlim(-25, 40)
    ax.set_ylim(-0.05, 1.05)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=9)
    ax.set_xlabel("task slack  =  deadline − empty-world finish  (steps)", color=C_MUT, fontsize=10)
    ax.axvline(0, color=C_GRID, lw=1, zorder=1)
    # zone labels
    ax.text(-24, 0.96, "makeable for ANY b →\n(bias irrelevant)", color=C_MUT, fontsize=8.5, va="top")
    ax.text(39, 0.96, "← makeable for ANY b\n(bias irrelevant)", color=C_MUT, fontsize=8.5,
            va="top", ha="right")
    ax.text(b, -0.02, f"bias b={b:.0f}\nFLIP SLIVER: {n_on} on-time + {n_late} late\n(mixed → no b sorts it)",
            color="#8a6d00", fontsize=9, ha="center", va="top", fontweight="bold")
    ax.set_title(f"Why sharpening the bias ≈ 0 on day-list   (at b={b:.0f}, "
                 f"{abandoned} truly-winnable tasks already marked doomed)",
                 color=C_INK, fontsize=10.5, loc="left")
    # legend
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0], [0], marker="o", color="w", markerfacecolor=C_ON, markersize=9,
                              label="truly ON-TIME"),
                       Line2D([0], [0], marker="o", color="w", markerfacecolor=C_LATE, markersize=9,
                              label="truly LATE")],
              loc="upper center", frameon=False, fontsize=9, ncol=2, labelcolor=C_INK)
    fig.text(0.005, 0.01, f"{len(tasks)} real committed tasks, day-list. Only the sliver flips; it's a "
             "mix of green & red, so no bias cleanly sorts it → sharpening ~0, over-shift sweeps green → loss.",
             color=C_MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    tasks = collect()
    rng = np.random.RandomState(0)
    ys = rng.uniform(0.12, 0.9, size=len(tasks))       # vertical jitter for visibility (cosmetic)
    sweep = list(np.arange(0, 28, 1.5))
    frames = [frame(tasks, b, ys) for b in sweep]
    frames += [frames[-1]] * 6
    durs = [240] * (len(frames) - 6) + [600] * 6
    frames[0].save("results/why_negative.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/why_negative.gif ({len(tasks)} tasks, {len(frames)} frames)")


if __name__ == "__main__":
    main()
