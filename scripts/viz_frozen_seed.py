"""Render one episode with the FROZEN AGVs highlighted, so the claim is visible rather than asserted.

Seed 65 under the champion + final-step config: all eight AGVs end up motionless around station (11,24),
each blocked by another robot on 99 of 99 measured steps. Frozen AGVs are drawn red with the number of
steps they have been stationary; everyone else is drawn normally.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import numpy as np
import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.warehouse import CollisionLayers, AgentType
from wwm_sim.demand import DemandModel
import congestion_policies as cp

SEED = int(os.environ.get("SEED", "65"))
FPS = int(os.environ.get("FPS", "12"))
OUT = os.environ.get("OUT", "results/frozen_seed%d.gif" % SEED)

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
ctrl = cp._SqWidePkRateAdaptive(env)

frames = []
still = {}
delivered = 0
for t in range(500):
    pre = {a.id: (a.x, a.y) for a in env.agents}
    _, rew, _, _, _ = env.step(ctrl.act())
    delivered += int(sum(rew))
    for a in env.agents:
        if (a.x, a.y) == pre[a.id]:
            still[a.id] = still.get(a.id, 0) + 1
        else:
            still[a.id] = 0
    agvs = [(a.x, a.y, a.carrying_shelf is not None, a.id, still.get(a.id, 0))
            for a in env.agents if a.type == AgentType.AGV]
    pks = [(p.x, p.y) for p in env.agents if p.type == AgentType.PICKER]
    shelves = np.argwhere(env.grid[CollisionLayers.SHELVES] > 0)
    frames.append((t, delivered, agvs, pks, shelves, len(env.request_queue)))

print("recorded %d frames; rendering..." % len(frames))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

H, W = env.grid_size
goals = set(env.goals)
fig, ax = plt.subplots(figsize=(7.2, 7.8))
fig.patch.set_facecolor("#111318")

STUCK = 25          # steps stationary before a robot is drawn as frozen


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
    ax.scatter([g[0] for g in goals], [g[1] for g in goals], s=170, marker="s",
               c="#1f6feb", edgecolors="#79c0ff", linewidths=1.4, zorder=2)
    if pks:
        ax.scatter([p[0] for p in pks], [p[1] for p in pks], s=95, marker="^",
                   c="#3fb950", edgecolors="white", linewidths=.6, zorder=4)
    nfrozen = 0
    for (x, y, carry, aid, sc) in agvs:
        frozen = sc >= STUCK
        if frozen:
            nfrozen += 1
            col, ec, lw, sz = "#f85149", "#ffdf5d", 2.6, 200
        elif carry:
            col, ec, lw, sz = "#d29922", "white", .6, 135
        else:
            col, ec, lw, sz = "#8b949e", "white", .6, 135
        ax.scatter([x], [y], s=sz, marker="o", c=col, edgecolors=ec, linewidths=lw,
                   zorder=6 if frozen else 5)
        if frozen:
            ax.annotate("%d" % sc, (x, y), color="#ffdf5d", fontsize=9, weight="bold",
                        xytext=(7, 7), textcoords="offset points", zorder=7)
    ax.set_title("seed %d  ·  step %3d/500  ·  delivered %d  ·  queue %d\n"
                 "RED = AGV stationary %d+ steps   ·   frozen now: %d of 8"
                 % (SEED, t, dl, q, STUCK, nfrozen),
                 color="#e6edf3", fontsize=10.5, pad=10)
    return []


FuncAnimation(fig, draw, frames=len(frames), blit=False).save(
    OUT, writer=PillowWriter(fps=FPS), dpi=95)
print("wrote", OUT)
