"""Best knob value per fleet ratio (AGV x picker), per world, for EVERY swept knob.

Reads results/knobsweep/{regime}_{agv}agv{pk}pk_{KNOB}.csv and draws one PNG per knob:
rows = AGVs (4-9), cols = pickers (4-9), cell = best value (annotated with on-time value).
Output: results/urg_best_{KNOB}.png + a printed table. Re-run anytime; handles partial data.

CAUTION (see docs/NOTES.md 2026-07-30): the per-cell argmax shown here is NOISE-DRIVEN when the
winner's margin is small relative to per-cell SE -- adding grid points DILUTES the true winner. Use
these maps as EXPLORATORY only; the confirmatory statistic is the pooled paired test across cells.
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
AGVS = [4, 5, 6, 7, 8, 9]
PKS = [4, 5, 6, 7, 8, 9]
REGIMES = ["daylist", "stream"]
MIN_SEEDS = 120                     # drop values that have not reached full sampling (stale/partial)

LABELS = {
    "URG_W": "AGV deadline weight URG_W",
    "PK_URG_W": "PICKER deadline weight PK_URG_W",
    "W_SYNC": "AGV sync-up penalty W_SYNC",
    "RATE_ALPHA": "PICKER distance sensitivity RATE_ALPHA",
    "CONG_LAMBDA": "congestion weight in route ranking CONG_LAMBDA",
    "CONG_WEIGHT": "congestion weight in find_path CONG_WEIGHT",
    "SEQ_DEPTH": "sequencer rollout depth SEQ_DEPTH",
}


def load():
    """data[knob][regime][(agv,pk)][value] -> list of on_time_value (split by the KNOB column)."""
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    for f in glob.glob("results/knobsweep/*agv*pk_*.csv"):
        for r in csv.DictReader(open(f)):
            data[r["knob"]][r["regime"]][(int(r["agvs"]), int(r["pickers"]))][float(r["value"])].append(
                float(r["on_time_value"]))
    return data


def draw_knob(knob, byreg):
    # colour scale + completeness target come from the knob's OWN swept values, not a hardcoded range
    allv = sorted({v for reg in byreg.values() for cell in reg.values()
                   for v, runs in cell.items() if len(runs) >= MIN_SEEDS})
    if not allv:
        print(f"  {knob}: no value at n>={MIN_SEEDS} yet, skipping")
        return
    vmin, vmax = min(allv), max(allv)
    if vmin == vmax:
        vmin, vmax = vmin - 0.5, vmax + 0.5
    ncomb = len(allv)

    fig, axes = plt.subplots(1, len(REGIMES), figsize=(6.4 * len(REGIMES), 5.6), dpi=115)
    fig.patch.set_facecolor("white")
    for ax, regime in zip(np.atleast_1d(axes), REGIMES):
        best = np.full((len(AGVS), len(PKS)), np.nan)
        print(f"\n=== {knob} / {regime}: best per ratio ===")
        for i, a in enumerate(AGVS):
            for j, pk in enumerate(PKS):
                cell = byreg[regime].get((a, pk), {})
                if not cell:
                    continue
                means = {v: np.mean(cell[v]) for v in sorted(cell) if len(cell[v]) >= MIN_SEEDS}
                if not means:
                    continue
                bv = max(means, key=means.get)
                best[i, j] = bv
                tag = "" if len(means) >= ncomb else f" (part {len(means)}/{ncomb})"
                print(f"  {a}agv/{pk}pk: best={bv:g}  ontime={means[bv]:.0f}  n={len(cell[bv])}{tag}")
                ax.text(j, i, f"{bv:g}\n{means[bv]:.0f}", ha="center", va="center",
                        fontsize=8, color="#20202a")
        im = ax.imshow(best, cmap="YlGnBu", vmin=vmin, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(PKS))); ax.set_xticklabels(PKS)
        ax.set_yticks(range(len(AGVS))); ax.set_yticklabels(AGVS)
        ax.set_xlabel("pickers"); ax.set_ylabel("AGVs")
        ax.set_title(f"{regime}", fontsize=11, fontweight="bold")
        cb = fig.colorbar(im, ax=ax, fraction=0.046, label=f"best {knob}")
        cb.set_ticks(allv)
    lbl = LABELS.get(knob, knob)
    fig.suptitle(f"Best {lbl} per fleet ratio  (top # = best value, bottom # = on-time $/day)\n"
                 f"EXPLORATORY: per-cell argmax is noise-driven -- see pooled tests",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = f"results/urg_best_{knob}.png"
    fig.savefig(out, facecolor="white"); plt.close(fig)
    print(f"PNG: {out}")


def main():
    data = load()
    if not data:
        print("no data yet"); return
    for knob in sorted(data):
        draw_knob(knob, data[knob])


if __name__ == "__main__":
    main()
