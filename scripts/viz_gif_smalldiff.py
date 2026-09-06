"""GIF 2 -- why delay makes such a SMALL difference to value, calculated from the real tasks.

A delay estimate only changes a decision by flipping a task makeable<->doomed at the deadline cliff.
A task can only flip if its SLACK (deadline - empty-world finish) is within the delay error of zero.
So of all the day's value: most is LOCKED MAKEABLE (slack >> error, banked no matter what) or LOCKED
DOOMED (slack << 0, lost no matter what); only a thin IN-PLAY slice near the cliff can move at all --
and half of it is a coin-toss (truly on-time vs truly late are mixed there). As the delay error grows
the in-play slice grows, but stays small, and half of it cancels. That is why a 20%-better delay
forecast banked ~0 extra. Grounded in real committed tasks. Output: results/gif_smalldiff.gif
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
C_MAKE, C_DOOM, C_PLAY = "#1baf7a", "#b5b4ab", "#eda100"
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
                if r is not None and "true" not in r:
                    r["true"] = float(t - r["t0"])
            done = (t >= STEPS)
        allt += [r for r in ctrl.log.values() if "true" in r]
        ctrl.log = {}
    return allt


def frame(tasks, err):
    slack = np.array([r["dl_rel"] - r["pred"] for r in tasks])
    val = np.array([r["value"] for r in tasks])
    ont = np.array([r["true"] <= r["dl_rel"] for r in tasks])
    tot = val.sum()
    locked_make = val[slack > err].sum()
    locked_doom = val[slack < -err].sum()
    inplay = val[np.abs(slack) <= err]
    inplay_on = val[(np.abs(slack) <= err) & ont].sum()
    inplay_late = val[(np.abs(slack) <= err) & ~ont].sum()
    ip = inplay.sum()
    net = abs(inplay_on - inplay_late)               # the most a perfect vs worst call could net

    fig, ax = plt.subplots(figsize=(10.2, 4.8), dpi=115)
    fig.patch.set_facecolor("white")
    left = 0.0
    for v, c, lab in [(locked_make, C_MAKE, "locked makeable"), (ip, C_PLAY, "in play"),
                      (locked_doom, C_DOOM, "locked doomed")]:
        ax.barh(0, v, left=left, height=0.5, color=c, edgecolor="white", linewidth=2)
        if v / tot > 0.05:
            ax.text(left + v / 2, 0, f"{v/tot*100:.0f}%", ha="center", va="center", color="white",
                    fontsize=11, fontweight="bold")
        left += v
    ax.set_xlim(0, tot)
    ax.set_ylim(-0.9, 0.7)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8)
    ax.set_xlabel("the day's total prize value", color=C_MUT, fontsize=9.5)
    ax.set_title(f"a delay error of ±{err:.0f} steps can only touch the amber slice",
                 color=C_INK, fontsize=12, loc="left", fontweight="bold")
    fig.text(0.06, 0.30, f"of the whole day's value, {ip/tot*100:.0f}% is even IN PLAY at a ±{err:.0f}-step "
             f"delay error —\nthe rest is banked or lost no matter what the delay estimate says.",
             color=C_INK, fontsize=11, va="top")
    fig.text(0.06, 0.15, f"and inside that slice, on-time ({inplay_on/tot*100:.0f}%) and late "
             f"({inplay_late/tot*100:.0f}%) are mixed — so even a perfect delay\ncall nets at most "
             f"{net/tot*100:.0f}%. A sharper-but-imperfect estimate reshuffles it to ~0.",
             color=C_MUT, fontsize=11, va="top")
    fig.subplots_adjust(bottom=0.46, top=0.86, left=0.06, right=0.97)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    tasks = collect()
    errs = list(range(2, 24, 2))
    frames = [frame(tasks, e) for e in errs]
    frames += [frames[-1]] * 5
    durs = [500] * len(errs) + [700] * 5
    frames[0].save("results/gif_smalldiff.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/gif_smalldiff.gif ({len(tasks)} tasks, {len(frames)} frames)")


if __name__ == "__main__":
    main()
