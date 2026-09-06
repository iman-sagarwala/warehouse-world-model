"""Draw the champion's architecture as a downloadable PNG.

`_SqWidePkRateAdaptive` = wide sequencer (`_SqWide`) + value-rate pickers (`_VRPicker`)
                        + regime-conditional deadline weight.
Every number annotated here is measured, not assumed; sources are in docs/NOTES.md.
Boxes are AUTO-SIZED to their content so nothing overflows.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

W, H = 17.6, 15.6
FG, MUT = "#1d1d1f", "#63636a"
BLUE, BLUE_E = "#e9f1fb", "#2f6fb5"
TEAL, TEAL_E = "#e3f4ee", "#17845f"
AMB, AMB_E = "#fdf1dd", "#a86d0c"
RED, RED_E = "#fbeaea", "#a83a3a"
GREY, GREY_E = "#f3f2ee", "#8d8d88"

TITLE_DY, LINE_DY, PAD_TOP, PAD_BOT = 0.34, 0.255, 0.20, 0.20

fig, ax = plt.subplots(figsize=(W, H), dpi=170)
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
fig.patch.set_facecolor("white")


def bh(lines):
    return PAD_TOP + TITLE_DY + len(lines) * LINE_DY + PAD_BOT


def box(x, ytop, w, title, lines, fc, ec, tsz=10.6, lsz=8.7):
    h = bh(lines)
    y = ytop - h
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.10",
                                fc=fc, ec=ec, lw=1.35, zorder=2))
    ax.text(x + 0.18, ytop - PAD_TOP - 0.06, title, fontsize=tsz, color=FG,
            weight="medium", va="top", zorder=3)
    for i, ln in enumerate(lines):
        ax.text(x + 0.18, ytop - PAD_TOP - TITLE_DY - 0.02 - i * LINE_DY, ln,
                fontsize=lsz, color=MUT, va="top", zorder=3)
    return y


def stack(x, ytop, w, items, gap=0.30, arrows=True):
    y = ytop
    centers = []
    for (title, lines, fc, ec) in items:
        bot = box(x, y, w, title, lines, fc, ec)
        centers.append((y, bot))
        if arrows and (title, lines, fc, ec) != items[-1]:
            ax.add_patch(FancyArrowPatch((x + w / 2, bot), (x + w / 2, bot - gap + 0.04),
                                         arrowstyle="-|>", mutation_scale=12,
                                         color=GREY_E, lw=1.4, zorder=1))
        y = bot - gap
    return y, centers


ax.text(0.35, H - 0.40, "The champion — _SqWidePkRateAdaptive", fontsize=17.5, color=FG,
        weight="medium")
ax.text(0.35, H - 0.78, "wide sequencer  +  value-rate pickers  +  regime-conditional deadline "
                        "weight.    Every figure below is measured — sources in docs/NOTES.md",
        fontsize=9.7, color=MUT)

# ------------------------------- AGV column -------------------------------
X, BW = 0.35, 7.55
ax.text(X + 0.04, H - 1.24, "AGV   ·   runs whenever a robot frees up", fontsize=11.6,
        color=BLUE_E, weight="medium")

stack(X, H - 1.44, BW, [
    ("1 · cross off the impossible",
     ["already taken · already delivered · wrong robot type"], GREY, GREY_E),
    ("2 · cheap screen  →  keep the top 15",
     ["value − 0.15 × distance      SCREEN_KEEP = 15"], GREY, GREY_E),
    ("3 · Yen's k-shortest routes   (k = 3)",
     ["on the real graph — AGVs drive under shelves, so Manhattan is exact"], GREY, GREY_E),
    ("4 · pick a route  ·  congestion-aware",
     ["CONG_LAMBDA = 0.3   (never swept — predicted null, it is a SPACE knob)"], GREY, GREY_E),
    ("5 · price each candidate   —   PREP, NOT A DECISION",
     ["rendezvous = max(my arrival, picker ETA)  →  finish = rendezvous + pad + dock",
      "tiered:  makeable 1000 + value + URG_W·urgency   /   doomed value × 0.98^late",
      "this only ORDERS the shortlist and hands the first move's finish to the sim.",
      "It never chooses — see below. (pad = LOAD_TIME 5, a constant, not the EMA)"],
     GREY, GREY_E),
    ("6 · THE SEQUENCER  —  the ONLY decision point",
     ["simulate ALL 15 forward to min(now + SEQ_DEPTH·75, 500), argmax BANKED VALUE",
      "robots freed by an event heap · pickers consumed · deadlines re-priced per",
      "imagined task · THE ADAPTIVE DELAY-EMA applied to every completion",
      "SEQ_TOPK=99 (nothing dropped) · SCORE_TOL=inf (nothing filtered) · DEV_MARGIN=0",
      "⇒ step 5's score can never override the simulation. One ranking, not two.",
      "Switching this OFF costs −24.05 (−7.2%, t = −30.6) — the biggest lever"],
     TEAL, TEAL_E),
    ("7 · commit the FIRST MOVE ONLY",
     ["the imagined tail is thrown away; re-plan at the next free-up",
      "(receding horizon — estimate error never reaches the actions)"], AMB, AMB_E),
])

# ------------------------------ picker column ------------------------------
X2, BW2 = 8.30, 5.55
ax.text(X2 + 0.04, H - 1.24, "PICKER   ·   runs whenever a picker is free", fontsize=11.6,
        color=TEAL_E, weight="medium")

ybot, _ = stack(X2, H - 1.44, BW2, [
    ("1 · candidate rendezvous",
     ["AGVs already heading to a shelf, not yet claimed"], GREY, GREY_E),
    ("2 · Yen's on the PICKER graph",
     ["pickers use the highway network, not the AGV graph"], GREY, GREY_E),
    ("3 · value-rate score",
     ["tier  +  value / Tp ^ RATE_ALPHA        Tp = rendezvous + LOAD",
      "RATE_ALPHA = 5 — every alternative negative, a bracketed peak.",
      "High α ⇒ emergent Voronoi zoning (territories nobody assigned)"], TEAL, TEAL_E),
    ("4 · take the best   (no rollout)",
     ["and that is deliberate — see below"], AMB, AMB_E),
])

ybot = box(X2, ybot - 0.45, BW2, "why the picker side stays simple",
    ["86.9% of picker dispatches have only ONE candidate.",
     "You cannot re-rank a list of one — a picker sequencer",
     "can fire in at most 13% of decisions, and changed the",
     "outcome in 2 seeds out of 720.",
     "The picker limit is HEADCOUNT, not allocation:",
     "8×4 → 8×6 is worth +25 (+7.3%) — 3× any knob."], RED, RED_E)

box(X2, ybot - 0.45, BW2, "what the imagination does NOT know",
    ["• no future orders — `_future_arrivals` returns []",
     "   perfect demand foresight measures −3.4%, and no",
     "   horizon helps (a perfect 10-step forecast = −0.10)",
     "• no cell-level traffic — the delay-EMA is one scalar",
     "   for the whole fleet, not a per-route estimate",
     "• the pinned first move consumes no picker",
     "   (fixing that is worth +1.48 / −0.31, i.e. nothing)",
     "• W_SYNC(0.3)·my_wait is still in the score but is a",
     "   NULL knob — the wait is already inside `finish`",
     "",
     "You know your own agents — you command them.",
     "You must learn the world — you do not."], GREY, GREY_E)

# ------------------------------- right rail -------------------------------
X3, BW3 = 14.25, 3.0
yr = box(X3, H - 1.44, BW3, "EXECUTION · the env moves",
    ["• soft route adherence — find_path",
     "   hugs the committed route",
     "• detours around blockers",
     "• disturbances (opt-in) are",
     "   treated as obstacles",
     "",
     "M1 was tuned with disturbances",
     "OFF — disclosed, one revalidation",
     "planned after M2 + M3."], GREY, GREY_E)

yr = box(X3, yr - 0.45, BW3, "FROZEN KNOBS",
    ["URG_W                    0 / 8",
     "W_SYNC                     0.3",
     "RATE_ALPHA                   5",
     "SEQ_DEPTH                    5",
     "CONG_LAMBDA / WEIGHT       0.3",
     "LOAD_TIME                    5"], AMB, AMB_E)

box(X3, yr - 0.45, BW3, "HOW IT WAS MEASURED",
    ["120 paired seeds per cell",
     "72 fleet configs (AGV 4–9 × pk 4–9)",
     "two regimes: day-list / stream",
     "~200,000 runs across M1",
     "",
     "ships only if pooled |t| ≥ 3 AND",
     "≥80% stable over 200 resamples"], GREY, GREY_E)

out = os.path.join("results", "champion_architecture.png")
fig.savefig(out, facecolor="white", bbox_inches="tight")
print("wrote", out)
