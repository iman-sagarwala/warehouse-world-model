"""Live bar-graph view of the M1 knob sweep. Globs results/knobsweep/*.csv (long format) and, for each
knob (URG_W, RATE_ALPHA), draws a grid of bar charts: rows = regime, cols = fleet size, x = knob value,
y = mean on-time value. Best bar per panel highlighted green. Re-run anytime to refresh as data lands.
Output: results/knob_URG_W.png, results/knob_RATE_ALPHA.png + a printed best-knob table.
"""
import csv
import glob
import os
import sys
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_BAR, C_BEST, C_INK, C_MUT, C_GRID = "#8fb2d9", "#1baf7a", "#40403e", "#8a8a82", "#d6d5cd"


def load():
    rows = []
    for f in glob.glob("results/knobsweep/*.csv"):
        with open(f) as fh:
            rows += list(csv.DictReader(fh))
    return rows


def main():
    rows = load()
    if not rows:
        print("no data yet"); return
    # index: [knob][regime][(agv,pk)][value] -> list of on_time_value
    D = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    for r in rows:
        D[r["knob"]][r["regime"]][(int(r["agvs"]), int(r["pickers"]))][float(r["value"])].append(
            float(r["on_time_value"]))

    for knob in sorted(D):
        regimes = sorted(D[knob])
        fleets = sorted({fl for rg in D[knob] for fl in D[knob][rg]}, key=lambda x: x[0])
        nr, nc = len(regimes), max(1, len(fleets))
        fig, axes = plt.subplots(nr, nc, figsize=(3.1 * nc + 1, 3.0 * nr + 0.6), dpi=115, squeeze=False)
        fig.patch.set_facecolor("white")
        print(f"\n=== {knob} — best value per cell ===")
        for i, rg in enumerate(regimes):
            for j, fl in enumerate(fleets):
                ax = axes[i][j]
                cell = D[knob][rg].get(fl, {})
                if not cell:
                    ax.axis("off"); continue
                vals = sorted(cell)
                means = [np.mean(cell[v]) for v in vals]
                ns = [len(cell[v]) for v in vals]
                best = int(np.argmax(means))
                cols = [C_BEST if k == best else C_BAR for k in range(len(vals))]
                x = np.arange(len(vals))
                ax.bar(x, means, 0.7, color=cols, edgecolor="white", zorder=3)
                lo, hi = min(means), max(means)
                pad = max(1.0, (hi - lo) * 0.25)
                ax.set_ylim(lo - pad, hi + pad * 1.6)
                for k, mv in enumerate(means):
                    ax.text(k, mv + pad * 0.12, f"{mv:.0f}", ha="center", fontsize=7.5,
                            color=C_INK, fontweight="bold" if k == best else "normal")
                ax.set_xticks(x); ax.set_xticklabels([f"{v:g}" for v in vals], fontsize=8)
                ax.set_title(f"{rg}  {fl[0]}×{fl[1]}  (best {knob}={vals[best]:g}, n={ns[best]})",
                             fontsize=8.5, color=C_INK)
                if j == 0:
                    ax.set_ylabel("on-time value $/day", fontsize=8, color=C_MUT)
                for sp in ("top", "right"):
                    ax.spines[sp].set_visible(False)
                for sp in ("left", "bottom"):
                    ax.spines[sp].set_color(C_GRID)
                ax.tick_params(colors=C_MUT, labelsize=7.5)
                print(f"  {rg:8} {fl[0]:2}x{fl[1]:<2}  best {knob}={vals[best]:g}  "
                      f"({means[best]:.1f}, +{means[best]-means[vals.index(8.0)] if 8.0 in vals else means[best]-means[0]:.1f} vs default)")
        label = {"URG_W": "AGV deadline-urgency weight URG_W (0 = value only)",
                 "PK_URG_W": "PICKER deadline-urgency weight PK_URG_W (0 = none)",
                 "RATE_ALPHA": "picker distance exponent RATE_ALPHA (0 = value-only picker)"}.get(
                     knob, f"{knob} sweep")
        fig.suptitle(f"M1 knob sweep — {label}", fontsize=12, fontweight="bold", color=C_INK, x=0.02, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        out = f"results/knob_{knob}.png"
        fig.savefig(out, facecolor="white")
        print(f"  PNG: {out}")


if __name__ == "__main__":
    main()
