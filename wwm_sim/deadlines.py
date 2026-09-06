"""wwm_sim.deadlines — load task deadlines from a doc/text and attach to tasks.

Scope (deliberately minimal): this is PLUMBING only. It does NOT generate
deadlines from any model/distribution — it just reads a human-editable list
(task -> deadline) and attaches each deadline onto the matching shelf/task.
Generating realistic deadlines is a later step.

A task == a requested shelf, identified by its shelf id. A deadline is the
absolute simulation step by which that shelf should be delivered (None = no
deadline). (Relative / arrival-based deadlines are a future refinement.)

File / text format — one task per line, very tolerant:
    # comments allowed
    15  200      # shelf 15 due by step 200   (whitespace-separated)
    7, 180       # or comma
    42: 260      # or colon
A header line like "task,deadline" is skipped automatically (non-integer).

Usage
-----
    from wwm_sim.deadlines import load_deadlines, attach_deadlines
    dl = load_deadlines("data/deadlines_example.txt")   # path OR raw text
    env.reset(seed=0)
    n = attach_deadlines(env, dl)
"""
from __future__ import annotations

import os
import re


def parse_deadlines(text: str) -> dict[int, int]:
    """Parse deadline lines from a raw string. Returns {shelf_id: deadline}."""
    out: dict[int, int] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()  # strip comments + whitespace
        if not line:
            continue
        # split on comma / colon / whitespace
        parts = [p for p in re.split(r"[,:\s]+", line) if p]
        if len(parts) < 2:
            continue
        try:
            task_id, deadline = int(parts[0]), int(parts[1])
        except ValueError:
            continue  # header or malformed line -> skip quietly
        out[task_id] = deadline
    return out


def load_deadlines(source: str) -> dict[int, int]:
    """Load deadlines from a file PATH or from a raw TEXT string (either works)."""
    if os.path.exists(source):
        with open(source, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = source  # treat the argument itself as the deadline text
    return parse_deadlines(text)


def attach_deadlines(env, deadlines: dict[int, int]) -> int:
    """Attach deadlines onto env's shelves by id. Returns how many were attached.

    Shelves absent from the mapping get deadline = None. Call AFTER env.reset().
    """
    attached = 0
    for sh in env.shelfs:
        dl = deadlines.get(sh.id)
        sh.deadline = dl
        if dl is not None:
            attached += 1
    return attached


def task_deadlines(env) -> list[tuple[int, int | None]]:
    """Convenience: (shelf_id, deadline) for the CURRENT tasks (request queue)."""
    return [(sh.id, sh.deadline) for sh in env.request_queue]
