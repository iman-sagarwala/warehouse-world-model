"""Ablation: is congestion layer 2 (predicted next-task routes) load-bearing?

Compares the champion against itself with layer 2 switched off, and against the corrected-anchor
version, under the demand stream. Paired by seed (identical arrival stream per seed).

Run:  python scripts/ablate_l2.py        (SEEDS=30 env var to change)
"""
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from wwm_sim.deadlines import load_deadlines, attach_deadlines
from wwm_sim.values import load_values, attach_values, task_value
from sim_priority import PartAController
from congestion_policies import (PartACongestionController, PartACongestionDockController,
                                 PartACongestionFreeL2Controller, PartACongestionNoL2Controller,
                                 PartACongestionPickerController,
                                 PartACongestionPickerTrafficController,
                                 PartACongestionLoadTimeController,
                                 _Cal0, _Cal2, _Cal4, _Cal7, _Cal10, _Cal14,
                                 _LT1, _LT3, _LT5, _LT8, _LT11, _LT15,
                                 _Depth1, _Depth2, _Depth3, _Depth5,
                                 _D2H0, _D2H20, _D3H0, _D3H20,
                                 _T1, _T2H0, _T3H0, _T2H20,
                                 _Rate20, _Rate40, _Rate80,
                                 _Blend10, _Blend20, _Blend40, _Blend80, _Rate160,
                                 _Adapt2, _Adapt4, _ExploreArm, _VScreen, _VSRate80, _VSBlend40,
                                 _Urg2, _Urg4, _Urg8, _U8P2, _U8P4, _U8P8, _P4,
                                 _Sq0, _Sq1, _Sq2, _Sq3, _Sq5, _Sq8,
                                 _S5M2, _S5M5, _S5M10, _S5T2, _S5T5, _S5T10,
                                 _Sq5S, _SA5, _Pre0, _Pre3, _Pre6, _JOff, _J2, _J3,
                                 _SqNB, _SqNP, _SqNF, _SqDC, _SqP15, _SqWide, _SqAll,
                                 _W8, _W12, _W20, _W25, _OpenLoop, _NoMap,
                                 _SqPacePick, _SqPaceComb, _SqWideNB, _SqPaceStep, _SqPaceCombDL,
                                 _SqPaceClust, _PkCommit, _PkRate, _SqWidePkRate, _SqWidePkRateNP,
                                 _PkRateNoSync, _SqWideFreePk, _PkRate3, _UrgFreePk,
                                 _SqWidePkRateMap, _PkRateCov, _PkRateCov1, _PkRateCov6,
                                 _PkRateUrg, _PkRateCovUrg, _SqWidePkRateUrg, _SqWidePkRateSA,
                                 _SqWidePkRateEV, _SqWidePkRateEV0, _SqWidePkRateEV25, _SqWidePkRateEV35, _SqWidePkRateEV50,
                                 _SqWidePkRateK1, _SqWidePkRateK2, _SqWidePkRateK4, _SqWidePkRateK8,
                                 _SqWidePkRateK2U0, _SqWidePkRateK2U16, _SqWidePkRateAdaptive)

ENV = os.environ.get("ENVID", "wwm_sim-large-8agvs-4pickers-globalobs-v1")
SEED_OFFSET = int(os.environ.get("SEED_OFFSET", "0"))
SEEDS = list(range(SEED_OFFSET, SEED_OFFSET + int(os.environ.get("SEEDS", "30"))))
STEPS = 500
REGIME = os.environ.get("REGIME", "")            # "stream" | "daylist" | "uniform"
DEMAND = (REGIME in ("stream", "daylist")) if REGIME else (os.environ.get("DEMAND", "1") == "1")
_DL = None if DEMAND else load_deadlines("data/deadlines_example.txt")
_VL = None if DEMAND else load_values("data/values_example.txt")
OUT = os.environ.get("OUT", "results/ablate_l2.csv")
BUILD = {"cong_l2on": PartACongestionController,
         "cong_l2off": PartACongestionNoL2Controller,
         "cong_freel2": PartACongestionFreeL2Controller,
         "parta": PartAController,
         "cong_dock": PartACongestionDockController,
         "cong_picker": PartACongestionPickerController,
         "cong_pktraffic": PartACongestionPickerTrafficController,
         "cong_load1": PartACongestionLoadTimeController,
         "cal0": _Cal0, "cal2": _Cal2, "cal4": _Cal4,
         "cal7": _Cal7, "cal10": _Cal10, "cal14": _Cal14,
         "lt1": _LT1, "lt3": _LT3, "lt5": _LT5,
         "lt8": _LT8, "lt11": _LT11, "lt15": _LT15,
         "depth1": _Depth1, "depth2": _Depth2, "depth3": _Depth3, "depth5": _Depth5,
         "d2h0": _D2H0, "d2h20": _D2H20, "d3h0": _D3H0, "d3h20": _D3H20,
         "t1": _T1, "t2h0": _T2H0, "t3h0": _T3H0, "t2h20": _T2H20,
         "rate20": _Rate20, "rate40": _Rate40, "rate80": _Rate80,
         "blend10": _Blend10, "blend20": _Blend20, "blend40": _Blend40, "blend80": _Blend80,
         "rate160": _Rate160, "adapt2": _Adapt2, "adapt4": _Adapt4, "explore": _ExploreArm, "vscreen": _VScreen, "vsrate80": _VSRate80, "vsblend40": _VSBlend40,
         "urg2": _Urg2, "urg4": _Urg4, "urg8": _Urg8,
         "u8p2": _U8P2, "u8p4": _U8P4, "u8p8": _U8P8, "p4": _P4,
         "sq0": _Sq0, "sq1": _Sq1, "sq2": _Sq2, "sq3": _Sq3, "sq5": _Sq5, "sq8": _Sq8,
         "s5m2": _S5M2, "s5m5": _S5M5, "s5m10": _S5M10,
         "s5t2": _S5T2, "s5t5": _S5T5, "s5t10": _S5T10,
         "sq5s": _Sq5S, "sa5": _SA5, "pre0": _Pre0, "pre3": _Pre3, "pre6": _Pre6,
         "joff": _JOff, "j2": _J2, "j3": _J3,
         "sqnb": _SqNB, "sqnp": _SqNP, "sqnf": _SqNF, "sqdc": _SqDC, "sqp15": _SqP15, "sqwide": _SqWide, "sqall": _SqAll,
         "w8": _W8, "w12": _W12, "w20": _W20, "w25": _W25, "oloop": _OpenLoop, "nomap": _NoMap,
         "pacepick": _SqPacePick, "pacecomb": _SqPaceComb,          # state-conditional pace-model delay bias
         "widenb": _SqWideNB, "pacestep": _SqPaceStep,              # no-bias / per-completion pace bias
         "pacecombdl": _SqPaceCombDL, "paceclust": _SqPaceClust,    # combined+dl / clustering-only
         "pkcommit": _PkCommit, "pkrate": _PkRate,                  # picker path-commit / value-rate
         "sqwidepr": _SqWidePkRate, "sqwideprnp": _SqWidePkRateNP,  # sequencer+value-rate; +/- sim picker model
         "pkratenosync": _PkRateNoSync, "pkrate3": _PkRate3, "urgfreepk": _UrgFreePk,  # alpha=3 / champ ceiling
         "sqwidefree": _SqWideFreePk,                               # sequencer + free pickers (picker-optimal ceiling)
         "sqwideprmap": _SqWidePkRateMap,                           # deployed stack + pickers-as-traffic in the map
         "pkratecov": _PkRateCov, "pkratecov1": _PkRateCov1, "pkratecov6": _PkRateCov6,  # value-rate + coverage/spread term
         "pkrateurg": _PkRateUrg, "pkratecovurg": _PkRateCovUrg,  # value-rate + urgency / + both
         "sqwideprurg": _SqWidePkRateUrg,  # deployed stack + picker urgency (stream test)
         "sqwideprsa": _SqWidePkRateSA,    # deployed stack + synthetic (random) future arrivals (Part-C)
         "sqwideprev": _SqWidePkRateEV, "sqwideprev0": _SqWidePkRateEV0,   # deterministic EXPECTED demand + trust knob
         "sqwideprev25": _SqWidePkRateEV25, "sqwideprev35": _SqWidePkRateEV35, "sqwideprev50": _SqWidePkRateEV50,
         "sqwideprk1": _SqWidePkRateK1, "sqwideprk2": _SqWidePkRateK2,   # MCTS-style: K sampled futures, averaged
         "sqwideprk4": _SqWidePkRateK4, "sqwideprk8": _SqWidePkRateK8,
         "sqwideprk2u0": _SqWidePkRateK2U0, "sqwideprk2u16": _SqWidePkRateK2U16,  # MCTS x urgency sweep
         "sqwidepr_fixed": _SqWidePkRate,  # fixed URG_W=8 base (for knob sweeps)
         "champion": _SqWidePkRateAdaptive}  # *** CHAMPION *** = sequencer + value-rate pickers + REGIME-COND URG_W (0 daylist / 8 stream)
#          The reference baseline as of 2026-07-25. Old champion (plain congestion controller) is
#          `cong_l2on`, kept for provenance only. New ideas must beat `champion`, not `cong_l2on`.
POLICIES = [p for p in os.environ.get("POLICIES", ",".join(BUILD)).split(",") if p in BUILD]


def run(seed, name):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    if DEMAND:
        env.request_queue = []
        env.demand_model = DemandModel(env, seed=seed)
        if REGIME == "daylist":
            env.demand_model.seed_day_list(env, horizon=STEPS)   # whole day drawn at t=0, world fixed
        else:
            env.demand_model.seed_initial(env, n=12)
    else:                                    # legacy uniform always-full queue
        attach_deadlines(env, _DL)
        attach_values(env, _VL)
    ctrl = BUILD[name](env)
    deliv = on = 0
    onv = 0.0
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        if DEMAND:
            for o in getattr(env, "fulfilled_this_step", []):
                deliv += 1
                if o.deadline is not None and t <= o.deadline:
                    on += 1
                    onv += o.value
        else:
            for sid, _a in getattr(env, "deliveries_this_step", []):
                sh = env.shelfs[sid - 1]
                deliv += 1
                if sh.deadline is not None and t <= sh.deadline:
                    on += 1
                    onv += task_value(sh)
        done = all(term) or all(trunc)
    return {"deliveries": deliv, "on_time": on, "on_time_value": round(onv, 1)}


def main():
    os.makedirs("results", exist_ok=True)
    rows = []
    for s in SEEDS:
        rec = {p: run(s, p) for p in POLICIES}
        rows.append((s, rec))
        print(f"seed {s}: " + "  ".join(f"{p}={rec[p]['on_time_value']:.0f}" for p in POLICIES), flush=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["seed"] + [f"{p}_{k}" for p in POLICIES for k in ("deliveries", "on_time", "on_time_value")])
        for s, rec in rows:
            w.writerow([s] + [rec[p][k] for p in POLICIES for k in ("deliveries", "on_time", "on_time_value")])
    print(f"\n--- MEAN over {len(rows)} seeds ---")
    for p in POLICIES:
        m = np.mean([r[1][p]["on_time_value"] for r in rows])
        print(f"  {p:<14} on_time_value {m:7.1f}")
    # Baseline for deltas: the NEW CHAMPION (sequencer + value-rate pickers) by default. Override with
    # BASE=<arm>. Falls back to the first policy if the requested base isn't in this run.
    base_name = os.environ.get("BASE", "champion")
    if base_name not in POLICIES:
        base_name = POLICIES[0]
    base = np.array([r[1][base_name]["on_time_value"] for r in rows])
    for p in POLICIES:
        if p == base_name:
            continue
        a = np.array([r[1][p]["on_time_value"] for r in rows])
        d = a - base
        se = d.std(ddof=1) / np.sqrt(len(d))
        print(f"  {p} vs {base_name}: {d.mean():+7.2f}  SE {se:5.2f}  t {d.mean()/se:+5.2f}  wins {(d>0).sum()}/{len(d)}")


if __name__ == "__main__":
    main()
