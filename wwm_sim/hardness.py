"""wwm_sim.hardness — load per-task SLA HARDNESS (late-decay `g`) and attach to tasks.

Plumbing only (mirrors wwm_sim.values / wwm_sim.deadlines). A task's hardness is the
per-step value-decay `g` applied once it is LATE: delivered-late value = value *
g**lateness. It is a SEPARATE axis from value (how much) and deadline (when):
  * steep g  (~0.90) = HARD SLA — value falls off a cliff the moment you're late.
  * gentle g (~0.995) = SOFT order — value bleeds off slowly; recoverable late.
Two tasks with the same value can have different hardness. None -> the controller's
global default `g`.

File / text format — one task per line, tolerant (whitespace/comma/colon, `#`
comments; a header line like "shelf,g" is skipped automatically):
    15  0.90    # shelf 15 is a HARD SLA (steep decay)
    7,  0.995   # shelf 7 is a SOFT order (gentle decay)
    42: 0.97
"""
from __future__ import annotations

import os
import re


def parse_hardness(text: str) -> dict[int, float]:
    out: dict[int, float] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p for p in re.split(r"[,:\s]+", line) if p]
        if len(parts) < 2:
            continue
        try:
            out[int(parts[0])] = float(parts[1])
        except ValueError:
            continue
    return out


def load_hardness(source: str) -> dict[int, float]:
    """Load hardness from a file PATH or a raw TEXT string (either works)."""
    if os.path.exists(source):
        with open(source, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = source
    return parse_hardness(text)


def attach_hardness(env, hardness: dict[int, float]) -> int:
    """Attach hardness `g` onto env's shelves by id. Returns how many were attached."""
    attached = 0
    for sh in env.shelfs:
        g = hardness.get(sh.id)
        sh.hardness = g
        if g is not None:
            attached += 1
    return attached


def task_hardness(shelf, default: float) -> float:
    """A shelf's late-decay g, falling back to `default` when unset."""
    return default if shelf.hardness is None else shelf.hardness
