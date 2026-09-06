"""Demo: the Beta rumor map OBSERVES disturbances into a calibrated, decaying belief (Part 2).
We do NOT act on it yet (that's Part B support + task selection, later). This just shows the map
accumulates belief where disturbances actually were, purely from sightings near robots.

Run the champion with disturbances on; each step, update the rumor map from what robots can see;
then check the map's hotspots against where disturbances actually spawned.
Run: python scripts/demo_rumor.py
"""
import os
import sys
import warnings

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_k] = "1"
sys.path.insert(0, "scripts")
warnings.filterwarnings("ignore")

import numpy as np
import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values
from wwm_sim.rumor_map import BetaRumorMap
from congestion_policies import PartACongestionController

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
DL = load_deadlines("data/deadlines_example.txt")
VL = load_values("data/values_example.txt")


def main():
    seed = 0
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    attach_deadlines(env, DL)
    attach_values(env, VL)
    env.disturb_rate = 0.15
    env._disturb_rng = np.random.RandomState(seed)
    ctrl = PartACongestionController(env)
    rumor = BetaRumorMap(env.grid_size, decay=0.99, sight_radius=5)

    true_counts = np.zeros(env.grid_size, dtype=np.float32)   # ground truth: disturbed-cell-steps
    t = 0
    while t < 500:
        env.step(ctrl.act())
        t += 1
        rumor.update(env)                                     # observe (partial obs, near robots)
        for (y, x) in getattr(env, "disturbed", set()):
            true_counts[y, x] += 1.0

    b = rumor.belief()
    print("=" * 64)
    print("Beta rumor map after 500 steps (disturb_rate=0.15, seed 0)")
    print("=" * 64)
    print(f"cells ever disturbed (ground truth): {(true_counts > 0).sum()}")
    print(f"belief > 0.5 cells (map thinks disturbed): {(b > 0.5).sum()}")
    print("\nTop-10 rumor hotspots  vs  ground-truth disturbance-steps at that cell:")
    for (y, x, p) in rumor.hotspots(10):
        print(f"  cell ({y:>2},{x:>2})  belief={p:.2f}   true_disturbed_steps={int(true_counts[y, x])}")
    # calibration-ish: of the top-20 belief cells, how many were actually ever disturbed?
    hs = rumor.hotspots(20)
    hit = sum(1 for (y, x, _p) in hs if true_counts[y, x] > 0)
    print(f"\nPrecision@20 (top-belief cells that were truly disturbed): {hit}/20")
    print("\n=> The map ACCUMULATES belief where disturbances actually were, from observation alone.")
    print("   It PREDICTS nothing about the future -- disturbances are unpredictable; it only remembers.")


if __name__ == "__main__":
    main()
