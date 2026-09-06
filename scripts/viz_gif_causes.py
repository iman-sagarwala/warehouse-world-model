"""GIF 1 -- the causes of delay, and why each one HAS to be a cause (structural, not a bug).

A task's time budget builds up left to right: the empty-world estimate, then each real-world delay
cause is added with the physical reason it is unavoidable given the warehouse's scarce shared
resources. Numbers are the measured autopsy means (steps/task); picker wait split travel/contention
by the picker-wait decomposition (~80/20). Output: results/gif_causes.gif
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_BASE, C_TRAV, C_CONT, C_TRAF, C_DOCK = "#1baf7a", "#2a78d6", "#eb6834", "#e34948", "#eda100"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"

# (label, width steps, color, why-it-must-happen)
SEGS = [
    ("empty-world estimate", 40.0, C_BASE, "the calculator: drive to the shelf + load + haul to a dock,\nas if the floor were empty and yours alone."),
    ("picker travel  +13", 13.0, C_TRAV, "4 pickers, 8 carriers, a big floor: a picker must WALK to your\nshelf — and you usually arrive first. Structural: fewer helpers\nthan carriers, spread across space."),
    ("picker contention  +3", 3.0, C_CONT, "sometimes all 4 pickers are already busy with other carriers,\nso none can even start toward you yet. Structural: the 4:8 ratio."),
    ("traffic block  +7", 7.0, C_TRAF, "one aisle, two robots, same cell — one must yield and wait.\nStructural: the paths are shared space, not private lanes."),
    ("dock queue  +2", 2.0, C_DOCK, "many deliveries, few docks: a short queue forms at the station.\nStructural: limited delivery points."),
]


def frame(upto):
    fig, ax = plt.subplots(figsize=(10.4, 5.0), dpi=115)
    fig.patch.set_facecolor("white")
    left = 0.0
    for i, (lab, w, c, _why) in enumerate(SEGS):
        on = i <= upto
        ax.barh(0, w, left=left, height=0.5, color=c if on else "#eeeeea",
                edgecolor="white", linewidth=2, zorder=2)
        if on and w > 2:
            ax.text(left + w / 2, 0, lab.split("  ")[0] if i == 0 else lab.split("  ")[-1],
                    ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
        left += w
    total_on = sum(s[1] for s in SEGS[:upto + 1])
    ax.axvline(40.0, color=C_BASE, ls=":", lw=1.4, zorder=1)
    ax.text(40, 0.42, "ideal", color=C_BASE, fontsize=8.5, ha="center", fontweight="bold")
    if upto >= 1:
        ax.annotate("", xy=(total_on, -0.36), xytext=(40, -0.36),
                    arrowprops=dict(arrowstyle="<->", color=C_MUT, lw=1.3))
        ax.text((40 + total_on) / 2, -0.46, f"+{total_on-40:.0f} steps of real-world delay",
                ha="center", va="top", color=C_INK, fontsize=9, fontweight="bold")
    ax.set_xlim(0, sum(s[1] for s in SEGS) + 4)
    ax.set_ylim(-0.75, 0.75)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8)
    ax.set_xlabel("steps a task actually takes", color=C_MUT, fontsize=9.5)
    lab, w, c, why = SEGS[upto]
    ax.set_title(lab.split("  ")[0], color=c if upto else C_BASE, fontsize=13, loc="left", fontweight="bold")
    fig.text(0.06, 0.30, why, color=C_INK, fontsize=11, va="top")
    if upto == len(SEGS) - 1:
        fig.text(0.06, 0.11, "Every extra step is the cost of SHARING scarce things — pickers, aisles, docks.\n"
                 "None is a mistake; all are structural — delay can't be removed, only managed.",
                 color=C_TRAF, fontsize=11, va="top", fontweight="bold")
    fig.subplots_adjust(bottom=0.5, top=0.88, left=0.06, right=0.97)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    frames = [frame(i) for i in range(len(SEGS))]
    durs = [1500, 2400, 2000, 2200, 2000]
    frames += [frames[-1]] * 3
    durs += [1800] * 3
    frames[0].save("results/gif_causes.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/gif_causes.gif ({len(frames)} frames)")


if __name__ == "__main__":
    main()
