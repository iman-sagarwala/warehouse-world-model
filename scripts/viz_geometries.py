"""All warehouse geometries used by the MPC campaign so far, at t=0 with charging bays.

Row 1: the dense family (1-cell lanes, column_height=6) from tiny to extralarge.
Row 2: the dual-carriageway family (2-cell opposing lanes, column_height=10).
Within a row panels share one cell scale (subplot widths proportional to map widths).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.warehouse import CollisionLayers
import importlib.util

spec = importlib.util.spec_from_file_location("m3b", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
m3b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m3b)

# rows of (label, env id fragment, n_agvs for bay count, campaign verdict note)
ROWS = [
    [
        ("tiny dense",       "tinydense-4agvs-3pickers",        4,  "4-3 parked +1.88"),
        ("small dense",      "smalldense-4agvs-3pickers",       4,  "4-3 flat / 8-6 open"),
        ("medium dense",     "mediumdense-8agvs-6pickers",      8,  "5-4, 12-8 ADOPTED\n8-6 parked"),
        ("large dense",      "largedense-8agvs-6pickers",       8,  "3-2, 5-4, 12-8, 16-9 ADOPTED\n8-6 parked"),
        ("extralarge dense", "extralargedense-12agvs-8pickers", 12, "12-8, 16-9, 19-9 ADOPTED\n8-6 lean-neg"),
    ],
    [
        ("medium dual",      "mediumdual-5agvs-4pickers",       5,  "5-4 ADOPTED +2.52"),
        ("large dual",       "largedual-8agvs-6pickers",        8,  "8-6 ADOPTED / 12-8 flat\n16-9 open"),
        ("extralarge dual",  "extralargedual-12agvs-8pickers",  12, "12-8 flat"),
    ],
]


def draw(ax, env, bays, title, note):
    H, W = env.grid_size
    storage = {(x, y) for (y, x) in env.action_id_to_coords_map.values()}
    goals = {tuple(g) for g in env.goals}
    ax.add_patch(mpatches.Rectangle((-0.5, -0.5), W, H, facecolor="#f4f1ea", edgecolor="#bbb", lw=0.8))
    for y in range(H):
        for x in range(W):
            if (x, y) in goals:
                ax.add_patch(mpatches.Rectangle((x - 0.5, y - 0.5), 1, 1,
                                                facecolor="#2e6f95", edgecolor="white", lw=0.4))
            elif (x, y) in storage:
                has_shelf = bool(env.grid[CollisionLayers.SHELVES, y, x])
                fc = "#c9a26b" if has_shelf else "#efe6d4"
                ax.add_patch(mpatches.Rectangle((x - 0.5, y - 0.5), 1, 1,
                                                facecolor=fc, edgecolor="white", lw=0.4))
    for (x, y) in bays:
        ax.add_patch(mpatches.Rectangle((x - 0.44, y - 0.44), 0.88, 0.88, facecolor="none",
                                        edgecolor="#e6b400", lw=1.6, zorder=5))
        ax.text(x, y, "⚡", ha="center", va="center", fontsize=6, color="#8a6d00", zorder=6)
    ax.set_xlim(-0.7, W - 0.3)
    ax.set_ylim(H - 0.3, -0.7)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("%s\n%dx%d, %d slots, %d bays" % (title, W, H,
                                                   len(storage) - len(goals), len(bays)),
                 fontsize=8.5)
    ax.text(0.5, -0.02, note, transform=ax.transAxes, ha="center", va="top",
            fontsize=6.8, color="#555")


built = []
for row in ROWS:
    r = []
    for label, frag, nagv, note in row:
        env = gym.make("wwm_sim-%s-globalobs-v1" % frag).unwrapped
        env.reset(seed=1)
        bays = m3b.setup_bays(env, n=max(4, nagv))
        r.append((label, env, bays, note))
    built.append(r)

fig = plt.figure(figsize=(15.5, 13.5))
gs = fig.add_gridspec(2, 1, height_ratios=[
    max(e[1].grid_size[0] for e in built[0]),
    max(e[1].grid_size[0] for e in built[1])], hspace=0.24)
for i, row in enumerate(built):
    widths = [e[1].grid_size[1] for e in row]
    sub = gs[i].subgridspec(1, len(row), width_ratios=widths, wspace=0.06)
    for j, (label, env, bays, note) in enumerate(row):
        draw(fig.add_subplot(sub[j]), env, bays, label, note)

legend = [
    mpatches.Patch(facecolor="#c9a26b", edgecolor="white", label="storage slot with pod"),
    mpatches.Patch(facecolor="#efe6d4", edgecolor="white", label="bare slot"),
    mpatches.Patch(facecolor="#f4f1ea", edgecolor="#bbb", label="aisle / highway"),
    mpatches.Patch(facecolor="#2e6f95", edgecolor="white", label="pick station"),
    mpatches.Patch(facecolor="none", edgecolor="#e6b400", lw=1.6, label="charging bay (shelf-free)"),
]
fig.legend(handles=legend, loc="lower center", ncol=5, fontsize=8.5, frameon=False,
           bbox_to_anchor=(0.5, 0.005))
fig.suptitle("MPC campaign geometries — dense family (1-cell lanes) and dual-carriageway family "
             "(2-cell opposing lanes)", fontsize=12, y=0.985)
out = os.path.join("results", "campaign_geometries.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("saved", out)
