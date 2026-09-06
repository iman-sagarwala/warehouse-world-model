"""ASSIGNMENT-LAYER HINDSIGHT ORACLE (crude/best-of-M form).

Question: how far below the hindsight-OPTIMAL assignment schedule does the champion sit? That optimum
upper-bounds every assignment policy -- greedy, bipartite matching, learned, AlphaZero-style search.
Computing it exactly is intractable, so per the plan we LOWER-BOUND it: M rollouts of the SAME seed
with randomized assignment choices (uniform among top-K scored candidates, half with shuffled robot
order), take the best. If best-of-M barely clears the champion, the ceiling is close and the whole
"smarter assignment" direction (incl. rung 3's joint evaluator) is settled cheaply.

Context: both lookahead grids (proxy AND true-funnel scores) came back <= 0, and the delay oracle was
null. This is the last open ceiling on the decision layer.

Honest limits: (a) LOWER bound only -- random search will not find adversarial schedules; (b) explores
within the funnel's structure (routes/tiers unchanged), so it bounds assignment-ORDER value, not
exotic policies that also change routing; (c) uniform regime's resample RNG advances with deliveries,
so each rollout is a legitimate alternative unrolling of the same seed, exactly like every paired
comparison we run.

Run:  SEEDS=5 M=120 python scripts/oracle_assign.py
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
from congestion_policies import (PartACongestionController, PartACongestionExploreController,
                                 _Rate80, _R80Explore, _Sq5, _StackExplore,
                                 _SqWidePkRateAdaptive, _ChampExplore)

ENV = os.environ.get("ENVID", "wwm_sim-large-8agvs-4pickers-globalobs-v1")
N_SEEDS = int(os.environ.get("SEEDS", "5"))
SEED_LIST = ([int(x) for x in os.environ["SEED_LIST"].split(",")]
             if os.environ.get("SEED_LIST") else list(range(N_SEEDS)))
M = int(os.environ.get("M", "120"))
DAYLIST = os.environ.get("DAYLIST", "0") == "1"
RATE80 = os.environ.get("RATE80", "0") == "1"     # 1 = baseline AND explorer use rate80 scoring
STACK = os.environ.get("STACK", "0") == "1"       # 1 = baseline hi-fi sq5 stack; explorer over urg8 scoring
CHAMP = os.environ.get("CHAMP", "0") == "1"   # 1 = measure over the CURRENT champion
BASE_CTRL = (_SqWidePkRateAdaptive if CHAMP else
             (_Sq5 if STACK else (_Rate80 if RATE80 else PartACongestionController)))
EXPL_CTRL = (_ChampExplore if CHAMP else
             (_StackExplore if STACK else (_R80Explore if RATE80 else PartACongestionExploreController)))   # 1 = fixed-world mode: ALL orders drawn at t=0,
                                                  # before any robot moves -> identical world across
                                                  # rollouts -> gap = PURE assignment headroom, zero spawn luck
STEPS = 500
_DL = load_deadlines("data/deadlines_example.txt")
_VL = load_values("data/values_example.txt")


def episode(seed, factory):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    if DAYLIST:
        env.request_queue = []
        # 2026-08-06: allow the oracle to run under the CORRECTED task/deadline layout so the
        # assignment ceiling can be compared like-for-like. WINDOW=1 puts the episode on the fixed
        # clock (seed = one of 36 windows tiling a day); UTIL sets utilisation-anchored arrival rate.
        # Defaults reproduce the legacy layout the +3.62% ceiling was measured under.
        _kw = dict(seed=seed, exogenous=True, horizon=STEPS)
        if os.environ.get("WINDOW", "0") == "1":
            _kw.update(window_index=seed, n_windows=36)
        if os.environ.get("UTIL"):
            _kw.update(utilisation=float(os.environ["UTIL"]))
        env.demand_model = DemandModel(env, **_kw)
        if os.environ.get("STREAM", "0") == "1":
            env.demand_model.seed_initial(env, n=env.demand_model.warm_start_n())
        else:
            env.demand_model.seed_day_list(env, horizon=STEPS)
    else:
        attach_deadlines(env, _DL)
        attach_values(env, _VL)
    ctrl = factory(env)
    onv = 0.0
    t = 0
    done = False
    while not done and t < STEPS:
        _, _, term, trunc, _i = env.step(ctrl.act())
        t += 1
        if DAYLIST:
            for o in getattr(env, "fulfilled_this_step", []):
                if o.deadline is not None and t <= o.deadline:
                    onv += o.value
        else:
            for sid, _a in getattr(env, "deliveries_this_step", []):
                sh = env.shelfs[sid - 1]
                if sh.deadline is not None and t <= sh.deadline:
                    onv += task_value(sh)
        done = all(term) or all(trunc)
    return onv


def main():
    rows = []
    for s in SEED_LIST:
        champ = episode(s, BASE_CTRL)
        vals = []
        best = -1.0
        for m in range(M):
            k = [2, 2, 3, 3, 4][m % 5]                      # vary exploration width
            v = episode(s, lambda e, _m=m, _k=k: EXPL_CTRL(
                e, rng_seed=1000 * s + _m, top_k=_k, shuffle_order=(_m % 2 == 1)))
            vals.append(v)
            if v > best:
                best = v
                print(f"seed {s} rollout {m:3d}: new best {best:.1f}  (champ {champ:.1f})", flush=True)
            if (m + 1) % 10 == 0:
                print(f"seed {s} progress {m+1}/{M}  best {best:.1f}  champ {champ:.1f}", flush=True)
        a = np.array(vals)
        rows.append((s, champ, best, a))
        print(f"SEED {s} DONE: champ {champ:.1f} | best-of-{M} {best:.1f} | gap {best-champ:+.1f} "
              f"({100*(best-champ)/max(champ,1):+.1f}%) | rollout mean {a.mean():.1f} p90 {np.percentile(a,90):.1f} "
              f"| rollouts beating champ: {int((a>champ).sum())}/{M}", flush=True)

    print("\n--- ASSIGNMENT HINDSIGHT ORACLE (lower bound), best-of-%d, %d seeds ---" % (M, N_SEEDS))
    gaps = []
    for (s, champ, best, a) in rows:
        gaps.append(100 * (best - champ) / max(champ, 1))
        print(f"  seed {s}: champ {champ:7.1f}  best {best:7.1f}  gap {best-champ:+7.1f} ({gaps[-1]:+.1f}%)  "
              f"beat-rate {int((a>champ).sum())}/{M}")
    print(f"  MEAN GAP: {np.mean([r[2]-r[1] for r in rows]):+.1f} otv  ({np.mean(gaps):+.1f}%)")
    print("  Reading: gap ~small => the assignment ceiling is close; smarter assignment (matching,")
    print("  learned, search) has little to win. gap large => real headroom exists above greedy.")


if __name__ == "__main__":
    main()
