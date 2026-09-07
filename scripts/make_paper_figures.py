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



# ------------------------------------------------------------------ figure 1
RACK = "#e3dccd"        # stored pod, warm neutral against the surface
RACK_E = "#cfc5b1"


def fig_coupled():
    """Figure 1: the four decisions a single free robot couples, on the real floor.

    Geometry is the shipped dense layout read off the simulator, not a sketch: 16 x 25 cells,
    vertical aisles every third column, cross-aisles at y = 0, 7, 14 and 21-23, three pick stations
    on the bottom row, eight charger bays. One cell is one metre.

    Colour roles are kept disjoint: routes are ink and orange, candidate pods aqua, energy amber,
    hazard red, stations blue. Nothing carries meaning by hue alone -- every element is also
    labelled on the floor.
    """
    from matplotlib.patches import (Rectangle, Circle, FancyArrowPatch, FancyBboxPatch)
    W, H = 16, 25
    aisle_x = {0, 3, 6, 9, 12, 15}
    cross_y = {0, 7, 14, 21, 22, 23, 24}
    stations = [(1, 24), (5, 24), (11, 24)]
    bays = [(1, 1), (2, 5), (4, 10), (5, 15), (7, 19), (10, 3), (11, 8), (13, 12)]

    def is_hw(x, y):
        return x in aisle_x or y in cross_y

    def c(x, y):
        return (x + .5, y + .5)

    fig = plt.figure(figsize=(12.4, 7.4))
    ax = fig.add_axes([0.015, 0.02, 0.40, 0.96])
    tx = fig.add_axes([0.44, 0.02, 0.55, 0.96])
    tx.axis("off")

    # ---- floor -----------------------------------------------------------------------------
    for y in range(H):
        for x in range(W):
            if (x, y) in stations:
                ax.add_patch(Rectangle((x, y), 1, 1, fc=C1, ec=SURFACE, lw=.7, zorder=2))
            elif (x, y) in bays:
                ax.add_patch(Rectangle((x, y), 1, 1, fc=SURFACE, ec=C4, lw=1.5, zorder=2))
            elif not is_hw(x, y):
                ax.add_patch(Rectangle((x, y), 1, 1, fc=RACK, ec=RACK_E, lw=.5, zorder=1))
    ax.add_patch(Rectangle((0, 0), W, H, fc="none", ec=GRID, lw=1.1, zorder=4))

    # ---- (4) hazard: one real, one believed but already cleared -----------------------------
    ax.add_patch(Rectangle((9, 7), 1, 1, fc=BAD, alpha=.85, ec="none", zorder=3))
    ax.add_patch(Rectangle((8.9, 6.9), 1.2, 1.2, fc="none", ec=BAD, lw=1.6,
                           ls=(0, (2.2, 1.6)), zorder=6))
    ax.add_patch(Rectangle((2.9, 16.9), 1.2, 1.2, fc="none", ec=BAD, lw=1.6,
                           ls=(0, (2.2, 1.6)), zorder=6))
    ax.text(4.6, 17.5, "believed blocked,\nactually clear", fontsize=7.4, color=BAD,
            va="center", zorder=7, linespacing=1.4)

    # ---- (2) two routes to the same pod ------------------------------------------------------
    # The two paths share the x = 12 stretch, so they are drawn with a small lateral offset:
    # without it neither route can be traced end to end where they overlap.
    clear = [(6, 10), (6, 14), (12, 14), (12, 4), (13, 4)]
    congested = [(6, 10), (6, 7), (12, 7), (12, 4), (13, 4)]

    def path(pts, dx):
        return [c(*p)[0] + dx for p in pts], [c(*p)[1] for p in pts]

    xs, ys = path(clear, -0.17)
    ax.plot(xs, ys, color=INK2, lw=2.6, zorder=5, solid_capstyle="round")
    xs, ys = path(congested, +0.17)
    ax.plot(xs, ys, color=C2, lw=2.6, ls=(0, (3.6, 2.0)), zorder=5, solid_capstyle="round")

    for p in ((8, 7), (10, 7), (11, 7)):
        ax.add_patch(Circle(c(*p), .30, fc=INK3, ec=SURFACE, lw=1.0, zorder=7))

    # Both routes start at the robot and end at the same pod, so they are named in a key below
    # the floor rather than in labels on it: the aisles are too narrow to hold legible text.
    def route_key(row, col, dash, name, dist, note):
        y = 26.95 + row * 1.40
        ax.plot([0.5, 2.4], [y, y], color=col, lw=2.6, zorder=6,
                ls=(0, (3.6, 2.0)) if dash else "solid", solid_capstyle="round")
        ax.text(2.9, y, "%s  ·  %d m" % (name, dist), fontsize=8.4, fontweight="bold",
                color=col, va="center", zorder=6)
        ax.text(7.9, y, note, fontsize=8.0, color=INK2, va="center", zorder=6)

    route_key(0, C2, True, "SHORT", 13, "crosses the aisle three robots are already in")
    route_key(1, INK2, False, "LONG", 21, "eight metres further, and empty")
    ax.text(0.5, 25.70, "TWO ROUTES TO THE SAME POD", fontsize=7.4, color=INK3,
            va="center", fontweight="bold", zorder=6)

    # ---- (1) two candidate pods ---------------------------------------------------------------
    ax.add_patch(Rectangle((7, 9), 1, 1, fc=C3, alpha=.32, ec=C3, lw=1.9, zorder=3))
    ax.add_patch(Rectangle((13, 4), 1, 1, fc=C3, alpha=.32, ec=C3, lw=1.9, zorder=3))
    ax.text(8.30, 9.55, "near,\nworth little", fontsize=7.4, color=C3, ha="left",
            va="center", zorder=7, linespacing=1.4)
    ax.text(13.5, 2.6, "far, worth much,\ndue soon", fontsize=7.4, color=C3, ha="center",
            va="center", zorder=7, linespacing=1.4)

    # ---- (3) energy: reachable set, and the nearest bay ---------------------------------------
    ax.add_patch(Circle(c(6, 10), 3.1, fc=C4, alpha=.07, ec=C4, lw=1.2,
                        ls=(0, (1.6, 2.0)), zorder=2))
    ax.plot([c(6, 10)[0], c(4, 10)[0]], [c(6, 10)[1], c(4, 10)[1]],
            color=C4, lw=2.2, ls=(0, (1.4, 1.6)), zorder=6)
    ax.text(1.0, 12.6, "how far 38%\nstill reaches", fontsize=7.4, color=C4, va="center",
            zorder=7, linespacing=1.4)

    # ---- the deciding robot -------------------------------------------------------------------
    ax.add_patch(Circle(c(6, 10), .42, fc=INK, ec=SURFACE, lw=1.7, zorder=9))
    ax.add_patch(Rectangle((4.55, 8.55), 1.55, .40, fc=SURFACE, ec=INK3, lw=.8, zorder=9))
    ax.add_patch(Rectangle((4.59, 8.59), 1.55 * .38, .32, fc=C4, ec="none", zorder=10))
    ax.text(4.35, 8.75, "38%", ha="right", va="center", fontsize=7.4, color=INK2, zorder=10,
            fontfamily="monospace")

    # ---- numbered badges ----------------------------------------------------------------------
    for n, (px, py), tgt in ((1, (10.6, 10.6), (13.3, 4.9)),
                             (2, (8.1, 12.3), (9.4, 14.3)),
                             (3, (2.2, 10.4), (4.3, 10.3)),
                             (4, (11.0, 5.4), (9.7, 7.2))):
        ax.add_patch(FancyArrowPatch((px, py), tgt, arrowstyle="-|>", mutation_scale=9,
                                     color=INK3, lw=1.0, shrinkA=10, shrinkB=4, zorder=8))
        ax.add_patch(Circle((px, py), .60, fc=INK, ec=SURFACE, lw=1.4, zorder=11))
        ax.text(px, py, str(n), ha="center", va="center", color=SURFACE,
                fontsize=9.2, fontweight="bold", zorder=12)
    ax.add_patch(FancyArrowPatch((10.6, 10.6), (8.15, 9.6), arrowstyle="-|>", mutation_scale=9,
                                 color=INK3, lw=1.0, shrinkA=10, shrinkB=4, zorder=8))

    # ---- scale bar ------------------------------------------------------------------------------
    ax.plot([0.6, 5.6], [22.6, 22.6], color=INK2, lw=1.6, solid_capstyle="butt", zorder=5)
    for xx in (0.6, 5.6):
        ax.plot([xx, xx], [22.3, 22.9], color=INK2, lw=1.2, zorder=5)
    ax.text(6.2, 22.6, "5 m   (one cell = 1 m)", va="center", fontsize=7.4, color=INK2, zorder=5)

    ax.set_xlim(-0.5, W + 2.3)
    ax.set_ylim(H + 4.0, -0.7)
    ax.set_aspect("equal")
    ax.axis("off")

    # ---- callouts ---------------------------------------------------------------------------------
    tx.text(0, 0.985, "One robot has just come free.", transform=tx.transAxes,
            fontsize=14.5, fontweight="bold", color=INK, va="top")
    tx.text(0, 0.930, "Answering \u201cwhat next?\u201d settles four questions at once. Each has a "
                      "literature of its own;\nthe coupling between them does not.",
            transform=tx.transAxes, fontsize=10, color=INK2, va="top", linespacing=1.5)

    items = [
        (0.826, 1, "Which task", C3,
         "A near pod worth little, or a distant pod worth much whose deadline is\n"
         "close. A late delivery banks nothing, so the choice is neither distance\n"
         "nor value but value that still arrives in time."),
        (0.632, 2, "Which route", C2,
         "Both paths reach the same pod. The short one crosses an aisle three\n"
         "robots are already in; the long one is clear. What a route costs\n"
         "depends on what every other robot has just been told to do."),
        (0.438, 3, "Whether to charge first", C4,
         "At 38% this robot can reach the pod, or reach a charger, but not\n"
         "reliably both. What binds is not a reserve threshold but whether a\n"
         "charger is still reachable from wherever the task ends."),
        (0.244, 4, "What it cannot see", BAD,
         "A spill sits in the short route. The fleet believes in it because\n"
         "somebody drove past \u2014 and believes in another that was cleared, because\n"
         "nobody has been back to look."),
    ]
    for y, n, title, col, body in items:
        tx.add_patch(Circle((0.024, y), 0.0175, fc=INK, ec="none",
                            transform=tx.transAxes, clip_on=False, zorder=5))
        tx.text(0.024, y, str(n), transform=tx.transAxes, ha="center", va="center",
                color=SURFACE, fontsize=8.8, fontweight="bold", zorder=6)
        tx.text(0.064, y + 0.004, title, transform=tx.transAxes, fontsize=11.5,
                fontweight="bold", color=col, va="center")
        tx.text(0.064, y - 0.072, body, transform=tx.transAxes, fontsize=9.5,
                color=INK2, va="center", linespacing=1.65)

    tx.plot([0.024, 0.062], [0.055, 0.055], transform=tx.transAxes, color=BAD, lw=5,
            solid_capstyle="butt", alpha=.85)
    tx.text(0.076, 0.055, "true state", transform=tx.transAxes, fontsize=9.2, color=INK2,
            va="center")
    tx.plot([0.235, 0.273], [0.055, 0.055], transform=tx.transAxes, color=BAD, lw=1.7,
            ls=(0, (2.2, 1.6)))
    tx.text(0.287, 0.055, "what the fleet believes", transform=tx.transAxes, fontsize=9.2,
            color=INK2, va="center")
    for i2, (fcol, ecol, lab) in enumerate(((RACK, RACK_E, "stored pod"),
                                            (C1, C1, "pick station"),
                                            (SURFACE, C4, "charger bay"))):
        xx = 0.024 + i2 * 0.200
        tx.add_patch(Rectangle((xx, 0.000), 0.028, 0.030, fc=fcol, ec=ecol, lw=1.3,
                               transform=tx.transAxes, clip_on=False))
        tx.text(xx + 0.038, 0.015, lab, transform=tx.transAxes, fontsize=9.2, color=INK2,
                va="center")

    save(fig, "fig_coupled.png")


FIGS = {"fig0": fig_coupled, "fig1": fig_benchmark, "fig2": fig_anticipation, "fig3": fig_sensing,
        "fig4": fig_ablation, "fig5": fig_horizon}

if __name__ == "__main__":
    want = sys.argv[1:] or list(FIGS)
    for k in want:
        FIGS[k]()
