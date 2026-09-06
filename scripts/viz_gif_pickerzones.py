"""GIF -- why value-rate + marginal assignment makes pickers SPREAD to different areas by themselves.

The floor has value hotspots (where valuable orders cluster). Pickers are assigned one at a time, each
choosing the area with the best value-rate (high value, short walk). The catch: once a picker claims an
area, the next picker treats it as already served, so it drops to the next-best UNCLAIMED area. No zones
are hard-coded -- coverage emerges: pickers fan out to distinct hot areas, and a single area gets two
pickers only if it's hot enough to still win after the first is spent. Output: results/picker_zones.gif
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_INK, C_MUT, C_GRID, C_PK, C_CLAIM = "#40403e", "#8a8a82", "#d6d5cd", "#2a78d6", "#1baf7a"

# value hotspots: (x, y, weight) on a 100x70 floor
HOTSPOTS = [(72, 48, 1.0), (24, 20, 0.85), (80, 16, 0.7), (30, 55, 0.6), (52, 34, 0.45)]
PICKERS = [(50, 4), (10, 4), (90, 4), (50, 66)]     # picker start positions (edges)
W, H = 100, 70


def value_field():
    yy, xx = np.mgrid[0:H, 0:W]
    f = np.zeros((H, W))
    for (hx, hy, w) in HOTSPOTS:
        f += w * np.exp(-((xx - hx) ** 2 + (yy - hy) ** 2) / (2 * 15.0 ** 2))
    return f


def assign():
    """Greedy value-rate: each picker takes the best UNCLAIMED hotspot (value / distance)."""
    claimed, order = [], []
    for (px, py) in PICKERS:
        best, bestscore = None, -1
        for i, (hx, hy, w) in enumerate(HOTSPOTS):
            if i in claimed:
                continue
            dist = np.hypot(hx - px, hy - py)
            rate = w / max(8.0, dist)                 # value-rate: value per distance
            if rate > bestscore:
                best, bestscore = i, rate
        if best is not None:
            claimed.append(best)
            order.append(((px, py), best))
    return order


def frame(field, order, upto):
    fig, ax = plt.subplots(figsize=(9.6, 5.6), dpi=115)
    fig.patch.set_facecolor("white")
    ax.imshow(field, origin="lower", cmap="YlOrBr", alpha=0.85, extent=[0, W, 0, H], aspect="auto")
    # claimed hotspots (already served)
    for k in range(upto):
        (px, py), hi = order[k]
        hx, hy, _ = HOTSPOTS[hi]
        ax.plot([px, hx], [py, hy], color=C_CLAIM, lw=2.4, zorder=3)
        ax.scatter([hx], [hy], s=430, facecolors="none", edgecolors=C_CLAIM, linewidths=3, zorder=4)
        ax.scatter([px], [py], s=90, color=C_CLAIM, zorder=5, edgecolors="white", linewidths=1.5)
        ax.text(hx, hy - 5, "served", color=C_CLAIM, fontsize=8.5, ha="center", fontweight="bold", zorder=6)
    # the picker being placed now
    if upto < len(order):
        (px, py), hi = order[upto]
        hx, hy, _ = HOTSPOTS[hi]
        # show it evaluating the remaining hotspots (faint spokes), then its pick (bold)
        claimed = {order[k][1] for k in range(upto)}
        for i, (ox, oy, _w) in enumerate(HOTSPOTS):
            if i not in claimed and i != hi:
                ax.plot([px, ox], [py, oy], color=C_MUT, lw=0.9, ls=":", alpha=0.6, zorder=2)
        ax.plot([px, hx], [py, hy], color=C_PK, lw=3, zorder=3)
        ax.scatter([px], [py], s=150, color=C_PK, zorder=6, edgecolors="white", linewidths=2)
        ax.text(px, py + 3.5, f"picker {upto+1}", color=C_PK, fontsize=9, ha="center", fontweight="bold", zorder=6)
        ax.set_title(f"picker {upto+1}: best UNCLAIMED area  (area {order[upto][1]+1} — "
                     f"others already served)", color=C_INK, fontsize=11.5, loc="left", fontweight="bold")
    else:
        ax.set_title("all pickers fanned out — coverage, no zones hard-coded",
                     color=C_INK, fontsize=12.5, loc="left", fontweight="bold")
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_color(C_GRID)
    fig.text(0.06, 0.02, "amber = where valuable orders cluster (value density). Each picker takes the "
             "best value-rate area that isn't already served → they spread automatically.",
             color=C_MUT, fontsize=8.5)
    fig.subplots_adjust(bottom=0.09, top=0.9, left=0.04, right=0.98)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    field = value_field()
    order = assign()
    frames = [frame(field, order, k) for k in range(len(order) + 1)]
    durs = [2600] * len(order) + [3200]
    frames += [frames[-1]] * 2
    durs += [2000] * 2
    frames[0].save("results/picker_zones.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/picker_zones.gif ({len(frames)} frames); assignment order "
          f"{[o[1]+1 for o in order]}")


if __name__ == "__main__":
    main()
