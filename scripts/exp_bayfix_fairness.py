"""Is retiring the bay pods actually unfair to the baseline? (2026-09-20)

NOTES 2026-09-06 concluded the bay-pod fix must not ship because it is not neutral between
arms: with the pods genuinely gone, the vendored FIFO was said to park pods on charger bays
while the champion does not, costing FIFO 39 value on stream and inflating our margin
62.6% -> 80.7%.

That conclusion rests on FIFO having no bay-exclusion notion. But the BASE controller in
scripts/sim_dashboard.py -- which FIFOController inherits -- already filters `env._charger_bays`
out of its empty-slot search. Whether that guard predates the 2026-09-06 measurement cannot be
settled from git (the repo was squashed at the open-source release on the same day), so this
script settles it by measurement instead.

Two floors, both arms, paired seeds:
    legacy   pods left on the bays (the floor every published number was measured on)
    retired  env._removed_shelf_ids populated, so _recalc_grid honours setup_bays' strip

If FIFO's drop under `retired` is small, the fairness objection dissolves and the fix can ship;
if FIFO drops ~39 on stream, the 2026-09-06 reading stands and the env-level work is required
first.

    BAYSEEDS=1-48 NPROC=8 python scripts/exp_bayfix_fairness.py
"""
from __future__ import annotations

import os
import sys
import csv
import io
import statistics as st
import multiprocessing as mp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# NB: not SEEDS -- m3_battery.py int()s that at import, so a range string kills every worker.
_s = os.environ.get("BAYSEEDS", "1-48")
if "-" in _s:
    _a, _b = _s.split("-")
    SEEDS = list(range(int(_a), int(_b) + 1))
else:
    SEEDS = [int(x) for x in _s.split(",")]
NPROC = int(os.environ.get("NPROC", "8"))
OUT = os.environ.get("OUT", os.path.join(ROOT, "results", "bayfix_fairness.csv"))
STEPS = 500


def run(job):
    seed, arm, floor = job
    import numpy as np
    from record_race import build
    from sim_dashboard import FIFOController
    from sim_priority import RushValueController

    env, ctrl = build("large-8-6", seed, stream=True)

    # FLOOR. `legacy` is the published floor: setup_bays strips the pods and _recalc_grid puts
    # them straight back, so the 2026-08-14 rule is cosmetic. `retired` honours the strip.
    env._removed_shelf_ids = set(env._charger_bay_ids) if floor == "retired" else set()

    if arm in ("fifo", "rush"):
        # baselines run with free energy, as everywhere else in this project
        ctrl = FIFOController(env) if arm == "fifo" else RushValueController(env)

    onv = 0.0
    bay_drops = 0
    bays = set(getattr(env, "_charger_bays", ()) or ())
    for t in range(STEPS):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        # count pods sitting on bay cells: the behaviour the fairness objection is about
        if bays and t % 25 == 0:
            from wwm_sim.warehouse import CollisionLayers as CL
            bay_drops += sum(1 for (x, y) in bays if env.grid[CL.SHELVES, y, x])
    return (seed, arm, floor, round(onv, 1), bay_drops)


def main():
    jobs = [(s, a, f) for s in SEEDS for a in ("fifo", "mpc") for f in ("legacy", "retired")]
    with mp.Pool(NPROC) as pool:
        rows = pool.map(run, jobs, chunksize=1)

    with io.open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["seed", "arm", "floor", "onv", "bay_occupancy_samples"])
        w.writerows(rows)

    by = {}
    for seed, arm, floor, onv, bd in rows:
        by.setdefault((arm, floor), {})[seed] = (onv, bd)

    print("\n%-6s %-9s %9s %9s %12s" % ("arm", "floor", "mean onv", "vs legacy", "bay pods"))
    for arm in ("fifo", "mpc"):
        base = st.mean(v[0] for v in by[(arm, "legacy")].values())
        for floor in ("legacy", "retired"):
            d = by[(arm, floor)]
            m = st.mean(v[0] for v in d.values())
            bd = st.mean(v[1] for v in d.values())
            print("%-6s %-9s %9.2f %9s %12.2f"
                  % (arm, floor, m, "-" if floor == "legacy" else "%+.2f" % (m - base), bd))

    def margin(floor):
        f = st.mean(by[("fifo", floor)][s][0] for s in SEEDS)
        c = st.mean(by[("mpc", floor)][s][0] for s in SEEDS)
        return 100.0 * (c - f) / f

    print("\nmargin over FIFO:  legacy %+.1f%%   retired %+.1f%%   (shift %+.1f pts)"
          % (margin("legacy"), margin("retired"), margin("retired") - margin("legacy")))
    print("\nREAD: a large negative FIFO shift means the 2026-09-06 fairness objection stands and")
    print("the fix needs env-level bay keepout first. A small shift means the base controller's")
    print("own bay filter already protects it, and the fix can ship.")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
