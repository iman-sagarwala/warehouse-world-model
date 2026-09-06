# Build Checklist — Warehouse World Model

Progress tracker following the plan's build order (each stage is the next
stage's baseline). `[x]` done · `[~]` in progress · `[ ]` not started.

---

## CURRENT STATE (2026-07-22) + NEXT STEPS

**CONFIRMED 2026-07-22 (final): day-list stack = champion + urg8 + HI-FI SEQUENCER (live pace bias +
per-order batch banking + 15-branch audition) = +12.8 (+3.3%) over plain champion, 120 fresh seeds
(sqwide vs urg8: t=3.24, sign p<0.00001; width marginal sign p=0.018). Width grid: cliff below 12,
flat plateau 12-25 -> 15 adopted, knob closed.**

**WHAT THE RANKER IS (clarified 2026-07-22ab):** per-task scores are PLAIN VALUE + urgency (no rate
formula anywhere). The FINAL pick maximizes SIMULATED TOTAL VALUE over the remaining day -- i.e.
value-per-robot-minute with a LIVE exchange rate for time (rate80's fixed rate was right only in
bottomless queues; the sim looks the rate up by playing the day out). The wage objective survived;
the formula that first carried it did not.

**Deployed config:** STREAM -> `parta_congestion` (plain champion — unbeaten by 17 scorer variants,
sequencer, arrival-aware sequencer, fetch-leg preemption, explorer-policy). DAY-LIST -> champion +
**urg8** (bounded urgency in makeable tier, **+0.9% CONFIRMED**, 120 fresh seeds, t=3.22, sign p<.001).
Uniform regime RETIRED (rate80's +10.8 was real but regime-bound; shelved with it: dock-choice +5.3,
map +3.4 — all unvalidated in realistic regimes).

**THE STANDING PRIZE:** day-list assignment oracle ceiling **+5.6%** (fixed worlds, zero luck), urg8
banked 0.9%, remaining **~4.5% residual** survived EVERYTHING searched with the analytic evaluator:
rates x4, blends x4, adaptive x2, screens x2, urgency x3, proximity x4, rollout re-ranking, deviation
gates (2 families), joint first-moves (beam). All cap at +1..2, coin-flip.

**LIVE HYPOTHESIS (2026-07-22q): it's the EVALUATOR, not the search.** Same perturb-and-select concept
scores +17 pts when judged by the REAL ENV (oracle) and +1 when judged by the analytic sim. The item-6
retirement is REVISED: timing precision is worthless for CLASSIFICATION (delay oracle, stands) but
evaluator fidelity may be decisive for RANKING SCHEDULES. Fidelity fixes queued, all certain-info:
- [x] **1. PICKERS INSIDE THE SIM — BUILT 2026-07-22** (_sim_core: rendezvous = max(AGV, best picker
      ready), pickers as (free_time, pos) resources). ABLATION VERDICT: **passenger, +0.13** — the sim's
      picker constraint rarely binds. Kept (harmless, honest physics); candidate for the bias-only
      simplification arm.
- [x] **2. FREED-POSITION FIX — BUILT 2026-07-22** (re-entry at nearest_empty_storage + return leg in
      the clock). ABLATION VERDICT: **passenger, +0.30**. Kept; same simplification candidate.
- [x] **3. LIVE CALIBRATION — BUILT 2026-07-22, THE ENGINE: +6.90 of the +7.97** (sim completions +=
      live _delay_ema). Extended same day by the PER-ORDER BANKING fix (batch cashier) and the
      WARM-START PRIOR (opening cold-clock; 120-seed validation in flight). Long-term successor: the
      PACE MODEL above.
- [x] **RE-RUN VERDICT: fidelity WAS the wall.** Same arms, same seeds: +1.07 -> +7.97 (screen);
      CONFIRMED on 120 fresh seeds: banking-fixed stack **+6.07 over urg8 (t=3.59, sign p=0.00006)**,
      total **+9.61 (+2.46%) over plain champion**. Ceiling above the stack re-measured at ~1.5%
      (2-4/120 shuffles beat it).

**DEAD FEEDERS (closed with evidence; do not revisit without new regimes):**
- Delay prediction in ALL forms — 5 nulls + perfect-info oracle (+0.37, CI [-2.9,+3.6]).
- Layer 2 / future-robot forecasting — deleted/perfect/per-route-window all ~0; information-gradient
  principle (avoidance points backwards). KEEP the code (harmless), never invest.
- Considerate one-ply lookahead — proxy AND true-funnel grids <= 0.
- Value-RATE / blend / load-ADAPTIVE pricing in realistic regimes — the final 120-seed matrix; blend40
  day-list +0.6% (sign p=.015) is the lone tiny survivor, unadopted.
- Pure-value screening — 28-29/30 exact ties; the cheap screen's distance term is decision-irrelevant
  (redundant with the deadline tier downstream).
- Proximity bonus (captured-category fix) — marginals <= 0 over urg8; the oracle collects starved
  orders via SEQUENCE, not at-the-moment closeness.
- Fetch-leg re-decision on new arrivals — null at margins 0/3/6 (stream).
- Frozen-arrival sequencing on the stream — actively harmful (-15.7, t=-2.0; predicted in advance);
  arrivals-in-horizon repairs to PAR only (+14.2 isolated, still 0 net vs champion).
- Joint first-moves — null (+0.17 vs urg8); k>=2 occurs ~2 rounds/day; beam-search enumeration kept
  (naive product self-destructs on preference overlap).
- Deviation gates — tightest gates best (+2 max), heavier gating rebuilds the incumbent; not adopted.

---

## ARCHIVED — CURRENT STATE (2026-07-18) + NEXT STEPS
**Champion = `parta_congestion`** (Part A funnel + congestion FORECAST steering routes; hard
makeable/doomed task tier). Paper outline: `docs/PAPER_DRAFT.md`.
Design rule: **route = congestion (sharp); deadline = task (hard tier); avoid, don't predict.**

**RE-MEASURED AT POWER (2026-07-18) — headline numbers revised DOWN:**
- Map vs NO map: uniform **+3.44** (SE 2.80, t=1.23, 120 seeds) · demand-stream +1.38 (t=0.42, 120).
  Pooled 236 paired seeds the map wins **57.6%**, sign-test z=+2.34 **p=0.019** → SMALL but REAL.
  The old 30-seed **+6.3 was ~2x inflated** (winner's curse). t-test is the WRONG instrument here:
  the map pays by preventing rare gridlock storms, and those storms inflate the SE it divides by.
  Mechanism intact: reroute p90 71.5→54.4 (**−24%**).
- **NEW WIN — congestion-aware DOCK choice** (`PartACongestionDockController`): **+5.32**
  (SE 2.19, t=**+2.43**, CI [+1.0,+9.6], 120 seeds, uniform) — *larger than the whole map*. Docks were
  ranked by raw path length, discarding the congestion cost `find_path` had already computed.
- **LAYER 2 (predicted next task) CLOSED — see the principle below.** Deleted −0.95 · perfect info
  −2.51 · perfect info + per-route window −0.33. All ~0 (120 seeds each). NOT harmful, just useless.
  KEEP IT (harmless, small compute); do NOT invest in it.

**PRINCIPLE — avoidance points BACKWARDS, never FORWARDS** (2026-07-18, the day's main result):
Information only grows with time. When I plan, robot B's next trip is a guess; when B plans, my route
is a FACT. So the LATER planner always knows more, and every now-vs-later conflict is better resolved
by it — for free, before B has moved. Layer 2 asked the WORSE-informed decision to do the avoiding;
no accuracy fixes an inverted information gradient (hence perfect foreknowledge = 0).
This UNIFIES layers 2 and 3: L3 imposes an ordering where simultaneous planning gave none (works);
L2 duplicates an ordering time already provides (inert). **Corollary — what belongs in the map: things
TRUE NOW that nobody else will handle for you.** Layer 1 yes · layer 3 yes · PICKERS yes (still a gap)
· future tasks no. Layer 1 pays because it prevents an expensive MID-FLIGHT reroute; layer 2 cannot,
because B re-plans from scratch at zero cost.

**METHOD RULES (earned the hard way 2026-07-18):**
1. **Anything under ~+8 on-time value needs 120+ paired seeds.** Five effects moved between n=30 and
   n=120 today: four shrank to ~0, one FLIPPED SIGN (+dock: −6.4@20 → +5.3@120).
2. **Never narrate a mechanism for an unresolved effect** — the story makes noise feel like signal and
   is hard to abandon. (Done 3x today, retracted 3x.)
3. Report TAIL stats (storms, worst-decile, quantiles) + sign test, not just mean+t.
4. Prefer an **ORACLE / value-of-perfect-information test BEFORE building any predictor.** Would have
   pre-empted the delay head, the variance head and layer 2 — all built, all null.
5. **Verify a patch applied; never assume.** Two silent failures today (an x/y swap that made 226/226
   lookups return empty and produced a FAKE result row; a string-patch that silently no-op'd).

Suggested next steps (rough priority):
- [~] **PICKERS INTO THE FORECAST MAP** — TESTED 2026-07-22 (cong_pktraffic): -4.67 at 30 seeds,
      unresolved-lean-negative as a MAP layer; superseded by 'pickers inside the SIM' above. Measured **37.7% of all moving-robot cells** are pickers and
      NONE are stamped (the loop is `for a in self.agvs`). They read the grid via find_path but never
      write to it. CERTAIN + CURRENT info, passes the principle above, ~one loop. Highest-value gap.
- [ ] **`parta_cong_task` AT POWER** — congestion in the cross-task score was tested at **15 seeds**
      only ("no clean win") = not a result by rule 1. The funnel ranks task-ROUTE combos and across
      tasks routes genuinely differ, so this is where congestion has spread to act on. Re-run at 120.
- [x] **COMPLETION-TIME ORACLE — DONE 2026-07-22: NULL (+0.37, CI [-2.9,+3.6], 30 seeds).** Perfect
      completion-time knowledge is worth nothing, even though the estimate is wrong by ~16 steps (p90
      +36) against a pad of 5. => NO delay model is worth building (5th agreeing result), and crucially
      **ROLLOUT ITEM 6 (the interference model) IS UNNECESSARY** -- rung 3 can chain cheap analytic
      estimates instead of simulating contention, collapsing it from weeks to days. Disturbances were
      OFF, the friendliest case, so the null generalises upward. Original rationale below.
- [~] ~~COMPLETION-TIME ORACLE (running)~~ — `scripts/oracle_delay.py`. Bounds the ENTIRE
      delay direction in one run, before anything is built. Pass 1 logs (assign_step, predicted finish)
      per task; with the actual delivery step that gives each task's REALIZED delay. Pass 2 feeds those
      true delays to the planner via `_finish_delay`, so every makeable/doomed call is made on TRUE
      completion time. Nothing -- learned head, rules model, or fleet-rollout world model -- can beat
      the truth. NULL => no delay model is worth building and rung 3 needs no interference model;
      LARGE => that gap is the prize and the world model is justified.
      PRIOR (unlike layer 2, which was null): the cutoff is a HARD threshold proven sensitive to ~4
      steps (LOAD_TIME p=0.021, p=0.009), and NOBODY ELSE resolves your missed deadline -- so the
      avoidance-points-backwards principle does NOT transfer. Early diagnostic: realized delay is
      mean +14.6 / median +12.1 / p90 +31 while the pad in use is only 5 -> the empty-world estimate
      is optimistic by ~3x the correction it carries.

- [ ] **ROLLOUT ENGINE — completion criteria to serve ALL parts incl. rung 3 (2026-07-22).**
      Today it is a per-task SCORING FORMULA; to serve Part B/C/D and a joint world model it must be a
      STATE-TRANSITION SIMULATOR: `advance(state, plan) -> (state', outcome)`. Blocking items:
        1. Return the END POSITION, not just `free_again` (a time). Cannot chain task 2 onto task 1
           without it. HALF-BUILT: `nearest_empty_storage()` already computes that cell for the battery
           reserve; it just is not returned.
        2. A STATE object (positions / assignments / batteries / queue) instead of loose per-call args.
        3. COMPOSITION — feed the rollout's output back in so a robot can do task -> task -> task.
        4. An OBJECTIVE ACCUMULATOR over a plan (on-time value, misses, sync waits), not per-task fields.
        5. PICKERS FIRST-CLASS: `partner_eta` averages over free/busy sets; a joint plan must ASSIGN
           pickers. Picker energy is not modelled at all.
        6. THE HARD ONE — the EMPTY-WORLD assumption. Fine for Part A (a constant pad patches it), fatal
           for rung 3, where contention IS what is being evaluated. Choose: step-simulate with the env's
           conflict rules (accurate, expensive, stochastic) vs aggregate slowdown from local density
           (cheap, approximate). THE ORACLE ABOVE DECIDES HOW ACCURATE THIS MUST BE.
        7. Calibration must COMPOUND correctly over a chain (3 tasks = 3 pads? unverified).
        8. Part B needs CHARGING AS A PLAN PREFIX (time + energy), so "charge then task" is expressible.
        9. Part C needs DEMAND ARRIVALS inside the horizon (the demand model now exists -> plumbing).
      SEQUENCING: the oracle first. If perfect timing is worth ~0, item 6 is unnecessary and rung 3 is
      mostly plumbing (1-5, 8-9) = days. If it is worth a lot, item 6 IS the project = weeks.

- [ ] **Scale/generalization study** — champion at other fleet/map sizes (the "size-agnostic" pitch).
- [x] **Final-scale eval** — DONE 2026-07-18 at 120 paired seeds (see revised numbers above).
- [~] **Knob tuning across the AGV×picker RATIO GRID** (2026-07-30, supersedes the Optuna/held-out plan —
      we use the full 72-cell grid × 120 paired seeds instead, which is stronger than a held-out split
      because every arm shares the identical seeds). Base = `_SqWidePkRateAdaptive` (sequencer +
      value-rate pickers; MRO verified). Coordinate ascent, one knob at a time. Full detail in ROADMAP M1.
      - [x] `URG_W` — 43,200 runs, comb {0,4,8,12,16}. **REGIME-conditional, not ratio-dependent:**
            **0 on day-list** (monotonic decline; optimum = term OFF, a natural boundary),
            **8 on stream** (interior peak; 8vs4 t=+2.69, 12vs8 t=−2.99). SHIPPED.
      - [x] `W_SYNC` — 34,560 runs, comb {0,0.15,0.3,0.5}. **NULL**, default 0.3 kept (pooled 0→−0.38,
            0.15→−0.03, 0.5→−0.30, all |t|<2). Killed the "W_SYNC=0 when pickers abundant" hypothesis.
            *Mechanism:* `my_wait` is already inside `finish` → already priced by the 1000-pt
            makeable/doomed tier; the explicit term is a 2nd invoice worth ~1–4 pts, so it only
            reorders near-ties. **This closes the old "W_SYNC-style overfit" worry — the knob is inert.**
      - [ ] `RATE_ALPHA` — RUNNING, comb {3,4,5,6,7}. Never swept at grid scale before (5.0 came from an
            early deployment-fleet-only sweep).
      - [ ] `CONG_LAMBDA` / `CONG_WEIGHT` / `SEQ_DEPTH` — queued.
      - [ ] `URG_S0` / `PK_URG_W` / `PK_URG_S0` — deferred (S0 = ramp shape).
      - **skip** `FUTURE_WEIGHT` (layer-2 = documented null).
- [ ] **DATA HYGIENE (paper-critical):** day-list and stream are NOT workload-matched. Verified
      `daylist == stream(warm=0)` bit-identical → the sole difference is stream's `seed_initial(n=12)`
      warm start (+25% orders, +33% value). Knob results SAFE (paired within regime); the **VoPI /
      perfect-foresight bound (day-list − stream) is contaminated by load, not pure information.**
      Fix = champion, both regimes, warm start matched, a few fleets × 120 seeds.
- **METHOD RULE (2026-07-30):** per-cell argmax maps are EXPLORATORY only — they fail split-half
      reproducibility on every knob tested so far (agreement ≈ marginal chance rate, z≈0). Pooled paired
      tests are the confirmatory instrument; deploy group-level rules, never per-cell bests.
- Route-driving is ALREADY DONE in the champion via soft ADHERENCE (env.prefer_committed +
  committed_cells; find_path hugs the committed route, detours around blockers). So committed routes
  DO drive today.
- [ ] (OPTIONAL) **ADG executor + Part D** — the STRONGER route-driving: strict crossing-order,
      delay->wait, 0 collisions BY CONSTRUCTION (built + toy-demo'd in `demo_adg_env.py`, but PARKED).
      Only buys the provable-collision-free guarantee, and REQUIRES fleet deconfliction (Part D) +
      loading/pick-deliver in ADG mode, else it deadlocks (confirmed this session). Adherence already
      wins, so pursue only if the hard guarantee is wanted.
- [ ] **Disturbance belief map** — the hidden-hazard Beta rumor map (still unbuilt); risk term + b_hard.
- [ ] **Benchmarks** — MAPF inner-loop, TA-RWARE head-to-head (evaluation harness below).
- [ ] **time-indexed forecast — RE-AIMED at LAYER 1 (2026-07-18)**, not at future tasks. Layer 1 stamps
      a robot's WHOLE remaining path as uniformly busy, but the robot occupies ONE cell at a time: if B
      crosses cell c at step 2 and I cross it at step 8 we never meet, yet it is marked and I detour.
      So layer 1 systematically OVER-marks, and it is the layer carrying the value. Noise is smallest
      here too (~11-step horizon vs 27+ for future trips). Timing noise sources: rendezvous waiting
      (2.55/7.68 busy AGVs are stationary awaiting a picker), reroutes, stucks, congestion itself —
      time-to-free MAE ~14 on mean 27, so bins must be wide. Adding a time axis to LAYER 2 is pointless
      (bounded at ~0 by the oracle); adding it to layer 1 is untested.

---

## Tooling / infrastructure (not a plan stage, but needed)

- [x] Virtualenv with all deps (numpy, gymnasium, networkx, pyglet, pyastar2d,
      lightgbm, pandas, scikit-learn, matplotlib)
- [x] TA-RWARE installed editable as the simulator substrate
- [x] `scripts/run_tarware.py` — run env with FIFO / random, report metrics
- [x] `--render` + `--fps` throttle for the single-env renderer
- [x] `scripts/sim_dashboard.py` — side-by-side FIFO vs random dashboard
      (legend, live per-AGV task list, running stats table)
- [x] Project README + progress notes (`docs/NOTES.md`) + this checklist

---

## Stage 0 — Foundation (all plain code, no learning)

> **What "the world model" is** (it is NOT one component): the planner simulates
> possible futures from THREE pieces working together —
> 1. **Rollout engine** (`wwm_sim/rollout.py`) = the SKELETON: futures under KNOWN
>    RULES + POSITION only (travel, battery, time), deterministic, **delay is always
>    zero here** — delay is not in the rulebook.
> 2. **Predictive heads** (analytic formulas @Stage0 → LightGBM @Stage3) = the DELAY
>    and RISK/interrupt guesses — "what the world does to the route."
> 3. **Beta rumor map** (belief filter) = the hidden-disturbance state estimator.
>
> So "simulate futures under position AND delay" = rollout (position) + heads (delay)
> + map (disturbances). The rollout engine alone handles position/rules, not delay.

- [x] Simulator substrate (adopt TA-RWARE)
- [x] FIFO nearest-agent baseline running (§6.1 comparison target)
- [x] **`wwm_sim`** — editable copy of the simulator (verbatim TA-RWARE fork,
      renamed; installed editable; FIFO parity verified). THIS is what we edit;
      vendored `tarware` stays as the untouched baseline.
- [x] **Battery model** — `wwm_sim/battery.py`: drive/idle/carry(AGV)/pick(Picker)
      drain, charge-at-charger, battery-floor→stranded. Constants grounded in
      Robotnik (RB-VOGUI/RB-KAIROS+), provisional+tunable, compressed via
      `steps_per_charge`. Dashboard shows per-robot battery bars.
      DONE (all 3 TODOs): (1) DEDICATED CHARGERS reachable by both types
      (`default_chargers`: spread of shelf-cells, since goals are barred to pickers —
      pickers now recharge); (2) MOVEMENT GATE + Stage-0 CHARGE DECISION
      (`BatteryAwareController` = "battery": low free robots charge; flat robots gated to
      no-op); (3) WIRED INTO ROLLOUT (`rollout.battery_feasible` = Part A step-4 filter).
      Verify (`scripts/verify_battery.py`, spc=400 binding): charge+gate cuts strandings
      6.2→1.0 /12 vs no rule. Full strandings=0 "by construction" (§6.1) completes with
      the Part A battery filter + Part B emergency tier (the model gives the mechanism;
      the guarantee is a later planner-stage integration). See NOTES 2026-07-10.
- [~] **Rollout engine** — `wwm_sim/rollout.py`: analytic Stage-0 version.
      `rollout_task(env, shelf, agvs, pickers) → fetch, rendezvous, finish,
      deadline_margin (+ battery_used/margin)`; `geom_completion` / `per_task_window`.
      Manhattan distances, calibrated to the adaptive window. First application (per-task
      doomed window) tested + LOST to the global window — completion is congestion/picker-
      wait dominated, not geometry; a good per-task estimate needs a delay signal (Stage 3
      head). Engine kept for its REAL use = Part A plan scoring (margins). See NOTES
      2026-07-09. TODO: use A* distances (not Manhattan) + wire into Part A scoring.
- [x] **State assembler** — DONE. The `feat` dict in `sim_priority.py` (~line 491), built per candidate
      plan: geometry (my_arrival, dock, path_stretch), task attrs (value, dl_slack, pred_finish), partner
      sync (picker_eta, my_wait), fleet state (n_busy_agv, n_free_pk, q_size, q_per_agv, busy_frac,
      free_pk_frac), congestion (local_density, delay_ema, dur_recent, dur_trend, deliv_rate), diurnal
      phase (sin_t, cos_t, day_frac), deadline clustering (dl_soon40/80/160). Feeds the delay/pace head.
      REMAINING FIELDS (add when their subsystems act, not blockers on the assembler): **battery**
      (needs Part B charge-as-prefix) and **belief values** (needs M2 rumor map wired into decisions).
- [~] **Belief filter — Beta rumor map BUILT (2026-07-16)** (`wwm_sim/rumor_map.py`): 2 counters/cell;
      SIGHTING (disturbance within sensing radius of a robot) raises alpha, CLEAN traversal raises beta,
      time DECAY toward the uniform prior. belief = alpha/(alpha+beta). OBSERVES disturbances (can't
      PREDICT them — exogenous random noise, no inferable ranking; forecasting would need a hand-built
      failure-layout model, which we explicitly avoid). Demo `scripts/demo_rumor.py`: precision@20 =
      20/20. NOT acted on yet → Part B support tier + task selection (later). See NOTES 2026-07-16.
- [~] **Hard-constraint filters** — battery-floor filter DONE (`rollout.battery_feasible`, Part A step 4).
      COLLISION filter built but a NO-OP on this substrate (env never crashes — it reroutes/waits; nothing
      to delete) → only meaningful WITH exact-route ADG execution; re-enable then. DISTURBANCE-MAP filter
      (avoid cells the rumor map suspects are disturbed) — only worth building once disturbances are
      SPATIALLY CLUSTERED (current model is uniform-random → no pattern to exploit). See NOTES 2026-07-16.
- [ ] **(LATER) Interrupt tier (Part B)** — mid-execution: ABORT/re-plan a task if (a) its route's
      rumor-map DISTURBANCE PROBABILITY exceeds a threshold, or (b) it would finish BELOW the battery
      floor. Deferred by user 2026-07-16 (needs the rumor map acting + battery integration). Edit later.
- [x] **Analytic formulas — CUT (2026-07-16).** Not needed: DELAY is provably unpredictable (chaotic per
      task — 4 ablations), so no analytic delay formula; RISK = random exogenous disturbances (uniform,
      unforecastable), so no analytic risk formula either. Completion is handled by the rollout engine.
      The "pre-learning heads" premise doesn't apply where the target is irreducible noise.
- [~] **Part A** — filter → cheap screen (top ~15) → Yen's k-routes → delete
      illegal → score → rank tasks by best route → commit "robot→task→route".
      STARTED (`PartAController` = "parta"; `wwm_sim/routing.py`): steps 1-3,5-7 built
      and RUNNING per-robot (cheap screen value−0.15·Manhattan; Yen's k=3 via
      networkx.shortest_simple_paths; RUSH-style value+decay utility; commits a ROUTE).
      Base `_assign_tasks()` extracted so the funnel overrides it.
      ROLLOUT FEATURES wired into step-5: (1) RENDEZVOUS SYNC-UP — `rollout.partner_eta`
      4 scenarios (committed/free_est/wait_free/unserviceable, cases 2&3 use AVERAGE not
      min — contention), `my_wait` penalised (W_SYNC); (2) RETURN-TO-FREE — `free_again`.
      Battery-floor FILTER kept; charge-DETOUR removed (support-then-task = Part B/C).
      PICKER-SIDE Part A: `_dispatch_pickers` now a symmetric funnel — each free picker
      screens candidate AGV-rendezvous, routes on the HIGHWAY graph (`build_picker_graph`,
      Yen's), ranks by the SAME value×decay parent-task utility as the AGVs (one task = AGV
      subtask + picker subtask) + sync penalties (agv_wait/picker_wait). Result: route-aware
      Part A now TIES RUSH — on-time 26.2 = 26.2, value 198.8 vs 200.2 (4 seeds) — while
      carrying routes + filters + sync RUSH lacks. VISUALIZATION
      `scripts/viz_parta.py` (--focus-kind agv|picker) → results/parta_routes.png:
      LEFT chosen route per AGV (bold), RIGHT all Yen's candidates (faint) + chosen bold.
      COLLISION filter (step 4) BUILT (reservation-table space-time vertex+edge-swap check)
      but PARKED (`COLLISION_FILTER=False`): the env drives its OWN A* + reroutes, ignoring
      our committed route, so route-level filtering is a no-op (hard-delete just dropped tasks
      → idle AGVs → throughput crash) until ADG execution (Stage 1) actually drives our
      routes. Machinery reused by Part D (combo-crash deletion). See NOTES 2026-07-11.
      b_hard/risk still PLACEHOLDER (need the rumor map). Next real Part A step = disturbances
      + Beta rumor map → risk term (step 5) + b_hard (step 4). TODO also: A* route lengths.
- [x] Deadlines on tasks — plumbing (`wwm_sim/deadlines.py`, `Shelf.deadline`, examples, demo) PLUS
      the **deadline-GENERATION model, DONE 2026-07-18** via `wwm_sim/demand.py`: every arriving order
      draws value + deadline = t_arrive + slack from a RUSH/STANDARD mixture (20% rush, tight slack
      25-60 and 1.6x value; standard 80-200). Batching: a shelf's value = SUM of its pending orders,
      deadline = EARLIEST. Deadline-met metric + Part A scoring already wired.
- [~] **Disturbance spawning BUILT (2026-07-16)** — `env.disturb_rate` + seeded `_disturb_rng` spawn
      random 1-3 cell highway blobs (20-60 steps) as temporary obstacles; find_path routes around them;
      policy-independent schedule (paired). 30-seed ranking check under disturbances: scripts/verify_disturb.py.
      Partial-obs sensing feeds the Beta rumor map above.

### Toward Part A — priority (deadline) task assignment (our strategy, started)
- [~] **Priority assignment** — `PriorityController` (in `scripts/sim_priority.py`):
      tasks assigned to nearest free AGV in DEADLINE order (soonest first), re-sorted
      every step so new urgent tasks jump ahead. Non-preemptive (free robots grab
      the most-urgent task; in-progress robots keep theirs). Single-sim dashboard
      with a deadline-ranked task panel. Verified: priority delivers low-deadline
      tasks first, FIFO ignores deadlines. TODO: preemption (option); full Part A
      (screen → Yen's k-routes → score → rank), multi-factor priority beyond deadline.
- [~] Value-aware priority (`ValuePriorityController`): among makeable tasks do
      HIGHEST-VALUE first (deadline tie-break); doomed shed. Per-task VALUE plumbing
      (`wwm_sim/values.py`). = value × P(on-time), hard P. Doomed cutoff `window` now
      ADAPTIVE (live mean assign→deliver duration: ~69 @ 8/4, ~60 @ 12/8; replaced
      fixed 83, +on-time value). VALUE-threshold shedding tested + REJECTED (worse:
      idles/attempts-late) — value only reorders, which is correct; opportunity-cost
      gating = Part C demand model. See NOTES 2026-07-09. (Superseded as default by
      RUSH below.) TODO: smooth P(on-time); per-task completion estimate.
- [x] **Lateness-decay rush priority** (`RushValueController`, **NOW THE DASHBOARD
      DEFAULT**): same makeable-first hard tier (on-time work never displaced), but the
      DOOMED tier is rush-ordered by DECAYED value `value × g**lateness` — rush the
      barely-late high-value tasks, sink the hopelessly-late ones. Metric-honest task
      value: on-time = full, late = partial (per-step decay), undelivered = 0. Per-task
      SLA HARDNESS `g` (`wwm_sim/hardness.py`, `Shelf.hardness`, `data/hardness_example
      .txt`) = a SEPARATE axis from value: steep g = hard-SLA cliff, gentle g = soft
      order; so each task carries deadline (when) + value (how much) + g (how badly late
      hurts). Verified (`scripts/verify_rush.py [--weighted]`, 10 seeds, hard 500-cap):
      RUSH ties on-time value (206.4 vs 206.6) and wins total decayed value (229.3 vs
      220.1, +4.2%); at global decay +1.4–2.6% across g=0.97–0.99. With g=1 RUSH == VALUE
      (decay is the entire difference). TODO: per-task rollout completion estimate to
      replace the global `window` in proj_lateness; Optuna-tune g per order class.
- [x] **Rendezvous-alignment term in task utility** — DONE, this is the Part A SYNC
      term (no longer a separate future idea). Both sides of the funnel score
      `value×decay − W_SYNC·wait`: an AGV penalises its wait for the picker, a picker
      penalises the AGV's wait (+ its own), with the partner ETA from `rollout.partner_eta`
      (committed / free-avg / wait-free / unserviceable). Rewards AGV+picker arriving
      together; attacks the picker-wait bottleneck. Superseded the earlier reverted
      `AlignedValueController` prototype. See NOTES 2026-07-10 (Part A sync-up + picker
      funnel). `W_SYNC` is tunable (Optuna later); a smoother arrival-uncertainty version
      arrives with the delay head, but the alignment term itself is implemented.

## Stage 1 — Full system (still plain code)

- [ ] Part B — support-then-task, judged from the imagined future; duration menu.
      CLARIFIED SCOPE (2026-07-11): Part B's genuine, non-overlapping job = STATE changes —
      CHARGE (battery) + RECOVER-de-risk (failure risk). Reroute (POSITION) is absorbed by
      Part A's k-route choice; wait (TIMING) by Part A sync-wait + ADG conflict-wait. So Part
      B ≠ reroute/wait. Upfront vs interrupt: charge/recover fire BOTH (upfront pit-stop OR
      mid-drive struggle); reroute/wait exist both but owned by Part A/ADG; DITCH-and-switch
      is interrupt-only; get-ready (Part C) is upfront-only. "Recover" has 2 senses: de-risk
      (state) and "ditch onto a better task" (abandon). Ditching WHILE CARRYING a shelf
      requires offloading it to a rack first (can't carry two / abandon mid-aisle) — a real
      cost that makes mid-carry ditching rare. See NOTES 2026-07-11.
- [~] Part C — future-readiness (demand proximity, deferred commitment, scouting).
      CUT 2026-07-11 because the always-full queue left no lull to prepare for, with the explicit
      condition *"revisit only if we add streaming demand."* **REVIVED 2026-07-18: we added it.**
      `wwm_sim/demand.py` now gives bursts/gaps + spatial popularity, and the queue genuinely ebbs
      (16.1 mean, 9-24 range, unclaimed candidates 11.4, idle AGVs 0.28/8).
      IMPORTANT — today's oracle result does NOT close this. That bounded knowing what *ROBOTS* do
      next, where the later planner resolves the conflict for free. **Demand does not reroute around
      you** — an order arriving in 80 steps will not accommodate your plans — so the
      avoidance-points-backwards principle does NOT transfer. Different information gradient.
      **RESOLVED AS A NULL 2026-07 (static demand).** SA5 (random future draw), EV (deterministic
      mean-field + trust knob β), and MCTS (K-sample chance nodes, ± urgency) were ALL wash-to-negative
      at 120 seeds. Anticipation is dead on the current STATIC-hotspot demand.
      **WHY they were null (diagnosed 2026-07-30, the useful part):** every one of those arms fed the
      forecast into TASK CHOICE — and on the stream there is nearly always a task available, so the
      forecast never changed an action. Measured: free AGVs exceed available tasks in only 0–20% of
      steps on the stream (0% at 4×4 and 4×9, 3% at 6×6, 8% at 9×4, 20% at 8×8). Foresight can only pay
      where it changes a decision. → **See ROADMAP M3c: aim the SAME estimator at IDLE-AGV staging**
      (where should a spare robot wait), gated on `free AGVs > available tasks`, stream + AGV-rich only.
      Not MCTS — an assignment against a predicted density field; the estimator already exists in
      `_SqWidePkRateEV`'s hot-cell machinery.
      ⚠️ **CORRECTION — the "perfect-foresight bound for free via `seed_day_list()`" is NOT clean.**
      Verified 2026-07-30: `daylist == stream(warm=0)` bit-identical, so the arrival process and every
      deadline match — but stream additionally gets `seed_initial(n=12)` (+25% orders, +33% value) that
      day-list never receives. **day-list − stream therefore mixes INFORMATION with LOAD and is not a
      pure VoPI.** Must be re-measured with the warm start matched before it is quoted anywhere.
- [ ] Part D — group decision over A/B plans only (Part C cut): combos, exact-route
      commit, regret-ordered fallback + LNS past ~5 robots. (pay-per-zone scout dedup was
      a Part C thing — moot without scouting.)
- [~] ADG execution (small lateness absorbed as waiting, not crashing) — ALGORITHM +
      ENV-INTEGRATED (movement-only): `wwm_sim/adg.py` (build_adg / simulate_adg /
      simulate_naive) + `scripts/demo_adg.py` (standalone: 1-step lateness → naive 1 collision
      vs ADG 0). ENV MODE in `wwm_sim.Warehouse`: `set_adg_plan(routes)` + `_adg_attribute()`
      drive committed routes in crossing-order via the real micro-action layer, step() skips
      reroute/stuck when `_adg_mode` (opt-in; normal RUSH unaffected). `scripts/demo_adg_env.py`
      proves it in the REAL env (stalled AGV → follower WAITS, 0 collisions, no reroute).
      Deadlock: ADG on a VALID plan is acyclic → deadlock-free; needs Part D deconfliction for
      fleet use (Yen's routes aren't jointly deconflicted). See NOTES 2026-07-11.
      NEXT: feed controller committed-routes per leg + pick/deliver in ADG mode + Part D
      deconfliction; then re-enable the Part A collision filter (env now executes our routes).
- [ ] Safety split (emergency filter vs. tradeable discomfort)
- [ ] Curiosity taper + scout dedup

## Stage 2 — Tuned knobs   ⟵ IN PROGRESS (2026-07-30)

- [~] **Ratio-grid knob sweep** (replaces the Optuna plan — see the detailed sub-checklist under
      "Knob tuning across the AGV×picker RATIO GRID" above for per-knob status).
      Done: `URG_W` (regime rule 0/8, shipped), `W_SYNC` (null). Running: `RATE_ALPHA`.
      Queued: `CONG_LAMBDA`, `CONG_WEIGHT`, `SEQ_DEPTH`.
- [ ] Optuna weight tuning of importance_* vs. throughput / tardiness / strandings
      *(unchanged — this is the DISTURBANCE/importance weighting, a different knob family from the
      decision-layer scorers above; still open and blocked behind M2 making the rumor map act.)*
- **RUNNING RESULT so far: tuning is coming back FLAT** — 1 regime rule + 1 null from 2 knobs, consistent
  with the standing "decision layer is near-maxed (~1.5–2% from the hindsight oracle)" finding. If
  CONG/SEQ_DEPTH also land null, freeze the knobs and move effort to M2 (rumor map) rather than tuning on.

## Stage 3 — Learned heads (calibration-gated, one at a time)

- [x] Simulator diary logging (predicted vs. actual) — `train_delay_head.py` /
      `train_variance_head.py` log per-commit features + realized delay over N seeds.
- [x] **delay head — REMOVED FROM THE PLAN (2026-07-22).** Built, tested, null five independent ways
      plus a perfect-information oracle (+0.37, CI [-2.9,+3.6]): per-task delay is irreducible noise.
      The Stage-3 learned-head slot is REASSIGNED to the **PACE MODEL** (fleet-level day-pacing profile
      across warehouse conditions — see CURRENT STATE): same LightGBM machinery, aimed at the quantity
      the 2026-07-22 ablation proved valuable (+6.9) instead of the one proven worthless.
      Artifacts retained for the record: results/delay_head*.pkl, train_*_head.py.
- [ ] Calibration gate (isotonic / Platt) per head
- [ ] Ship gate: ≥15% better than formula AND calibrated

## Stage 4 — Upgrades (optional)

- [x] **Demand model upgrade — DONE 2026-07-18, pulled forward from Stage 4** (`wwm_sim/demand.py`).
      Non-homogeneous Poisson base λ(t)=rate·diurnal(t) (rate 0.075 ≈ delivery capacity, amp 0.8 →
      0.2x..1.8x) + **Hawkes** self-exciting bursts (p=.006, jump .4, decay .90) + **Zipf(1.1)** SKU
      popularity under VELOCITY SLOTTING (rank by proximity to 3 hot centres + jitter, so popularity is
      genuinely spatially clustered) + rush/standard value-deadline mixture + order BATCHING (many
      orders per shelf; one trip fulfils all). Two modes: streaming, and `seed_day_list()` = whole day
      known up front (also the perfect-demand-foresight bound). Env hook: `env.demand_model`, orders
      retire on delivery (no uniform resample) so the queue ebbs and flows.
      KNOWN FLAW (unfixed): `_inject` excludes shelves currently CARRIED, so the shelf choice depends on
      robot state → the stream is NOT perfectly policy-independent, and 2026-07-18's demand-regime
      comparisons were not exactly paired. Fix = drop the exclusion (a customer orders regardless), but
      it re-baselines every demand-stream number.
- [ ] Optional GATv2 graph feature encoder (head inputs only)
- [ ] Optional ablation opponents (learned ranker, Dreamer-style)

---

## Evaluation harness (spans all stages)

- [ ] Planner-outcome metrics: throughput, deadline hit rate, tardiness (mean +
      p95), energy/task, strandings=0, collisions=0
- [ ] Rumor-map metrics: 90/90 sensitivity/specificity, latency ≤15, calibration
      ±10% (Brier + reliability diagram), with-map vs. without-map on same seeds
- [x] **Ablation runner — DONE 2026-07-18**: `scripts/ablate_l2.py` (paired, identical seeds, one
      mechanism toggled; `POLICIES=` / `SEEDS=` / `DEMAND=` / `OUT=` env vars), plus
      `scripts/oracle_test.py` + `scripts/oracle_perroute.py` (value-of-perfect-information harness:
      pass 1 records every commit, pass 2 replays it as ground truth) and `scripts/storm_check.py`
      (tail/storm statistics). NOTE the ≥3%-or-cut rule needs the power rule attached: 3% of ~200 is
      +6, which is BELOW the noise floor at n<120.
- [ ] Benchmarks: MovingAI MAPF inner-loop ≥98%, Lifelong MAPF, TA-RWARE head-to-head

---

## Back-pocket ideas (stowed; specifics TBD)

- [x] **Congestion FORECAST map — BUILT + CURRENT CHAMPION** (un-demoted 2026-07-15;
      `scripts/congestion_policies.py::PartACongestionController`). A per-cell traffic grid built
      each step by rolling FUTURES forward (a lightweight world model): (1) busy robots' remaining
      paths, (2) about-to-finish robots' PREDICTED next task+route (same cheap-screen rule) = the
      future-aware part, (3) prioritized stamping (robots assigned one-at-a-time, each dodging those
      before it). Used to (a) pick the least-congested Yen route, (b) reroute around traffic
      (env.congestion_grid feeds find_path), (c) adhere softly to the committed route.
      **REVISED 2026-07-18 (120 paired seeds): +3.44 uniform / +1.38 demand; pooled 57.6% of 236 seeds
      (sign-test p=0.019) — SMALL but REAL, roughly HALF the old 62-seed claim. Source (2), the
      "future-aware part", contributes ~NOTHING and is CLOSED (deleted −0.95 / perfect info −2.51 /
      perfect + per-route window −0.33). The value lives in (1) and (3), both CERTAIN — see the
      information-gradient principle in CURRENT STATE.**
      KEY LESSON: congestion is for AVOIDANCE (routing), NOT PREDICTION — it's a
      FIELD you steer around, not a gauge you read a delay from (models SPACE reliably, skips the
      noisy TIME dimension). Adherence (env.prefer_committed + agv.committed_cells) only pays off
      WITH the forecast spreading routes first; alone it locks robots into jams. See NOTES 2026-07-15.
      Still open: SOFT P(on-time) from a bounded rollout (the one un-tried deadline lever).
- [~] **Rendezvous-alignment / smooth P(on-time) / per-task completion estimate** —
      rendezvous-alignment is DONE (the Part A sync term, see above). Still open:
      SMOOTH P(on-time) and a per-task completion estimate — both wait on the delay head.
