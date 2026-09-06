"""Short visual: run the champion with disturbances for ~100 steps and save a GIF so you can SEE
the disturbances spawn/expire and robots route around them. Disturbances = BLACK squares.
Non-interactive (Agg) + collect-then-render, so it won't hang. Run: python scripts/viz_disturbances.py
"""
import os
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib
matplotlib.use("Agg")                       # no display -> no pyglet/gym render hang
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.animation import FuncAnimation, PillowWriter

import gymnasium as gym
import wwm_sim  # noqa: F401
from wwm_sim.warehouse import AgentType
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values
from congestion_policies import PartACongestionController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 100
OUT = "results/disturbances.gif"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def main():
    env = gym.make(ENV).unwrapped
    env.reset(seed=1)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    env.disturb_rate = 0.18                 # a bit higher so spawns are visible
    env._disturb_rng = np.random.RandomState(1)
    ctrl = PartACongestionController(env)
    H, W = env.grid_size

    # static background: corridors light, racks darker
    base = np.full((H, W, 3), 0.88, dtype=float)
    for y in range(H):
        for x in range(W):
            if not env._is_highway(x, y):
                base[y, x] = (0.62, 0.62, 0.66)

    frames = []
    for t in range(STEPS):
        env.step(ctrl.act())
        agvs = [(a.x, a.y, bool(a.carrying_shelf)) for a in env.agents if a.type == AgentType.AGV]
        pks = [(a.x, a.y) for a in env.agents if a.type == AgentType.PICKER]
        dist = list(getattr(env, "disturbed", set()))
        frames.append((t + 1, agvs, pks, dist))

    fig, ax = plt.subplots(figsize=(7, 7))

    def draw(i):
        ax.clear()
        step, agvs, pks, dist = frames[i]
        ax.imshow(base, origin="upper", interpolation="nearest")
        for (y, x) in dist:                                  # DISTURBANCES = black
            ax.add_patch(Rectangle((x - 0.5, y - 0.5), 1, 1, color="black"))
        if agvs:
            ax.scatter([a[0] for a in agvs], [a[1] for a in agvs],
                       c=[("navy" if a[2] else "royalblue") for a in agvs], s=60,
                       edgecolors="white", linewidths=0.6, zorder=3)
        if pks:
            ax.scatter([p[0] for p in pks], [p[1] for p in pks], c="limegreen", s=45,
                       marker="s", edgecolors="black", linewidths=0.5, zorder=3)
        ax.set_title(f"step {step:>3}   |   AGV=blue (dark=loaded)  picker=green  "
                     f"DISTURBANCE=black  ({len(dist)} active)")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlim(-0.5, W - 0.5); ax.set_ylim(H - 0.5, -0.5)

    anim = FuncAnimation(fig, draw, frames=len(frames), interval=120)
    os.makedirs("results", exist_ok=True)
    anim.save(OUT, writer=PillowWriter(fps=8))
    plt.close(fig)
    total_spawned = len({tuple(c) for _, _, _, d in frames for c in d})
    print(f"wrote {OUT}  ({STEPS} steps, ~{total_spawned} distinct cells disturbed over the run)")


if __name__ == "__main__":
    main()
