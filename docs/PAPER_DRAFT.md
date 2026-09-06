# Paper Draft — A Lightweight Interpretable Decision-Layer World Model for Deadline-and-Value Multi-Robot Warehousing

> **Rewritten 2026-08-06 after the realism pass.** Every number in the previous draft was measured on a
> simulator that was ~3x too productive (31% storage vs a realistic 40-60%, zero service time anywhere,
> two mutually contradictory clocks). Those results are preserved in
> `docs/PAPER_DRAFT_preRealism_2026-08-06.md` but must not be cited.
> **Headline was: +11.83% on-time value over the strongest heuristic, t=+4.14, 486 paired seeds
> (= 3 simulated days) on a warehouse whose every constant is either calibrated or declared.**

> **Updated 2026-09-05 (M5 closed).** The headline is no longer an in-house comparison. Against
> **TA-RWARE's own dispatcher**, on 144 paired days per regime, the planner is worth **+21.1%**
> (wave) and **+47.5%** (live-stream) on clean floors, rising to **+31.6%** and **+60.4%** once
> disturbances are active (t = 9.1–12.5) — while paying an energy cost the baselines skip. A
> policy-gradient dispatcher given identical information loses to the hand-built rules by 5.3%.
> **Ten mechanisms shipped, twenty-two measured and cut** (`docs/ABLATION.md`).

---

## Working title (options)
- "Re-Plan, Don't Predict: An Interpretable Rollout World Model for Deadline-and-Value Warehousing"
- "Honest About the Present, Silent About the Future"
- "What a Warehouse Planner Cannot Learn: Six Negative Results and One That Pays"

## Abstract
In a multi-robot warehouse with per-task deadlines and values, the objective is **on-time value** — a
late delivery banks zero — and the hard question is *"will this task finish before its deadline?"* We
present a lightweight, interpretable **decision-layer world model**: for each free robot the planner
enumerates candidate plans, simulates each one forward under the fleet's own physics, ranks by
simulated banked value, and **commits only the first move**, re-planning at every decision point. The
dynamics are written down rather than learned, so learning is reserved for what the rules cannot
supply. The method's value comes not from the plan — obeying the whole imagined schedule *loses* value
— but from constant re-planning anchored to one honest correction: a **live measured pace bias**
applied to every imagined completion.

Against **TA-RWARE's own dispatcher**, on 144 paired days per regime, the planner is worth **+21.1%**
(wave) and **+47.5%** (live-stream) on clean floors and **+31.6%** / **+60.4%** once disturbances are
active (t = 9.1–12.5), while paying an energy cost the baselines skip. Safety is absolute rather than
statistical: **zero strandings** across 2,300+ runs and **zero collisions** of either vertex or swap
type, measured directly over ~96,000 robot-steps per controller, with the inner-loop planner solving
100% of 1,800 MovingAI MAPF scenarios. A policy-gradient dispatcher trained on 960 days with
*identical* inputs, candidates and machinery beats the vendored dispatcher, ties a value-plus-urgency
rule, and still loses to the hand-built rules by **5.3%**.

The second contribution is a characterisation of what this class of problem **cannot** reward,
obtained cheaply by a **value-of-perfect-information discipline** — feed a candidate predictor the
true future *before* building it. Six independent channels come back null or negative, each with a
mechanism: per-task delay prediction, demand foresight (harmful, and monotonically worse with
horizon), idle pre-positioning, hazard-location prediction, execution-layer priority, and charging
foresight — where a *scrambled* forecast beat the true one, exposing the real mechanism as threshold
*movement* rather than information. Ten mechanisms shipped and twenty-two were cut against a bar fixed
in advance; the two halves separate cleanly into reasoning about what already exists and acting on
what does not.

Third, we grade the fleet's disturbance belief as a **forecaster** rather than only as a router:
Brier **0.0204**, skill **+0.351** against a base-rate reference, AUPRC 0.367 against 0.032 random,
calibration of 98.0% stated against 97.9% observed, and 99.8% of the physical sensing ceiling. The map
it replaced scored **+0.013** skill — useful enough to route on, and almost no forecaster at all — a
distinction no value experiment could have drawn. Fourth, we report a **realism audit** in which
correcting the simulator's world constants cut throughput 66% and *increased* the method's margin, and
argue such audits should be routine, because most of our own earlier findings did not survive one.

---

## 1. Introduction

**Setting.** Fulfilment warehouses run fleets of AGVs plus pickers under a stream of orders carrying
**deadlines** (SLA) and **values**. Under overload you cannot do everything on time, so the objective is
**on-time value**, not throughput. A late delivery banks **zero**.

**Contributions.**
1. **A rollout sequencer** for task choice, worth **+21.1% / +47.5%** over the simulator's own
   dispatcher on clean floors and **+31.6% / +62.3%** under disturbances (§5.20), at **zero**
   strandings and **zero** measured collisions.
2. **Six negative results with mechanisms**, obtained cheaply via a VoPI discipline (§5.3, §5.5,
   §5.19, §5.25), including one where a *scrambled* forecast outperformed the true one.
3. **A learned opponent, not a straw one**: a policy-gradient dispatcher with identical inputs and
   candidates beats the vendored heuristic and loses to the rules by 5.3% (§5.21).
4. **The belief map graded as a probabilistic forecaster** — Brier, skill, AUPRC, reliability and
   detection latency — which separates "useful to route on" from "honest as numbers" (§5.22).
5. **A realism audit methodology** and the finding that our own pre-audit results largely did not
   survive it (§3, §7), plus a **pre-registered keep/cut ledger** of all 32 mechanisms (§5.24).

---

## 2. Related Work

**World models, learned and known.** The world-model literature learns the dynamics: Ha and
Schmidhuber's original formulation, the Dreamer line's latent imagination, and MuZero's learned model
trained purely to support planning. AlphaZero occupies the other pole — the rules are written down and
the search does the work. This paper sits at that second pole and takes the *behavioural* definition of
a world model seriously: the test is not whether the dynamics were learned, but whether decisions are
made from imagined futures. Ours are — every commitment is the winner of a forward simulation, and
every tuner adoption is the winner of a forward simulation of the tuner's own settings. The interesting
consequence is reported in §5.19 and §5.21: with the dynamics written down, the parts one would
*expect* to learn (a pace head, the dispatch policy itself) turn out to be the parts that do not pay.

**Rollout, approximate dynamic programming and MPC.** The sequencer is a **policy rollout** in
Bertsekas's sense — estimate each first move by simulating the base policy forward, commit the best,
and inherit the guarantee that rollout is no worse than its base policy — wrapped in a
receding-horizon commit-one-and-re-plan loop, i.e. model-predictive control, with the forward value
estimate playing the role of approximate DP (Powell). The same select-by-imagined-continuation skeleton
underlies MCTS and receding-horizon lifelong MAPF (RHCR); ours is the single-trajectory ancestor, with
no tree and no learned model. **The skeleton is not the contribution.** What we add is the discipline
around it: which fidelity corrections pay (a live measured pace bias, §4), which do not (§5.19), and —
in §5.26 — that a rollout horizon must be sized against the duration of the decision it is asked to
judge, a parameter the MPC literature treats as a tuning detail and which here is worth 3.5%.

**Warehouse simulators and the objective gap.** Grid/algorithmic warehouse benchmarks — RWARE,
TA-RWARE, MAPF and Lifelong-MAPF, the League of Robot Runners — optimise **pure throughput**: pick rate
or task count. Demand is uniform-resampled (RWARE/TA-RWARE) or endogenous 1:1 (LMAPF, where a task
appears only as one finishes), and the LMAPF organisers themselves flag uniform task sampling as
unrealistic against imbalanced, spatially correlated real demand. The physics/perception camp (Isaac
Sim and similar) supplies warehouse assets but bolts scheduling on from outside. The closest recent
effort, WareRover, couples order scheduling with MAPF under realistic e-commerce demand, but remains a
simulator-and-coupling contribution rather than an objective one. **None of them jointly models
deadlines, per-order values, battery, disturbances and exogenous demand, and none optimises on-time
value.** We fork TA-RWARE and change the objective, which is why §3's audit of its world constants is
reported as a contribution rather than as setup: on the throughput objective those constants are
second-order, and on ours they decide the answer.

**Learned decision layers for task allocation.** RTAW, DC-MRTA and MRTAgent learn dispatch, but under
*soft* delay penalties rather than hard deadlines with per-task values. Dehghan, Cevik and Bodur
(arXiv:2312.16026) are the closest decision-layer prior work — an MDP with neural ADP, per-task
deadlines, stochastic arrivals, battery and human–robot collaboration — and the differences are
instructive: they optimise order *count*, have no disturbances, and model congestion as worker capacity
rather than spatial corridor contention. Notably, what they learn is the **value-to-go**, which is the
legitimate lever; what we show cannot be learned usefully here is **delay** (§5.19), and even the
value-to-go route is tested directly in §5.21, where a policy-gradient dispatcher with the champion's
own candidates and features beats the vendored heuristic and loses to the hand-built rules by 5.3%.

**MAPF, execution under delay, and liveness.** We use the standard MovingAI benchmark suite (Stern et
al.) to validate the inner loop rather than to compete on it (§5.20). At execution, persistent and
robust MAPF execution under delay (Hönig et al.) and Action Dependency Graphs are the reference
machinery for keeping a plan valid as robots slip. For deadlock and livelock, the standard resolution
is priority-based victim selection: PIBT negotiates locally over next cells and is deadlock-free on
bi-connected graphs — a guarantee that explicitly fails on the dead-ends and tree-shaped rack
rendezvous of a picker–AGV warehouse — while PIWTP extends it to pickup-and-delivery via priority
inheritance, and standby-based avoidance targets the dead-end case directly. Our value-and-deadline
tier is precisely the priority function these schemes consume. §5.12 and §5.13 report the relevant
empirical finding: every attempt to resolve the warehouse's stalls at the *movement* layer cost
liveness, while uncrossing the *errands* at the dispatch layer dissolved them for free.

**Belief maps, probabilistic detection and calibration.** Occupancy grids and Bayesian belief maps are
standard in robotics, and are almost always evaluated by the downstream task. §5.22 instead imports the
forecast-verification apparatus — the Brier score (Brier, 1950), its decomposition into reliability and
resolution (Murphy, 1973), reliability diagrams and precision–recall against the base rate — and
applies it to a fleet's disturbance belief. The result argues for the practice: the map we replaced was
useful enough to route on while carrying a skill score of +0.013, which no value experiment would have
revealed.

**Value of information.** The value-of-perfect-information bound (Howard, 1966) is normally used to
decide whether to *buy* information. We use it as a **build gate**: hand a candidate predictor the true
future, and if the oracle does not pay, do not build the estimator. Six channels were retired this way
at one experiment each (§5.3, §5.5, §5.19, §5.25). §5.25 adds a refinement we have not seen used — a
*scrambled*-information control alongside the uninformed one — which is what exposed a positive result
as parameter movement rather than knowledge.

**Demand realism.** Real warehouse inter-arrivals are heavy-tailed and bursty rather than homogeneous
Poisson, which motivates the Hawkes process in §3.6; within-day hotspot drift is calibrated from the
Instacart Market Basket sample (§5.18). We report the negative outcome of that calibration honestly: it
was built specifically to give anticipation its best chance, and anticipation still did not pay.

---

## 3. The Simulator, and Why Its Constants Are the Result

We fork TA-RWARE. **The single most consequential thing we did was audit its world constants**, and we
report it as a contribution because the audit changed nearly every downstream number.

### 3.1 The two-clock contradiction
A step is **one cell of robot travel**, which pins its duration. Two incompatible clocks were live:

| clock | implies |
|---|---|
| robot: RB-KAIROS+ 1.5 m/s over 1 m cells | 1 step ≈ 1 s |
| demand: `period = 250` steps = "one day" | 1 step ≈ 5.8 min |

**~280x apart.** Under the demand clock a robot crawls 1 m every 6 minutes; to keep robot speed, cells
become 259 m and the warehouse is 9 km wide. Neither survives. **Resolution:** a step is one cell, and
the day spans **episodes** rather than sitting inside one — seed *i* is the *i*-th window of a 24 h day,
so diurnal variation lives across seeds (hours) and burstiness lives within an episode (minutes, via a
Hawkes process), each mechanism at the timescale it was measured at.

### 3.2 Step duration, from kinematics
Naively 1 m / 1.5 m/s = 0.67 s. But measured straight runs between turns are **short** (p25 1, median 3,
p75 8 cells), so a robot rarely reaches cruise. Applying a trapezoidal/triangular profile per run with
`a = 0.8 m/s²` (published AMR decel) and `v_max = 1.2 m/s` (laden) gives **1.069 s per cell** — the
naive figure is **38% too fast**. Episode = 500 steps ≈ 8.9 min; **162 seeds = exactly one day**.

### 3.3 Geometry
The stock layout hardcodes 2-wide pod blocks with 2-cell lanes: **31% storage, 69% open aisle.** Real
in-aisle-picking systems run **40–60%** (conventional racking with access aisles; Kiva pod-to-station
reaches ~65% only because nothing is picked in the field). We parameterise block width and lane width
and adopt **4×6 clusters with 1-cell lanes = 55% storage**, inside the realistic band. Pod ≈ 1×1 m and
the drive unit (75×60 cm) travels beneath it, so **1 m cells and one-robot-per-cell are correct as
found**. One-way lanes are implemented (directed A*, alternating Manhattan) and reported as **opt-in**:
they are the real rule but cost 16% at our robot density, because they trade conflict cost for detour
cost and conflicts are rare with 8 robots on 650 cells.

### 3.4 Service time
The simulator spent **zero time on every physical operation**. We add, each grounded:

| operation | was | now | source |
|---|---|---|---|
| picker load (arm cycle) | 0 s | 8 steps | UR-arm pick-and-place ~5–10 s |
| station pick, **per item** | 0 s | 6 steps/item | 300–600 picks/hr manufacturer station rates |

Station dwell scales with item count because one pod trip serves **every** order pending on that shelf.
This is capacity, not latency: a held robot leaves the fleet.

### 3.5 Station count, by throughput balance
Station count was an accident of the layout (every non-highway bottom-row cell). Balance says
~468 pods/hr × ~1.5 orders/pod ≈ 700 picks/hr against 300–600 picks/hr per station → **1.2–2.3
stations** suffice for 8 AGVs; the stock map had 10. **Adding robots is the wrong lever** — saturating
10 stations needs 35–70 AGVs, ≈24% lane occupancy, i.e. gridlock first. We set 3.

### 3.6 Demand
Values are **lognormal** (real order values are long-tailed; uniform 1–15 spans only 5.3× p90/p10).
Arrival rate is **utilisation-anchored** (`rate = utilisation × n_agvs / task_steps`) rather than a bare
constant that implied 47% utilisation. Demand is **exogenous**: the whole arrival schedule is pre-drawn
from the seed, because the stock model chose shelves from those not in transit, making demand
policy-dependent (two policies shared only ~22% of (time, shelf) pairs) and paired comparison invalid.

### 3.7 What the audit cost
| configuration | deliveries / 3 episodes |
|---|---|
| original (31% storage, 10 stations, uniform values, no service) | **171** |
| + realistic geometry and stations | 95 |
| + lognormal values | 76 |
| + service times | **58** |

**Throughput falls 66%.** The simulator was ~3× too productive, and every pre-audit number was measured
on that world.

---

## 4. Method

**Part A — a seven-step funnel per free robot.** (1) cross off impossible; (2) cheap screen to ~15
finalists; (3) Yen's *k*-shortest routes (k=3); (4) delete illegal routes (collision, battery floor);
(5) score by tier + value + urgency; (6) **rollout**; (7) commit the first move only.

**Part B — the rollout sequencer.** For each of the 15 finalists, simulate the fleet forward to
`now + SEQ_DEPTH × 75`, with pickers as consumed resources and an event heap of robot free times, and
rank by **total banked on-time value**. Commit one move; re-plan next tick.

**The one honest correction.** Every imagined completion carries a **live pace bias** — an EMA of
realised-minus-predicted completion — so the imagination plans in today's actual time.

**A deliberate asymmetry (Sec 5.7).** The rollout is calibrated; the step-5 admission filter is
deliberately **optimistic** (no bias term). Predicting carefully to *choose*, optimistically to *admit*.

---

## 4.1 Figures

All figures are regenerated from current data by `scripts/make_paper_figures.py`. **The roadmap's
original figure list — `stream_stack`, `picker_ceiling`, `oracle_gap` — was produced in July 2026,
before the realism audit, on a simulator ~3× too productive. Those PNGs are retained for provenance and
must not be cited.**

| # | file | what it shows | section |
|---|---|---|---|
| 1 | `champion_architecture.png` | the seven-step funnel and where the rollout sits | §4 |
| 2 | `diag_realism_pass.png` | the realism audit: what each corrected constant cost | §3 |
| 3 | `fig_benchmark.png` | head-to-head vs the simulator's own dispatcher, both regimes, ± disturbances | §5.20 |
| 4 | `m5_belief_curves.png` | the belief map as a forecaster: PR, reliability, detection latency | §5.22 |
| 5 | `fig_sensing.png` | the prediction inversion across sight radius | §5.23 |
| 6 | `fig_ablation.png` | the pre-registered keep/cut ledger, 10 shipped / 22 cut | §5.24 |
| 7 | `fig_anticipation.png` | the anticipation null: horizon damage, and six channels | §5.3, §5.25 |
| 8 | `fig_horizon.png` | the tuner's cadence/horizon grid, value against compute | §5.26 |

Palette note: the categorical slots are validated for colour-vision deficiency (worst adjacent-pair
ΔE 9.1, normal-vision ΔE 22.9); two slots fall below 3:1 against the page, so every bar carries a
visible direct label rather than relying on colour alone.

---

## 5. Experiments

All on the corrected world (§3), paired by seed, no disturbances or battery unless stated. Seeds tile a
day, so split-half is **evens vs odds**, never first-half/second-half.

**Two standing methods guards**, both the residue of errors we made and had to unwind.

*The day-list − stream gap is capacity, not information, and is never a VoPI bound.* An earlier version
of this work read the difference between the wave (whole day known at t=0) and live-stream regimes as
the value of knowing the future. It is not. Once the two regimes are workload-matched the gap doubles
(+70 → +142.9, t = +60.8), which is the tell: the wave regime can *serve* an order early, and no
forecast can grant that. The gap measures a capacity difference that foresight cannot buy. Every
foresight number in this paper instead comes from the direct construction — stream physics, the genuine
future injected into the planner's rollout, exogenous demand — which is what produces the −3.4% of
§5.3. Readers should not re-derive an information bound from the regime comparison in §5.1.

*Comparisons predating the exogenous-demand fix are only partially paired.* Demand was originally
endogenous to the policy (`_inject` skipped in-transit shelves, so only 22% of orders matched between
two policies on the same seed). `DemandModel(exogenous=True)` pre-draws the whole arrival schedule from
the seed, so both arms now face identical orders; the legacy path was verified unchanged. Results
measured before that fix share order counts and times but not shelf identities — they are reported as
such, and every headline number in §5.15 onward is fully paired.

### 5.1 Main result — the controller ladder
162 seeds = one simulated day; champion vs rush re-run at 486 seeds = three days.

| controller | on-time value | vs FIFO | step gain |
|---|--:|--:|--:|
| FIFO (oldest first) | 110.0 | — | — |
| + nearest-first | 171.1 | +55.6% | +61.1 (t=+5.7) |
| + drop impossible | 163.6 | +48.8% | −7.4 |
| + rank by value | 212.2 | +93.0% | **+48.6 (t=+5.1)** |
| + deadline urgency | 212.1 | +92.8% | −0.2 |
| **rollout sequencer** | **231.9** | **+110.9%** | +19.8 |

**Champion vs rush, 486 seeds: +27.08 (+11.83%), t = +4.14, W/L 286/186**, split-half +23.2 / +30.9.

Two observations. **Value ranking is the single largest decision-layer gain** (+48.6) — larger than the
rollout. And the feasibility filter and urgency term are flat *as ladder rungs*; both remain in the
stack (feasibility is a correctness guard, and a flat rung is not evidence for removal).

### 5.2 Negative result — per-task delay prediction is unlearnable
Learned delay head, congestion-feature head, rules-based delay, soft P(on-time): all null or negative,
including with an **oracle**. Delay is chaotic at task granularity.

### 5.3 Negative result — perfect demand foresight is *harmful*
VoPI with the true future schedule: **−3.43%** at every horizon. Not "our estimator was weak" — knowing
future orders does not help this system at any accuracy or range.

### 5.4 Negative result — the makeable/doomed tier is decorative
`TIER_GAP` swept 0 → 10,000. Above the max task value it is a **gate**: 300/3000/10000 are bit-identical.
Removing it entirely (`gap_0`) changes **68% of episodes** and banks the **same value**. The rollout
already prices doom, because it ranks by *banked on-time* value by construction.

### 5.5 Negative result — execution-layer priority
Priority-ordered clash yielding, 4,800 runs: value-ranked **−5.71** (t=−5.06), deadline-ranked **−6.45**
(t=−5.40), **ranking-free control least bad** (−1.47). Mechanism is starvation, exactly as the MAPF
literature predicts for static priority without inheritance. Prioritized reroute (both robots replan in
utility order) was **−20%**: replanning costs a tick, and doing it to both doubles the cost.
*Refined, not contradicted, by §5.11–5.14: execution-layer **priority and rationing** lose, but
execution-layer **queue restructuring** (station discipline, rendezvous swaps) is the largest gain in
the project.*

### 5.6 Negative result — belief-based disturbance avoidance (M2 premise; STRENGTHENED, see 5.16)
With clairvoyant routing removed (planners route on a line-of-sight belief map, execution hits ground
truth) and debris at **10× the calibrated rate (20 cells/episode)**, disturbance cost is **statistically
zero** across three routing models. An arm that ignores debris entirely and simply collides is the
*best* performer. **Perfect disturbance information is worth ≤ 0.** Traffic-weighted spawning raised the
sharing count past the threshold (0.83 → 1.67 robots per disturbed cell) and cost stayed zero.

### 5.7 Optimism beats accuracy in the admission filter
Feeding the live pace bias into the step-5 deadline check — making it *more accurate* — costs **−0.3%**.
Accuracy about lateness reclassifies marginal tasks as doomed so they are never attempted; the
optimistic estimate sends the robot and it sometimes makes it.

### 5.8 Ties dominate
**48.6%** of rollout decisions end in a tied maximum (mean tie size 5.09), because banked value is a sum
of discrete task values. Lognormal values reduce this to 45.7% but not below ~half: most ties are
**structural** (the horizon completes the same work whatever the first move), not a granularity artifact.

### 5.9 Knob tuning is flat on the corrected world
Full re-sweep, 486 paired runs per arm, 3 fleets: **no knob clears |t| ≥ 3**. Two reproduce across
split-halves with ≥2% effects — `SEQ_DEPTH = 1` on day-list (+4.6%) and `RATE_ALPHA = 3.5` on stream
(+3.3%) — and both sit at a comb boundary; extension running. `URG_W = 8`, M1's only behavioural rule,
is **unsupported in five independent experiments** and was traced to the policy-dependent-demand bug.

### 5.10 An assignment ceiling, and it shrinks under realism
Best-of-80 perturbed rollouts: **+3.3%** under the legacy layout, **+2.3%** under the corrected clock and
load. Headroom is **concentrated** — a third of seeds are exactly optimal while the worst give up 8–14%.

### 5.11 The liveness arc — from deadlock in half of all episodes to zero
The dense map initially deadlocked **permanently in 51% of episodes** (74/144), a rate hidden through
eight failed fixes by a **measurement trap**: a freeze detector that counted movement across *all*
agents reported a fully deadlocked AGV fleet as "moving", because pickers keep shuffling during a jam.
The honest metric — *a carrying AGV whose cell never changes for 100 steps* — exposed it. Three rules
eliminated it at zero value cost:
1. **Station headway** — arrivals hold one cell back from an occupied station;
2. **Station exit priority** (+3.05%, t=+3.30) — the occupant gets first claim on a free *side* cell
   (sideways only: a perpendicular step makes the route continuation diagonal, which is unexecutable);
3. **Free pod return** — an AGV may lower its own pod without a picker present. Upstream TA-RWARE
   requires a picker on the cell, so an AGV whose picker never arrives holds its pod *forever*; this
   single inherited rule caused 100% of residual permanent deadlock.
Deadlock: **67/144 → 0/144**, audited per instance, and held at 0/144 under every subsequent champion.

### 5.12 Negative family — rationing reroutes always loses
Five independent clash-level interventions — wait-vs-reroute ranked by value rate, one-waiter (hold),
one-waiter (sidestep), forced yielder, progress-aging priority — were **all null-to-negative** (pooled
t from −0.03 to −1.76; several reintroduced deadlock). So were **space-time reservations** (cooperative
A*, windowed, with and without prioritised planning): without an ordering, "everybody waits" is a
consistent solution the search happily finds — one robot stood still 488/500 steps with *nothing*
blocking it. The principle: **rerouting is how the fleet separates robots, and separation is what keeps
it live**; any rule that rations it trades liveness for the detour it avoids. The huge detours are also
structural, not planner error: pickers are confined to highways and a pod has a single lane doorway, so
"around" is genuinely 30–46 steps.

### 5.13 Main liveness result — station discipline and rendezvous swaps (+6.8%, t=+6.8)
Where clash-level rationing failed, **queue restructuring** succeeded. The champion stack (dense map,
8 AGV × 6 pickers, 144 paired seeds):

| stage | on-time value | delivered | pod-wait steps | max single wait | frozen AGVs |
|---|--:|--:|--:|--:|--:|
| deadlock-free baseline | 727.55 | 493 | 67,571 | 138 | 0 |
| + picker goes in, waits on the pod | 732.29 | 526 | 47,835 | 95 | 11* |
| + side-keepout + station divert | 770.39 | 511 | 49,648 | — | 2* |
| + cross-drop swap & repairs (v1) | 776.95 | 577 | 51,723 | 448† | 0 |
| + rendezvous swaps (v2) | 778.34 | 576 | 48,611 | 114 | 0 |
| + rendezvous re-election (v3) | 775.77 | 540 | 46,424 | **83** | 0 |
| **+ trajectory-simulated clashes (champion v4)** | 777.23 | 557 | **44,608** | 92 | **0** |

\* sums over all 144 episodes, never simultaneous counts. † v1's tail case (a picker–picker lock) is
what the rendezvous swap removes. The two station rules are a **complement pair**: side-keepout alone
is catastrophic (147 frozen — one-sided queueing with no outlet); divert is the drain that makes it
work. The stack is the **first and only result in the project to clear the |t| ≥ 3 shipping bar**
(+6.79%, t=+6.78 at v1; v2–v4 keep that value — see the version comparison below — while cutting
the worst wait 448 → 114 → 83 → 92 at the lowest total waiting on record).

The swap family generalises one idea: **when two robots' errands cross irresolvably, uncross the
errands, not the robots.** Cross-assigned drop slots → swap missions, both drop in place (zero
movement). Two pickers in a one-wide lane, each needing the doorway past the other → swap rendezvous.
A picker squatting on another's target pod → the squatter serves the pod it occupies. All are dispatch
decisions with no physics change, gated to fire only on measured unremovable locks (both robots
stationary ≥ 10 steps plus the geometric lock signature).

**Rendezvous re-election (v3) is the general form**, of which the swap shapes are special cases: when
an AGV is parked at its rendezvous and the committed picker has made no progress for 12 steps, the
server is re-elected among *all* pickers by (a) actual route length and (b) a legal route existing
*now* (`find_path` with robots as obstacles) — proximity alone does not qualify a candidate that cannot
move in. It delivers the deepest tail cut of any single rule (max wait 114 → 83, pod-wait −4.5%).

**On-time value across champion versions (144 paired seeds):** v2 = 778.34, v3 = 775.77 and
v4 = 777.23 are **statistically indistinguishable** (pairwise |t| ≤ 1.23); all sit ≈ +7% above the
deadlock-free baseline (727.55) and all hold frozen = 0/144. The versions differ on the *tail and
throughput mix*, not the objective: v3 buys max-wait 114 → 83 at −6% raw deliveries; v4 recovers half
those deliveries and reaches the lowest total waiting of any configuration (44,608) at a slightly
fatter tail (92). v4 is the reference champion; if the worst single wait ever becomes the metric,
disable `clash_sim` (v3, max 83); if raw throughput does, `picker_reelect` is the first flag to
revisit.

**v4 — wait-vs-detour by trajectory simulation — reverses a six-experiment negative.** At every clash
where a detour exists, both options are scored by *simulated arrival time*: a deterministic cellular
walk of every robot along its **published path**, iterated to a fixpoint per tick so follow-the-leader
chains cascade (blocker's blocker's blocker moves, freeing each in turn); parked robots never move;
ties go to the detour. This uses trajectories for **evaluation, not constraint** — the two prior
failures were constraint-shaped (space-time reservations: the "everybody waits" fixed point) or
model-free (a guessed blocker-clearance term that measurably never influenced the decision, t = −1.76).
The identical decision with a simulated estimate scores t = **+0.76**: the movement-layer conclusion
was never "deliberation loses" but "*badly-informed* deliberation loses". A staleness haircut
(veto long-predicted waits) was tested and is **worse on every column** (max wait 92 → 123): the
simulation's long-wait verdicts are mostly *correct*, and predicted delays are bimodal (≤3 ticks or
effectively infinite), so there is no middle to trim.

### 5.14 The realism audit as a live instrument — side access measured, rejected, outperformed
An alternative fix — letting pickers enter a pod from all four adjacent cells — cut the worst wait
448 → 104 but was then **measured against the audit**: storage runs 97.1% full mid-episode, and **98%
of side-access traversals passed through a cell holding a parked pod** — walking through a rack. It was
retired, and the realistic replacement (the rendezvous swap, a pure dispatch change) **matched or beat
it on every metric**. The audit is not a one-off table; it is a rejection criterion that improved the
final system.

### 5.15 M1 closeout — ladders and weight flatness on both regimes (champion v6, RATE_ALPHA=7)

All on the dense map with the full liveness stack applied to **every** arm (the stack is
execution-layer physics, not part of the decision layer under test), 144 paired seeds per regime.
Champion v6 = the v5 stack + RATE_ALPHA=7 (shipped at the project's revised t ≥ 2 bar after a
monotone 5→8 dose–response and a pre-registered 288-seed confirmation: +0.61%, t=+2.71, split-halves
+1.37/+2.52, frozen 0/288).

**Controller ladder, day-list:**

| arm | on-time value | vs FIFO | delivered | max wait | frozen |
|---|--:|--:|--:|--:|--:|
| FIFO | 649.27 | — | 500 | 495 | 11 |
| rush (value-greedy) | 682.96 | +5.2% | 553 | 194 | 12 |
| **champion v6** | **775.35*** | **+19.4%** | 570 | 70 | **0** |

**Controller ladder, stream:**

| arm | on-time value | vs FIFO | delivered | frozen |
|---|--:|--:|--:|--:|
| FIFO | 398.66 | — | 605 | 8 |
| rush (value-greedy) | 526.43 | +32.0% | 688 | 4 |
| **champion v6** | **583.59** | **+46.4%** | **759** | **0** |

\* the day ladder ran at the v5 stack (α=5); v6's day-list reference is 782.03.

**All pairwise significances** (paired t, 144 seeds):

| comparison | day-list | stream |
|---|--:|--:|
| rush vs FIFO | +2.71 | +9.18 |
| champion vs rush | **+10.15** | **+6.29** |
| champion vs FIFO | **+9.24** | **+12.62** |

Two claims fall out. First, the decision layer is worth **+19.4% (day) / +46.4% (stream)** over FIFO
and **+13.5% / +10.9%** over the best heuristic — the stream gap is the largest effect in the project.
Second, **the decision layer is part of liveness**: FIFO and rush freeze (8–12 instances) on the very
same env stack where the champion holds 0/144, in both regimes.

**Weights, day-list** (one knob away from champion; extended α/depth sweep; 144 seeds):

| arm | mean value | t vs champ | note |
|---|--:|--:|---|
| champion (α=5 at time of sweep) | 775.35 | — | |
| URG_W 0 / 8 everywhere | 775.35 / 775.28 | bit-id / −0.81 | day-list urgency weight is 0 by the regime rule |
| α = 5.5 / 6 / 6.5 / **7** / 8 | 777.7 / 778.4 / 780.6 / **782.0** / 782.6 | +1.27…**+2.56**…+2.12 | monotone climb, peak ≈ 7–8; α=7 shipped |
| SEQ_DEPTH 3 / 4 / 7 / 9 | 779.2 / 776.5 / 775.0 / 775.0 | +0.78 / +0.24 / −0.07 / −0.07 | saturated at 5; depth 3 carries a frozen instance |
| W_SYNC 0.15 | 775.31 | −0.70 | |

**Weights, stream** (one knob away from champion v6; 144 seeds):

| arm | mean value | t vs champ | note |
|---|--:|--:|---|
| champion (α=7, URG=8, depth 5) | 583.59 | — | |
| URG_W 0 / 4 everywhere | 581.43 / 582.29 | −1.01 / −0.63 | first (weak) support for the stream urgency rule |
| α = 5 / 6 / 8 | 579.55 / 578.91 / 586.88 | −0.74 / −1.07 / +1.06 | α=7 validated in its second regime |
| SEQ_DEPTH 3 | 583.59 | **bit-identical** | stream queues exhaust the horizon before depth 3 |
| W_SYNC 0.15 | 582.25 | −0.59 | |

No knob clears the bar in either regime: **the champion's weights are flat on top in both worlds** —
the configuration is robust, not knife-edge-tuned. Two micro-findings: the urgency mechanism is
provably unused on day-list (bit-identical at URG=0) yet weakly load-bearing on stream, matching the
regime rule it encodes; and SEQ_DEPTH literally cannot bind on stream because arrivals keep the queue
shorter than the rollout's horizon.

**Route algorithm** (Yen's k=3 vs single A*-shortest, champion stack): day-list +0.68% (t=+1.67) for
A*, **stream −1.42% (t=−1.30)** — the trend reverses, pooled t=−0.41. By the pre-stated rule Yen's
k=3 stays: route diversity at dispatch earns its keep exactly when arrivals are bursty, and nowhere
else.

### 5.16 M2 closed — perfect disturbance information is *harmful* under a disciplined executor
Re-measured under champion v6 with the bounding pair (clairvoyant router vs debris-blind router),
144 paired seeds: at the calibrated debris rate VoPI = −0.04% (t=−0.18); at **10× debris,
VoPI = −1.18% (t=−2.60)** — the blind fleet *beats* the perfectly-informed fleet, significantly.
Frozen AGVs are 0 in every arm: liveness is debris-proof at 10×.

This is the project's **third** perfect-information-is-harmful result (demand foresight §5.3,
admission accuracy §5.7) — but a code audit prompted by the result sharpened its meaning: **debris in
this simulator has no execution-layer existence.** `disturbed` is consulted only by the spawner and by
`find_path`; nothing blocks movement through a disturbed cell, so a debris-blind robot drives straight
through. The measured cost of disturbances is therefore *entirely self-inflicted* — debris hurts only
the fleets that believe in it and detour around it, and VoPI ≤ 0 is close to structural. The honest
statement: **the real disturbance question — do physical blockages cost value, and does information
recover it — has not yet been tested here**, because physical blockage is not implemented. The belief map is thereby doubly dead: its premise
was to cheaply approximate clairvoyance, and there is no value in approximating a signal whose
perfect form costs 1.2%. **M2 closes as a signed negative**, and the M1 executor is the reason —
robustness at the movement layer substitutes for information at the planning layer.

**Scope of the claim.** The negative is conditional on three modeled properties of disturbances:
they are *transient* (amnesty ≈ 27 steps, comparable to a detour's cost), *point-sized* (one cell,
uncorrelated — maximally cheap to sidestep on contact), and *collisions are free* (discover-and-replan
costs a tick). Real disturbances persist for minutes-to-hours, correlate (a stalled robot seals a
one-wide lane end to end), and real collisions cost damage and safety stops. As persistence grows past
detour cost, or as collision cost grows past detour cost, VoPI must cross zero. The result therefore
defines a **phase boundary between "be robust" and "be informed"** — mapping it is the designated
M2 coda, which now has three parts: (i) implement execution-level enforcement (a disturbed cell
refuses entry, or entering it costs a collision penalty), (ii) sweep persistence (amnesty rate) ×
collision cost, (iii) audition the belief map on the informed side, and imperfect belief maps get their audition on
the informed side of that boundary, where approximate information should still capture most of the
(then-positive) value.

---

### 5.17 M3 closed — battery is free when charging is planned, and the sim can tune its own thresholds

**Setup.** Battery physics anchored to Robotnik spec: full discharge in 1,500 driving-steps
(compressed from the real ~21,600; the charge:discharge ratio 0.30 is preserved under compression,
so a charging robot is off-fleet for ~0.3× the runtime it buys back), carrying drains 1.5×, idling
0.25×, planning floor 0.10, hard-dead 0.02. Episodes start mid-day (levels U(0.15, 1.0)) so charging
binds. Charging happens at **dedicated shelf-free bays** — building infrastructure, fixed per floor
(4–12 by storage capacity), never storage slots: the earlier chargers-on-slots design was the root
of every battery failure mode we traced (a busy robot arriving at a shelf-bearing charger auto-lifts
the stored pod and becomes a missionless "zombie" wall; bare charger cells lure drops; parked
chargers eat the bare-slot supply until the warehouse saturates and delivered carriers starve at the
dock; below the emergency trigger a re-firing pod-drop wipes the path every tick and livelocks the
robot). Five controller-layer fixes, each traced per-instance, took frozen carriers **73 → 0/144**.

**Design (M3): feasibility + charge-to-need + timing.** Every funnel candidate is priced for
round-trip energy including the reserve to reach a bay from the end slot; infeasible tasks are
deleted like impossible-deadline tasks. A robot charges exactly when its feasible set empties, to a
**charge-to-need** target (need × pessimism + floor + margin) with early release — never to full
(a full charge is ~30% of a shift; charge-to-full alone costs −3–5%). A **concurrency cap** (≤2
planned trips) prevents the measured death spiral where half the fleet charged simultaneously,
deliveries lagged, goods-to-person batching inflated station dwell (6 steps × items ≈ 100–180
steps), and the day died.

**Result.** 144 seeds, paired: no-battery ceiling 783.97; Stage-0 thresholds (charge at 0.35, to
0.95) **−3.1%**; the shipped `m3mpc` **784.49 (+0.1% = noise)** with **frozen 0/144 and stranded
0/144** (fleet minimum level 0.077). Managed well, battery physics costs *nothing at zero
casualties* — and the old −1.1% penalty was mostly a slot-liquidity tax of chargers squatting
storage cells, not an energy cost. The zero-stranded line required one forensic finding: every
hard-dead robot in the earlier builds was a **picker worked to death** — the charge rule fired only
when idle, and busy days never idle a picker. The fix that survived (after a mission-level preempt
was silently overwritten by the dispatcher within the same tick) is enforcement at the **action
layer**: a picker below half its threshold has its charge mission restored and its move forced
toward a bay every tick — the dispatcher may rewrite the mission, never the move — with
charge-to-need applied to pickers as well (a charge-to-0.9 outage is ~315 steps; to θ+0.1 is ~110).

**MPC-over-parameters: the sim as its own world model.** The champion's third simulation rung
(after rollout task pricing and `clash_sim`): every 50 steps the controller **forks the live
warehouse (deepcopy) and plays 100 steps of the true physics forward** under the incumbent setting
plus three UCB-chosen variants of (battery pessimism, picker threshold, charge cap), scores each
future by on-time value − 100·hard-dead − 20·floor-breach, and adopts the winner. Ties keep the
incumbent. This is receding-horizon MPC with a known model, searching policy *parameters* rather
than actions; in the day-list regime the fork's demand foresight is legitimate (the day is known).

**Campaign.** A self-updating sequential-testing driver (deepen uncertain cells with disjoint
36-seed blocks; explore new cells otherwise; verdict at |z| ≥ 2) ran the tuner against fixed
constants across **30 warehouse configurations** — five map sizes × two aisle geometries × fleet
mixes from 3-2 to 19-9. Final era-1 outcome (grid saturated at 99 blocks ≈ 7,100 paired days): **16 of 30 cells
MPC-ADOPTED, 0 resolved negative**, remainder flat or parked; pooled z = **+8.4**; mean effect
+0.31%/day lifetime and ≈ +1%/day on the final controller. Effect size scales with how *logistical* charging is: up to +1.15% on
the densest floors, adopted even for a 3-AGV skeleton fleet on a large map, and inert exactly where
it should be — small maps (chargers always near; stranded 0 with no tuning) and dual-carriageway
floors (wide opposing lanes erase the congestion whose time-variation the tuner monetizes).
Mechanistically, on dense fleets ~37% of replans adopt a non-shipped setting, **bimodally**:
pessimism drops to ~1.3 when the simulated future is safe (work more, charge later) and the picker
threshold rises to ~0.5 ahead of a crunch — the optimal charging policy is time-varying, and the
forward simulation times the switches. No fixed constant, hand-tuned or fitted, can do that.

**Weights are context-robust; thresholds are not.** Given the same freedom over the champion's
decision weights (RATE_ALPHA, SEQ_DEPTH, urgency weight, clash hysteresis, each with local moves),
the tuner moved them in **0–1% of 4,572 adoptions** across every tested context — §5.15's
weight-flatness generalizes from one map to the whole grid. The dichotomy is the finding:
**dispatch weights generalize across warehouses; energy thresholds do not** — which is precisely
why the thresholds deserve a run-time tuner and the weights do not.

**Stream regime: the tuner ships there too, and the honest fork wins.** On the live stream
(arrivals invisible until they land) the fork mechanically contains only currently-visible tasks —
rollouts never advance the demand process, so there is no clairvoyance to plug. Tested head-to-head,
these **visible-task forks beat belief forks** (arrivals sampled inside the rollout from the demand
statistics the robots legitimately own): +1.85% vs +0.79% on matched seeds — §5.3's "foresight is
harmful" result, reproduced at the parameter-tuning layer with *statistical* rather than perfect
foresight. Visible-fork MPC vs fixed constants over six independent 36-seed blocks on two warehouse
types: every block positive, **pooled z = +2.76 over 216 paired days**, mean ≈ +1.8%/day — roughly
double the day-list effect, consistent with the mechanism: an unknown future leaves more
time-variation to exploit. In one block the fixed arm froze two carriers and the tuner froze none —
under stream chaos the forward simulation doubles as a liveness aid.

**The shipped champion is now `m3mpc`**: champion v6 + M3 battery management + the embedded
forward-simulation tuner (auto-disabled below 100 storage slots, where it is provably useless), on
both demand regimes.

---

### 5.18 M2 coda closed — the VoPI phase boundary, and what honest sensing is worth

We gave debris an execution-layer existence (`debris_hold_steps`: entering a disturbed cell
immobilizes the robot for k recovery steps) and swept collision cost × persistence, blind router
(belief threshold above any evidence) vs clairvoyant avoidance, four 24-seed blocks per cell.
**The phase boundary §5.16 predicted is real and monotone in collision cost**: with consequence-free
debris, information is *provably harmful* (day-long/hold-0: pooled z = −2.22 — the §5.16 negative,
now past the bar); by hold-20 it is *provably valuable* (transient/hold-20: z = +2.83); the crossing
sits at ~5–20 recovery steps at 2%/step debris. Persistence is second-order. Same warehouse, same
information — only the physics of consequence decides its sign.

On the valuable side we auditioned the **belief map**: line-of-sight sensing, decaying, fleet-shared
(one robot's collision becomes everyone's knowledge). Pooled over 96 seeds: clairvoyant VoPI
z = +2.81; belief captures **~65%** of it (87% on calm days, 57% under peak pressure where fast
debris turnover makes beliefs stale) while cutting collisions ~3×. The answer to the question that
opened this milestone — *shouldn't realistic, slightly-inaccurate knowledge still capture most of
the value?* — is yes, measured: about two-thirds, wherever the value exists at all.

A harsher, arguably more physical enforcement — **stuck until amnesty** (a robot entering debris is
immobilized until the debris is cleaned; cost = the hazard's remaining lifetime) — amplifies
everything: clairvoyant VoPI reaches **+68.1 (t = +5.51)**, the largest value-of-information ever
measured in this project (+8.7% of a day), and the belief map becomes independently significant
(+29.9, t = +3.89). Across the severity gradient the belief's *capture fraction falls* (87% → 57% →
44% → 28%) even as its absolute value grows tenfold: the more catastrophic one unseen hazard is,
the more the residual gap between seeing-most-things and seeing-everything costs — the economic
argument for better sensing scales with the stakes, and so does the remaining value of an oracle.

Finally, replacing the timed despawn with an **earned amnesty** — a single janitor summoned by the
fleet's sightings, walking the aisles and mopping each spill — collapses that oracle premium
entirely: blind 855.7, belief 863.6 (t = +1.77), clairvoyant 863.2 — **honest sensing captures
~100% of clairvoyant value**. With responsive cleanup, spills are too short-lived for avoidance
knowledge to matter; the residual value of information is *summoning the response*, which
line-of-sight sightings deliver as well as omniscience. The capture arc across all five regimes
(87% → 57% → 44% → 28% → ~100%) supports a clean claim: *the gap between honest sensing and
perfect information is a symptom of slow response to hazards, not of ignorance about them.*

A pure-accuracy audit (per-step recall of the believed-blocked set against the true disturbed
set, benchmarked against a perfect-memory oracle fed the identical line-of-sight stream) then
exposed the last inefficiency: the incremental Beta update lets stale clean-history outvote
fresh sightings — busy cells hold ~100 "clean" votes at equilibrium, so slower forgetting
*reduces* recall (38% at perfect memory) and uniform evidence scaling provably changes nothing.
Replacing votes with **observation-reset updates** (a look overwrites the cell's evidence —
last-observation-wins for noiseless sensors, plus decay toward ignorance) reaches 99.8% of the
sensing ceiling (recall 84.7% vs 84.9%, precision 95%, detection latency 19 steps) and converts
directly into value: +28.8 over the incremental map (t = +4.05), debris hits 236 → 80, raising
honest sensing from 38% to **83% of clairvoyant value**. The residual gap is physics — cells no
robot's sight crosses while dirty. *Most of the oracle premium was a bad update rule, not bad
eyes.*

Three codas complete the account. **First, the negative family.** Learning the disturbance
*process* — event size and spatial hazard — works (the fleet estimated mean event size 2.43
against a true 2.1 from sightings alone), but every way of spending that prediction measured
flat or negative: neighbor-suspicion avoidance (−0.4), hot-zone slow forgetting (−3.2, the sole
cause of the combined variant's loss), opportunistic scout detours priced into A* costs (−5.7),
and even pre-positioning the janitor at the learned hotspot (−0.3, despite zero opportunity
cost). The mechanism is consistent: at realistic spill rates, ordinary work traffic already
sweeps essentially the whole floor, so paid information-gathering buys what routine driving
collects free, and zone-level hazard knowledge cannot name the *cell*. One variant deserves
note: gating the estimated spread of a confirmed spill on *observability* — avoid a suspected
neighbor cell only until anyone's line of sight resolves it — repaired the entire −3.2 harm
(to +0.6, flat), confirming that the loss was lingering fear after cells were visibly clean,
never the caution itself. **Second, epistemics as architecture.** The shipped map now runs two
regimes: cells in any robot's sight read exact truth (a noiseless look leaves nothing to
estimate), and everything else is an explicit prediction decaying toward ignorance. This made
the decision bin *exactly* calibrated (stated 98.0% blocked vs observed 97.9%) while leaving
every routing decision unchanged; the residual overconfidence lives only in the idle prior,
the documented price of fast detection. The original 90% sensitivity target is provably
unattainable — the sensing ceiling given real trajectories is 84.9%, and the map sits at 99.8%
of it. **Third, the fix composes with planning.** The update-rule repair carries through the
model-predictive layer almost additively (+26.4 through the self-tuner vs +28.8 through fixed
constants), and the tuner's own edge *halved* on the repaired map (+4.4 → +2.1, adoptions
45 → 33): the tuner is a compensator, and it correctly goes quiet as the world's defaults
improve. Making the map's trust weights themselves tunable closed the loop — the tuner
auditioned trust moves inside its imagined futures and declined them, certifying the shipped
constants by forward simulation rather than fiat. Fork honesty was extended to match: imagined
rollouts re-seed the disturbance process, so the planner samples spill futures rather than
replaying the true one — the same discipline that made visible-only forks win on the stream
regime. A final revalidation closes the loop opened in the tuning study: with battery and
disturbances both live, the champion's dispatch constants were re-bracketed and every one held
(no perturbation within the significance bar; the sequencing depth is a two-sided local optimum;
the urgency weight is bit-inert). The decision layer's flatness, first measured in the clean
world, survives the full one.

The anticipation null also gains a fourth, harder leg. Its strongest remaining objection was
that our demand was spatially static — anticipation can only pay if the hotspot *moves*. We
calibrated within-day hotspot drift from a real order stream (the Instacart sample: three
department-groups whose demand shares swing 11–17% across the day, produce peaking mid-morning,
snacks and bakery mid-afternoon), replayed it through the exogenous scheduler, and re-ran the
value-of-perfect-information test. A short 25-step oracle preview leaned positive on the first
seed block (+4.6, t = +0.9) and inverted on a disjoint block twice the size (−5.3, t = −1.2):
pooled −2.0, z = −0.45 — flat; the full-day preview stayed flat-negative. Anticipation is not
rescued by realistic demand drift: every estimator was null, perfect information is harmful, no
horizon pays, and now — even when the hotspot genuinely moves at real-world magnitude — the
oracle still gains nothing. Its positional cousin dies by accounting: tracing every stream-day
pickup back to the assigned robot's preceding idle period shows idle-approach travel totals
2.4% of the fleet's step budget — 2.6 steps per pickup — because a robot that finishes a task
has, by finishing it, already positioned itself where the next order tends to appear. That 2.4%
is the teleportation ceiling for any pre-positioning policy; the realistic prize is a fraction
of it, and the mechanism was never built.

### 5.19 M4 closed — delay *is* partly predictable; the decision rule was built not to ask

The last learned head died the same disciplined death. Stage 3's surviving proposal — replace
the live delay-EMA with a state-conditional pace model — was run as a three-way gate: the EMA,
a LightGBM head on the assembler's fleet features, and a simulation arm that measures pace
inside the planner's own 50-step forks. The head beat the EMA's raw error by 15.4% but failed
calibration (slope 0.43), and a train-fitted recalibration made held-out error *worse* — the
edge does not transfer. The diagnosis is the finding: the EMA's own calibration slope is
*negative* (−0.23), because pace prediction here is endogenous to control — a high delay
forecast triggers conservative dispatch that falsifies the forecast. A predictor living inside
its own control loop punishes offline learning by construction, and a one-line trailing formula
that participates in the loop remains the right tool. The simulation arm is the sharper test of
that claim, because it is the same machinery that wins elsewhere in this system: reading pace
from inside the planner's own forks matched the formula and no more (+0.9%, 811 held-out tasks).
Forking pays for battery futures — physics the present does not reveal — and pays nothing for
pace, because pace is the system's own recent behavior, which a trailing average already
measures directly and with less noise than a short imagined rollout can.

Putting all three in the loop settles the milestone and explains the entire null family. Racing
the champion against a flat EMA pad, the fork-measured pace, and the per-candidate head on
held-out days gives 388.8 / 388.1 / 385.7 / 388.3 — every challenger flat or slightly negative.
The cause is structural rather than statistical: the champion's deadline score is a hard tier —
a task projected to make its deadline scores by *value alone*, with the finish estimate absent
from the expression — so a pace correction can only change a decision by flipping a task across
the makeable/doomed boundary. Instrumentation confirms it end to end: the head is live and
candidate-discriminating (its predictions differ by ~26 steps between candidates evaluated in
the same instant) and yet it changed *zero* of sixty-eight assignment decisions. The recurring
finding that task delay "cannot be predicted usefully" is therefore mis-stated. Delay is
partially predictable; the decision rule was designed not to consult it.

Improving the clock cannot help a controller that asks only whether a deadline is reachable and
then ranks by value — the lever, if one is ever wanted, is a smooth on-time-probability score, which
is a decision-layer redesign rather than a learned component.

### 5.20 M5 — head-to-head against the simulator's own dispatcher, safety, and inner-loop validation

**Figure 3** (`results/fig_benchmark.png`) is the headline result of this section.

**Benchmarks.** Against the simulator's own dispatcher and a value-plus-urgency baseline, on 144
paired days per regime (1,152 runs), the champion delivers 779.3 on-time value on wave days
versus 643.5 for FIFO and 684.8 for Rush (+21.1% and +13.8%; t = 9.1 and 9.2), and 602.0 on
live-stream days versus 408.0 and 542.4 (+47.5% and +11.0%; t = 12.4 and 5.3) — clearing the
pre-registered "at least FIFO, target +10%" bar in both regimes. The margins are conservative:
the baselines run without battery physics, so they pay no charging cost while the champion does.
The safety columns are as important as the value columns: across all 1,152 runs the champion and
its self-tuning variant stranded zero robots, and wedged carriers appear only once (a single
stream seed) against four to thirteen for the baselines in every cell. The self-tuner adds +0.5%
on wave (t = 2.41, clearing the significance bar at this sample size) and +0.9% on stream
(t = 1.08, below it), consistent in sign with the campaign's pooled estimate but not, on the
live-stream regime, in significance.

Repeating the comparison with disturbances active — the condition the benchmark was specified
for — widens every margin: 764.0 versus 580.6 (FIFO) and 659.7 (Rush) on wave days, 543.5 versus
338.9 and 467.4 on stream, i.e. **+31.6% and +60.4% over the simulator's own dispatcher**
(t = 11.0 and 12.5), with better deadline hit rates and lower tardiness at both the mean and the
95th percentile. The belief map and the repair layer are worth *more* precisely when the floor is
hazardous, which is the strongest available evidence that the decision layer's advantage is not
an artifact of a clean world. Two auxiliary results complete the suite. Collisions, measured
rather than assumed (the first pass silently read a nonexistent counter), are zero of both vertex
and swap type for every controller across 96,000 agent-steps per arm; replans per disturbance run
from 9.0 (FIFO) to 14.3 (champion), and the champion's higher replan rate is the mechanism paying
off, since it also yields the lowest stuck-time. And the inner-loop planner reproduces the
MovingAI benchmark cleanly: 1,800 scenarios solved at 100% (bar 98%), optimal on the warehouse
and empty maps against four-connected ground truth. The self-tuner's behaviour under noise is more
interesting than we first reported. On wave days with disturbances its edge does collapse to nothing
(+0.0%, t = 0.06): the forks now sample stochastic spill futures, the hazard noise swamps the
difference between candidate settings, and the tuner correctly abstains rather than chasing it. But
on *live-stream* days with disturbances it is worth **+3.2% (t = +3.62)** — its largest measured
edge anywhere, against +0.5% and +0.9% on clean floors. The two conditions differ in what there is
to find: a wave day is fully known at t = 0 and the champion's fixed constants are already near
optimal for it, whereas a live-stream day under hazards keeps changing what the right settings are,
and re-deciding them every fifty steps pays. Imagination earns its keep where the world moves, and
abstains where it does not — which is the same lesson as §5.26's horizon, arrived at from the other
direction. *(An earlier draft reported the tuner as quiet in both disturbed regimes, +0.0% / +0.2%;
that came from the pre-2026-08-25 benchmark table and did not survive re-measurement.)*

### 5.21 A learned dispatcher, given exactly the same information

The strongest objection to the ladder in §5.20 is that both baselines are heuristics — one vendored,
one ours — so the comparison never shows what a *learner* would do with the same problem. We built
one. `scripts/marl_dispatch.py` is a shared-parameter policy, MLP(24→64→64→1), that scores exactly the
candidate set the champion scores, on exactly the 24 assembler features the champion sees, plugged
into the same `_pick_winner` slot; routing, picker sequencing, battery machinery and the referee are
untouched. **Only the choice is learned.** Training is REINFORCE with a running baseline and an
entropy bonus, dense per-decision credit (each decision credited with the on-time value the task it
chose actually banked), softmax sampling in training and argmax at evaluation: 40 iterations × 24
episodes = **960 training days** on seeds 1–96.

The level was chosen deliberately. RWARE-standard *move-level* MARL would spend most of its capacity
learning locomotion and is known to trail greedy heuristics at this fleet size; scoring the same
candidates isolates the decision layer, which is the claim actually under test.

It learns — mean episode value rises from 895 to ≈930 over the 40 iterations. On held-out seeds
97–144, evaluated greedily: **champion 388.75 vs learned 368.20, −5.3% (t = −5.57, 7 wins in 48)**.
Placed among the others on the identical seeds: FIFO 357.30 < **MARL 368.20** < Rush 370.24 <
champion 388.75 < champion + tuner 389.42. The learned policy therefore **beats the simulator's own
dispatcher and ties the value-plus-urgency rule** — it is a real opponent, not a broken one — and
still loses to the rules. This is §5.9's flatness result seen from the other side: the decision layer
is near-maximal for this information set, and a policy-gradient learner with identical inputs cannot
find headroom the rules leave behind.

The caveats are stated because the claim is a negative one: REINFORCE rather than PPO, ~960 episodes,
no hyperparameter search, one fleet and one map. A tuned PPO with 10–100× the budget might close or
invert the 5.3%. This is evidence about *where the headroom is not*, not a proof of impossibility.
(Seed ranges also differ in richness — `window_index = seed` maps to a diurnal phase, so seeds 1–96
average 974.5 against 388.8 for seeds 97–144 under the champion. Every comparison above is within-seed
paired, so the split is harmless, but raw values must never be compared across ranges.) **The decision
layer ships with zero learned components, by measurement rather than by ideology.**

### 5.22 The belief map graded as a forecaster, not only as a router

Every claim about the belief map so far has been a *value* claim: routing on it is worth so many
points. The proposal also promised to grade it as what it structurally is — a per-cell probabilistic
detector of "this cell is blocked right now" — so we did, taking the map's own numbers at face value
with no thresholding. `scripts/exp_m5_brier.py` runs two arms on identical seeds, the shipped
observation-reset map and the pre-2026-08-23 incremental-vote map, scored on **every highway cell at
every step** of 24 days — ≈**4.8M predictions per arm** — accumulated into 1000-bin score histograms
so nothing has to be held in memory.

| measure | shipped (reset) | legacy (votes) |
|---|---|---|
| Brier score (lower better) | **0.0204** | 0.0310 |
| skill vs the base-rate reference | **+0.351** | +0.013 |
| AUPRC (random = 0.032) | **0.367** | 0.260 |
| sensitivity at the decision threshold | **84.76%** | 75.30% |
| specificity at the decision threshold | **99.87%** | 99.76% |
| precision at the decision threshold | **95.58%** | 91.45% |
| false-positive rate | **0.131%** | 0.236% |
| detection latency, mean / median | 20.4 / 2 | 18.8 / 1 |

The confusion matrix behind the shipped column, over 2.55M highway cell-steps: TP 72,672 ·
FN 13,067 · FP 3,358 · TN 2,550,903.

**The base rate matters more than the raw Brier does.** Only **3.2%** of cells are blocked at any
moment, so a degenerate forecaster that ignores its sensors and answers "3.2%" everywhere already
scores 0.031 — within a third of the shipped map's error, purely because blockages are rare. Skill
removes that floor: the shipped map eliminates 35.1% of the reference forecaster's error, while **the
map it replaced eliminated 1.3%**. The old map was a genuinely useful thing to route on and *almost no
forecaster at all*. No value experiment could have drawn that distinction, because a router needs its
ordering to be right only where it acts.

**Calibration is exact where the map acts, and deliberately wrong where it does not.** Beliefs are
near-binary — nearly all the mass sits at the two ends — and the decision bin lands on the diagonal
(**stated 98.0% blocked vs observed 97.9%**). The reliability curve sags in the middle because
unobserved cells sit at 0.5 by convention and are almost never actually blocked. That is a documented
design choice, not an artefact: replacing the convention with the true base rate was tried and
rejected, because it rebuilds the mountain of stale "probably clean" evidence the reset rule exists to
remove (§5.18).

**The most informative panel is the one where nothing happens.** Detection latency is *identical*
across the two arms (median 1–2 steps). Both maps see every spill immediately; the entire +28.8 value
difference comes from what happens *after* the sighting, when the old map lets a few steps of
accumulated clean-history outvote fresh evidence and forgets what it has just seen. The improvement
was never perception — it was memory, and two coincident CDFs are the cleanest available proof,
because they rule out the explanation a reader would otherwise assume.

**On the 90/90 bar this project set itself.** The pre-registered target was 90% sensitivity *and*
90% specificity. Specificity passes enormously — 99.87% — and we report that with a caveat rather
than as a win, because **at a 3.2% base rate specificity is the easy half**: a map that says "clear"
everywhere scores 100% specificity and 0% sensitivity, so the constraint was never really binding.
The binding half is sensitivity, and it is the one that cannot be met: 84.76% against a physical
sensing ceiling of 84.9% (§5.18). A 90/90 pair was the wrong pre-registration for a detector at this
prevalence; the right one is the pairing we ended up reporting — sensitivity against its ceiling,
and precision or false-positive rate, which at 95.58% and 0.131% are the numbers a router actually
feels.

One boundary is load-bearing and worth stating because we got it wrong first. Unobserved cells sit
at *exactly* 0.5 by convention, and the router uses a strict `belief > 0.5`; scoring with `>=`
instead sweeps the entire uninformed prior into the positive class and reports specificity 94.7% and
precision 36.0% for the same map. Both are "correct" arithmetic on the same histogram. When a
detector parks its don't-know mass on the decision boundary, the inequality is part of the metric
definition, not an implementation detail.

**Figure 4** (`results/m5_belief_curves.png`) — precision–recall, reliability, and detection-latency
CDF, both arms overlaid.

### 5.23 What prediction itself is worth

**Figure 5** (`results/fig_sensing.png`) is the clearest single picture in the paper.

Finally, decomposing the sensing value isolates what prediction itself is worth. A fleet that
routes only around hazards *currently in someone's view* (no memory) captures most of the
benefit when sensors are generous (sight radius 5: eyes +36.7, prediction +12.8 — 74/26), but
the split inverts at honest sensor ranges: with near-contact sensing (radius 1, the realistic
model for camera-less drive units), eyes alone are worth +6.5 while prediction — remembering
each encounter and believing it until seen clean — is worth **+20.3 (t = +2.28)**, 76% of the
sensing value and still 48.5% of the full clairvoyant premium. *The worse the sensors, the more
the world model is the sensor.* Sight radius is exposed as a world knob (r3 ≈ r5 within noise;
below r3 each lost meter costs real value), and it is deliberately not a policy knob: hardware
is not a decision, and a planner that imagines better cameras into its forks would be cheating
by construction.

### 5.24 The consolidated ablation ledger

`docs/ABLATION.md` collects every mechanism ever built for this project and judges it against the
standing rule — **≥3% or cut**, on paired seeds, with safety mechanisms judged on the hard constraints
instead of on value. The count is **ten shipped, twenty-two measured and cut**.

Shipped: the board rollout (**−7.2% if removed**, t = −30.6, the largest single mechanism effect in
the project), value-rate picker sequencing, belief-map routing (**+6.2%** under spills, 800.6 → 850.1,
collisions 364 → 80), the reset update rule (**+3.5%**), the sight-is-certainty / out-of-sight-is-
prediction split, battery management (value-neutral at 784.5 vs 784.0 with free energy, and 0 stranded
/ 0 frozen across 144 audited days), dedicated charger bays, the janitor, the MPC self-tuner
(~+1%/day pooled, z = +11.2 across 46 configs), and the deadlock/flow flags (`free_pod_return` alone
eliminating 100% of permanent deadlock on dense maps). Cut: five anticipation mechanisms, six
hazard-guess mechanisms, five learned components, and six others (the sixth being the spare-storage
sweep of §5.27).

**Figure 6** (`results/fig_ablation.png`) renders the whole ledger as one page.

Read as two halves, the ledger states the thesis without any prose. **Everything kept reasons about
things that already exist** — the tasks in hand, the batteries draining, the spill somebody saw.
**Everything cut tried to act on something that did not exist yet**, or on a guess no observation had
confirmed. The ledger is cheap to produce only because the bar was fixed before the experiments, which
is the methodological point: a 3% rule chosen afterwards would have kept several of the twenty-two.

### 5.25 Charging foresight — the sixth leg of the anticipation null, and a real finding underneath it

Five channels had been tested for the value of perfect information: which task to take, how far ahead
to look, drifting hotspots, where to park idle robots, and which cells will get dirty. One remained —
**when to charge** — and it was the most plausible of the six, because charging is the one decision
whose consequences unfold over a horizon long enough for a forecast to matter.

`scripts/exp_charge_foresight.py`, on stress days (`M3SPC=300` plus low starting charge, the regime
where charging binds), 48 paired seeds, threshold re-evaluated every 25 steps with a 0.03 deadband:

| arm | value | vs base | stranded | mean threshold |
|---|---|---|---|---|
| base — fixed threshold | 742.30 | — | 123 | 0.400 |
| **fore** — *true* oracle preview of arrivals | 771.62 | +29.33 (t = +1.34) | 108 | 0.377 |
| **shuf** — *scrambled* preview (wrong half of the day) | **792.57** | **+50.27 (t = +3.15)** | 104 | 0.377 |
| hi — constant higher threshold | 761.04 | +18.74 (t = +0.84) | 112 | 0.460 |
| const — constant at the varying arm's own mean | 744.25 | +1.95 (t = +0.10) | 117 | 0.377 |

**Foresight does not pay on the charging channel either.** The deliberately wrong forecast *beats* the
true one, and a constant threshold at the same mean is worth nothing. The information content is
worthless. This is the sixth independent leg of the anticipation null and the sharpest of them,
because the control this time is the same policy driven by noise rather than a policy without the
mechanism at all.

The finding is what is left once the information is subtracted. What pays is **threshold variation**,
and the cause is an asymmetry in what a threshold change does: raising a charge threshold *causes* a
charge event, while lowering one merely *postpones* one. An oscillating threshold therefore ratchets
charge frequency up — 22.8 trips per day against 20.0 — even though its mean is *lower* (0.377 vs
0.400), and it buys the safety benefit intermittently instead of paying for it all day as a
constant-high threshold does (23.5 trips for only +2.5%). Desynchronisation was tested and rejected as
the explanation: the varying arm clusters charge starts *more* (3.8 vs 2.5 within three steps) at
identical concurrency.

(A live defect surfaced en route and was fixed: `sim_dashboard.py:210` raised `KeyError` when a
charge decision preempted a returning mission; since the MPC retunes θ every 50 steps this was a
production crash risk, not an experiment artefact.)

**Built, and it is the largest single mechanism found since the belief map.** The result above was
obtained through a forecast-shaped wrapper, which leaves open whether the effect survives when the
forecast machinery is removed entirely. `scripts/exp_theta_oscillation.py` implements the mechanism
directly — θ alternates by ±A every 25 steps around whatever level is current, reading no state and
consulting nothing — and races it against the shipped self-tuner, which already owns θ as a *level*
via its `th+`/`th-` moves. Stress days, 48 paired seeds:

| arm | value | vs fixed | t | vs tuner | stranded | charge trips/day | mean θ |
|---|---|---|---|---|---|---|---|
| fixed θ = 0.40 (shipped) | 742.30 | — | — | — | 123 | 103.9 | 0.400 |
| oscillation, A = 0.07 | 801.95 | +59.66 | +2.91 | — | **72** | 113.2 | 0.400 |
| oscillation, A = 0.10 | 805.49 | +63.20 | +2.68 | — | 80 | 111.8 | 0.400 |
| the self-tuner (θ as a level) | 799.87 | +57.57 | +3.23 | — | 95 | 106.2 | 0.393 |
| **self-tuner + oscillation** | **833.49** | **+91.19** | **+3.81** | **+33.62** | 93 | 100.7 | 0.289 |

Two things fall out. First, **a rule with no information in it matches the entire self-tuner**:
+63.2 against +57.6, from one line that alternates a number, versus a controller that deep-copies the
whole warehouse every fifty steps and simulates candidate settings a hundred steps forward. The mean
θ is identical to the fixed arm by construction (0.400), so the gain is movement and nothing else.
Second, **it composes**: layering oscillation on the tuner is worth a further +33.6, so the two are
not competing for the same effect and oscillation is a genuinely new axis rather than a cheaper route
to the level the tuner would have found. That is the answer to the question the experiment was built
to settle — it belongs in the move set.

The combined arm also shows what the asymmetry buys. It settles at a mean θ of **0.289**, far below
the shipped 0.400, and still strands 93 against the tuner's 95 — but on *fewer* charge trips (100.7
against 106.2). Oscillation therefore does not simply buy safety by charging more; run on top of a
tuner that is free to lower the level, it buys the same safety at a lower standing cost, which is a
different and better mechanism than the one the foresight experiment exposed. We flag that as a
finding with one measurement behind it rather than a settled account.

**The ordinary-day gate refuses it, and that is the most useful part of the result.** Same protocol,
48 paired ordinary wave days:

| arm | value | vs fixed | t | vs tuner | stranded | trips/day | mean θ |
|---|---|---|---|---|---|---|---|
| fixed θ = 0.40 | 1052.36 | — | — | — | **0** | 50.5 | 0.400 |
| oscillation, A = 0.10 | 1039.12 | −13.23 | −1.64 | — | 0 | 55.5 | 0.400 |
| the self-tuner | 1061.22 | +8.86 | +2.14 | — | 0 | 51.0 | 0.411 |
| self-tuner + oscillation | 1048.65 | −3.70 | −0.49 | **−12.57** | 0 | 48.8 | 0.256 |

On an ordinary day oscillation is mildly negative on its own and *erases the tuner's edge* when
layered on top (+8.86 → −3.70). The mechanism is legible in the stranded column: it is **zero in
every arm**, so the safety the oscillation buys is worth nothing, and the extra charge trips (55.5
against 50.5) are pure cost. The same mechanism is worth **+91 on a stress day and −4 on an ordinary
one** — a swing of nearly a hundred points from the regime alone.

So it must never be a default, and the right home for it is exactly the one the numbers point at:
**a move in the tuner's set**, auditioned in forward simulation and adopted only where it pays. The
tuner has already demonstrated it will decline moves that do not help — it auditioned the
belief-trust knobs and kept the constants (§5.17) — and a mechanism this regime-dependent is the
strongest argument we have for why a self-tuner is worth its compute at all: no fixed constant can
be right for both of these days, and the tuner does not have to be.

This is also the clearest vindication of the standing rule that a mechanism must be validated in the
deployment regime. Measured only where it was discovered, oscillation looks like the largest single
win in the project since the belief map. Measured one regime over, it is a regression.

### 5.26 The tuner's horizon was too short

The deferred "tune the tuner later" item. `scripts/exp_mpc_cadence.py`, stress days, 48 paired seeds,
against the fixed-constant control:

| cadence / horizon | value | vs fixed | t | adoptions | imagined steps/day | stranded |
|---|---|---|---|---|---|---|
| fixed (no MPC) | 742.30 | — | — | 0 | 0 | 123 |
| 25 / 50 | 789.02 | +46.72 | +2.51 | 129 | 2,909 | 88 |
| 25 / 100 | 815.35 | +73.05 | +3.73 | 211 | 5,543 | 69 |
| **50 / 100 (shipped)** | 799.87 | +57.57 | +3.23 | 127 | 2,952 | 95 |
| 50 / 200 | **838.99** | **+96.69** | **+5.86** | 137 | 5,770 | 66 |
| 100 / 200 | 817.64 | +75.34 | +5.07 | 90 | 3,000 | **63** |

**Figure 7** (`results/fig_horizon.png`) plots value against compute for the whole grid.

**Horizon is the lever; cadence is not.** Doubling the horizon at the shipped cadence is worth +39
more value than the shipped setting and cuts strandings from 95 to 66. Halving the cadence at a fixed
horizon buys +16 for twice the forks. The best value per unit of compute is **100/200**: +75.3
(t = +5.07) at 3,000 imagined steps per day — the *same* budget the shipped 50/100 spends — with the
fewest strandings of any cell tested.

The mechanism is the very failure the horizon exists to prevent, merely mis-sized: a charge round-trip
plus its productive tail does not fit inside 100 steps, so the shipped tuner was scoring candidate
settings before their cost or their benefit had landed. The rollouts were never wrong; they were
short.

**The ordinary-day re-check.** Because that grid was measured only where charging binds, we re-ran it
on ordinary wave days, 48 paired seeds, against the same fixed-constant control:

| cadence / horizon | value | vs fixed | t | imagined steps/day |
|---|---|---|---|---|
| fixed (no MPC) | 1052.36 | — | — | 0 |
| **50 / 100 (shipped)** | 1061.22 | +8.86 | +2.14 | 3,000 |
| 100 / 200 | 1060.96 | +8.60 | +2.08 | 3,000 |
| 50 / 200 | 1064.61 | +12.25 | +2.92 | 6,008 |

Repeating it on ordinary live-stream days puts every cell inside the noise — fixed 840.81, shipped
+4.43 (t = +0.44), 100/200 +2.47 (t = +0.20), 50/200 +10.50 (t = +0.90) — which is the same verdict
in a weaker instrument: on a day where charging does not bind, the tuner has little to find and the
horizon does not matter either way.

On an ordinary wave day the longer horizon is **neutral** — 100/200 and the shipped 50/100 are
indistinguishable (+8.60 vs +8.86) at identical compute — and doubling the fork budget buys a further
+3.4 (t = +2.92). Nothing regresses in either regime. Combined with the stress grid, where 100/200 is worth +17.8 over
the shipped setting for the same compute and cuts strandings from 95 to 63, the case is a free one:
**adopt 100/200**. It costs nothing on the days that do not need it and pays on the days that do,
which is the correct shape for a safety-relevant parameter.


### 5.27 The last liveness defect: a silent bug, a fix that relocates it, and why the fix does not ship

One live-stream day (seed 125) wedged two carriers for the last hundred steps of the episode; 574 of
576 benchmark runs were clean. The diagnosis on record was structural — the floor has no spare
storage, so an AGV holding a pod can find every legal slot occupied. Auditing that in order to build
the fix turned up something else first, and the something else is the more useful result.

**The bug.** `_recalc_grid()` rebuilds the whole occupancy grid from `env.shelfs` at the end of
*every* step. `setup_bays()` — which implements the standing world rule that a charger cell carries
no pod — cleared those pods straight out of the `SHELVES` layer, and the next step silently put them
back. The rule had therefore never been in force during any run we ever measured, and the floor was
worse than the diagnosis said: 180 storage cells, 8 of them charger bays excluded from the champion's
drop selection, so the *intended* floor is **172 pods for 172 legal slots** — exactly zero slack —
while the floor we actually ran was **180 pods for 172 legal slots**, negative slack of eight.

**The fix works, and relocates the failure.** Retiring those pods properly (a `_removed_shelf_ids`
set that `_recalc_grid` honours; `env.shelfs` cannot be mutated, because `shelfs[id − 1]` indexing is
pervasive) and sweeping extra slack on top, on the held-out live-stream block, 48 paired seeds:

| floor | spare cells | value | vs legacy | t | frozen carriers |
|---|---|---|---|---|---|
| legacy (180 pods / 172 slots) | 0 | 290.38 | — | — | 2 (seed 125) |
| pods retired (172 / 172, zero slack as documented) | 0 | 283.34 | −7.05 | −0.77 | **2 (seed 106)** |
| + 2% spare | 3 | 278.92 | −11.47 | −1.56 | 2 (seed 106) |
| + 5% spare | 9 | 280.60 | −9.79 | −1.09 | 2 (seed 106) |

Seed 125 closes and stays closed at every slack level; **seed 106, clean under the legacy floor,
wedges under all three corrected floors**. Adding genuinely empty slots on top changes neither the
wedge nor the value. Two wedged carriers in 48 days before, two after, on a different day: this is
the fourth time in this project that a rare-event fix has **relocated** the residual failure rather
than removing it, and the cleanest instance. Slack was the hypothesis; slack was supplied; the wedge
moved. The value column cannot arbitrate — at −7.05, t = −0.77, the arms are indistinguishable.

**Why it does not ship, and the reason is the finding.** Re-verifying the head-to-head on the
corrected floor showed the change is not neutral between arms. On live-stream days the *baseline*
moved: FIFO fell 39 points while the champion moved +13, so our reported margin would have widened
from **+62.6% to +80.7%** — an eighteen-point gain banked entirely from the opponent getting worse.
The mechanism is plain once seen. An occupied cell is what makes a charger bay invisible to a
controller's empty-slot search; `charger_keepout` is a champion-side notion that the vendored
dispatcher has no equivalent of. With the pods genuinely gone, FIFO starts parking pods on charger
bays and the champion does not. **The pod on the bay was load-bearing, and the rule it violated was
cosmetic.** Making the world match its stated rule therefore requires first making bays
non-targetable at the *environment* level, for every controller equally; until that exists, retiring
the pods buys realism in the diagram and an unearned margin in the table.

So: the bug is documented, the `_removed_shelf_ids` mechanism stays in the simulator (the spare-slot
sweep needs it), `setup_bays` deliberately keeps the pod with the reasoning recorded at the call
site, the extra-slack sweep is **cut**, and the liveness item **stays open**. The generalisable
lesson is the one we would want a reviewer to take: *when a fix moves your headline, check whether it
moved your baseline, and check it in the direction that would embarrass you.* A change that improves
your margin by degrading the opponent is not an improvement, and it is very easy to bank one by
accident while fixing something real.

---

## 6. Discussion — principles the results support
- **Avoid, don't predict.** Every attempt to *estimate* delay failed; using known robot futures to
  *avoid* congestion worked.
- **Re-plan, don't commit.** Obeying the imagined plan open-loop loses value; only the first move is
  trustworthy.
- **Predict carefully to choose; optimistically to admit.** Pessimism is unrecoverable at an admission
  gate — a task never attempted banks zero for certain.
- **Additive score nudges cannot compete with a gate.** Knobs worth ~1 point cannot move a task across
  a 1000-point tier boundary; expect null (predicted in advance, confirmed for `W_SYNC`, `CONG_*`).
- **Verify an arm differs from its parent before believing its null.** Four arms in this project
  produced plausible numbers while measuring nothing.
- **Audit the world's constants before tuning the policy.** Ours were wrong by 280× (clock), 2× (density)
  and ∞ (service time), and correcting them changed nearly every result.
- **Measure the failing subsystem, not the aggregate.** A fleet-wide movement average hid total AGV
  deadlock behind picker shuffling for eight failed fixes; the per-carrier metric exposed a 51% rate.
- **Uncross the errands, not the robots.** Physically impossible swaps dissolve at the dispatch layer
  for free; every attempt to solve them at the movement layer cost liveness (§5.12 vs §5.13).
- **Grade a belief as a forecaster, not only as a router.** A map can be worth routing on and still
  carry essentially no probabilistic skill (§5.22: +0.013). Only the forecaster grading separates a
  useful *ordering* from honest *numbers*, and only the latter survives a change of decision rule.
- **When an intervention helps, look for the panel where nothing changes.** Identical detection-latency
  curves are what proved the belief fix was about memory rather than perception (§5.22); the value
  number alone was compatible with either story.
- **Include a scrambled-information control, not just an uninformed one.** Twice in this project a
  randomised forecast matched or beat the true one (§5.25), converting "our forecast helps" into
  "moving this parameter helps" — a different, cheaper, and more honest mechanism.
- **A learner is the right control for "your baselines are heuristics".** Building the opponent that
  the reviewer would ask for costs one experiment and settles the objection either way (§5.21).
- **When a fix moves your headline, check whether it moved your baseline.** Retiring the pods from
  the charger bays was a real correctness fix that would have widened our reported margin from
  +62.6% to +80.7% — every point of it from the opponent getting worse, because an occupied cell is
  what hides a bay from a controller that has no notion of keep-out (§5.27). Re-run the baseline
  after any world change, and look first in the direction that would embarrass you.
- **Size a lookahead against the duration of the decision it must judge.** The tuner's horizon was
  shorter than a charge round-trip, so it scored settings before their consequences landed (§5.26) —
  the failure the horizon exists to prevent, arrived at by mis-sizing rather than by omission.
- **At 1-in-144 rarity, a fix must beat the cost of re-verifying.** Rare-event fixes perturb dynamics
  and can *relocate* the residual failure rather than remove it (observed three times); ship only what
  converges under the full audit.

## 7. Limitations
- **Ratio coverage.** The corrected-world sweeps use **3 of 36** AGV×picker cells; ratio-dependence is
  undetectable and the nulls are ~3× less powered than the pre-audit ones.
- **One-way lanes** are implemented but off by default; the reported dense-map numbers use bidirectional
  lanes, which is *harsher* than reality in narrow aisles.
- **Uncalibrated constants**, declared not hidden: `disturb_rate` (no public data exists), amnesty
  duration, utilisation operating point, and the demand-shape parameters (`zipf_s`, Hawkes, `n_hot`,
  `slot_jitter`, `rush_frac`) whose *mechanisms* are literature-backed but whose *magnitudes* were chosen.
- **Collisions = 0** holds for committed *routes* by construction, not executed positions (measured: 2
  of 800 runs had a co-located pair, caused by a since-fixed silencing defect). Robot–robot collisions
  are impossible by referee construction; picker–AGV co-occupancy at a rendezvous is the sanctioned
  load handshake, not a collision.
- ~~**Debris is planning-layer-only**~~ **RESOLVED** (§5.18): debris now has an execution-layer
  existence (`debris_hold_steps`), and the sign of the information's value was shown to depend
  monotonically on that consequence cost. §5.6/§5.16's negatives should be read as the
  consequence-free end of that gradient, not as a general result.
- ~~**Disturbances are off** in the headline results~~ **RESOLVED** (§5.20): both regimes are now
  reported with disturbances active, and the margins are *larger* there. Battery remains at
  compressed scale (1,500-step discharge vs the real ~21,600) with the charge:discharge ratio
  preserved — the absolute timescale, not the trade-off structure, is the unrealistic part.
- **The headline benchmark table was re-measured, and the process failure behind it is worth
  reporting.** `results/m5_bench.csv` was produced on 2026-08-24; `wwm_sim/warehouse.py` changed on
  2026-08-25, and the table was never re-run. A full 1,152-run re-measurement on current code
  (`results/m5_bench_current.csv`, 2026-09-06) resolves it: **wave is bit-identical** (643.5 / 684.8 /
  779.3 / 782.9), while every live-stream value rose by 40–55 points — FIFO 368.0 → 408.0, champion
  547.8 → 602.0 — so the live-stream margin moves **+48.9% → +47.5%** (t = 12.4) and the tuner's
  live-stream edge falls from +1.7% (t = 1.90) to +0.9% (t = 1.08), i.e. below the bar. All numbers
  in this paper are the re-measured ones. The claim survived because it is a *paired* margin, but
  the near-miss is the point: nothing in our process forced a re-run after a simulator change, and
  the absolute values were wrong for twelve days. Re-running the benchmark on every simulator commit
  is now the rule.
- **One open liveness defect** (§5.20, seed 125, live-stream): two carriers frozen for the last 100
  steps under both champion and tuner — 574 of 576 runs clean. **Chased down in §5.27 and still open.** The
  structural diagnosis (no spare storage) was tested by supplying slack, and the wedge relocated to
  another seed rather than closing; the audit did turn up a real bug — the "charger cells carry no
  pod" rule was silently inert — but correcting it handicaps the vendored baseline, so it does not
  ship. The wedge is therefore *not* a storage-slack phenomenon, and its actual mechanism is unknown.
- **The learned opponent is modestly resourced** (§5.21): REINFORCE rather than PPO, ~960 episodes, no
  hyperparameter search, one fleet and one map. The 5.3% gap is evidence about where the headroom is
  not, not a proof that no learner can close it.
- **The forecaster grading is narrow** (§5.22): 24 seeds, one disturbance rate, highway cells only.
  The metrics are stable at 4.8M predictions per arm, but they characterise this hazard process rather
  than disturbance forecasting in general.
- **Charging foresight and the horizon sweep are stress-day results** (§5.25, §5.26): both were run in
  the regime where charging binds, and neither has been re-checked on ordinary wave or stream days.
  Neither has shipped for that reason.
- **The inner-loop planner is not optimal on unstructured maps** (§5.20): 100% of MovingAI scenarios
  are solved and paths are 100% optimal on the warehouse and empty maps, but on randomly cluttered
  maps 19 of 200 paths are 2–4 steps long (mean +0.22). Aisle topology leaves the heuristic no room to
  mis-order equal-cost frontiers, so this does not touch our domain — but the planner should not be
  described as optimal in general.
- **Liveness rules are env-level opt-ins** (12 flags, runner-set); the champion is a configuration, not
  a default. All frozen-AGV counts reported are sums over episodes, never simultaneous counts.
- **The residual worst case is bounded, not zero**: one 92-step rendezvous wait per 144 episodes
  under champion v4 (83 under v3), mechanism class documented; the pickers_free oracle caps all
  remaining picker-side gains at +3.74% off-peak / +1.44% at peak.
- **The v2/v3/v4 family trades tail vs throughput at fixed on-time value** (pairwise |t| ≤ 1.23);
  delivery or max-wait counts quoted from any one version must name the version.
- **The trajectory simulator ignores turning costs and swap conflicts** — a uniform optimism applied
  to both sides of each comparison, not a bias toward either.

## 8. Conclusion + Future Work
Against the simulator's own dispatcher the decision layer is worth **+21.1%** on wave days and
**+47.5%** on live-stream days with a clean floor, and **+31.6%** / **+60.4%** once disturbances are
active (t = 9.1–12.5, 144 paired days per cell, 2,304 runs) — while paying an energy cost the
baselines skip. The liveness layer is worth a further **+6.8%** on the dense map while taking
permanent deadlock from **51% of episodes to zero**, and the safety claims are measured rather than
assumed: **zero strandings** in 2,300+ runs, **zero** vertex and swap collisions over ~96,000
robot-steps per controller, and 100% of 1,800 MovingAI MAPF scenarios solved.

The remaining value is not in better prediction. Six independent channels were fed the true future and
none paid; the sixth was the sharpest, because a *scrambled* forecast beat the real one and exposed the
mechanism as parameter movement rather than information (§5.25). Nor is it in a learned decision
layer: given identical candidates and identical features, a policy-gradient dispatcher beat the
vendored heuristic, tied the urgency rule, and lost to the hand-built rules by 5.3% (§5.21). Nor is it
in better eyes — the belief map already sits at 99.8% of the physical sensing ceiling and, graded as a
forecaster, removes 35% of a base-rate reference's error against the 1% its predecessor removed
(§5.22). What is left is **queue structure**, **errand assignment**, and — newly — **how far the tuner
imagines** (§5.26).

The reference champion is **`m3mpc`**: on-time value 784.5 with full battery physics against 784.0
with free energy, frozen 0/144 and stranded 0/144 on wave days. The bar for any new idea remains: beat
it on on-time value without breaking 0/144.

**M1–M5 are closed** (§5.15–§5.26): ladders and weights on both regimes; the disturbance-information
phase boundary mapped and pinned at both ends; battery measured *free* under planned charging;
the pace family closed by showing the deadline rule never consults a clock; and the full external
evaluation suite — head-to-head benchmarks with and without disturbances, safety metrics, MAPF
validation, a learned baseline, forecaster metrics, and a pre-registered keep/cut ledger.

**Next steps, in priority order:**
1. ~~Stranded = 0~~ **CLOSED** (picker action-layer charge enforcement; frozen 0/144 AND
   stranded 0/144 at value parity with the no-battery ceiling).
2. ~~M2 coda~~ **CLOSED** (§5.18: boundary mapped and pinned at both ends; the reset rule lifts honest
   sensing to ~83% of clairvoyant VoPI and 99.8% of the sensing ceiling).
3. ~~M5 external evaluation~~ **CLOSED** (§5.20–§5.24).
4. **Adopt the 200-step tuner horizon** (§5.26) — proven on stress days at equal compute; needs an
   ordinary-day re-check before it becomes the default.
5. **Give the floor spare storage slots** (§7) — the diagnosed cause of the one remaining liveness
   defect; a world-constant change, so it needs a deliberate decision and a full re-verification.
6. **Threshold oscillation as a tuner move** (§5.25) — measured at ~+7% and a third of the strandings
   on stress days, not built.
7. **Assemble the paper and the figure set**; then the open-source release.
8. **Port the swap family to stock TA-RWARE** — external validity for §5.13's dispatch rules.
   *Scoped but not built.* The port must be an adapter that applies our dispatch rules on top of the
   unmodified vendored package, never a patch to it: the whole evidential value of the head-to-head
   rests on the baseline being untouched. That is a multi-hour build whose failure mode is a subtly
   different environment that silently invalidates the comparison, so it wants a fresh session and a
   parity check against our fork before it is trusted.
9. **Idle-picker yield** — deliberately deferred, and the reason is worth recording. Every liveness
   rule that shipped (§5.13) works by *gating a move an agent already requested*; a yield rule is the
   first that must *synthesise* a move for an agent that requested nothing, which means writing into
   the referee's path and action state rather than filtering it. That is a materially riskier class
   of change, and the prize is small: the residual it targets is one 92-step rendezvous wait per 144
   episodes. By this project's own rule — at 1-in-144 rarity a fix must beat the cost of re-verifying
   — it does not currently clear the bar to build.
(The former fleet-ratio-grid item is absorbed: the §5.17 campaign covered 30 size×fleet cells and
answered the ratio question for both the weights — robust — and the thresholds — context-bound.)

---

## 9. References

**Verified.**
1. Ha, D. & Schmidhuber, J. (2018). *World Models.* arXiv:1803.10122.
2. Hafner, D., Pasukonis, J., Ba, J. & Lillicrap, T. (2023). *Mastering Diverse Domains through World
   Models (DreamerV3).* arXiv:2301.04104.
3. Schrittwieser, J. et al. (2020). *Mastering Atari, Go, Chess and Shogi by Planning with a Learned
   Model.* Nature 588, 604–609.
4. Silver, D. et al. (2018). *A general reinforcement learning algorithm that masters chess, shogi and
   Go through self-play.* Science 362(6419), 1140–1144.
5. Bertsekas, D. P. (2020). *Rollout, Policy Iteration, and Distributed Reinforcement Learning.*
   Athena Scientific. — the rollout guarantee the sequencer inherits.
6. Powell, W. B. (2011). *Approximate Dynamic Programming: Solving the Curses of Dimensionality.*
   2nd ed., Wiley.
7. Li, J., Tinka, A., Kiesel, S., Durham, J. W., Kumar, T. K. S. & Koenig, S. (2021). *Lifelong
   Multi-Agent Path Finding in Large-Scale Warehouses (RHCR).* AAAI.
8. Okumura, K., Machida, M., Défago, X. & Tamura, Y. (2019). *Priority Inheritance with Backtracking
   for Iterative Multi-agent Path Finding (PIBT).* IJCAI.
9. Hönig, W., Kiesel, S., Tinka, A., Durham, J. W. & Ayanian, N. (2019). *Persistent and Robust
   Execution of MAPF Schedules in Warehouses.* IEEE RA-L 4(2).
10. Stern, R. et al. (2019). *Multi-Agent Pathfinding: Definitions, Variants, and Benchmarks.* SoCS.
    arXiv:1906.08291.
11. Sturtevant, N. *MovingAI MAPF benchmarks.* movingai.com/benchmarks/mapf.
12. Papoudakis, G., Christianos, F., Schäfer, L. & Albrecht, S. V. (2021). *Benchmarking Multi-Agent
    Deep Reinforcement Learning Algorithms in Cooperative Tasks (RWARE).* arXiv:2006.07869.
13. *Task-Assignment Multi-Robot Warehouse (TA-RWARE).* arXiv:2212.11498. — the substrate we fork.
14. Yen, J. Y. (1971). *Finding the K Shortest Loopless Paths in a Network.* Management Science 17(11).
15. Brier, G. W. (1950). *Verification of forecasts expressed in terms of probability.* Monthly Weather
    Review 78(1), 1–3. — the score of §5.22.
16. Murphy, A. H. (1973). *A new vector partition of the probability score.* Journal of Applied
    Meteorology 12(4), 595–600. — reliability/resolution, the decomposition behind the skill number.
17. Howard, R. A. (1966). *Information Value Theory.* IEEE Transactions on Systems Science and
    Cybernetics 2(1), 22–26. — the VoPI bound we use as a build gate.
18. Williams, R. J. (1992). *Simple statistical gradient-following algorithms for connectionist
    reinforcement learning (REINFORCE).* Machine Learning 8. — the learner of §5.21.
19. Auer, P., Cesa-Bianchi, N. & Fischer, P. (2002). *Finite-time Analysis of the Multiarmed Bandit
    Problem (UCB1).* Machine Learning 47. — the tuner's move selector.
20. Ke, G. et al. (2017). *LightGBM: A Highly Efficient Gradient Boosting Decision Tree.* NeurIPS. —
    the pace head cut in §5.19.
21. Hawkes, A. G. (1971). *Spectra of some self-exciting and mutually exciting point processes.*
    Biometrika 58(1). — the burstiness of §3.6.
22. Akiba, T., Sano, S., Yanase, T., Ohta, T. & Koyama, M. (2019). *Optuna: A Next-generation
    Hyperparameter Optimization Framework.* KDD.
23. Instacart (2017). *The Instacart Online Grocery Shopping Dataset.* — hour-of-day × department
    shares, the drift calibration of §5.18.

**Carried from the project's 2026-07-16 literature pass — identifiers to be re-verified before
submission.** These support the gap analysis in §2 and no result depends on them.
24. Dehghan, M., Cevik, M. & Bodur, M. (2023). *Dynamic AGV Task Allocation in Intelligent Warehouses.*
    arXiv:2312.16026. — closest decision-layer prior work.
25. *It Takes Two to Tango (WareRover).* arXiv:2602.13999. — order scheduling coupled with MAPF under
    realistic e-commerce demand.
26. *LSMART.* arXiv:2602.15721.
27. *Bursty Arrivals, Smooth Sojourns.* arXiv:2607.04866. — heavy-tailed real warehouse inter-arrivals.
28. *League of Robot Runners / LMAPF task-sampling realism.* arXiv:2404.16162.
29. RTAW (ICRA'23), DC-MRTA (IROS'22), MRTAgent (AAMAS'25) — learned task allocation under soft delay
    penalties.
