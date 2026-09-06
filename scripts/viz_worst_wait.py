"""Find the episode with the worst AGV pod-wait and render it as an animation.

A "pod wait" = an AGV parked on its rendezvous cell, not carrying, no path left, with no picker on the
cell: it is re-requesting TOGGLE_LOAD every step and the load silently no-ops. Those steps are 91% of
all TOGGLE_LOAD activity and ~29% of all non-moving AGV time.

Pass 1 scans seeds for the longest single wait. Pass 2 replays the winner recording every frame.
Output: results/worst_wait.gif  (+ a stills strip at the key moments).

Env: SCAN=72 (seeds to scan), FPS, OUT.
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

SCAN = int(os.environ.get("SCAN", "144"))
FPS = int(os.environ.get("FPS", "12"))
OUT = os.environ.get("OUT", "results/worst_wait_CHAMPION_v5.gif")


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
    # THE CHAMPION (2026-08-09, all-realistic mechanics) -- the reference every new idea compares to.
    env.picker_free_move = "committed"
    env.picker_final_step = True
    env.station_side_keepout = True
    env.station_divert = True
    env.swap_return_drop = True
    env.picker_swap = True
    env.picker_swap_squat = True
    env.agv_free_move = True
    env.slot_divert = True
    env.picker_reelect = "progress"
    env.clash_sim = True
    env.clash_hysteresis = 20
    return env, cp._SqWidePkRateAdaptive(env)


def waiting_ids(env):
    """AGV ids GENUINELY waiting for a picker: actively requesting a load that no-ops.

    The earlier definition (not carrying + no path + on a shelf cell + no picker) did NOT check that
    the robot wanted to load, so an AGV with no task parked on a shelf cell counted as a waiter. That
    produced a bogus 205-step "worst wait" on seed 3 which was really an idle robot after the episode
    ran dry (busy=False, mission=None, request queue empty).
    `req_action == TOGGLE_LOAD` while not carrying is the real waiting state: the AGV is asking to load
    on every step and `_execute_load` silently does nothing because no picker is present."""
    from wwm_sim.warehouse import Action
    out = []
    for a in env.agents:
        if a.type != AgentType.AGV or a.carrying_shelf is not None:
            continue
        if a.req_action != Action.TOGGLE_LOAD:
            continue
        if env.grid[CollisionLayers.SHELVES, a.y, a.x] and not env.grid[CollisionLayers.PICKERS, a.y, a.x]:
            out.append(a.id)
    return out


# ---- pass 1: find the worst single wait -------------------------------------------------
best = (0, None, None)      # (length, seed, agv_id)
FROZEN = []
for seed in range(1, SCAN + 1):
    env, ctrl = build(seed)
    run = {}
    for t in range(500):
        env.step(ctrl.act())
        w = set(waiting_ids(env))
        for i in list(run):
            if i not in w:
                run.pop(i)
        for i in w:
            run[i] = run.get(i, 0) + 1
            if run[i] > best[0]:
                best = (run[i], seed, i)
    fr = 0
    for a in env.agents:
        if a.type == AgentType.AGV and a.carrying_shelf is not None:
            fr += 1
    FROZEN.append(fr)
    if seed % 12 == 0:
        print("  scanned %d seeds, worst so far: %d steps (seed %s, agv %s)" % (seed, best[0], best[1], best[2]))
print("WORST WAIT: %d consecutive steps -- seed %s, AGV %s" % best)
print("AGVs still holding a pod at episode end: %d over %d seeds" % (sum(FROZEN), len(FROZEN)))

# ---- pass 2: replay and record ----------------------------------------------------------
seed = best[1]
env, ctrl = build(seed)
H, W = env.grid_size
shelf_static = None
frames = []
run = {}
delivered = 0
for t in range(500):
    _, rew, _, _, _ = env.step(ctrl.act())
    delivered += int(sum(rew))
    w = set(waiting_ids(env))
    for i in list(run):
        if i not in w:
            run.pop(i)
    for i in w:
        run[i] = run.get(i, 0) + 1
    agvs = [(a.x, a.y, a.carrying_shelf is not None, a.id, run.get(a.id, 0))
            for a in env.agents if a.type == AgentType.AGV]
    pks = [(p.x, p.y) for p in env.agents if p.type == AgentType.PICKER]
    shelves = np.argwhere(env.grid[CollisionLayers.SHELVES] > 0)
    frames.append((t, delivered, agvs, pks, shelves, len(env.request_queue)))

print("recorded %d frames; rendering..." % len(frames))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

goals = set(env.goals)
fig, ax = plt.subplots(figsize=(7.2, 7.6))
fig.patch.set_facecolor("#111318")


def draw(k):
    t, dl, agvs, pks, shelves, q = frames[k]
    ax.clear()
    ax.set_facecolor("#111318")
    ax.set_xlim(-0.5, W - 0.5)
    ax.set_ylim(H - 0.5, -0.5)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#333")
    # pods in storage
    if len(shelves):
        ax.scatter(shelves[:, 1], shelves[:, 0], s=26, marker="s", c="#3a3f4b", linewidths=0)
    # stations
    gx = [g[0] for g in goals]
    gy = [g[1] for g in goals]
    ax.scatter(gx, gy, s=150, marker="s", c="#1f6feb", edgecolors="#79c0ff", linewidths=1.2, zorder=2)
    # pickers
    if pks:
        ax.scatter([p[0] for p in pks], [p[1] for p in pks], s=95, marker="^",
                   c="#3fb950", edgecolors="white", linewidths=0.6, zorder=4)
    # AGVs
    for (x, y, carry, aid, wt) in agvs:
        if wt:
            col, ec, lw = "#f85149", "#ffdf5d", 2.2         # waiting at a pod = the thing we are hunting
        elif carry:
            col, ec, lw = "#d29922", "white", 0.6           # carrying a pod
        else:
            col, ec, lw = "#8b949e", "white", 0.6           # travelling empty
        ax.scatter([x], [y], s=135, marker="o", c=col, edgecolors=ec, linewidths=lw, zorder=5)
        if wt:
            ax.annotate("%d" % wt, (x, y), color="#ffdf5d", fontsize=8, weight="bold",
                        xytext=(6, 6), textcoords="offset points", zorder=6)
    worst = max([w for (_, _, _, _, w) in agvs] or [0])
    ax.set_title("seed %d  ·  step %3d/500  ·  delivered %d  ·  queue %d\n"
                 "red = AGV stalled at a pod waiting for a picker (number = steps waited, worst now %d)"
                 % (seed, t, dl, q, worst),
                 color="#e6edf3", fontsize=10.5, pad=10)
    return []


anim = FuncAnimation(fig, draw, frames=len(frames), blit=False)
anim.save(OUT, writer=PillowWriter(fps=FPS), dpi=95)
print("wrote", OUT)
