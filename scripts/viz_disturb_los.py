"""Four-panel figure: exactly how disturbances + line-of-sight sensing work.

A: one robot's TRUE visible set on the real map (radius-5 rays, racks occlude; computed with the
   actual BetaRumorMap geometry).
B: debris physics mid-episode (blind fleet, until-amnesty): spilled cells, a robot stuck in one.
C: the fleet's belief map at the same instant: heat = P(disturbed); sighted vs unseen debris.
D: one debris cell's life: spawn -> sightings raise belief -> amnesty -> decay forgets.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

os.environ["M3SPC"] = "1500"
from record_race import build
from wwm_sim.rumor_map import BetaRumorMap

env, ctrl = build("large-8-6", 7)
env.disturb_rate = 0.03
env._disturb_rng = np.random.RandomState(777)
env.disturb_dur = (150, 400)
env.debris_hold_steps = -1
env.use_belief_routing = True
rm = BetaRumorMap(env.grid_size)
env.rumor_map = rm
env.b_hard = 1.1              # BLIND routing (so robots actually hit debris) but the map still learns
env.los_sensing = True
H, W = env.grid_size
hw = env.highways

# ---- run, recording what each panel needs ----
belief_hist = {}              # cell -> [belief per step]
snap = None
SNAP_T = 260
spawn_t, amnesty_t = {}, {}
prev_dist = set()
for t in range(400):
    env.step(ctrl.act())
    rm.update(env, line_of_sight=True)
    cur = set(getattr(env, "disturbed", ()))
    for c in cur - prev_dist:
        spawn_t[c] = t
    for c in prev_dist - cur:
        amnesty_t[c] = t
    prev_dist = cur
    b = rm.belief()
    for c in cur | set(belief_hist):
        belief_hist.setdefault(c, [0.5] * t).append(float(b[c[0], c[1]]))
    for c in belief_hist:
        if len(belief_hist[c]) < t + 1:
            belief_hist[c].append(float(b[c[0], c[1]]))
    if t == SNAP_T:
        snap = dict(
            disturbed=set(cur),
            belief=b.copy(),
            agents=[(a.x, a.y, a.type.name if hasattr(a.type, "name") else str(a.type),
                     bool(getattr(a, "_debris_stuck", False)),
                     getattr(a, "carrying_shelf", None) is not None) for a in env.agents])

storage = {(x, y) for (y, x) in env.action_id_to_coords_map.values()}
goals = {tuple(g) for g in env.goals}
bays = set(env._charger_bays)

# ---- exact LOS set for one robot (same geometry as BetaRumorMap.update) ----
# pick a highway cell mid-map automatically (aisle junction area)
rob = None
for yy in range(10, 16):
    for xx in range(6, 12):
        if hw[yy, xx]:
            rob = (xx, yy)
            break
    if rob:
        break
assert rob is not None
visible = {(rob[0], rob[1])}
r = rm.sight_radius
for (dy, dx), between in rm._los_table():
    y, x = rob[1] + dy, rob[0] + dx
    if not (0 <= y < H and 0 <= x < W):
        continue
    if any(0 <= rob[1] + by < H and 0 <= rob[0] + bx < W and not hw[rob[1] + by, rob[0] + bx]
           for (by, bx) in between):
        continue
    visible.add((x, y))

RACK, AISLE, VIS, OCC, DEBRIS, STA = "#c9a26b", "#f4f1ea", "#9fd7f0", "#6f675c", "#1a1a1a", "#2e6f95"


def base(ax, title):
    for y in range(H):
        for x in range(W):
            if (x, y) in goals:
                fc = STA
            elif (x, y) in storage:
                fc = "#eee3cd" if (x, y) in bays else RACK
            else:
                fc = AISLE
            ax.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor=fc,
                                            edgecolor="white", lw=0.4))
    ax.set_xlim(-0.6, W - 0.4)
    ax.set_ylim(H - 0.4, -0.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=10)


fig, axes = plt.subplots(2, 2, figsize=(13.5, 15))
axA, axB, axC, axD = axes[0][0], axes[0][1], axes[1][0], axes[1][1]

# ---------- A: line of sight ----------
base(axA, "A — line of sight (radius 5, racks block the ray)")
for (x, y) in visible:
    if (x, y) != rob:
        ax_fc = VIS
        axA.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor=ax_fc,
                                         edgecolor="white", lw=0.4, alpha=0.85))
occluded = [(rob[0] + dx, rob[1] + dy) for (dy, dx), _ in rm._los_table()
            if 0 <= rob[1] + dy < H and 0 <= rob[0] + dx < W
            and (rob[0] + dx, rob[1] + dy) not in visible]
for (x, y) in occluded:
    axA.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor="none",
                                     edgecolor=OCC, lw=1.0, hatch="///", alpha=0.55))
circ = mpatches.Circle((rob[0], rob[1]), rm.sight_radius, fill=False,
                       edgecolor="#2e6f95", lw=1.5, linestyle="--")
axA.add_patch(circ)
axA.add_patch(mpatches.Circle((rob[0], rob[1]), 0.35, facecolor="#b8434e", edgecolor="black", zorder=5))
axA.text(rob[0], rob[1] - 0.9, "robot", ha="center", fontsize=8, color="#b8434e", fontweight="bold")

# ---------- B: debris physics ----------
base(axB, "B — debris physics at t=%d (blind fleet, until-amnesty)" % SNAP_T)
for (y, x) in snap["disturbed"]:
    axB.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor=DEBRIS,
                                     edgecolor="#e6b400", lw=1.4, zorder=4))
for (x, y, typ, stuck, carrying) in snap["agents"]:
    if typ == "AGV":
        col = "#b8434e" if carrying else "#8a8a8a"
        axB.add_patch(mpatches.Circle((x, y), 0.33, facecolor=col, edgecolor="black", zorder=6))
        if stuck:
            axB.add_patch(mpatches.Circle((x, y), 0.48, fill=False, edgecolor="#e6b400",
                                          lw=2.2, zorder=7))
            axB.annotate("stuck until cleaned", (x, y), (x + 4.4, y - 2.0), fontsize=8,
                         color="#e6b400", fontweight="bold",
                         arrowprops=dict(arrowstyle="->", color="#e6b400"), zorder=8)
    else:
        axB.add_patch(mpatches.RegularPolygon((x, y), 3, radius=0.3, facecolor="#3f7d3a",
                                              edgecolor="black", zorder=6))

# ---------- C: belief map ----------
base(axC, "C — the fleet's belief at the same instant (heat = P(blocked))")
bmap = snap["belief"]
for y in range(H):
    for x in range(W):
        p = bmap[y, x]
        if p > 0.52:
            axC.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1,
                                             facecolor=plt.cm.YlOrRd(min(1.0, (p - 0.5) * 2)),
                                             edgecolor="none", alpha=0.9, zorder=3))
for (y, x) in snap["disturbed"]:
    seen = bmap[y, x] > 0.5
    axC.add_patch(mpatches.Rectangle((x - .48, y - .48), 0.96, 0.96, facecolor="none",
                                     edgecolor=("#3f7d3a" if seen else "#b8434e"),
                                     lw=2.0, zorder=5))
axC.text(0.01, -0.055, "outline green = real debris the fleet has SEEN (routed around)   "
         "red = real debris NOBODY has seen (invisible to the router)",
         transform=axC.transAxes, fontsize=7.6, color="#444")

# ---------- D: one cell's life ----------
cell = max(((c, len(h)) for c, h in belief_hist.items() if c in spawn_t and c in amnesty_t
            and max(h) > 0.7), key=lambda kv: max(belief_hist[kv[0]]), default=(None, 0))[0]
axD.set_title("D — one debris cell's life: spawn, sightings, amnesty, forgetting", fontsize=10)
if cell:
    h = belief_hist[cell]
    axD.plot(range(len(h)), h, color="#b8434e", lw=1.8)
    axD.axvline(spawn_t[cell], color="#1a1a1a", lw=1.2, linestyle="--")
    axD.axvline(amnesty_t[cell], color="#3f7d3a", lw=1.2, linestyle="--")
    axD.text(spawn_t[cell] + 3, 0.95, "spill appears", fontsize=8.5)
    axD.text(amnesty_t[cell] + 3, 0.88, "cleaned (amnesty)", fontsize=8.5, color="#3f7d3a")
    axD.axhline(0.5, color="#999", lw=0.8, linestyle=":")
    axD.text(len(h) - 2, 0.515, "router avoids above this line (b_hard = 0.5)", fontsize=7.6,
             ha="right", color="#666")
    axD.set_ylim(0.35, 1.02)
    axD.set_xlabel("step", fontsize=9)
    axD.set_ylabel("fleet belief P(blocked)", fontsize=9)
    axD.tick_params(labelsize=8)
fig.suptitle("Disturbances and line-of-sight sensing — computed from a live blind run (large-8-6, "
             "until-amnesty physics)", fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.965))
out = os.path.join("results", "disturbances_los.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("saved", out, "| visible cells:", len(visible), "| debris at snap:", len(snap["disturbed"]),
      "| story cell:", cell)
