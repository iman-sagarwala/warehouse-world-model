"""How much of the remaining gap is a PICKER problem? Four points on the same 120 day-list seeds:
  champion  -> sequencer (stupid pickers) -> sequencer + value-rate pickers (now) -> sequencer +
  FREE pickers (picker-optimal ceiling, zero picker wait).
The gap NOW -> CEILING = the picker problem still on the table after the value-rate fix.
Reads stack_*.csv (champion, sqwide, sqwidepr) + free_*.csv (sqwidefree). Output: results/picker_ceiling.png
"""
import csv
import os
import sys

import numpy as np
from math import comb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_CH, C_SEQ, C_NOW, C_CEIL = "#b5b4ab", "#2a78d6", "#1baf7a", "#eda100"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"


def load(prefix, offs):
    rows = []
    for off in offs:
        with open(f"results/{prefix}_{off}.csv") as fh:
            rows += list(csv.DictReader(fh))
    return {int(r["seed"]): r for r in rows}


def paired(a, b):
    d = a - b
    se = d.std(ddof=1) / np.sqrt(len(d))
    w = int((d > 0).sum()); l = int((d < 0).sum()); m = w + l
    p = sum(comb(m, k) for k in range(min(w, l) + 1)) / 2 ** (m - 1) if m else 1.0
    return d.mean(), se, d.mean() / se, w, l, p


def main():
    st = load("stack", (0, 30, 60, 90))
    fr = load("free", (0, 30, 60, 90))
    seeds = sorted(set(st) & set(fr))
    def col(d, k): return np.array([float(d[s][k]) for s in seeds])
    ch = col(st, "cong_l2on_on_time_value")
    sq = col(st, "sqwide_on_time_value")
    pr = col(st, "sqwidepr_on_time_value")
    fp = col(fr, "sqwidefree_on_time_value")
    print(f"n={len(seeds)} seeds")
    for nm, a, b in [("sequencer - champion", sq, ch), ("value-rate - sequencer (mean)", pr, sq),
                     ("CEILING - now (picker problem LEFT)", fp, pr),
                     ("CEILING - sequencer (total picker headroom)", fp, sq)]:
        m, se, t, w, l, p = paired(a, b)
        print(f"  {nm:44} {m:+6.2f}  t {t:+5.2f}  W/L {w}/{l}  sign p={p:.4f}")

    names = ["champion", "sequencer\n(stupid pickers)", "+ value-rate\npickers (now)", "+ FREE pickers\n(ceiling)"]
    vals = [ch.mean(), sq.mean(), pr.mean(), fp.mean()]
    cols = [C_CH, C_SEQ, C_NOW, C_CEIL]
    fig, ax = plt.subplots(figsize=(9.8, 5.6), dpi=115)
    fig.patch.set_facecolor("white")
    x = np.arange(4)
    ax.bar(x, vals, 0.6, color=cols, edgecolor="white", linewidth=1.5, zorder=3)
    for xi, v in zip(x, vals):
        ax.text(xi, v + 0.6, f"{v:.0f}", ha="center", color=C_INK, fontsize=11, fontweight="bold")
    lo = ch.mean() - 6
    ax.set_ylim(lo, fp.mean() + 8)
    # delta brackets
    def bracket(x0, x1, y, txt, color):
        ax.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="<->", color=color, lw=1.6))
        ax.text((x0 + x1) / 2, y + 0.5, txt, ha="center", color=color, fontsize=9.5, fontweight="bold")
    top = fp.mean() + 3
    bracket(0, 1, sq.mean() + 3, f"sequencer  +{sq.mean()-ch.mean():.0f}", C_SEQ)
    bracket(1, 2, pr.mean() + 3, f"value-rate  +{pr.mean()-sq.mean():.1f} mean\n(crater rescue)", C_NOW)
    bracket(2, 3, top, f"picker problem LEFT  +{fp.mean()-pr.mean():.1f}", C_CEIL)
    ax.set_xticks(x)
    ax.set_xticklabels(names, color=C_INK, fontsize=9.5)
    ax.set_ylabel("on-time value ($/day, 120 seeds)", color=C_MUT, fontsize=10)
    ax.set_title("How much of the remaining gap is a picker problem?", color=C_INK, fontsize=12.5,
                 loc="left", fontweight="bold")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(C_GRID)
    ax.tick_params(colors=C_MUT, labelsize=8.5)
    fig.text(0.06, 0.02, "FREE pickers = zero picker wait (upper bound, better than any real 4-picker "
             "assignment). Gap 'now -> ceiling' = the picker value the sequencer + value-rate still leave.",
             color=C_MUT, fontsize=8)
    fig.subplots_adjust(bottom=0.16, top=0.9, left=0.09, right=0.97)
    fig.savefig("results/picker_ceiling.png", facecolor="white")
    print("PNG: results/picker_ceiling.png")


if __name__ == "__main__":
    main()
