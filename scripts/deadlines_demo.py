"""Demo: feed a deadlines doc into wwm_sim and attach deadlines to tasks.

Reads a task->deadline list (file OR pasted text), attaches each deadline onto the
matching shelf/task, and prints the current tasks with their deadlines. This is
PLUMBING only — no deadline model/generation yet.

    python scripts/deadlines_demo.py                             # uses data/deadlines_example.txt
    python scripts/deadlines_demo.py --file my_deadlines.txt     # your own file
    python scripts/deadlines_demo.py --text "15 200; 42 180"     # or paste inline
"""
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.deadlines import load_deadlines, attach_deadlines, task_deadlines


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load deadlines from a doc and attach to tasks.")
    p.add_argument("--env", default="wwm_sim-tiny-3agvs-2pickers-globalobs-v1")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--file", default="data/deadlines_example.txt",
                   help="Path to a task->deadline list (or use --text).")
    p.add_argument("--text", default=None,
                   help="Inline deadline text instead of a file, e.g. '15 200; 42 180' "
                        "(use newlines or ; between entries).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    env = gym.make(args.env).unwrapped
    env.reset(seed=args.seed)

    source = args.text.replace(";", "\n") if args.text else args.file
    deadlines = load_deadlines(source)
    n = attach_deadlines(env, deadlines)

    print(f"env: {args.env} | seed {args.seed}")
    print(f"loaded {len(deadlines)} deadline entries; attached to {n} shelves")
    print("-" * 46)
    print("CURRENT TASKS (request queue) and their deadlines:")
    for sid, dl in task_deadlines(env):
        print(f"  shelf {sid:>3}  ->  deadline {dl if dl is not None else '(none)'}")
    missing = [sid for sid, dl in task_deadlines(env) if dl is None]
    if missing:
        print(f"\n  note: {len(missing)} current tasks had no deadline in the doc: {missing}")


if __name__ == "__main__":
    main()
