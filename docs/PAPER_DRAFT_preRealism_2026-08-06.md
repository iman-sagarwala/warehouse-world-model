# Paper Draft — A Lightweight Interpretable World Model for Deadline-and-Value Multi-Robot Warehousing

> Working outline. Each section holds the material to expand into prose. Act-I (congestion) numbers
> are from the 2026-07-15/16 experiments; Act-II (sequencer / pace) numbers from 2026-07-19..23
> (see docs/NOTES.md). Confirmed headline = the hi-fi rollout sequencer at +12.8 on-time value
> (+3.3%) over the congestion champion, 120 fresh day-list seeds. Re-run the older no-disturbance
> bake-offs at 100+ seeds before submission.

---

## Working title (options)
- "Honest About the Present, Silent About the Future: A Two-Part World Model for Deadline-and-Value Warehousing"
- "Avoid, Don't Predict; Re-Plan, Don't Commit: An Interpretable Decision-Layer World Model for Multi-Robot Warehouses"
- "Steer, Don't Forecast: Why Spatial Congestion + Receding-Horizon Rollout Beat Learned Delay Prediction"

## Abstract (to write last)
One-paragraph version of the thesis: in a multi-robot warehouse with per-task deadlines and values,
the objective is **on-time value**, and the hard question is "will this task finish before its
deadline?" We present a lightweight, **interpretable two-part decision-layer world model**. (i) A
**spatial congestion field** — a per-cell occupancy forecast rolled forward from known robot
futures — drives **route** choice: it beats every attempt to *predict* per-task delay (learned
delay head, congestion-feature head, rules-based delay, soft probability), because it is used to
**avoid** congestion, not estimate it. (ii) A **receding-horizon rollout sequencer** drives **task**
choice: for each candidate first move it simulates the whole fleet forward under the base policy and
commits only the first move, re-planning every decision. Its value comes not from the plan (obeying
the whole imagined schedule *loses* 11.3 value) but from constant re-planning anchored to two honest
corrections — a live **pace bias** (measured, not assumed, completion delay) and a per-order
**cashier** matching the real payout. We further use a **value-of-perfect-information** discipline —
feeding a candidate predictor the true future *before* building it — to kill three dead ends
(next-task prediction, per-task delay heads) at the cost of one experiment each, and to localize the
binding constraint on value to **picker rendezvous**, not congestion. We give the design, paired-seed
evaluations across a realistic non-homogeneous demand model, and a set of transferable control-design
principles the results support.

---

## 1. Introduction
- **Setting.** Fulfilment warehouses run fleets of AGVs + human/robot pickers under a continuous
  stream of orders that carry **deadlines** (SLA) and **values** (priority). Under overload you can't
  do everything on time; the objective is **on-time value**, not raw throughput.
- **Gap.** Classic MAPF/lifelong-MAPF optimizes throughput/makespan; task-assignment heuristics
  optimize distance or deadline. Few price *congestion* into *deadline-and-value* decisions, and
  learned "how late will this be?" heads are attractive but (we show) mis-targeted.
- **Contribution.**
  1. A **congestion forecast world model**: a one-pass rollout of robot futures into a per-cell
     occupancy field, used for route selection + rerouting (Act I).
  2. A per-robot **funnel planner** (Part A) that separates the *task* decision (value + a hard
     deadline tier) from the *route* decision (congestion), and drives committed routes with soft
     adherence.
  3. A **receding-horizon rollout sequencer** (Act II): the funnel's ranked shortlist becomes the
     candidate set for a Bertsekas-style rollout — simulate the whole fleet forward under the base
     policy per candidate first move, commit only the first move, re-plan every decision. Two honest
     corrections (a **live pace bias** and a per-order **cashier**) turn a naive rollout worth ≈0 into
     a **+12.8 on-time value (+3.3%)** gain (120 fresh day-list seeds).
  4. An empirical case that **the plan is worth ~nothing and the re-planning is worth ~everything**:
     obeying the whole imagined schedule open-loop *loses* 11.3 value vs re-planning every decision;
     plans drift off reality within ~2 decisions.
  5. An empirical case that **delay is the wrong thing to learn**: four delay-estimation approaches
     fail to beat a hard cutoff; a value-of-perfect-information test shows even *true* per-task delay
     is worth ≈+0.4. The one learnable temporal quantity is the **aggregate pace** (a state-conditional
     delay bias), which forecasts ~20% better than a lagging EMA but — on day-list, where demand is
     known — is value-neutral (its diurnal signal targets the streaming regime).
  6. A **binding-constraint analysis**: a value-loss autopsy + AGV:picker ratio sweep localize the
     lost on-time value to **picker rendezvous** (≈75% of the addressable cliff loss), not congestion;
     adding pickers is ~10× the value lever of adding AGVs.
  7. A set of transferable **control-design principles** (Sec. 6).

## 2. Related Work / Literature Review (citations from the 2026-07-16 research pass)
- **The gap (verified across simulators).** Warehouse sims split into two camps that both miss the
  deadline-and-value decision layer: (i) physics/perception (NVIDIA Isaac Sim — warehouse assets, but
  scheduling is a bolt-on via cuOpt, not native) and (ii) grid/algorithmic (RWARE, TA-RWARE, MAPF /
  Lifelong-MAPF, **League of Robot Runners** [Harabor/Koenig, ICAPS'24], **LSMART** [arXiv 2602.15721])
  that all optimize **pure throughput** (pick-rate / task-count). Demand is uniform-resampled (RWARE/
  TA-RWARE) or **endogenous 1:1 replacement** (LoRR/LMAPF — a task appears only when one finishes). None
  jointly models deadlines + values + battery + disturbances + realistic exogenous demand, and none
  optimizes on-time VALUE. Even learned decision-layer RL (RTAW ICRA'23, DC-MRTA IROS'22, **MRTAgent**
  AAMAS'25) uses SOFT delay penalties — no hard deadlines / per-task values. LMAPF organizers themselves
  flag uniform task sampling as unrealistic vs imbalanced/spatially-correlated real demand [arXiv 2404.16162].
- **Closest new work — WareRover** ("It Takes Two to Tango," arXiv 2602.13999, Feb 2026): a holistic
  simulator coupling order-scheduling + MAPF with realistic e-commerce demand (wave orders, hotspot SKUs,
  bursty promotions). Differs from us: a simulator/coupling effort, not on-time-VALUE + disturbances +
  interpretable spatial congestion. Mild competitor / must-cite.
- **Dehghan, Cevik & Bodur (2023), "Dynamic AGV Task Allocation"** (arXiv:2312.16026) — closest
  decision-layer method: MDP + Neural ADP, per-task deadlines, stochastic arrival (Beta(5,2) volume +
  normalized Poisson spatial), battery, human-robot. Gaps we fill: order-COUNT not on-time-VALUE; no
  disturbances; congestion = worker capacity only, not SPATIAL. They LEARN value-to-go (anticipation) —
  the legitimate ML lever — NOT delay (which we show is irreducible).
- **MAPF / Lifelong MAPF**: prioritized planning, conflict-based search, ADG/execution under delay;
  our congestion forecast = a soft, aggregate cousin of prioritized planning + reservation tables.
- **Deadlock / livelock resolution (execution layer).** The standard resolution is priority-based
  victim selection — abort or yield the lowest-priority participant in the cycle. **PIBT** [Okumura et
  al., IJCAI'19, https://www.ijcai.org/proceedings/2019/0076.pdf] does this incrementally: agents
  commit only their NEXT cell each timestep and negotiate locally with neighbours — destination-aware
  but *path-blind* — and it is deadlock-free **on bi-connected graphs**. That guarantee explicitly
  fails on dead-ends and tree-shaped paths, which is precisely the shelf-aisle/rack-rendezvous
  geometry of a picker-AGV warehouse. **Priority Inheritance with Temporary Priority (PIWTP)**
  [https://arxiv.org/pdf/2205.12504] extends the guarantee to Multi-Agent Pickup and Delivery by
  letting a blocker temporarily INHERIT the blocked agent's priority, which is what prevents static
  priority from degenerating into starvation of the lowest-value robot. **Standby-based deadlock
  avoidance** [https://arxiv.org/pdf/2201.06014] targets the dead-end/rack case directly.
  RELEVANCE TO US: our value/deadline tier is exactly the priority function these schemes consume, so
  the natural design is PIBT-style local negotiation (mechanism) ordered by on-time value (priority)
  with inheritance to bound yielding. STATUS: not yet built — see §7, where we report that the stalls
  we measured were a single-robot recovery livelock, NOT multi-robot deadlock, so we have as yet no
  measured instance this machinery would resolve.
- **Rollout / approximate dynamic programming / MPC (the sequencer's lineage).** Our Act-II sequencer
  is a **policy rollout** (Bertsekas): estimate each first move by simulating the base policy forward,
  commit the best, and inherit the classical guarantee that rollout is no worse than its base policy.
  The receding-horizon commit-one-and-re-plan loop is **model-predictive control**; the
  simulate-forward-under-a-base-policy value estimate is **approximate DP / rollout** (Powell). The
  same select-by-imagined-continuation + commit-one + re-search skeleton underlies **MCTS / AlphaZero**
  (our version is the single-trajectory ancestor, no tree, no learned model) and receding-horizon
  lifelong-MAPF (**RHCR**). Novelty is not the skeleton — it is that the *paying* parts are the
  fidelity corrections (measured pace, per-order cashier) that align the cheap sketch's clock and
  cashier with reality, found by an in-house oracle→autopsy→ablate loop rather than copied.
- **Task assignment in MRS / warehouse (RWARE / TA-RWARE)**: EDF, value/priority heuristics,
  auction/market methods; we build on a TA-RWARE fork (throughput objective — arXiv 2212.11498).
- **Demand realism (empirical)**: "Bursty Arrivals, Smooth Sojourns" (arXiv 2607.04866) — real-warehouse
  inter-arrivals are heavy-tailed / bursty, statistically incompatible with homogeneous Poisson →
  motivates a Hawkes/bursty arrival process over plain Poisson.
- **Congestion / flow-aware routing**: reservation tables, BPR-style latency, potential/field methods
  (our map is a potential field you steer around).
- **Learned world models & predictive heads**: model-based RL, learned delay/ETA prediction; our
  negative result (delay is chaotic/unlearnable per-task) is the contrast.
- **Calibrated prediction / value × P(success)**: why a hard threshold beats a soft probability here.
- **Dehghan, Cevik & Bodur (2023), "Dynamic AGV Task Allocation in Intelligent Warehouses"
  (arXiv:2312.16026)** — closest decision-layer prior work: MDP + Neural ADP for non-myopic AGV task
  allocation with per-task DEADLINES, stochastic ORDER ARRIVAL, battery/charging, and human–robot
  collaboration. Demand model = left-skewed Beta(α=5,β=2) order volume/epoch + normalized Poisson(λ=1)
  spatial demand (9×20 grid, 24h). CONTRASTS / gaps we fill: (1) they optimize order-COUNT (uniform
  reward), we optimize on-time VALUE; (2) no disturbances/failures — we add them; (3) congestion is only
  worker CAPACITY (2–3/worker), not SPATIAL corridor congestion — our core. LEARNING NUANCE: they learn
  the VALUE-TO-GO (NeurADP) for anticipation — the legitimate ML lever here — NOT delay prediction
  (which we show is irreducible). We adopt their demand model as our task-order workflow.

## 3. Problem Setup
- **Simulator.** TA-RWARE fork (`wwm_sim`), grid warehouse (35×22, 240 shelves), N AGVs + M pickers
  (AGV fetches a shelf, a picker must rendezvous at the shelf cell to load, deliver to docks, return
  the shelf to an empty slot before free again). Env drives its own A* + resolves conflicts
  (reroute-or-wait); exposes per-step reroute events and deliveries. Default fleet 8 AGV / 4 picker.
- **Tasks & batching.** Each shelf may carry **several orders** (SKU model); one trip fulfils every
  order pending on that shelf, and each order is scored against **its own** deadline (a late trip for
  order 1 still banks orders 2–5). Each order has a **value** and a **deadline** (+ optional SLA
  hardness g).
- **Demand model (replaces the old always-full queue).** A realistic non-homogeneous arrival process:
  NHPP with a **diurnal** rate (sinusoid, amp 0.8) + **Hawkes** self-excitation (order bursts) +
  **Zipf** SKU popularity with velocity slotting + a rush/standard mixture (1-in-5 rush orders arrive
  tight but pay more). Two **regimes** from the same generator: **day-list** (the whole day's orders
  are *visible* at t=0 — a batch/wave release; due-times still staggered by the diurnal draw) and
  **stream** (orders arrive over the day; the realistic online case). A third "uniform always-full"
  regime was **retired** as unrealistic. Day-list = the perfect-demand-foresight bound: any demand
  predictor's value is bounded by day-list − stream.
- **Objective.** On-time value = Σ values of orders delivered at/before their deadline (late = 0).
- **Evaluation protocol.** *Paired seeds*: seed N = identical world for every policy; compare on the
  same seeds; average over many. Two instruments — a paired **t-test** (mean effect) and a **sign
  test** on decided seeds (robust to heavy tails). **120 seeds** for any effect < +8 (30-seed effects
  flipped sign more than once). Every experiment carries a **sanity arm** (a control that must be
  bit-identical to a known policy; if it differs, the plumbing is broken and the numbers are void).

## 4. Method
### 4.1 The rollout / world model (known rules)
- Deterministic forward simulation under **position + rules** (travel, load, rendezvous, battery),
  **delay ≡ 0** (delay is not in the rulebook). Gives arrival/finish/margin per candidate plan.
### 4.2 Part A funnel (per-robot task→route→commit)
1. **Cheap screen** (traffic-blind prefilter): `value − 0.15·Manhattan`, keep top ~15.
2. **Yen's k-shortest routes** on the real map.
3. **Route choice = congestion** (Sec 4.3): pick `argmin(length + λ·congestion)`.
4. **Task score = value + a HARD deadline tier**: makeable (`now+finish ≤ deadline`) → `1000+value`;
   doomed → `value·g^lateness`. Plus a rendezvous **sync** term.
5. Rank tasks, **commit robot→task→route**, drive with **soft adherence**.
### 4.3 The congestion forecast (the core)
- Per-cell occupancy grid rebuilt each step by rolling futures forward:
  (1) busy robots' **known** remaining paths (full weight);
  (2) about-to-finish robots' **predicted** next task (same cheap-screen rule) + route (lighter);
  (3) **prioritized** stamping — robots assigned one-at-a-time, each dodging those already placed.
- Used for (a) route ranking, (b) rerouting (env `find_path` adds the grid to cell costs), (c) soft
  route **adherence** (off-route cells cost more, so paths hug the committed route but detour around
  real blockers). It models SPACE (where) reliably; it does not model TIME (how-late).

### 4.4 The rollout sequencer (temporal world model, Act II) — the core of the second contribution
The funnel (4.2) is greedy: each robot takes the top-ranked task for *itself*. The sequencer replaces
the final `argmax` with a **Bertsekas-style rollout over the base policy**:
- **Candidate set.** The funnel's ranked shortlist of the top **K = 15** tasks (a policy-network-like
  prefilter — a Manhattan/value screen that makes the expensive step affordable; widening K past ~12
  plateaus, below ~12 it cliffs).
- **One imagined day per candidate.** Pin the candidate as this robot's first move; fast-forward the
  **whole fleet**: whenever any robot frees up *inside the imagination* it picks its next task by the
  **same funnel rules** from the queue *as it stands at that imagined moment* (tasks get consumed,
  deadlines tick, pickers get busy). Bank each order delivered before its deadline. Read the day's
  total. The imagined robots use the cheap base rules, **not** a nested sequencer (no imagination
  inside imagination). ≈4 ms/day; deterministic (no sampling) → same snapshot, same sketch.
- **Commit the first move only** (receding horizon); throw the imagined rest away; re-imagine from
  scratch at the next decision.
- **Two honest corrections make the cheap sketch pay** (turning naive rollout ≈0 into +3.3%):
  - **The pace bias (the engine, ≈+6.9 of +8 in ablation).** The empty-world completion math is
    optimistic; real completions run a state-dependent amount slower. The sim clock adds a **live
    measured** delay bias (`_delay_ema`, an EMA of realized minus predicted completion) to every
    imagined finish, so the imagination plans in *today's* actual time, not textbook time.
  - **The per-order cashier.** A batched shelf pays **per order** in the imagination, exactly as
    reality does — before this fix a slightly-late batch was written off whole, and the planner
    postponed goldmine shelves until they died (a family of disaster days; fixing it halved the worst
    craters).
- **Why it works despite being wrong in the details.** The sketch mis-estimates the day's total by
  ~10 points, yet the **ranking** of first moves survives (all K sketches share the same optimistic
  bias — a "scale that reads 5 lb heavy still says which box is heavier"). The receding horizon means
  only the one-step-ahead ranking must be right, and it is. Relation to AlphaZero/MuZero: same
  select-by-imagined-continuation + commit-one + re-search skeleton; ours is a single straight-line
  rollout (the classical ancestor of MCTS) with handwritten dynamics + one measured constant, not a
  learned model or a branching tree (Sec 5.8, 6).

## 5. Experiments
### 5.1 Main result (62 paired seeds)
| policy | on-time value (mean) | reroutes (mean) | reroute max | storms (>150) |
|---|--:|--:|--:|--:|
| **parta_congestion (ours)** | **199.8** | **74.5** | **582** | 3 |
| rush (scalar baseline) | 197.4 | 92.4 | 923 | 5 |
| parta + variance delay head | 194.9 | 134.6 | 1311 | 6 |
| rush + congestion route | 194.8 | 93.5 | 1311 | 3 |
| parta + baseline delay head | 193.8 | 132.0 | 1311 | 5 |
- Ours wins value AND robustness; the congestion map eliminates gridlock storms other policies suffer.
### 5.2 Delay prediction is a dead end (four ablations)
- Learned delay head: +33% MAE vs predict-0 but only +9% vs a constant, ~0 on the tail (jams).
- Variance head (+9 live congestion features): +1% over baseline; still worse than a constant on tail.
- Rules-based congestion-finish (add congestion delay to the deadline check): −2.2 value, 4W/10L/16T.
- Soft P(on-time) (smooth cutoff, congestion-widened): −10.3 value, 5W/25L over 30 seeds.
### 5.3 Sharp beats soft (route side, 30 seeds)
- Probabilistic forecast (spread each prediction over top-3): −5.3 value; median tied (200 vs 196) but
  **storms the chaotic seeds** (max 893 vs 94) the concentrated forecast prevents. Cost = the crash.
### 5.4 Component analyses
- **Adherence needs the forecast**: adherence alone (RushYen / rush-congestion) locks robots onto the
  congested shortest lanes → more reroutes, occasional storms; only pays off once the forecast spreads
  routes first. Adherence ↓ stucks (persistent lane), but ↑ reroutes without spreading.
- **Rush's window vs a per-task funnel**: Rush's global window is a strong scalar cutoff but a *worse*
  cutoff inside a funnel that already has per-task finish (`rush_cong_full` worst on value).

### 5.5 Route vs. deadline: two redundant ways to use congestion (30 seeds, no disturbances)
Congestion can drive the **route** (champion) *or* the **deadline** (`dl_cong`: shortest routes,
congestion inflates the finish → makeable/doomed; no route steering, no score term). Both beat plain
Part A and **tie on value** (dl_cong 199.7 vs champion 201.4, 15W/14L). But they are **alternatives,
not complements**:
- Combining them (add the congestion-deadline term *on top of* route-steering) is **neutral** — once
  routes already avoid congestion, the route-congestion is low, so the deadline term has nothing to
  flag and goes **inert**. Whichever mechanism dodges congestion *first* neutralizes the other
  (explains the double-count).
- **Route-steering is more storm-robust**: it *physically spreads* robots (0 storms, max 94);
  deadline-*deterrence* only discourages taking jammed tasks without spreading the ones it takes
  (3 storms, max 789). Task-level deterrence is a weaker form of congestion-avoidance than routing.

### 5.6 Robustness to disturbances (exogenous random blockages, 100 seeds)
We add unpredictable temporary blockages (1–3 highway cells, 20–60 steps, paired schedule) that force
reactive rerouting. 100-seed comparison **with disturbances**:
| policy | on-time value (mean / median) | reroutes (mean) | storms (>150) |
|---|--:|--:|--:|
| **champion (route-steer)** | **194.6 / 192** | **64.6** | **2** |
| parta_head (delay head, no congestion) | 192.7 / 197 | 122.5 | 10 |
| dl_cong (congestion→deadline only) | 191.4 / 194 | 123.4 | 11 |
- **The champion wins on value *and* robustness under disturbances.** A 30-seed run had `parta_head`
  "ahead"; at 100 seeds it flips — parta_head wins *more* head-to-head seeds (higher median) but its
  **10 catastrophic storms** (max 1311) drag its mean below the champion. *Methodology note:* the
  reroute metric is heavy-tailed → 30 seeds is misleading; this comparison class needs **100 seeds**.
- `dl_cong` is *most* disturbance-fragile: it pipes congestion straight into a **hard** makeable/doomed
  cut, so disturbance-inflated congestion **over-sheds doable tasks** — *and* it still storms (no
  physical spreading). Worst of both.
- **Disturbance-aware adherence** (drop the committed route when a disturbance blocks it → shortest
  detour, don't fight to rejoin): a **strict Pareto improvement** — never worse, occasional large save,
  identical robustness.
- **Disturbances are observed, not predicted.** A **Beta rumor map** (per-cell α/β; a *sighting* near a
  robot raises α, a *clean traversal* raises β, time decay) accumulates a calibrated belief of *where*
  disturbances have been (precision@20 = 20/20 in a demo), for a later support tier — it never forecasts
  them. Feeding disturbances as a *predictive feature* would worsen decisions (current ones are already
  in the route length; future ones are pure noise) — a direct instance of Principle 2.

### 5.7 The rollout sequencer: confirmation and fidelity decomposition (day-list)
- **Headline (120 fresh day-list seeds).** The hi-fi sequencer at K=15 (`sqwide`) = **+12.8 on-time
  value (+3.3%)** over the congestion champion; sequencer-vs-champion sign test p ≪ 0.001. The
  hindsight-oracle ceiling above the stack collapsed to ~1.5% (only 2–4 of 120 shuffles beat it).
- **Fidelity ablation (what makes the sketch pay).** Starting from a naive rollout (empty-world clock,
  all-or-nothing cashier) worth ≈+1 over greedy, the components add: **pace bias +6.9** (the engine),
  **per-order cashier** (fixes a crater family; general +7.97→+9.47), pickers-as-resources +0.13,
  freed-position geography +0.30. A warm-start prior and a decayed-credit term were tested and
  **dropped** (the latter let the imagination buy value the real cashier never pays).
- **Branch width.** K swept 8–25: cliff below ~12, plateau 12–25; K=15 adopted. Removing the Manhattan
  prescreen and simulating *every* candidate did not beat K=15.

### 5.8 Plan vs. re-planning: the value is in the receding horizon (30 seeds)
- **Open-loop isolation.** Extract the sequencer's full imagined per-robot schedule and **execute it
  blind** (no re-scoring) vs re-planning every decision: re-planning wins **+11.3** (t=3.75, sign
  p=0.004). Plans drift off reality within ~2 decisions. Lookahead executed *without* re-decision is
  ≈+3.6 (n.s.). Interpretation: **the plan is worth ~nothing; the re-planning is worth ~everything**
  — the imagination is a flashlight (choose the next step), not a map (sketch once, walk blind).

### 5.9 Value-of-perfect-information: killing predictors before building them
A recurring method: hand a candidate predictor the *true* future and measure the ceiling; a null
kills the whole direction for one experiment.
- **Next-task / congestion layer 2.** Feeding the map the literally-correct next task of every other
  robot helped **≈0** — other robots re-plan around you, so their forecast is redundant.
- **Per-task delay head.** True per-task delay was worth **≈+0.4**. Per-task delay is chaotic; even
  perfect knowledge is nearly valueless (corroborates 5.2).
- **Principle.** Avoidance points backwards (later planners know more); predicting other agents' or
  tasks' futures is dominated by re-planning against the observed present.

### 5.10 The binding constraint on value is picker rendezvous, not congestion
- **Value-loss autopsy (per order, 10 day-list seeds).** Of ~9% potential value lost, **0% is doomed
  from the start** (everything is reachable at t=0), and the addressable "missed at the deadline cliff"
  slice decomposes to **≈75% picker wait, ≈25% traffic block, ≈0% dock queue**. A steps-late autopsy
  agrees: mean +16 steps/task, of which picker wait ≈16.5, traffic ≈7.4, detour ≈+1 (straight-line
  geometry is nearly exact — the error is *waiting*, not *driving*).
- **AGV:picker ratio sweep (30 seeds/config, demand fixed).** Adding pickers 2→8 (fixed 8 AGV) lifts
  banked value **+50** (350→400); adding AGVs 6→10 (fixed 4 picker) lifts it **+5** — a picker is
  ~**10× the value lever** of an AGV. Picker-wait loss falls with picker supply (25→13) and is flat in
  AGV count; too-few pickers shifts the failure mode to outright starvation (never-served 52/day at
  8×2). Saturation ≈6 pickers per 8 AGV. Confirms picker availability as the binding constraint.

### 5.11 The pace model: the one learnable temporal quantity, and where it pays
- **Model.** A state-conditional replacement for the sequencer's flat-EMA pace bias, trained
  (LightGBM) on (fleet-state → realized delay) over 120 day-list seeds. Two variants: **picker**
  (contention only) and **combined** (picker + diurnal day-curve + traffic).
- **Offline.** Both beat the incumbent live EMA by ~20% MAE (combined 12.39 vs EMA 15.58); the
  combined model's top signal is the day-arc (`day_frac`+`sin_t` ≈41%) — anticipation the lagging EMA
  cannot do. (Notably a flat constant also beats the live EMA offline, 13.17 — the EMA's lag/noise
  makes it worse than a constant at forecasting.)
- **Online (30 paired day-list seeds).** Value is **unchanged**: combined +1.1 (n.s., sign p=1.0),
  picker −0.4. Expected: on day-list demand is known and the imagination already simulates against
  every explicit deadline, so a sharper *aggregate* bias (one scalar applied to all K futures) has
  almost no channel to change the first move — it moves the makeable/doomed threshold, not the ranking.
- **Interpretation & next.** The diurnal signal is *present but redundant* on day-list (deadlines are
  visible) and should be *predictive and unique* on the stream (arrivals are hidden). The causal
  quantity is **deadline clustering** around now (time is only a proxy); the clean factoring is:
  measure clustering directly where visible (day-list), **forecast** it from the demand model where
  not (stream), and feed it to the pace model either way. Comparable-not-worse on day-list is the
  green light to test the combined model on the stream, its intended home.

### 5.12 Server specialization: value-rate for pickers, value for AGVs (and why they differ)
Both robot types choose tasks by the same makeable/doomed tier. The natural idea is to rank the
makeable tier by **value per unit time** (value-rate) rather than raw value, so a robot stops taking
long detours for a marginally bigger prize. Applied to **AGVs** ("rate80": `1000 + κ·value/completion`)
it was the **largest single win we ever measured — +10.78 (+5.4%), t=4.36, confirmed on three
independent seed sets with no shrinkage** — but *only in the retired always-full "uniform" regime*.
Re-validated in the **deployment regimes** it flipped **negative** (stream −3.4; day-list negative
across all rate scales; plain value the unbeaten champion of 11 scorer variants). Applied to
**pickers** (`tier + value / Tp^α`, distance heavily weighted) it is a **confirmed win in the
deployment regime**: swept α, monotone rise to a **plateau at α≈5–8 worth +7.7–8.1 over the champion
(t≈4)**; even α=8 (≈ "nearest, ignore value") wins.

The **asymmetry is measured on both sides and has a clean cause — selection vs execution:**
- **AGVs *choose*** which orders get delivered from a **finite, shrinking queue** (~8–10 orders/day go
  unserved). When you cannot do everything, *which* you do matters → **value** must win; a rate that
  "grabs the quick stuff, there's always more" strands valuable orders (true in the infinite uniform
  buffet, false in a finite day — hence the regime flip).
- **Pickers *serve*** every AGV that is dispatched (a waiting AGV is never abandoned; it waits until
  loaded), so they face no selection, only **ordering**. Serving all of them, the order that banks the
  most on-time value is the **fastest** one (nearest-first) → **speed** wins; value is already fixed
  upstream by the AGV's choice, so re-optimizing it downstream is redundant *and* costs throughput.

**Deployment nuance (stacking + crater insurance).** On the champion base the picker value-rate is a
clean +6–8. On top of the *sequencer* its mean contribution collapses to +1.4 (n.s.) — **but that mean
hides a strong tail effect**: the sequencer and the pickers **fail on disjoint seeds** (worst-8 sets:
0/8 overlap), and adding value-rate pickers **rescues the sequencer's crater days by +29 on average**
(up to +96) while being flat on its good days (corr(sequencer-vs-champion, picker-rescue) = −0.33).
So the two levers are **orthogonal, not redundant**: sequencer = task choice, pickers = placement, and
craters are exactly the days task choice cannot dodge a physical picker shortage. Value-rate pickers
are therefore **variance/tail insurance** on the deployed stack, not a mean lift.

**The remaining picker gap is headcount, not assignment.** A 2×2 (stupid/value-rate × 8×4/8×8, demand
held identical) shows: doubling pickers to 1:1 buys **+9–10**; value-rate assignment buys **+1.4 at
2:1 and exactly 0 at 1:1** (−0.16, a 45/45 split). So smarter assignment is a *scarcity patch* that
vanishes once pickers are abundant; the +11 gap to the free-picker ceiling is ~+9 headcount + ~+2.5
crowding + the small (captured) assignment slice. Diagnostic on the residual long picker waits (α=5):
they are 85% *travel*, at *ordinary* shelf locations (dock-distance 17.4 vs 17.0 avg) — i.e. **bad
timing, not spatial isolation**: an ordinary AGV arrives when the pickers are momentarily all elsewhere.
Corollary: zone-based picker assignment and area-marginal / coverage-bonus spreading are predicted
flat-to-negative here, because our demand *concentrates* in a fixed high-value corner — the regime
where a global flocking pool beats fixed territories (spreading schemes fit *uniform/wandering* demand).

## 6. Discussion — principles the results support
1. **Compute from rules; don't learn the unlearnable.** Occupancy is computable from movement rules
   (a mini rollout); per-task delay is chaotic and has no learnable structure beyond its mean. A good
   world model *reports* that irreducibility (delay ≈ constant + noise) rather than fabricating it.
2. **Avoid, don't predict.** Use congestion to route *around* delay, not to *estimate* it. Avoidance
   needs only a relative ordering (robust to noise); prediction needs a precise number (destroyed by
   noise). Every attempt to feed a delay estimate into the deadline decision failed. *Corollary for
   truly exogenous hazards (disturbances):* they cannot be predicted at all → **observe and react**
   (reactive reroute + a Beta belief map), never forecast-and-feed. A disturbance *feature* would only
   add noise (current blockages are already in the route; future ones are unpredictable).
3. **Aggregate is predictable; individual is not.** Occupancy sums over many robots → a sharp, stable
   field (law of large numbers). One task's delay has nothing to average over → diffuse and
   undifferentiated. Robustness comes from aggregating over agents, not hedging any one.
4. **Sharp beats soft — most under stress.** A hard makeable/doomed *task* tier and a concentrated
   *route* forecast both beat their softened versions. Softening (soft P, spread forecast) is harmless
   on calm seeds but loses control on chaotic ones — it fails exactly when needed. The planner wants
   *decisive* signals on both axes: task-by-hard-deadline, route-by-sharp-congestion.
- Corollary (architecture): **route = congestion (the realistic time-rank); deadline = task (a
  hard tier).** Routes to a task are length-tied → share the deadline verdict → no per-route deadline
  check needed; congestion-ranking is the only realistic route time-ordering and helps the deadline
  for free.
5. **Re-plan, don't commit; the plan is worth ~nothing, the re-planning is worth ~everything.** In a
   stochastic (or merely detail-chaotic) fleet, an imagined plan drifts off reality within ~2
   decisions (open-loop −11.3). A fast, deliberately-inaccurate rollout re-run at every decision beats
   both greedy (no lookahead) and a committed optimal-looking plan. Only the one-step-ahead *ranking*
   must be right, and shared bias makes it right even when the absolute numbers are wrong.
6. **Honest present ≫ guessed future.** Every payoff came from replacing an *assumption* with a
   *measurement* of the present (the live pace bias; the per-order cashier; observed disturbances via
   the Beta map). Every null/failure came from a *guess about the future* (next-task prediction,
   per-task delay, invented stream arrivals, the whole imagined plan). Value-of-perfect-information is
   the cheap gate: if the true future is worth ≈0, no predictor of it can help — kill the branch.
7. **Localize the binding constraint before optimizing.** A value-loss autopsy (per-order,
   cause-attributed) + a structural sweep (AGV:picker ratio) showed the lost value is picker
   rendezvous, not congestion — redirecting the learned component (pace model) toward picker/deadline
   state and identifying a hardware lever (ratio) no controller change can reach. Optimize what the
   autopsy indicts, not what is easiest to model.
8. **Specialize the objective to the agent's job: choosers rank by value, servers rank by speed.** An
   agent that *selects* work from a queue it cannot finish must rank by **value** (skip the cheap, keep
   the valuable); an agent that *executes* a stream of already-selected work it will finish must rank by
   **speed** (serve them all, fastest-first, banking the most before deadlines). The *same* value-rate
   idea therefore *wins* for the server (pickers, +7.7) and *loses* for the chooser (AGVs, negative in
   the deployment regime) — measured on both sides. Re-optimizing an upstream decision downstream is
   redundant *and* forfeits the dimension the downstream agent actually controls. Corollary
   (regime-boundedness): "grab the quick stuff, there's always more" is only true in an infinite buffer;
   the same scorer that won +10.78 in the retired always-full regime went negative in the finite
   deployment regimes — **validate in the regime you deploy in.**
9. **Some gaps are structural, not algorithmic — a decomposition tells you which.** Doubling pickers
   buys +9–10; the best assignment rule buys +1.4 and vanishes at 1:1. When the ratio sweep shows the
   lever is headcount, no scorer/coordination scheme can close the gap — and the residual-wait
   diagnostic (bad timing, not spatial isolation) confirms it is a resource-count limit, not a
   placement one. Know which before building a coordination layer.

## 7. Limitations
- Single map/fleet size evaluated so far; the forecast's *normalized* features are designed to
  generalize but this is untested at other scales.
- **Act-II results (sequencer, pace, ratio, autopsy) are day-list**; the streaming regime — where the
  pace model's diurnal signal is meant to pay and where nothing has yet beaten the plain champion — is
  the main open front. The stream ceiling (best-of-N hindsight oracle) is unmeasured.
- The rollout is a **single straight-line** sketch per candidate (no branching, no sampled futures);
  a sampled-futures rollout for the stochastic stream is future work, gated on a perfect-demand-
  foresight VoPI test first (Principle 6).
- Pace model uses **time as a proxy for deadline clustering**; a direct deadline-density feature
  (measured on day-list, forecast on stream) is the cleaner formulation and is not yet built.
- Congestion forecast is one-pass + time-aggregated; a time-indexed version is future work (but see
  Principle 4 — sharpness caution). Its measured value predates the sequencer; a map-off ablation
  under the full stack shows it is now near-zero on the average day but prevents a ~1-in-30 gridlock
  meltdown (insurance, not ranking) — keep, but its role has narrowed.
- Fleet-level route deconfliction (Part D) and ADG execution not yet integrated.
- Delay-prediction negatives are within this substrate's dynamics; a less-chaotic domain may differ.
- Beta rumor map is built + validated (observation only); *acting* on it is not yet evaluated.

## 8. Conclusion + Future Work
- The design is a two-part world model that is **honest about the present and silent about the
  future**: a spatial congestion field steers *around* delay (never predicts it), and a
  receding-horizon rollout chooses tasks by imagining the fleet forward under measured — not assumed —
  physics, committing one move and re-planning constantly. The plan is disposable; the re-planning and
  the honest corrections carry the value. A value-of-perfect-information discipline retired every
  future-prediction dead end cheaply, and a value-loss autopsy localized the real constraint to picker
  rendezvous.
- Future: **take the pace/combined model to the stream** with a direct deadline-density feature and a
  demand-forecast of clustering; a **sampled-futures rollout** for the stream (VoPI-gated); measure the
  **stream ceiling**; **act on** the disturbance belief map (support/recovery tier); fleet
  deconfliction (Part D) + strict ADG execution; scale/generalization study; MAPF / TA-RWARE
  throughput yardsticks.

---
## Assets (for figures/tables)
- **Act I** bake-off CSVs: `results/bakeoff_100.csv` (62-seed main), `results/soft_bakeoff.csv`,
  `results/prob_bakeoff30.out`, `results/variance_head.out`, `results/reroutes_bakeoff.csv`,
  `results/dl_cong_bakeoff.csv`, `results/disturb_100.csv` (100-seed disturbances),
  `results/disturb_adhere_bakeoff.csv`.
- **Act II** — sequencer confirm: `results/fixconf_120.csv`, `results/wideconf_*.csv`,
  `results/width_*.csv`; open-loop: `results/oloop_*.csv`; map-off ablation: `results/nomap_*.csv`;
  ratio sweep: `results/ratio_*.csv` (+ `scripts/exp_ratio.py`, `exp_ratio_plot.py`,
  `results/ratio_sweep.png`); value-loss autopsy: `scripts/viz_value_loss.py`,
  `results/value_loss.png`; delay autopsy GIF: `scripts/viz_delay.py`, `results/delay_causes.gif`;
  pace model: `scripts/train_pace.py`, `results/pace_{picker,combined}.pkl`, `results/pace_rank_*.csv`,
  `scripts/viz_pace.py`, `results/pace_vs_ema.png`.
- Core code: sequencer `scripts/congestion_policies.py` (`PartACongestionSeqController`, `_SqWide`,
  `_SqPacePick`, `_SqPaceComb`); funnel `scripts/sim_priority.py`; rollout `wwm_sim/rollout.py`;
  demand `wwm_sim/demand.py`; universal paired harness `scripts/ablate_l2.py`.
- Disturbance model: `wwm_sim/warehouse.py`. Beta rumor map: `wwm_sim/rumor_map.py`.
- GIF viz: `scripts/viz_futures.py`, `viz_gap.py`, `viz_openloop.py`. Plain-language companion:
  `docs/HOW_IT_WORKS_SIMPLE.md`. Full experiment log + reasoning: `docs/NOTES.md`.
