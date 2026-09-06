# Consolidated ablation table (M5)

Every mechanism ever built for this project, with its measured effect on **on-time value** and a
keep/cut verdict against the standing rule: **≥3% or cut**, judged on paired seeds, and (for
safety mechanisms) on the hard constraints instead of value.

Conventions: "value" is on-time value per 500-step day; `t`/`z` are paired statistics; a mechanism
is SHIPPED only if it cleared its bar *before* being adopted. Sources are `docs/NOTES.md` entries
by date and the `results/*.csv` files named per row.

---

## A. Shipped — the champion stack

| mechanism | measured effect | evidence |
|---|---|---|
| **Board rollout** (imagine how *current* tasks play out, then commit) | **−7.2% if removed** (t = −30.6) | the largest single mechanism effect in the project; M1 sequencer ablation |
| **Value-rate picker sequencing** | folded into the above; disabling the sequencer is the −7.2% | M1 |
| **Belief-map routing** (M2) | **+6.2%** vs a blind fleet under spills (800.6 → 850.1) | `exp_m2_scout.py`, 48 paired seeds |
| **Reset update rule** (a look *replaces* the cell's memory) | **+3.5%** (+28.8, t = +4.05); spill collisions 236 → 80 | 2026-08-23; carries +26.4 through the MPC too |
| **Sight = certainty / out-of-sight = prediction** | recovered +22 of the old map's deficit; decision-bin calibration exact (98.0% stated vs 97.9% real) | 2026-08-23 |
| **Battery management** (funnel filter, charge-to-need, concurrency cap, emergency drop, picker enforcement) | value-neutral (784.5 vs 784.0 free-energy) and **0 stranded / 0 frozen in 144 audited days** | M3; judged on the hard constraint, not the 3% bar |
| **Dedicated charger bays** (shelf-free, fleet-independent) | enabling infrastructure; no standalone value claim | M3 + user realism rules |
| **Janitor** (earned amnesty: cleanup summoned by sightings) | changes the regime — honest sensing rises to ~100% of oracle value | 2026-08-21 |
| **MPC self-tuner** | **~+1%/day** pooled (z = +11.2, 46 configs); +0.5% wave at 144 seeds (t = +2.41); **0 under disturbances** | campaign + `m5_bench.csv`; kept for tail risk (stress days) |
| **Deadlock/flow flags** (`free_pod_return`, `picker_swap`, `station_headway`, `clash_sim`, …) | `free_pod_return` eliminated 100% of permanent deadlock on dense maps | standing env config |

**Stack total vs the simulator's own dispatcher:** +21% (wave) / +49% (stream) on clean floors;
**+31.6% / +62.3% under disturbances** (t = 11.0 / 11.8), while paying an energy cost the
baselines skip.

---

## B. Cut — predicting the future

| idea | measured effect | why it failed |
|---|---|---|
| Perfect knowledge of future orders | **−3.4%** (t = −5.98) | you cannot serve an order early; preparing for it only taxes the present |
| Foresight window sweep (10 / 25 / 50 / 100 / whole day) | 0 / −1.65 / −3.91 / −5.32 / **−11.23** | damage grows monotonically with how far ahead it looks |
| Demand-drift anticipation (real Instacart calibration) | pooled **−2.0, z = −0.45** (flat) | the fleet re-chases demand in ~25 steps; real hotspots move in 100+ |
| Idle-AGV pre-positioning | **2.4% teleportation ceiling** — below the bar before building | finishing a task already leaves you where the work is |
| Anticipation estimators (SA5 / EV / MCTS) | all wash-to-negative at 120 seeds | explained by the oracle being negative |

---

## C. Cut — acting on guessed hazards

| idea | measured effect | why it failed |
|---|---|---|
| Scout detours (information priced into A* costs) | **−5.7** | ordinary work traffic already sweeps the whole floor for free |
| Hot-zone slow forgetting | **−3.2** | stale fear outlives the evidence |
| Neighbor-suspicion spread | −0.4 (flat) | zone knowledge does not name the cell |
| Sight-gated spread placeholders (user design) | +0.6 (flat) — **repaired the −3.2 harm**, kept flag-gated | correct mechanism, too little exposure at these spill rates |
| Janitor pre-positioning at learned hotspots | −0.27 | even at zero opportunity cost, where-prediction buys nothing |
| Longer map memory | accuracy 61% → **38%** recall | forgetting exists to erase stale *clean* history, not spills |

---

## D. Cut — learned components

| idea | measured effect | why it failed |
|---|---|---|
| Learned pace head (LightGBM, per-candidate) | +13.5% prediction accuracy but **0 of 68 decisions changed**; value −0.42 | the deadline rule is a step function: makeable tasks rank by *value*, ignoring finish time |
| Sim-pace (pace read inside the planner's forks) | +0.9% accuracy; −3.10 value in the four-arm race | simulation cannot beat direct measurement of the system's own recent behavior |
| **MARL learned dispatcher** (policy gradient, same candidates + features) | **−5.3% vs champion** (t = −5.57, 7 wins / 48); beat FIFO, level with Rush | given identical information there was no headroom left to find |
| Delay prediction (5 earlier attempts) | all null | same step-function cause, now identified |
| Context prior for the tuner (k-NN over warehouse size/fleet) | −0.1%/day (leave-one-out) | dispatch weights are context-robust; priors add nothing |

---

## E. Cut — other

| idea | measured effect | why |
|---|---|---|
| Joint first moves / Part D windowed optimisation | −0.59 (W10) → −6.91 (W30) | the rollout already co-decides the partner in every branch |
| Rationing reroutes on a guessed clash model | all variants negative | replaced by the *simulated* clash model, which flipped the sign and shipped |
| Full ADG deconfliction | not built | collisions already measured at 0 (both vertex and swap) |

---

## Summary

**Ten mechanisms shipped; twenty-one measured and cut.** The kept set shares one property — every
one of them reasons about *things that already exist* (current tasks, current batteries, spills
someone has seen). The cut set shares the opposite one: each tried to act on something that did
not exist yet, or on a guess no observation had confirmed.
