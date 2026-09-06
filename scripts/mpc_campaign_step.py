"""SELF-UPDATING campaign driver (USER RULE 2026-08-16: "continuously running and/or updating
depending on if beating a significance threshold after the first some tests").

Each invocation makes ONE move, chosen sequentially from the evidence so far:
  1. DEEPEN: any config whose pooled z sits in the uncertain band (0.8 <= |z| < 2) with seed
     budget left gets another disjoint 36-seed block -- sequential testing until it resolves.
  2. EXPLORE: otherwise, run the next unexplored config from the frontier.
Verdicts per config: |z| >= 2 -> resolved (MPC ADOPTED if positive, FIXED RETAINED if negative);
z < 0.8 after 72+ seeds -> flat (fixed constants fine there). Pooling is Stouffer over each
config's independent per-block t stats (blocks use disjoint seed sets). Status is rewritten to
results/mpc_status.md every step. Run me again after each batch completes -- forever.
"""
import csv
import math
import os
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "results", "mpc_campaign.csv")
STATUS = os.path.join(ROOT, "results", "mpc_status.md")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

# disjoint 36-seed blocks (mixed off-peak/peak halves); block 0 was the first sweep
BLOCKS = [
    list(range(1, 19)) + list(range(73, 91)),
    list(range(19, 37)) + list(range(91, 109)),
    list(range(37, 55)) + list(range(109, 127)),
    list(range(55, 73)) + list(range(127, 145)),
]

FRONTIER = [
    "large-8-6", "medium-5-4", "small-4-3", "extralarge-12-8", "large-12-8",
    "large-5-4", "extralarge-16-9", "medium-8-6",
    # round 2: fleet extremes + dual-carriageway geometry
    "large-16-9", "medium-12-8", "extralarge-8-6", "largedual-8-6",
    "largedual-12-8", "small-8-6", "extralarge-19-9", "mediumdual-5-4",
    "large-3-2", "tiny-4-3", "largedual-16-9", "extralargedual-12-8",
    # era 2: remaining permutations
    "medium-19-5", "extralargedual-16-9", "largedual-3-2", "small-3-2",
    "extralarge-19-5", "mediumdual-8-6", "extralargedual-8-6", "tiny-8-6",
    # era 3: last permutations
    "tinydual-4-3", "smalldual-8-6", "tiny-3-2", "mediumdual-16-9",
    "extralargedual-5-4", "largedual-19-9", "small-5-4", "medium-8-9",
    # round 3: asymmetric AGV:picker ratios + remaining extremes
    "large-8-3", "large-8-9", "medium-16-9", "extralarge-5-4", "largedual-5-4",
    "smalldual-4-3", "extralarge-16-6", "medium-3-2", "large-19-5", "mediumdual-12-8",
]


def load():
    runs = defaultdict(list)          # config -> [(t_stat, n_seeds), ...] from mpc rows
    if os.path.exists(CSV):
        for r in csv.DictReader(open(CSV, encoding="utf-8")):
            if r["arm"] == "mpc":
                runs[r["config"]].append((float(r["t_stat"]), int(r["n_seeds"])))
    return runs


def pooled_z(ts):
    return sum(t for t, _ in ts) / math.sqrt(len(ts)) if ts else 0.0


def decide(runs):
    # 1. deepen the most promising uncertain config with budget left
    cands = []
    for cfg, ts in runs.items():
        z = pooled_z(ts)
        if 0.8 <= abs(z) < 2.0 and len(ts) < len(BLOCKS):
            cands.append((abs(z), cfg))
    if cands:
        cands.sort(reverse=True)
        cfg = cands[0][1]
        return cfg, BLOCKS[len(runs[cfg])], "deepen (pooled z=%.2f after %d block(s))" % (
            pooled_z(runs[cfg]), len(runs[cfg]))
    # 2. explore the next new config
    for cfg in FRONTIER:
        if cfg not in runs:
            return cfg, BLOCKS[0], "explore (new config)"
    # 3. frontier exhausted: deepen whatever is least sampled and unresolved
    open_cfgs = [(len(ts), cfg) for cfg, ts in runs.items()
                 if abs(pooled_z(ts)) < 2.0 and len(ts) < len(BLOCKS)]
    if open_cfgs:
        open_cfgs.sort()
        cfg = open_cfgs[0][1]
        return cfg, BLOCKS[len(runs[cfg])], "deepen (frontier exhausted)"
    return None, None, "all configs resolved -- extend FRONTIER"


def write_status(runs, action_line):
    total_z = pooled_z([(pooled_z(ts), 0) for ts in runs.values()]) if runs else 0.0
    lines = ["# MPC campaign status (auto-updated)\n",
             "overall pooled z across %d configs: %+.2f\n" % (len(runs), total_z),
             "| config | blocks | pooled z | verdict |", "|---|---|---|---|"]
    for cfg in sorted(runs, key=lambda c: -abs(pooled_z(runs[c]))):
        z = pooled_z(runs[cfg])
        v = ("MPC ADOPTED" if z >= 2.0 else
             "FIXED RETAINED" if z <= -2.0 else
             "flat" if len(runs[cfg]) >= 2 and abs(z) < 0.8 else "testing")
        lines.append("| %s | %d | %+.2f | %s |" % (cfg, len(runs[cfg]), z, v))
    lines.append("\nlast action: %s\n" % action_line)
    open(STATUS, "w", encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    runs = load()
    cfg, seeds, why = decide(runs)
    if cfg is None:
        write_status(runs, why)
        print(why)
        sys.exit(0)
    action = "%s on %s (%d seeds): %s" % (
        "run", cfg, len(seeds), why)
    print(action)
    env = dict(os.environ, CONFIG=cfg, SEEDLIST=",".join(map(str, seeds)))
    r = subprocess.run([PY, os.path.join(ROOT, "scripts", "m3_mpc.py")],
                       env=env, cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout[-2000:])
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-2000:])
        sys.exit(1)
    write_status(load(), action)
