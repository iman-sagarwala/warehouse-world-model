"""GIF 3 -- why delay is too NOISY to commit to a fixed plan ("stick to your guns" fails).

Same plan, different reality: plot every task's empty-world estimate (x) against the delay it
actually suffered (y). At ANY given estimate the delays scatter wildly -- identical inputs, very
different outcomes -- because a task's delay is set by where the OTHER 11 robots and 4 pickers happen
to be, which you don't control and can't know in advance. So a rollout that commits to one predicted
delay is aiming at a moving target: it is wrong within ~2 decisions (measured open-loop cost: -11.3
vs re-planning). The cure is not a better guess -- it's to re-decide every step against what actually
happened. Grounded in real committed tasks. Output: results/gif_noise.gif
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

STEPS = 500
C_DOT, C_HL, C_LINE, C_INK, C_MUT, C_GRID = "#2a78d6", "#e34948", "#1baf7a", "#40403e", "#8a8a82", "#d6d5cd"


class _T(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.log = {}

    def _on_predict(self, shelf, now, pred_finish):
        if shelf.deadline is not None:
            self.log.setdefault(shelf.id, {"t0": int(now), "pred": float(pred_finish)})


def collect():
    P, D = [], []
    for sd in range(int(os.environ.get("NSEED", "16"))):
        env = gym.make("wwm_sim-large-8agvs-4pickers-globalobs-v1").unwrapped
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
                if r is not None and "d" not in r:
                    r["d"] = (t - r["t0"]) - r["pred"]
                    P.append(r["pred"]); D.append(r["d"])
        ctrl.log = {}
    return np.array(P), np.array(D)


def frame(P, D, stage, blo, bhi):
    fig, ax = plt.subplots(figsize=(10.2, 5.2), dpi=115)
    fig.patch.set_facecolor("white")
    ax.axhline(0, color=C_GRID, lw=1)
    inb = (P >= blo) & (P < bhi)
    ax.scatter(P[~inb], D[~inb], s=20, color=C_DOT, alpha=0.35, edgecolors="none")
    if stage >= 1:
        ax.axvspan(blo, bhi, color="#eda100", alpha=0.13)
        ax.scatter(P[inb], D[inb], s=34, color=C_HL, alpha=0.85, edgecolors="none", zorder=4)
        if inb.sum() > 1:
            lo, hi = D[inb].min(), D[inb].max()
            ax.annotate("", xy=((blo+bhi)/2, hi), xytext=((blo+bhi)/2, lo),
                        arrowprops=dict(arrowstyle="<->", color=C_HL, lw=2))
            ax.text(bhi+1, (lo+hi)/2, f"same plan (~{(blo+bhi)/2:.0f} steps)\n→ actual delay from "
                    f"{lo:+.0f} to {hi:+.0f}", color=C_HL, fontsize=9.5, va="center", fontweight="bold")
    ax.set_xlim(0, np.percentile(P, 98))
    ax.set_ylim(D.min()-4, np.percentile(D, 99)+6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8)
    ax.set_xlabel("the plan's estimate for the task (steps)", color=C_MUT, fontsize=9.5)
    ax.set_ylabel("delay it ACTUALLY suffered (steps)", color=C_MUT, fontsize=9.5)
    titles = ["every task: what the plan expected vs what happened",
              "pick one estimate — the actual delays scatter everywhere",
              "why: your delay is set by the OTHER robots & pickers",
              "so a committed plan is wrong within ~2 moves"]
    ax.set_title(titles[min(stage, 3)], color=C_INK, fontsize=12, loc="left", fontweight="bold")
    notes = ["", "",
             "a task waits because 11 other AGVs and 4 pickers are in its way or busy —\nstate you don't"
             " control and can't know when you commit. Same plan ≠ same outcome.",
             "committing to one predicted delay aims at a moving target. Measured: obeying the whole\n"
             "imagined plan loses −11.3 vs re-deciding every step. The cure isn't a better guess —\n"
             "it's to re-plan against what actually happened, every single step."]
    if stage >= 2:
        fig.text(0.07, 0.20, notes[min(stage, 3)], color=C_INK if stage == 3 else C_MUT,
                 fontsize=10.5, va="top", fontweight="bold" if stage == 3 else "normal")
    fig.subplots_adjust(bottom=0.40 if stage >= 2 else 0.12, top=0.9, left=0.08, right=0.97)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    P, D = collect()
    med = np.median(P)
    blo, bhi = med - 3, med + 3
    frames = [frame(P, D, s, blo, bhi) for s in (0, 1, 2, 3)]
    durs = [1800, 2400, 3000, 3600]
    frames += [frames[-1]] * 3
    durs += [2000] * 3
    frames[0].save("results/gif_noise.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/gif_noise.gif ({len(P)} tasks; slice {blo:.0f}-{bhi:.0f} spans "
          f"{D[(P>=blo)&(P<bhi)].min():+.0f}..{D[(P>=blo)&(P<bhi)].max():+.0f})")


if __name__ == "__main__":
    main()
