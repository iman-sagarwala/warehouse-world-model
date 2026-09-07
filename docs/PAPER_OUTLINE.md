# Paper Outline

Built against the Research Paper Guide, 2026-09-06. Bullet-level detail: if a bullet still requires
thinking about *what* to say, it is not finished — say so and it gets expanded.

**Note on fitting the template.** The guide is written for a supervised-ML paper (dataset → model →
train/test split → accuracy). This project is a *planning* paper whose headline result is that the
learned components were all cut. Three sections are therefore re-mapped rather than filled in
literally, and each re-mapping is flagged where it occurs:

| Guide asks for | This paper supplies | Why |
|---|---|---|
| Dataset | The simulator and its calibration sources | The data is generated, not collected; its *constants* are the contribution |
| Modeling / training | Planner architecture + the two learned components that were gated and cut | Nothing learned ships; the gates are the result |
| Train/test split | The seed protocol (1–96 train, 97–144 held out, paired throughout) | Applies to the learned arms and to every exploratory lead |

---

## Title

Aim: state the thesis **and** hint the result, per the guide's good/poor contrast.

- **Preferred —** "Re-plan, don't predict: a known-rules world model beats learned dispatch and
  perfect foresight in deadline-driven warehousing"
  - states the thesis (re-plan, don't predict), hints two results (beats a learner; beats foresight)
- Alternatives, if the above is too long for the venue:
  - "Imagining the present beats predicting the future in multi-robot warehouse dispatch"
  - "A known-rules world model for deadline-and-value warehousing, and six things it cannot learn"
- **Reject:** "A world model for warehouse robots" — the poor-title failure mode: topic only, no result.

---

## Abstract

*Write last. 150–250 words. Every number must be meaningful without the paper.*

- **Objective** — in a warehouse with per-task deadlines and values, the objective is on-time value
  (a late delivery banks zero), not throughput; the hard question is "will this task finish in time?"
- **Approach, one sentence** — for each free robot, enumerate candidate plans, simulate each forward
  under the fleet's own physics, commit only the first move, re-plan every decision; dynamics are
  written down, not learned
- **Headline result** — vs the simulator's own dispatcher, 144 paired days per regime: **+21.7%**
  and **+48.8%** clean, **+31.6%** and **+65.4%** under disturbances
- **Safety** — zero strandings in 2,300+ runs; zero collisions measured over ~96,000 robot-steps
- **The negative result** — six information channels fed the true future; all null or negative. A
  policy-gradient dispatcher with identical inputs loses by **5.8%**
- **Method contribution** — a realism audit that cut throughput 66% and *increased* the margin
- **Conclusion** — imagination pays on what exists; prediction of what does not exist does not
- **Do not include:** t-statistics, seed counts, section references

---

## 1. Introduction

### 1.1 Motivation

- **Problem statement (big picture)**
  - Fulfilment warehouses run fleets of robots against orders carrying deadlines and values
  - Under overload you cannot do everything on time, so the objective is **on-time value**; a late
    delivery banks **zero**, which makes the problem a scheduling problem with a cliff, not a
    throughput problem
  - One question, asked continuously: *what should this free robot do next?*
- **Why it is hard — four coupled sub-problems usually studied separately**
  - which task to assign · how to route without collisions · when to charge · how to recover from
    disruptions the robots cannot directly sense
  - each has a literature; the coupling does not
- **Why it matters**
  - deployments are judged on service-level agreements, not pick rate
  - real sites do not all have dense sensing; a method that needs it does not transfer
  - figure candidate: **Fig. 1**, the four coupled decisions on one floor plan
- **The tempting move, and the paper's counter-thesis**
  - the instinct is to predict — forecast demand, anticipate hotspots, learn delays
  - this paper's claim is the opposite: **imagine the future of what already exists**, and do not act
    on what does not exist yet
  - state up front that this claim is falsifiable and was tested six ways

### 1.2 Background

*Sub-sections titled meaningfully, per the guide.*

- **1.2.1 World models: learned dynamics versus known rules**
  - learned-dynamics line: Ha & Schmidhuber; DreamerV3; MuZero
  - known-rules line: AlphaZero — rules written down, search does the work
  - the behavioural definition adopted here: a world model is a system whose decisions come from
    imagined futures, regardless of how the dynamics were obtained
- **1.2.2 Rollout, approximate dynamic programming and MPC**
  - policy rollout (Bertsekas) and its guarantee: no worse than the base policy
  - receding-horizon commit-one-and-re-plan = MPC; forward value estimate = approximate DP (Powell)
  - RHCR as the lifelong-MAPF instance of the same skeleton
  - **state plainly that the skeleton is not the contribution**
- **1.2.3 Warehouse simulators and the objective gap**
  - RWARE, TA-RWARE, MAPF / Lifelong-MAPF, League of Robot Runners — all optimise throughput
  - demand is uniform-resampled or endogenous 1:1; organisers themselves flag this as unrealistic
  - WareRover as the closest recent coupling effort
  - **the gap:** none jointly models deadlines + values + battery + disturbances + exogenous demand,
    and none optimises on-time value
- **1.2.4 Learned decision layers for task allocation**
  - RTAW, DC-MRTA, MRTAgent — soft delay penalties, not hard deadlines
  - Dehghan, Cevik & Bodur: closest prior work; MDP + neural ADP with deadlines, battery, stochastic
    arrivals. They learn **value-to-go** — the legitimate lever. This paper shows **delay** is not.
- **1.2.5 Execution-layer liveness**
  - PIBT (deadlock-free on bi-connected graphs — a guarantee that fails on rack dead-ends), PIWTP,
    standby-based avoidance; ADG for execution under delay
  - note the value/deadline tier is exactly the priority function these consume
- **1.2.6 Belief maps and forecast verification**
  - occupancy grids / Bayesian belief maps are standard, and are almost always judged by the
    downstream task
  - the forecast-verification apparatus this paper imports: Brier score (Brier 1950), its
    reliability/resolution decomposition (Murphy 1973), reliability diagrams, PR against base rate
- **1.2.7 Value of information as a build gate**
  - Howard (1966) VoPI, normally used to decide whether to *buy* information
  - used here to decide whether to *build* an estimator: hand the candidate the true future first
- **Governing quantities** *(set as numbered equations, variables italicised and defined at first use)*
  - **Eq. 1** on-time value: `V = Σ_o v_o · 1[t_deliver(o) ≤ d_o]`
  - **Eq. 2** the deadline tier used in scoring (makeable vs doomed), showing explicitly that the
    finish estimate appears **only** inside the indicator — this equation carries §5's pace result
  - **Eq. 3** the Beta belief update and its decay, with the hard-block test `b > b_hard`
  - **Eq. 4** skill score: `SS = 1 − BS / BS_ref`, with `BS_ref` the base-rate reference

### 1.3 Objective

- **Focused statement:** determine whether a known-rules, decision-layer world model can beat the
  best available dispatch on on-time value under deadlines, values, battery and unsensed
  disturbances — and determine which information, if any, is worth predicting
- **Original contributions, numbered**
  1. the rollout sequencer + self-tuner, measured against the field's own baseline
  2. six negative results with mechanisms, obtained by a VoPI build gate
  3. a learned opponent given identical information, which loses
  4. the belief map graded as a forecaster, not only as a router
  5. a realism audit methodology and a pre-registered keep/cut ledger

---

## 2. Methods

### 2.1 The simulated environment, and why its constants are the result

*(This is the guide's "Dataset" section, re-mapped — flag that explicitly in the first sentence.)*

- **Substrate:** a fork of TA-RWARE; the unmodified original supplies the FIFO baseline
- **Episode definition:** 500 steps ≈ 8.9 min at a calibrated 1.069 s/step; one *seed* = one window
  of a simulated day, so seeds carry diurnal variation
- **The realism audit — report as a contribution, with a before/after table**
  - two mutually contradictory clocks reconciled (280× discrepancy)
  - storage density corrected 31% → 55%
  - per-operation service times added (8 steps picker load, 6 steps/item at station)
  - order values made lognormal; demand made **exogenous** (schedule pre-drawn from the seed, so two
    policies face identical orders)
  - **net effect: measured throughput fell 66%**, and the method's margin *increased*
  - **Table 1.** Each corrected constant, its old and new value, its source, and its throughput cost
  - **Fig. 2.** The realism pass — what each correction cost
- **External calibration sources** *(state what each was and was not used for)*
  - MovingAI MAPF benchmarks — 1,800 scenarios; used to validate the inner-loop planner only
  - Instacart Market Basket — 3,221 orders / 30,121 matched item-lines; used *only* to calibrate
    within-day demand drift (hour-of-day × department shares → three zone curves, 11–17% swings)
  - Robotnik AMR specifications — battery and kinematic constants (1.2 m/s laden, 0.8 m/s²)
- **Generated data**
  - the planner's **diary**: at each commitment, a 24-feature snapshot + predicted finish + realised
    outcome. One collection run = **3,836 labelled decisions across 144 seeds**
  - the RL baseline generated **960 episodes** of decision/reward traces
  - **Table 2.** The 24 features, grouped (self, task, fleet, congestion), with units
- **Splits and pairing protocol**
  - seeds **1–96 train**, **97–144 held out** for every learned component
  - benchmark comparisons **paired across all 144 seeds** — same seed drives every arm
  - exploratory leads must survive a **disjoint** 48-seed block before being believed
  - caveat to state: seed ranges differ in richness (97–144 is the quieter diurnal half), so raw
    values are not comparable across ranges even though paired differences are

### 2.2 The planner

- **2.2.1 The seven-step funnel** *(per free robot)*
  1. cross off impossible tasks · 2. cheap screen to ~15 finalists · 3. Yen's *k*-shortest routes
  (k=3) · 4. delete illegal routes (collision, battery floor) · 5. score by deadline tier + value +
  urgency · 6. **rollout** · 7. commit the first move only
  - **Fig. 3.** The funnel, annotated with what each stage removes
- **2.2.2 The rollout sequencer**
  - simulate the fleet forward to `now + SEQ_DEPTH × 75`, pickers as consumed resources, event heap
    of robot free times; rank by total banked on-time value
  - the one honest correction: a **live measured pace bias** (EMA of realised-minus-predicted)
  - the deliberate asymmetry: rollout is calibrated, the admission filter is **optimistic**
- **2.2.3 The belief map**
  - Beta belief per cell from line-of-sight sightings, fleet-shared, decaying
  - **observation-reset** update: a look *replaces* the cell's evidence
  - two regimes: in-sight = certainty, out-of-sight = prediction
- **2.2.4 The battery layer** — energy-feasibility filter, charge-to-need, concurrency cap,
  emergency tier; compressed discharge (1,500 steps vs the real ~21,600) with the charge:discharge
  ratio preserved
- **2.2.5 The model-predictive self-tuner** — every 50 steps, deep-copy the warehouse, play 100 (now
  200) steps forward under candidate settings, adopt the winner; UCB1 over seven knobs
  - **state explicitly: the shipped system is rules + tuner (`m3mpc`). Champion-alone is an ablation.**

### 2.3 The learned components, and the gates they had to pass

*(This is the guide's "Modeling" section. Both components were carried to completion and cut.)*

- **2.3.1 The pace head** — LightGBM on the assembler's fleet features; gate fixed in advance:
  **≥15% better than the analytic formula AND calibrated**
- **2.3.2 The learned dispatcher** — shared-parameter MLP(24→64→64→1) scoring the champion's own
  candidate set; REINFORCE + running baseline + entropy bonus; dense per-decision credit; softmax in
  training, argmax at evaluation; 40 iterations × 24 episodes = **960 days** on seeds 1–96
  - **state the level choice and why:** task selection, not primitive moves — move-level MARL would
    mostly learn locomotion
  - **state the honest asymmetry:** the learner replaces `_pick_winner`, which in the champion *is*
    the rollout; so it must have learned what the rollout would have told it

### 2.4 Experimental protocol

- Paired by seed throughout; two instruments reported (paired *t* **and** a sign/win count)
- Standing rule: **every mechanism earns ≥3% or is cut**; safety mechanisms judged on the hard
  constraints instead
- Split-half (evens vs odds) as the test for whether a tuning map is real
- Value-of-perfect-information used as a **build gate**
- **Metric suite:** on-time value (primary); throughput, deadline hit-rate, tardiness mean and p95,
  energy per task, strandings, collisions, replans per disturbance; for the belief map: Brier, skill,
  AUPRC, precision/recall, specificity, calibration, detection latency
- **Table 3.** The metric suite: each metric, what it grades, and its pre-registered target

---

## 3. Results

### 3.1 Main result — against the simulator's own dispatcher

- 4 controllers × 2 regimes × 144 paired days, run twice (clean and with disturbances) = **2,304 runs**
- **Table 4.** Full benchmark: value, deliveries, hit-rate, tardiness mean/p95, energy/task,
  strandings, wedged carriers — every arm, every regime
- Shipped system vs FIFO: **+21.7%** wave / **+48.8%** stream clean (t = 9.30, 12.20); **+31.6%** /
  **+65.4%** disturbed (t = 10.85, 13.02)
- **The margin grows under disturbances** — the key robustness claim
- Margins are conservative: baselines run without battery physics
- **Fig. 4.** Benchmark bars, both regimes, ± disturbances
- Tuner contribution by cell: +0.5% clean wave, +0.9% clean stream, +0.0% disturbed wave,
  **+3.2% disturbed stream** — imagination pays where the world moves

### 3.2 Safety, measured rather than assumed

- 0 vertex and 0 swap collisions, all controllers, ~96,000 robot-steps each
- 0 strandings in 2,300+ runs, audited robot-by-robot
- replans per disturbance 9.0 (FIFO) → 14.3 (ours), with the **lowest** stuck-time — the mechanism
  paying off
- **report the caught placeholder:** the first pass read a nonexistent counter and silently reported
  zero. This belongs in Results, not hidden in Discussion.

### 3.3 Inner-loop validation

- 1,800 MovingAI scenarios, 100% solved (bar 98%); 100% shortest on warehouse and empty maps
- honest sub-result: 91% optimal on randomly cluttered maps (mean +0.22 steps) — irrelevant to aisle
  topology, but the planner is not optimal in general
- **decision-event latency: 1.3 ms median, 510 ms worst** over 3,992 decisions (proposal target ≤1 s)

### 3.4 The anticipation null — six channels

- **Table 5.** Each channel, its oracle construction, its effect, its mechanism
  - task choice with perfect order knowledge: **−3.4%** (t = −6.0)
  - horizon sweep 10/25/50/100/day: 0 / −1.65 / −3.91 / −5.32 / **−11.23** — damage is monotone
  - drift-calibrated demand: pooled z = −0.45
  - idle pre-positioning: **2.4% teleportation ceiling** — cut before building
  - hazard-location prediction: −0.3 to −5.7 in every form
  - charging: true forecast +29.3, **scrambled forecast +50.3** — the sharpest of the six
- **Fig. 5.** Horizon damage curve + the six channels
- **Joint test:** channels do not detectably interact (+27.11, t = +1.53), so the null composes

### 3.5 The learned components

- Pace head: +13.5% raw accuracy, calibration slope 0.14, **0 of 68 decisions changed**
- The mechanism, and it is the finding: the deadline rule is a step function that never consults
  finish time (refer back to **Eq. 2**)
- Learned dispatcher: FIFO 357.3 < **MARL 368.2** < Rush 370.2 < champion 388.8 < **shipped 389.4**
- Shipped system beats the learner by **+5.8%** (t = −5.66, learner wins 14/48)
- **Table 6.** The ladder, with the learner placed in it

### 3.6 The belief map as a forecaster

- 4.8M per-cell predictions per arm, 24 seeds
- **Table 7.** shipped vs the map it replaced: Brier 0.0204 / 0.0310; skill **+0.351 / +0.013**;
  AUPRC 0.367 / 0.260 (random 0.032); sensitivity 92.2% by event; specificity 99.87%; precision
  95.6%; median latency 2 steps
- **Fig. 6.** PR curve, reliability diagram, detection-latency CDF
- **The mechanism, from the panel where nothing happens:** latency is identical between the two maps,
  so the improvement was memory, not perception
- The one failed criterion: phantom hard-blocks 9.8 per 1,000 against a target of ≤1 — with a
  perfect-memory oracle at 9.2, i.e. the map is within 5% of the attainable floor

### 3.7 What sensing is worth, and what prediction is worth

- **Table 8.** blind 800.6 → eyes 837.3 → +memory 850.1 → oracle 855.8
- **The inversion:** at sight radius 5 the split is eyes 74% / prediction 26%; at radius 1 it becomes
  eyes 24% / **prediction 76%** (+20.3, t = +2.28)
- **Fig. 7.** The inversion across sight radius
- The janitor result: with responsive cleanup, honest sensing captures ~100% of clairvoyant value —
  the oracle premium was a symptom of slow response, not of ignorance

### 3.8 The ablation ledger

- **Fig. 8.** Ten kept, twenty-two cut, each with its measured number
- State the pattern explicitly: everything kept reasons about what exists; everything cut acted on
  what did not

### 3.9 Tuning the tuner

- Horizon 100 → 200: +17.8 and strandings 95 → 63 on stress days, statistical tie on ordinary days
  at identical compute → adopted
- Threshold oscillation: +91.2 with the tuner on stress days (t = +3.81), **−3.7 on ordinary days**
  → gated, never a default
- **The tuner's own ceiling:** captures **39%** of the hindsight-best-per-day bound, and ties the
  best single constant head-to-head (24 wins in 48)

---

## 4. Discussion

- **4.1 Why imagination pays and prediction does not**
  - the asymmetry: you cannot serve an order before it exists, so preparing for it taxes the present
  - reactive re-planning already recovers what a short forecast would have bought
  - relate to §1.2.4: Dehghan et al. learn value-to-go and are right to; delay is the wrong target
- **4.2 Why the learned components failed, and what that does not prove**
  - pace: the decision rule is a step function (Eq. 2) — a predictor inside its own control loop is
    punished by construction, because a high forecast triggers behaviour that falsifies it
  - dispatch: the decision layer is near-maximal for this information set
  - **what it does not prove:** modest budget, REINFORCE not PPO, one map. Evidence about where the
    headroom is not, not a proof of impossibility
- **4.3 Sources of error and unexpected results**
  - **placeholder metrics** — a collision counter reading a nonexistent attribute; a documented world
    rule (shelf-free charger bays) that never executed
  - **seed-block reversals** — three occasions where a result flipped sign between seed blocks; the
    default seed range is a silent selector
  - **staleness** — a benchmark table that predated a simulator change by twelve days
  - **metric-definition errors** — two targets recorded as failures for months because they were
    scored against the wrong quantity (per-cell-step recall vs per-event detection; mean vs median)
  - **a fix that moved the baseline** — a correctness fix that would have widened the reported margin
    by degrading the opponent, and was withheld
- **4.4 Limitations**
  - ratio coverage: 3 of 36 AGV×picker cells on the corrected world
  - uncalibrated constants, declared: disturbance rate, amnesty duration, utilisation operating point
  - compressed battery timescale
  - one open liveness defect; cheapest known fix costs 8.1%
  - the phantom hard-block rate, and the sensing density the target implicitly assumed
  - the belief-map grading is 24 seeds, one hazard process, highway cells only
- **4.5 Reasonable modifications**
  - per-day / regime-conditional settings — the largest unclaimed headroom (2.2× any constant)
  - a smooth on-time-probability score in place of the hard tier, which would give a pace model
    something to move
  - denser sensing as the only lever on phantom blocks
  - external validity: port the dispatch rules to the unmodified simulator

---

## 5. Conclusions

- Restate the objective from §1.3 and answer it directly
- Numerical summary with uncertainty: +21.7% / +48.8% clean, +31.6% / +65.4% disturbed
  (t = 9.3–13.0, 144 paired days per cell), zero strandings, zero collisions
- The negative result as a positive contribution: six channels, one mechanism each
- Broader implication: for decision layers with hard deadlines, **fidelity about the present beats
  forecasting the future** — and the discipline that produced that claim (oracle first, build second)
  is transferable
- Future work: per-day adaptation; a probabilistic deadline score; external validity on stock
  TA-RWARE; denser sensing as the phantom-block lever
- **Do not introduce anything new here**

---

## 6. Acknowledgments

- Mentor / advisor
- TA-RWARE and pyastar2d authors (vendored, MIT)
- MovingAI benchmark maintainers; Instacart for the public dataset

---

## 7. References

- ASME style, citation manager (Zotero)
- **Verified group** — Ha & Schmidhuber; Hafner et al.; Schrittwieser et al.; Silver et al.;
  Bertsekas; Powell; Li et al. (RHCR); Okumura et al. (PIBT); Hönig et al.; Stern et al.;
  Sturtevant; Papoudakis et al.; TA-RWARE; Yen; Brier; Murphy; Howard; Williams; Auer et al.;
  Ke et al.; Hawkes; Akiba et al.; Instacart
- **To verify before submission** — nine identifiers carried from the 2026-07-16 literature pass
  (Dehghan et al.; WareRover; LSMART; bursty-arrivals; LMAPF realism; RTAW; DC-MRTA; MRTAgent)
- At least one peer-reviewed source: satisfied many times over

---

## Figure and table register

*Every item is referenced in the text before it appears. Figure captions below the image, table
captions above the table.*

| # | Type | Content | Section | Status |
|---|---|---|---|---|
| Fig. 1 | Diagram | Four coupled decisions on one floor plan | §1.1 | exists |
| Fig. 2 | Chart | The realism audit: cost of each corrected constant | §2.1 | **rebuild** |
| Fig. 3 | Diagram | The funnel, the rollout, and the tuner loop | §2.2.1 | **rebuild** |
| Fig. 4 | Chart | Benchmark, both regimes, ± disturbances | §3.1 | exists |
| Fig. 5 | Chart | Horizon damage + six anticipation channels | §3.4 | exists |
| Fig. 6 | Chart | PR / reliability / detection-latency CDF | §3.6 | exists |
| Fig. 7 | Chart | Sensing-radius inversion | §3.7 | exists |
| Fig. 8 | Chart | The keep/cut ledger | §3.8 | exists |
| Fig. 9 | Chart | Tuner cadence/horizon grid | §3.9 | exists |
| Table 1 | Table | Corrected world constants, old → new, source, cost | §2.1 | **to build** |
| Table 2 | Table | The 24 decision features, grouped, with units | §2.1 | **to build** |
| Table 3 | Table | Metric suite and pre-registered targets | §2.4 | **to build** |
| Table 4 | Table | Full benchmark, all arms and metrics | §3.1 | data ready |
| Table 5 | Table | Six anticipation channels | §3.4 | data ready |
| Table 6 | Table | The controller ladder including the learner | §3.5 | data ready |
| Table 7 | Table | Belief map as forecaster, shipped vs prior | §3.6 | data ready |
| Table 8 | Table | Sensing ladder: blind → eyes → memory → oracle | §3.7 | data ready |

---

## Writing rules for this paper

- **No first person.** "The parameters were adjusted", not "I tweaked".
- **No colloquialisms.** The running log uses them freely; the paper does not.
- Every figure and table is **introduced in the text before it appears**.
- Equations centred, numbered at the right margin, variables italicised and defined at first use.
- Uncertainty travels with every headline number: paired *t*, seed count, and the win count.
- Terms of art defined at first use: on-time value, seed, paired day, wave vs live-stream, rollout,
  makeable/doomed tier, phantom hard-block.
- Where a result was corrected, say so in the text rather than silently publishing the corrected
  number — three of §4.3's items are corrections of this paper's own earlier claims.


---

Build specifications for every figure and table — the claim each must make, its data source, form,
required annotations and a draft caption — are in [`docs/FIGURE_SPECS.md`](FIGURE_SPECS.md).
