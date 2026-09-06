"""ORACLE TEST: what is PERFECT knowledge of each robot's next task/route actually worth?

Layer 2 guesses what a robot does next. Rather than build a better guesser (e.g. a policy rollout), we
first measure the CEILING: run the episode, record what every robot ACTUALLY committed to next, then
re-run feeding layer 2 those true answers. No predictor can beat perfect information, so:
  oracle ~= champion  -> prediction is NOT the lever; no rollout can help. Question closed.
  oracle >> champion  -> prediction pays, and the gap is the maximum prize worth chasing.

Caveat: stamping the true future changes behaviour, so pass 2 drifts from the recording -- this is
NEAR-oracle. A null is therefore strong evidence; a win is an upper bound.

Run under UNIFORM by default (DEMAND=0): the regime where the map has a measurable effect at all.
"""
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
from congestion_policies import (PartACongestionOracleController, PartACongestionRecordController)

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
SEEDS = list(range(int(os.environ.get("SEEDS", "120"))))
STEPS = 500
DEMAND = os.environ.get("DEMAND", "0") == "1"
_DL = None if DEMAND else load_deadlines("data/deadlines_example.txt")
_VL = None if DEMAND else load_values("data/values_example.txt")


def episode(seed, ctrl_factory):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    if DEMAND:
        env.request_queue = []
        env.demand_model = DemandModel(env, seed=seed)
        env.demand_model.seed_initial(env, n=12)
    else:
        attach_deadlines(env, _DL)
        attach_values(env, _VL)
    ctrl = ctrl_factory(env)
    onv = 0.0
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        if DEMAND:
            for o in getattr(env, "fulfilled_this_step", []):
                if o.deadline is not None and t <= o.deadline:
                    onv += o.value
        else:
            for sid, _a in getattr(env, "deliveries_this_step", []):
                sh = env.shelfs[sid - 1]
                if sh.deadline is not None and t <= sh.deadline:
                    onv += task_value(sh)
        done = all(term) or all(trunc)
    return ctrl, onv

HORIZONS = [int(h) for h in os.environ.get("HORIZONS", "6,10,14,22,none").replace("none", "-1").split(",")]


def main():
    base = []
    orac = {h: [] for h in HORIZONS}
    late = {h: 0 for h in HORIZONS}
    hits = {h: 0 for h in HORIZONS}
    for s in SEEDS:
        rec, v1 = episode(s, PartACongestionRecordController)      # pass 1 == champion + logging
        log = rec.commit_log
        base.append(v1)
        line = f"seed {s}: champ={v1:.0f}"
        for h in HORIZONS:                                          # replay SAME recording per horizon
            hh = None if h < 0 else h
            oc, v2 = episode(s, lambda e, _h=hh: PartACongestionOracleController(e, log, horizon=_h))
            orac[h].append(v2)
            late[h] += oc.oracle_late
            hits[h] += oc.oracle_hits
            line += f"  H{h if h > 0 else 'inf'}={v2:.0f}"
        print(line, flush=True)
    a = np.array(base)
    print("")
    print(f"--- TIMED ORACLE SWEEP, {len(a)} seeds, {'DEMAND' if DEMAND else 'UNIFORM'} ---")
    print(f"  champion {a.mean():.1f}")
    print(f"  {'horizon':<11}{'otv':>8}{'effect':>9}{'SE':>6}{'t':>7}{'95% CI':>17}{'wins':>9}{'kept':>8}")
    for h in HORIZONS:
        b = np.array(orac[h]); d = b - a
        se = d.std(ddof=1) / np.sqrt(len(d))
        lbl = "none(all)" if h < 0 else f"start <= {h}"
        frac = 100.0 * hits[h] / max(hits[h] + late[h], 1)
        print(f"  {lbl:<11}{b.mean():8.1f}{d.mean():+9.2f}{se:6.2f}{d.mean()/se:+7.2f}"
              f"  [{d.mean()-1.96*se:+5.1f},{d.mean()+1.96*se:+5.1f}]{int((d>0).sum()):>6}/{len(d)}{frac:>7.0f}%")


if __name__ == "__main__":
    main()
