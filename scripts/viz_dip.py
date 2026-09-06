"""Where each lever dips, and how they rescue each other. The stacking "+1.4 null" was a misleading
mean: value-rate pickers barely help where the sequencer is fine, but RESCUE its crater days.
x = sequencer's result vs champion (left = its bad days); y = how much adding pickers rescues that
seed. Strong up-left = pickers fix exactly where the sequencer fails. results/dip_rescue.png"""
import csv
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_DOT, C_HL, C_INK, C_MUT, C_GRID = "#2a78d6", "#e34948", "#40403e", "#8a8a82", "#d6d5cd"


def load(prefix):
    rows = []
    for off in (0, 30, 60, 90):
        with open(f"results/{prefix}_{off}.csv") as fh:
            rows += list(csv.DictReader(fh))
    return {int(r["seed"]): r for r in rows}


def main():
    vs, st = load("vs"), load("stack")
    seeds = sorted(vs)
    ch = np.array([float(vs[s]["cong_l2on_on_time_value"]) for s in seeds])
    sq = np.array([float(vs[s]["sqwide_on_time_value"]) for s in seeds])
    spr = np.array([float(st[s]["sqwidepr_on_time_value"]) for s in seeds])
    dsq = sq - ch                 # sequencer vs champion (x)
    resc = spr - sq               # picker rescue on the sequencer (y)

    fig, ax = plt.subplots(figsize=(9.6, 5.6), dpi=115)
    fig.patch.set_facecolor("white")
    ax.axhline(0, color=C_GRID, lw=1)
    ax.axvline(0, color=C_GRID, lw=1)
    worst = set(np.argsort(dsq)[:10])
    for i, s in enumerate(seeds):
        hl = i in worst
        ax.scatter(dsq[i], resc[i], s=70 if hl else 34, color=C_HL if hl else C_DOT,
                   alpha=0.9 if hl else 0.5, edgecolors="white" if hl else "none",
                   linewidths=1.3, zorder=4 if hl else 2)
    # trend
    b, a = np.polyfit(dsq, resc, 1)
    xs = np.array([dsq.min(), dsq.max()])
    ax.plot(xs, a + b * xs, color=C_INK, lw=2, ls="--", zorder=3)
    r = np.corrcoef(dsq, resc)[0, 1]
    ax.text(dsq.min() + 3, resc.max() - 4, f"corr = {r:+.2f}\nslope {b:+.2f}",
            color=C_INK, fontsize=10, fontweight="bold", va="top")
    ax.annotate("sequencer's CRATER days →\npickers rescue them (+29 avg)",
                (dsq[np.argmin(dsq)], resc[np.argmin(dsq)]),
                (dsq.min() + 6, resc.max() - 26), color=C_HL, fontsize=10, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=C_HL, lw=1.5))
    ax.text(dsq.max() - 2, 6, "sequencer's good days:\npickers ~flat (redundant here)",
            color=C_MUT, fontsize=9.5, ha="right", va="bottom", fontweight="bold")
    ax.set_xlabel("sequencer vs champion  (← its worst days)", color=C_MUT, fontsize=10)
    ax.set_ylabel("value rescued by adding pickers (seq+pk − seq)", color=C_MUT, fontsize=10)
    ax.set_title("The picker fix isn't redundant — it's crater insurance for the sequencer",
                 color=C_INK, fontsize=12, loc="left", fontweight="bold")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8.5)
    fig.text(0.06, 0.02, "120 day-list seeds. Red = sequencer's 10 worst days. The +1.4 stacking mean "
             "hides this: ~0 on good days, +29 rescue on crater days -> variance cut, not mean lift.",
             color=C_MUT, fontsize=8)
    fig.subplots_adjust(bottom=0.13, top=0.9, left=0.09, right=0.97)
    fig.savefig("results/dip_rescue.png", facecolor="white")
    print(f"PNG: results/dip_rescue.png  (corr {r:+.2f}, slope {b:+.2f})")
    print(f"worst-10 rescue {resc[list(worst)].mean():+.1f}  vs all-seed {resc.mean():+.1f}")


if __name__ == "__main__":
    main()
