"""Regenerate the paper's figure set from current (post-realism-audit) data.

Every figure here is measured on the corrected world. The roadmap's original figure list
(stream_stack / picker_ceiling / oracle_gap) was produced in July 2026, BEFORE the realism
audit, on a simulator ~3x too productive -- those PNGs must not be cited and are not
regenerated here.

    python scripts/make_paper_figures.py [fig1 fig2 ...]     (default: all)

Outputs results/fig_*.png at 200 dpi.

Palette: the validated categorical slots 1-4 (blue / orange / aqua / yellow), adjacent-pair
CVD dE 9.1, normal-vision dE 22.9. Two slots sit under 3:1 on a light surface, so every bar
carries a visible direct label (the relief rule).
"""
import csv
import io
import json
import os
import sys
import collections
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results")

# --- palette (validated; see module docstring) --------------------------------
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GOOD, BAD = "#008300", "#e34948"
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#8a8a86"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.size": 9, "axes.titlesize": 10.5, "axes.labelsize": 9,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.titlecolor": INK,
    "grid.color": GRID, "grid.linewidth": 0.8,
    "legend.frameon": False, "legend.fontsize": 8,
})


def recess(ax, xgrid=False):
    ax.grid(axis="x" if xgrid else "y", alpha=0.9, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)


def save(fig, name):
    p = os.path.join(OUT, name)
    fig.savefig(p, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("saved", p)


def bench_means(path):
    d = collections.defaultdict(list)
    for x in csv.DictReader(io.open(path, encoding="utf-8")):
        d[(x["arm"], x["regime"])].append(float(x["onv"]))
    return {k: sum(v) / len(v) for k, v in d.items()}, d


# ------------------------------------------------------------------ figure 1
def fig_benchmark():
    """Head-to-head against the simulator's own dispatcher, both regimes, +/- disturbances."""
    # prefer the 2026-09-06 re-measurement on current code; fall back to the older tables
    def pick(*names):
        """First complete table wins: a re-measurement still in flight is not used."""
        for n in names:
            p_ = os.path.join(OUT, n)
            if not os.path.exists(p_):
                continue
            m, raw = bench_means(p_)
            want = {(a_, r_) for a_ in ("fifo", "rush", "champ", "mpc")
                    for r_ in ("wave", "stream")}
            if want <= set(raw) and min(len(v) for v in raw.values()) >= 144:
                return p_
        raise IOError(names[0])
    clean, _ = bench_means(pick("m5_bench_current.csv", "m5_bench.csv"))
    dist, _ = bench_means(pick("m5_bench_disturb_current.csv", "m5_bench_disturb.csv"))
    arms = [("fifo", "FIFO (built-in)", C1), ("rush", "Rush", C2),
            ("champ", "champion", C3), ("mpc", "champion + tuner", C4)]

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9), sharey=True)
    for ax, (src, title) in zip(axes, [(clean, "Clean floor"), (dist, "With disturbances")]):
        for gi, regime in enumerate(("wave", "stream")):
            for ai, (key, _lbl, col) in enumerate(arms):
                x = gi * 5 + ai
                v = src[(key, regime)]
                ax.bar(x, v, width=0.86, color=col, zorder=3,
                       edgecolor=SURFACE, linewidth=1.4)          # 2px surface gap
                ax.text(x, v + 12, "%.0f" % v, ha="center", va="bottom",
                        fontsize=7.6, color=INK2)                  # relief: direct labels
        # the headline margin: the SHIPPED system (rules + tuner) against the vendored dispatcher.
        # Bracketing `champ` here would contradict the text, which leads with the shipped arm.
        for gi, regime in enumerate(("wave", "stream")):
            f, c = src[("fifo", regime)], src[("mpc", regime)]
            top = max(src[(k, regime)] for k, _l, _c in arms) + 78
            x0, x1 = gi * 5, gi * 5 + 3
            ax.plot([x0, x0, x1, x1], [top - 16, top, top, top - 16],
                    color=INK3, lw=1.0, zorder=5, solid_joinstyle="miter")
            ax.text((x0 + x1) / 2, top + 12, "+%.1f%%" % (100 * (c - f) / f),
                    ha="center", fontsize=8.6, color=INK, fontweight="bold")
        ax.set_xticks([1.5, 6.5])
        ax.set_xticklabels(["wave days", "live-stream days"])
        ax.set_title(title)
        ax.set_ylim(0, 1010)
        recess(ax)
    axes[0].set_ylabel("on-time value per day")
    axes[0].legend(handles=[Patch(facecolor=c, label=l) for _k, l, c in arms],
                   loc="upper center", bbox_to_anchor=(1.03, -0.12), ncol=4)
    fig.suptitle("144 paired days per cell; margins are for the shipped system (rules + self-tuner); "
                 "the baselines run with free energy", y=1.03, fontsize=8.6, color=INK2)
    save(fig, "fig_benchmark.png")


# ------------------------------------------------------------------ figure 2
def fig_anticipation():
    """The anticipation null: damage grows with horizon, and all six channels are flat-to-negative."""
    # left: foresight-window sweep (results/foresight_window.csv, NOTES 2026-08-01)
    win = [(0, 0.0), (10, 0.0), (25, -1.65), (50, -3.91), (100, -5.32), (200, -11.23)]
    # right: the six channels (NOTES 2026-08-01 .. 2026-08-25); value is % of a day
    chan = [("Which task to take\n(perfect order knowledge)", -3.4, "−3.4%  t=−6.0"),
            ("Drifting hotspots\n(Instacart-calibrated)", -0.25, "flat  z=−0.45"),
            ("Where to park idle robots", -0.0, "2.4% ceiling — cut before building"),
            ("Which cells will get dirty", -1.2, "−0.3 to −5.7 in every form"),
            ("Execution-layer priority", -0.6, "null"),
            ("When to charge\n(true forecast)", 4.0, "+4.0% t=1.3 — but see below")]

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(12.4, 4.1),
                                   gridspec_kw={"width_ratios": [1, 1.5], "wspace": 0.62})

    xs = [w for w, _ in win]
    ys = [v for _, v in win]
    axA.axhline(0, color=INK3, lw=1.0, zorder=2)
    axA.plot(xs, ys, "o-", color=C1, lw=2, ms=6, zorder=4)
    for x, y in win[2:]:
        off = (-4, -14) if x == 200 else (7, 5)
        ha = "right" if x == 200 else "left"
        axA.annotate("%.2f" % y, (x, y), textcoords="offset points", xytext=off,
                     ha=ha, fontsize=7.6, color=INK2)
    axA.set_ylim(-13.2, 1.4)
    axA.set_xlabel("steps of perfect order knowledge given to the planner")
    axA.set_ylabel("on-time value vs no foresight")
    axA.set_title("More of the future is monotonically worse")
    axA.set_xticks(xs)
    axA.set_xticklabels(["0", "10", "25", "50", "100", "whole\nday"])
    recess(axA)

    lbl = [c[0] for c in chan][::-1]
    val = [c[1] for c in chan][::-1]
    note = [c[2] for c in chan][::-1]
    cols = [GOOD if v > 0 else BAD for v in val]
    axB.barh(range(len(val)), val, color=cols, height=0.62, zorder=3,
             edgecolor=SURFACE, linewidth=1.4)
    axB.axvline(0, color=INK3, lw=1.0, zorder=4)
    for i, (v, nt) in enumerate(zip(val, note)):
        right = v > 0.05                      # only the one positive bar labels to its right
        axB.text(v + (0.35 if right else -0.35), i, nt, va="center",
                 ha="left" if right else "right", fontsize=7.4, color=INK2)
    axB.set_yticks(range(len(lbl)))
    axB.set_yticklabels(lbl, fontsize=8)
    axB.set_xlim(-11.5, 11.5)
    axB.set_xlabel("effect on on-time value (%)")
    axB.set_title("Six channels fed the true future; none pays")
    recess(axB, xgrid=True)
    axB.text(0.5, -0.30, "The charging channel is positive but NOT from information: a scrambled "
                         "forecast scores +6.8% against\nthe true forecast's +4.0%, and a constant "
                         "threshold at the same mean is worth +0.3%. See §5.25.",
             transform=axB.transAxes, ha="center", va="top", fontsize=7.4, color=INK2)
    save(fig, "fig_anticipation.png")


# ------------------------------------------------------------------ figure 3
def fig_sensing():
    """The prediction inversion: the worse the sensors, the more the world model IS the sensor."""
    # NOTES 2026-08-23; blind baseline 800.6, oracle 855.8
    blind, oracle = 800.6, 855.8
    rows = [(1, 807.1, 827.4), (2, 819.0, 839.3), (3, 826.5, 848.1), (5, 837.3, 850.1)]
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    for i, (r, eyes, full) in enumerate(rows):
        e, p = eyes - blind, full - eyes
        ax.bar(i, e, width=0.62, color=C1, zorder=3, edgecolor=SURFACE, linewidth=1.4)
        ax.bar(i, p, bottom=e, width=0.62, color=C3, zorder=3, edgecolor=SURFACE, linewidth=1.4)
        tot = e + p
        ax.text(i, e / 2, "%.0f%%" % (100 * e / tot), ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")
        ax.text(i, e + p / 2, "%.0f%%" % (100 * p / tot), ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")
        ax.text(i, tot + 1.4, "+%.1f" % tot, ha="center", va="bottom", fontsize=7.8, color=INK2)
    ax.axhline(oracle - blind, ls="--", color=INK3, lw=1.1, zorder=2)
    ax.text(3.42, oracle - blind + 1.0, "mind-reading oracle (+%.1f)" % (oracle - blind),
            ha="right", fontsize=7.8, color=INK2)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(["1 cell\n(camera-less)", "2 cells", "3 cells\n(modest camera)",
                        "5 cells\n(shipped)"])
    ax.set_xlabel("how far a robot can see")
    ax.set_ylabel("on-time value above a blind fleet")
    ax.set_title("At honest sensor ranges, prediction carries the sensing value")
    ax.legend(handles=[Patch(facecolor=C1, label="eyes — dodge what is visible now"),
                       Patch(facecolor=C3, label="prediction — remember it until seen clean")],
              loc="upper left")
    ax.set_ylim(0, 70)
    recess(ax)
    save(fig, "fig_sensing.png")


# ------------------------------------------------------------------ figure 4
def fig_ablation():
    """The pre-registered keep/cut ledger: 10 shipped, 21 cut, one bar each."""
    SAFE = "0 stranded / 0 frozen in 144 days"
    ENAB = "enabling infrastructure — no value claim"
    keep = [("Board rollout", 7.2, None), ("Belief-map routing", 6.2, None),
            ("Reset update rule", 3.5, None), ("Sight / prediction split", 2.8, None),
            ("Battery management", 0.0, SAFE), ("Charger bays", 0.0, ENAB),
            ("Janitor", 0.0, "honest sensing reaches ~100% of oracle"),
            ("MPC self-tuner", 1.0, None),
            ("Value-rate picker seq.", 0.0, "folded into the rollout ablation"),
            ("Deadlock / flow flags", 0.0, "eliminated 100% of permanent deadlock")]
    cut = [("Perfect order knowledge", -3.4, None), ("Foresight, whole day", -11.2, None),
           ("Drift anticipation", -0.2, None), ("Idle pre-positioning", -2.4, None),
           ("Anticipation estimators", -1.0, None), ("Scout detours", -5.7, None),
           ("Hot-zone slow forgetting", -3.2, None), ("Neighbour suspicion", -0.4, None),
           ("Sight-gated spread", 0.6, None), ("Janitor pre-positioning", -0.3, None),
           ("Longer map memory", -2.3, None), ("Neural dispatcher", -5.3, None),
           ("Learned pace head", -0.4, None), ("Sim-pace in forks", -3.1, None),
           ("Delay prediction (x5)", 0.0, "null in five independent attempts"),
           ("Tuner context prior", -0.1, None),
           ("Joint first moves", -6.9, None), ("Guessed clash model", -2.0, None),
           ("Full ADG deconfliction", 0.0, "not built — collisions already measured at 0"),
           ("Layer-2 congestion", -0.5, None), ("Windowed pair optim.", -0.6, None),
           ("Spare storage slots", -10.6, "slack supplied; the wedge relocated instead")]

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(10.6, 6.5),
                                   gridspec_kw={"width_ratios": [1, 1]})
    for ax, rows, col, title, sub in (
            (axA, keep, GOOD, "Kept — 10 mechanisms",
             "bars show measured value effect; four ship on safety, not value"),
            (axB, cut, BAD, "Cut — 22 mechanisms",
             "the standing bar was fixed in advance: ≥3% or cut")):
        rows = rows[::-1]
        ax.barh(range(len(rows)), [v for _n, v, _t in rows], color=col, height=0.66,
                zorder=3, edgecolor=SURFACE, linewidth=1.2)
        ax.axvline(0, color=INK3, lw=1.0, zorder=4)
        for i, (_n, v, nt) in enumerate(rows):
            if abs(v) < 0.05:
                ax.text(0.4, i, nt, va="center", fontsize=6.9, color=INK3)
            elif v < -9:
                ax.text(v + 0.4, i, "%+.1f%%" % v, va="center", ha="left",
                        fontsize=7.4, color="white", fontweight="bold")
            else:
                ax.text(v + (0.35 if v >= 0 else -0.35), i, "%+.1f%%" % v, va="center",
                        ha="left" if v >= 0 else "right", fontsize=7.4, color=INK2)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([n for n, _v, _t in rows], fontsize=8)
        ax.set_xlim(-15.5, 15.5)
        ax.set_title(title, color=col)
        ax.set_xlabel(sub, fontsize=7.6)
        recess(ax, xgrid=True)
    fig.suptitle("Everything kept reasons about what already exists; everything cut acted on what did not",
                 y=0.98, fontsize=9.6)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save(fig, "fig_ablation.png")


# ------------------------------------------------------------------ figure 5
def fig_horizon():
    """Value against compute for the tuner's cadence/horizon grid; stress days, and ordinary if run."""
    stress = [("fixed", 742.30, 0, 123), ("25/50", 789.02, 2909, 88),
              ("25/100", 815.35, 5543, 69), ("50/100", 799.87, 2952, 95),
              ("50/200", 838.99, 5770, 66), ("100/200", 817.64, 3000, 63)]
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(10.0, 4.0),
                                   gridspec_kw={"width_ratios": [1.15, 1]})
    OFF = {"fixed": (10, 6, "left"), "25/50": (10, -3, "left"), "25/100": (10, -3, "left"),
           "50/100": (-11, -3, "right"), "50/200": (-11, -3, "right"), "100/200": (-11, 9, "right")}
    for lbl, v, cmp_, _s in stress:
        ship = lbl == "50/100"
        best = lbl == "100/200"
        col = C2 if ship else (C3 if best else C1)
        axA.scatter(cmp_, v, s=120 if (ship or best) else 62, color=col, zorder=4,
                    edgecolor=SURFACE, linewidth=1.6)
        if lbl == "fixed":
            continue                      # the dashed reference line already names it
        dx, dy, ha = OFF[lbl]
        axA.annotate(lbl + ("  (shipped)" if ship else ""), (cmp_, v),
                     textcoords="offset points", xytext=(dx, dy), ha=ha,
                     fontsize=7.8, color=INK if (ship or best) else INK2,
                     fontweight="bold" if (ship or best) else "normal")
    axA.annotate("best value per unit of compute:\nthe shipped fork budget, +17.8 value",
                 xy=(3080, 817.6), xytext=(4250, 800), fontsize=7.6, color=C3,
                 arrowprops=dict(arrowstyle="->", color=C3, lw=1.0))
    axA.axhline(742.30, ls="--", color=INK3, lw=1.0, zorder=2)
    axA.text(700, 744.5, "fixed settings, no imagination", fontsize=7.6, color=INK2)
    axA.set_xlabel("imagined steps per day (the compute price)")
    axA.set_ylabel("on-time value, stress days")
    axA.set_title("Horizon is the lever; cadence is not")
    axA.set_xlim(-500, 7600)
    axA.set_ylim(736, 852)
    recess(axA)

    lab = [s[0] for s in stress]
    strand = [s[3] for s in stress]
    axB.bar(range(len(lab)), strand, width=0.66, zorder=3, edgecolor=SURFACE, linewidth=1.4,
            color=[C2 if l == "50/100" else (C3 if l == "100/200" else C1) for l in lab])
    for i, s in enumerate(strand):
        axB.text(i, s + 1.6, str(s), ha="center", fontsize=7.8, color=INK2)
    axB.set_xticks(range(len(lab)))
    axB.set_xticklabels(lab, fontsize=8)
    axB.set_ylabel("robots stranded (48 stress days)")
    axB.set_title("A longer horizon also strands fewer robots")
    axB.set_ylim(0, 140)
    recess(axB)

    ordinary = os.path.join(OUT, "horizon_ordinary.json")
    if os.path.exists(ordinary):
        d = json.load(io.open(ordinary, encoding="utf-8"))
        txt = "  ·  ".join("%s %s: %+.1f (t=%+.2f)" % (r["regime"], r["cell"], r["diff"], r["t"])
                           for r in d if r["cell"] != "fixed")
        fig.text(0.5, -0.04, "Ordinary-day re-check — " + txt, ha="center",
                 fontsize=7.6, color=INK2)
    fig.tight_layout()
    save(fig, "fig_horizon.png")


FIGS = {"fig1": fig_benchmark, "fig2": fig_anticipation, "fig3": fig_sensing,
        "fig4": fig_ablation, "fig5": fig_horizon}

if __name__ == "__main__":
    want = sys.argv[1:] or list(FIGS)
    for k in want:
        FIGS[k]()
