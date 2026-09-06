"""GIF: how disturbances FORM, from a real run. Random timing, instant physics-bounded extent.

Full floor over a day: each event pops at full size (1-3 contiguous cells, impact scatter),
flashes a ring at birth, then never changes footprint until cleaned. Caption tracks event
count + sizes to show the statistics (learnable) vs the locations (memoryless random).
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

env, ctrl = build("large-8-6", 11)
env.disturb_rate = 0.04                      # denser than the audits, for a legible demo
env._disturb_rng = np.random.RandomState(42)
env.disturb_dur = (150, 400)
env.disturb_event_cells = (1, 3)
H, W = env.grid_size

frames = []
events = []                                   # (t, frozenset(cells))
prev = set()
for t in range(400):
    env.step(ctrl.act())
    cur = set(env.disturbed)
    new = cur - prev
    if new:
        events.append((t, frozenset(new)))    # one spawn event per step (single attempt/step)
    prev = cur
    frames.append(dict(t=t, disturbed=set(cur),
                       agents=[(a.x, a.y) for a in env.agents if a.type.name == "AGV"]))

storage = {(x, y) for (y, x) in env.action_id_to_coords_map.values()}
goals = {tuple(g) for g in env.goals}
bays = set(env._charger_bays)

fig, ax = plt.subplots(figsize=(10.5, 8.2))
SUB = 3
FLASH = 5                                     # frames the birth-ring stays visible


def draw(fi):
    ax.clear()
    tt = frames[fi * SUB]["t"]
    f = frames[fi * SUB]
    for y in range(H):
        for x in range(W):
            if (x, y) in goals:
                fc = "#2e6f95"
            elif (x, y) in storage:
                fc = "#eee3cd" if (x, y) in bays else "#c9a26b"
            else:
                fc = "#f4f1ea"
            ax.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor=fc,
                                            edgecolor="white", lw=0.4))
    for (y, x) in f["disturbed"]:
        ax.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor="#1a1a1a",
                                        edgecolor="#e6b400", lw=1.2, zorder=4))
    for (x, y) in f["agents"]:
        ax.add_patch(mpatches.Circle((x, y), 0.28, facecolor="#8a8a8a",
                                     edgecolor="black", lw=0.5, zorder=5))
    born = [(et, cells) for (et, cells) in events if 0 <= tt - et <= FLASH * SUB]
    for et, cells in born:
        ys = [c[0] for c in cells]; xs = [c[1] for c in cells]
        cx0, cy0 = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        r = max(max(xs) - min(xs), max(ys) - min(ys)) / 2.0 + 1.6
        ax.add_patch(mpatches.Circle((cx0, cy0), r, fill=False, edgecolor="#e07b39",
                                     lw=2.6, zorder=7))
        ax.text(cx0, cy0 - r - 0.5, "%d-cell event: FULL SIZE AT BIRTH" % len(cells),
                ha="center", fontsize=9, color="#e07b39", fontweight="bold", zorder=8)
    n_ev = sum(1 for et, _ in events if et <= tt)
    sizes = [len(c) for et, c in events if et <= tt]
    ax.set_title("t=%d   %d spawn events so far   sizes: %s\n"
                 "timing memoryless-random · placement random over aisles · extent = impact"
                 " scatter (1–3 cells, instant) · footprint NEVER grows afterwards"
                 % (tt, n_ev, sizes if len(sizes) <= 14 else sizes[-14:]), fontsize=10)
    ax.set_xlim(-0.6, W - 0.4)
    ax.set_ylim(H - 0.4, -0.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


anim = FuncAnimation(fig, draw, frames=len(frames) // SUB, interval=90)
out = os.path.join("results", "spawn_physics.gif")
anim.save(out, writer=PillowWriter(fps=11))
sizes = [len(c) for _, c in events]
print("saved", out, os.path.getsize(out) // 1024, "KB |", len(events), "events, sizes", sizes)
