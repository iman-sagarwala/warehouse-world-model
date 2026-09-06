"""GIF: the belief map predicting disturbance physics and the fleet learning around it.

Two panels per frame from ONE real run (reset-mode map, belief routing active):
  left  = the TRUE floor: spill (black/gold), robots, stations
  right = the FLEET'S BELIEF: heat = P(blocked); the map's memory holds between sightings
Phases: spill lands (nobody knows) -> SIGHTED (one look flips the map) -> fleet detours on
memory, not sight -> seen clean / cleaned (one look wipes it).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation, PillowWriter
import numpy as np

os.environ["M3SPC"] = "1500"
from record_race import build
from wwm_sim.rumor_map import BetaRumorMap

env, ctrl = build("large-8-6", 7)
env.disturb_rate = 0.03
env._disturb_rng = np.random.RandomState(777)
env.disturb_dur = (150, 400)
env.disturb_event_cells = (1, 3)
env.debris_hold_steps = -1
env.use_belief_routing = True
rm = BetaRumorMap(env.grid_size)         # reset-mode default: one look is decisive
env.rumor_map = rm
env.b_hard = 0.5
env.los_sensing = True
H, W = env.grid_size

frames = []
spawn_t, det_t, clean_t = {}, {}, {}
prev = set()
for t in range(400):
    env.step(ctrl.act())
    cur = set(env.disturbed)
    for c in cur - prev:
        spawn_t.setdefault(c, t)
    for c in prev - cur:
        clean_t.setdefault(c, t)
    prev = cur
    b = rm.belief()
    for c in cur:
        if c not in det_t and b[c[0], c[1]] > 0.5:
            det_t[c] = t
    frames.append(dict(
        t=t, disturbed=set(cur), belief=b.copy(), live=set(rm._live),
        agents=[(a.x, a.y, getattr(a, "carrying_shelf", None) is not None,
                 bool(getattr(a, "_debris_stuck", False)), a.type.name) for a in env.agents]))

# pick the DETECTED spill whose believed-and-dirty life is longest (best detour story)
cands = [(min(clean_t.get(c, 400), 400) - det_t[c], c) for c in det_t if c in spawn_t]
assert cands, "no detected spill this seed"
cell = max(cands)[1]
t0 = max(0, spawn_t[cell] - 8)
t1 = min(399, clean_t.get(cell, 399) + 12)
cy, cx = cell
x0, x1 = max(0, cx - 7), min(W, cx + 8)
y0, y1 = max(0, cy - 6), min(H, cy + 7)

storage = {(x, y) for (y, x) in env.action_id_to_coords_map.values()}
goals = {tuple(g) for g in env.goals}
bays = set(env._charger_bays)

fig, (axT, axB) = plt.subplots(1, 2, figsize=(11.6, 5.6))
SUB = 3


def draw(fi):
    f = frames[t0 + fi * SUB]
    tt = f["t"]
    for ax in (axT, axB):
        ax.clear()
        ax.set_xlim(x0 - .6, x1 - .4)
        ax.set_ylim(y1 - .4, y0 - .6)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    # ---- left: truth ----
    for y in range(y0, y1):
        for x in range(x0, x1):
            if (x, y) in goals:
                fc = "#2e6f95"
            elif (x, y) in storage:
                fc = "#eee3cd" if (x, y) in bays else "#c9a26b"
            else:
                fc = "#f4f1ea"
            axT.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor=fc,
                                             edgecolor="white", lw=0.5))
    for (y, x) in f["disturbed"]:
        if x0 <= x < x1 and y0 <= y < y1:
            axT.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor="#1a1a1a",
                                             edgecolor="#e6b400", lw=1.6, zorder=4))
    for (x, y, carrying, stuck, typ) in f["agents"]:
        if not (x0 <= x < x1 and y0 <= y < y1):
            continue
        if typ == "AGV":
            col = "#b8434e" if carrying else "#8a8a8a"
            axT.add_patch(mpatches.Circle((x, y), 0.33, facecolor=col, edgecolor="black", zorder=6))
            if stuck:
                axT.add_patch(mpatches.Circle((x, y), 0.47, fill=False, edgecolor="#e6b400",
                                              lw=2.4, zorder=7))
        else:
            axT.add_patch(mpatches.RegularPolygon((x, y), 3, radius=0.3, facecolor="#3f7d3a",
                                                  edgecolor="black", zorder=6))
    axT.set_title("the real floor", fontsize=10)
    # ---- right: belief ----
    b = f["belief"]
    for y in range(y0, y1):
        for x in range(x0, x1):
            p = float(b[y, x])
            if not (x, y) in storage and not (x, y) in goals:
                fc = plt.cm.Reds(min(1.0, max(0.0, (p - 0.5) * 2))) if p > 0.5 else \
                     ("#ffffff" if p > 0.45 else "#e8f0e8")
            else:
                fc = "#d8d2c4"
            axB.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor=fc,
                                             edgecolor="white", lw=0.5))
            if p > 0.5 and (x, y) not in storage:
                axB.add_patch(mpatches.Rectangle((x - .46, y - .46), 0.92, 0.92, fill=False,
                                                 edgecolor="#8b0000", lw=1.4, zorder=5))
    bc = float(b[cy, cx])
    in_sight = (cy, cx) in f.get("live", ())
    axB.set_title("the fleet's belief   P = %.0f%%  (%s)" % (100 * bc,
                  "IN SIGHT: certainty" if in_sight else "out of sight: PREDICTION"), fontsize=10)
    # phase caption
    if tt < spawn_t[cell]:
        ph = "clean aisle"
    elif tt < det_t[cell]:
        ph = "spill is DOWN - nobody has seen it (map still calm)"
    elif cell in f["disturbed"]:
        ph = "SIGHTED at t=%d - one look flipped the map; fleet detours on MEMORY" % det_t[cell]
    else:
        ph = "cleaned - one clean look wipes the memory"
    fig.suptitle("t=%d   %s" % (tt, ph), fontsize=11)


n_frames = (t1 - t0) // SUB
anim = FuncAnimation(fig, draw, frames=n_frames, interval=100)
out = os.path.join("results", "belief_physics.gif")
anim.save(out, writer=PillowWriter(fps=10))
print("saved", out, os.path.getsize(out) // 1024, "KB | cell", cell,
      "spawn %d seen %d clean %s window %d..%d"
      % (spawn_t[cell], det_t[cell], clean_t.get(cell, "end"), t0, t1))
