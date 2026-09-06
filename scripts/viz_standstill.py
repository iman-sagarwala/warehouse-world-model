"""LONGEST STANDSTILL with space-time reservations ON.

(a) does deadlock survive space-time  -- carrying AGVs still holding a pod at episode end, and
    carrying AGVs whose cell never changes over the last 100 steps
(b) longest consecutive standstill of ANY single robot (AGV or picker), position unchanged
(c) GIF of that episode with the offending robot highlighted
(d) the state of that robot DURING the standstill, so the cause is measured not guessed

A robot standing still is not automatically a fault: service dwell, waiting at a pod for a picker, and
having no task all look identical from position alone. The diagnostic therefore records, for every step
of the worst standstill, what the robot was carrying / requesting / whether it held a task and a path.

Env: SCAN (default 24), FPS, OUT.
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

SCAN = int(os.environ.get("SCAN", "24"))
FPS = int(os.environ.get("FPS", "12"))
OUT = os.environ.get("OUT", "results/worst_standstill.gif")


def build(seed):
    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed, n_windows=162,
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
    env.spacetime_reservations = True          # kept ON per user decision
    env.st_window = 16
    return env, cp._SqWidePkRateAdaptive(env)


# ---- pass 1: scan -------------------------------------------------------------------------
best = (0, None, None, None)          # (length, seed, agent_id, start_step)
still_holding = 0
frozen_carriers = 0
for seed in range(1, SCAN + 1):
    env, ctrl = build(seed)
    run = {}
    tail = {}
    for t in range(500):
        pre = {a.id: (a.x, a.y) for a in env.agents}
        env.step(ctrl.act())
        for a in env.agents:
            if (a.x, a.y) == pre[a.id]:
                if a.id not in run:
                    run[a.id] = [0, t]
                run[a.id][0] += 1
                if run[a.id][0] > best[0]:
                    best = (run[a.id][0], seed, a.id, run[a.id][1])
            else:
                run.pop(a.id, None)
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen_carriers += sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    still_holding += sum(1 for a in env.agents
                         if a.type == AgentType.AGV and a.carrying_shelf is not None)
    if seed % 8 == 0:
        print("  scanned %d/%d seeds; worst standstill so far %d steps (seed %s, agent %s)"
              % (seed, SCAN, best[0], best[1], best[2]))

print("\n(a) DEADLOCK WITH SPACE-TIME ON, %d seeds" % SCAN)
print("      carrying AGVs frozen 100+ steps at the tail : %d" % frozen_carriers)
print("      AGVs still holding a pod at episode end     : %d" % still_holding)
print("\n(b) LONGEST STANDSTILL BY ANY ROBOT: %d consecutive steps"
      "  (seed %s, agent %s, from t=%s)" % best)

# ---- pass 2: replay the winner, record frames + diagnose ----------------------------------
LEN, seed, WHO, T0 = best
T1 = T0 + LEN
env, ctrl = build(seed)
who = next(a for a in env.agents if a.id == WHO)
H, W = env.grid_size
frames = []
diag = collections.Counter()
delivered = 0
for t in range(500):
    _, rew, _, _, _ = env.step(ctrl.act())
    delivered += int(sum(rew))
    if T0 <= t <= T1:
        diag["steps"] += 1
        diag["carrying" if who.carrying_shelf is not None else "empty"] += 1
        diag["has path (len>0)" if getattr(who, "path", None) else "NO path"] += 1
        diag["req %s" % str(who.req_action).split(".")[-1]] += 1
        diag["busy" if getattr(who, "busy", False) else "not busy"] += 1
        sv = getattr(env, "_service_until", {}) or {}
        if sv.get(who.id, 0) > t:
            diag["in service dwell"] += 1
        if who in getattr(ctrl, "assigned_agvs", {}) or who in getattr(ctrl, "assigned_pickers", {}):
            diag["has a mission"] += 1
        else:
            diag["NO mission"] += 1
        if getattr(who, "path", None):
            nx_, ny_ = who.path[0]
            occ = env.grid[CollisionLayers.AGVS, ny_, nx_] or env.grid[CollisionLayers.PICKERS, ny_, nx_]
            diag["next cell BLOCKED by robot %d" % 0 if False else
                 ("next cell blocked" if occ else "next cell FREE")] += 1
    agvs = [(a.x, a.y, a.carrying_shelf is not None, a.id) for a in env.agents
            if a.type == AgentType.AGV]
    pks = [(p.x, p.y, p.id) for p in env.agents if p.type == AgentType.PICKER]
    shelves = np.argwhere(env.grid[CollisionLayers.SHELVES] > 0)
    frames.append((t, delivered, agvs, pks, shelves, len(env.request_queue)))

print("\n(d) STATE OF AGENT %d DURING ITS %d-STEP STANDSTILL (t=%d..%d)" % (WHO, LEN, T0, T1))
tot = diag["steps"] or 1
for k, v in diag.most_common():
    if k == "steps":
        continue
    print("      %-34s %5d  (%3.0f%%)" % (k, v, 100.0 * v / tot))

# ---- render -------------------------------------------------------------------------------
print("\nrendering %d frames..." % len(frames))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

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
    ax.scatter([g[0] for g in goals], [g[1] for g in goals], s=150, marker="s",
               c="#1f6feb", edgecolors="#79c0ff", linewidths=1.2, zorder=2)
    for (x, y, pid) in pks:
        hot = (pid == WHO and T0 <= t <= T1)
        ax.scatter([x], [y], s=150 if hot else 95, marker="^",
                   c="#f85149" if hot else "#3fb950",
                   edgecolors="#ffdf5d" if hot else "white",
                   linewidths=2.2 if hot else .6, zorder=6 if hot else 4)
    for (x, y, carry, aid) in agvs:
        hot = (aid == WHO and T0 <= t <= T1)
        if hot:
            col, ec, lw, sz = "#f85149", "#ffdf5d", 2.4, 190
        elif carry:
            col, ec, lw, sz = "#d29922", "white", .6, 135
        else:
            col, ec, lw, sz = "#8b949e", "white", .6, 135
        ax.scatter([x], [y], s=sz, marker="o", c=col, edgecolors=ec, linewidths=lw,
                   zorder=6 if hot else 5)
        if hot:
            ax.annotate("%d" % (t - T0 + 1), (x, y), color="#ffdf5d", fontsize=9, weight="bold",
                        xytext=(7, 7), textcoords="offset points", zorder=7)
    inwin = "  <<< STANDSTILL" if T0 <= t <= T1 else ""
    ax.set_title("seed %d  ·  step %3d/500  ·  delivered %d  ·  queue %d%s\n"
                 "red = agent %d, longest standstill in the scan (%d steps, t=%d-%d)"
                 % (seed, t, dl, q, inwin, WHO, LEN, T0, T1),
                 color="#e6edf3", fontsize=10, pad=10)
    return []


FuncAnimation(fig, draw, frames=len(frames), blit=False).save(
    OUT, writer=PillowWriter(fps=FPS), dpi=95)
print("wrote", OUT)
