# Roadmap to Finish — Warehouse World Model

Target: complete a **defensible, written-up** project by ~mid-Sep (≈7.5 weeks from 2026-07-26).
Sized in ~1-week chunks, dependency-ordered, core novelty front-loaded, paper + buffer at the end.
No calendar dates — just ordered time-chunks. Each milestone has a **done-when** and a **de-scope lever**
so we can stay on schedule if something overruns.

Guiding facts (from NOTES/checklist — don't re-litigate):
- **Decision layer is near-maxed** (~1.5–2% from the hindsight oracle). Don't over-invest in new scorers.
- **New champion = `sqwidepr`** (sequencer + value-rate pickers). Beat THIS, not `cong_l2on`.
- **Delay prediction is dead** (5 nulls + oracle). Only surviving Stage-3 head = the **pace model**.
- **Layer-2 / joint-first-moves are null.** Full Part D combo-optimization is a *documented* result, not a build.
- **Rumor map is BUILT but INERT.** The central novelty (belief-driven decisions under disturbances) is
  currently unvalidated → highest-value remaining work.
- Method rules stand: 120-seed rule, two instruments (t + sign), ablate one mechanism at a time,
  every-mechanism-≥3%-or-cut, validate in the deployment regime.
- **NEW (2026-07-30) knob-sweep method rules — apply to every remaining tuning milestone:**
  - **Pooled paired tests are CONFIRMATORY; per-cell argmax maps are EXPLORATORY.** Per-cell winners are
    noise-driven (per-cell SE ≫ true effect) and *dilute* as you add grid points.
  - **Split-half reproducibility is the test for "is this map real?"** Recompute the argmax on seeds 0-59
    and 60-119; agreement must beat the marginal-implied chance rate. Every knob so far = patchwork (z≈0).
  - **Bracket the optimum:** grids must include a value on each side of the winner; extend only when the
    winner lands at a boundary (URG_W did). Refine sub-boundaries only if adjacent points are resolvable
    AND the peak location is uncertain — near a smooth peak, halving the grid gains ~¼ of the adjacent-step
    difference, usually below the noise floor.
  - Deploy **group-level rules** (regime/ratio-conditional), never per-cell bests — the latter aren't
    reproducible and aren't a deployable policy.

---

## ✅ Already done (not re-listed as milestones)
Simulator (`wwm_sim`), Part A funnel + congestion map (champion), **sequencer** (rollout), **value-rate
pickers**, **demand model** (Stage 4, pulled forward), deadlines/values/hardness, battery model,
disturbance spawning, **rumor map built**, ADG built + toy-demo'd, ablation runner + oracle harness,
stream validation, oracle-gap map, strategy guide.

---

## M1 — Lock & tune the decision core  (~1 wk)  ⟵ **CLOSED 2026-08-05** (~220,000 runs)
Close Stage 2 and stop touching the decision layer. Coordinate ascent on `_SqWidePkRateAdaptive`
(= sequencer `_SqWide` + value-rate pickers `_VRPicker`; MRO verified 2026-07-30), full AGV×picker
4-9 ratio grid × {daylist, stream} × 120 seeds = 72 cells per knob.

**Checklist**
- [x] **`URG_W` (AGV deadline weight)** — 72/72 cells, comb {0,4,8,12,16}, **43,200 runs**. Result:
      **regime-conditional, NOT ratio-dependent** → 0 on day-list (monotonic decline; optimum is the term
      switched off = natural boundary), **8 on stream** (clean interior peak, both neighbours resolvably
      lower: 8vs4 t=+2.69, 12vs8 t=−2.99). Shipped as `_SqWidePkRateAdaptive`.
- [x] **`W_SYNC` (AGV sync-up penalty)** — 72/72 cells, comb {0,0.15,0.3,0.5}, **34,560 runs**.
      **NULL** — no value beats the 0.3 default (pooled: 0→−0.38, 0.15→−0.03, 0.5→−0.30; all |t|<2).
      Killed the "W_SYNC=0 wins when pickers are abundant" hypothesis. Default kept, no base change.
      *Mechanism:* `my_wait` is already inside `finish` → already priced by the 1000-pt makeable/doomed
      tier; the explicit penalty is a 2nd invoice worth ~1–4 pts. It reorders only near-ties.
- [x] **`RATE_ALPHA` (picker distance sensitivity)** — DONE, 72/72 cells, 43,200 runs. Incumbent **5 CONFIRMED** (real bracketed curve peaking at 5; the early alpha=3 hint decayed +5.7 -> -1.27). Comb, comb {3,4,5,6,7}. Was the last knob never
      swept at grid scale (5.0 came from an early deployment-fleet-only sweep). Early hint: α=3 beat 5 by
      +5.7 (t=3.41) at stream 4×4 — **must pass split-half before it's believed**.
- [x] **`CONG_LAMBDA`, `CONG_WEIGHT`, `SEQ_DEPTH`** — DONE. Frozen at CONG_* 0.3, SEQ_DEPTH 5 (SEQ_DEPTH prediction held: it was the one with a real mechanism, -33.9 t=-28.7 off-optimum). All three defaults are already
      interior to their combs, so no extension needed unless a winner lands at a boundary.
      *Prediction on record:* CONG_LAMBDA/CONG_WEIGHT are additive score nudges in the same weak regime as
      W_SYNC → expect null. `SEQ_DEPTH` is the one with a real mechanism (it changes how many candidate
      futures the sequencer evaluates → alters the TIER classification itself, not just scores within it).
- [x] **`URG_S0` / `PK_URG_W` / `PK_URG_S0`** — DONE, ALL NULL (5 fleets x 120 seeds). URG_S0 40 holds. Finding inside the null: picker urgency is BIT-IDENTICAL at 4/8/16 -- a two-state switch (off/on), not a magnitude, because 86.9% of picker dispatches have a single candidate. S0 is the ramp shape (half the deadline knob);
      only worth tuning if the deadline term survives as load-bearing.
- [x] **DATA-HYGIENE FIX (paper-critical, cheap) — DONE.** Workload-matched: daylist(w0)-stream(w0) = +142.91 (54.9%, t=+60.8); daylist(w12)-stream(w12) = +135.47 (40.6%, t=+53.8). day-list and stream are **not workload-matched** —
      verified `daylist == stream(warm=0)` bit-identical, so the sole difference is stream's
      `seed_initial(n=12)` warm start (+25% orders, +33% value). Knob results are SAFE (paired within
      regime), but the **VoPI / perfect-foresight bound (day-list − stream) is contaminated by load, not
      pure information.** Fix = champion, both regimes, warm start matched, a few fleets × 120 seeds.
- **skip:** `FUTURE_WEIGHT` (layer-2 = documented null).
- [x] Scale/generalization sanity — DONE and STRENGTHENED: champion vs `cong_l2on`, 3 maps x 120 seeds, all four cells significant, and the advantage GROWS with map size (+3.5% medium -> +5.0% extralarge).
- [x] Assignment oracle ceiling — **+4.0%** at 8x6 day-list, and CONCENTRATED (3/12 seeds exactly optimal; seeds 3 and 11 give up 10-14%).
- [x] **Knob revalidation with disturbances AND battery on — DONE 2026-08-23** (the last deferred item).
  Full world (standard battery + multi-cell spills + reset-mode belief routing), champion vs +/- brackets
  on all four dispatch knobs, 24 paired seeds: ALL CONSTANTS HOLD (no bracket reaches |t|>=2; SEQ_DEPTH=5
  bracketed worse on BOTH sides; URG_W bit-identical = inert in this regime). M1 fully closed.
- **Done when:** a tuned, frozen champion + a small scale table; numbers in NOTES; every knob's map has a
  split-half verdict attached.
- **De-scope lever:** tuning IS coming back flat, as predicted (2 of 2 knobs so far: one regime rule, one
  null). If CONG/SEQ_DEPTH also land null, accept current knobs and move on — that's a clean paper result
  ("the decision layer is near-maxed") not a failure.

## M2 — Make the rumor map ACT (the core novelty)  (~1.5 wk)  ⟵ highest value
Turn disturbances on and let the belief map drive decisions.
- Wire rumor-map belief into Part A: **risk term** (step 5) + **`b_hard`** avoidance (step 4) → robots
  route around suspected-disturbed cells.
- **Part B interrupt tier:** abort/reroute a task mid-flight when its route's disturbance probability
  crosses threshold (the "one robot's pain → fleet knowledge" claim).
- **Done when:** with-map vs without-map ablation **under disturbances** (the central result) + rumor-map
  metrics (90/90 sensitivity/specificity, latency ≤15, calibration ±10%).
- **De-scope lever:** if acting-on-the-map is null, that itself is a paper result (honest negative) — cap
  effort at the ablation, don't chase.

## M3 — Part B charging + strandings=0 + Part C pre-positioning  (~1 wk)
Finish the battery half of Part B and the one genuinely novel decision extension.
- **Part B charge-as-prefix:** "charge then task" expressible; emergency battery tier → **strandings=0**.
- **Part C future-readiness — RESOLVED as a NULL on static demand (2026-07).** Pre-positioning / demand
  anticipation was tested exhaustively — SA5 (random draw), EV (mean-field + trust knob β), MCTS (K-sample
  ± urgency) — all **wash-to-negative** at 120 seeds. The honest clock + reactive re-planning already
  capture it, bursts are rare/short, and picker capacity caps what being-ready can clear. **On the current
  STATIC-hotspot demand, anticipation is dead.** The only version with a chance is drift-gated → see **M3b**.
- **Done when:** strandings=0 verified (the surviving Part-B piece); Part-C anticipation documented as a null.

## M3b — CUT 2026-08-23 by its own gate: anticipation is flat even under REAL-calibrated drift
**Gate probe (exp_drift_vopi.py):** drift calibrated from the real Instacart sample
(data/instacart/, 30,121 item-lines; 3 zone-groups, 11-17% share swings/day, produce-morning /
snacks-afternoon), wired into DemandModel (opt-in `drift=`). VoPI re-test, 8x8, exogenous:
block 1 (48 seeds) W=25 +4.63 (t=+0.91, deepen band); DISJOINT block 2 (96 seeds) -5.28
(t=-1.19). POOLED: -1.98, z=-0.45 -> FLAT. W=999 -2.22 (flat). The premise (a moving hotspot
makes anticipation pay) is dead at real drift magnitude -- the fourth independent leg of the
anticipation null. Staging never built, per the gate design. Original plan below for context.

## ~~M3b — (GATED, evidence-backed) spatial-temporal demand DRIFT + adaptive picker staging~~  (~1.5 wk)
Anticipation is a null on STATIC demand (M3). It can only pay off if the demand hotspot **moves** — which
real warehouses genuinely exhibit: they re-slot high-demand SKUs **hourly** as demand shifts by
hour/season/promotion (evidence + sources in NOTES 2026-07-28). Two gated pieces:
1. **Demand-model upgrade — calibrate DRIFT from a REAL dataset.** Make the hot centers in
   `wwm_sim/demand.py` drift over the day (diurnal zone rotation), calibrated from the **Instacart Market
   Basket** dataset (~3M orders, hour-of-day × department/aisle popularity → map department→zone; the key
   signal = does the hot mix shift by hour). ADDITIVE scenario — does NOT invalidate static-demand M1/M2
   (drift changes *where* work is, not *how* to rank/route it).
   **KEEP THE TIME LAYOUT — do NOT re-section time.** Map the 24-hour Instacart profile onto the existing
   diurnal *phase* (period≈250): make `popularity(zone)` a function of `phase(t)`, the same phase that
   already drives the rate. Fit a SMOOTH curve (few Fourier terms / interpolate the 24 points) evaluated at
   continuous phase — the 24 hours are calibration data, never sim structure (avoids the ~10.4-steps/hour
   ugliness). Only change: `wt` static → phase-dependent. Episode length, period, timestep meaning unchanged.
2. **Recency-based adaptive staging.** Windowed empirical estimate of *where demand is heading* (last X
   steps of observed order locations) → facility-location (k-means over the windowed density, k = idle
   pickers) → stage idle pickers **ahead** of the drifting hotspot. Competes with "serve nearest AGV now."
- **Done when:** drift model calibrated from Instacart + staging ablation on the DRIFTING-demand stream vs champion.
- **Why it's the good version:** rides the *predictable* (spatial-trend) part of demand, ignores the
  *unpredictable* (exact timing); on a shifting warehouse it's where "adaptive world model tracks moving
  demand" finally has teeth — a genuinely novel contribution vs the static-demand null.
- **De-scope lever:** skip unless the shifting-demand narrative is wanted for the paper — the static-demand
  finding (anticipation is dead) stands on its own.

## M3c — CUT 2026-08-24 by its own gate: headroom is 2.4%, under the ship bar
**Probe (exp_m3c_headroom.py, 24 stream seeds):** trace every pickup back to the AGV's preceding
idle period; idle-approach travel = the ONLY thing pre-positioning could eliminate. Measured:
95 steps/day = 2.38% of the AGV step-budget (2.6 steps per pickup; 94% of pickups follow an
idle) -- and that is the TELEPORTATION ceiling; a real policy recovers a fraction. Why so small:
an AGV idles where its last delivery ended, near stations/hot racks -- finishing a task IS
pre-positioning. Never built, per the gate design.

## ~~M3c — (GATED, headroom-measured) IDLE-AGV pre-positioning on the stream~~  (~0.5–1 wk)
User idea (2026-07-30): when **AGVs outnumber the available tasks**, the marginal decision is no longer
*which task* but *where should a spare robot wait*. Every prior anticipation arm (SA5 / EV / MCTS) fed
forecasts into TASK CHOICE — and in the stream there is nearly always a task to choose, so the forecast
never changed an action. That is very likely *why* they were all null. This aims the same estimator at a
decision that actually exists.

**Headroom MEASURED first (6 seeds, champion) — % of steps with free AGVs > available tasks:**
| fleet | day-list | stream | avg surplus (stream) |
|---|---|---|---|
| 4×4 | 11% | **0%** | 0.0 |
| 6×6 | 35% | **3%** | 0.9 |
| 8×8 | 52% | **20%** | 1.7 |
| 9×4 | 45% | **8%** | 1.0 |
| 4×9 | 9% | **0%** | 0.0 |

**The key asymmetry:** day-list has abundant idle time but *nothing to anticipate* (all orders known at
t=0; `step()` is a no-op — robots are idle there because the work is FINISHED). Stream is where future
demand exists and is exactly where spare robots are rare. **Addressable window = stream, AGV-rich fleets
(~8×8): 20% of steps, ~1.7 spare AGVs.** Narrow but non-zero.

**NOT MCTS.** Tree search over action sequences is the wrong tool (and already proven not to pay). The
decision is an assignment against a predicted field. Build:
1. **Trigger/guard:** fire only when `free AGVs > available unassigned tasks` (inert 80–100% of the time).
2. **Field:** decayed histogram of recent order locations per region — the empirical averager (NO reading
   true demand params). Reuse `_SqWidePkRateEV`'s hot-cell machinery — the estimator already exists.
3. **Action:** send each spare AGV to the legal waiting cell minimising expected time-to-next-task, spread
   across hot regions so they don't stack.
4. **Metric:** on-time value, stream only, AGV-rich fleets. Compare vs champion (spare robots hold position).
- **Knob impact — VALIDATION, not a re-tune.** Staging fires only when a robot has NO task, so it never
  touches the task-ranking score (URG_W / W_SYNC / RATE_ALPHA / CONG live there). But it moves robots, which
  shifts travel→finish estimates. Re-check `URG_W`(stream) + `RATE_ALPHA` on 2–3 AGV-rich fleets with
  staging on; re-sweep ONLY a knob whose peak actually moves.
- **Done when:** staging ablation on the stream in the AGV-rich corner + the knob-stability check.
- **Expectation on record:** small positive at best, confined to AGV-rich stream; quite possibly another
  null — but unlike M3's arms, the mechanism targets a decision that exists.
- **De-scope lever:** the 0–8% headroom outside 8×8 caps this hard. If the 8×8 stream ablation is flat, cut
  it and report the headroom table as the reason — that's a cleaner negative than the M3 arms gave us.

## M4 — CLOSED 2026-08-24: the last learned head CUT by its own gate; the EMA stands
**Three-way gate (exp_m4_pace.py, 24 seeds, held-out test):** zero-correction MAE 31.3 / EMA
23.5 (the incumbent earns its keep) / LightGBM head 19.8 (+15.4%, but calibration slope 0.43)
/ sim-pace fork arm 22.3 (+4.8%). Linear recalibration fitted on train made TEST WORSE (+7.8%,
slope still 0.33) -- the edge does not transfer. CONFIRMED AT FULL SCALE (144 seeds, 96/48
train/test): head +13.5% (below the bar) with slope 0.14 -- more data made calibration WORSE,
proving the miscalibration structural. GATE FAIL -> EMA stays. HEADLINE FINDING: the
EMA's calibration slope is NEGATIVE (-0.23) -- pace prediction is ENDOGENOUS to control (a high
prediction triggers conservative behavior that falsifies it), which is exactly why offline heads
cannot cleanly beat an in-the-loop formula. Original plan below.

## ~~M4 — Stage 3: the pace model (the one learned head)~~  (~1 wk)
The only Stage-3 head aimed at a proven-valuable quantity (live calibration was +6.9).
- Train the fleet-level **pace model** (LightGBM, state-conditional day-pacing) as successor to the flat
  delay-EMA; pass the **calibration gate**; ship only if **≥15% better than the formula AND calibrated**.
- **Done when:** pace model shipped-or-cut by the gate; the "improves with use" claim demonstrated or
  honestly cut.
- **De-scope lever:** if it fails the gate (plausible), keep the live-EMA and report the head as cut —
  still a clean Stage-3 story.

## M5 — Full evaluation + benchmarks + ablation table  (~1 wk)
Assemble the credibility layer (much tooling already exists).
- Complete the **metric suite** (§5): throughput, deadline-hit-rate, tardiness (mean+p95), energy/task,
  strandings=0, collisions=0, replans/disturbance.
- **TA-RWARE head-to-head** (≥ FIFO clean, target +10% under disturbances).
- **MovingAI MAPF inner-loop** sanity (≥98%) — plumbing validation only.
- **Consolidated ablation table** — every mechanism ≥3% or cut; document that **joint-first-moves/full
  Part D are null** (the sequencer's prioritized-greedy already ≈ joint) and **ADG** gives 0-collisions
  by construction (toy-demo'd) while the env already hits 0 empirically.
- **Done when:** every headline number for the paper is locked, on the tuned champion.
- **De-scope lever:** drop Lifelong-MAPF and Gazebo battery calibration (nice-to-have, not core).

## M6 — Write the paper  (~1.5 wk)
- Finish `docs/PAPER_DRAFT.md`: positioning (from the deep-research), method (known-rules world model =
  rollout + heads + rumor map; sequencer; value-rate pickers), results (M1–M5), the **honest negatives**
  (delay unpredictable; decision layer near-maxed; stream gap is picker *capacity* not assignment;
  layer-2/joint null), limitations, future work.
- Figures: stream_stack, picker_ceiling, oracle_gap, rumor-map reliability diagram, the ablation table.
- **Done when:** a complete, submittable draft with all figures.

## Buffer  (~0.5 wk before target)
Overrun slack, a second paper pass, recovery from any failed experiment.

---

## Explicitly CUT / OPTIONAL (to protect the timeline)
- **Full Part D** joint combo-optimization + LNS — null on value; documented, not built.
- **Full ADG integration** (Part D deconfliction + pick/deliver in ADG mode) — toy-demo suffices; empirical
  collisions already 0. Future work.
- **GATv2** graph encoder (Stage 4) — explicitly optional; only if hand features plateau (they haven't).
- **Lifelong-MAPF benchmark, Gazebo calibration, THUD++/JRDB** human-motion tuning — stretch only.

## Risk notes
- M2/M3 are new code that may come up null (like this session's picker experiments). That's fine —
  honest ablations are paper content, not failure. Cap effort with the de-scope levers.
- Biggest schedule risk is M2 (rumor map acting). If it slips, pull the buffer forward and compress M5.
