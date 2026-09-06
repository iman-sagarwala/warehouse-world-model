# Findings & Results Log

A running record of *observations* from running the sim, and whether each is
expected/correct and why. Separate from `NOTES.md` (which logs decisions and
understanding). Entries are dated; newest at the bottom.

---

## 2026-07-06 — FIFO vs. random, per-metric (tiny env, battery on, compressed)

Observed while watching the dashboard and running `scripts/verify_trials.py`
(seeds 0/1/2). Verdict on each metric:

### 10-trial FIFO-vs-random verification (CSV) — model structure CONFIRMED
`scripts/verify_10trials.py` → `results/fifo_vs_random_10trials.csv` (seeds 0-9).
ALL consistency checks pass. (a) Model-invariant (same both policies/all trials):
battery ratios charge:discharge=3.333, idle:drive=0.25, carry:drive=0.5,
pick:drive=0.3, drive-drain=0.00333/step, floor=0.10; movement 1 cell/step; fleet
3 AGV+2 pickers. (b) Differences: FIFO deliveries mean 20.3 (17-23) vs random 0.5
(0-2); stucks FIFO ~0.2 vs random ~31.6; reroutes both noisy (6-29 / 0-20); FIFO
pickers strand EVERY trial (busy, no charger reach) while random retains more
(idle) — end-batt similar ~29-30%; in_transit (picks-deliveries) 0-3 both →
consistency invariant holds. FIFO first_done = ordered pickups by nearest free
AGV; random barely completes. Caveat: random wobbles run-to-run (un-seeded action
sampling); FIFO deterministic. Verdict: structure correct.

### Throughput & Deliveries — FIFO always higher ✅ EXPECTED (and the point)
Throughput and Deliveries are the **same quantity** — throughput = deliveries ×
1000 / steps (a rate; deliveries is the raw count). So they always move together.
FIFO wins every seed (17–22 vs 0–1) because it completes the fetch→deliver→return
cycle; random almost never does. This is the core validation and our §6.1
baseline. Correct.

### Stucks — random ≫ FIFO (30+ vs 0) ✅ EXPECTED and GOOD
A *stuck* = a robot that couldn't make progress and abandoned its task. Random
robots pick incoherent targets and wedge into dead-ends/congestion the pathing
can't resolve. FIFO robots go to sensible targets on valid A* paths and rarely
wedge. So "random has more stucks" is the correct signature of a bad policy vs a
good one — it confirms the substrate rewards coordination and punishes flailing.
Stucks IS a policy-quality signal (unlike collisions below).

### Why stucks diverge but reroutes don't (the key link)
A reroute is a *momentary* blip ("we both want that cell next step, so one steps
aside"); a stuck is a *sustained* failure (sat too long, gave up the task). The
difference between policies isn't the blips — it's whether a blip resolves or
compounds. FIFO robots have a committed, sensible destination, so a reroute
resolves cleanly (there's a real place to go) and they keep progressing. Random
robots chase a NEW random target ~every step, so contention has no coherent
escape destination → they thrash, make no net progress, and the stuck-timer
trips. **Rerouting only rescues you if you have a sensible place to go — FIFO
does, random doesn't.** So reroute counts look similar (contention happens to
both), but stucks diverge massively (only random lets contention + incoherence
pile into giving up). Corollary: reroutes are NOT a policy-quality metric; stucks
and throughput are.

### Reroutes — no clear ordering, looks noisy ✅ EXPECTED
NB: the metric (`clashes` in the env) is a **reroute count**, NOT collisions — a
"clash" is a *detected-and-avoided* conflict where one agent reroutes; robots
never actually collide. Each reroute costs energy/time (a longer path). It is NOT
a policy-quality metric. FIFO's reroutes come from *productive* convergence on
shared cells (fairly stable per seed); random's come from chaotic movement and
are erratic — and the random policy is **un-seeded**, so its reroute count swings
a lot run-to-run (seen: 2–62). Sometimes random < FIFO (stuck robots don't move,
so fewer conflicts), sometimes >. So "it looks pretty random" is correct — don't
read policy quality into it; it's a congestion side-effect.

### Deadlines met — both N/A ✅ CORRECT
Deadlines aren't modelled yet (a later Stage-0 layer). Showing N/A rather than a
fabricated number is intended.

### Battery — no fixed FIFO-vs-random ordering; flips over time ✅ EXPECTED, here's why
Battery drain is driven by **activity**, offset by **recharging**:
- moving / carrying / picking → drain;  sitting on a charger → recharge;
  idle (stuck) → minimal drain (idle = 0.25× drive).

That creates **competing effects**, so there is NO clean "FIFO always drains more"
or vice-versa:
- **FIFO pickers** — high activity, never reach a charger (docks only sit under
  AGV routes) → drain hardest → **strand every seed** (DETERMINATE).
- **FIFO AGVs** — high drain, but pass delivery docks (= chargers) → **sawtooth**
  (drain then top up) (DETERMINATE shape).
- **Random robots** — stuck/idle much of the time → **drain slowly**, rarely
  carry/pick, never recharge → **plateau high**, rarely strand in 500 steps.

So the honest picture: for *individual robots* the pattern IS determinate (pickers
monotonic→strand; AGVs sawtooth; random slow decline). For the *aggregate FIFO
vs random ordering* it is genuinely seed/moment-dependent — early on both move
(noisy), FIFO AGVs recharge (pulls FIFO back up), and random is un-seeded. Net
tendency by episode end: **random retains more charge** because "working hard
costs battery" and stuck robots do nothing. That the ordering looks noisy is
correct, and the mechanism above is why.

---

## 2026-07-07 — Battery uniformity, model structure, reroute pairs, deadlines

### Battery constants/ratios — UNIFORM across simulation policies ✅
`scripts/verify_battery_uniformity.py` → `results/battery_uniformity.csv`. All 13
battery attributes read from independently-created trackers in a FIFO run and a
random run are **identical** (every row YES): steps_per_charge 300, drive-drain
0.003333, idle 0.000833, carry_extra 0.001667, pick_cost 0.001, charge_gain
0.011111, charge:discharge 3.333, idle:drive 0.25, carry:drive 0.5, pick:drive
0.3, floor 0.10, start 1.0. So the policy changes *outcomes*, never the *physics*.

### Battery structure across ROBOT TYPES — shared base + 2 work terms
SAME for AGV & Picker: drive/idle/charge/floor/start/capacity (steps_per_charge).
PER-TYPE: carrying penalty (AGV only, while carrying), pick penalty (Picker only,
per pick). **Simplification flagged:** capacity is the SAME for both types — does
NOT model the ~4× real gap (RB-VOGUI 720 Wh carrier vs RB-KAIROS+ 2.78 kWh
picker); per-type capacity deferred.

### Reroute pairs — only AGVs appear ✅ EXPECTED
Dashboard reroute-pairs + the env's `clash_pairs_this_step`: only AGV↔AGV pairs
show up. Pickers are exempt from counted reroutes at loading cells by design
(warehouse.py:450), so they never trigger a reroute. FIFO reroutes spread across
AGV pairs; random often concentrates on one pair (e.g. AGV1↔AGV3) as two robots
repeatedly contend at a spot. Per-pair counts sum to the "Reroutes" metric.

### Value-aware priority — maximises VALUE delivered on time ✅
Added per-task VALUE (reward for delivering ON TIME; `wwm_sim/values.py`,
`data/values_example.txt`, values 1-10 uncorrelated with deadlines). New objective
= total on-time VALUE.

**CSV:** `results/deadline_vs_value_10trials.csv` (script
`scripts/verify_deadline_vs_value.py`, large env, 10 seeds). CLARIFICATION: BOTH
policies run the IDENTICAL tasks — every task carries a deadline AND a value in
both runs; the DEADLINE-based policy simply IGNORES that value in its ordering.
Only the ordering rule differs.

**How measured:** run the full 500-step episode; on each delivery of shelf S at
step t, it's on-time iff `t ≤ S.deadline`, and if so `on_time_value += S.value`.

**Result (means):**
| policy | deliveries | on-time # | on-time % | **on-time VALUE** | late |
|---|---|---|---|---|---|
| FIFO (baseline) | 31.1 | 17.4 | 56.1 | 97.5 | 13.7 |
| DEADLINE-based (value-blind) | 34.8 | 25.4 | 72.9 | 146.1 | 9.4 |
| **DEADLINE+VALUE-based** | 33.6 | 26.9 | **80.2** | **200.8** | 6.7 |

Value-based wins on EVERY axis (value +37%, on-time% +7pt, fewer late) at ~equal
deliveries.

**Why VALUE-based is LESS late than DEADLINE-based (counterintuitive).** Measured
buffer at task start (deadline − assign step): DEADLINE-based mean 39 vs VALUE-based
mean 94 (~2.4x). Deadline-first grabs the TIGHTEST makeable task (least slack, just
above doom line) → starts with ~39 steps buffer for an ~83-step job → any picker-
wait/congestion tips it late (EDF-at-the-edge = fragile). Value-first picks by value
(uncorrelated with deadline here), so its tasks have scattered deadlines → ~94 steps
buffer → absorbs delays → fewer late. Principle: slack = robustness under
uncertainty; EDF minimises slack so it's fragile. CAVEAT: fewer-late is partly LUCK
(value ⟂ deadline); if rush orders were high-value AND tight, value-first would chase
the edge too. → the real fix is a SMOOTH P(on-time) that prefers high-buffer tasks
on purpose (Part A), not the hard makeable/doomed cutoff.

**Two benefits of value-priority (why it's better for UTILITY).**
(a) GETS THE BIG ONES DONE. Utility = VALUE delivered on time, not task count. By
    sorting on value (not just deadline), it secures the high-value tasks first, so
    at ~equal delivery count it banks far more value (200.8 vs 146.1). It focuses on
    the payoff, not just the clock → directly higher utility.
(b) LETS FEWER TASKS GO LATE. Because it is NOT scattering after the most-urgent
    (tightest, lowest-buffer) tasks the way EDF does, it works higher-buffer tasks
    (mean 94 vs 39 steps) → fewer slip late (6.7 vs 9.4). EDF chases the fragile
    edge and lets collateral tasks fall late; value-priority's steadier, higher-
    buffer work profile keeps lateness down. So it beats EDF on BOTH the value it
    banks AND the lateness it avoids.

**On the 83-step window (design note).** 83 = measured avg completion in the
CROWDED sim (8 AGV/4 pickers) — i.e. WITH other-robot disturbance; the ALONE
(1 AGV/1 picker) average is 52, so ~31 steps is contention/congestion overhead.
But 83 is a single GLOBAL AVERAGE applied to every task at every moment → crude
(a close/idle-picker task completes ~30, a far/all-busy one 150+). Better: per-task
`est_completion = base_travel (rollout engine, exact) + disturbance_delay (delay
head, learned)`; buffer = deadline − now − est_completion → smooth P(on-time). A
global average both wrongly ABANDONS makeable-but-faster tasks and wrongly ATTEMPTS
doomed-but-slower ones. Deferred: needs rollout engine (Stage 0) + delay head
(Stage 3). Fixed 83 is a placeholder. Formula: among MAKEABLE tasks (deadline−now ≥ ~83) do HIGHEST-VALUE
first (deadline tie-break); DOOMED shoved to bottom = value × P(on-time) with a
HARD makeable/doomed P. `ValuePriorityController`, dashboard default; panel shows a
value column + On-time VALUE stat. Next: SMOOTH P(on-time) instead of the hard
cutoff (Part A).

### Feasibility-aware priority barely helps — the real problem is "EDF-at-the-edge" ⚠️
3-way 10-trial (large env, deadlines, seeds 0-9): on-time% FIFO 55.9 / PRIORITY 38.2
/ FEASIBLE 39.8; on-time COUNT FIFO 17.4 / PRIORITY 13.2 / FEASIBLE 13.7.
Feasibility-aware (expired tasks deprioritised below tasks due in next ~83 steps)
moved the needle only +1.6pt — deprioritising EXPIRED tasks wasn't the fix.
**Real mechanism:** any urgency-first scheme (EDF) delivers tasks "just in time"
(low slack) → under overload they're fragile and miss. FIFO's random order
DEsynchronises delivery from deadline, so far-deadline tasks get delivered EARLY
(huge slack) → trivially on-time. So under overload, urgency is counterproductive
for the on-time objective. Fix is NOT expired-filtering — it's slack/value-aware
scheduling (Part A scores value × P(on-time), which avoids doomed AND fragile
tasks), or relieving the overload (more pickers). Also: maximising on-time COUNT
is a different objective than urgency (cf. Moore-Hodgson).

**FOLLOW-UP — the SLACK-aware fix WINS (corrected feasibility threshold).** The
first feasibility attempt shed only ALREADY-EXPIRED tasks (deadline < now) → barely
helped. The correct threshold sheds UN-MAKEABLE tasks: deadline − now < window
(~83 = completion time) — a task due sooner than you can finish it is already
doomed even if not expired. Bake-off (10 trials, large env, on-time count / %):
FIFO 17.4 / 55.9 · naive EDF 13.2 / 38.2 · MAX-SLACK (far-first) 23.9 / 71.1 ·
**FEASIBLE-EDF (shed un-makeable, then EDF) 25.4 / 73.0 — WINS.** Intuition: under
overload you WILL miss some; give up the impossible (guaranteed misses) and
guarantee the makeable (high-slack = safe), rather than chase fragile/doomed urgent
tasks (miss them anyway + cause collateral misses). `FeasiblePriorityController`
updated to this logic; it's the dashboard default. Caveat: equal task values here
→ maximises on-time COUNT; real value×P(on-time) needs task values (Part A).

### Realistic AMR throughput (Robotnik) — frames the overload
RB-KAIROS+ = 1.5 m/s (Robotnik). Large warehouse ~35×22 m (1 m/cell). Task cycle
travel ~52 m (fetch+deliver+return) → ~35 s top-speed, ~50 s with accel/turn
overhead, +~10-15 s load/unload ≈ ~60-65 s/task. So one DEDICATED (1:1) AGV+picker
pair ≈ **8 tasks / 500 s** (7-10 range). (Manufacturers publish station rates
300-600 picks/hr, not per-robot cycles → first-principles estimate.) Sim delivers
~4-5 tasks/AGV/500 steps — BELOW the 8/pair ideal — because the 2:1 AGV:picker
ratio starves AGVs of pickers. Measured avg completion 83 steps ~= 83 s ~ ideal
65 s + picker-wait. Confirms: more tasks/tighter deadlines than 8 AGV / 4 pickers
can serve on time → overload.

### 10-trial Priority vs FIFO — naive deadline-priority BACKFIRES under overload ⚠️
`scripts/verify_priority_10trials.py` → `results/priority_vs_fifo_10trials.csv`
(large env, 8 AGV / 4 pickers, deadlines attached, seeds 0-9). Result (means):
- deliveries: PRIORITY **34.6** vs FIFO 31.1 (priority delivers MORE total)
- on-time COUNT: PRIORITY **13.2** vs FIFO **17.4** (priority delivers FEWER on time)
- on-time %: PRIORITY **38.2%** vs FIFO **56.1%** (priority much lower)

**Mechanism (traced, seed 0):** delivery slack = deadline − delivery-step. FIFO
mean slack **+29** (range to +342) — random order banks high-slack far-deadline
tasks that are trivially on-time. PRIORITY mean slack **−49** (max only +112) — it
always works the most-urgent task, so deliveries cluster "at the deadline edge,"
and once it falls behind (OVERLOADED: 40+ open tasks, ~30-35 deliverable/500
steps, pickers 2:1) they land near/PAST deadline.

**This is the classic EDF-under-overload result:** earliest-deadline-first is
optimal only when the system is feasible; under overload it pours effort into
near-miss/doomed urgent tasks → worse deadline-hit than even FIFO. **Lesson:
deadline-ONLY priority is not enough** — the planner needs feasibility/slack
awareness (prioritise what you can still MEET, shed the doomed), i.e. Part A's
"deadline chances" scoring. This finding MOTIVATES the fuller planner (naive
EDF is a strawman our real strategy must beat). Also: picker_wait ~1050 steps
both policies (2:1 AGV:picker cap unchanged by task-order choice).

### Why AGVs sit idle + the picker-dispatch fix ✅
Diagnosis (seed 0, 250 steps): AGVs stationary ~52% of steps; **41%+ of idle time
is an AGV parked at its shelf waiting for a picker** (more is picker-wait during
RETURNING). Root cause: an AGV cannot load/unload without a picker on the SAME
cell (warehouse.py:536) — 2 pickers, 3 AGVs → someone always waits. Fix:
`PriorityController._dispatch_pickers` sends the NEAREST free picker to the
MOST-URGENT (soonest-deadline) waiting AGV, instead of zone-locked first-come.
Measured (500 steps): deliveries 21→24 (+3, ~14%), AGV picker-wait 422→357
(−65, ~15%). Honest cap: 357 wait-steps remain — 2 pickers is a structural
bottleneck; better dispatch maximizes the 2 you have, doesn't remove the cap.
Picker battery kept SIMPLE: flat `pick_penalty` per pick (no per-item/weight
scaling) — deliberate.

### Priority (deadline) assignment WORKS ✅
`scripts/sim_priority.py` (PriorityController: assign nearest free AGV in deadline
order). Verified vs FIFO on seed 0 with scrambled deadlines: PRIORITY delivers
first (shelf,deadline) = (10,140)(47,149)(1,147)(11,177)(20,170)(21,207) — low
deadlines first; FIFO = (15,325)(42,304)(18,436)(8,406)(11,177)(22,244) — ignores
deadlines, queue order. Delivery order not perfectly monotonic (149 before 147)
because each urgent task → NEAREST free AGV, so travel distance adds jitter;
ASSIGNMENT is strictly priority-ordered, delivery timing has noise. Non-preemptive
(in-progress robots keep their task). Deadline-ranked task panel in the dashboard
confirms the ordering live.

### Deadlines — plumbing verified
`wwm_sim/deadlines.py` loads a task→deadline doc/text and attaches to `Shelf.deadline`.
Verified: file path attaches all 20 seed-0 tasks; inline text "15 200; 42: 180;
18,240" attaches those 3, rest None. No deadline-met metric or generation model
yet (deliberate).

## Consolidated scoreboard (2026-07-11) — all tracked metrics

Means over ~10 seeds, 8 AGV / 4 picker large env, 500-step episodes (small cross-experiment
variation from different bake-offs / caps).

POLICY SCOREBOARD (the value-learning ladder):
  Policy                         Deliveries  On-time  On-time_value  Total@80%late  Decay-wtd
  FIFO (baseline)                31.1        17.4     97.5           162.5          -
  Deadline (EDF+Moore-Hodgson)   34.6        20.5     111.5          176.6          -
  Value-aware                    34.2        27.4     206.6          249.7          220.1
  Rush (lateness-decay)          34.6        27.5     206.4          -              229.3
  Part A (AGV+picker funnel)     35.3        26.7     198.8          -              -
Metric defs: on-time_value = sum value of tasks beating deadline (late=0); Total@80%late =
late kept at 80%; Decay-wtd = sum value*0.98^lateness. Ladder: each step buys value; value-
aware >2x's on-time value over FIFO (97->207); rush wins decay-wtd; Part A ties value, tops
throughput.

SYSTEMS SCOREBOARD:
  Adaptive window: avg completion 68.7 (8/4) -> 59.6 (12/8).
  Battery charge rule (spc=400): strandings 6.2 -> 1.0 / 12.
  Native execution clashes = WAIT events (not reroutes): ~194 (RUSH & Part A).
  Collision filter hard-delete: throughput 34 -> 7.5 (PARKED; env drives its own A*).
  ADG execution: 1-step lateness -> naive 1 collision vs ADG 0 (delay absorbed as wait).
  Part A vs Rush (10-trial): on-time value 198.8 vs 205.5 (~3% behind; delay head closes it).

## All policies on the SAME decay-weighted metric (2026-07-11, 10 seeds, hard-500)

Apples-to-apples on decay-weighted value = sum value*0.98^lateness (g=0.98):
  policy    deliv  on-time  on-time_val  DECAY-WEIGHTED
  FIFO      31.1   17.4     97.5         115.9
  Deadline  34.6   20.5     111.5        152.8
  Value     34.2   27.4     206.6        214.7
  Rush      34.0   27.4     205.5        218.9   <-- wins
  PartA     35.3   26.7     198.8        211.7
Ladder on the weighted metric: FIFO 116 -> Deadline 153 -> Value 215 -> Rush 219 (best;
harvests late high-value tasks) -> Part A 212 (~3% analytic-finish gap behind Rush). Big
jump = Deadline->Value (+62); Rush edge over Value = +4 (late harvesting).

## Part A gap diagnosis (2026-07-11): split source is NOT the cause

Hypothesis: Part A lags RUSH because it uses per-task rollout FINISH (not RUSH's global
window) for the makeable/doomed split. Test (10 seeds, hard-500), added USE_GLOBAL_WINDOW toggle:
  policy                        deliv  on-time  on-time_val  decay-wtd
  RUSH                          34.0   27.4     205.5        218.9
  PartA (per-task finish)       35.3   26.7     198.8        211.7
  PartA (RUSH global window)    35.8   26.3     197.4        209.0
RESULT: using RUSH's exact split did NOT close the gap — slightly WORSE. Both Part A variants
~197-199 on-time value, ~7 behind RUSH 205.5. => the split source is NOT the gap.
LIKELY CAUSE (narrowed): the funnel's TASK SELECTION, not the score. Two suspects: (1) the
CHEAP SCREEN keeps only top-15 by value-0.15*Manhattan -> can MISS a high-value-but-farther
task RUSH would take (distance term biases toward nearby-lower-value work) [prime suspect];
(2) robot-centric (each AGV picks) vs RUSH's task-centric (sort queue, nearest AGV per task).
Note: Part A delivers MORE (35.8 vs 34) but converts fewer to on-time value -> it's doing more
low-value/late work, consistent with the distance-biased screen. Next: widen/de-bias the
screen (drop or shrink the distance term) or make selection task-centric, then re-bake.

## CONFIRMED (2026-07-11): Part A's delivery edge = the picker sync-up

Isolation test (10 seeds, W_SYNC on/off):
  policy               deliveries  on-time  on-time_val
  RUSH                 34.0        27.4     205.5
  PartA sync(0.3)      35.3        26.7     198.8
  PartA NO-sync(0)     33.5        26.1     199.0
CONFIRMED: sync-up CAUSES the delivery edge. Off -> deliveries 35.3 -> 33.5 (BELOW RUSH 34.0).
The ~1.8 extra deliveries are 100% the sync (tight AGV<->picker meet-ups -> faster round-trips
-> more done). On-time VALUE gap to RUSH (~199 vs 205.5) does NOT move with sync (198.8 vs
199.0) -> that gap = traffic-blind timing, not sync. Sync even nudges on-time count up a hair
(26.7 vs 26.1). SUMMARY: sync = "fast hands" (delivery edge, proven); traffic-blind = "bad
watch" (on-time value gap, proven). More boxes, fewer on time.

## Delay head STARTED + the key lesson (2026-07-11)

Built the delay head pipeline: diary (Part A logs pred finish + congestion features per commit;
delivery gives actual finish; label = actual - pred = the delay the rollout missed), LightGBM
trainer (scripts/train_delay_head.py), wired via PartAController.delay_head. 706 rows (20 seeds);
delay mean +16.6, std 16.6, range -10..+107 -> rollout SYSTEMATICALLY underestimates by ~16.
HEAD ACCURACY (test MAE, steps): formula predict-0 = 17.57; constant predict-mean = 12.82;
LightGBM head = 14.11. Head beats formula by 19.7% (clears the 15% gate) BUT LOSES to the
constant mean by 10% -> per-task FEATURES barely help; delay is mostly a CONSTANT offset.
CONSTANT-OFFSET BAKE-OFF (10 seeds): RUSH on-time_val 205.5 / decay 218.9; PartA 198.8 / 211.7;
PartA+16.6 offset 197.8 / 209.7 -> a MORE ACCURATE finish made decisions SLIGHTLY WORSE.
WHY (key lesson): Part A's makeable/doomed is a BINARY cutoff. A more-accurate AVERAGE finish
just shoves borderline tasks into "doomed" -> sheds them -> loses the ones that (per-task noise)
would still land on time. When OPTIMISTIC, Part A keeps borderline tasks high-priority and
CATCHES the winners. So finish-accuracy can't help a hard cutoff; the per-task NOISE decides
on-time, not the average.
STACKED: (1) delay ~ constant (features weak, learned head < constant); (2) even a perfect
average doesn't help because the BINARY cutoff is the bottleneck. => the delay head only pays
off feeding a SMOOTH P(on-time) = P(finish+delay <= deadline), scored value x P(on-time) -- so
borderline tasks are WEIGHTED, not shed. Needs the delay SPREAD (quantile), not just the mean.
That smooth value x P(on-time) is the next build; the delay head is its input.
