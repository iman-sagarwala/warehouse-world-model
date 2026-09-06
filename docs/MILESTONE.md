# Project Milestone

**Domain / Category:** Robotics / Multi-Agent Decision-Making (world models, planning under partial observability)
**Author Name:** *(your name)*
**Email:** muhammad@pacbell.net

---

## 1. Introduction

A robotic fulfilment warehouse has to answer one question over and over: *what should this free
robot do next?* Every answer couples four problems that are usually studied separately — which
task to assign, how to route without collisions, when to charge, and how to recover from
disruptions the robots cannot directly sense. Real systems solve slices of this and typically
assume dense sensing that a new site may not have.

I am building an **event-driven decision-layer world model**: for each free robot the planner
enumerates candidate plans (do-task, and charge-then-task), simulates each one forward under the
fleet's own physics, and commits only the first move, re-planning at every decision point. The
model is *known-rules* in the AlphaZero/MPC sense rather than learned like Dreamer — the dynamics
are written down, so learning is reserved for what the rules cannot supply.

The project interests me because it inverts the usual instinct. The tempting move is to predict
the future — forecast demand, anticipate hotspots, learn delays. My central hypothesis is the
opposite: a planner should **imagine the future of what already exists** (the tasks in hand, the
batteries draining, the spill someone saw) and should **not** try to act on things that do not
exist yet. That claim is falsifiable, and testing it has produced the project's most interesting
results — including several that contradicted my own expectations.

## 2. Dataset

The project is **simulation-first**, so the primary dataset is self-generated, with four external
sources used for grounding.

**Self-generated (primary).** A forked TA-RWARE simulator produces every run. Each episode is 500
steps (≈8.9 minutes at the calibrated 1.069 s/step), and a *seed* is one window of a simulated
day, so seeds carry diurnal variation while within-episode burstiness comes from a Hawkes
process. The planner writes a **diary**: at every commitment it logs a 24-feature snapshot plus
the predicted finish time, and later the realised outcome. One collection run produced **3,836
labelled decisions across 144 seeds**; the reinforcement-learning baseline generated **960
episodes** of decision/reward traces.

*Sample diary row (abridged):*
`pred_finish=46.0, my_arrival=17, picker_eta=12, my_wait=5, q_size=11, value=23.4, dl_slack=88,
busy_frac=0.62, local_density=0.21, path_stretch=1.31, ... → realised delay = +31`

**External grounding.**
- **MovingAI MAPF benchmarks** — 1,800 standard scenarios (including their warehouse map) used to
  validate the inner-loop path planner. *Sample:* `23  warehouse-10-20-10-2-1.map  161 63  69 39
  139 11  95.65685425`.
- **Instacart Market Basket** (3,221 orders / 30,121 matched item-lines) — used only to calibrate
  *demand drift*: hour-of-day × department shares, smoothed over the well-sampled 07:00–21:00
  window into three zone-group curves with 11–17% swings across a day. *Sample:* produce peaks
  mid-morning; snacks and bakery peak mid-afternoon.
- **Robotnik AMR specifications** — battery and kinematic constants (1.2 m/s laden, 0.8 m/s²).
- **TA-RWARE** — the substrate and its built-in FIFO dispatcher, used as a baseline.

**Pre-processing.** The largest single piece of work was a **realism audit** of the simulator's
constants: two contradictory clocks were reconciled, storage density was corrected from 31% to a
realistic 55%, per-operation service times were added (8 steps picker load, 6 steps per item at a
station), order values were made lognormal, and demand was made *exogenous* — the whole arrival
schedule is pre-drawn from the seed so two policies face identical orders. That audit cut measured
throughput by 66%: every pre-audit number had been measured on a world three times too productive.

**Splits.** Seeds **1–96 train**, seeds **97–144 held out** for every learned component;
benchmark comparisons are *paired* across all 144 seeds (the same seed drives both arms), and
belief-map disturbance experiments use disjoint 48-seed blocks so exploratory leads must survive
a fresh block before being believed.

## 3. Approach

The baseline is complete and frozen. The planner is a seven-step funnel per free robot: filter
impossible tasks → cheap screen to ~15 finalists → Yen's *k*-shortest routes → drop illegal routes
(collision, battery floor) → score by deadline tier, value and urgency → **rollout** → commit the
first move only. A Beta "rumour map" tracks disturbances from line-of-sight observations, and a
battery layer adds energy-feasibility filtering, charge-to-need and an emergency tier.

Two additions sit on top. First, a **model-predictive tuner**: every 50 steps the controller
deep-copies the whole warehouse, plays 100 steps forward under a handful of candidate settings,
and adopts the winner — a UCB1 bandit over seven knobs. Second, **observation-reset belief
updates**: a direct look *replaces* what the map believed about a cell rather than adding one vote
to accumulated history.

Where learning was attempted, it was gated in advance. A LightGBM pace head had to beat the
analytic formula by ≥15% *and* be calibrated; a policy-gradient dispatcher (shared-parameter
network over the same candidate set and the same 24 features) was trained as a genuine
reinforcement-learning opponent. Both were carried to completion and both were cut by their own
gates — reported below as results, not omissions.

## 4. Evaluations

**Metrics.** Primary: on-time value per day (late = zero). Secondary: throughput, deadline
hit-rate, tardiness mean and p95, energy per task, strandings, collisions, replans per
disturbance. For the belief map: Brier score and skill, AUPRC, precision/recall, calibration, and
detection latency. Every mechanism must earn **≥3% or be cut**.

**Results so far.** Against TA-RWARE's own dispatcher on 144 paired days, the planner delivers
**+21.1%** (wave) and **+47.5%** (live-stream) on clean floors, rising to **+31.6%** and
**+62.3%** once disturbances are active (t = 9–12) — while paying an energy cost the baselines
skip. Safety is absolute rather than statistical: **zero strandings** across 2,300+ runs and
**zero collisions** (vertex and swap, measured directly over ~96,000 robot-steps per controller).
Full battery physics costs nothing (784.5 with management vs 784.0 with free energy). The belief
map captures **90% of a clairvoyant fleet's advantage** and reaches **99.8% of the physical
sensing ceiling** (recall 84.7% vs a maximum of 84.9%), with Brier 0.0204 (skill +0.351 vs the
base rate), AUPRC 0.367 against a 0.032 random baseline, and calibration of 98.0% claimed vs
97.9% observed. The planner's inner loop solves 100% of 1,800 MAPF benchmark scenarios.

**Negative results, each with a mechanism.** Perfect knowledge of future orders is *harmful*
(−3.4%), and the damage grows monotonically with horizon; real-calibrated demand drift does not
rescue it; idle-robot pre-positioning has a 2.4% ceiling; the learned pace head changed **zero of
68 decisions** because the deadline rule is a step function that never consults finish time; and
the reinforcement-learning dispatcher lost to the hand-built rules by 5.3%.

**Plots.** An eight-figure set, regenerated from current data by `scripts/make_paper_figures.py`:
the head-to-head benchmark (both regimes, ± disturbances), precision–recall / reliability /
detection-latency for the belief map, the sensing-radius decomposition, the keep/cut ledger, the
anticipation null, and the tuner's horizon grid. *An earlier figure list was discarded: three plots
had been rendered before the realism audit, on a world three times too productive.*
**Qualitative analysis:** decision traces ("why did R2 charge?"), and animations of the belief map
beside hidden ground truth, both already produced and published in an interactive sandbox.

## 5. Next Steps

Since the milestone was written, (a) and (b) below have both been resolved, one as a win and one as
an instructive failure.

**(a) The longer planning horizon is adopted.** The ordinary-day re-check came back a clean tie at
identical compute — wave +8.6 against the shipped +8.9, live-stream +2.5 against +4.4, all inside
noise — while the stress-day gain stands at +17.8 value and strandings 95 → 63. Nothing regresses,
so the change is free in exactly the shape a safety parameter should be.

**(b) The "zero spare storage slots" flaw was not the cause, and its fix does not ship.** Auditing it
turned up a real bug — the occupancy grid was rebuilt every step, silently restoring pods that had
been stripped from the charging bays, so a documented world rule had never once been in force and
the floor was running eight *fewer* slots than pods. Correcting it closes the failing day and opens
a different one; adding genuinely empty slots changes neither. Worse, with the bay pods really gone
the vendored baseline starts parking pods on charging bays — it has no keep-out notion, our
controller does — which would have widened our reported margin from +62.6% to +80.7% purely by
degrading the opponent. The pod turned out to be load-bearing and the rule cosmetic, so the bug is
documented rather than patched and the liveness item stays open.

Remaining: (c) assemble the paper and figures — the draft is complete through §5.27 with an
eight-figure set and a reference list, and needs typesetting and a citation check; (d) the
open-source release is staged as a licensed, gitignored repository with the two vendored
dependencies reduced to pinned commits plus patches, awaiting only the decision to publish.

The main challenge has remained methodological rather than technical. Several apparent wins
evaporated on fresh seeds; one "result" came from a metric silently reading a value that was never
written; a documented world rule turned out never to have executed; and the benchmark table was
found to predate a simulator change and is being re-measured. Controls and re-verification are now
standard practice, and the most useful habit added this week is narrower than that: **when a change
moves your headline, check whether it moved your baseline.**

## 6. Deliverables

A short paper and an open-source GitHub release by the final submission, plus the interactive
sandbox already built for exploring results.

## 7. References

1. Ha, D. & Schmidhuber, J. (2018). *World Models.* arXiv:1803.10122.
2. Hafner, D. et al. (2023). *Mastering Diverse Domains through World Models (DreamerV3).* arXiv:2301.04104.
3. Schrittwieser, J. et al. (2020). *Mastering Atari, Go, Chess and Shogi by Planning with a Learned Model.* Nature 588.
4. Silver, D. et al. (2018). *A general reinforcement learning algorithm…* Science 362(6419).
5. Papoudakis, G. et al. (2021). *Benchmarking Multi-Agent Deep RL in Cooperative Tasks (RWARE).* arXiv:2006.07869.
6. *Task-Assignment Multi-Robot Warehouse (TA-RWARE).* arXiv:2212.11498.
7. Hönig, W. et al. (2019). *Persistent and Robust Execution of MAPF Schedules in Warehouses.* IEEE RA-L.
8. Stern, R. et al. (2019). *Multi-Agent Pathfinding: Definitions, Variants, and Benchmarks.* SoCS. arXiv:1906.08291.
9. Yen, J. Y. (1971). *Finding the K Shortest Loopless Paths in a Network.* Management Science 17(11).
10. Akiba, T. et al. (2019). *Optuna: A Next-generation Hyperparameter Optimization Framework.* KDD.
11. Instacart (2017). *Market Basket Analysis dataset.*
12. Sturtevant, N. *MovingAI MAPF benchmarks.* movingai.com/benchmarks/mapf.
