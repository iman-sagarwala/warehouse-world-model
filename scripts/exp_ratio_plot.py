"""exp_ratio_plot -- visualize the AGV:picker sweep. Two panels: picker sweep, AGV sweep.
Each shows the value-loss decomposition (stacked by cause) across configs, with banked value
annotated. Reads results/ratio_<cfg>.csv."""
import csv
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_PICK, C_BLOCK, C_NEVER, C_DOOM = "#2a78d6", "#eb6834", "#4a3aa7", "#8a8a82"
C_BANK, C_INK, C_MUT, C_GRID = "#1baf7a", "#40403e", "#8a8a82", "#d6d5cd"

PICK_SWEEP = ["8x2", "8x4", "8x6", "8x8"]
AGV_SWEEP = ["4x4", "6x4", "8x4", "10x4"]


def load(cfg):
    rows = []
    with open(f"results/ratio_{cfg}.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({k: float(v) for k, v in r.items()})
    m = {k: np.mean([r[k] for r in rows]) for k in rows[0] if k != "seed"}
    return m


def panel(ax, sweep, xlabels, title, xaxis):
    data = [load(c) for c in sweep]
    x = np.arange(len(sweep))
    pick = [d["pick"] for d in data]
    block = [d["block"] for d in data]
    never = [d["never"] for d in data]
    doom = [d["doomed"] for d in data]
    banked = [d["banked"] for d in data]
    pot = data[0]["potential"]
    w = 0.6
    b0 = np.zeros(len(sweep))
    for vals, c, lab in [(pick, C_PICK, "picker wait"), (block, C_BLOCK, "traffic block"),
                         (never, C_NEVER, "never served"), (doom, C_DOOM, "doomed")]:
        ax.bar(x, vals, w, bottom=b0, color=c, edgecolor="white", linewidth=1.5, label=lab)
        b0 = b0 + np.array(vals)
    for xi, (tot, bk) in enumerate(zip(b0, banked)):
        ax.text(xi, tot + pot * 0.012, f"banked\n{bk:.0f}\n{bk/pot*100:.0f}%",
                ha="center", va="bottom", color=C_INK, fontsize=8.5, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, color=C_INK, fontsize=9)
    ax.set_ylim(0, max(b0) * 1.55)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8)
    ax.set_xlabel(xaxis, color=C_MUT, fontsize=9.5)
    ax.set_ylabel("prize value LOST ($/day, avg)", color=C_MUT, fontsize=9.5)
    ax.set_title(title, color=C_INK, fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=C_INK, loc="upper right", ncol=2)


def main():
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.4, 5.0), dpi=115)
    fig.patch.set_facecolor("white")
    panel(axL, PICK_SWEEP, ["2", "4", "6", "8"],
          "Add PICKERS (fixed 8 AGV): loss collapses", "pickers")
    panel(axR, AGV_SWEEP, ["4", "6", "8", "10"],
          "Add AGVs (fixed 4 pickers): loss barely moves", "AGVs")
    # shared y-scale for honest visual comparison
    ymax = max(axL.get_ylim()[1], axR.get_ylim()[1])
    axL.set_ylim(0, ymax)
    axR.set_ylim(0, ymax)
    fig.text(0.005, 0.01, "30 day-list seeds/config, champion+urg8  |  potential value fixed at "
             "431/day (same demand); only robot counts change.", color=C_MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig("results/ratio_sweep.png", facecolor="white")
    print("PNG: results/ratio_sweep.png")
    # console summary
    for name, sweep in (("PICKER", PICK_SWEEP), ("AGV", AGV_SWEEP)):
        print(f"\n{name} sweep:")
        for c in sweep:
            d = load(c)
            print(f"  {c}: banked {d['banked']:.0f} ({d['banked']/d['potential']*100:.0f}%)  "
                  f"picker-wait {d['pick']:.0f}  traffic {d['block']:.0f}  never {d['never']:.0f}")


if __name__ == "__main__":
    main()
