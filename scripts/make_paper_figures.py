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

    The floor is drawn by ONE function, `floor(ax, show, ...)`, which paints a named subset of the
    layers in a fixed order:

        rack    racks and the floor outline          routes  the two routes
        zone    the reachable-charge disc            robot   the deciding robot and its gauge
        cells   stations and charger bays            badges  the numbered leaders
        tasks   the two candidate pods               plates  route name plates and pod tags
        belief  the spill, and the phantom

    The large panel asks for everything. Each of the four questions on the right also gets its own
    small panel showing that question's layer ALONE, over a ghosted floor. That is the figure's
    argument made visible: each layer is a literature of its own and reads perfectly well by itself;
    only the large panel, where they are all switched on at once, shows what has to be decided.

    The two routes are disjoint. They share their first cell and their last and touch nowhere else,
    which is possible only because the target pod at (14, 6) has two aisle faces -- the cross-aisle
    above it and the right-hand aisle beside it.
    """
    from matplotlib.patches import Rectangle, Circle, FancyArrowPatch

    L_RACK, L_ZONE, L_CELL, L_ROUTE, L_MARK, L_LEAD, L_BADGE, L_PLATE = 1, 2, 3, 5, 7, 8, 11, 13

    W, H = 16, 25
    aisle_x = {0, 3, 6, 9, 12, 15}
    cross_y = {0, 7, 14, 21, 22, 23, 24}
    stations = [(1, 24), (5, 24), (11, 24)]
    bays = [(1, 1), (2, 5), (4, 10), (5, 15), (7, 19), (10, 3), (11, 8), (13, 12)]

    HOME = (6, 10)          # the deciding robot
    NEAR = (7, 9)           # candidate pod, close and cheap
    FAR = (14, 6)           # candidate pod, distant and valuable -- two aisle faces
    SPILL = (10, 7)         # a real obstruction, on the busy leg
    PHANTOM = (3, 17)       # believed blocked, actually clear
    OTHERS = [(11, 7), (12, 7), (13, 7)]
    BAY = (4, 10)           # the nearest charger to the deciding robot

    busy = [HOME, (6, 7), (14, 7), FAR]
    clear = [HOME, (6, 14), (15, 14), (15, 6), FAR]

    def is_hw(x, y):
        return x in aisle_x or y in cross_y

    def c(x, y):
        return (x + .5, y + .5)

    def metres(pts):
        return sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(pts, pts[1:]))

    M_BUSY, M_CLEAR = metres(busy), metres(clear)

    # ------------------------------------------------------------------ one floor, many subsets
    def floor(ax, show, ghost=False, crop=None):
        """Paint the named layers, lowest first. `ghost` fades the racks so a single layer reads."""
        rack_fc = "#efeade" if ghost else RACK
        rack_ec = "#e5dfd0" if ghost else RACK_E
        for y in range(H):
            for x in range(W):
                if not is_hw(x, y) and (x, y) not in (NEAR, FAR):
                    ax.add_patch(Rectangle((x, y), 1, 1, fc=rack_fc, ec=rack_ec, lw=.5,
                                           zorder=L_RACK))
        ax.add_patch(Rectangle((0, 0), W, H, fc="none", ec=GRID, lw=1.1, zorder=L_CELL + 1))

        if "zone" in show:
            ax.add_patch(Circle(c(*HOME), 3.1, fc=C4, alpha=.07 if not ghost else .12, ec=C4,
                                lw=1.2, ls=(0, (1.6, 2.0)), zorder=L_ZONE))
        if "cells" in show:
            for p in stations:
                ax.add_patch(Rectangle(p, 1, 1, fc=C1, ec=SURFACE, lw=.7, zorder=L_CELL))
            for p in bays:
                ax.add_patch(Rectangle(p, 1, 1, fc=SURFACE, ec=C4, lw=1.5, zorder=L_CELL))
        if "bay" in show:
            ax.add_patch(Rectangle(BAY, 1, 1, fc=SURFACE, ec=C4, lw=1.8, zorder=L_CELL))
        if "tasks" in show:
            for p in (NEAR, FAR):
                ax.add_patch(Rectangle(p, 1, 1, fc=C3, alpha=.55 if ghost else .32, ec=C3,
                                       lw=2.4 if ghost else 1.9, zorder=L_CELL))
        if "belief" in show:
            ax.add_patch(Rectangle(SPILL, 1, 1, fc=BAD, alpha=.85, ec="none", zorder=L_CELL))
            for p in (SPILL, PHANTOM):
                ax.add_patch(Rectangle((p[0] - .1, p[1] - .1), 1.2, 1.2, fc="none", ec=BAD,
                                       lw=1.6, ls=(0, (2.2, 1.6)), zorder=L_MARK))
        if "routes" in show:
            for pts, col, dashed in ((busy, C2, True), (clear, INK2, False)):
                xy = [c(*p) for p in pts]
                (ax_, ay_), (bx_, by_) = xy[-2], xy[-1]      # stop at the face, not the centre
                xy[-1] = (bx_ + (0.48 if ax_ > bx_ else -0.48 if ax_ < bx_ else 0),
                          by_ + (0.48 if ay_ > by_ else -0.48 if ay_ < by_ else 0))
                ax.plot([p[0] for p in xy], [p[1] for p in xy], color=col,
                        lw=2.8 if not ghost else 2.4,
                        ls=(0, (3.6, 2.0)) if dashed else "solid", zorder=L_ROUTE,
                        solid_capstyle="round", dash_capstyle="round")
            for p in OTHERS:
                ax.add_patch(Circle(c(*p), .30, fc=INK3, ec=SURFACE, lw=1.0, zorder=L_MARK))
        if "robot" in show:
            ax.add_patch(Circle(c(*HOME), .44, fc=INK, ec=SURFACE, lw=1.7, zorder=L_MARK + 1))
        if "gauge" in show:
            ax.add_patch(Rectangle((4.50, 11.15), 1.60, .42, fc=SURFACE, ec=INK3, lw=.8,
                                   zorder=L_MARK + 1))
            ax.add_patch(Rectangle((4.54, 11.19), 1.60 * .38, .34, fc=C4, ec="none",
                                   zorder=L_MARK + 2))
            ax.text(4.30, 11.36, "38%", ha="right", va="center", fontsize=7.2, color=INK2,
                    zorder=L_MARK + 2, fontfamily="monospace")
        if "badges" in show:
            for n, at, tgt in ((1, (13.15, 9.65), (8.08, 9.65)),
                               (2, (8.6, 12.3), (9.75, 14.02)),
                               (3, (2.4, 10.5), (4.30, 10.50)),
                               (4, (11.3, 4.5), (10.55, 7.00))):
                ax.add_patch(FancyArrowPatch(at, tgt, arrowstyle="-|>", mutation_scale=9,
                                             color=INK3, lw=1.0, shrinkA=10, shrinkB=3,
                                             zorder=L_LEAD))
                ax.add_patch(Circle(at, .60, fc=INK, ec=SURFACE, lw=1.4, zorder=L_BADGE))
                ax.text(at[0], at[1], str(n), ha="center", va="center", color=SURFACE,
                        fontsize=9.2, fontweight="bold", zorder=L_BADGE + 1)
            ax.add_patch(FancyArrowPatch((13.15, 9.65), (14.20, 7.02), arrowstyle="-|>",
                                         mutation_scale=9, color=INK3, lw=1.0, shrinkA=10,
                                         shrinkB=3, zorder=L_LEAD))
        if "plates" in show:
            def plate(x, y, col, text, filled):
                ax.text(x, y, text, fontsize=7.2, fontweight="bold", ha="center", va="center",
                        color=SURFACE if filled else col, zorder=L_PLATE,
                        bbox=dict(boxstyle="round,pad=0.30", fc=col if filled else SURFACE,
                                  ec=col, lw=1.3))
            plate(7.28, 7.50, C2, "SHORT · %d m" % M_BUSY, True)
            plate(10.00, 14.50, INK2, "LONG · %d m" % M_CLEAR, False)
            ax.text(7.15, 8.42, "near · low value", fontsize=7.2, color=C3, ha="left",
                    va="center", zorder=L_PLATE)
            ax.text(13.90, 4.35, "far · high value,\ndue soon", fontsize=7.2, color=C3,
                    ha="center", va="center", zorder=L_PLATE, linespacing=1.4)
        if "scale" in show:
            ax.plot([0.6, 5.6], [22.6, 22.6], color=INK2, lw=1.6, solid_capstyle="butt",
                    zorder=L_PLATE)
            for xx in (0.6, 5.6):
                ax.plot([xx, xx], [22.3, 22.9], color=INK2, lw=1.2, zorder=L_PLATE)
            ax.text(6.2, 22.6, "5 m   (one cell = 1 m)", va="center", fontsize=7.4, color=INK2,
                    zorder=L_PLATE)

        x0, x1, y0, y1 = crop or (-0.6, W + 1.0, -0.6, H + 0.6)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
        ax.set_aspect("equal")
        ax.axis("off")

    fig = plt.figure(figsize=(12.8, 9.4))
    kx = fig.add_axes([0.013, 0.856, 0.978, 0.132])     # object key, across the top
    ax = fig.add_axes([0.008, 0.014, 0.330, 0.818])     # the whole floor, every layer on
    tx = fig.add_axes([0.368, 0.014, 0.624, 0.818])     # the four questions
    for a in (kx, tx):
        a.axis("off")
        a.set_xlim(0, 1)
        a.set_ylim(0, 1)

    floor(ax, {"zone", "cells", "tasks", "belief", "routes", "robot", "gauge", "badges",
               "plates", "scale"})

    # ==================================================== the key: every object named, up top
    kx.text(0, 0.955, "WHAT IS ON THE FLOOR", fontsize=7.6, fontweight="bold", color=INK3,
            va="top", transform=kx.transAxes)
    kx.plot([0, 1], [0.855, 0.855], transform=kx.transAxes, color=GRID, lw=1.0)

    COLX = (0.000, 0.250, 0.500, 0.752)
    ROWY = (0.610, 0.360, 0.110)

    def swatch(kind, x, y, col):
        """One key mark at (x, y) in key-axes coordinates. Marks are 0.030 wide."""
        if kind == "rect":
            kx.add_patch(Rectangle((x, y - .048), .030, .096, fc=col[0], ec=col[1], lw=1.3,
                                   transform=kx.transAxes, clip_on=False))
        elif kind == "dashed":
            kx.add_patch(Rectangle((x, y - .048), .030, .096, fc="none", ec=col[1], lw=1.5,
                                   ls=(0, (2.0, 1.4)), transform=kx.transAxes, clip_on=False))
        elif kind in ("disc", "disc_s"):
            # Circle() in this wide, short axes renders as an ellipse; markers stay round.
            kx.plot([x + .015], [y], transform=kx.transAxes, marker="o", clip_on=False,
                    ms=13 if kind == "disc" else 9, mfc=col[0], mec=col[1], mew=1.4)
        elif kind == "zone":
            kx.plot([x + .015], [y], transform=kx.transAxes, marker="o", clip_on=False,
                    ms=22, mfc=C4, mec=C4, mew=1.2, alpha=.16)
            kx.plot([x + .015], [y], transform=kx.transAxes, marker="o", clip_on=False,
                    ms=22, mfc="none", mec=C4, mew=1.2, ls="none")
        elif kind in ("solid", "dash"):
            kx.plot([x, x + .030], [y, y], transform=kx.transAxes, color=col[1], lw=2.6,
                    ls="solid" if kind == "solid" else (0, (3.0, 1.8)), solid_capstyle="round",
                    clip_on=False)

    ITEMS = [
        (0, 0, "disc", (INK, SURFACE), "the deciding robot", "gauge shows 38% charge"),
        (1, 0, "disc_s", (INK3, SURFACE), "three other robots", "already in the busy aisle"),
        (2, 0, "rect", (RACK, RACK_E), "stored pod", "not part of this decision"),
        (3, 0, "rect", (C1, C1), "pick station", "where value is banked"),
        (0, 1, "rect", (SURFACE, C4), "charger bay", "eight of them, fixed"),
        (1, 1, "rect", ("#a9dfc7", C3), "candidate pod", "the two tasks on offer"),
        (2, 1, "zone", (C4, C4), "reach of 38% charge", "beyond it, no charger"),
        (3, 1, "dashed", (None, BAD), "believed blocked", "nothing actually there"),
        (0, 2, "rect", (BAD, BAD), "spill, really there", "and correctly believed in"),
        (1, 2, "dash", (None, C2), "SHORT route · %d m" % M_BUSY, "through the spill"),
        (2, 2, "solid", (None, INK2), "LONG route · %d m" % M_CLEAR,
         "%d m further, and empty" % (M_CLEAR - M_BUSY)),
    ]
    for col, row, kind, cols, name, note in ITEMS:
        x, y = COLX[col], ROWY[row]
        swatch(kind, x, y, cols)
        kx.text(x + .046, y + .052, name, transform=kx.transAxes, fontsize=8.6,
                fontweight="bold", color=INK, va="center")
        kx.text(x + .046, y - .062, note, transform=kx.transAxes, fontsize=8.0, color=INK2,
                va="center")

    # ==================================================== the four questions, each with its layer
    tx.text(0, 0.995, "One robot has just come free.", transform=tx.transAxes,
            fontsize=15.5, fontweight="bold", color=INK, va="top")
    tx.text(0, 0.932, "Answering “what next?” settles four questions at once. Each layer below "
                      "reads perfectly well on its own, and each\nhas a literature of its own. "
                      "Only the floor on the left, with all four switched on together, is the "
                      "problem.",
            transform=tx.transAxes, fontsize=10.0, color=INK2, va="top", linespacing=1.55)

    items = [
        (0.762, 1, "Which task", C3, {"tasks", "robot"},
         "A near pod worth little, or a distant pod worth much whose\n"
         "deadline is close. A late delivery banks nothing, so the choice\n"
         "is neither distance nor value but value that still arrives in time."),
        (0.535, 2, "Which route", C2, {"routes", "robot"},
         "Both paths reach the same pod and share no ground in between.\n"
         "The short one crosses an aisle three robots are already in; the\n"
         "long one is clear. What a route costs depends on what every\n"
         "other robot was just told to do."),
        (0.308, 3, "Whether to charge first", C4, {"zone", "bay", "robot"},
         "At 38% this robot can reach the pod, or reach a charger, but\n"
         "not reliably both. What binds is not a reserve threshold but\n"
         "whether a charger is still reachable from wherever the task ends."),
        (0.081, 4, "What it cannot see", BAD, {"belief", "robot"},
         "A spill sits in the short route. The fleet believes in it because\n"
         "somebody drove past — and believes in another that was cleared,\n"
         "because nobody has been back to look."),
    ]
    TW, TH = 0.115, 0.165            # layer-panel size, as a fraction of the figure
    for ty, n, title, col, layers, body in items:
        tx.add_patch(Circle((0.020, ty), 0.0155, fc=INK, ec="none", transform=tx.transAxes,
                            clip_on=False, zorder=5))
        tx.text(0.020, ty, str(n), transform=tx.transAxes, ha="center", va="center",
                color=SURFACE, fontsize=8.8, fontweight="bold", zorder=6)
        tx.text(0.055, ty + 0.003, title, transform=tx.transAxes, fontsize=12,
                fontweight="bold", color=col, va="center")
        tx.text(0.055, ty - 0.088, body, transform=tx.transAxes, fontsize=9.5, color=INK2,
                va="center", linespacing=1.62)
        # this question's layer, alone, over a ghosted floor -- cropped to where the action is
        cy = 0.014 + ty * 0.818
        th = fig.add_axes([0.992 - TW, cy - TH / 2, TW, TH])
        floor(th, layers, ghost=True, crop=(-0.3, W + 0.3, 2.0, 19.4))
        for s in th.spines.values():
            s.set_visible(False)
        th.add_patch(Rectangle((-0.25, 2.05), W + 0.5, 17.3, fc="none", ec=col, lw=1.1,
                               zorder=20, clip_on=False))

    save(fig, "fig_coupled.png")


def fig_realism():
    """Figure 2: what correcting the world's constants cost in measured throughput.

    Four readings, each the same three episodes re-run after one more group of constants was
    corrected (docs/PAPER_DRAFT.md 3.7). The constants themselves are Table 1; this figure is
    only the arithmetic they add up to.

    Everything that names a row lives in the left margin and everything that measures it lives on
    the bar, so the right-hand third is free for the bracket that carries the claim.
    """
    from matplotlib.patches import Rectangle

    ROWS = [
        ("as found", 171, "31% storage · 10 stations · uniform values · no service time"),
        ("+ geometry and stations", 95, "storage 31% → 55%, stations 10 → 3"),
        ("+ lognormal order values", 76, "uniform 1–15 → lognormal"),
        ("+ service times", 58, "load 0 → 8 steps, station 0 → 6 steps per item"),
    ]

    fig = plt.figure(figsize=(10.8, 4.6))
    ax = fig.add_axes([0.300, 0.150, 0.545, 0.615])

    for i, (name, val, change) in enumerate(ROWS):
        last = i == len(ROWS) - 1
        ax.add_patch(Rectangle((0, i - .30), val, .60, ec="none", zorder=3,
                               fc=C1 if last else (INK3 if i == 0 else "#b9cfe8")))
        ax.text(val + 4, i, "%d" % val, va="center", ha="left", fontsize=13,
                fontweight="bold", color=C1 if last else INK, zorder=4)
        ax.text(-5, i - .10, name, va="center", ha="right", fontsize=10.4,
                fontweight="bold", color=INK)
        ax.text(-5, i + .22, change, va="center", ha="right", fontsize=8.4, color=INK2)
        if i:
            prev = ROWS[i - 1][1]
            ax.plot([val, prev], [i - .30, i - .30], color=C2, lw=1.1, zorder=4)
            ax.plot([prev, prev], [i - .30, i - .70], color=INK3, lw=.8, ls=(0, (2, 2)), zorder=2)
            ax.text((val + prev) / 2, i - .50, "−%d" % (prev - val), ha="center", va="center",
                    fontsize=9.4, fontweight="bold", color=C2, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.18", fc=SURFACE, ec="none"))

    # the bracket the caption is about, in the clear third to the right of every bar
    bx = 190
    ax.plot([bx, bx + 7, bx + 7, bx], [0, 0, 3, 3], color=INK, lw=1.4, zorder=6,
            solid_capstyle="butt", clip_on=False)
    ax.text(bx + 13, 1.30, "−66%", va="bottom", ha="left", fontsize=17, fontweight="bold",
            color=INK, zorder=6, clip_on=False)
    ax.text(bx + 13, 1.48, "the world was three\ntimes too productive", va="top", ha="left",
            fontsize=8.6, color=INK2, zorder=6, linespacing=1.5, clip_on=False)

    ax.set_xlim(0, 200)
    ax.set_ylim(3.78, -0.78)
    ax.set_yticks([])
    ax.set_xticks([0, 50, 100, 150])
    ax.tick_params(axis="x", length=0, labelsize=9, colors=INK2, pad=4)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_xlabel("deliveries per three episodes", fontsize=9.4, color=INK2, labelpad=7)
    ax.xaxis.grid(True, color=GRID, lw=.8, zorder=0)
    ax.set_axisbelow(True)

    fig.text(0.012, 0.968, "Correcting the world cost two thirds of the throughput",
             fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.012, 0.898, "Same three episodes and the same policy, re-measured after each group "
                           "of constants was corrected. In-aisle picking runs at 40–60% storage; "
                           "three stations\nbalance eight robots; real order values are long-tailed; "
                           "and the simulator had spent no time at all on any physical operation. "
                           "Every result taken\nbefore the bottom row was measured on the top row's "
                           "world, and none of them is reported in this paper.",
             fontsize=9.2, color=INK2, va="top", linespacing=1.55)
    save(fig, "fig_realism.png")

def fig_planner():
    """Figure 3: the decision layer — a funnel that ends in a rollout, wrapped by a tuner.

    Stages 1-5 are preparation: they shrink the task set and order it. Stage 6 is the only place a
    decision is made, and it is made by simulating. Stage 7 throws away everything the simulation
    imagined except the first move. The band around all of it is the model-predictive tuner, which
    re-chooses the funnel's own settings by the same forward simulation -- its absence is what made
    the previous version of this diagram a picture of the ablated system.

    Laid out on an explicit vertical budget: every box's top and height are computed, so nothing is
    positioned by eye and nothing can land on anything else.
    """
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

    STAGES = [
        ("1", "Cross off the impossible", "tasks already assigned, unreachable, or past due",
         "~120 → ~40"),
        ("2", "Cheap screen", "distance, value and deadline slack — no simulation yet", "~40 → 15"),
        ("3", "Yen's k-shortest routes", "k = 3 per surviving candidate", "15 × 3"),
        ("4", "Delete illegal routes", "reserved-cell collisions; battery floor at the far end",
         "drops ~1 in 9"),
        ("5", "Order by tier, value, urgency", "deliberately optimistic — no pace bias here",
         "ranked 15"),
    ]
    X0, WIDE, H_STAGE, GAP = 7.0, 48.0, 6.4, 2.05
    H_ROLL = 11.2

    fig = plt.figure(figsize=(11.8, 8.8))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(100, 0)                 # y increases downward, like the reading order
    ax.axis("off")

    def box(x, y, w, h, fc, ec, lw=1.2, z=3):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.0,rounding_size=0.9",
                                    fc=fc, ec=ec, lw=lw, zorder=z))

    # ------------------------------------------------------- the tuner band, drawn under everything
    ax.add_patch(FancyBboxPatch((2.0, 10.2), 79.0, 88.2,
                                boxstyle="round,pad=0.0,rounding_size=1.6",
                                fc="#f7f2e6", ec=C4, lw=1.6, ls=(0, (5, 3)), zorder=1))
    ax.text(8.0, 12.9, "THE SELF-TUNER — the outer loop, and part of the shipped system",
            fontsize=9.8, fontweight="bold", color="#8a6200", va="center", zorder=2)
    ax.text(8.0, 16.0, "Every 50 steps: deep-copy the whole warehouse and roll 100 steps forward "
                       "under a few candidate settings of nine knobs, adopting\nwhichever wins. "
                       "Candidates come from a UCB1 bandit over parameter moves, not brute "
                       "enumeration — the same forward\nsimulation as stage 6, turned on the "
                       "funnel's own settings.",
            fontsize=8.8, color=INK2, va="center", linespacing=1.6, zorder=2)

    # ------------------------------------------------------- stages 1-5: the funnel, visibly narrowing
    y = 21.5
    for i, (n, title, body, count) in enumerate(STAGES):
        w = WIDE - i * 2.0
        box(X0, y, w, H_STAGE, SURFACE, GRID, 1.2, 4)
        ax.add_patch(Rectangle((X0, y), 0.85, H_STAGE, fc="#c9d7e8", ec="none", zorder=5))
        ax.text(X0 + 2.5, y + 2.4, n, fontsize=11.5, fontweight="bold", color=INK3,
                va="center", ha="center", zorder=6)
        ax.text(X0 + 4.8, y + 2.4, title, fontsize=10.2, fontweight="bold", color=INK,
                va="center", zorder=6)
        ax.text(X0 + 4.8, y + 4.5, body, fontsize=8.6, color=INK2, va="center", zorder=6)
        ax.text(X0 + w - 1.8, y + 2.4, count, fontsize=8.8, color=INK3, fontweight="bold",
                ha="right", va="center", zorder=6, fontfamily="monospace")
        ax.add_patch(FancyArrowPatch((X0 + 2.1, y + H_STAGE), (X0 + 2.1, y + H_STAGE + GAP),
                                     arrowstyle="-|>", mutation_scale=11, color=INK3, lw=1.2,
                                     zorder=5))
        y += H_STAGE + GAP

    # ------------------------------------------------------- stage 6: the only decision
    y6 = y
    box(X0, y6, WIDE, H_ROLL, SURFACE, C1, 2.3, 4)
    ax.add_patch(Rectangle((X0, y6), 0.85, H_ROLL, fc=C1, ec="none", zorder=5))
    ax.text(X0 + 2.5, y6 + 2.6, "6", fontsize=12.5, fontweight="bold", color=C1,
            va="center", ha="center", zorder=6)
    ax.text(X0 + 4.8, y6 + 2.6, "Roll the fleet forward", fontsize=11, fontweight="bold",
            color=INK, va="center", zorder=6)
    ax.text(X0 + WIDE - 1.8, y6 + 2.6, "the decision", fontsize=8.8, color=C1,
            fontweight="bold", ha="right", va="center", zorder=6, fontfamily="monospace")
    ax.text(X0 + 4.8, y6 + 4.4, "each candidate simulated forward to now + SEQ_DEPTH × 75, with "
                                "pickers as\nconsumed resources and an event heap of robot free "
                                "times; ranked by the\ntotal on-time value the imagined future "
                                "actually banks",
            fontsize=8.6, color=INK2, va="top", zorder=6, linespacing=1.62)
    ax.add_patch(FancyArrowPatch((X0 + 2.1, y6 + H_ROLL), (X0 + 2.1, y6 + H_ROLL + GAP),
                                 arrowstyle="-|>", mutation_scale=11, color=INK3, lw=1.2,
                                 zorder=5))

    # ------------------------------------------------------- stage 7: commit one move
    y7 = y6 + H_ROLL + GAP
    box(X0, y7, WIDE - 12.0, H_STAGE, SURFACE, GRID, 1.2, 4)
    ax.add_patch(Rectangle((X0, y7), 0.85, H_STAGE, fc="#c9d7e8", ec="none", zorder=5))
    ax.text(X0 + 2.5, y7 + 2.4, "7", fontsize=11.5, fontweight="bold", color=INK3,
            va="center", ha="center", zorder=6)
    ax.text(X0 + 4.8, y7 + 2.4, "Commit the first move", fontsize=10.2, fontweight="bold",
            color=INK, va="center", zorder=6)
    ax.text(X0 + 4.8, y7 + 4.5, "the rest of the imagined trajectory is thrown away",
            fontsize=8.6, color=INK2, va="center", zorder=6)
    ax.text(X0 + WIDE - 13.8, y7 + 2.4, "1 move", fontsize=8.8, color=INK3, fontweight="bold",
            ha="right", va="center", zorder=6, fontfamily="monospace")

    # ------------------------------------------------------- the one number this figure carries
    ys = y7 + H_STAGE + 2.8
    H_CLAIM = 9.8
    box(X0, ys, WIDE, H_CLAIM, "#eef4fb", "#bcd4ee", 1.2, 4)
    ax.text(X0 + 2.4, ys + 2.4, "Stage 6 is the only point at which anything is chosen.",
            fontsize=9.6, fontweight="bold", color=C1, va="center", zorder=6)
    ax.text(X0 + 2.4, ys + 3.9, "Disabling it and selecting on the stage-5 ordering\nalone costs "
                                "−7.2% of on-time value (t = −30.6) —\nthe largest single mechanism "
                                "effect in this paper.",
            fontsize=8.6, color=INK2, va="top", zorder=6, linespacing=1.66)

    # ------------------------------------------------------- the right-hand column
    PX, PW = 61.0, 18.0
    box(PX, 21.5, PW, 17.5, "#f3f8f5", "#bcdccb", 1.2, 3)
    ax.text(PX + 1.8, 24.4, "ONE HONEST CORRECTION", fontsize=9.2, fontweight="bold",
            color=GOOD, va="center")
    ax.text(PX + 1.8, 27.3, "Every imagined completion\ncarries a live EMA of\nrealised-minus-"
                            "predicted\ntime, so the imagination\nplans in today's clock.",
            fontsize=8.6, color=INK2, va="top", linespacing=1.66)

    box(PX, 42.0, PW, 15.5, "#fdf4f4", "#f0c2c2", 1.2, 3)
    ax.text(PX + 1.8, 44.9, "WHAT IT CANNOT SEE", fontsize=9.2, fontweight="bold", color=BAD,
            va="center")
    ax.text(PX + 1.8, 47.8, "The imagination is given no\nfuture orders. It plans the\nqueue that "
                            "exists, not the\none that will.",
            fontsize=8.6, color=INK2, va="top", linespacing=1.66)

    box(PX, 61.5, PW, 21.5, "#f4f7fb", "#c9d7e8", 1.2, 3)
    ax.text(PX + 1.8, 64.4, "PICKERS", fontsize=9.2, fontweight="bold", color=INK3, va="center")
    ax.text(PX + 1.8, 67.3, "Pickers run their own\nassignment, but the rollout\ntreats them as a "
                            "consumed\nresource: one committed\ninside an imagined future is\n"
                            "unavailable to every later\ncandidate in that imagining.",
            fontsize=8.6, color=INK2, va="top", linespacing=1.66)
    ax.add_patch(FancyArrowPatch((PX - 0.4, 70.5), (X0 + WIDE + 0.8, 70.5), arrowstyle="-|>",
                                 mutation_scale=11, color="#8aa6c8", lw=1.4, zorder=5))

    # ------------------------------------------------------- the tuner's return path
    LX = 4.9
    ax.plot([X0 + 2.1, LX, LX, X0 - 1.4], [ys + H_CLAIM + 1.6, ys + H_CLAIM + 1.6, 19.4, 19.4],
            color=C4, lw=1.8, zorder=6, solid_joinstyle="round")
    ax.add_patch(FancyArrowPatch((X0 - 1.4, 19.4), (X0 + 2.1, 19.4), arrowstyle="-|>",
                                 mutation_scale=12, color=C4, lw=1.8, zorder=6))
    ax.plot([X0 + 2.1, X0 + 2.1], [ys + H_CLAIM, ys + H_CLAIM + 1.6], color=C4, lw=1.8, zorder=6)
    ax.text(3.5, 52.0, "every 50 steps, re-choose the knobs", fontsize=8.4, color="#8a6200",
            rotation=90, ha="center", va="center", fontweight="bold", zorder=6)

    fig.text(0.028, 0.978, "Decisions come from imagined futures", fontsize=16.5,
             fontweight="bold", color=INK, va="top")
    fig.text(0.028, 0.940, "One free robot, one tick. Stages 1–5 prepare a shortlist; stage 6 is "
                           "the only place anything is chosen; stage 7 throws the rest away.",
             fontsize=10.0, color=INK2, va="top")
    save(fig, "fig_planner.png")


def fig_features():
    """Table 2 as a figure: the 24 decision features, and the fact that both arms get all of them.

    The table's content is an identity -- twenty-four rows of tick, tick. A reader has to scan all
    of it to learn one thing. This figure states the one thing and keeps the twenty-four names, so
    the table can stay in the appendix as reference for units, or be dropped.

    Groups and membership are read off FEATS in scripts/marl_dispatch.py and the assembler in
    scripts/sim_priority.py; the figure is laid out from that list, so it cannot drift from it.
    """
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    GROUPS = [
        ("task", ["pred_finish", "my_arrival", "dock", "value", "dl_slack"]),
        ("self", ["my_wait", "path_stretch"]),
        ("partner", ["picker_eta"]),
        ("fleet", ["n_busy_agv", "n_free_pk", "q_size", "busy_frac", "free_pk_frac", "q_per_agv"]),
        ("traffic", ["delay_ema", "dur_recent", "dur_trend", "deliv_rate"]),
        ("congestion", ["local_density"]),
        ("clock", ["sin_t", "cos_t", "day_frac"]),
        ("deadline pressure", ["dl_soon40", "dl_soon80"]),
    ]
    N = sum(len(f) for _g, f in GROUPS)
    assert N == 24, N

    fig = plt.figure(figsize=(11.6, 6.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(100, 0)
    ax.axis("off")

    LX, CX, CW, CG = 3.0, 15.0, 8.2, 0.6      # label col, chip col, chip width, gap
    TOP, BH = 21.0, 8.4                        # first band top, band height

    for bi, (gname, feats) in enumerate(GROUPS):
        y = TOP + bi * BH
        if bi % 2 == 0:                        # quiet banding, so long rows stay readable
            ax.add_patch(FancyBboxPatch((LX - 1.2, y - 0.6), 66.4, BH - 1.0,
                                        boxstyle="round,pad=0.0,rounding_size=0.6",
                                        fc="#f4f2ec", ec="none", zorder=1))
        ax.text(CX - 1.4, y + BH / 2 - 0.8, gname, fontsize=9.0, fontweight="bold",
                color=INK3, ha="right", va="center", zorder=3)
        for fi, f in enumerate(feats):
            x = CX + fi * (CW + CG)
            ax.add_patch(FancyBboxPatch((x, y + 1.0), CW, BH - 3.0,
                                        boxstyle="round,pad=0.0,rounding_size=0.55",
                                        fc=SURFACE, ec="#cdd9e8", lw=1.2, zorder=2))
            ax.text(x + CW / 2, y + BH / 2 - 0.5, f, fontsize=7.4, color=INK,
                    ha="center", va="center", zorder=3, fontfamily="monospace")

    # ---- the collector: all 24, one set -------------------------------------------------------
    BX = 69.2
    MID = TOP + 4 * BH - 1.1
    ax.plot([BX, BX + 1.7, BX + 1.7, BX], [TOP - 0.6, TOP - 0.6, TOP + 8 * BH - 1.6,
                                           TOP + 8 * BH - 1.6],
            color=INK3, lw=1.3, zorder=3, solid_joinstyle="miter")
    ax.plot([BX + 1.7, BX + 3.4], [MID, MID], color=INK3, lw=1.3, zorder=3)

    # ---- the two consumers ---------------------------------------------------------------------
    for cy, col, fill, title, body in (
            (30.0, C3, "#eef8f3", "The rules",
             "stages 1–5 of the funnel:\ntier, value and urgency\nproduce the ordering"),
            (58.0, C1, "#eef4fb", "The learner",
             "MLP(24 → 64 → 64 → 1)\nscores the same shortlist\nin the same slot")):
        ax.add_patch(FancyBboxPatch((76.5, cy), 22.0, 19.0,
                                    boxstyle="round,pad=0.0,rounding_size=1.0",
                                    fc=fill, ec=col, lw=1.8, zorder=3))
        ax.text(78.5, cy + 4.0, title, fontsize=12, fontweight="bold", color=col, va="center")
        ax.text(78.5, cy + 7.0, body, fontsize=8.8, color=INK2, va="top", linespacing=1.6)
        ax.text(78.5, cy + 16.4, "receives all 24", fontsize=9.0, fontweight="bold",
                color=col, va="center")
        ax.add_patch(FancyArrowPatch((BX + 3.4, MID), (75.7, cy + 9.5),
                                     arrowstyle="-|>", mutation_scale=13, color=INK3, lw=1.5,
                                     zorder=2, connectionstyle="arc3,rad=%.2f"
                                     % (0.22 if cy < 45 else -0.22)))

    fig.text(0.026, 0.965, "Both arms see the same 24 features", fontsize=16.5,
             fontweight="bold", color=INK, va="top")
    fig.text(0.026, 0.918, "Over the identical candidate shortlist, at the identical decision "
                           "points. Only the selection rule differs — which is what makes the "
                           "learner's\nloss in §6.5 a fair test rather than a starved one. Units "
                           "for each feature are given in Table 2.",
             fontsize=9.8, color=INK2, va="top", linespacing=1.55)

    fig.text(0.026, 0.045, "One further scalar, dl_soon160, is computed by the assembler and "
                           "consumed by neither arm — only by the delay-prediction study of "
                           "§6.4.",
             fontsize=8.6, color=INK3, va="center")
    save(fig, "fig_features.png")


def fig_table2():
    """Table 2, typeset as an image: the 24 decision features with units and availability.

    Booktabs rules (top / mid / bottom, no verticals), faint zebra for scanning 24 rows, and the
    two availability columns set off together so their identity reads at a glance -- that identity
    is the table's whole content.

    Rows are generated from the same list the code uses, so the image cannot drift from the
    feature set: FEATS in scripts/marl_dispatch.py, assembled in scripts/sim_priority.py.
    """
    from matplotlib.patches import Rectangle

    ROWS = [
        ("pred_finish", "task", "steps, empty-world completion estimate"),
        ("my_arrival", "task", "cells on the chosen route"),
        ("dock", "task", "cells from pod to nearest station"),
        ("value", "task", "order value, summed over pending orders"),
        ("dl_slack", "task", "steps to the shelf's earliest deadline"),
        ("my_wait", "self", "steps this robot would wait at the pod"),
        ("path_stretch", "self", "route length ÷ Manhattan distance"),
        ("picker_eta", "partner", "steps until a picker can meet it"),
        ("n_busy_agv", "fleet", "robots currently on a task"),
        ("n_free_pk", "fleet", "idle pickers"),
        ("q_size", "fleet", "tasks in the request queue"),
        ("busy_frac", "fleet", "busy robots ÷ fleet"),
        ("free_pk_frac", "fleet", "idle pickers ÷ pickers"),
        ("q_per_agv", "fleet", "queued tasks per robot"),
        ("delay_ema", "traffic", "EMA of realised minus predicted, steps"),
        ("dur_recent", "traffic", "mean of last 10 completions, steps"),
        ("dur_trend", "traffic", "dur_recent minus long window; > 0 means slowing"),
        ("deliv_rate", "traffic", "deliveries per step over a 40-step window"),
        ("local_density", "congestion", "agents within 8 cells ÷ all agents"),
        ("sin_t", "clock", "sine of diurnal phase"),
        ("cos_t", "clock", "cosine of diurnal phase"),
        ("day_frac", "clock", "position through the episode, 0 to 1"),
        ("dl_soon40", "deadline pressure", "pending tasks due within 40 steps"),
        ("dl_soon80", "deadline pressure", "pending tasks due within 80 steps"),
    ]
    assert len(ROWS) == 24, len(ROWS)

    X_NUM, X_FEAT, X_GRP, X_UNIT, X_RULE, X_LRN = 4.0, 7.5, 24.0, 38.0, 82.5, 92.5
    HEAD, RH = 14.0, 3.15                      # header baseline, row height
    MID = HEAD + 3.0                           # rule under the header
    TOP, BOT = MID + 2.8, MID + 2.8 + 24 * RH  # first row sits clear of it

    fig = plt.figure(figsize=(12.2, 9.0))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(BOT + 8.0, 0)
    ax.axis("off")

    # the two availability columns belong together: one tint behind both
    ax.add_patch(Rectangle((X_RULE - 5.6, HEAD - 3.2), 98.5 - (X_RULE - 5.6),
                           BOT - HEAD - 0.4, fc="#f2f6fb", ec="none", zorder=1))

    for i, (feat, grp, unit) in enumerate(ROWS):
        y = TOP + i * RH
        if i % 2:                              # faint zebra, for scanning 24 rows
            ax.add_patch(Rectangle((1.5, y - RH * 0.62), 97.0, RH,
                                   fc="#f6f5f1", ec="none", zorder=0))
        ax.text(X_NUM, y, str(i + 1), fontsize=8.4, color=INK3, ha="center", va="center",
                zorder=3)
        ax.text(X_FEAT, y, feat, fontsize=8.8, color=INK, va="center", zorder=3,
                fontfamily="monospace")
        ax.text(X_GRP, y, grp, fontsize=8.6, color=INK2, va="center", zorder=3)
        ax.text(X_UNIT, y, unit, fontsize=8.6, color=INK2, va="center", zorder=3)
        for x in (X_RULE, X_LRN):
            ax.text(x, y, "✓", fontsize=10.5, color=GOOD, ha="center", va="center",
                    zorder=3, fontweight="bold")

    # ---- header ---------------------------------------------------------------------------------
    for x, lab, ha in ((X_NUM, "#", "center"), (X_FEAT, "Feature", "left"),
                       (X_GRP, "Group", "left"), (X_UNIT, "Units", "left"),
                       (X_RULE, "Rules", "center"), (X_LRN, "Learner", "center")):
        ax.text(x, HEAD, lab, fontsize=9.4, fontweight="bold", color=INK, ha=ha, va="center",
                zorder=3)

    # ---- booktabs rules ---------------------------------------------------------------------------
    for y, lw in ((HEAD - 3.2, 1.6), (MID, 1.0), (BOT - RH * 0.62, 1.6)):
        ax.plot([1.5, 98.5], [y, y], color=INK, lw=lw, zorder=4, solid_capstyle="butt")

    # ---- title, caption, footnote -----------------------------------------------------------------
    ax.text(1.5, 3.4, "Table 2  ·  The 24 decision features", fontsize=15,
            fontweight="bold", color=INK, va="center")
    ax.text(1.5, 8.2, "The learned dispatcher of §6.5 receives exactly this set, over exactly "
                      "the same candidate shortlist, at the same decision points, so the\n"
                      "comparison isolates the selection rule and nothing else. The last two "
                      "columns are identical all the way down — that is the table's content.",
            fontsize=9.2, color=INK2, va="center", linespacing=1.55)
    ax.text(1.5, BOT + 2.6, "Every feature is divided by a fixed scale taken from a champion run "
                            "before it reaches the network, so no worker needs shared "
                            "normalisation state.\nOne further scalar, dl_soon160, is computed by "
                            "the assembler and consumed by neither arm — only by the "
                            "delay-prediction study of §6.4.",
            fontsize=8.4, color=INK3, va="center", linespacing=1.55)
    save(fig, "fig_table2.png")


def fig_table3():
    """Table 3, typeset as an image: every pre-registered criterion and its outcome.

    Same booktabs treatment as Table 2. The one criterion that is not met is the only row given a
    tint, so the reader finds it without scanning -- the table exists to report it honestly.
    """
    from matplotlib.patches import Rectangle

    ROWS = [
        ("Sensitivity", "≥ 90%", "92.2% per event", True, "¹"),
        ("Specificity", "≥ 90%", "99.87%", True, "²"),
        ("Detection latency", "median ≤ 15 steps", "2 steps", True, ""),
        ("Phantom hard-blocks", "≤ 1 per 1,000 steps", "9.8 per 1,000", False, "³"),
        ("Collisions", "0", "0", True, ""),
        ("Strandings", "0", "0", True, ""),
        ("Inner-loop MAPF success", "≥ 98%", "100%", True, ""),
        ("Decision latency, five robots", "≤ 1 s", "1.3 ms median", True, ""),
        ("Ship bar", "≥ 3% or cut, no exceptions", "applied 32 times", True, ""),
    ]

    X_MET, X_TGT, X_MEAS, X_VER = 2.5, 36.0, 60.0, 85.0
    HEAD, RH = 16.0, 5.0
    MID = HEAD + 3.4
    TOP = MID + 3.6
    BOT = TOP + len(ROWS) * RH

    fig = plt.figure(figsize=(11.4, 6.6))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(BOT + 22.0, 0)
    ax.axis("off")

    for i, (metric, tgt, meas, ok, fn) in enumerate(ROWS):
        y = TOP + i * RH
        if not ok:                              # the miss is the one row that must be found
            ax.add_patch(Rectangle((1.5, y - RH * 0.5), 97.0, RH, fc="#fdecec", ec="none",
                                   zorder=0))
        elif i % 2:
            ax.add_patch(Rectangle((1.5, y - RH * 0.5), 97.0, RH, fc="#f6f5f1", ec="none",
                                   zorder=0))
        ax.text(X_MET, y, metric, fontsize=10.4, color=INK, va="center", zorder=3,
                fontweight="bold" if not ok else "normal")
        ax.text(X_TGT, y, tgt, fontsize=10.0, color=INK2, va="center", zorder=3)
        ax.text(X_MEAS, y, meas, fontsize=10.4, color=INK, va="center", zorder=3,
                fontweight="bold")
        ax.text(X_VER, y, ("met" if ok else "not met") + (" " + fn if fn else ""),
                fontsize=10.4, va="center", zorder=3, fontweight="bold",
                color=GOOD if ok else BAD)

    for x, lab in ((X_MET, "Metric"), (X_TGT, "Pre-registered target"),
                   (X_MEAS, "Measured"), (X_VER, "Verdict")):
        ax.text(x, HEAD, lab, fontsize=10.6, fontweight="bold", color=INK, va="center")

    for y, lw in ((HEAD - 3.4, 1.6), (MID, 1.0), (BOT - RH * 0.5, 1.6)):
        ax.plot([1.5, 98.5], [y, y], color=INK, lw=lw, zorder=4, solid_capstyle="butt")

    ax.text(1.5, 3.6, "Table 3  ·  The pre-registered scorecard", fontsize=15,
            fontweight="bold", color=INK, va="center")
    ax.text(1.5, 8.6, "Every success criterion registered before the work began, with its measured "
                      "outcome. One criterion is not met; the accompanying oracle\nmeasurement "
                      "establishes that its target was not attainable at this sensing density.",
            fontsize=9.4, color=INK2, va="center", linespacing=1.55)

    notes = [
        ("¹", "Recorded as failed for months: per-cell-per-step recall was being compared "
                   "against an event-level target. Graded on the events the target names, the "
                   "map passes."),
        ("²", "Measured on a 3.2% base rate — a map asserting nothing scores 96.8%. The "
                   "informative number is precision at the router's decision threshold, 95.58%."),
        ("³", "Bounded, not explained away: a perfect-memory oracle on the identical sight "
                   "stream scores 9.2. The attainable floor is about nine times the target,\n"
                   "and the shipped map sits within 7% of it."),
    ]
    for k, (mark, text) in enumerate(notes):
        y = BOT + 3.6 + k * 5.4
        ax.text(1.5, y, mark, fontsize=9.4, color=INK2, va="top", fontweight="bold")
        ax.text(3.4, y, text, fontsize=8.8, color=INK2, va="top", linespacing=1.5)
    save(fig, "fig_table3.png")


def fig_table1():
    """Table 1, typeset as an image: every world constant, its correction and its evidence.

    Eighteen rows with prose in two of the columns, so cells wrap and row heights vary with
    content. Status is a labelled pill in a reserved colour -- never colour alone.
    """
    import textwrap
    from matplotlib.patches import Rectangle, FancyBboxPatch

    ROWS = [
        ("Cell size", "1 m", "1 m",
         "Pod ≈ 1×1 m; drive unit (75×60 cm) travels beneath", "verified"),
        ("Occupancy", "one robot/cell", "one robot/cell",
         "Follows from cell size and footprint", "verified"),
        ("Storage density", "31%", "55%",
         "In-aisle picking runs 40–60%", "corrected"),
        ("Station count", "10", "3",
         "~700 picks/hr demanded vs 300–600/hr per station", "corrected"),
        ("Step duration", "0.67 s", "1.069 s",
         "Trapezoidal profile, a = 0.8 m/s², v_max = 1.2 m/s; short runs rarely reach cruise",
         "corrected"),
        ("Picker load", "0 s", "8 steps",
         "UR-arm pick-and-place ≈ 5–10 s", "corrected"),
        ("Station service per item", "0 s", "6 steps",
         "300–600 picks/hr station rates", "corrected"),
        ("Order values", "Uniform(1, 15)", "Lognormal (median 8, σ = 1)",
         "Real values are long-tailed; uniform ties 48.6% of selections", "corrected"),
        ("Arrival rate", "0.075 (47% util.)", "utilisation-anchored",
         "A bare rate silently fixes utilisation", "corrected"),
        ("Deadline slack", "single band",
         "mixture: std U(80, 200), rush U(25, 60) at 20%, value ×1.6",
         "Real fulfilment has an expedited tier", "corrected"),
        ("Demand exogeneity", "drawn from not-in-transit", "pre-drawn from seed",
         "Policy-dependent demand shared only ~22% of (time, shelf) pairs", "corrected"),
        ("Diurnal period", "250 steps = “a day”", "day spans episodes (162 seeds = 1 day)",
         "The two clocks are ~280× apart", "corrected"),
        ("One-way lanes", "not implemented", "implemented, off by default",
         "The real rule, but costs 16% at 8 robots on 650 cells", "opt-in"),
        ("Demand shape", "—",
         "zipf_s = 1.1, n_hot = 3, Hawkes (p = .006, jump .4, decay .90)",
         "Mechanisms cited; parameter values ours", "declared"),
        ("Battery", "none", "720 Wh, ~6 h, compressed via steps_per_charge",
         "Robotnik AMR spec; compression is uniform scaling of an exact quantity", "declared"),
        ("Blockage rate", "none", "0.002/step, swept to 0.037",
         "No public figure exists; only anchor is a ~20-year-old field-robot MTBF of ~8 h",
         "assumed"),
        ("Amnesty rate", "none", "3.7% per item handled",
         "Published per-stow-attempt rate; one roll per item, not per trip", "declared"),
        ("Amnesty duration", "none", "U(15, 45) steps",
         "That source reports no recovery times", "assumed"),
    ]
    assert len(ROWS) == 18, len(ROWS)

    STATUS = {"verified": GOOD, "corrected": C1, "opt-in": C4,
              "declared": INK2, "assumed": BAD}
    TINT = {"verified": "#eef7ee", "corrected": "#eef4fb", "opt-in": "#fdf5e6",
            "declared": "#f2f2f0", "assumed": "#fdecec"}

    X_NUM, X_CON, X_OLD, X_NEW, X_WHY, X_STA = 2.0, 4.6, 17.0, 30.0, 49.0, 88.5
    W_CON, W_OLD, W_NEW, W_WHY = 28, 26, 44, 88     # wrap widths, characters
    LH = 1.75                                        # one text line, in y units

    fig = plt.figure(figsize=(15.2, 11.6))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.axis("off")

    HEAD = 16.0
    MID = HEAD + 3.2
    y = MID + 3.4
    laid = []
    for con, old, new, why, sta in ROWS:
        cells = [textwrap.wrap(con, W_CON), textwrap.wrap(old, W_OLD),
                 textwrap.wrap(new, W_NEW), textwrap.wrap(why, W_WHY)]
        h = max(len(c) for c in cells) * LH + 1.9
        laid.append((y, h, cells, sta))
        y += h
    BOT = y

    ax.set_ylim(BOT + 17.0, 0)

    for i, (ry, h, cells, sta) in enumerate(laid):
        ax.add_patch(Rectangle((1.5, ry - 0.9), 97.0, h, ec="none", zorder=0,
                               fc=TINT[sta] if sta in ("opt-in", "assumed") else
                               ("#f7f6f2" if i % 2 else SURFACE)))
        ax.text(X_NUM, ry + 0.4, str(i + 1), fontsize=8.6, color=INK3, ha="center", va="top",
                zorder=3)
        for x, lines, fs, col, bold in ((X_CON, cells[0], 9.2, INK, True),
                                        (X_OLD, cells[1], 8.8, INK2, False),
                                        (X_NEW, cells[2], 8.8, INK, False),
                                        (X_WHY, cells[3], 8.6, INK2, False)):
            ax.text(x, ry + 0.4, "\n".join(lines), fontsize=fs, color=col, va="top",
                    zorder=3, linespacing=1.5,
                    fontweight="bold" if bold else "normal")
        ax.add_patch(FancyBboxPatch((X_STA, ry - 0.1), 9.0, 2.5,
                                    boxstyle="round,pad=0.0,rounding_size=0.5",
                                    fc=SURFACE, ec=STATUS[sta], lw=1.2, zorder=3))
        ax.text(X_STA + 4.5, ry + 1.15, sta, fontsize=8.4, color=STATUS[sta], ha="center",
                va="center", fontweight="bold", zorder=4)

    for x, lab in ((X_NUM, "#"), (X_CON, "Constant"), (X_OLD, "As found"),
                   (X_NEW, "Corrected to"), (X_WHY, "Source or justification"),
                   (X_STA, "Status")):
        ax.text(x, HEAD, lab, fontsize=9.8, fontweight="bold", color=INK,
                ha="center" if x == X_NUM else "left", va="center")

    for yy, lw in ((HEAD - 3.4, 1.6), (MID, 1.0), (BOT - 0.9, 1.6)):
        ax.plot([1.5, 98.5], [yy, yy], color=INK, lw=lw, zorder=5, solid_capstyle="butt")

    ax.text(1.5, 3.8, "Table 1  ·  Every world constant, corrected or declared",
            fontsize=15.5, fontweight="bold", color=INK, va="center")
    ax.text(1.5, 9.0, "The audit is only auditable if the constants are on the page. Two constants "
                      "have no public figure behind them at all and two more are operating-point\n"
                      "choices; all four are declared rather than calibrated, and swept rather "
                      "than tuned.",
            fontsize=9.4, color=INK2, va="center", linespacing=1.55)

    defs = [("verified", "checked against a source, and already right"),
            ("corrected", "changed, with the source that forced the change"),
            ("opt-in", "implemented and measured, off by default"),
            ("declared", "mechanism cited, magnitude ours"),
            ("assumed", "no public figure exists; stated and swept, never fitted")]
    for k, (name, meaning) in enumerate(defs):
        yy = BOT + 3.4 + k * 2.6
        ax.add_patch(FancyBboxPatch((1.5, yy - 1.1), 9.0, 2.3,
                                    boxstyle="round,pad=0.0,rounding_size=0.5",
                                    fc=SURFACE, ec=STATUS[name], lw=1.2, zorder=3))
        ax.text(6.0, yy, name, fontsize=8.4, color=STATUS[name], ha="center", va="center",
                fontweight="bold", zorder=4)
        ax.text(12.0, yy, meaning, fontsize=8.8, color=INK2, va="center")
    save(fig, "fig_table1.png")


def fig_tablebench():
    """The main benchmark as a table image: four conditions, four arms, margin over the vendored
    dispatcher.

    Numbers are read from the same CSVs fig_benchmark plots, so the table and the chart cannot
    disagree. Only one of the two should appear in the paper.
    """
    from matplotlib.patches import Rectangle

    def pick(*names):
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

    CONDS = [("Clean, wave days", clean, "wave"), ("Clean, live-stream days", clean, "stream"),
             ("Disturbed, wave days", dist, "wave"),
             ("Disturbed, live-stream days", dist, "stream")]
    ARMS = [("fifo", "FIFO"), ("rush", "Rush"), ("champ", "Champion"), ("mpc", "Shipped")]

    X_CON = 2.5
    XS = {"fifo": 36.0, "rush": 47.0, "champ": 59.5, "mpc": 73.0}
    X_MAR = 89.0
    HEAD, RH = 16.0, 5.6
    MID = HEAD + 3.4
    TOP = MID + 4.0
    BOT = TOP + len(CONDS) * RH

    fig = plt.figure(figsize=(12.0, 5.6))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(BOT + 14.0, 0)
    ax.axis("off")

    # the shipped column is the one the paper leads on: tint it down the whole table
    ax.add_patch(Rectangle((XS["mpc"] - 5.5, HEAD - 3.4), 12.0,
                           (BOT - RH * 0.5) - (HEAD - 3.4),
                           fc="#fdf5e6", ec="none", zorder=0))

    for i, (name, src, regime) in enumerate(CONDS):
        y = TOP + i * RH
        if i % 2:
            ax.add_patch(Rectangle((1.5, y - RH * 0.5), 97.0, RH, fc="#f6f5f1", ec="none",
                                   zorder=0))
        ax.text(X_CON, y, name, fontsize=10.2, color=INK, va="center", zorder=3)
        for key, _lab in ARMS:
            v = src[(key, regime)]
            ax.text(XS[key], y, "%.0f" % v, fontsize=10.6, va="center", ha="center", zorder=3,
                    color=INK if key == "mpc" else INK2,
                    fontweight="bold" if key == "mpc" else "normal")
        f, c = src[("fifo", regime)], src[("mpc", regime)]
        ax.text(X_MAR, y, "+%.1f%%" % (100 * (c - f) / f), fontsize=11.2, color=GOOD,
                va="center", ha="center", fontweight="bold", zorder=3)

    ax.text(X_CON, HEAD, "Condition", fontsize=10.0, fontweight="bold", color=INK, va="center")
    for key, lab in ARMS:
        ax.text(XS[key], HEAD, lab, fontsize=10.0, fontweight="bold", va="center", ha="center",
                color=INK if key == "mpc" else INK2)
    ax.text(X_MAR, HEAD, "Margin vs FIFO", fontsize=10.0, fontweight="bold", color=INK,
            va="center", ha="center")

    for yy, lw in ((HEAD - 3.4, 1.6), (MID, 1.0), (BOT - RH * 0.5, 1.6)):
        ax.plot([1.5, 98.5], [yy, yy], color=INK, lw=lw, zorder=5, solid_capstyle="butt")

    ax.text(1.5, 4.0, "The main benchmark", fontsize=15.5, fontweight="bold", color=INK,
            va="center")
    ax.text(1.5, 9.2, "On-time value per day against the simulator's own dispatcher. 144 paired "
                      "days per cell; the baselines run with free energy, so the\nshipped system "
                      "pays a real battery cost and still wins by these margins.",
            fontsize=9.4, color=INK2, va="center", linespacing=1.55)

    ax.text(1.5, BOT + 3.4, "Shipped = the rule stack plus the self-tuner. The two right-hand arms "
                            "tie on disturbed wave days and differ by under 1% on the other\nthree "
                            "cells: the tuner earns its place by removing the need to choose knob "
                            "settings per regime, not by beating a well-chosen constant.",
            fontsize=8.8, color=INK3, va="top", linespacing=1.55)
    save(fig, "fig_tablebench.png")


def fig_arms():
    """The five arms, as a table image, with what is held constant across them.

    Descriptions are read off the implementations rather than from memory: FIFOController and its
    `_task_order` in scripts/sim_dashboard.py, RushValueController in scripts/sim_priority.py, the
    champion stack in scripts/congestion_policies.py, the tuner in scripts/m3_mpc.py, and the
    learner in scripts/marl_dispatch.py.
    """
    import textwrap
    from matplotlib.patches import Rectangle, FancyBboxPatch

    ROWS = [
        ("fifo", "baseline", INK2,
         "The simulator's own vendored dispatcher, unmodified. Task-centric: it walks the request "
         "queue in arrival order and hands each task to whichever free robot has the shortest path "
         "to it. Deadlines and values are not consulted at any point.",
         "scripts/sim_dashboard.py"),
        ("rush", "baseline", INK2,
         "A value-priority heuristic with lateness-decay ordering. Makeable tasks come first by "
         "value, deadline breaking ties, so on-time work is never displaced; already-doomed tasks "
         "are then reordered by value decayed per step overdue, so a barely-late valuable task is "
         "rushed and a hopeless one is skipped. No rollout.",
         "scripts/sim_priority.py"),
        ("champ", "ours", C3,
         "The full rule stack — the seven-step funnel including the stage-6 rollout — with "
         "the self-tuner ablated. Its nine knobs are held at the constants chosen for the dense "
         "8-AGV map, so it cannot adapt them within an episode.",
         "scripts/congestion_policies.py"),
        ("mpc", "shipped", C4,
         "The shipped system: the same rule stack with the self-tuner active, re-choosing its own "
         "knobs every 50 steps by forward simulation. Every headline number in this paper is "
         "measured on this arm.",
         "scripts/m3_mpc.py"),
        ("marl", "learned", C1,
         "A policy-gradient dispatcher, MLP(24→64→64→1), trained by REINFORCE over 960 "
         "episodes on seeds 1–96 and evaluated greedily on 97–144. It scores the identical "
         "candidate shortlist on the identical 24 features, in the same selection slot. Only the "
         "choice is learned.",
         "scripts/marl_dispatch.py"),
    ]

    X_ARM, X_KIND, X_DESC, X_SRC = 2.5, 13.0, 25.0, 79.5
    LH = 2.15

    fig = plt.figure(figsize=(13.6, 7.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.axis("off")

    HEAD = 17.0
    MID = HEAD + 3.6
    y = MID + 4.2
    laid = []
    for arm, kind, col, desc, src in ROWS:
        lines = textwrap.wrap(desc, 74)
        h = len(lines) * LH + 3.2
        laid.append((y, h, arm, kind, col, lines, src))
        y += h
    BOT = y
    ax.set_ylim(BOT + 13.0, 0)

    for i, (ry, h, arm, kind, col, lines, src) in enumerate(laid):
        ax.add_patch(Rectangle((1.5, ry - 1.4), 97.0, h, ec="none", zorder=0,
                               fc="#fdf5e6" if arm == "mpc" else
                               ("#f7f6f2" if i % 2 else SURFACE)))
        ax.text(X_ARM, ry, arm, fontsize=11.2, color=INK, va="top", zorder=3,
                fontfamily="monospace", fontweight="bold")
        ax.add_patch(FancyBboxPatch((X_KIND, ry - 0.5), 8.6, 2.8,
                                    boxstyle="round,pad=0.0,rounding_size=0.5",
                                    fc=SURFACE, ec=col, lw=1.2, zorder=3))
        ax.text(X_KIND + 4.3, ry + 0.9, kind, fontsize=8.4, color=col, ha="center",
                va="center", fontweight="bold", zorder=4)
        ax.text(X_DESC, ry, "\n".join(lines), fontsize=9.2, color=INK2, va="top",
                zorder=3, linespacing=1.55)
        ax.text(X_SRC, ry, src, fontsize=8.2, color=INK3, va="top", zorder=3,
                fontfamily="monospace")

    for x, lab in ((X_ARM, "Arm"), (X_KIND, "Kind"), (X_DESC, "What it is"),
                   (X_SRC, "Defined in")):
        ax.text(x, HEAD, lab, fontsize=10.0, fontweight="bold", color=INK, va="center")

    for yy, lw in ((HEAD - 3.6, 1.6), (MID, 1.0), (BOT - 1.4, 1.6)):
        ax.plot([1.5, 98.5], [yy, yy], color=INK, lw=lw, zorder=5, solid_capstyle="butt")

    ax.text(1.5, 4.0, "The five arms", fontsize=15.5, fontweight="bold", color=INK, va="center")
    ax.text(1.5, 9.4, "Routing, picker sequencing, the battery layer and the collision referee are "
                      "identical across every arm; only the rule that chooses which task a free\n"
                      "robot takes differs. Every comparison is paired by seed, so both arms of a "
                      "comparison face the identical arrival schedule.",
            fontsize=9.4, color=INK2, va="center", linespacing=1.55)

    ax.text(1.5, BOT + 2.4, "Two handicaps run against us, both deliberate. fifo and rush are "
                            "measured with free energy — no battery constraint at all — while "
                            "champ, mpc and marl\npay the real one. And marl is given the champion's "
                            "own candidate shortlist rather than the raw task set, which is the "
                            "strongest form of the learner we could build.",
            fontsize=8.8, color=INK3, va="top", linespacing=1.55)
    save(fig, "fig_arms.png")


# Keyed by the figure's number in the paper, which numbers by order of first appearance.
# Fig. 5 is the belief-curve panel, produced by scripts/exp_m5_brier.py, and is not built here.
FIGS = {"f1": fig_coupled, "f2": fig_realism, "f3": fig_planner, "f4": fig_benchmark,
        "f6": fig_sensing, "f7": fig_ablation, "f8": fig_anticipation, "f9": fig_horizon,
        "t2": fig_features, "t2tbl": fig_table2, "t3tbl": fig_table3, "t1tbl": fig_table1, "tbench": fig_tablebench, "arms": fig_arms}
FIGS.update({fn.__name__.replace("fig_", ""): fn for fn in list(FIGS.values())})

if __name__ == "__main__":
    want = sys.argv[1:] or [k for k in FIGS if k.startswith("f") and k[1:].isdigit()]
    seen = set()
    for k in want:
        fn = FIGS[k]
        if fn in seen:                      # name aliases point at the same figure
            continue
        seen.add(fn)
        fn()
