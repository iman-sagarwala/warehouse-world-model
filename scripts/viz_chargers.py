"""Snapshot of the simulator map with the M3 charger cells highlighted.

Left panel: the raw map at t=0 (storage racks, aisles, stations, charger bays).
Right panel: a mid-episode m3 step (seed 5, t=120) with robots, carried pods, and
battery levels, so the charger cells can be seen in use.
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
import numpy as np
import wwm_sim  # noqa
from wwm_sim.warehouse import AgentType, CollisionLayers
from wwm_sim.demand import DemandModel
import importlib.util

spec = importlib.util.spec_from_file_location("m3b", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
m3b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m3b)

os.environ["M3SPC"] = "1500"

SNAP_T = 120


def build(seed=5):
    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    m3b.setup_bays(env)
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    dm.shelfs = [s_ for s_ in dm.shelfs if s_.id not in env._charger_bay_ids]
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    for k, v in dict(picker_service_steps=8, station_service_steps=6, station_headway=True,
                     station_exit_priority=True, free_pod_return=True, picker_free_move="committed",
                     picker_final_step=True, station_side_keepout=True, keepout_top=True,
                     station_divert=True, swap_return_drop=True, picker_swap=True,
                     picker_swap_squat=True, agv_free_move=True, slot_divert=True,
                     picker_reelect="progress", clash_sim=True, clash_hysteresis=20).items():
        setattr(env, k, v)
    ctrl, bc = m3b.make_controller("m3", env)
    rng = np.random.RandomState(7000 + seed)
    for a in env.agents:
        bc.battery.level[a.id] = float(rng.uniform(0.15, 1.0))
    return env, ctrl, bc


def draw_map(ax, env, bc, ctrl=None, title=""):
    H, W = env.grid_size  # (rows=y, cols=x)
    storage = {(x, y) for (y, x) in env.action_id_to_coords_map.values()}
    goals = {tuple(g) for g in env.goals}
    chargers = set(bc.battery.chargers)
    # background: aisles
    ax.add_patch(mpatches.Rectangle((-0.5, -0.5), W, H, facecolor="#f4f1ea", edgecolor="none"))
    for y in range(H):
        for x in range(W):
            if (x, y) in goals:
                ax.add_patch(mpatches.Rectangle((x - 0.5, y - 0.5), 1, 1,
                                                facecolor="#2e6f95", edgecolor="white", lw=0.6))
            elif (x, y) in storage:
                has_shelf = bool(env.grid[CollisionLayers.SHELVES, y, x])
                fc = "#c9a26b" if has_shelf else "#e8dcc8"
                ax.add_patch(mpatches.Rectangle((x - 0.5, y - 0.5), 1, 1,
                                                facecolor=fc, edgecolor="white", lw=0.6))
    # charger bays on top
    for (x, y) in chargers:
        ax.add_patch(mpatches.Rectangle((x - 0.46, y - 0.46), 0.92, 0.92, facecolor="none",
                                        edgecolor="#e6b400", lw=2.4, zorder=5))
        ax.text(x, y, "⚡", ha="center", va="center", fontsize=11, zorder=6,
                color="#8a6d00")
    for (x, y) in goals:
        ax.text(x, y, "STN", ha="center", va="center", fontsize=6.5, color="white",
                fontweight="bold", zorder=6)
    # robots
    if ctrl is not None:
        from sim_priority import MissionType
        for a in env.agents:
            if a.type == AgentType.AGV:
                m = ctrl.assigned_agvs.get(a)
                charging = m is not None and m.mission_type == MissionType.CHARGING
                col = "#b8434e" if a.carrying_shelf is not None else (
                    "#e6b400" if charging else "#5a5a5a")
                ax.add_patch(mpatches.Circle((a.x, a.y), 0.34, facecolor=col,
                                             edgecolor="black", lw=0.8, zorder=8))
                if a.carrying_shelf is not None:
                    ax.add_patch(mpatches.Rectangle((a.x - 0.22, a.y - 0.22), 0.44, 0.44,
                                                    facecolor="#7a4e1d", edgecolor="black",
                                                    lw=0.6, zorder=9))
                lvl = bc.battery.level.get(a.id, 1.0)
                ax.text(a.x, a.y - 0.62, "%d%%" % round(100 * lvl), ha="center", va="center",
                        fontsize=5.2, color="#333", zorder=10)
            else:
                ax.add_patch(mpatches.RegularPolygon((a.x, a.y), numVertices=3, radius=0.30,
                                                     facecolor="#3f7d3a", edgecolor="black",
                                                     lw=0.7, zorder=8))
    ax.set_xlim(-0.6, W - 0.4)
    ax.set_ylim(H - 0.4, -0.6)  # y down = row 0 on top, stations at the bottom
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=10)


env, ctrl, bc = build()
fig, axes = plt.subplots(1, 2, figsize=(11.6, 9.2))
draw_map(axes[0], env, bc, ctrl=None,
         title="Map at t=0: racks, aisles, 3 stations, 8 charger bays")
for t in range(SNAP_T):
    env.step(ctrl.act())
draw_map(axes[1], env, bc, ctrl=ctrl,
         title="m3 arm, seed 5, t=%d: robots + battery levels" % SNAP_T)

legend = [
    mpatches.Patch(facecolor="#c9a26b", edgecolor="white", label="storage cell with pod"),
    mpatches.Patch(facecolor="#e8dcc8", edgecolor="white", label="bare storage cell"),
    mpatches.Patch(facecolor="#f4f1ea", edgecolor="#ccc", label="aisle"),
    mpatches.Patch(facecolor="#2e6f95", edgecolor="white", label="pick station (goal)"),
    mpatches.Patch(facecolor="none", edgecolor="#e6b400", lw=2.4, label="charger bay (dedicated, shelf-free)"),
    mpatches.Circle((0, 0), 1, facecolor="#5a5a5a", edgecolor="black", label="AGV (empty)"),
    mpatches.Circle((0, 0), 1, facecolor="#b8434e", edgecolor="black", label="AGV carrying pod"),
    mpatches.Circle((0, 0), 1, facecolor="#e6b400", edgecolor="black", label="AGV on charge trip"),
    mpatches.RegularPolygon((0, 0), 3, radius=1, facecolor="#3f7d3a", edgecolor="black", label="picker"),
]
fig.legend(handles=legend, loc="lower center", ncol=3, fontsize=8, frameon=False,
           bbox_to_anchor=(0.5, -0.005))
fig.suptitle("wwm_sim large-dense map with M3 charger bays (⚡)", fontsize=12, y=0.98)
fig.tight_layout(rect=(0, 0.06, 1, 0.96))
out = os.path.join("results", "map_chargers.png")
fig.savefig(out, dpi=160, bbox_inches="tight")
print("saved", out)
