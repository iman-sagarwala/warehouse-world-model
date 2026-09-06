"""Autonomous sweep DRIVER — CONVERGENT design (robust to duplicate drivers, teardowns, re-spawns).
Repeatedly scans every cell for ACTUAL completeness (each value x SEEDS seeds present in its CSV) and
launches workers only for cells that are incomplete AND not currently locked by another worker. Stops
only when every cell is genuinely complete. Cell locks (in results/locks/, outside the knobsweep glob)
prevent same-cell collisions; seed-level resume in exp_knob_sweep prevents lost work.

PHASE 1 = urgency (AGV URG_W + picker PK_URG_W), matched fleets 4x4..9x9, both worlds.
PHASE 2 = smart pickers (RATE_ALPHA). Regenerates bar-graphs each pass.
Run in background:  python scripts/exp_urg_driver.py
"""
import collections
import csv
import glob
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
AGVS_RANGE = [4, 5, 6, 7, 8, 9]
PICKERS_RANGE = [4, 5, 6, 7, 8, 9]
REGIMES = os.environ.get("REGIMES", "daylist,stream").split(",")   # e.g. REGIMES=daylist to skip stream
SEEDS = int(os.environ.get("SEEDS", "120"))
CONC = int(os.environ.get("CONC", "4"))
MODE = os.environ.get("MODE", "grid")
GRID = [(a, p) for a in AGVS_RANGE for p in PICKERS_RANGE]     # full AGV x picker 4-9 ratio grid
if MODE == "wsync":                         # coordinate-ascent step 2: W_SYNC on FULL GRID, base = adaptive
    FLEET_PAIRS = GRID                        #  champion (regime-conditional URG_W already baked in)
    SWEEP = [("champion", "W_SYNC", "0.0,0.15,0.3,0.5")]
elif MODE == "urgfill":                     # PAPER FIX: widen the URG_W comb to {0,4,8,12,16} on ALL 72
    FLEET_PAIRS = GRID                        #  cells. 8 cells already had 12/16 (leftovers from an early
    SWEEP = [("sqwidepr", "URG_W", "0,4,8,12,16")]   # wider run) while 64 had only {0,4,8} -> per-cell
    #  argmax was best-of-5 vs best-of-3 (biased), AND the chosen URG_W=8 sat at the comb EDGE, so we
    #  could not show the curve TURNING OVER. Base MUST stay `sqwidepr` to match the original sweep.
    #  Seed-level resume means only the missing (value,seed) pairs actually run: ~15,360 of 43,200.
elif MODE == "alpha":                       # PAPER GAP: RATE_ALPHA (picker distance sensitivity) was set
    FLEET_PAIRS = GRID                        #  to 5 by an EARLY sweep on the deployment fleets only --
    SWEEP = [("champion", "RATE_ALPHA", "3,4,5,6,7")]   # never on the 72-cell ratio grid at 120 seeds.
    #  Comb brackets the incumbent 5 on both sides (prior note: 3->4->5 climbs, 6 turns down), so the
    #  curve should peak in the interior. Base = `champion` (best URG_W baked in) to keep the
    #  coordinate-ascent chain consistent with the W_SYNC and CONG/SEQ_DEPTH steps.
elif MODE == "seqdepth":                    # M1 final knob. SEQ_DEPTH ONLY -- the CONG pair is SKIPPED
    FLEET_PAIRS = GRID                        #  (predicted regime-invariant + null; see NOTES 2026-07-31
    SWEEP = [("champion", "SEQ_DEPTH", os.environ.get("SEQ_COMB", "3,5,8"), ["daylist"]),
             # STREAM MECHANISM ABLATION (not a knob sweep): depth 0 DISABLES the sequencer entirely
             # ("0 = champion exactly", PartACongestionSeqController docstring). We proved depths 3/5/8
             # are BIT-IDENTICAL on the stream -- but depth 0 was never tested, so we do not yet know
             # whether the sequencer does ANYTHING there. If 0 == 3, the sequencer is DEAD WEIGHT on the
             # stream (pay full rollout cost for zero value -> cut it there, real runtime win + a sharp
             # paper finding). If 0 < 3, it earns its place and only its DEPTH is irrelevant.
             ("champion", "SEQ_DEPTH", "0,3", ["stream"])]
    #  MEASURED 2026-07-31 (first 10 cells/regime, then STOPPED and RE-SCOPED to daylist + comb {1,2,3,5}):
    #   - STREAM IS COMPLETELY INERT: depths 3/5/8 give BIT-IDENTICAL results on 120/120 seeds in all 10
    #     cells. Mechanism: `_sim_core` can only use the CURRENTLY VISIBLE queue (env.request_queue) and
    #     `_future_arrivals` returns [] -> on the stream the imagined queue EMPTIES long before even depth
    #     3's 225-step horizon binds. There is nothing to look ahead AT. -> stream dropped via REGIMES.
    #   - DAYLIST IS LOAD-BEARING: 115-118 of 120 seeds change per cell; depth 3 is worse (-2.40, t=-2.24).
    #   - SATURATION: `horizon = min(now + SEQ_DEPTH*75, 500)`. From t=125 onward depths 5 and 8 BOTH hit
    #     the 500 cap and are identical, so "8 vs 5" only probes the first quarter of the day (hence its
    #     weak -0.61). Max useful depth ~ 500/75 = 6.7 -> BRACKETED BY CONSTRUCTION at the top; extending
    #     above 8 is meaningless. The real curve lives at the SHORT end -> comb {1,2,3,5}.
    #  "SPACE knobs are regime-invariant, FUTURE knobs are
    #  not"). SEQ_DEPTH = the sequencer's lookahead horizon = a FUTURE knob -> the ONLY remaining knob
    #  that TESTS that principle rather than confirming it again. Default 5 is interior to {3,5,8}.
    #  NOTE: cost per run RISES with depth (depth 8 simulates more), so this is slower than run-count
    #  alone suggests. If 8 wins, extend the comb upward before believing it (bracketing rule).
elif MODE == "rest":                        # step 3: CONG_LAMBDA/WEIGHT + SEQ_DEPTH on grid, base = BASE_REST
    FLEET_PAIRS = GRID                        #  (a champion variant with best URG_W + best W_SYNC baked in)
    _b = os.environ.get("BASE_REST", "champion")
    SWEEP = [(_b, "CONG_LAMBDA", "0.0,0.15,0.3,0.5"),
             (_b, "CONG_WEIGHT", "0.0,0.15,0.3,0.5"),
             (_b, "SEQ_DEPTH", "3,5,8")]
elif MODE == "flat":                        # (deprecated) ratio-flat knobs on deployment fleet only
    FLEET_PAIRS = [(8, 4), (8, 8)]
    SWEEP = [("sqwidepr", "W_SYNC", "0.0,0.15,0.3,0.5"),
             ("sqwidepr", "CONG_LAMBDA", "0.0,0.15,0.3,0.5"),
             ("sqwidepr", "CONG_WEIGHT", "0.0,0.15,0.3,0.5"),
             ("sqwidepr", "SEQ_DEPTH", "3,5,8")]
else:                                       # M1 ratio grid: URG_W across AGV x picker 4-9
    FLEET_PAIRS = GRID
    SWEEP = [("sqwidepr", "URG_W", "0,4,8")]
os.makedirs("results/knobsweep", exist_ok=True)
os.makedirs("results/locks", exist_ok=True)
LOCK_STALE = 180.0


def all_cells():
    for entry in SWEEP:
        base, knob, values = entry[0], entry[1], entry[2]
        regimes = entry[3] if len(entry) > 3 else REGIMES      # optional PER-SWEEP regime list
        for (agv, pk) in FLEET_PAIRS:
            env_id = f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1"
            for regime in regimes:
                out = f"results/knobsweep/{regime}_{agv}agv{pk}pk_{knob}.csv"
                yield {"env": env_id, "regime": regime, "base": base, "knob": knob,
                       "values": [float(v) for v in values.split(",")], "vstr": values,
                       "out": out, "agv": agv, "pk": pk}


def complete(cell):
    if not os.path.exists(cell["out"]):
        return False
    have = collections.defaultdict(set)
    try:
        with open(cell["out"]) as fh:
            for r in csv.DictReader(fh):
                have[float(r["value"])].add(int(r["seed"]))
    except Exception:
        return False
    return all(len(have[v]) >= SEEDS for v in cell["values"])


def locked(cell):
    lp = os.path.join("results", "locks", os.path.basename(cell["out"]) + ".lock")
    return os.path.exists(lp) and (time.time() - os.path.getmtime(lp)) < LOCK_STALE


GLOBAL_CAP = int(os.environ.get("GLOBAL_CAP", "7"))   # max workers across ALL drivers (cores-1); self-limits duplicates


def active_workers():
    now = time.time()
    n = 0
    for f in glob.glob("results/locks/*.csv.lock"):    # one lock per running worker (excludes _driver.lock)
        try:
            if now - os.path.getmtime(f) < LOCK_STALE:
                n += 1
        except OSError:
            pass
    return n


def launch(cell):
    e = dict(os.environ, ENVID=cell["env"], REGIME=cell["regime"], BASE=cell["base"],
             KNOB=cell["knob"], VALUES=cell["vstr"], SEEDS=str(SEEDS), OUT=cell["out"],
             PYTHONIOENCODING="utf-8")
    logf = open(cell["out"].replace(".csv", ".log"), "a")
    return subprocess.Popen([PY, "-u", "scripts/exp_knob_sweep.py"], env=e,
                            stdout=logf, stderr=subprocess.STDOUT), logf


def regen():
    try:
        subprocess.run([PY, "scripts/viz_urg_grid.py"], timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main():
    cells = list(all_cells())
    print(f"driver(convergent): {len(cells)} cells, conc={CONC}, seeds={SEEDS}", flush=True)
    running = []
    while True:
        incomplete = [c for c in cells if not complete(c)]
        if not incomplete and not running:
            break
        # reap finished workers
        still = []
        for p, logf, out in running:
            if p.poll() is None:
                still.append((p, logf, out))
            else:
                logf.close()
        if len(still) != len(running):
            regen()
        running = still
        # launch more incomplete+unlocked cells up to CONC
        for c in incomplete:
            if len(running) >= CONC or active_workers() >= GLOBAL_CAP:
                break                                   # global cap: total workers across ALL drivers <= GLOBAL_CAP
            if locked(c) or any(o == c["out"] for _, _, o in running):
                continue
            p, logf = launch(c)
            running.append((p, logf, c["out"]))
            print(f"  START {c['regime']} {c['agv']}agv/{c['pk']}pk {c['knob']}", flush=True)
        time.sleep(15)
    regen()
    print("driver: ALL CELLS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
