"""GIF: one spill's full life under until-amnesty physics, from a real blind run.

Frames show: the spill appearing on an aisle, robots detouring or driving in and getting stuck
(gold ring), the countdown to amnesty, then the cell clearing and the stuck robot resuming.
No cleanup robot exists in the model: amnesty is an off-model janitor (a timed despawn drawn at
spawn from disturb_dur), which the caption states honestly.
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
env.debris_hold_steps = -1
env.use_belief_routing = True
env.rumor_map = BetaRumorMap(env.grid_size)
env.b_hard = 1.1
env.los_sensing = True
env.janitor = True
H, W = env.grid_size

frames = []
prev = set()
spawn_t, exp_t = {}, {}
for t in range(400):
    env.step(ctrl.act())
    cur = set(getattr(env, "disturbed", ()))
    for c in cur - prev:
        spawn_t[c] = t
        exp_t[c] = env._disturb_expiry.get(c)
    prev = cur
    jj = getattr(env, "_jan", None)
    frames.append(dict(
        t=t, disturbed=set(cur),
        jan=(jj["x"], jj["y"], jj["clean_left"] > 0) if jj else None,
        agents=[(a.x, a.y, getattr(a, "carrying_shelf", None) is not None,
                 bool(getattr(a, "_debris_stuck", False)), a.type.name)
                for a in env.agents]))

# pick the spill with the longest STUCK drama: cell where some agent was stuck most steps
stuck_near = {}
for f in frames:
    for (x, y, c, stuck, typ) in f["agents"]:
        if stuck and (y, x) in f["disturbed"]:
            stuck_near[(y, x)] = stuck_near.get((y, x), 0) + 1
cell = max(stuck_near, key=stuck_near.get)
clean_t = next((f["t"] for f in frames if f["t"] > spawn_t[cell] and cell not in f["disturbed"]), 399)
t0 = max(0, spawn_t[cell] - 12)
t1 = min(len(frames) - 1, clean_t + 18)
cy, cx = cell
x0, x1 = max(0, cx - 6), min(W, cx + 7)
y0, y1 = max(0, cy - 5), min(H, cy + 6)

storage = {(x, y) for (y, x) in env.action_id_to_coords_map.values()}
goals = {tuple(g) for g in env.goals}
bays = set(env._charger_bays)

fig, ax = plt.subplots(figsize=(7.2, 6.2))
SUB = 4     # frame stride to keep the gif small


def draw(fi):
    ax.clear()
    f = frames[t0 + fi * SUB]
    for y in range(y0, y1):
        for x in range(x0, x1):
            if (x, y) in goals:
                fc = "#2e6f95"
            elif (x, y) in storage:
                fc = "#eee3cd" if (x, y) in bays else "#c9a26b"
            else:
                fc = "#f4f1ea"
            ax.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor=fc,
                                            edgecolor="white", lw=0.5))
    for (y, x) in f["disturbed"]:
        if x0 <= x < x1 and y0 <= y < y1:
            ax.add_patch(mpatches.Rectangle((x - .5, y - .5), 1, 1, facecolor="#1a1a1a",
                                            edgecolor="#e6b400", lw=1.6, zorder=4))
    for (x, y, carrying, stuck, typ) in f["agents"]:
        if not (x0 <= x < x1 and y0 <= y < y1):
            continue
        if typ == "AGV":
            col = "#b8434e" if carrying else "#8a8a8a"
            ax.add_patch(mpatches.Circle((x, y), 0.33, facecolor=col, edgecolor="black", zorder=6))
            if stuck:
                ax.add_patch(mpatches.Circle((x, y), 0.47, fill=False, edgecolor="#e6b400",
                                             lw=2.4, zorder=7))
        else:
            ax.add_patch(mpatches.RegularPolygon((x, y), 3, radius=0.3, facecolor="#3f7d3a",
                                                 edgecolor="black", zorder=6))
    if f.get("jan"):
        jx, jy, mopping = f["jan"]
        if x0 <= jx < x1 and y0 <= jy < y1:
            ax.add_patch(mpatches.Rectangle((jx - .32, jy - .38), 0.64, 0.76,
                                            facecolor="#e07b39", edgecolor="black", zorder=8))
            ax.text(jx, jy - 0.75, "janitor" + (" (mopping)" if mopping else ""), ha="center",
                    fontsize=8, color="#e07b39", fontweight="bold", zorder=9)
    tt = f["t"]
    if tt < spawn_t[cell]:
        phase = "clean aisle"
    elif cell in f["disturbed"]:
        phase = "SPILL DOWN - waiting for the janitor"
    else:
        phase = "CLEANED (amnesty) - traffic resumes"
    ax.set_title("t=%d   %s" % (tt, phase), fontsize=11)
    ax.set_xlim(x0 - .6, x1 - .4)
    ax.set_ylim(y1 - .4, y0 - .6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


n_frames = (t1 - t0) // SUB
anim = FuncAnimation(fig, draw, frames=n_frames, interval=90)
out = os.path.join("results", "amnesty.gif")
anim.save(out, writer=PillowWriter(fps=11))
print("saved", out, os.path.getsize(out) // 1024, "KB | cell", cell,
      "spawn t=%d amnesty t=%s window %d..%d" % (spawn_t[cell], exp_t[cell], t0, t1))
