"""viz_pace -- progress against the EMA. Two panels:
  LEFT  (offline): delay-forecasting accuracy, MAE, pace vs EMA vs baselines -- pace WINS ~20%.
  RIGHT (online):  banked value, paired delta vs the EMA arm (sqwide) with SE bars -- COMPARABLE.
The story: the pace model forecasts delay much better, but on day-list that does not move value
(demand is fully known, the flat EMA already captures the average). Its reason to exist is the
diurnal signal for the STREAM regime -- comparable-not-worse on day-list is the green light."""
import csv
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_EMA, C_PICK, C_COMB, C_MUT2 = "#eda100", "#2a78d6", "#1baf7a", "#b5b4ab"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"

# offline MAE (from train_pace_daylist.log, 120-seed model, 20% holdout)
OFF = [("predict-0", 17.88, C_MUT2), ("flat const", 13.17, C_MUT2),
       ("EMA", 15.58, C_EMA), ("pace-picker", 12.57, C_PICK), ("pace-comb", 12.39, C_COMB)]


def load(p):
    rows = []
    for f in ("results/pace_rank_a.csv", "results/pace_rank_b.csv"):
        with open(f, encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    return np.array([float(r[f"{p}_on_time_value"]) for r in rows])


def main():
    sq, pp, pc = load("sqwide"), load("pacepick"), load("pacecomb")
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.6, 4.8), dpi=115)
    fig.patch.set_facecolor("white")

    # LEFT: offline MAE (lower = better)
    xs = np.arange(len(OFF))
    axL.bar(xs, [v for _, v, _ in OFF], 0.62, color=[c for _, _, c in OFF],
            edgecolor="white", linewidth=1.5)
    axL.axhline(OFF[2][1], color=C_EMA, ls="--", lw=1.3, zorder=0)
    for x, (_, v, _) in zip(xs, OFF):
        axL.text(x, v + 0.25, f"{v:.1f}", ha="center", color=C_INK, fontsize=9, fontweight="bold")
    axL.set_xticks(xs)
    axL.set_xticklabels([n for n, _, _ in OFF], color=C_INK, fontsize=8.5, rotation=12)
    axL.set_ylim(0, 20)
    for s in ("top", "right"):
        axL.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        axL.spines[s].set_color(C_GRID)
    axL.tick_params(colors=C_MUT, labelsize=8)
    axL.set_ylabel("delay-forecast error (MAE, steps)", color=C_MUT, fontsize=9.5)
    axL.set_title("OFFLINE: pace forecasts delay ~20% better than EMA",
                  color=C_INK, fontsize=10, loc="left")
    axL.text(4, 12.39 - 1.6, "-20%", ha="center", color=C_COMB, fontsize=10, fontweight="bold")

    # RIGHT: online banked value, paired delta vs EMA (sqwide = 0)
    dpp, dpc = pp - sq, pc - sq
    labels = ["pace-picker", "pace-comb"]
    means = [dpp.mean(), dpc.mean()]
    ses = [dpp.std(ddof=1) / np.sqrt(len(dpp)), dpc.std(ddof=1) / np.sqrt(len(dpc))]
    ys = np.arange(len(labels))[::-1]
    axR.axvline(0, color=C_EMA, lw=1.6)
    axR.text(0, 1.62, "EMA (sqwide)", color=C_EMA, fontsize=8.5, ha="center", fontweight="bold")
    axR.errorbar(means, ys, xerr=ses, fmt="o", ms=11, color=C_COMB,
                 ecolor=C_GRID, elinewidth=2.5, capsize=5, zorder=5)
    axR.scatter([means[0]], [ys[0]], s=120, color=C_PICK, zorder=6, edgecolors="white", linewidths=1.5)
    axR.scatter([means[1]], [ys[1]], s=120, color=C_COMB, zorder=6, edgecolors="white", linewidths=1.5)
    for m, se, y in zip(means, ses, ys):
        axR.text(m, y + 0.22, f"{m:+.1f} ± {se:.1f}", ha="center", color=C_INK, fontsize=9,
                 fontweight="bold")
    axR.set_yticks(ys)
    axR.set_yticklabels(labels, color=C_INK, fontsize=9.5)
    axR.set_ylim(-0.6, 1.9)
    axR.set_xlim(-10, 10)
    for s in ("top", "right", "left"):
        axR.spines[s].set_visible(False)
    axR.spines["bottom"].set_color(C_GRID)
    axR.tick_params(colors=C_MUT, labelsize=8)
    axR.set_xlabel("banked value vs EMA ($/day, 30 paired seeds)", color=C_MUT, fontsize=9.5)
    axR.set_title("ONLINE: on day-list, value is unchanged (comparable)",
                  color=C_INK, fontsize=10, loc="left")

    fig.text(0.005, 0.01, "day-list, 30 paired seeds. Offline win doesn't move day-list value "
             "(demand fully known). Diurnal signal targets the STREAM -- next test.",
             color=C_MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig("results/pace_vs_ema.png", facecolor="white")
    print("PNG: results/pace_vs_ema.png")


if __name__ == "__main__":
    main()
