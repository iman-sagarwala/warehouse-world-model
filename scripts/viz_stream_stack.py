"""Stream-regime validation: the sequencer WITH vs WITHOUT the recent fixes, in the 8x4 and 8x8
worlds. Chain per world: champion (cong_l2on) -> +urgency (urg8) -> +sequencer (sqwide, stupid
pickers) -> +value-rate pickers (sqwidepr = full deployed stack). Two panels. Reads stream_84.csv /
stream_88.csv. Output: results/stream_stack.png  (+ prints two-instrument stats).
"""
import csv
import os
import sys
from math import comb

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_CH, C_URG, C_SEQ, C_FULL = "#b5b4ab", "#8a8a82", "#2a78d6", "#1baf7a"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"
ARMS = [("cong_l2on", "champion", C_CH), ("urg8", "+ urgency", C_URG),
        ("sqwide", "+ sequencer\n(stupid pk)", C_SEQ), ("sqwidepr", "+ value-rate\npickers (full)", C_FULL)]


def paired(a, b):
    d = a - b
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else 0.0
    w = int((d > 0).sum()); l = int((d < 0).sum()); m = w + l
    p = sum(comb(m, k) for k in range(min(w, l) + 1)) / 2 ** (m - 1) if m else 1.0
    return d.mean(), se, (d.mean() / se if se else 0.0), w, l, int((d == 0).sum()), min(1.0, p)


def load(path):
    rows = list(csv.DictReader(open(path)))
    return {a[0]: np.array([float(r[f"{a[0]}_on_time_value"]) for r in rows]) for a in ARMS}, len(rows)


def main():
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), dpi=115)
    fig.patch.set_facecolor("white")
    for ax, (path, world) in zip(axes, [("results/stream_84.csv", "8 AGVs : 4 pickers"),
                                        ("results/stream_88.csv", "8 AGVs : 8 pickers (1:1)")]):
        if not os.path.exists(path):
            ax.text(0.5, 0.5, f"{path}\nnot ready", ha="center", va="center", color=C_MUT); continue
        cols, n = load(path)
        base = cols["cong_l2on"]
        print(f"\n=== STREAM {world}  n={n}  champion={base.mean():.1f}/day ===")
        vals = [cols[a[0]].mean() for a in ARMS]
        x = np.arange(len(ARMS))
        ax.bar(x, vals, 0.62, color=[a[2] for a in ARMS], edgecolor="white", lw=1.5, zorder=3)
        for xi, a in zip(x, ARMS):
            arm = cols[a[0]]
            ax.text(xi, arm.mean() + 0.6, f"{arm.mean():.0f}", ha="center", color=C_INK, fontsize=10.5, fontweight="bold")
            m, se, t, w, l, tie, p = paired(arm, base)
            if xi > 0:
                sig = "" if p < 0.05 else " n.s."
                ax.text(xi, base.mean() - 5, f"{m:+.1f}{sig}", ha="center", color=C_MUT, fontsize=8.5, fontweight="bold")
                print(f"  {a[0]:10} {arm.mean():7.1f}  vs champ d {m:+6.2f}  t {t:+5.2f}  W/L/tie {w}/{l}/{tie}  sign p={p:.4f}")
        # incremental full-vs-sequencer (the picker fix on stream)
        m, se, t, w, l, tie, p = paired(cols["sqwidepr"], cols["sqwide"])
        print(f"  value-rate pickers vs stupid (sqwidepr-sqwide): d {m:+.2f}  t {t:+.2f}  W/L/tie {w}/{l}/{tie}  sign p={p:.4f}")
        ax.axhline(base.mean(), color=C_GRID, ls=":", lw=1.3, zorder=1)
        ax.set_ylim(base.mean() - 8, max(vals) + 8)
        ax.set_xticks(x); ax.set_xticklabels([a[1] for a in ARMS], color=C_INK, fontsize=9)
        ax.set_title(f"STREAM — {world}  (n={n})", color=C_INK, fontsize=12, loc="left", fontweight="bold")
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        for s in ("left", "bottom"): ax.spines[s].set_color(C_GRID)
        ax.tick_params(colors=C_MUT, labelsize=8.5)
    axes[0].set_ylabel("on-time value ($/day)", color=C_MUT, fontsize=10)
    fig.suptitle("Do the recent fixes survive on the demand stream?", color=C_INK, fontsize=13.5, fontweight="bold", x=0.09, ha="left")
    fig.text(0.09, 0.02, "Deltas vs champion below each bar. Full stack = sequencer + value-rate pickers. "
             "Compare to day-list: sequencer +16, value-rate +7-8.", color=C_MUT, fontsize=8.5)
    fig.subplots_adjust(bottom=0.16, top=0.88, left=0.07, right=0.98, wspace=0.18)
    fig.savefig("results/stream_stack.png", facecolor="white")
    print("\nPNG: results/stream_stack.png")


if __name__ == "__main__":
    main()
