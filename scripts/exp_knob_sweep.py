"""M1 knob sweep: tune the DEADLINE-term weight (URG_W) and PICKER smartness (RATE_ALPHA) as a function
of regime (daylist/stream) and fleet size. Base = _PkRate (champion + urgency + value-rate pickers).

One process = one (regime, fleet, knob) cell; sweeps the knob's VALUES over SEEDS seeds, holding the
OTHER knob fixed. Writes a long-format CSV (regime,agvs,pickers,knob,value,seed,on_time_value),
appended after each knob value so the visual can update live.

Env: ENVID, REGIME(daylist|stream), KNOB(URG_W|RATE_ALPHA), VALUES(csv), ALPHA_FIX, URGW_FIX,
     SEEDS(120), SEED_OFFSET(0), OUT.
URG_W=0 -> no deadline term (pure value in makeable tier). RATE_ALPHA=0 -> value-only picker (no distance).
"""
import collections
import csv
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.demand import DemandModel
from congestion_policies import _PkRate, _SqWidePkRate, _SqWidePkRateUrg, _SqWidePkRateAdaptive

# sqwidepr = fixed URG_W=8 base. champion = REGIME-CONDITIONAL URG_W (0 daylist / 8 stream) -> sweep other knobs on top.
BASES = {"sqwidepr": _SqWidePkRate, "sqwideprurg": _SqWidePkRateUrg, "pkrate": _PkRate,
         "champion": _SqWidePkRateAdaptive}
BASE = BASES[os.environ.get("BASE", "sqwidepr")]     # default = the SEQUENCER champion (deployed)

ENV = os.environ["ENVID"]
REGIME = os.environ.get("REGIME", "daylist")
KNOB = os.environ["KNOB"]                                   # URG_W | RATE_ALPHA
VALUES = [float(v) for v in os.environ["VALUES"].split(",")]
ALPHA_FIX = float(os.environ.get("ALPHA_FIX", "5"))
URGW_FIX = float(os.environ.get("URGW_FIX", "8"))
SEEDS = int(os.environ.get("SEEDS", "120"))
SEED_OFFSET = int(os.environ.get("SEED_OFFSET", "0"))
STEPS = 500
OUT = os.environ["OUT"]
_m = re.search(r"(\d+)agvs-(\d+)pickers", ENV)
AGVS, PICKERS = int(_m.group(1)), int(_m.group(2))

# lock lives OUTSIDE results/knobsweep/ so stray `Remove-Item results/knobsweep/*.lock` re-spawns can't wipe it
os.makedirs("results/locks", exist_ok=True)
LOCKPATH = os.path.join("results", "locks", os.path.basename(OUT) + ".lock")
LOCK_STALE = 180.0        # a lock whose heartbeat (mtime) is older than this = dead owner -> steal it


def _acquire_lock():
    import time
    while True:
        try:
            fd = os.open(LOCKPATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # atomic: only one wins
            os.write(fd, str(os.getpid()).encode()); os.close(fd)
            return True
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(LOCKPATH)
            except OSError:
                continue
            if age < LOCK_STALE:
                return False                           # a live instance owns this cell
            try:
                os.remove(LOCKPATH)                    # stale (dead owner) -> remove and retry create
            except OSError:
                pass


def make_cls(value):
    attrs = {"RATE_ALPHA": ALPHA_FIX, "URG_W": URGW_FIX}
    attrs[KNOB] = value
    return type(f"_Sw_{KNOB}_{value}", (BASE,), attrs)


def run(seed, cls):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    if REGIME == "daylist":
        env.demand_model.seed_day_list(env, horizon=STEPS)
    else:
        env.demand_model.seed_initial(env, n=12)
    ctrl = cls(env)
    onv = 0.0
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t <= o.deadline:
                onv += o.value
        done = all(term) or all(trunc)
    return round(onv, 1)


def _write(rows):
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["regime", "agvs", "pickers", "knob", "value", "seed", "on_time_value"])
        w.writerows(rows)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows = []
    have = collections.defaultdict(set)                      # value -> set of seeds already saved
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["regime"], int(r["agvs"]), int(r["pickers"]), r["knob"],
                             float(r["value"]), int(r["seed"]), float(r["on_time_value"])))
                have[float(r["value"])].add(int(r["seed"]))
    target = list(range(SEED_OFFSET, SEED_OFFSET + SEEDS))
    for v in VALUES:
        missing = [s for s in target if s not in have[v]]    # SEED-LEVEL resume: only run what's missing
        if not missing:
            print(f"{REGIME} {AGVS}x{PICKERS} {KNOB}={v}: complete ({len(have[v])}), skip", flush=True)
            continue
        cls = make_cls(v)
        for k, s in enumerate(missing):
            onv = run(s, cls)
            rows.append((REGIME, AGVS, PICKERS, KNOB, v, s, onv))
            have[v].add(s)
            try:
                os.utime(LOCKPATH, None)                      # heartbeat
            except OSError:
                pass
            if (k + 1) % 10 == 0:                             # save every 10 seeds (lose <=10 on a kill)
                _write(rows)
        _write(rows)
        vv = [r[6] for r in rows if r[4] == v]
        print(f"{REGIME} {AGVS}x{PICKERS} {KNOB}={v}: mean {np.mean(vv):.1f}  (n={len(vv)})", flush=True)


if __name__ == "__main__":
    if not _acquire_lock():
        print(f"lock fresh ({LOCKPATH}) -> another instance owns this cell, exiting", flush=True)
        sys.exit(0)
    try:
        main()
    finally:
        try:
            os.remove(LOCKPATH)
        except OSError:
            pass
