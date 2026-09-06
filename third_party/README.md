# Vendored dependencies

Two upstream projects are used as local editable checkouts rather than as PyPI packages, because
each needs a small local patch. They are **not committed** to this repository; restore them with the
pinned commit plus the patch file beside this README.

Both are MIT-licensed; see the top-level `LICENSE`.

## TA-RWARE — the base simulator and the FIFO baseline

Upstream: <https://github.com/uoe-agents/task-assignment-robotic-warehouse>
Pinned commit: **`6109c33`**
Patch: [`tarware-local.patch`](tarware-local.patch) — packaging only (a stale `README.txt`
reference and an explicit package list, so `pip install -e .` succeeds). No behaviour changes: this
checkout is our benchmark opponent and is deliberately left untouched.

```sh
git clone https://github.com/uoe-agents/task-assignment-robotic-warehouse.git
git -C task-assignment-robotic-warehouse checkout 6109c33
git -C task-assignment-robotic-warehouse apply ../third_party/tarware-local.patch
.venv/Scripts/python.exe -m pip install -e ./task-assignment-robotic-warehouse --no-deps
```

## pyastar2d (TA-RWARE fork) — the inner-loop A*

Upstream: <https://github.com/raulsteleac/pyastar2d_TARWARE>
Pinned commit: **`ff9257d`**
Patch: [`pyastar2d-local.patch`](pyastar2d-local.patch) — 5 lines in `src/cpp/astar.cpp`.

```sh
git clone https://github.com/raulsteleac/pyastar2d_TARWARE.git
git -C pyastar2d_TARWARE checkout ff9257d
git -C pyastar2d_TARWARE apply ../third_party/pyastar2d-local.patch
.venv/Scripts/python.exe -m pip install -e ./pyastar2d_TARWARE
```

This planner is validated against 1,800 MovingAI MAPF scenarios in `scripts/exp_m5_mapf.py`:
100% solved, 100% shortest on the warehouse and empty maps. On randomly cluttered maps 19 of 200
paths come back 2–4 steps long (mean +0.22) — its heuristic is not tight for 4-connected movement.
Aisle topology leaves no room for that, so it does not affect any result here, but the planner
should not be described as optimal in general.

## Note on the working copy in this repo

The local `task-assignment-robotic-warehouse/` checkout also carries three untracked leftovers from
Stage 0 — `scripts/generate_data.py`, `scripts/train_delay_head.py` and an 18 MB `data/` directory
of step traces. They belong to the delay-prediction work that was cut (§5.19) and are not needed by
anything in the shipped stack.
