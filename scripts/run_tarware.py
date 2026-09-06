"""Run the base TA-RWARE environment (Stage 0 substrate).

This is the entry point for the adopted simulator: it instantiates a TA-RWARE
warehouse, runs an episode with either the built-in FIFO nearest-agent
heuristic (our head-to-head baseline) or random actions, and reports the
info-dict statistics that map onto our evaluation metrics:

    shelf_deliveries          -> throughput
    clashes                   -> collisions
    stucks                    -> stuck/stranding proxy
    *_distance_travelled      -> energy proxy
    *_idle_time               -> idle time

Everything here is *unmodified* TA-RWARE. Our own rulebook (battery,
disturbances, believed-state rollout, Parts A-D) will be layered on top in
later work; this script exists to prove the substrate runs end-to-end.

Examples
--------
    python scripts/run_tarware.py --policy heuristic --episodes 3
    python scripts/run_tarware.py --env tarware-tiny-3agvs-2pickers-globalobs-v1 --render
"""

from __future__ import annotations

import argparse
import time
import warnings

import gymnasium as gym

import tarware  # noqa: F401  (registers the tarware-* gym ids on import)
from tarware.heuristic import heuristic_episode


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the base TA-RWARE environment.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--env",
        default="tarware-tiny-3agvs-2pickers-globalobs-v1",
        help="Registered TA-RWARE gym id to run.",
    )
    p.add_argument(
        "--policy",
        choices=["heuristic", "random"],
        default="heuristic",
        help="'heuristic' = built-in FIFO nearest-agent baseline; 'random' = sampled actions.",
    )
    p.add_argument("--episodes", type=int, default=1, help="Number of episodes to run.")
    p.add_argument("--seed", type=int, default=0, help="Base seed (episode i uses seed+i).")
    p.add_argument("--render", action="store_true", help="Render the environment in a window (works for both policies).")
    p.add_argument(
        "--fps",
        type=float,
        default=0.0,
        help="Throttle rendering to this many steps/sec so it's watchable (0 = full speed). Only affects --render.",
    )
    return p.parse_args()


def throttle_render(env, fps: float) -> None:
    """Wrap the (unwrapped) env's render method to sleep 1/fps after each frame.

    Done as an instance-level wrapper so both the heuristic (which renders inside
    vendored TA-RWARE code) and our random loop slow down uniformly, without
    editing any vendored files.
    """
    if fps <= 0:
        return
    u = env.unwrapped
    original_render = u.render
    delay = 1.0 / fps

    def throttled(*args, **kwargs):
        result = original_render(*args, **kwargs)
        time.sleep(delay)
        return result

    u.render = throttled


def summarize(infos: list[dict]) -> dict:
    """Collapse a list of per-step info dicts into episode totals."""
    totals = {
        "deliveries": sum(i.get("shelf_deliveries", 0) for i in infos),
        "clashes": sum(i.get("clashes", 0) for i in infos),
        "stucks": sum(i.get("stucks", 0) for i in infos),
        "steps": len(infos),
    }
    last = infos[-1] if infos else {}
    totals["agvs_distance"] = last.get("agvs_distance_travelled", 0)
    totals["pickers_distance"] = last.get("pickers_distance_travelled", 0)
    # Throughput in the doc's units: tasks completed per 1,000 simulation steps.
    totals["throughput_per_1k"] = (
        1000.0 * totals["deliveries"] / totals["steps"] if totals["steps"] else 0.0
    )
    return totals


def run_heuristic_episode(env, seed: int, render: bool) -> dict:
    infos, global_return, _agent_returns = heuristic_episode(env.unwrapped, render, seed)
    stats = summarize(infos)
    stats["global_return"] = global_return
    return stats


def run_random_episode(env, seed: int, render: bool = False) -> dict:
    # tarware's reset returns just the observation tuple (older gym convention).
    env.reset(seed=seed)
    infos: list[dict] = []
    done = False
    while not done:
        if render:
            env.unwrapped.render(mode="human")
        actions = env.action_space.sample()
        _obs, _reward, terminated, truncated, info = env.step(actions)
        infos.append(info)
        done = all(terminated) or all(truncated)
    return summarize(infos)


def main() -> None:
    warnings.filterwarnings("ignore")
    args = parse_args()
    env = gym.make(args.env)
    if args.render:
        throttle_render(env, args.fps)
    print(f"env: {args.env}")
    u = env.unwrapped
    print(
        f"agents: {u.num_agents} ({u.num_agvs} AGVs + {u.num_pickers} pickers) "
        f"| grid (rows, cols): {u.grid_size} | actions/agent: {u.action_size}"
    )
    print(f"policy: {args.policy} | episodes: {args.episodes} | base seed: {args.seed}")
    print("-" * 78)

    for i in range(args.episodes):
        seed = args.seed + i
        start = time.time()
        if args.policy == "heuristic":
            stats = run_heuristic_episode(env, seed, args.render)
        else:
            stats = run_random_episode(env, seed, args.render)
        elapsed = time.time() - start
        fps = stats["steps"] / elapsed if elapsed else float("inf")
        print(
            f"ep {i:>3} (seed {seed:>3}) | "
            f"deliveries={stats['deliveries']:>4} | "
            f"throughput/1k={stats['throughput_per_1k']:>6.2f} | "
            f"clashes={stats['clashes']:>4} | "
            f"stucks={stats['stucks']:>4} | "
            f"steps={stats['steps']:>4} | "
            f"{fps:>7.1f} steps/s"
        )

    env.close()


if __name__ == "__main__":
    main()
