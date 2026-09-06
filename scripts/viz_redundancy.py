"""viz_redundancy -- what "redundant on day-list, informative on stream" means (GIF).

Redundancy = handing the planner information it can already DERIVE from what it has.

Both panels use the SAME real orders (demand model, one seed). Each order has a deadline and an
arrival time. The "deadline clustering" curve (how many deadlines fall near each moment) is IDENTICAL
in both -- the only difference is what the planner can SEE:

  DAY-LIST (top): every order is visible at t=0. The planner already holds all deadlines, so it can
                  compute the clustering itself. A clustering feature is DERIVABLE -> REDUNDANT.
  STREAM  (bottom): an order is visible only once it arrives; the future is fog. The clustering ahead
                  is NOT derivable from what's visible, so a FORECAST of it is genuine new info.

A "now" cursor sweeps the day. Day-list stays fully lit ahead of now; stream reveals deadlines only
as they arrive and shows a forecast (dashed) as the only signal inside the fog.
Output: results/redundancy.gif
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gymnasium as gym
import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEED = int(os.environ.get("SEED", "4"))

C_KNOWN, C_FOG, C_FORE = "#2a78d6", "#1baf7a", "#eb6834"
C_INK, C_MUT, C_GRID, C_HIDDEN = "#40403e", "#8a8a82", "#d6d5cd", "#e8e8e3"


def get_orders():
    env = gym.make(ENV).unwrapped
    env.reset(seed=SEED)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=SEED)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    dl, arr = [], []
    for _sid, lst in env.demand_model.pending.items():
        for o in lst:
            if o.deadline is not None:
                dl.append(float(o.deadline))
                arr.append(float(o.t_arrive))
    dm = env.demand_model
    # forecast curve = the demand model's expected deadline density (diurnal rate shifted by mean slack)
    ts = np.arange(0, STEPS)
    rate = np.array([dm.rate * dm._diurnal(t) for t in ts])
    slack = max(1.0, float(np.mean(np.array(dl) - np.array(arr))))
    fore = np.zeros(STEPS)                       # push arrival-rate forward by mean slack -> deadline density
    for t in ts:
        td = int(t + slack)
        if td < STEPS:
            fore[td] += rate[t]
    # smooth
    k = np.ones(25) / 25.0
    fore = np.convolve(fore, k, mode="same")
    return np.array(dl), np.array(arr), fore


def density(deadlines, bins):
    h, _ = np.histogram(deadlines, bins=bins, range=(0, STEPS))
    return np.convolve(h, np.ones(3) / 3.0, mode="same")


def draw(now, dl, arr, fore, bins, xcent, dl_full, dmax):
    fig, (axA, axB) = plt.subplots(2, 1, figsize=(9.6, 5.6), dpi=115, sharex=True)
    fig.patch.set_facecolor("white")
    fmax = max(dmax, fore.max() * (len(dl) / max(1, fore.sum())) * bins) if fore.max() > 0 else dmax

    # --- TOP: DAY-LIST -- all deadlines visible always ---
    axA.fill_between(xcent, dl_full, color=C_KNOWN, alpha=0.18, zorder=1)
    axA.plot(xcent, dl_full, color=C_KNOWN, lw=2, zorder=2)
    axA.scatter(dl, np.full(len(dl), -dmax * 0.13), marker="|", s=90, color=C_KNOWN, alpha=0.5, zorder=1)
    axA.axvline(now, color=C_INK, lw=1.6, zorder=5)
    axA.text(0.015, 0.86, "DAY-LIST: every deadline visible from t=0", transform=axA.transAxes,
             color=C_INK, fontsize=11, fontweight="bold")
    axA.text(now + 6, dmax * 0.9, "planner already sees ahead →\nclustering is DERIVABLE = REDUNDANT",
             color=C_KNOWN, fontsize=9.5, va="top", fontweight="bold")
    axA.set_ylim(-dmax * 0.22, dmax * 1.15)
    axA.set_ylabel("deadline density", color=C_MUT, fontsize=9)

    # --- BOTTOM: STREAM -- only arrived deadlines visible; future = fog + forecast ---
    revealed = dl[arr <= now]
    dl_rev = density(revealed, bins) if len(revealed) else np.zeros(len(xcent))
    axB.axvspan(now, STEPS, color=C_HIDDEN, zorder=0)                 # fog over the future
    axB.fill_between(xcent, dl_rev, color=C_FOG, alpha=0.20, zorder=1)
    axB.plot(xcent, dl_rev, color=C_FOG, lw=2, zorder=2, label="visible (arrived)")
    fore_s = fore * (dmax / max(fore.max(), 1e-9)) * 0.92            # scale forecast to same axis
    axB.plot(xcent, np.interp(xcent, np.arange(STEPS), fore_s), color=C_FORE, lw=2.2, ls="--",
             zorder=3, label="forecast (from day-curve)")
    axB.scatter(revealed, np.full(len(revealed), -dmax * 0.13), marker="|", s=90, color=C_FOG,
                alpha=0.6, zorder=1)
    axB.axvline(now, color=C_INK, lw=1.6, zorder=5)
    axB.text(0.015, 0.86, "STREAM: future deadlines hidden until they arrive", transform=axB.transAxes,
             color=C_INK, fontsize=11, fontweight="bold")
    axB.text(now + 6, dmax * 0.92, "the fog →\nforecast is the ONLY signal = INFORMATIVE",
             color=C_FORE, fontsize=9.5, va="top", fontweight="bold")
    axB.text(now - 6, dmax * 0.92, "seen", color=C_FOG, fontsize=9.5, va="top", ha="right",
             fontweight="bold")
    axB.set_ylim(-dmax * 0.22, dmax * 1.15)
    axB.set_ylabel("deadline density", color=C_MUT, fontsize=9)
    axB.set_xlabel("time of day (steps)", color=C_MUT, fontsize=9)
    axB.legend(loc="upper right", frameon=False, fontsize=8.5, labelcolor=C_INK)

    for ax in (axA, axB):
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(C_GRID)
        ax.tick_params(colors=C_MUT, labelsize=8)
        ax.set_yticks([])
        ax.set_xlim(0, STEPS)
    fig.suptitle("Redundancy: same deadlines, different visibility  —  a feature only helps if you "
                 "can't already derive it", color=C_INK, fontsize=11.5, x=0.01, ha="left")
    fig.text(0.01, 0.005, f"real orders, seed {SEED}. Identical clustering in both panels; only what "
             "the planner can SEE differs.", color=C_MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    dl, arr, fore = get_orders()
    bins = 50
    xcent = (np.arange(bins) + 0.5) * (STEPS / bins)
    dl_full = density(dl, bins)
    dmax = dl_full.max() * 1.05
    nows = list(range(20, STEPS + 1, 12))
    frames = [draw(n, dl, arr, fore, bins, xcent, dl_full, dmax) for n in nows]
    frames += [frames[-1]] * 8
    durs = [200] * (len(frames) - 8) + [500] * 8
    frames[0].save("results/redundancy.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/redundancy.gif ({len(frames)} frames, {len(dl)} orders seed {SEED})")


if __name__ == "__main__":
    main()
