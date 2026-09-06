# TODO — what's LEFT

Clean working list. **Only remaining work.** Everything finished lives in `STAGE_CHECKLIST.md`
(full history + why) and `NOTES.md` (results). Ordered by `ROADMAP.md` milestones.

**Built and frozen — do not re-open:** simulator, Part A funnel + congestion map, rollout engine
(Yen k-routes, partner ETA, sync wait, return-to-free, battery-floor filter), sequencer, value-rate
pickers, state assembler, demand model, deadlines/values/hardness, rumor map (built, inert), ADG
(toy-demo'd), ablation + oracle harness, knob-sweep infrastructure.

**Closed as nulls — documented, not to be retried:** delay prediction (5 nulls + oracle), layer-2 /
joint first moves, full Part D, anticipation on static demand (SA5 / EV / MCTS), `W_SYNC` tuning.

---

## ~~M1 — Lock the decision core~~  ·  **CLOSED 2026-08-02 — TABLE FROZEN**
**`URG_W` 0 day-list / 8 stream · `W_SYNC` 0.3 · `RATE_ALPHA` 5 · `SEQ_DEPTH` 5 · `CONG_*` 0.3 ·
`LOAD_TIME` 5.** Verified under exogenous (fully-paired) demand on stream — the only regime the
endogenous-demand bug ever touched; day-list generates all orders at t=0 before any robot moves, so it
was always policy-independent. No alternative won any contest. Everything below is history.

<details><summary>M1 detail (kept for the paper)</summary>
- [x] `RATE_ALPHA` — 72 cells, comb {3,4,5,6,7}. **α=5 confirmed both regimes**, every alternative
      negative, bracketed peak. No champion change.
- [x] `SEQ_DEPTH` — 36/36 both regimes. **Day-list: 5 best**, monotonic (depth 1 = −9.8, t=−22.5),
      100% stability. **Stream: depths 3/5/8 bit-identical** (imagined queue empties before the horizon
      binds) **but switching the sequencer OFF costs −24.05 (−7.2%, t=−30.6)** — the largest mechanism
      effect in M1. Inert depth ≠ inert mechanism.
- [x] `CONG_LAMBDA` / `CONG_WEIGHT` — **skipped by design** (spatial knobs → predicted regime-invariant
      and null by the space-vs-future principle; not worth ~30 hr to confirm a third time).
- [x] **Foresight-window sweep — DONE. There is NO useful prediction horizon.** W=10 → −0.10 (t=−0.07,
      exactly zero); then monotonic decline: W=25 −1.65, W=50 −3.91, W=100 −5.32, W=999 −11.23
      (t=−5.98). A *perfect* 10-step forecast is worth nothing; damage scales with reach.
      => the anticipation chapter now rests on three independent legs: every estimator was null,
      perfect information is negative, and no horizon pays.
- [x] **ROLLOUT FIDELITY — closed 2026-08-02, group killed by its cheapest member.**
      The imagination really was wrong: the pinned first move consumed **no picker** (`jj = None`), so
      every imagined task believed all pickers were free — optimistic by exactly one picker, whole
      horizon, every branch, on the binding resource. Corroborated: 26.1% of rendezvous a picker
      evaluates are doomed, i.e. the AGV's average-picker "makeable" verdict is wrong ~1/4 of the time.
      **Fixing it bought nothing**: day-list +1.48 (t=1.81, CI [−0.12,+3.07]), stream −0.31 (t=−0.21,
      W/L 322/319). Arm verified live (24/24 seeds differ), so this is a real null.
      => `URG_W` needs no re-validation; **the knob table stands as swept**.
      => closes unbuilt, by gating: matched-picker `partner_eta`, adaptive delay pad, contention-aware
      funnel tier — all would supply *worse* information than the arm that just failed.
- [ ] *(demoted to a methods note)* Re-validate shipped knobs under `exogenous=True` (~6,000 runs).
      Would confirm, not correct — the effects at stake are t=−16.7 and t=−30.6, and partial pairing
      cannot flip results of that size. State the caveat in the paper instead of spending the compute.
- [ ] Apply split-half test to each finished knob; attach the verdict to its heatmap
- [x] **VoPI — DONE 2026-08-01, and it is a headline result.** Three findings:
      (a) the documented day-list − stream figure was wrong by 2x (+70 → +143 once workload-matched);
      (b) that gap is **capacity, not knowledge** — day-list can *serve* orders early, which no
          forecast can grant — so it was never a valid information bound;
      (c) the real test (stream physics, genuine future in the rollout, exogenous demand):
          **−11.23, −3.43%, t=−5.98** — perfect demand information is HARMFUL, in all six fleets.
      => the SA5/EV/MCTS nulls are explained: an oracle loses, so no estimator can win.
- [x] **Simulator fix — demand was endogenous to the policy** (`_inject` skipped in-transit shelves →
      only 22% of orders matched between two policies on the same seed). Added opt-in
      `DemandModel(exogenous=True)`; legacy path verified unchanged. Note in the paper's methods that
      pre-fix comparisons are *partially* paired (same counts/times, different shelf identities).
- [ ] Freeze the champion; write the final knob table
- [ ] Scale/generalization: champion vs `cong_l2on` at 2–3 other fleet/map sizes
- [ ] *(deferred, only if the deadline term stays load-bearing)* `URG_S0`, `PK_URG_W`, `PK_URG_S0`

## ~~Part D — windowed joint first moves~~  ·  **CLOSED AND DELETED 2026-08-02**
Code removed (`_SqWidePkRateJoint*` classes, `scripts/exp_joint.py`). Result kept as a documented
negative — `results/joint_partd.csv` and the NOTES entry are the evidence.
**Why cut:** no headroom in any form. 720 paired runs per cell: W=10 ≈ 0 (t=−1.16 / −1.55), then
monotonically harmful (W=30: −6.91 t=−10.79 day-list, −5.81 t=−4.43 stream). The mechanism only has
**~10 eligible decisions per 500-step episode** anyway (`_pick_winner` fires 17×, 7 at t=0 with nothing
busy to pair). And the reason it can't win is structural: **the rollout already co-decides the partner
inside every branch**, so joint optimisation adds no information — it only hardens an assumption that
evaporates when the partner re-decides on freeing. The binding variant was never validly tested (it
came back bit-identical to its parent), but the non-binding evidence is sufficient to close it.
*Retained from the work: `_sim_core` pins may now carry an optional 5th element (a pinned robot's free
time), which is backward-compatible and useful for any future multi-robot branch.*

<details><summary>original entry (kept for context)</summary>
The old "joint simultaneously-free robots" null had a specific cause, now measured precisely:
`_pick_winner` fires only **17× per 500-step episode** (7 at t=0 with nothing busy to pair), and partner
free-gaps are 6–33 steps. So W=5 literally cannot fire; there are only ~10 joint-eligible decisions
in a whole day. Built `_SqWidePkRateJoint` (W10/W20/W30) + an optional 5th pin element carrying the
partner's free time so a busy partner isn't evaluated as if free now.
- [x] **Full run DONE — no headroom.** 720 paired runs per cell:
      day-list W10 −0.59 (t=−1.16) · W20 −4.71 (t=−7.18) · W30 −6.91 (t=−10.79)
      stream   W10 −1.62 (t=−1.55) · W20 −5.48 (t=−4.20) · W30 −5.81 (t=−4.43)
      Zero at W=10, monotonically harmful beyond. *Why:* the rollout already co-decides the partner in
      every branch, so joint optimisation only hardens an assumption that evaporates when B re-decides.
- [ ] **Binding variant — STILL UNTESTED.** The run completed but produced output *bit-identical* to
      `joint_w20` (−4.71/−5.48, same t) → the reservation never fired. Cause: hooked `_task_order()`,
      but the champion's funnel iterates `finalists` from the cheap screen (sim_priority.py:455) and
      never calls it. **Do not quote its number — it is the parent arm's.**
      Correct hook = filter the screen's `finalists`, or the queue feeding it.
      *(Third silently-inert arm this session. Earlier two: the partner filter excluded `assigned_agvs`
      — every robot actually executing a mission, i.e. exactly the ones about to free; and reservations
      written into `assigned_items` clobbered the partner's current task. **Standing rule: before
      believing any new arm's null, verify it differs from its parent on some seeds.**)*
</details>

## Deferred commitment — **STRUCTURALLY DEAD, closed 2026-08-02 without a full run**
Idea: leave a task unassigned when a robot freeing soon would do it much better. Measured before
spending 120 seeds on it, and the gate can never open:
- **`theirs − mine` never exceeds 8.0** (309 assignments; median 0.0, p90 5.4, max 8.0). Both robots
  compete for the *same task*, so both get the same `1000 + v` — the only difference possible is the
  urgency term, capped at `URG_W`=8. A margin of 50 or 250 is unreachable by construction.
- **The sign is backwards.** The 28.8% of positive gaps are positive *because the later robot has less
  slack*, so urgency rewards it for being nearer its deadline. Not a reason to wait for it.
- **`min = −1021`** — a tier flip the other way; deferring there loses the task outright.
- Root cause: `t_free` has a **floor of ~6, median 28**, against grid distances of 15–30. Freeing later
  almost always means finishing later; position can't outrun the time penalty.
*(First draft also used `DEFER_W`=10, below the ~6 floor's practical reach — only 8.8% of busy robots.
Same class of error as Part D's W=5. Windows recalibrated to 30/60 before concluding.)*
- [ ] Once binding lands: write Part D up as a **documented negative** for M5's ablation table.

</details>

## Fleet ratio — NEW, and the largest actionable finding in the project (2026-08-04)
From the 72-cell grid at shipped `URG_W`, stream on-time value:
`8×4 = 341` · **`8×6 = 366`** · `8×8 = 361` · `9×7 = 366`
- **+25 (+7.3%) from 8×4 → 8×6** — three times the biggest decision-layer effect, and it costs two robots.
- **8×6 beats 8×8 with two FEWER robots.** Pickers past ~6 don't just stop helping, they cost (−0.9/picker
  at 8×8), and the constraint hands back to AGVs (+5.7/AGV at 8×8).
- Optimum is ~**4 AGVs : 3 pickers**, not 2:1. Day-list agrees more mildly (peak 8×7 = 423).
- Reframes the free-picker ceiling: "+11–22 if pickers were free" is real at 8×4, but the fix is **two**
  more pickers, not unlimited ones.
- [ ] Write up as an M5 result — data already banked, zero new compute.
- [ ] Decide whether the deployment fleet should change from 8×4.

## Value-loss ledger (keep current — where the money actually goes)
Base accounting = 2026-07-23 per-order autopsy (10 seeds, day-list 8x4): banked on time 384 (**91%**) |
doomed from start 0 (0%) | **missed at the cliff 30 (7%)** | **never served 10 (2%)**.
Cliff loss splits **75% PICKER WAIT / 25% traffic / 0% dock queue**. Never-served is NOT junk (high and
mid tiers ~4/day each, low ~2) — the capacity limit drops valuable orders too.

| cause | size | status |
|---|---|---|
| **picker-wait cliff** | **dominant (75% of cliff loss)** | THE leak. No controller change moves it — only fleet composition. |
| fleet ratio misallocation | **+8.4% on STREAM** (4->6 pickers, t=+6.09) | REVISED 2026-08-05 under the self-loop fix: a PLATEAU with a knee at ~6, not a peak. "8x6 beats 8x8" REFUTED (t=+0.25 / -0.90). **Day-list is FLAT across 4..9 (+0.6%, null)** — the effect is stream-only. |
| movement-referee silencing (was "deadlock / circular waits") | +0.65% value, collisions -87%, freezes 50->27 | **RESOLVED 2026-08-05.** Root cause = self-loops in `resolve_move_conflict`'s graph: a stationary agent made `find_cycle` report a cycle, so `dag_longest_path` never ran and every moving agent in that component was NOOPed. FIXED + verified (t=+3.02, stability 99% pooled). This was the THIRD of the three candidates the old entry listed (the env's own collision filter) — not TOGGLE_LOAD, not a stale path. |
| never-served tasks | ~8-10 | known; capacity/sequencing |
| traffic | ~7 (25% of cliff loss) | known; the map governs only this slice |
| assignment order (vs hindsight oracle) | was +4.0% at 8x6 day-list | **RE-MEASURING 2026-08-05** — the +4.0% predates the self-loop fix and is capacity-dependent, i.e. exactly the kind of number that already moved twice today. |
| doomed tasks | 0 | handled by the tier (and the tier itself is decorative — `gap_0` is null) |
| residual freezes | 27 remain (down from 50) | **OPEN** — a second source, not yet traced |

### Execution-layer priority: CLOSED, all negative (2026-08-05, ~4,800 runs)
yield by value -5.71 (t-5.06) | yield by deadline -6.45 (t-5.40) | arbitrary control -1.47 (t-1.44) |
prioritized reroute (both replan, utility order) -20% smoke. The ranking-free control is the LEAST bad.
Mechanism = starvation (static priority without inheritance); and after the self-loop fix collisions are
~0, so a collision-arbitration component has nothing left to arbitrate. Do not revisit without aging
(PIBT's `eta` = time since last goal) as the primary key.

## M2 — Make the rumor map ACT  ⟵ CLOSED 2026-08-23 (full clause accounting in NOTES)
The central novelty. Everything above is polish by comparison.
- [x] Wire belief into Part A: risk term (step 5) + `b_hard` avoidance (step 4)
      — `b_hard` shipped and load-bearing; risk term built (`belief_risk_w`) and proven
      null-by-construction: the shipped reset-mode map has NO sub-threshold gray zone to price
      (0 cell-steps/day). Flag-gated off.
- [x] Part B interrupt tier: abort/reroute mid-flight when route disturbance probability crosses threshold
      — delivered functionally: routes replan continuously against the live map (one robot's
      hit → fleet reroutes; hits 236→80). NOT built as a distinct abort mechanism — absorbed.
- [x] With-map vs without-map ablation **under disturbances** (the headline result)
      — exceeded: blind/belief/clairvoyant across five regimes; phase boundary (harmful z=−2.2 ↔
      valuable z=+2.8); capture arc 38%→83% of clairvoyant VoPI (reset map, t=+4.05).
- [x] Rumor-map metrics: 90/90 sensitivity/specificity, latency ≤15, calibration ±10%
      — specificity PASS (95%+); calibration PASS in the decision bins (seen-dirty +2.1pp,
      seen-clean −4.0pp; ~96% of mass), structurally overconfident at the idle prior (chosen
      trade — base-rate prior = beta-mountain = slow detection); sensitivity 84.7% vs spec 90:
      **spec physically unattainable** — sensing ceiling is 84.9% at radius-5 occluded sight
      (we sit at 99.8% of it; spec predates the occlusion model); latency 19 vs ≤15 (was 59;
      remainder is the same physics).
- [CUT 2026-08-23] Add `belief` fields to the state assembler once the map drives decisions
      — cut (user): NOTHING SHIPPED uses learned heads. delay_head=None in the champion; only
      the experimental congestion arms (which the champion beat) ever load one. Feature columns
      for a consumer that lost its audition are dead plumbing, not a milestone step.

## M3 — Part B charging  ⟵ CLOSED 2026-08-20 (roadmap done-when met)
- [x] Charge-as-prefix: "charge then task" expressible in a plan
      — absorbed: CHARGING missions + charge-to-need + early release deliver charge-then-resume
      without a distinct plan-prefix formalism (same category as M2's interrupt tier).
- [x] Emergency battery tier → **strandings = 0** verified
      — funnel filter + emergency pod-drop + hard-dead gate + picker action-layer enforcement;
      frozen 0/144 AND stranded 0/144 audited per-instance at standard compression (m3mpc
      784.49, +0.1% vs nobat). ASTERISK: stress days (5× drain + low starts) are best-effort
      for BOTH arms by design (user 2026-08-23) — zero is earned, not scripted, there.
- [CUT 2026-08-23] Add `battery` fields to the state assembler
      — cut (user), same reason as M2's belief fields: no shipped consumer for learned-head
      features exists.

## M3b — (GATED, BAR RAISED) demand DRIFT + adaptive picker staging
⚠️ 2026-08-01: perfect demand information is **negative** (−3.4%) on STATIC demand. This milestone's
premise — that anticipation pays once hotspots move — is now the *only* thing keeping it alive, and it
is untested. Before building the Instacart calibration, run the cheap version of the question: does the
VoPI ceiling turn positive under drifting demand? If not, cut the milestone.
Only if the shifting-demand narrative is wanted. Static-demand null stands alone.
- [ ] Calibrate drift from Instacart (hour-of-day × department → zone), map onto the existing diurnal
      phase — keep the time layout, smooth curve, `wt` static → phase-dependent
- [ ] Recency-based picker staging (k-means over windowed density, k = idle pickers)
- [ ] Ablation on drifting-demand stream vs champion

## M3c — (GATED, BAR RAISED) idle-AGV pre-positioning
Headroom measured: stream only, AGV-rich fleets (~20% of steps at 8×8, 0–8% elsewhere). Not MCTS.
⚠️ 2026-08-01: survives the VoPI result only because it acts through a DIFFERENT CHANNEL — *where a
spare robot waits*, not *which task to take*. Note the awkward overlap though: VoPI damage is smallest
in exactly the AGV-rich fleets where this has headroom (9×9 −1.0%, 8×8 −1.9%), so the two findings
point at the same corner from opposite directions. Test the guard-and-stage arm directly; do not
assume the channel distinction saves it.
- [ ] Trigger guard: fire only when `free AGVs > available tasks`
- [ ] Density field: decayed histogram of recent order locations (reuse `_SqWidePkRateEV` machinery)
- [ ] Stage spare AGVs to minimise expected time-to-next-task, spread across hot regions
- [ ] Ablation on stream, AGV-rich fleets
- [ ] Knob-stability check (NOT a re-tune): re-verify `URG_W`(stream) + `RATE_ALPHA` peaks don't move

## M4 — Pace model (the one learned head)
- [ ] Train fleet-level pace model (LightGBM, state-conditional day-pacing)
- [ ] Calibration gate: ship only if ≥15% better than the formula AND calibrated — else report as cut

## M5 — Evaluation + benchmarks  ⟵ CLOSED 2026-08-24 (roadmap done-when met)
- [x] Metric suite: throughput, deadline-hit-rate, tardiness (mean + p95), energy/task, strandings,
      collisions, replans/disturbance — all seven measured, none assumed
- [x] TA-RWARE head-to-head (≥ FIFO clean; target +10% under disturbances) — cleared 3–6× over
- [x] MovingAI MAPF inner-loop sanity (≥98%) — 100% solved
- [x] Consolidated ablation table — every mechanism ≥3% or cut → `docs/ABLATION.md`, 10 shipped / 21 cut
- [x] Lock every headline number on the frozen champion — done for the champion; the *tuner* numbers
      move if the 200-step horizon is adopted (see "Tune later"), so those are quoted at 50/100

## M5 — Evaluation (IN PROGRESS 2026-08-24)
- [x] Safety metrics MEASURED (exp_m5_safety.py): 0 vertex + 0 swap collisions for all 4 arms
      across 48 seeds x 500 steps (the `collisions=0` column in the first bench table was a
      placeholder reading a nonexistent attribute -- caught and replaced). Replans/spill 9.0
      (fifo) -> 14.3 (champ), the roadmap's missing replans-per-disturbance metric.
- [x] Metric suite + benchmark table: 1152 runs (fifo/rush/champ/mpc x wave/stream x 144 seeds),
      results/m5_bench.csv. Champion +21.1% over FIFO (wave), +48.9% (stream); 0 stranded in all
      1152; MPC +0.5% wave (t=+2.41) / +1.7% stream (t=+1.90).
- [x] TA-RWARE head-to-head UNDER DISTURBANCES (the roadmap's stated target) -- DONE, 1152 runs,
      results/m5_bench_disturb.csv. Champion +31.6% wave (t=10.95) / +62.3% stream (t=11.81) over
      the vendored FIFO -- the ">=FIFO clean, +10% under disturbances" bar cleared 3-6x. Margins
      are LARGER than on clean floors. New finding: the tuner goes quiet under hazard noise
      (+0.0% / +0.2%, t<0.3) and correctly abstains.
- [x] MovingAI MAPF inner-loop sanity -- PASS: 1800 benchmark cases, 100% solved (bar 98%);
      100% optimal on the warehouse + empty maps, 91% on random clutter (+0.22 steps mean,
      a loose pyastar2d heuristic for 4-connected moves; no effect on aisle layouts)
- [x] Consolidated ablation table (every mechanism >=3% or cut; incl. this week's negatives)
      -- docs/ABLATION.md, ten shipped / twenty-one cut; rendered as results/fig_ablation.png
- [x] **CLOSED 2026-09-06: seed 125 stream freezes 2 carriers.** Root cause was NOT the layout
      constant. `_recalc_grid()` runs at the end of every step and rebuilt the SHELVES layer from
      `env.shelfs`, silently restoring pods that `setup_bays` had stripped -- so the USER RULE
      2026-08-14 "charger cells have no shelf" was inert during every run ever measured, and the
      floor carried 180 pods for 175 legal drop cells (NEGATIVE slack, not zero). Fixed with an
      `env._removed_shelf_ids` set honoured by `_recalc_grid` (env.shelfs untouched, because
      `shelfs[id-1]` indexing is pervasive). See exp_spare_slots.py for the paired re-measurement
      and the extra-slack sweep on top of it.

## M6 — Paper  (IN PROGRESS 2026-09-06)
- [x] `PAPER_DRAFT.md`: positioning (§2 written properly, no longer a pointer to the pre-realism
      draft), method, results through §5.26, honest negatives, limitations, future work
- [x] **VoPI-gated arguments fixed.** The line refs were stale (they pointed into the pre-realism
      draft). The current draft never re-derives the invalid bound; two standing methods guards were
      added to the §5 preamble instead: (a) the day-list − stream gap is CAPACITY, not information,
      and is never a VoPI bound; (b) comparisons predating `exogenous=True` are only partially paired.
- [x] References section added (§9) — verified classics separated from the 2026-07-16 literature
      pass, whose identifiers still need re-checking before submission
- [x] Figures — **the roadmap's list was stale**: `stream_stack`, `picker_ceiling` and `oracle_gap`
      were rendered in July 2026, BEFORE the realism audit, on a world ~3× too productive. They must
      not be cited. Replaced by `scripts/make_paper_figures.py`, which regenerates a validated
      eight-figure set from current data (see §4b of the draft).
- [ ] Assemble to a submittable format (LaTeX/PDF) and re-verify the §2 citation identifiers
- [ ] Abstract is written but marked "write last" — re-read once the draft stops moving

---

## Tune later (user 2026-08-23)
- [x] **MPC cadence/horizon sweep -- CLOSED 2026-09-06. 100/200 ADOPTED.** Stress days: 50/200 best
      absolute (+96.7, t=+5.86); 100/200 best per unit compute (+75.3, t=+5.07, same fork budget as
      the shipped 50/100 which scores +57.6). Ordinary-day re-check (48 paired seeds each) came back
      a TIE at identical compute -- wave 100/200 +8.60 (t=2.08) vs shipped +8.86 (t=2.14); stream
      +2.47 (t=0.20) vs +4.43 (t=0.44), both inside noise. Nothing regresses, so the change is free:
      neutral where it is not needed, +17.8 and strandings 95->63 where it is.
- [x] **Threshold OSCILLATION built and gated (2026-09-06).** exp_theta_oscillation.py. Stress days:
      osc alone +63.2 (matching the ENTIRE tuner, +57.6, at identical mean theta); tuner+osc +91.2
      (t=+3.81, i.e. +33.6 ON TOP of the tuner -- a genuinely new axis). Ordinary days: -13.2 alone,
      -3.7 with the tuner, and it ERASES the tuner's +8.9. Mechanism: 0 stranded in every ordinary
      arm, so the safety is worthless and the extra trips are pure cost. VERDICT: never a default;
      it belongs in the tuner's MOVE SET, adopted only where it pays. Not yet wired into m3_mpc.py.
- [x] **Full benchmark re-measurement (2026-09-06)**, both tables, 2304 runs, after finding that
      results/m5_bench.csv predated a 2026-08-25 simulator change. Wave bit-identical in both; every
      live-stream value rose. Margins: +21.1% / +47.5% clean, +31.6% / +60.4% disturbed. One claim
      corrected -- the tuner is NOT quiet under all noise: +3.2% (t=3.62) on live-stream with spills.
      STANDING RULE ADDED: re-run the benchmark after any simulator change.
- [ ] ~~MPC cadence/horizon sweep~~: the 50-step replan interval and 100-step rollout horizon were
  DESIGNED, never tuned (the campaign tuned the knob values inside settings, not the meta-loop).
  Sweep e.g. 25/50, 50/100, 50/200, 100/200 on stress cells where the tuner's edge is visible;
  check whether 50/100 sits on a plateau like the dispatch weights did.

## Deferred with reasons (2026-09-06)
- [ ] **Wire oscillation into `m3_mpc.py` as a move** (`osc+` / `osc-` on a 10th setting field).
      Measured and gated above; the remaining work is plumbing plus a re-run of the campaign.
- [ ] **Port the swap family to stock TA-RWARE.** Must be an ADAPTER over the unmodified vendored
      package, never a patch to it -- the head-to-head's whole value rests on the baseline being
      untouched. Multi-hour build whose failure mode is a subtly different env that silently
      invalidates the comparison; wants a fresh session and a parity check against our fork.
- [ ] **Idle-picker yield.** Every liveness rule that shipped works by GATING a move an agent already
      requested; a yield rule is the first that must SYNTHESISE one, i.e. write into the referee's
      path/action state rather than filter it. Materially riskier class of change, and the residual
      it targets is one 92-step wait per 144 episodes -- it does not clear the project's own
      "at 1-in-144 rarity a fix must beat the cost of re-verifying" bar.
- [ ] **Bays non-targetable at the env level.** Prerequisite for ever making the "charger cells carry
      no pod" rule real: today an occupied cell is the only thing hiding a bay from a controller's
      empty-slot search, and only our controller knows about `charger_keepout` (see NOTES 2026-09-06).

## Parked / optional (protect the timeline)
- [ ] Optuna tuning of `importance_*` vs throughput/tardiness/strandings — blocked behind M2
- [ ] Safety split (emergency filter vs tradeable discomfort)
- [ ] Curiosity taper + scout dedup
- [ ] Full ADG integration + Part D deconfliction — toy-demo suffices; empirical collisions already 0
- [ ] GATv2 encoder — only if hand features plateau (they haven't)
- [ ] Lifelong-MAPF benchmark, Gazebo calibration, THUD++/JRDB — stretch only

## Standing method rules
120-seed rule · two instruments (t + sign) · one mechanism at a time · ≥3%-or-cut · validate in the
deployment regime · **pooled paired tests are confirmatory, per-cell argmax maps are exploratory**
(they fail split-half on every knob so far) · **bracket the optimum**, extend only at a boundary ·
deploy group-level rules, never per-cell bests.
