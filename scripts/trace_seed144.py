"""Seed 144, AGV 4: the 448-step wait under the FULL champion. Trace + GIF in one pass.

Questions the trace must answer:
  1. when does the wait start, and where
  2. is a picker COMMITTED to that cell during the wait (the seed-11 pattern), or was none ever sent
  3. if committed: where is that picker and why does it never arrive -- travelling, PARKED on another
     pod (a picker_final_step robot waiting for an AGV that never comes), silenced, or looping
  4. does the AGV's own task/mission stay live the whole time

Renders results/seed144_trace.gif with AGV 4 highlighted (wait counter) and any picker committed to
its cell highlighted in yellow.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import numpy as np
import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.warehouse import CollisionLayers, AgentType, Action
from wwm_sim.demand import DemandModel
import congestion_policies as cp

SEED, WATCH = 144, 4
FPS = int(os.environ.get("FPS", "14"))
OUT = "results/seed144_trace.gif"

env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
env.reset(seed=SEED)
env.request_queue = []
dm = DemandModel(env, seed=SEED, exogenous=True, horizon=500, window_index=SEED, n_windows=162,
                 value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
env.demand_model = dm
n = dm.warm_start_n()
dm.seed_day_list(env, horizon=500)
dm.seed_initial(env, n=n)
env.picker_service_steps = 8
env.station_service_steps = 6
env.station_headway = True
env.station_exit_priority = True
env.free_pod_return = True
env.picker_free_move = "committed"
env.picker_final_step = True
env.station_side_keepout = True
env.station_divert = True
env.swap_return_drop = True
ctrl = cp._SqWidePkRateAdaptive(env)

agv = next(a for a in env.agents if a.id == WATCH and a.type == AgentType.AGV)
wait = 0
start = None
committed_hist = collections.Counter()
picker_state = collections.Counter()
snaps = []
frames = []
delivered = 0

for t in range(500):
    _, rew, _, _, _ = env.step(ctrl.act())
    delivered += int(sum(rew))

    waiting = (agv.carrying_shelf is None and agv.req_action == Action.TOGGLE_LOAD
               and env.grid[CollisionLayers.SHELVES, agv.y, agv.x]
               and not env.grid[CollisionLayers.PICKERS, agv.y, agv.x])
    my_cell = (agv.x, agv.y)
    committed_pk = None
    ap = getattr(ctrl, "assigned_pickers", {})
    for p, m in ap.items():
        if (m.location_x, m.location_y) == my_cell:
            committed_pk = p
            break
    if waiting:
        wait += 1
        if wait == 1:
            start = t
        committed_hist["a picker IS committed to my cell" if committed_pk else "NO picker committed"] += 1
        if committed_pk is not None:
            p = committed_pk
            parked = (not getattr(p, "path", None)
                      and env.grid[CollisionLayers.SHELVES, p.y, p.x]
                      and (p.x, p.y) != my_cell)
            if parked:
                picker_state["parked ON A DIFFERENT POD (final-step, waiting for its own AGV)"] += 1
            elif not getattr(p, "path", None):
                picker_state["no path, not parked on a pod"] += 1
            else:
                picker_state["travelling (has a path)"] += 1
        if wait in (1, 5, 25, 100, 200, 300, 400, 448) or (wait % 100 == 0):
            others = []
            for p in ctrl.pickers:
                m = ap.get(p)
                onpod = bool(env.grid[CollisionLayers.SHELVES, p.y, p.x]) and not getattr(p, "path", None)
                others.append("p%d@%s%s%s" % (p.id, (p.x, p.y),
                                              ("->%s" % ((m.location_x, m.location_y),)) if m else " FREE",
                                              " [PARKED-ON-POD]" if onpod else ""))
            snaps.append((t, wait, my_cell,
                          committed_pk.id if committed_pk is not None else None, " ".join(others)))
    else:
        wait = 0

    highlight_pk = committed_pk.id if committed_pk is not None else None
    agvs = [(a.x, a.y, a.carrying_shelf is not None, a.id,
             wait if (a.id == WATCH and a.type == AgentType.AGV) else 0)
            for a in env.agents if a.type == AgentType.AGV]
    pks = [(p.x, p.y, p.id, p.id == highlight_pk,
            bool(env.grid[CollisionLayers.SHELVES, p.y, p.x]) and not getattr(p, "path", None))
           for p in env.agents if p.type == AgentType.PICKER]
    shelves = np.argwhere(env.grid[CollisionLayers.SHELVES] > 0)
    frames.append((t, delivered, agvs, pks, shelves, len(env.request_queue)))

print("seed %d, AGV %d -- wait started t=%s" % (SEED, WATCH, start))
print("\nDuring the wait, was anyone committed to my rendezvous?")
for k, v in committed_hist.most_common():
    print("   %-46s %d steps" % (k, v))
print("\nAnd when committed, what was that picker doing?")
for k, v in picker_state.most_common():
    print("   %-58s %d steps" % (k, v))
print("\nSnapshots:")
for (t, w, cell, pk, others) in snaps[:14]:
    print("  t=%-4d waited=%-4d cell=%-9s committed=%s" % (t, w, str(cell), ("p%d" % pk) if pk else "NONE"))
    print("     %s" % others)

# ---------------- render ----------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

H, W = env.grid_size
goals = set(env.goals)
fig, ax = plt.subplots(figsize=(7.2, 7.8))
fig.patch.set_facecolor("#111318")


def draw(k):
    t, dl, agvs, pks, shelves, q = frames[k]
    ax.clear()
    ax.set_facecolor("#111318")
    ax.set_xlim(-0.5, W - 0.5)
    ax.set_ylim(H - 0.5, -0.5)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#333")
    if len(shelves):
        ax.scatter(shelves[:, 1], shelves[:, 0], s=26, marker="s", c="#3a3f4b", linewidths=0)
    ax.scatter([g[0] for g in goals], [g[1] for g in goals], s=160, marker="s",
               c="#1f6feb", edgecolors="#79c0ff", linewidths=1.2, zorder=2)
    for (x, y, pid, hot, onpod) in pks:
        if hot:
            c, ec, lw, sz = "#ffdf5d", "#f85149", 2.0, 150     # the picker committed to AGV 4
        elif onpod:
            c, ec, lw, sz = "#8957e5", "white", 1.0, 110       # parked on a pod (final-step)
        else:
            c, ec, lw, sz = "#3fb950", "white", .6, 95
        ax.scatter([x], [y], s=sz, marker="^", c=c, edgecolors=ec, linewidths=lw,
                   zorder=6 if hot else 4)
    for (x, y, carry, aid, wt) in agvs:
        if wt:
            col, ec, lw, sz = "#f85149", "#ffdf5d", 2.6, 200
        elif carry:
            col, ec, lw, sz = "#d29922", "white", .6, 135
        else:
            col, ec, lw, sz = "#8b949e", "white", .6, 135
        ax.scatter([x], [y], s=sz, marker="o", c=col, edgecolors=ec, linewidths=lw,
                   zorder=7 if wt else 5)
        if wt:
            ax.annotate("%d" % wt, (x, y), color="#ffdf5d", fontsize=9, weight="bold",
                        xytext=(7, 7), textcoords="offset points", zorder=8)
    ax.set_title("seed %d  ·  step %3d/500  ·  delivered %d  ·  queue %d\n"
                 "red = AGV %d waiting (counter) · yellow triangle = its committed picker · "
                 "purple = picker parked on a pod"
                 % (SEED, t, dl, q, WATCH),
                 color="#e6edf3", fontsize=9.5, pad=10)
    return []


FuncAnimation(fig, draw, frames=len(frames), blit=False).save(
    OUT, writer=PillowWriter(fps=FPS), dpi=95)
print("\nwrote", OUT)
