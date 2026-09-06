# Progress & Understanding Notes

A running log of understanding milestones for the Warehouse World Model project.
Each entry records a summary or question (mine, the user's) and the confirmed
answer, so the reasoning behind decisions stays visible over time.

New entries are appended at the bottom with a date. From now on, whenever I give
a summary sentence or ask a clarifying question, the confirmed answer is recorded
here.

---

## 2026-07-04 — Project understanding

**Read:** `Project_Plan_Main.docx` + `PartA/B/C/D_Plain.docx`.

**Core idea.** Event-driven planner for a multi-robot warehouse. At each decision
event it simulates candidate futures for every free robot and commits the plan
whose predicted future scores best under a fixed, human-readable utility.

**Architecture thesis.** KNOWN-RULES pattern (AlphaZero/MPC family), *not*
learned-dynamics (Dreamer/MuZero). We wrote the environment's rules, so we
simulate with them directly; only the *predictions* (uncertainty heads) are
learned. Runs under partial observability via a Bayesian "rumor map" (Beta
beliefs) of disturbances inferred from robot execution struggle, not sensing.

**The four Parts.** A = pick a task + route (one robot); B = support-then-task
(judge the task from the imagined post-pit-stop future); C = future-readiness
(prepare for work that doesn't exist yet); D = the group decision (combine
per-robot shortlists, commit the exact route combo).

---

## 2026-07-04 — Evaluation metrics understanding

The metrics split into three distinct jobs, not one:
- **Scores to maximize** (§5.1 outcomes): throughput, deadline hit rate,
  tardiness (mean + p95), energy/task.
- **Invariants to verify at zero** (safety-by-construction): collisions,
  strandings — any count > 0 is a bug, not underperformance.
- **Gates that block bad additions**: learned heads must beat the analytic
  formula by ≥15% AND be calibrated (§5.3); every mechanism must show ≥3%
  ablation improvement or it is cut (§5.4).

Recurring theme: **calibration appears twice** (rumor map §5.2 and heads §5.3)
for the same reason — the utility *multiplies* probabilities, so honest
confidence matters more than correct ranking. Rumor-map group is judged
with-map vs. without-map on identical seeds (the 90/90 sensitivity/specificity
pair, latency ≤15 steps, calibration ±10%).

---

## 2026-07-04 — Immediate next step (decided)

**Question:** what is the immediate next step for implementation?

**Answer / decision:** Stage 0 is the foundation (every later stage is a
baseline comparison against it). The first brick is the simulator + a rollout
engine that *shares one rulebook* with it. Rather than build a simulator from
scratch, **adopt TA-RWARE as the simulator substrate** and layer our rulebook
(battery, disturbances, believed-state rollout, Parts A–D) on top — TA-RWARE
also gives us the FIFO baseline and layouts we need for §6 evaluation.

---

## 2026-07-04 — User summary: what was built

**User's summary:** "You made the environment runnable and documented how to
run it in the README."

**Confirmed.** TA-RWARE installed editable (two packaging fixes to its
`pyproject.toml`), a runner (`scripts/run_tarware.py`) exposing FIFO and random
policies, and a README documenting setup, run commands, and the metric mapping.

---

## 2026-07-04 — User summary: what FIFO vs random is for

**User's summary:** "FIFO you just ran to see if the substrate was wired
correctly because in most environments it should prevail over random selection
of tasks, and FIFO will also help with a baseline comparison for throughput,
right?"

**Confirmed — both roles, and they are distinct:**
1. **Wiring check (today).** FIFO is a known-good controller; if the substrate
   is wired correctly it should massively beat random on identical seeds. It
   did (~20× deliveries; random also racked up ~30 stucks). This proves the
   plumbing — orders → movement → picks → deliveries, plus collision/stuck
   accounting. It does NOT test our contribution (battery/disturbances/rumor
   map) because none of that exists in base TA-RWARE yet.
2. **Baseline comparison (later).** FIFO is TA-RWARE's built-in baseline and the
   §6.1 success target: throughput ≥ FIFO in clean runs, ≥10% above under
   disturbances. It is the right yardstick precisely because it is memoryless —
   no map, no lookahead — so it keeps sending robots into known trouble, which
   is exactly where our belief map + support actions should win. This comparison
   (FIFO vs. our planner) can't happen until the planner exists.

**Key method detail:** matched seeds pin the layout AND the order stream, so any
outcome difference is caused purely by the decisions, not luck.

---

## 2026-07-04 — Clarification: `--render`

`--render` opens a pyglet window (needs a real display; run locally). Initially
it only worked for the heuristic; fixed so both policies render. Added a `--fps`
throttle so the sim is watchable. Later superseded for demos by the side-by-side
dashboard (`scripts/sim_dashboard.py`).

---

## 2026-07-04 — Clarification: FIFO has more "clashes" than random — a concern?

**Question:** FIFO shows many more collisions (clashes) than random, but far
fewer stucks and more tasks completed — is the high clash count a concern?

**Answer: no — it's the healthy trade, because a TA-RWARE "clash" is not a
crash.** Verified in `warehouse.py`:
- A **clash** (`resolve_move_conflict`) is a *detected-and-avoided* conflict:
  when one agent's next move would hit another, the agent is stopped
  (`NOOP`) and reroutes (`fixing_clash`). Robots never share a cell. Cost =
  one stopped step + a recompute → it's a **congestion / contention** signal,
  not damage.
- A **stuck** (`resolve_stuck_agents`) is the real failure: an agent sat too
  long, gives up (`busy=False`), and **abandons its task**.

**Why FIFO clashes more but sticks less and delivers more:** FIFO agents
productively converge on shared hot spots (requested shelves, the few bottom-row
goal stations, empty return slots) and move constantly → lots of contention,
all safely resolved (0 stucks). Random agents wander, wedge into dead-ends where
no reroute helps → those escalate to stucks, and deliver ~nothing. FIFO is
effectively converting would-be deadlocks (stucks, which kill tasks) into
transient resolved conflicts (clashes, which cost a step). High clashes + 0
stucks + high throughput = a pass. It would only matter if clashes grew so large
that rerouting dominated and throughput collapsed (a high-density congestion
pathology) — exactly what our ADG ordering + selective replanning target.

**Doc correction triggered:** earlier metric mapping `clashes → Collisions` was
misleading. TA-RWARE `clashes` = avoidance interventions (congestion proxy,
≈ plan's *replans per disturbance*), NOT actual crashes. Our "Collisions = 0
absolute" means real crashes, which base TA-RWARE already prevents by
construction. README mapping updated accordingly.

---

## 2026-07-04 — Clarification: what defines a collision

**Question:** what defines a collision?

**Answer — two cases in a single timestep (standard MAPF definition, and what
the plan uses):**
1. **Vertex conflict** — two robots occupy the *same cell at the same timestep*
   (drive-into an occupied cell, or two into the same empty cell).
2. **Edge / swap conflict** — two robots *exchange cells* in one step
   (A: c1→c2 while B: c2→c1); they pass through each other. No cell is shared,
   so a vertex-only check misses it — hence called out separately.

Plan usage: Part A hard-filter deletes any route that "collides — same cell same
moment, or an edge swap"; Part D commits at the cell-and-timestep level so both
are verifiable. Collisions are **deletions, never prices** → "Collisions = 0
absolute" (§6.1) means real vertex/edge conflicts on committed routes, impossible
by construction.

**In TA-RWARE code** (`resolve_move_conflict`, warehouse.py:441-479): checks if
an agent's next cell == another's current cell (catches drive-into AND swap) or
== another's next cell (same-target). On conflict it stops one agent (NOOP) +
reroutes → prevents the collision and counts a `clash`. So base TA-RWARE never
lets two robots share a cell.

**Deliberate exception (line 450):** inside a rack (non-highway), a picker and an
AGV of *different* types may share a cell — that's the loading rendezvous, a
feature not a conflict. So "same cell" ≠ always a collision.

---

## 2026-07-04 — Clarification: are my sim runs logged to data/*.csv?

**Question:** are the simulations I'm running being written into `data/legs.csv`
and `data/steps.csv`?

**Answer: no.** `scripts/run_tarware.py` and `scripts/sim_dashboard.py` write NO
CSV — they only print and render; each run is ephemeral. The two CSVs
(`task-assignment-robotic-warehouse/data/`) are written *only* by TA-RWARE's own
`scripts/generate_data.py`, which was run 07-03 (before this session), producing
~500k step-rows and ~52k leg-rows. `train_delay_head.py` reads `legs.csv` to
train a delay head. My runner/dashboard sit outside that pipeline.

**Plan connection:** those CSVs are a first draft of the Stage-3 "simulator
diary" (predicted-vs-actual logging for the learned heads); `steps.csv` =
per-step trace, `legs.csv` = per-leg features + labels. Logging is a deliberate
Stage-3 step, intentionally NOT done during Stage 0 (the features worth logging —
battery, beliefs, deadlines — don't exist in the env yet). Left ephemeral for now.

---

## 2026-07-04 — DECISION POINT: how to overlay battery / deadlines / disturbances

**Question:** to add battery + disturbances + deadlines, do we edit our copy of
TA-RWARE, and how do we then factor in disturbances?

**Framing.** The three additions are NOT equally invasive:
- *Deadlines* = pure annotation (due-time per task); no dynamics change → wrapper.
- *Battery* = mostly in OUR planner (hard-filter constraint + score term); world
  needs only a tiny "charge while on charger" rule.
- *Disturbances* = the hard one: must actually impede execution (the "struggle"
  the rumor map infers from) AND be hidden → needs per-cell movement control.
  Must be **authored by us** (no benchmark has them); we write a seeded
  disturbance generator and hold ground truth so latency/detection are measurable.

**The fork (needs user confirmation):**
- **Option A** — subclass/fork TA-RWARE's movement to inject battery+struggle.
  Painful: TA-RWARE moves via macro-action + internal A* + clash-fixing (no
  per-cell control), and the rollout engine would have to mirror that exactly.
- **Option B (recommended)** — write our own thin event-driven simulator
  (movement = 1 cell/step 4-conn, + battery/time/disturbances), seeded with
  TA-RWARE layouts + task rates; keep TA-RWARE UNMODIFIED as the FIFO throughput
  benchmark. Rollout engine reuses our exact rules on believed state (the
  "deterministic, zero compounding error" promise). Matches the plan's own words
  ("port its layouts into our simulator... layer disturbances on top") and Stage
  0 item 1 ("simulator ... all plain code").

Either way the vendored TA-RWARE copy is NOT destructively edited. **Answer to
"do we edit the record?": no** — disturbances go into OUR simulator's movement
rule, not the TA-RWARE copy. *Status: awaiting user pick of A vs B before Stage 0
build proceeds.*

**Update — user leaning Option B.** User's summary: "TA-RWARE is just the
baseline / to see the baseline works; then we make our own simulator (runner)
that also displays deadlines, battery, etc. on the side." Confirmed as Option B,
with one sharpening: TA-RWARE is NOT a throwaway — it keeps two permanent jobs:
(1) source of layouts + task rates that seed our simulator, and (2) the lifelong
FIFO throughput yardstick our planner is measured against (§6.1: match clean,
beat ≥10% under disturbances). So: TA-RWARE = yardstick + layouts (never edited);
our sim = the contribution (battery/deadlines/disturbances/partial-obs), shown in
the view.

**Done — editable simulator copy created (`wwm_sim`).** Per user request, made an
editable copy of the TA-RWARE *simulator* (NOT the CSVs): copied `tarware/` →
`wwm_sim/`, renamed `tarware` → `wwm_sim` (ids now `wwm_sim-*`), added a root
`pyproject.toml`, installed editable (`pip install -e . --no-deps`). FIFO parity
verified (seed 0: 22 deliveries / 14 clashes, identical to tarware). This is the
package we edit going forward; vendored `tarware` stays untouched.

**Clarification logged:** "our simulator is our rollout model" — *almost*. The
simulator steps the real world; the rollout engine is a lightweight function
replaying the SAME rules on believed state to predict a candidate future. One
rulebook (ours), two callers — that shared rulebook is what makes rollout exact.

---

## 2026-07-04 — Clarification: the FIFO-vs-ours comparison runs in ONE package

**Question:** we use the same FIFO baseline and our own strategy, compare the
two, but it's all on the same package (`wwm_sim`) — we don't edit old tarware,
right?

**Answer: exactly right.** The living comparison is **FIFO-in-`wwm_sim` vs.
ours-in-`wwm_sim`, identical seeds, identical world** (same battery rules, same
disturbances, same task stream) — the ONLY difference is the decision strategy,
and both are scored by the SAME metric set. That's the only fair setup; running
ours in enriched `wwm_sim` but comparing to FIFO's vanilla-tarware numbers would
be two different worlds = meaningless.

**Sharpening of the earlier "tarware = yardstick" framing:** the FIFO *strategy*
is the yardstick and it lives INSIDE `wwm_sim` (copy already has `heuristic.py`).
Vanilla `tarware` narrows to (1) a **parity reference** — confirm our copy still
reproduces base FIFO numbers so edits didn't corrupt the physics — and (2)
layout / task-rate source. Not edited.

> Tarware just anchors that we didn't corrupt the baseline when we forked it.

**Fairness nuance (decide when battery lands):** FIFO is battery/disturbance-
unaware by design; running it in the enriched world where it strands robots and
re-enters known spills IS the experiment (§6.1). But to avoid a strawman, we may
give FIFO a minimal naive "charge when low" augmentation so it's a *fair*
baseline. TBD at battery time.

**What "strawman" means here (clarification):** a strawman is winning against a
deliberately *weakened* opponent instead of its fair best — a hollow victory.
Concretely: plain FIFO in a battery world never charges, so its robots strand and
die; our planner "wins by 40%" — but only because FIFO sabotaged itself, NOT
because our belief-map / lookahead were smart. That margin is fake. The fair fix
is to give FIFO the minimum obvious battery sense ("low battery → nearest
charger") so it's a real opponent; if we STILL beat it, the margin is earned by
our actual contributions. Matters because the §6.1 "≥10% over FIFO" claim only
means something if FIFO is a fair baseline. Rule: don't win by crippling the
opponent; beat it at its reasonable best.

---

## 2026-07-04 — Battery calibration: NO Gazebo data exists; plan = AMR spec sheets

**Status check before writing battery code:** searched the whole project — there
is **no Gazebo dataset** (no `.world`/`.sdf`/`.urdf`, no battery data). Gazebo is
a 3D physics simulator you *run*, not a dataset you read; running it (install +
AMR model + physics runs) is a heavy separate task, not done.

**Four constants to ground:** `energy_per_step` (drive draw), `carrying_penalty`
(payload draw), `idle_drain` (standby), `charge_rate` (charger power vs capacity).

**Chosen grounding source = real AMR manufacturer spec sheets** (the plan's own
cross-check). AMR = Autonomous Mobile Robot = the shelf-hauling warehouse robots
(= our "AGVs"; TA-RWARE is modeled on Quicktron/Quickbin). Manufacturers (Amazon
Robotics/Kiva, Quicktron, Geek+, Locus, Fetch/Zebra, MiR, OTTO...) publish
datasheets on their sites. Map: capacity(Wh)+runtime(h) → energy_per_step;
payload → carrying_penalty; charge-time+capacity → charge_rate; standby →
idle_drain (usually estimated). **Caveat:** spec sheets are marketing (best-case
runtime, no idle-vs-carry breakdown) → they give grounded *ballpark* ratios, not
lab-precise physics. Hence constants stay TUNABLE parameters, labeled provisional;
a real Gazebo run can refine later. *Next: pull specs from 2-3 real AMRs, derive
constants with citations, then build battery model.*

---

## 2026-07-04 — Battery: (a) vs (b) accuracy + per-robot-type specs pulled

**Q1 — does compressed (b) vs realistic (a) cost accuracy if properly trained?**
No. Battery is a KNOWN-RULE quantity the rollout engine computes exactly
(`rate × steps`), not a learned prediction. So (a)→(b) is a pure change of units
on an exactly-computed number — accuracy unaffected *provided* (i) train and
evaluate on the same regime, and (ii) compression is a clean uniform scaling that
preserves the ratios (carry/idle/charge). What (a) vs (b) actually changes is
whether battery-aware machinery (Part B/C) gets EXERCISED within a 500-step
episode — experiment-design, not model accuracy. → go with (b), tunable +
documented.

**Q2 — specs for BOTH robot types (pulled).** TA-RWARE roles: AGV (carries shelf)
+ Picker (picks items, never hauls the shelf). Mapping to Quicktron:
- **AGV → M60**: 600 kg ✅, 2 m/s ✅, ~9 h ✅, 145 kg ✅, battery 48 V×36 Ah ≈
  1.73 kWh ⚠️(unverified).
- **Picker → C56** (bin picker w/ arm): 30–50 kg ⚠️, battery 25.2 V×16.5 Ah ≈
  0.42 kWh ⚠️, runtime unpublished (sibling M5 same battery = 4–11 h).
- ✅ = on a spec page; ⚠️ = search result, not datasheet-confirmed. Sources:
  qviro.com/product/quicktron/m60, quicktron.com.cn C56, directindustry C56
  order-picker, quicktron.com bin-to-person.

**Design implications:** (1) Picker `carrying_penalty ≈ 0` by ROLE (never carries
the shelf; structural, needs no spec); AGV pays it only while `carrying_shelf`.
(2) AGV battery ~4× Picker's (1.73 vs 0.42 kWh). (3) BOTH robots' realistic
runtimes (~30k–65k+ driving-steps) ≫ 500-step episode → compression (b) applies
to both, not an artifact of one robot. Charge time unpublished; industry AMR norm
= 1–2 h full / 10–20 min opportunity → anchor for `charge_rate`.

---

## 2026-07-04 — Is there a more updated warehouse simulator? (survey + decision)

**Question:** since TA-RWARE is based on an older warehouse paradigm, is there a
more updated simulator closer to current hardware?

**Survey (3 categories):**
1. *Abstract grid + task assignment* (TA-RWARE's niche) — STILL the standard; 2025
   MARL warehouse papers still use RWARE/TA-RWARE. No hardware-modern drop-in
   replacement here.
2. *Lifelong coordination at scale* — **League of Robot Runners** (live 2023–25
   competition, MIT/USC/UCI/Monash/Rutgers): lifelong MAPF + task assignment,
   large fleets, robot dynamics. More "realistic" but MAPF-centric (NO battery,
   NO disturbances) and a heavy harness. Role for us: future *scaling* benchmark.
3. *Hardware-realistic 3D* — **NVIDIA Isaac Sim**: photoreal, physics/sensors,
   digital twins, bin-to-person robots. Genuinely modern + hardware-faithful, but
   needs RTX GPU + 32 GB RAM and is a physics/perception sim, NOT a decision
   benchmark. Role for us: only if we later do a physical digital-twin extension.

**Decision: stay on TA-RWARE (+ our `wwm_sim`).** Rationale (user's framing,
confirmed): (a) 3D physics/perception = slower + harder to overlay battery/
disturbances, for realism our decision-level contribution doesn't use; (b) shelf
vs bin is COSMETIC at our abstraction ("robot carries a load A→B") — planner/
inference apply identically; (c) the warehouse is just a TESTBED for the real
question — *can disturbances be inferred at all* — so abstraction is a feature
(isolates the idea from perception noise), matching the known-rules thesis.

**Anything-else points:** (1) The only thing that would truly matter isn't
hardware — it's whether a benchmark already has disturbances/partial-obs. NONE do
(confirms the plan's novelty gap); we must build it in `wwm_sim`. (2) Staying
abstract only drops perception + continuous dynamics, which don't touch our
thesis — our disturbance signal is BEHAVIORAL (struggle), not perceptual. (3) Not
boxed in: abstract-now → Isaac Sim / physical digital-twin-later is a clean
upgrade path the plan already anticipates (THUD++/JRDB bridge).

---

## 2026-07-04 — Battery calibration source: Robotnik (over Fetch/TIAGo), + built

**Vendor journey (honest record):** Quicktron (TA-RWARE's inspiration) → specs too
thin/unverified. Fetch+Freight → real arm but older SLA + murky Wh. TIAGo → I
initially preferred it but the reason was weak ("I had its PDF"). On a fair
comparison **Robotnik won**: RB-KAIROS+ = RB-VOGUI base + a UR arm (7.5–16 kg),
so the Picker is literally the carrier + arm → shared drive/battery physics,
per-type diff = carry-penalty (AGV) vs pick-penalty (Picker). Modern Li-ion
(2.78 kWh), industry-standard UR arm (best pick grounding), same-platform
carrier (RB-VOGUI 720 Wh, ~6 h). **Runtime source decision:** use QVIRO's ~6 h
(conservative working-load) NOT Robotnik's "up to 12 h" (best-case marketing);
range 6–12 h documented.

**Built (`wwm_sim/battery.py` + `scripts/battery_demo.py`):** KNOWN-RULE model,
pure/deterministic so the rollout engine can reuse it. Per-step drain =
drive / idle / +carry (AGV) / +pick (Picker at load event); charge at charger;
battery-floor → `stranded`. Constants PROVISIONAL + tunable, compressed via
`steps_per_charge` (default 300; realistic ~21,600). Chargers provisionally =
delivery docks (only AGVs visit → pickers strand, the pressure Part B/C will
manage). **Validated (seed 0):** picks_charged=22 == FIFO deliveries (clean
consistency); at 300 → 1 stranded; at 150 → all 5 strand; at 21,600 (realistic)
→ min 98.7%, 0 stranded (proves realistic battery never binds in 500 steps, so
compression is required). Does NOT yet gate movement (planner-level, later).

**Why Robotnik — the benefits, in two buckets.**

*A) Accuracy to the simulator (= operational concept + layout ONLY — the sim
models no hardware, so there is nothing hardware-wise to match; "accuracy" here
just means: do the robots map onto the sim's two roles?).*
- **Clean role mapping:** RB-VOGUI (carrier) → AGV; RB-KAIROS+ (same base + UR
  arm) → Picker. Matches TA-RWARE's AGV-carrier + Picker-loader operational
  concept and its grid-layout roles exactly.
- **Shared platform → drive/battery physics stay consistent across the pair.**
  The Picker is literally the carrier + an arm, so both inherit one base's
  movement + energy behaviour. This mirrors the sim's own abstraction (both robot
  types live in ONE grid world under ONE movement rulebook), so our per-type
  constants differ only where the roles differ (carry vs. pick) — internally
  consistent by construction, not a mismatched two-vendor stitch-up.

*B) Realism / modernity (the hardware-fidelity axis — optional for our thesis,
but free grounding quality).*
- **Modern Li-ion** (RB-KAIROS+ 2.78 kWh, RB-VOGUI 720 Wh) vs. Fetch's older SLA
  — current warehouse battery tech, so the constants reflect today's robots.
- **Industry-standard UR arms** (UR7e/12e/16e, 7.5–16 kg) — separately documented
  in huge detail (power, torque), so the pick-energy grounding is unusually
  well-supported ✅✅ (far more than any bespoke arm's spec line).
- **Current industrial AMR** (ROS 2, logistics-grade) — reflects how real
  warehouse robots are actually built now, and gives a clean later upgrade path.

**Dashboard update:** `sim_dashboard.py` now runs on `wwm_sim` (not tarware) and
shows per-robot battery bars (colour-coded, 10% floor line, stranded markers).
Emergent observation worth noting: FIFO drains *faster* than random, because
busy robots pay full drive+carry drain while random robots sit stuck on the
cheaper `idle_drain` — "working hard" costs more battery than "flailing", a
tradeoff the planner will later have to weigh.

---

## 2026-07-06 — Reading the dashboard: 3 clarifications (added to sim + docs)

Questions raised while watching the live dashboard. Also added as an on-screen
footnote in `sim_dashboard.py`.

**(a) Why do the FIFO task numbers look random? How is "FIFO" defined?** The
numbers are **shelf IDs** — arbitrary labels for physical shelf locations; which
shelves are *requested* is sampled randomly, so the IDs look random. FIFO is NOT
about the ID values — it's about **queue order**: the env holds a
`request_queue` of open tasks; the heuristic walks it front-to-back and assigns
each request to the **nearest free AGV** (nearest-agent). So first-in = front of
queue = served first. (Honesty note: on delivery the queue replaces the finished
request *in place* (warehouse.py:598), so it's the paper's *nominal* FIFO, not a
strict arrival-time queue.)

**(b) Why do an AGV and Picker overlap with no collision alert?** That's the
**loading rendezvous**, allowed by design (warehouse.py:450): inside a rack cell,
an AGV + a Picker of *different types* may share a cell — the Picker loading the
shelf onto the AGV. It's a feature, excluded from collision counting. A real
collision (same-type robots sharing a cell / edge-swap) never happens.

**(c) What does teal↔purple mean?** **Teal = requested shelf = an open task;
purple = idle shelf (no order).** A shelf stays teal from request until
**delivery**. When an AGV picks it up, the shelf's position follows the AGV
(warehouse.py:519-520), so the teal square **rides along with the red AGV**,
still teal, until it reaches a dock — then it turns **purple** (fulfilled) and a
**new purple shelf elsewhere turns teal**, keeping the open-task count constant.
So: purple→teal = new order appeared; teal→purple = order delivered; a moving
teal = a task-shelf being carried to a dock.

---

## 2026-07-06 — What changes under battery compression + a fix + 3-trial verify

**(A) Which battery aspects change under compression (steps_per_charge ↓).** Only
the ABSOLUTE per-step timescale changes; every RATIO and every dimensionless
threshold is preserved:
| aspect | absolute size changes? | ratio-to-drive preserved? |
|---|---|---|
| drive_drain = 1/steps_per_charge | YES (bigger) | reference |
| idle_drain = 0.25·drive | YES (scales) | YES |
| carry_extra = 0.5·drive (AGV) | YES (scales) | YES |
| pick_cost = 0.3·drive (Picker) | YES (scales) | YES |
| charge_gain = 1/charge_steps | **was NO → ratio BROKE** | **now YES (after fix)** |
| floor (0.10), start (1.0) | NO (dimensionless) | unchanged |

**Fix applied:** `charge_steps` was a fixed absolute (90), so charging did NOT
scale with compression — at realistic steps_per_charge it made charging ~250×
too fast vs discharge, breaking the "ratios preserved" guarantee. Replaced with
`charge_fraction=0.30` → `charge_steps = 0.30·steps_per_charge`, so charge scales
too. Verified: charge/discharge ratio = 3.333 at BOTH steps_per_charge=300 and
21,600. Default behaviour unchanged (0.30·300 = 90). Net: with the fix,
compression is a pure change of the TIME UNIT — everything drains/charges
proportionally faster, nothing else moves → confirms zero accuracy cost.

**(B) Dashboard task panel simplified** to three plain lists per the user:
BEING DONE (shelf + AGV + state) · WAITING (in order) · FINISHED (recent).

**DECISION — don't move chargers yet.** FIFO pickers strand every seed, but that's
a POLICY artifact (FIFO is battery-blind — never routes anyone to charge), NOT a
layout flaw (nothing forces pickers through a bad chokepoint; they *can* reach a
dock, just never get sent). Criterion: only relocate now if stranding were a
definitive structural flaw (always forced through a bad point) — it isn't. Our
battery-aware planner (Part B/C) will decide charging + charger placement
together. Flag for then: dock-chargers are awkward for pickers (pickers don't
visit docks), so Part B/C will likely add dedicated picker-reachable chargers.
Provisional dock-chargers stay for now.

**Clash-vs-collision + stucks — exact wording (preserve).**
> #2 (collisions): A "collision" here is not a crash — it's the system catching
> two robots about to hit and stopping one to reroute. So the collision is
> prevented; the count is just "how many times the avoidance system had to step
> in." That means it's not a good/bad quality signal — it's a congestion
> side-effect, a tiny cost (one stopped step + a reroute), all safely resolved.
> It "looks random" because the robots don't coordinate, so when/where they
> nearly-hit is unpredictable — and the random policy is un-seeded, so it swings
> run-to-run. The real cost of "not considering other robots" does not show up as
> the clash count — it shows up as stucks and lower throughput.
>
> #3 (why stucks diverge): A clash is a momentary blip ("we both want that cell
> next step"); a stuck is a sustained failure — a robot sat too long and gave up.
> FIFO robots have a committed, sensible destination, so a clash reroutes cleanly
> and they keep progressing. Random robots chase a new random target ~every step,
> so contention has no coherent escape destination → they thrash, make no net
> progress, and the stuck-timer trips. Rerouting only rescues you if you have a
> sensible place to go — FIFO does, random doesn't. So collisions look similar
> (contention happens to both), but stucks diverge massively.

**DECISION (pending build) — move to a REAL-collision model via our own movement.**
The current "Collisions" metric is really TA-RWARE's conflict-AVOIDANCE
(rerouting), which is misleading AND architecturally wrong for us: collision
avoidance is the PLANNER's job (Part A/D + ADG), not the simulator's. User wants
the sim to just let robots actually collide (allow brief overlap, count it, let
them separate next step) — no auto-reroute. Reality check (verified in code):
TA-RWARE's movement assumes ONE agent per cell (grid layers store agent id at a
cell; picker-loading + pathfinding read them), so real overlap can't be a small
tweak — it needs replacing the macro-action+A*+clash-fixing execution with our
own dumb per-step movement (= Stage-0 "simulator" / Option B). Conceptually
simpler in our own model (positions as a list, collision = same cell, no
avoidance). Interim: relabel the metric "Conflicts (avoided)" so it's honest
until real collisions land. Awaiting green light to build the own-movement core.

**SUPERSEDED 2026-07-06 — keep the avoidance (reroute) model; do NOT build real
collisions.** User reconsidered: keeping collision-avoidance is fine. But then the
mechanic must be named honestly as **rerouting**, not "collision," because a
reroute is what actually happens AND it costs energy (a longer path — already
captured implicitly as extra drive drain). Actions taken:
- Dashboard metric renamed **"Reroutes"**; README + FINDINGS reworded from
  collision → reroute ("risk of rerouting" instead of "collision risk").
- **Terminology rule going forward:** the sim's `clashes` metric = REROUTES
  (avoid-conflict events), never "collisions."

**FUTURE IDEA (do NOT implement yet) — reroute OR wait as a decision point.**
Rather than auto-rerouting/auto-waiting, every time a robot has to reroute OR
wait (for an unforeseen approaching conflict), it enters an INTERRUPTED state;
after one cell / one wait-step it DECIDES: continue/commit to the reroute-or-wait,
or ditch the task entirely (recover + take another task). This maps onto the
plan's struggle→re-open-the-menu (Part B) and makes both reroute AND wait scored
support actions, not freebies. Context (user's framing): planning-time deletion
removes FORESEEABLE collisions up front so execution avoidance is only needed for
UNFORESEEN conflicts — and each such reroute/wait then triggers a decision path.
Deferred — noted only.

**Clarification — foreseeable collision → new route, not a patch; and reroute IS
ranked.** Two cases, same machinery (generate candidate routes + rank), different
timing/start:
- FORESEEABLE (collision with a KNOWN committed path): the colliding candidate is
  deleted (illegal); planner picks a genuinely different route — one of Part A's
  3-5 Yen's k-shortest alternatives (from the start). So you avoid the collision
  point entirely, never "drive to it and patch." That's the improvement
  (avoid > drive-and-correct).
- UNFORESEEN (emerges mid-run — new assignment / disturbance / timing drift): can't
  pre-delete. The conflict is a struggle signal → RE-OPEN the menu → regenerate
  candidate routes FROM THE CURRENT POSITION and RANK them (deadline/battery/risk),
  like a fresh Part A/B decision. So the reroute-continuation IS ranked, never a
  blind continue.
Net: reroute = a re-ranked replan from where the robot is; foreseeable = rank
upfront from start (colliding routes deleted), unforeseen = re-rank mid-run.

**Clarification — shortest+repair vs k-shortest (for foreseeable collisions).**
Shortest-then-patch-at-collision is cheaper but STRICTLY WEAKER — a degenerate
form of k-shortest, not a rival to it:
- Local repair is myopic (shortest-until-conflict + detour); Yen's likely already
  contains that repair as ONE of its k, plus better complete alternatives. Repair
  = one deviation; k-shortest = top-k deviations, ranked.
- For FORESEEABLE conflicts, patching wastes the foresight: you know the other's
  path at planning time, so plan a clean route from the start (repair is an
  execution-time tool used on a planning problem).
- k-shortest is load-bearing for two plan features repair loses: (a) ranking needs
  several COMPLETE candidates; (b) the feasibility-ratio robustness bonus (3
  surviving routes > 1). Repair gives one route → both signals gone. Repair can
  also collide with a THIRD path → cascade.
Decision: KEEP k-shortest. BUT worth a tiered/lazy optimization — compute shortest
first; if collision-free (common case) use it and skip Yen's; generate full
k-shortest only when the shortest is illegal or when the robustness signal is
wanted. Fits the plan's "cheap screen first, expensive step only when needed."

**REFINEMENT (corrected an overstatement).** It is NOT always worse, and
planning-time patch does NOT "waste foresight":
- "Globally worse" = on the FULL utility (deadline/battery/risk), not raw
  distance, and ONLY when a structurally-different route scores better. Example:
  shortest+repair stays in congested/high-disturbance aisle A (24 cells, 2 risky
  cells); k-shortest surfaces aisle B (23 cells, no risk) → B wins on the utility;
  the local patch can't see B (anchored to the shortest). If no better structural
  alternative exists (clean world / B blocked), the patch IS best and cheaper.
- Value of divergent COMPLETE routes is highest in LUMPY environments (congestion,
  region-varying disturbances, tight deadlines); marginal in a clean/empty world.
- "Wasting foresight" was an overstatement: a PLANNING-TIME patch (detect
  collision in the candidate, repair it) uses the known path fine and is faster
  (cheaper compute). The critique only holds for driving-to-collision-then-reroute
  at EXECUTION. Planning-time patch's only real cost vs k-shortest: it yields ONE
  route (loses ranking-among-alternatives + feasibility-ratio robustness) and can
  miss a better global route when lumpy. Neither dominates always → tiered.

**KEY INSIGHT (user) — the patch is a MEMBER of k-shortest, not a rival.** Yen's
generates "spur" paths: follow the shortest, deviate at one node, rejoin. So a
"keep-most-of-the-good-route, detour-only-around-the-collision" route IS a Yen's
variant by construction — the patch is already in the k-shortest set. And since
Yen's orders by length, that minimal-deviation variant ranks EARLY; you only get
the big "jump" to a structurally different route when the local detour is actually
worse. So k-shortest hands you the whole spectrum (local-patch → full-alternative)
in one ranked set, scored on the full utility → a separate patch step is
REDUNDANT. Cleaner framing than "patch vs k-shortest": the patch is a case OF
k-shortest. (Tiered optimization survives, but now only decides WHEN to run Yen's
at all — skip when the shortest is already collision-free; once run, no manual
patching.)

**Nuance on the "twist" (corrected an intuition).** A local "twist" (detour
around the blocked cell, rejoin) is usually the SHORTEST avoiding option (adds a
couple of cells), NOT the longest — so it's not generally true that "shorter
non-twist paths exist." A structurally different route (whole different aisle) is
usually a BIGGER length change. Non-twist wins only when geometry makes the local
detour awkward (walls force a long doubling-back) and a parallel aisle is cheaper.
Punchline unchanged: you don't reason about which case — Yen's generates BOTH the
tiny twist and the clean alternatives and ranks them, so the winner is always in
the set. The patch is redundant because it's ALWAYS a ranked candidate (best or
not), not because non-twist paths are usually shorter.

**No "rerouting prescreen" needed.** Foreseeable conflict → deleted + avoiding
route already a ranked k-shortest candidate (nothing to prescreen). Unforeseeable
→ can't prescreen by definition; handled at execution by re-opening the menu. So
a reroute-prescreen step has no job.

**BACKLOG CANDIDATE (do NOT add to plan yet) — a "reroute-risk" scoring factor.**
User's sharp distinction: current design has collision FEASIBILITY (binary: delete
if it hits a KNOWN committed path) but no collision RISK (probability of a FUTURE
conflict), because the check only sees what's there now. Proposed factor: given
future areas of focus (demand), estimate the chance a route will HAVE to reroute
later. Assessment:
- Mostly ALREADY captured by the delay head: per plan §3.8 it predicts lateness
  from congestion features (nearby robots, route overlaps, narrow cells) — that
  predicted delay IS the expected cost of waiting/rerouting around robots
  (prob × cost folded in). So current-congestion reroute-risk is already priced.
- The GENUINELY new part is FORWARD-LOOKING: use the demand model to anticipate
  where robots will concentrate LATER → is this a real, novel refinement, but the
  hard part (predicting future assignments from exogenous demand) and easy to
  over-engineer.
Decision: keep as a BACKLOG candidate, NOT in the plan `.docx`. Reasons: (1)
unproven — must beat the delay head alone by ≥3% in ablation (§5.4) to earn a
spot; (2) depends on components that don't exist yet (delay head = Stage 3, demand
model = Stage 4) — can't build it until then; (3) keep the plan lean/proven; its
machinery can already absorb this as another head input. Promote into the plan IF
it proves out.

**Link — the reroute-risk INPUT already exists (demand model / Part C).** Part C
benefit #1 already does per-region future-task counting: "the arrival rate near
Station A says how often orders pop up there → future_area_action_value = chance ×
value × closeness × fit" (PartC). The engine is the demand model (§3.5: "per-region
frequency counting... Feeds Part C only"). So the "future areas of focus" a
reroute-risk factor needs = the demand model's per-region output; reroute-risk
would be a SECOND consumer of it, no new input machinery. Subtle tension (coherent,
not contradictory): Part C uses demand to pull robots TOWARD future-work areas
(be ready); reroute-risk would use the same signal to AVOID routing THROUGH them
(they get crowded). The utility already balances this — Part C closeness *value*
vs the delay head's congestion *cost*.

---

## 2026-07-07 — Deadlines: plumbing built (no model), per user

User: keep reroute-risk in the back pocket (NOT in the plan) ✓ (logged as backlog).
Start deadlines, but PLUMBING ONLY — feed a task→deadline doc/text into the sim,
extract, attach to tasks; no deadline-generation model yet.

Built: `Shelf.deadline` slot; `wwm_sim/deadlines.py` (`load_deadlines` accepts a
file path OR raw pasted text — the "text box" path; tolerant format
whitespace/comma/colon, `#` comments; `attach_deadlines(env, dl)` sets
`sh.deadline` by id, None if absent); example `data/deadlines_example.txt` (seed-0
tasks); demo `scripts/deadlines_demo.py`. A task = a requested shelf (by id);
deadline = absolute sim step to deliver by (relative/arrival-based = future
refinement). Verified: file path attaches all 20 seed-0 tasks; inline
"15 200; 42: 180; 18,240" attaches those 3, rest None. TODO (later): deadline
model, deadline-met metric, feed into Part A scoring.

**Clarification — are battery metrics uniform across "types of simulation"?**
- Across POLICIES (FIFO/random) + env layouts: YES, all battery CONSTANTS are
  uniform (one `BatteryConfig`, policy/layout-independent) → that's the CSV's
  invariant block. Only charger PLACEMENT varies (defaults to goal cells).
  Outcomes (min/end batt, strandings) differ by policy = the results, not consts.
- Across ROBOT TYPES (AGV vs Picker): mostly uniform, deliberately not fully.
  SAME for both: drive drain, idle drain, charge rate, floor, start, capacity
  (`steps_per_charge`=300). PER-TYPE: carrying_penalty (AGV only, while carrying)
  and pick_penalty (Picker only, per pick).
- HONEST FLAG / simplification: capacity is currently the SAME for both types
  (single steps_per_charge) — does NOT model the ~4x real battery-size gap
  (RB-VOGUI 720 Wh carrier vs RB-KAIROS+ 2.78 kWh picker). Per-type capacity would
  need splitting the config into AGV/Picker variants; deferred.

---

## 2026-07-07 — Pivot: single sim + PRIORITY (deadline) task assignment

User: sim no longer needs FIFO-vs-random side by side — one simulator now; and
task assignment must be PRIORITY-first, not FIFO. Priority is supreme (new urgent
tasks still take precedence). For now priority = deadline distance (deadline −
now). Show tasks ranked by deadline to verify ordering.

Built: `PriorityController(FIFOController)` overriding `_task_order()` to sort the
request queue by deadline (soonest first; None last), re-sorted every step. Tiny
refactor: `FIFOController.act()` now iterates `self._task_order()` (base = FIFO
queue order) so subclasses can override. New single-sim dashboard
`scripts/sim_priority.py` (grid + legend + DEADLINE-RANKED task panel + battery +
reroute pairs + stats); loads/attaches deadlines from `data/deadlines_example.txt`
(regenerated with SCRAMBLED deadlines so priority != FIFO is visible).

Semantics: NON-PREEMPTIVE — free robots grab the most-urgent unassigned task
(incl. newly-arrived), but an in-progress robot keeps its task. Full preemption
(yank a robot off for a newer more-urgent task) = future option.

Verified (seed 0): PRIORITY delivers low-deadline shelves first
(140/149/147/177/170/207); FIFO ignores deadlines (325/304/436/406/...). Delivery
order slightly non-monotonic because urgent task → NEAREST free AGV (travel
jitter); ASSIGNMENT is strictly priority-ordered. `sim_dashboard.py` kept as the
FIFO-vs-random baseline. TODO: multi-factor priority (Part A: + distance/battery/
risk), preemption option, deadline-met metric.

---

## 2026-07-07 — Picker dispatch fix (ranked-priority pickers) + battery-simplicity call

**Why AGVs sit idle (user asked):** an AGV can't load/unload a shelf without a
picker on the SAME cell (warehouse.py:536). Diagnosed: ~52% of AGV-steps
stationary, 41%+ of that is at-shelf-waiting-for-picker. 2 pickers / 3 AGVs =
structural bottleneck (not battery, not choice).

**Fix = ranked-priority pickers (user's ask).** Refactored `FIFOController` picker
logic into an overridable `_dispatch_pickers()` (base = zone-based). New
`PriorityController._dispatch_pickers`: nearest free picker → most-urgent
(soonest-deadline) waiting AGV; keeps a picker parked at a rendezvous until the
AGV loads. Measured (500 steps, seed 0): deliveries 21→24 (+3), AGV picker-wait
422→357 (−65). FIFO base unchanged (22). Honest cap: 357 wait-steps remain — 2
pickers can't serve 3 AGVs at once; better dispatch ≠ removing the cap (more
pickers = config change). "Made more complex later" per user (pickers could also
weigh battery/distance/batching).

**Battery-simplicity call (user asked):** KEEP flat `pick_penalty` per pick — do
NOT scale picker battery by items-picked/weight/shelf-contents. Already the simple
version; per-item scaling deferred (add only if it earns its place).

**Robot mechanics documented** in README ("How the robots work"): AGV carry +
Picker load cooperation; load needs same-cell rendezvous; AGV state machine
PICKING→DELIVERING→RETURNING→free; 1 cell/step A* movement; battery + task
lifecycle.

**Two-subtask task format (user).** User's framing: each task = 2 subtasks (AGV
part + Picker part). Changed `sim_priority.py` task panel to show, per task ranked
by deadline: `AGV subtask` (fetch/carry/return) + `Picker subtask` (coming/loading/
none). Makes coordination + bottleneck visible in one view: e.g. at step 8, the 3
soonest tasks all have an AGV fetching, both pickers go to the 2 MOST-urgent, and
the 3rd AGV shows "picker: none" (both busy) → it will wait. Confirms priority-
ranked pickers working AND shows the 2-picker cap. Internal model still tracks
AGV missions + picker dispatch separately; explicit subtask objects = later option.

---

## 2026-07-07 — Learnings to remember (pickers, env size, deadline priority)

- **Pickers must be physically present at a shelf to load it** → so we now
  priority-assign PICKERS too, on the same deadline priority as AGVs/tasks. This
  adds a new coordination variable: a picker's **"coming" (en-route) state** — a
  task whose picker is already on the way is closer to done. NOT modeled as a
  scoring factor yet; probably in play LATER, not now.
- **The env was too small** (tiny 15×14 looked cramped). Switched the priority
  sim's default to **large** (35×22, 8 AGV + 4 pickers, 240 shelves).
- **Not enough pickers for every AGV.** Tiny had 2 pickers / 3 AGVs; large has
  4 / 8 (a 2:1 ratio — proportionally even fewer pickers). So AGVs wait at shelves
  for pickers → some deadline misses, compounded by there being no priority
  assignment before. Lever for picker-limited throughput = MORE pickers (config),
  not more dispatch cleverness.
- **Deadline-based priority assignment works** (verified). Other battery
  attributes uniform / fine (see earlier uniformity CSV).

---

## 2026-07-07 — Feasibility-aware priority + dashboard fixes + Robotnik throughput

**Dashboard fixes (`sim_priority.py`):** marker sizes now scale with grid
(`4500/span`, `2600/span`) so they fit the large env; removed redundant grid
title (suptitle no longer clumped); **charger cells highlighted GOLD** (`C_CHARGER`,
+ colour key under the grid); **completed-tasks list** added (recent shelf ids +
total). Task panel now shows the CONTROLLER's actual order and marks expired
deadlines "(over*)".

**Feasibility-aware priority (`FeasiblePriorityController`, user's spec):** 3-tier
`_task_order` — tier0 urgent&feasible (deadline in next `window`=83 steps = measured
avg completion), tier1 feasible-not-urgent, tier2 no-deadline, tier3 EXPIRED
(deadline<now, shoved to bottom). Dashboard defaults to it (`--controller feasible|
priority`).

**Robotnik realistic throughput (research):** RB-KAIROS+ 1.5 m/s (robotnik.eu).
First-principles cycle in large warehouse ~60-65 s/task → ~8 tasks per dedicated
(1:1) AGV+picker pair per 500 s. Sim does ~4-5/AGV (2:1 picker starvation).

**KEY RESULT — first feasibility attempt (shed only EXPIRED, deadline<now) barely
helped (38.2→39.8%). The CORRECTED slack-aware version WINS.** Proper threshold:
shed UN-MAKEABLE tasks (deadline−now < window≈83 = completion time) — a task due
sooner than you can finish it is already doomed. Bake-off (10 trials): FIFO 55.9%
(17.4 on-time) · naive EDF 38.2% (13.2) · **SLACK-AWARE/FEASIBLE-EDF 73.0% (25.4)
— WINS**. `FeasiblePriorityController` updated to this; dashboard default. Why it
works (user asked): under overload you WILL miss some — give up the impossible
(guaranteed misses), guarantee the makeable (high-slack = safe), don't chase
fragile/doomed urgent tasks (miss them + collateral). Caveat: equal values →
maximises on-time COUNT; value×P(on-time) needs task values (Part A).

**CURRENT PRIORITY FORMULA (reference — updated to VALUE-aware).** Still a
lexicographic sort key, now 3-level, per task s (deadline d, value v [default 1],
now, W=83 est completion): `key(s) = (tier, −v, d)`, ascending, where tier = 0 if
d≠None and (d−now)≥W (MAKEABLE), 1 if DOOMED (d−now<W), 2 if d=None. I.e. among
makeable, HIGHEST-VALUE first, deadline as tie-break; doomed shoved to bottom. =
`value × P(on-time)` with a HARD makeable/doomed P. Drives AGV assignment (tasks
in key order → nearest free AGV) + picker dispatch (nearest picker → most-urgent
waiting AGV). Controllers: `value` (default) / `feasible` (value-blind) / `priority`
(naive EDF). NOT included yet (= Part A next): SMOOTH P(on-time) (currently hard
cutoff), distance/travel cost, battery, disturbance risk. Task value = reward for
ON-TIME delivery, loaded via `wwm_sim/values.py` (plumbing; no model).

**Behaviour over time (clarification).** Early on it IS pure naive EDF: at now=0
all deadlines (110-450) ≥ now+W=83 → all MAKEABLE (tier 0) → sorts by deadline
only. The feasibility filter is dormant. As now climbs, tasks flip to DOOMED when
now > d−W (deadline gets closer than you can finish) and drop to the bottom — so
the formula diverges from EDF progressively. IMPORTANT nuance: slack is only a
BINARY makeable/doomed FILTER (drop the impossible), NOT a smooth "prefer high
slack" preference — within the makeable set it's still pure EDF (most-urgent
makeable first, incl. fragile-but-makeable, to bank them before they're lost). So:
"EDF + a feasibility filter that switches on gradually as the clock advances."

**PLAN .docx EDIT — flagged, NOT done, needs user confirmation.** User asked to
rename "collision" → "risk of rerouting" in the original plan docs too. IMPORTANT
distinction: in the plan, "collision" means the **planner deleting colliding
routes at planning time** ("Collisions = 0 absolute", "crashes are deletions,
never prices") — a HARD safety-by-construction guarantee. That is a DIFFERENT
(and stronger) concept than execution-time rerouting. Blanket-renaming it would
replace a hard guarantee with a softer reroute model = a real DESIGN change, not
a rename. So the sim-side docs were reworded, but the plan `.docx` was left
untouched pending user's call: (a) truly pivot the plan to a rerouting model, or
(b) keep the plan's collision-deletion thesis and only fix sim terminology.

**RESOLVED — user chose (b).** Plan's collision-deletion thesis KEPT. Added one
complementary paragraph to `PartB_Plain.docx` (after "Big lateness triggers a
rethink"): rerouting is an execution-time support action with an energy/time cost
(not free), distinct from planning-time collision-deletion, and a FUTURE
refinement makes it a decision point (interrupt → keep rerouting or ditch+recover).
Also added a **reroute-pairs panel** to the dashboard: per policy, lists which
robot pairs rerouted + counts; totals match the "Reroutes" metric (verified 11/17
on seed 0). Only AGVs appear (pickers exempt at loading cells by design).

**Clarification — can you have BOTH "collision" and "reroute", if robots never
actually collide?** Yes; they measure different things, no contradiction:
- A COLLISION is the EVENT (two robots, one cell) → a SAFETY INVARIANT, always 0;
  >0 means a filter has a bug. It's the outcome we verify.
- A REROUTE / wait / deletion is a MECHANISM + COST → the work done to keep that
  event at 0 (energy/effort). A run can be 0 collisions + 500 reroutes (safe but
  inefficient) — hence track both.
Collisions stay 0 via TWO layers catching DIFFERENT conflicts: (1) planning-time
deletion (route that would hit a KNOWN path is deleted, never reaches execution);
(2) execution-time avoidance of UNFORESEEN conflicts — in the plan by WAITING
(ADG take-turns ordering), in the TA-RWARE sim by auto-rerouting. Each conflict is
caught by exactly one layer (known→delete, unforeseen→wait/reroute) → they
partition, don't overlap. There is ONE risk (potential collision) and several
neutralizers. Edge case: if avoidance finds no path, the robot waits/stops →
becomes a STUCK, never a collision; the guarantee holds.

**(C) 3-trial verification (`scripts/verify_trials.py`, seeds 0/1/2): ALL PASS.**
FIFO deliveries 22/20/17, random 0-1; FIFO stucks 0, random 30-33; battery
drains to 0-7%, 1 picker strands each seed. Subtlety caught & explained: picks
can exceed deliveries by ≤ nAGVs — an AGV that picked up a shelf but hadn't
reached a dock when the 500-step episode ended (in-transit), NOT a bug. Correct
invariant is `0 ≤ picks − deliveries ≤ nAGVs`. **Why it works:** FIFO serves the
queue in order → nearest free AGV → clean fetch→deliver→return cycles →
coordinated, high throughput, never wedges (0 stucks). Random picks uniform
targets → no coordination → wedges into dead-ends (30+ stucks), ~0 deliveries.
Battery event-counting (pick = AGV load transition) stays consistent with the
sim's own delivery counter. (Random deliveries vary run-to-run because action
sampling isn't tied to the episode seed; FIFO is deterministic.)

---

## 2026-07-04 — Battery calibration robot: vendor comparison → Robotnik chosen

Iterated through AMR vendors to ground the two robot types (carrier=AGV,
picker=Picker). Requirements: a real arm-picker (to ground `pick_penalty`) + a
carrier, modern Li-ion, verifiable specs, ideally one platform.

- **Quicktron** (M60/C56): TA-RWARE's inspiration, but specs thin/unverified; C56
  "picker" is really a shelf carrier. Rejected.
- **Fetch + Freight**: true warehouse carrier + arm-picker (6 kg arm), but OLDER
  **SLA** batteries, Wh only derived. Superseded.
- **PAL TIAGo + TIAGo Base**: Li-ion 720 Wh, 7-DoF 3 kg arm, full clean datasheet.
  Good, but service-scale (3 kg arm) and I over-favored it just because I had its
  PDF — not a real advantage.
- **Robotnik RB-VOGUI (carrier) + RB-KAIROS+ (= base + UR arm, picker) — CHOSEN.**
  Reasons: (1) UR e-Series arm (7.5–16 kg) → better-documented, bigger pick
  grounding than TIAGo's 3 kg; (2) cleanest structural match — KAIROS+ is literally
  a VOGUI base + arm, so carrier & picker share IDENTICAL drive/battery physics,
  differing only by the arm → maps exactly to our model (shared drive/battery;
  AGV `carrying_penalty` vs Picker `pick_penalty`); (3) modern Li-ion 2.78 kWh,
  industrial/warehouse scale, ROS 2. TIAGo's only edges (one tidy PDF, lighter,
  academic pedigree) don't outweigh these.

Data note: Robotnik's full PDF is registration-gated, but public page + QVIRO
give ~all needed fields (arm payload/reach, 48 V×58 Ah = 2.78 kWh, ~6 h runtime,
100–250 kg platform payload, 1.5 m/s, 115 kg). Charge time unpublished for BOTH
Robotnik and TIAGo (use Li-ion norm ~1–2 h). **QVIRO = third-party robot-spec
comparison website (a source/catalog), NOT a robot and NOT a Robotnik product.**

**Terminology (user asked):** RB-VOGUI = wheeled base, no arm = CARRIER (AGV);
RB-KAIROS+ = same base + a Universal Robots arm = PICKER; difference = just the
arm (truck vs. truck-with-crane). Same base → same drive/battery physics.

---

## 2026-07-09 — Congestion/collision-risk map — detailed specifics (back-pocket)

Framing: really a CONGESTION/DELAY-risk map — collisions stay 0 by construction
(deletion + ADG), so this predicts where robots must REROUTE/WAIT to avoid each
other (the cost of avoidance), not crashes.

A. Representation: per-cell risk [0,1] (P(delay/reroute here)) or expected-traffic
   count; optionally TIME-INDEXED (space-time: risk(cell, future-window)); optionally
   EDGE-based too (swap/head-on); optionally net flow direction per cell.
B. Input layers: (1) busy robots' PLANNED paths -> space-time reservation/occupancy
   count (MAPF reservation-table idea); (2) HISTORY -> decayed count of where
   clashes/reroutes/stucks actually happened (event count + time decay, like the
   disturbance map); (3) TASK PLACEMENT -> density of open shelves + docks + chargers
   (convergence magnets), extend with demand model for FUTURE density; (4 add)
   STRUCTURAL chokepoints -> static, from layout graph (narrow aisles, dock
   approaches, high betweenness-centrality cells).
C. Time: static aggregate (simplest) vs time-bucketed space-time (arrival-aware).
D. Combine: weighted sum of layers -> one field; weights TUNABLE (Optuna); calibrate.
E. Consumers: route gen/selection (congestion as edge cost in A*/Yen's, or penalize
   k-routes); delay/P(interrupt) estimate (feature to delay head or analytic formula);
   reroute-risk term (sum map-risk along a route); task assignment load-balancing;
   rendezvous-alignment (congestion -> arrival uncertainty); Part C positioning.
F. Update: rebuild planned-path layer each decision event; history layer increments
   on clash/reroute/stuck + decays (tunable half-life); task layer from current
   queue+demand; incremental vs full rebuild.
G. Validation: calibration (cells called X% congested see ~X%; Brier/reliability);
   predictive (does high risk predict actual reroutes/stucks); ablation (with vs
   without map -> fewer reroutes/stucks/delay; >=3%-or-cut).
H. Cheap-first (analytic weighted sum, Stage 0/1) vs learned (head predicting per-cell
   reroute-prob, or map as feature to delay head, Stage 3).
I. Relationship: COMPLEMENTS the disturbance rumor map (this=KNOWN congestion from
   plans+history+layout; that=HIDDEN hazards inferred from struggle) — two parallel
   belief layers; feeds delay head + reroute-risk; overlaps demand model; does NOT
   touch collisions=0 guarantee.
J. Open decisions: cell vs edge vs both; static vs space-time; probability vs raw
   score; whole-grid vs hot-corridors-only (speed); layer weights; history decay;
   trust in committed plans (hard reservation vs soft occupancy).

**EXACT open-source formulas to COPY (user: reuse, don't reinvent).** MAPF's
sophisticated congestion heatmaps (Guidance-Graph Optimization, Zhang 2024) are
LEARNED (CMA-ES/CNN), no closed-form usage->weight eqn. But two exact public
formulas map cleanly:
1. Planned-paths occupancy layer = MAPF RESERVATION TABLE (Silver, Cooperative
   Pathfinding 2005 — standard, in every MAPF codebase): reserve (x,y,t) for each
   committed path; occupancy(x,y)=|paths through (x,y)| (or (x,y,t) space-time).
2. usage -> cost/delay = BPR volume-delay function (US Bureau of Public Roads
   1964, public domain): w = w0·(1 + α·(usage/capacity)^β), α=0.15, β=4;
   usage=occupancy from (1), capacity=1 for single-agent cell (higher for wide
   corridors), w0=free-flow cost. Output = congestion-inflated edge weight (for
   A*/Yen's routing) AND a delay estimate (for delay head / reroute-risk).
History + task-density layers = simple decaying counters (no formula to copy).
Learned guidance-graph optimization = Stage-3+ upgrade if BPR analytic plateaus.
Sources: aaai Cooperative Pathfinding (Silver); BPR VDF; arxiv 2402.01446 (GGO).

## 2026-07-09 — collision map demoted; Part B rendezvous-alignment reverted

**Collision/congestion-risk map is likely NOT needed as its own mechanism.** User's
point: the planner ALREADY accounts for where robots converge, twice over —
- Part A scores each candidate plan AGAINST THE BUSY robots' committed paths (their
  future cell occupancy), so a route into a congested corridor already looks worse.
- Part D scores the JOINT plan (all robots signed up together), so mutual
  interference is priced at commit time.
So a separate spatial congestion field would mostly re-derive what Part A/D see. Kept
the exact formulas (reservation table + BPR) recorded above as back-pocket reference,
but the map is DEMOTED — build only if Part A/D prove insufficient in ablation.

**Part B rendezvous-alignment (arrival-aligned picker dispatch) — built, tested, then
REVERTED at user request.** Prototype `AlignedValueController` added an ETA estimate
(committed-path remaining length, else Manhattan + buffer B) and a just-in-time picker
dispatch (send the picker whose ETA matches the AGV's, so scarce pickers aren't tied
up waiting early). 10-seed bake-off vs the `value` default: picker-wait proxy -6%
(1011->949 steps), deliveries +3% (33.6->34.7), on-time VALUE ~flat (200.8->197.6).
A making-pickers-value-aware variant DEADLOCKED (doomed AGVs starved of a picker sit
forever; seed 3 collapsed 34->9 deliveries) — lesson: picker SERVICE order must stay
deadline-urgency, value belongs in TASK selection. User chose to revert the whole
Part B alignment prototype for now (it's a real Part A/B scoring term for later, needs
the rollout engine + delay head for true arrival uncertainty). Code removed;
`sim_priority.py` back to priority/feasible/value.

## 2026-07-09 — adaptive window; value-threshold tested and rejected

**Doomed-cutoff `window` is now ADAPTIVE (was a fixed 83).** The base controller
measures every task's actual assign->deliver duration; `FeasiblePriorityController.
window` returns the running mean of the last ~60 completions (fallback 83 until 5 have
completed). It self-calibrates to the fleet + congestion over time.
Measured averages: 8 AGV/4 picker = 68.7 steps; 12 AGV/8 picker = 59.6 steps (more
pickers -> less rendezvous wait -> faster tasks, ~59 vs ~34 tasks/episode). The old
fixed 83 was OVER-shedding (marking makeable tasks doomed): switching to adaptive
raised VALUE on-time value 200.8 -> 206.6 at 8/4 (10 seeds). 12-AGV/8-picker env
(`wwm_sim-large-12agvs-8pickers-globalobs-v1`) already registered; window handles it
automatically. Knobs: `_window_min_samples`, `_window_safety` (>1 = shed more
conservatively; a >mean percentile is the robust alternative to the plain mean).

**Value threshold / value-participates-in-shedding — TESTED, REJECTED (made it
worse).** Tried a value-weighted cutoff (low-value tasks shed sooner via a wider
effective window; high-value attempted even when tight): on-time value 206.6 -> 198.9,
on-time count 27.4 -> 25.2 over 10 seeds. Why it hurts: (1) attempting a high-value
task when tight tends to deliver it LATE = zero on-time value AND a robot burned;
(2) shedding a low-value task early just IDLES a robot that could have earned its
(small) value. The current rule (best-value-first among makeable; only the DEADLINE
sheds) is near-right BECAUSE the value-sort already maximally defers low-value tasks —
they run only when nothing better exists, which beats dropping them. So "value only
reorders, doesn't gate" is CORRECT behavior here, not a bug. The real thing the
value-gating intuition points at is OPPORTUNITY COST: once started, a low-value task
ties up a robot ~60 steps (non-preemptive), during which a high-value task may arrive
unserved. Gating on that needs a DEMAND model (how likely is high-value demand soon) =
the plan's Part C (future-readiness / deferred commitment), not a static value floor.

## 2026-07-09 — partial-credit TOTAL value (late keeps 80%)

Q: on-time value is all-or-nothing (late = 0). If instead a LATE delivery keeps 80%
of its value (sheds 20%), which of DEADLINE- vs VALUE-based wins TOTAL value?
Metric: total = Σ(value if on-time, else 0.8×value if delivered late, else 0). 10
seeds, 8 AGV/4 picker.
  strategy   deliv on-time late  on-time_val late_val  TOTAL(80% late)
  FIFO       31.1  17.4    13.7   97.5        81.3      162.5
  DEADLINE   34.6  20.5    14.1  111.5        81.4      176.6
  VALUE      34.2  27.4     6.8  206.6        53.9      249.7
VALUE wins total value too (249.7 vs 176.6, +41%). But partial credit NARROWS its
lead: +85% on on-time value -> +41% on total value, because deadline-based's many
late deliveries (14.1 vs 6.8) get rescued to 80% instead of 0. VALUE still wins by
converting HIGH-value tasks to FULL credit (its late value is only 53.9 vs 81.4).
Reminder — on-time value = Σ value×(1 if delivered before deadline else 0); late or
undelivered = 0.
META-POINT: under a partial-credit metric, SHEDDING doomed tasks is suboptimal — a
doomed task delivered late is worth 0.8×value > the 0 from dropping it. All three
strategies still shove doomed to the bottom (a habit from the on-time objective), so
they leave value on the floor here. A total-value-optimal policy would STOP shedding
and deliver everything on-time-first. Untested variant, flagged for later.

## 2026-07-09 — effective-value ranking (discount doomed, don't shed)

Idea (user): don't zero/hard-tier doomed tasks — discount to 70% of value and rank
ALL tasks on one effective-value scale (eff = value×0.7 if doomed else value; deadline
tiebreak). A high-value doomed task then outranks a low-value makeable one and gets
done quickly, instead of being stuck below every makeable task.
Test (10 seeds, 8/4, doomed keep = late credit = 0.7):
  strategy               deliv on-time late  ON-TIME_val  TOTAL(70% late)
  VALUE (sheds doomed)   34.2  27.4    6.8   206.6        244.3
  EFF70 (discount)       34.7  22.6    12.1  184.6        248.9
Result: EFF70 WINS total value (248.9 > 244.3) — confirms discounting beats shedding/
zeroing when late retains value. BUT small (+2%) and it costs on-time value (−11%):
it pulls robots toward doomed/late work (12.1 vs 6.8 late), converting full-value
on-time deliveries into 70%-value late ones. Win is only 2% because shedding was never
"never do" (shove-to-bottom still does doomed tasks when robots are free), so most
recoverable value was already captured.
METRIC DECIDES (they cross over): on-time/SLA objective (late=0) -> keep SHEDDING
(VALUE wins 206.6 vs 184.6); total-value objective (late keeps k) -> effective-value
DISCOUNT, with the ranking discount SET EQUAL to the metric's late credit k. When
they match, eff-value ranking = "do the highest expected-value task next" = the
correct greedy rule for total value.
Terminology clarified: value RANKING (order among makeable; value>deadline) = the
winner; value-WEIGHTED SHEDDING (value moves the doomed cutoff) = the earlier loser;
effective-value DISCOUNT (this) = a third thing, right for the partial-credit metric.
Not promoted to a permanent controller yet (marginal; metric-dependent) — offer open.

## 2026-07-09 — discount sweep k; the flat-discount tradeoff is a Pareto dial

Swept the doomed ranking discount k (eff = value*k if doomed). 6 seeds, 8/4.
  policy       on-time late ON-TIMEval tot@.7 tot@.8 tot@.9
  VALUE(shed)  27.0    7.0  202.3      243.8  249.7  255.6
  EFF k=0.3    25.5    8.0  198.5      244.3  250.9  257.4
  EFF k=0.4    25.0    8.5  195.8      245.4  252.5  259.6
  EFF k=0.5    24.0    9.8  191.7      247.7  255.7  263.7
MONOTONIC TRADEOFF: as k rises, total value up, on-time value down, every step.
k=0.3 nominally meets "comparable on-time (198.5 vs 202.3, -1.9%) + greater total at
every credit" — but +0.5% total for -1.9% on-time is within 6-seed noise. No flat k
wins BIG on both; VALUE sits at the on-time end of a Pareto frontier.
WHY no free lunch: VALUE already mops up doomed tasks with OTHERWISE-IDLE robots (it
shelves doomed below makeable but keeps them in queue; a free robot with no makeable
task grabs the top doomed one -> its ~7 late deliveries). So "free" late deliveries
are already captured; extra total from a bigger discount can only come from DISPLACING
makeable work -> costs on-time. A flat discount only reranks; can't add total without
subtracting on-time.
THE UNLOCK (user's "rush high-value late tasks fast") needs a PER-STEP-DECAY penalty,
not flat k: under flat credit WHEN you deliver a late task is irrelevant (k regardless),
so nothing to rush. Under decay (little-late ~= near-full, very-late ~= little),
delivering a slipping high-value task SOONER recovers more — and you can do it by
REORDERING the doomed tasks idle robots were already going to do, WITHOUT displacing
makeable work => a potential real Pareto gain the flat-k model structurally can't see.
NEXT: implement lateness-decay value (value * g^lateness or value*max(floor,1-late/L))
+ rush-order doomed by value/urgency; test whether it beats VALUE on total WITHOUT
losing on-time. This is the metric-honest version of task value.

## 2026-07-09 — industry framing: how real warehouses balance on-time vs value

Why this matters: it explains WHY our two-part scheduler is the right shape, not an
arbitrary choice.

INDUSTRY STANDARDS (general fulfillment-ops practice; varies by operation):
- The HEADLINE metric is on-time / SLA compliance — % of orders shipped by their
  carrier CUTOFF ("orders by 2pm ship today"). Orders batch into WAVES tied to carrier
  pickup times; miss the wave -> ships next day -> real cost (customer dissatisfaction,
  sometimes contractual penalty). So warehouses care about late A LOT.
- VALUE/PRIORITY is NOT a replacement for caring about deadlines — it is the RATIONING
  rule under overload: when there's more work than labor, protect the high-priority
  orders' deadlines FIRST (Prime/express/high-value/perishable), let the cheap
  non-urgent stuff slip. "High-value-first" = decides WHO gets their deadline protected.
- LATE-TOLERANCE VARIES BY ORDER TYPE. Hard-SLA/perishable late = near-total loss;
  standard order late = mild (still ships, customer just waits). So partial-credit-for-
  late is realistic for some order classes, not others.
- Real ops SEGMENT orders into CLASSES (hard-cutoff express vs soft standard) and apply
  different urgency per class.
- Scheduling-theory names: our on-time-value goal = "maximize weighted number of
  on-time jobs" (weighted Moore-Hodgson); our total-decayed-value goal = "minimize
  weighted tardiness" (lateness weighted by value). Both are classic; real warehouses
  blend them.

HOW OUR SCHEDULER MAPS TO IT (the whole arc, in order):
1. Deadline-based with the proper MOORE-HODGSON split: makeable (can finish before
   deadline) vs doomed (can't). Makeable first.
2. We VALUATE BOTH ENDS — top and bottom of the pile:
   - TOP (makeable): highest VALUE first (protect the valuable on-time work).
   - BOTTOM (doomed/late): rank by DECAYED value = value * g**lateness (rush the barely-
     late high-value tasks, skip the hopelessly-late ones).
3. The decay g = THE BUSINESS COST OF BEING LATE, and it is the single dial between the
   two goals: steep g (late ~= total loss) -> behaves like on-time/high-value-first,
   shed the doomed; gentle g (late ~= mild) -> rush-ordering harvests recoverable value.
   Per-order-CLASS g mirrors real operations (hard-SLA vs soft orders side by side).
   => You can't maximize on-time AND total value independently past a load; g is the
   knob that sets where on that spectrum you sit.

DECAY-SHAPE INSIGHT (user): exponential decay is right because value SATURATES at the
bottom — "there's a difference between 50 days and 51 days late? they just don't care."
Once a task is very late its value has already decayed near the floor, so one more step
of lateness barely changes it (marginal loss shrinks as lateness grows). That is exactly
what value*g**lateness does. A hard SLA is the limit case (g steep / cliff at the
cutoff); a soft order is a gentle exponential that flattens out once it's clearly late.

## 2026-07-09 — per-task SLA hardness (separate axis from value)

User insight: SLA-vs-soft is NOT captured by value — value = how much (height); SLA
hardness = how fast value decays once late (shape of g). Two tasks, same value, can
have different g; you can't fake a hard SLA with high value (high value + gentle decay
still gets delivered late for value; a hard SLA yields ~0 late regardless).
Built: per-task `Shelf.hardness` (= late-decay g) + `wwm_sim/hardness.py`
(parse/load/attach/task_hardness, mirrors values.py/deadlines.py) +
`data/hardness_example.txt`. RushValueController now uses g = shelf.hardness if set
else global DECAY_G. So each task carries three axes: deadline (when), value (how much),
hardness g (how badly late hurts). Demo (even shelves HARD g=0.90, odd SOFT g=0.995;
3 seeds): HARD on-time 12.7 / late 1.7; SOFT on-time 13.7 / late 7.0 — 81% of late
deliveries are SOFT. Scheduler protects hard orders on-time then DROPS them once doomed
(late hard ~= worthless), and HARVESTS soft orders late (still ~full value) — exactly
the order-class behavior real warehouses segment for, with no special-casing.

## 2026-07-09 — weighted (per-task g) rush verification + a tooling gotcha

RESULT (10 seeds, per-task hardness attached, each task decays at its own g):
  policy  on-time  on-time_value  weighted_total
  VALUE   27.4     206.6          236.6
  RUSH    27.5     206.4          251.4
Headline confirmed with per-task decay: RUSH TIES on-time value (206.4 vs 206.6) and
WINS weighted total (251.4 vs 236.6, +6.3%) — same direction as the global-decay pilot.
CAVEAT: this inline run's `late` count came out ~100 (vs ~7 in 500-step runs) => some
episodes ran past 500 (a t<2000 safety cap masked non-termination), inflating the very-
late tail. Trust the DIRECTION, not the exact weighted magnitude. TODO: re-run with a
hard 500-step assert to get trustworthy absolutes.

TOOLING GOTCHA (cost a lot of time): long sim runs HANG when backgrounded by the harness
or piped `python ... | tail`. Root cause: the python process doesn't EXIT cleanly (gym/
pyglet teardown), so `tail` waits forever for an EOF that never comes, and detached/
backgrounded runs spin instead of finishing. Worse, each hung process keeps spinning and
PINS a CPU core, so failed attempts accumulate and slow every later run ~5x. Reliable
recipe: run inline/foreground in SMALL batches (<~15s), or `python x.py &` writing to a
RESULT FILE + poll the file (don't depend on the process exiting); and kill stragglers
(Get-CimInstance ... python.exe | Stop-Process) between attempts. A single episode is
~0.8-2s; 20 episodes ~40s on a clean field.

## 2026-07-09 — weighted rush verification, HARD 500-step cap (trustworthy absolutes)

Re-ran with every episode hard-capped at exactly 500 steps (fixes the earlier run's
inflated late tail). 10 seeds, per-task hardness attached, each task decays at its own g:
  policy  deliveries on-time late on-time_value weighted_total
  VALUE   34.2       27.4    6.8  206.6         220.1
  RUSH    34.6       27.5    7.1  206.4         229.3
CONFIRMED (trustworthy): RUSH TIES on-time value (206.4 vs 206.6) and WINS weighted
total (229.3 vs 220.1, +4.2%), with late count back to the expected ~7. Supersedes the
earlier caveated numbers (236.6/251.4) that were inflated by episodes running past 500.

## 2026-07-09 — RushValueController promoted to DEFAULT

`RushValueController` ("rush") is now the dashboard + CLI default (was "value"):
sim_priority.py PriorityDashboard(controller="rush"), argparse default="rush", choices
now include "rush". Rationale: it ties the old default on on-time value and wins total
(decayed) value, and it degrades to VALUE when g=1, so it's a strict generalization.
Runs fine without hardness attached (uses global DECAY_G=0.98); attach hardness for
per-task SLA behavior. Other controllers (value/feasible/priority) still selectable via
--controller.

## 2026-07-09 — rollout engine built; per-task window LOST to global window

Built `wwm_sim/rollout.py` (analytic Stage-0 rollout): geom_completion / per_task_window /
rollout_task(env, shelf, agvs, pickers) -> fetch, rendezvous, finish, deadline_margin,
+ optional battery_used/battery_margin. Manhattan distances (cheap), calibrated so the
per-task average matches the adaptive `window`. This is the shared movement/time/battery
model the plan calls for (precursor to the learned heads; needed for Part A scoring).

FIRST APPLICATION TESTED — replace the global doomed-window with a PER-TASK completion
estimate. Bake-off (10 seeds, hard 500-cap):
  policy                 on-time on-time_val weighted_total
  RUSH (global window)   27.5    206.4       229.3
  ROLLOUT (per-task geom)26.7    203.7       228.9
  DOCK (per-task, dock-only, stable) 26.4  202.0  227.3
=> BOTH per-task variants LOSE (on-time -1 to -1.5%, total ~tied). Reason: completion
time here is CONGESTION / PICKER-WAIT dominated, not geometry-dominated, so a distance-
based per-task estimate is a NOISIER predictor of makeable/doomed than the empirical
mean. The global adaptive window already wins. Kept RUSH + global window as default;
removed the losing RolloutRushController from CONTROLLERS (left a code note).
IMPLICATION: a good per-task completion estimate needs a CONGESTION/PICKER-WAIT signal
(learned delay head, Stage 3), not just distance. The rollout ENGINE's real payoff is
Part A plan SCORING (deadline_margin, battery_margin to rank robot->task->route), not the
doomed cutoff — that's the next build.

## 2026-07-10 — Part A methodology (from PartA_Plain.docx + Project_Plan_Main.docx)

Part A = ONE free robot picks ONE task AND ONE route (multi-robot combine = Part D).
7-step funnel (cheap -> expensive):
  1. Cross off impossible: 3 yes/no hard checks (done? taken? wrong robot type?). No score.
  2. Cheap screen: task_reward_value - discounted Manhattan distance; keep top ~15.
     (Cheap version of the SAME value+cost scored later; not priority-alone, not dist-alone.)
  3. Yen's k-shortest-paths per finalist: 3-5 real routes on the map (the expensive step).
  4. Delete illegal routes (DELETIONS not prices): cell rumor > b_hard; collides with an
     already-driving robot (same cell/time or edge-swap); finishes below battery floor.
  5. Score survivors: ONE number = task value + deadline chance + battery used + travel
     time + risk (risk = P(through uninterrupted) from Beta rumor map). Guesses (delay,
     risk) from predictive layer: analytic formulas @Stage0, learned heads @Stage3.
  6. Rank tasks by their BEST route (not avg) + small feasibility-ratio bonus (3 routes > 1).
  7. Commit winner as "R1 -> T2 using route_2" (always task AND route).
Architecture map: generator = Yen's routes + shortlist; kitchen = rollout engine (built,
analytic: rollout_task); health code = step-4 hard filters; prices = fixed utility, Optuna-
tuned between runs (frozen within a run). Four quantity kinds: FIXED rules, GENERATED
options, TUNED knobs, PREDICTED guesses (only guesses are learned).
REFRAME vs current controllers: they rank the whole QUEUE by a scalar + assign nearest AGV;
Part A is PER-ROBOT + ROUTE-AWARE (funnel per freed robot -> commit robot->task->route). The
value/deadline/decay logic becomes INGREDIENTS in step-5 utility, not the whole decision.
DEPENDENCIES still missing before full Part A: Yen's k-routes generator; Beta rumor map
(for b_hard + risk); state assembler; analytic risk/delay formulas. Buildable NOW without
the map: cheap screen, battery-floor filter (via rollout), collision-with-driving-robots
filter, and a Stage-0 utility with risk=1 placeholder until the map exists.

## 2026-07-10 — Part A started: cheap screen + Yen's routes (funnel runs; scoring pending)

Built the per-robot Part A funnel (doc steps 1-7):
- `wwm_sim/routing.py`: build_agv_graph (4-connected open grid — AGVs traverse everything;
  only dynamic robots block), k_shortest_routes (Yen's = nx.shortest_simple_paths, ~9ms/call,
  3 shape-distinct routes), cheap_screen (value - 0.15*Manhattan, top ~15).
- Refactored base controller: extracted `_assign_tasks()` so assignment is overridable
  (task-centric default vs Part A's per-robot funnel).
- `PartAController` ("parta"): per FREE AGV -> hard checks -> cheap screen (top 15) -> Yen's
  k=3 routes -> filter (PLACEHOLDER: all survive; b_hard/collision/battery not wired) ->
  score (rollout finish -> RUSH-style value+lateness-decay, one number) -> best-route pick ->
  feasibility bonus -> commit robot->task->ROUTE (stored in self.routes). ~3s/episode.
BAKE-OFF (10 seeds, hard 500): RUSH on-time 27.4 / val 205.5 vs PARTA on-time 23.7 / val
188.3 (-8%). Part A UNDERPERFORMS — SAME reason as the per-task window: its step-5 utility
scores by a per-task rollout FINISH estimate, which is noisier than RUSH's empirically-
calibrated global window (completion is congestion/picker-wait dominated, analytic finish
can't see it). The FUNNEL STRUCTURE works (screen + Yen's + per-robot route commit all
function); the analytic scoring is what the delay head (Stage 3) + rumor map (risk, b_hard)
are meant to lift. Part A is the right ARCHITECTURE (route-aware, enables collision/b_hard
filters + ADG execution that RUSH structurally can't do), just not a Stage-0 win yet.
NEXT OPTIONS: (a) hybrid — use the proven global window in Part A's utility to reach RUSH
parity while keeping the funnel (pragmatic); (b) build the real step-4 filters (collision
vs committed routes, battery floor) which need the route-awareness Part A now provides;
(c) build the Beta rumor map to unlock b_hard + risk scoring.

## 2026-07-10 — Q: why separate heads? why not feed map + head outputs into the rollout?

Partly already done: the rumor MAP does feed in — rollout(BELIEVED_state, plan); the map
also drives the b_hard hard filter (delete) and the risk scoring term. So map info is
consumed in 3 places, just not all inside the rollout.
Heads stay SEPARATE (composed on top, not fused into the rollout) because:
1. Exact vs guess — rollout is exact arithmetic on known rules (verifiable, deterministic);
   heads are statistical guesses (can be miscalibrated/wrong). Keep exact clean, quarantine
   the guesses -> you can tell WHICH part failed (interpretability).
2. Data-dependency direction — delay is a FUNCTION OF the route the rollout produces (route
   features: nearby robots, overlaps, narrow cells). It doesn't exist until the route is
   drawn. So order is rollout -> route -> head reads route -> delay -> shifts arrival. A
   composition, not a merge; delay can't be a pre-fed rollout input.
3. Calibration/gating — the utility MULTIPLIES probabilities (risk, completion), so they
   must be calibrated; the ship gate is "beat the formula by >=15% AND calibrated". Only
   possible if each head is a separable, measurable predictor. Fused = one un-gateable box.
4. Merging = the learned-world-model (Dreamer/MuZero) design the plan REJECTS (compounds
   error). Thesis = known-rules pattern: simulate exact rules directly, learn only the
   residual. Rollout = rules; heads = residual. Separation keeps the sim non-compounding.
One-liner (plan's Google Maps analogy): route from the known road map (rollout) + ETA delay
from a separate historical-traffic model (head), added at the end. Don't bake traffic into
the road graph. Rollout and heads meet at SCORING, not inside the rollout.

## 2026-07-10 — refinement: TWO distinct "whys" (don't conflate them)

The ordering and the modularity are separate facts with separate causes:
- WHY the heads run AFTER the rollout = DATA DEPENDENCY (not calibration). Delay depends
  on the route's own shape (crowding, overlaps), which doesn't exist until the rollout
  draws the route. Can't predict traffic on a route before you have the route -> "after"
  is unavoidable regardless of anything else.
- WHY they're kept as SEPARATE modules = CALIBRATION/GATING. The utility multiplies each
  head's probability into the score, so each must be independently measurable, calibrated,
  and gated (ship only if beats formula >=15% AND honest about confidence).
So: "after" = needs the finished route; "separate" = each guess calibrated on its own.
Pipeline: rollout (exact route + numbers) -> heads read the route -> combine at SCORING.

## 2026-07-10 — battery model finished (mechanism + chargers + gate + rollout wiring)

Closed the 3 battery TODOs:
1. DEDICATED CHARGERS reachable by BOTH types — `wwm_sim.battery.default_chargers(env)`:
   goals sit on the bottom row Pickers are barred from, so goals can't charge pickers;
   pickers CAN reach all 240 shelf-cells (verified) -> chargers = a spread of shelf-cell
   action-targets. BatteryTracker now defaults to these (pickers recharge: min pick 0.14).
2. GATE MOVEMENT (planner-level) — `BatteryAwareController`: a robot at/below floor away
   from a charger is stranded and gated to no-op (stops). Plus a Stage-0 CHARGE DECISION:
   free robots below GO_CHARGE (0.35-0.45) go to the nearest charger, held until FULL,
   then released (emergency-charge precursor to Part B).
3. WIRED INTO ROLLOUT — `wwm_sim.rollout.battery_feasible(res)` (delete a route that would
   finish below the floor = Part A step-4 hard filter); rollout_task already returns
   battery_used/battery_margin.
Verify (`scripts/verify_battery.py`, spc=400 so battery BINDS, 5 seeds): RUSH with no rule
strands 6.2/12; BatteryAware charge+gate cuts it to 1.0/12 (both types stay ~>=floor). The
charge rule works but does NOT reach a full zero — residual strandings are mid-carry / en-
route-to-charger cases that need the Part A battery FILTER (don't start a task you can't
finish above floor) + Part B EMERGENCY interrupt. That is exactly where the plan's
"strandings=0 by construction" (§6.1) completes — the battery MODEL provides the mechanism;
the GUARANTEE is a planner-stage integration. New controller: "battery". MissionType.CHARGING
added. Harsher compression (spc 150-300) leaves more residual, as expected.

## 2026-07-10 — design: rendezvous sync-up with BUSY robots' committed plans (rollout feature)

Q (user): when ranking a task, account for whether a partner is already committed to it
(picker for an AGV, AGV for a picker) and the SYNC-UP WAIT between my arrival and being
able to finish. Useful? Where does it plug into Part A / the rollout?
ANSWER: yes, useful, and it belongs in the ROLLOUT (known rule), not a head. Rendezvous
(both-present-to-load) is a rule; if the partner is already committed, its arrival is
computable from its route -> the wait is EXACT arithmetic, not a guess. Only the residual
("will the partner hit that ETA?") is the delay head's job later. Clean split.
COMPUTE: partner_eta = committed partner's arrival at the cell (if one is on this task);
else nearest-free partner ETA; else BIG (nobody can meet me). rendezvous = max(my_arrival,
partner_eta); my_wait = max(0, partner_eta - my_arrival); finish = rendezvous + load + dock.
my_wait pushes finish later (worse deadline margin) AND is a direct cost.
THREE CASES it distinguishes (the value): (a) partner committed & aligned -> wait~0, ready;
(b) committed but far -> I sit, later finish, deprioritize; (c) none free/committed ->
unserviceable now -> penalize hard. Current rollout only does nearest-FREE-picker Manhattan
= blind to committed partners; collapses these three.
PLUG-IN (Part A): input = busy robots' committed routes (= believed state / reservation
table). (1) rollout_task gains a partner_eta arg: committed picker -> now+len(picker.path);
else free-picker ETA; else BIG. (2) Part A step-5: finish already includes wait via
deadline-margin; optionally add explicit sync cost score -= w_sync*wait. Data flow: busy
committed routes -> partner ETA -> rollout rendezvous/wait -> finish/margin (+sync cost) ->
Part A score. Symmetric for pickers; full joint meet-up optimization = Part D.
CAVEAT: nearest-free alignment was marginal earlier (congestion-dominated, guessed ETA).
Committed-ETA is better grounded (actual planned route) but still no-traffic until the delay
head refines. Should help task CHOICE (esp. avoiding case-(c)); accuracy improves with the
head. STATUS: designed, not yet implemented — offered to build + bake off vs plain Part A.

## 2026-07-10 — rendezvous scenarios enumerated + candidate rollout features (for decision)

A) Every partner scenario when a FREE robot scores a task (AGV's partner = picker; symmetric
for picker's AGV). rollout returns (partner_eta, my_wait, reason_code):
  1 partner already committed to THIS cell -> partner_eta = now+len(partner.path) [EXACT]  code ALIGNED
  2 none here but >=1 FREE partner -> partner_eta = now + nearest-free route [ESTIMATE; which one = Part D]  code FREE_ESTIMATE
  3 none committed, none free, busy will free -> partner_eta = now + min(steps_to_finish_current + travel_release->S) [optimistic]  code WAIT_FOR_FREE
  4 no partner prospect at all -> partner_eta = inf -> DELETE task / huge penalty  code UNSERVICEABLE
  Sub-case within 1-3 by comparing partner_eta to my_arrival:
    partner<=mine -> PARTNER_WAITS (ready for me, flags wasted partner time)
    ~equal -> ALIGNED (my_wait~0, ideal)
    partner>mine -> I_WAIT (my_wait = partner-mine, finish later)
  my_wait -> finish -> deadline margin (+ optional sync penalty). User's cases map: same-location
  active = #1; no free pickers/AGVs = #3/#4; free pickers (which one = probabilistic) = #2 (Part A
  uses nearest-free estimate; joint assignment deferred to Part D).
B) Candidate rollout-engine features (all known-rule/deterministic), presented for decision:
  1 Rendezvous sync-up (above) — RECOMMENDED.
  2 Charge-detour finish (battery-aware GRADED finish: insert a charge stop + needs_charge flag
    instead of just deleting) — HIGH value, synergizes w/ battery model, attacks residual strandings.
  3 Return-to-free time (free_again = finish + return leg) — cheap, lookahead; more Part C/D value.
  4 Committed-path congestion inflation (reservation-table + BPR travel bump) — LOW/redundant
    (Part A/D already price busy-path overlap; straddles rollout/head; previously demoted).
STATUS: designed, awaiting user's pick of which to implement.

## 2026-07-10 — Part A: 3 rollout features implemented + route visualization

Implemented features 1+2+3 into the rollout + Part A funnel:
- SYNC-UP (feature 1): `rollout.partner_eta(shelf, now, committed/free/busy)` returns
  (eta, reason) for the 4 scenarios — committed(exact len(path)) / free_est(nearest-free
  Manhattan) / wait_free(soonest busy free_again + travel) / unserviceable(1e6). Unit-tested
  all 4 (3,'committed'; 1,'free_est'; 16,'wait_free'; 1e6,'unserviceable'). `rollout_task`
  now takes my_arrival + partner_arrival, returns my_wait; Part A scores score -= W_SYNC*my_wait
  (W_SYNC=0.3) and -1e6 for unserviceable. `PartAController._partner_groups` builds the groups
  from assigned_pickers + picker.path.
- CHARGE-DETOUR (feature 2): if battery margin<0 and a charger is reachable, rollout_task
  inserts charger_dist + charge_steps into finish + sets needs_charge (graded, not just
  deleted). Active in Part A when a battery tracker is attached (else dormant); the step-4
  hard filter deletes only if infeasible AND no charger to detour to.
- RETURN-TO-FREE (feature 3): rollout_task returns free_again = finish + return leg; feeds
  next-availability AND the sync-up case-3 estimate (when a busy partner frees). Per user:
  "free again is important for sync-up and availability in general."
Part A now stores candidate_routes (all Yen's per chosen task) + routes (chosen) for viz.
Runtime ~7s/episode (sync-up overhead); on-time ~24 seed0 (~unchanged — analytic finish still
underperforms global window; sync-up mainly improves task CHOICE, esp. dodging unserviceable).

VISUALIZATION `scripts/viz_parta.py` (headless PNG, avoids live-window hang): two panels —
LEFT chosen route per AGV (bold, colour-coded, star=target); RIGHT all Yen's candidate routes
(faint) with chosen bold, so you SEE the alternatives + the pick. Chargers/AGVs/pickers/tasks
drawn. Output results/parta_routes.png. Run: python scripts/viz_parta.py [--seed S --step N
--out path]. (Live matplotlib window hangs in this env — PNG is the reliable path.)

## 2026-07-10 — removed charge-DETOUR (feature 2) from Part A

User: the charge-detour (charge-then-continue) is a SUPPORT action -> it belongs in the
support/task combo (Part B/C), not baked into Part A's task rollout. Removed:
rollout_task no longer takes charger_dist / inserts a charge stop / returns needs_charge;
Part A dropped the cdist wiring. KEPT: the battery-floor FILTER (battery_used/margin +
battery_feasible) — deleting a route that would strand IS legit Part A step-4. So Part A
just won't PICK a task it can't finish above the floor; arranging a charge first is Part
B/C. Sync-up (1) and return-to-free (3) unchanged. Part A features now: sync-up + filter +
return-to-free.

## 2026-07-10 — partner_eta cases 2 & 3: AVERAGE not shortest (contention)

User: for rendezvous cases 2 (free) & 3 (wait-free), average or shortest? There's no
guarantee the picker chooses YOU if others compete. -> Switched min -> AVERAGE. Why:
using the NEAREST free / SOONEST busy partner assumes you WIN it, but you don't control
the partner assignment; under contention (more AGVs than free pickers, or you're not
top-priority) you get a TYPICAL partner, not the best one. min = optimistic best-case
that HIDES real waits and defeats the sync-up penalty's purpose; average reflects the
expected partner. Verified: 3 free at 1/5/9 -> 5.0 (not 1); 2 busy freeing at 11/33 ->
22.0 (not 11); committed/unserviceable unchanged. Exact winner = joint assignment = Part
D; cheap refinement = contention factor competing_AGVs/available_partners. Case 1
(committed) stays EXACT (len(path)); case 4 unchanged.

## 2026-07-10 — viz fix: show MULTIPLE candidate TASKS, not just the chosen task's routes

User caught it: the controller DOES evaluate multiple tasks (Yen's k=3 on all ~15 screened
finalists, then commit best), but the viz only showed the chosen task's k=3 routes because
that's all I stored (candidate_routes[agv] = chosen shelf's routes; other finalists' routes
were computed then discarded). Not deliberate clutter-hiding — just under-retention. Fix:
PartAController now also stores `candidate_tasks[agv] = [(shelf,best_route) for top-5
finalists by score]`; viz right panel redrawn as "Candidate TASKS weighed per AGV (top 5) —
chosen bold": faint best-route to each of the top-5 tasks (small star each) + chosen bold
(big star). So the multi-TASK funnel is now visible. Screen keeps 15 + Yen's runs on all 15;
we DRAW the top-5 for readability (noted in the panel). results/parta_routes.png regenerated.

## 2026-07-10 — viz: "only a few routes" explained + FOCUS view added

Diagnosed: the all-AGV candidate panel WAS drawing 40 routes (5 tasks x 8 AGVs) but to only
16 UNIQUE target shelves — AGVs pile onto the SAME high-value candidate tasks (e.g. (11,25),
(11,33),(11,18),(11,13) appear in almost every AGV's top-5), so routes overlap in the aisles
and collapse into a few visible bundles. That shared-candidate overlap = real CONTENTION
(resolved by Part D), not a display bug. Fix for legibility: added `--focus <i>` — the right
panel now shows ONE AGV's funnel, its N candidate tasks each a DISTINCT colour (cand 1..N)
with the chosen bold + the focused AGV ringed. Clear multi-TASK view. Left panel still shows
the fleet's chosen routes. `python scripts/viz_parta.py --seed S --step N --focus i`.

## 2026-07-10 — viz: show each candidate task's full Yen's route set

Per request: the focus panel now draws, for each of the AGV's candidate tasks, ALL its
Yen's k=3 route alternatives (not just the best one). PartAController.candidate_tasks now
stores (shelf, [all_routes]) per task; viz focus panel loops the routes per task — chosen
task's routes bold (chosen route boldest), other candidate tasks' route bundles faint, each
task a distinct colour. Title: "AGV{id} funnel: N candidate tasks x Yen's routes".
NOTE: the Part A funnel runs only for AGVs today; PICKERS are still DISPATCHED (nearest/
rendezvous), not funnel'd, so there are no picker candidate routes to draw — picker-side
Part A (symmetric funnel) is a separate build.

## 2026-07-10 — Part A funnel for PICKERS (symmetric, synced to AGV availability)

Built the picker-side Part A funnel (was: nearest-picker dispatch). Each FREE picker now
runs a funnel to choose which AGV-rendezvous to serve:
- routing.build_picker_graph(env): 4-connected HIGHWAY graph (pickers travel aisles only) +
  each shelf/target connected to adjacent highway cells; Yen's k=3 on it (verified: 3 routes
  to a shelf). 770 nodes.
- PartAController._dispatch_pickers override: candidates = AGVs needing a picker (PICKING/
  RETURNING); for each, picker route via highway Yen's, and RENDEZVOUS SYNC vs the AGV's
  committed AVAILABILITY: agv_eta = len(agv.path); agv_wait = max(0, picker_arrival-agv_eta)
  (AGV waits -> delays a valuable task); picker_wait = max(0, agv_eta-picker_arrival) (wasted
  picker time). score = agv_task_value - W_SYNC*agv_wait - 0.5*W_SYNC*picker_wait. Commits
  best; stores picker_routes + picker_candidate_tasks ([(gx,gy),[routes]]).
RESULT: picker sync-up HELPS — seed0 on-time 24->27; 4-seed on-time 25.5 (vs AGV-only Part A
~23.7, RUSH 26.2). Narrows the gap to RUSH; still slightly behind (analytic finish < global
window, the known gap the delay head closes). on-time_val 191.5 vs RUSH 200.2.
VIZ: viz_parta.py --focus-kind picker shows a picker's rendezvous funnel (candidate AGV
rendezvous x Yen's highway routes, chosen bold); left panel now draws AGV routes (solid) +
picker rendezvous routes (dashed). results/parta_picker.png.

## 2026-07-10 — clarify: picker priority basis (always chooses among BUSY AGVs)

A picker only ever serves an AGV that's ON a task, so its candidates are ALWAYS busy AGVs
(normal case, not special). It ranks them by the AGV's task VALUE (highest-value task's AGV
served first) — so it follows the task value ranking, BUT: (1) rendezvous SYNC modulates it
(W_SYNC: a better-aligned lower-value AGV can win); (2) it uses RAW task_value, NOT the full
AGV ranking (value×decay + makeable/doomed) — tracks value, not urgency/decay. To make the
picker follow the EXACT AGV ranking, swap raw value for the RUSH-style value×decay score
(one-line change). OPEN: user to decide identical-ranking vs value-only for pickers.

## 2026-07-10 — plain-terms: why rollout lags Part A, how the delay head fixes it

Rollout = GPS on an EMPTY road: exact DISTANCE, blind to TRAFFIC (other robots, picker
waits, jams). Real finish is longer by a DIFFERENT amount per task -> rollout mis-ranks
tasks. RUSH uses ONE number (measured avg real trip ~69) that has traffic baked in from
real runs -> crude (same for all) but honest-on-average -> wins now. Precise-but-blind <
crude-but-traffic-honest. Delay head = the TRAFFIC LAYER: learns from history "trips with
these features (nearby robots, route overlaps, narrow cells) ran ~+X late" and ADDS that
to the rollout's clean finish. Result = exact distance (rollout) + traffic bump (head) PER
TASK -> beats the global average. Literally Google Maps (road map + traffic ETA model).
Mini-example: A far/light rollout40 real45 (head +5); B near/heavy rollout20 real50 (head
+30). Rollout alone ranks A slower (wrong); rollout+head -> 45 vs 50 -> correctly flags B.
Table: rollout(exact dist, no traffic, per-task) / global-window(no dist, traffic-avg, one
number) / rollout+head(exact dist, traffic per-route, per-task = best).

## 2026-07-10 — clarify: what a picker does when AGVs are free (12 AGV / 8 picker)

Pickers never pick a task directly — a picker's candidates ARE "busy AGVs needing loading",
so if ALL AGVs are free -> no rendezvous -> picker IDLES (nothing to rank). Pickers are
REACTIVE (no pre-positioning/scouting; that's Part B/C). Within a step the order is AGVs
assign first (_assign_tasks) THEN pickers respond (_dispatch_pickers), so "all free" is only
a momentary pre-assignment state; pickers idle only if the task queue is genuinely empty.
12/8 angle: once work flows, up to 12 AGVs get tasks but only 8 pickers exist -> pickers
serve the top-8 rendezvous by value+sync, other 4 AGVs WAIT for a picker -> pickers are the
BOTTLENECK, which is why their value+sync ranking matters. Answer: busy AGVs -> picker ranks
by value(+sync); all AGVs free -> picker waits.

## 2026-07-10 — picker uses the SAME task ranking as AGVs (value×decay) + sync => Part A ties RUSH

User: pickers should rank by a similar task ranking to AGVs (one task = AGV subtask + picker
subtask, both scored by the parent task's utility). Confirmed multiple busy AGVs ARE already
ranked (scored.sort in _dispatch_pickers). Implemented: picker scores each candidate AGV-
rendezvous by the SAME value×lateness-decay (makeable-first) utility the AGV funnel uses,
computed from the rendezvous-aware finish (max(picker_arrival, agv_eta)+load+dock), PLUS
sync penalties (agv_wait + 0.5*picker_wait) so it stays aligned on MAKEABLE tasks (where the
decay base can't tell the AGV-wait apart).
4-seed on-time: value-only 25.5 / full-ranking-no-sync 25.0 / FULL-RANKING+SYNC 26.2 (= RUSH
26.2); on-time_val 198.8 vs RUSH 200.2. => route-aware Part A (AGV+picker funnels) now TIES
the scalar RUSH on on-time, ~ties on value, while carrying routes + filters + sync RUSH
lacks. (Lesson repeat: relying on the analytic finish ALONE (no sync) was worse — sync
terms recovered it; delay head will lift both further.)

## 2026-07-10 — confirm: sync check = normal task ranking MINUS sync-up wait (both sides)

User's model confirmed: the sync check does not replace the ranking, it ADDS to it. Both
AGV and picker score = normal task ranking (value × decay by deadline/time) − sync-up wait.
The sync-up time enters TWO ways: (1) inside FINISH — rendezvous = max(my_arrival,
partner_arrival), so a late partner -> later finish -> worse deadline margin -> lower
value×decay (captures on-time effect); (2) explicit WAIT PENALTY −W_SYNC×wait (punishes
wasted idle time even when the task is still makeable). AGV penalizes its own wait; picker
penalizes the AGV's wait (delaying a valuable task) + its own wasted time. Same shape, both
directions.

## 2026-07-10 — Part A 10-trial bake-off + 1-AGV/1-picker decision demo

10-TRIAL bake-off (scripts/verify_parta.py, hard 500-cap):
  metric        RUSH   Part A
  on-time       27.4   26.7
  on-time_value 205.5  198.8
  deliveries    34.0   35.3
=> Part A competitive but ~3% behind RUSH on on-time value, AHEAD on raw deliveries (35.3
vs 34.0). The 4-seed "tie" (26.2=26.2) was optimistic; honest 10-seed = Part A slightly
behind. Gap = traffic-blind analytic finish (delay head closes it). CSV:
results/parta_vs_rush_10trials.csv.
DECISION DEMO (scripts/demo_decision.py, 1 AGV + 1 picker, small env): prints the AGV task
funnel + picker rendezvous funnel with the real score breakdown, + draws
results/decision_1agv_1picker.png. KEY illustration: shelf 16 and shelf 96 BOTH value 9,
but shelf 16 wins (score 1009 vs 1006.3) because myWait=0 (synced) vs shelf 96's myWait=9
(AGV would wait 9 for the picker -> -0.3*9 sync penalty). Sync check breaking a value tie,
live. Picker then drives 14 to meet AGV (ETA 17) -> arrives 3 early, good sync.

## 2026-07-10 — all-robots-free / joint sync = a PART D problem, not Part A

Resolved framing: the "sync ALL robots with each other at once" case (optimal fleet-wide
pairing/assignment when many/all robots are free) is a PART D problem (joint assignment),
NOT Part A.
- Part A = SINGLE-ROBOT optimization: each free robot greedily picks its own best
  task+route, syncing only against whatever is ALREADY committed. It never needs a joint
  all-free solve.
- "All robots free" (start, or the rare all-free-MID-RUN edge case — almost never, since
  robots normally finish STAGGERED so there's usually a committed robot to sync against):
  Part A handles it by the per-step funnel processing free robots ONE AT A TIME (sequential
  greedy) — first robot picks+commits, next syncs against it, etc. So it's NOT a problem for
  Part A; just sequential single-robot passes over the current task queue.
- Only the OPTIMAL joint coordination (everyone-with-everyone, simultaneous, best global
  pairing) is deferred to PART D. Right now we just want each robot to sync against the
  committed others = single-robot optimization. Full joint = Part D.

## 2026-07-10 — rendezvous-alignment term = the Part A sync term (marked DONE)

User: don't keep "rendezvous-alignment term" as a separate pending idea — we already do a
SYNC term, so it's covered. Marked the checklist item [x] DONE: the Part A sync term
(value×decay − W_SYNC·wait, both AGV and picker, partner ETA from rollout.partner_eta) IS the
rendezvous-alignment term. Superseded the old reverted AlignedValueController prototype.
Back-pocket item split: rendezvous-alignment DONE; only SMOOTH P(on-time) + per-task
completion estimate remain open (both wait on the delay head).

## 2026-07-11 — project structure / roadmap (from all 4 plan docs)

SPINE (invariant): every action = a scored PLAN in ONE ranked list per robot. 5 rules:
(1) one list no special lanes; (2) broad-to-choose exact-to-commit (never output a task
combo, always the cell+timestep route); (3) deletions never prices (crash/illegal/strand/
emergency deleted, never outbid); (4) known rules + learned residuals (rollout simulates,
heads learn only the guesses, calibration-gated); (5) generator (menu: Yen's routes,
shortlists) vs planner (score/filter/commit).
STAGES:
- 0 foundations + Part A (HERE ~90%): remaining = collision filter, disturbances+Beta belief
  map -> risk term, analytic formulas.
- 1 full system: Part B (pit-stop-then-task: simulate support -> score task FROM imagined
  future; fixed charge-duration menu 5/10/15/20; support+switch cost; alignment bonus;
  safety score). Part C (future-readiness: demand counting -> future_area_action_value;
  deferred commitment; scouting; battery; guards = idle penalty + safety split/emergency).
  Part D (group: shortlists -> one-plan-per-robot combos -> delete same-task[combo]/busy-
  crash[route]/internal-crash[pairing] -> score group shared-currency + fleet penalties +
  robustness bonus; pay-once-per-zone dedup; commit EXACT route combo; regret-order + LNS
  past ~5 robots). + ADG execution (order-preserving, absorbs small lateness), safety split
  (global), curiosity taper, scout dedup.
- 2 Optuna tunes importance_* weights between runs (shape fixed).
- 3 learned heads one at a time interrupt->delay->energy->completion (LightGBM), ship only
  if >=15% better than formula AND calibrated (isotonic/Platt). Closes Part A traffic gap.
- 4 optional: demand Poisson->Hawkes; GATv2 head-inputs; ablation opponents.
Cross-cutting: eval harness (planner metrics + rumor 90/90 + ablations >=3%-or-cut +
benchmarks). ONE-LINER: 0/1 build the machine in formulas, 2 tunes weights, 3 swaps formulas
for calibrated learned guessers one at a time, 4 polish. A->B->C->D = wider generators
feeding the same scoring machine.

## 2026-07-11 — Part A #1 collision filter: BUILT, but PARKED (env ignores our route)

Built the reservation-table collision filter (step 4): `_build_reservation` (space-time
vertex + edge-swap sets from busy robots' committed paths), `_route_clash` (vertex/edge-swap
within a near horizon), `_add_route_to_reservation`. Bake-off (4 seeds) revealed it CANNOT
work on this substrate:
  NO filter      : on-time 26.2  value 198.8  deliv 34.2  clashes 194.5
  HARD delete    : on-time  7.5  value  68.8  deliv  7.5  clashes  17.0   (CATASTROPHIC)
  SOFT prefer H8 : on-time 26.2  value 198.8  deliv 34.2  clashes 194.5   (identical = no-op)
ROOT CAUSE: the env executes its OWN A* to the target and REROUTES dynamically — it does NOT
drive our committed route. Our Yen's route only informs the DECISION (task scoring + viz),
never execution. So: soft filter = no-op (env drives its A* regardless); hard filter's clash
drop (194->17) was purely from DROPPING tasks (all-routes-clash -> idle AGVs -> fewer active
robots -> fewer clashes AND fewer deliveries). Confirms the earlier "prescreen reroute
unnecessary" call — with the mechanism now pinned: route-level collision avoidance can't
reduce real clashes until the env EXECUTES our committed routes = ADG execution (Stage 1).
ACTION: COLLISION_FILTER=False (default off). KEPT the machinery (correct + reusable): Part D
needs the same space-time clash/edge-swap check for combo-crash deletion, and ADG execution
will drive our routes so the filter re-activates then. So #1 is BUILT but PARKED behind ADG
execution. Next real Part A step -> #2 (disturbances + Beta rumor map -> risk term).

## 2026-07-11 — clarifications: Part C need, cheap reroutes in Yen's, what A* is

Q1 Part C need: only under STREAMING/lifelong demand (orders arrive over time, LULLS where a
robot is free but profitable work hasn't appeared yet + history predicts WHERE). Our TA-RWARE
sim keeps the request queue ALWAYS FULL (deliver -> refill, ~40 tasks always) -> a free robot
always has real work -> Guard-1 idle penalty makes direct tasks win -> Part C DORMANT by
construction. Part C activates only after a DEMAND-ARRIVAL model (gaps/bursts + spatial
pattern) is added = Stage 4 dependency. User's instinct right: Part C is a later/streaming
thing.
Q2 cheap reroutes in Yen's: YES they show up (near-shortest detours ARE in the k-set) — the
collision filter did NOT fail from missing alternatives. It failed (a) primary: env drives
its OWN A* + reroutes, ignores our committed route, so route choice is moot until ADG
execution; (b) secondary: hard-delete checked the WHOLE route (full horizon) for ANY overlap
-> on a crowded open grid every route brushes someone's far-future cell -> all k deleted ->
task dropped. A near-horizon filter would just pick a cheap clean route from the k-set
(confirms earlier "short route already shows up"). So cheap routes exist; execution + full-
horizon strictness were the problems.
Q3 A* = shortest-path finder: explores from start but SMART — favors cells heading toward the
goal via a distance heuristic (Manhattan), beelines + detours around obstacles (vs Dijkstra/
BFS flooding). Used twice: env moves each robot via A* to its target (reroute on block) = the
path actually DRIVEN; Yen's builds k-shortest ON shortest-path search. A* = single shortest
path engine; Yen's = top-k using it as a subroutine.

## 2026-07-11 — ADG execution STARTED (standalone algorithm + demo)

Built the Action Dependency Graph execution layer (Stage-1 start):
- `wwm_sim/adg.py`: build_adg(routes) -> Type-2 ordering deps (per shared cell, robots cross
  in planned-arrival order; pred[(robot,cell)] must LEAVE before robot enters). simulate_adg
  (execute committed routes respecting deps + own-path order, optional injected delays;
  collisions 0 by construction; returns traj/collisions/finish/waits). simulate_naive
  (blindly follow routes, ignores deps -> collisions when a delay desyncs a crossing) for
  contrast.
- `scripts/demo_adg.py`: 2 robots cross at one junction, A planned first. Inject 1 STEP of
  lateness on A (reaches J same tick as B): NAIVE -> 1 collision (both land on J); ADG -> 0
  collisions, B WAITS for A to clear J (no replan). Proves the key property: small lateness
  absorbed as WAITING, not a crash.
KNOWN minor: executor is conservative at tick granularity (a robot waits 1 tick for a cell
occupied at tick-start even if the occupant vacates that tick) -> a small extra wait even in
the no-delay case. Follow-chains / entering-a-vacating-cell same tick = a refinement.
NEXT for ADG: env INTEGRATION — drive wwm_sim's micro-action layer (execute_micro_actions)
from committed routes + ADG ordering, replacing attribute_macro_actions' A* + resolve_move_
conflict's reroute. THAT is what un-parks the Part A collision filter (env would then execute
OUR routes) and makes reroutes a priced decision (Part B) instead of automatic.

## 2026-07-11 — ADG execution ENV-INTEGRATED (movement-only cut) + deadlock clarification

DEADLOCK Q: ADG guarantees 0 collisions always. Deadlock: on a VALID (collision-free) joint
plan the ADG is provably ACYCLIC (deps come from one consistent time-ordering; a cycle = a
deadlock, and a time order has no cycles) -> deadlock-free, absorbs FINITE delays. It does
NOT rescue an invalid/conflicting plan (cycles -> deadlock) or a PERMANENTLY stalled robot
(infinite delay -> everyone waits; that's the "big lateness -> replan" path). Our Part A
routes are per-robot Yen's, NOT jointly deconflicted -> ADG deadlock-freedom is INHERITED
from Part D's deconfliction (not present yet).
ENV INTEGRATION: added an ADG execution MODE to wwm_sim.Warehouse (our editable env):
`set_adg_plan({agent_id:[cells]})` builds the ADG + enables mode; `_adg_attribute()` sets
each agent's micro-action toward its next committed cell IFF the ADG allows (predecessor has
physically LEFT that cell, tracked via departures) AND the cell is free; step() branches on
`_adg_mode` to use it and SKIP resolve_move_conflict + resolve_stuck_agents (ADG replaces
reroute). Reuses execute_micro_actions for real moves (orientation/turns handled naturally
since deps use actual departures, not tick indices). Opt-in: fresh env `_adg_mode=False`,
normal RUSH unaffected (33 deliveries, verified).
DEMO `scripts/demo_adg_env.py`: 2 AGVs cross J=(6,10) in the REAL env; stall AGV_a 4 ticks ->
AGV_b HOLDS at (6,11) until AGV_a clears J (enters at tick9), 0 collisions, no reroute. Delay
became a WAIT in the actual simulator.
SCOPE / NEXT: movement-only (pick/deliver still via normal leg-end logic — not yet driven in
ADG mode); needs Part D deconflicted routes for FLEET use (else deadlock); follow-chain /
same-tick-vacate refinement. This UN-PARKS the Part A collision filter conceptually (env can
now execute our committed routes). Big remaining: wire the controllers to feed committed
routes into set_adg_plan per leg + handle pick/deliver in ADG mode + Part D deconfliction.

## 2026-07-11 — ADG bake-off assessment: env already WAITS; ADG win is Part-D-gated

Key finding from reading `resolve_move_conflict`: the env's native execution ALREADY resolves
conflicts by WAITING (builds a digraph of intended moves; commits a longest-path/cycle set to
move, NOOPs the rest) — it does NOT reroute. So the ~194 "clashes" for RUSH and Part A are
WAIT events, not reroutes. "no-ADG" is already collision-safe-by-waiting (ADG-LIKE, just
per-step greedy vs fixed-plan).
=> ADG's ONLY distinctive gain over the native waiter = a CONSISTENT global crossing order
from a FIXED deconflicted plan -> provably deadlock-free + order-preserving. That needs Part
D. Without it: per-step ADG ~= native waiter (no throughput win), and full-fleet ADG on our
UN-deconflicted Yen's/A* routes would likely DEADLOCK (worse than native).
Therefore a throughput bake-off ADG-vs-plans CANNOT honestly show an ADG win pre-Part-D. The
ADG execution MECHANISM is up + proven (env mode + demo: stall->wait, 0 collisions). Its VALUE
is unlocked by Part D (the deconflicted fixed plan ADG needs). Recommended sequence: Part D
first, then ADG pays off. Offered: build the full-episode ADG runner to EMPIRICALLY show
ADG ~= native / deadlocks on un-deconflicted routes (confirming the gate) — user to choose
that vs moving to Part D.

## 2026-07-11 — clarify: Part B = one support-action machine used at two moments (reroute is one option)

Q: Part B seems like "support-then-task BEFORE you start", but reroute is mid-drive — overlap?
A: YES, intentional overlap. Part B = "do a SUPPORT ACTION, then continue", scored from the
imagined future. Support MENU = {charge, wait, reroute, recover} — reroute is just ONE option;
charge/wait/recover are others (so support != just reroute, user right). SAME machinery runs
at TWO decision-event moments:
  1) UPFRONT (robot frees): pit-stop-then-task — charge/reroute/wait/recover THEN task, judged
     from the post-support future (later time, fuller battery, new start cell).
  2) MID-DRIVE (robot struggles / unforeseen conflict): interrupt state re-opens the SAME menu
     — keep going / reroute / wait / charge / ditch-and-recover.
Reroute FEELS mid-drive and charge FEELS upfront only because of which situation triggers each
(you plan charge knowing your battery; a reroute is forced by a surprise) — mechanically the
SAME menu (could plan a reroute upfront, could charge mid-drive). Part B isn't strictly
"before the action"; it's available at EVERY decision event (robot frees OR robot struggles).

## 2026-07-11 — sharpening: upfront reroute collapses into Part A's k-route choice

User insight: an UPFRONT reroute is basically just picking a different k-shortest route in
light of the expected delay. CONFIRMED + sharpens the A/B line:
- ROUTE CHOICE (which of the k routes) = PART A. "Reroute upfront to avoid a known jam" =
  Part A choosing the longer-but-clearer k-route because the shortest scores worse once
  congestion/delay is priced in. Not a separate action -> absorbed by Part A (esp. once its
  score carries delay/congestion/sync/risk terms).
- Genuinely-distinct PART B = things a route choice CANNOT express: CHARGE (insert battery
  stop), WAIT (insert pause), RECOVER (spend steps erasing failure risk) — structural plan
  changes. Plus REROUTE-ON-SURPRISE (mid-drive interrupt) = reaction to NEW info the route
  wasn't planned against.
=> "reroute" is the FUZZIEST support-menu item: upfront it's really Part A; only mid-drive
(surprise) is distinctly Part B. Clean Part B contributions = charge/wait/recover (upfront,
structural) + reroute-on-surprise (mid-drive). If Part A's utility already has the delay/
sync/risk terms, upfront reroute is ENTIRELY Part A (user's point).

## 2026-07-11 — cleanest A/B/ADG boundary: Part B's real job = STATE changes (charge, recover)

User completed the collapse: WAIT folds in too (like reroute). Two kinds of wait, both already
handled: conflict-wait = ADG (automatic); sync-wait = Part A sync term (my_wait). So neither
reroute NOR wait is a distinct upfront Part B action — both are POSITION/TIMING moves owned by
Part A (route choice) + ADG/sync (timing).
What genuinely CAN'T be a route or a pause = actions that change the robot's INTERNAL STATE:
  CHARGE -> battery state ; RECOVER -> risk state (spend steps to erase elevated failure prob).
No route/timing choice can refill a battery or de-risk a slipping robot. THAT is the real Part B.
CLEAN SPLIT:
  Position (which route)      -> Part A (k-route choice)
  Timing   (when to pause)    -> ADG (conflict-wait) + Part A sync term (sync-wait)
  State    (battery, risk)    -> PART B (charge, recover)
Mid-drive interrupt on a SURPRISE picks from reroute / charge / recover / ditch-and-switch;
plain wait is already ADG's default (only escalate to Part B for a route or STATE change).
ONE-LINER: Part B's genuine non-overlapping job = STATE-changing supports (charge=battery,
recover=risk); everything positional/temporal (reroute, wait) is absorbed by Part A + ADG.

## 2026-07-11 — clarify: reroute (POSITION) vs recover (STATE) — opposite sides, NOT hand-in-hand

User guessed reroute+recover go together (reroute=route fix, recover=putting down a shelf).
CORRECTION:
- REROUTE = POSITION fix (change the route you drive) -> Part A k-route choice. (user right)
- RECOVER = STATE fix, NOT dropping a shelf. Doc: a "slipping-wheel" robot does "recover 10
  steps, then task" and it wins "because recovering erases its elevated FAILURE RISK". So
  recover = spend steps to restore health/reliability (risk state). Nothing to do with cargo.
=> They are OPPOSITE sides of the split: reroute=POSITION (Part A), recover=STATE (Part B,
same side as CHARGE). Natural pairing is CHARGE + RECOVER (charge=battery state, recover=risk
state) — both fix an internal condition no route can fix = the genuine Part B.
Word caveat: "recover" has 2 senses in the doc — (1) recover-N-steps = de-risk (support menu);
(2) "ditch the task and recover onto something better" = abandon + switch to a better task
(mid-drive interrupt escalation). Neither = putting down a shelf.

## 2026-07-11 — upfront vs interrupt-state table + the mid-carry ditch (offload the shelf first)

UPFRONT vs INTERRUPT-STATE (which decision fires when):
  Action              upfront?  interrupt?  kind          owner
  reroute/route pick  yes       yes         position      Part A
  wait                yes       yes         timing        Part A sync / ADG
  charge              yes       yes         state:battery  Part B
  recover (de-risk)   yes       yes         state:risk     Part B
  ditch & switch      no        yes         task-switch    Part B interrupt
  get-ready (Part C)  yes       no          readiness      Part C
Read: position/timing exist both moments but owned by Part A/ADG; STATE (charge, recover) =
Part B, either moment; ditch = interrupt-only; get-ready = upfront-only.
SHELF Q: if carrying a shelf and you DITCH onto a better task, you must PUT THE SHELF DOWN at
an empty rack first (AGV carries only one; can't abandon mid-aisle). That offload = extra
travel + drop = real cost -> mid-carry ditching is RARE (usually finish the delivery). This
VINDICATES the user's earlier "recover = put down a shelf" for THIS case: recover-onto-a-
better-task WHILE CARRYING starts with dropping the shelf. (The de-risk sense of recover is
still about risk state, not cargo.)

## 2026-07-11 — DECISION: Part C entirely CUT; focus = finish Part A

Part C (future-readiness) ENTIRELY DROPPED. Rationale: dormant by construction in our always-
full-queue sim (no streaming demand -> no lull -> idle penalty makes direct tasks win). Only
matters with a demand-arrival model. Consequences: Part D now combines A/B only; pay-per-zone
scout dedup (a Part C thing) is moot; the rumor map's SCOUTING use is gone (its risk/b_hard
uses for A/B/D remain). "wait"/background stuff parked to sort later. FOCUS now = finish Part A.
PART A completion state: FUNCTIONALLY complete (screen -> Yen's k-routes -> value×decay+sync
score -> best-route rank -> commit robot->task->route, BOTH AGV + picker; ties RUSH). What's
LEFT is GATED, not buildable-now-cheaply: (1) RISK term (step5) + b_hard (step4) need the Beta
rumor map — BUT both are MOOT without DISTURBANCES (no hazards -> risk=1 -> current placeholder
is already correct); (2) the ~3% gap to RUSH = the DELAY HEAD (Stage 3, learned); (3) collision
filter PARKED (needs ADG-driven execution). Only cheap buildable-now bit: A* dock distances
(minor). => "Finish Part A" = declare the Stage-0 form DONE (risk=1 is legit in a no-
disturbance world) + minor tidy; making risk REAL needs disturbances (separate call).

## 2026-07-11 — why value-first beats deadline-first on ON-TIME COUNT + decay-wtd (not just value)

Q: value-first obviously wins on-time VALUE, but why also on-time COUNT (27.4 vs 20.5) and
decay-weighted (214.7 vs 152.8)?
A: SLACK / ROBUSTNESS. Deadline-first = EDF = works the task CLOSEST to its deadline = LEAST
slack = most fragile. Deterministic single-machine: EDF is optimal for count. But our world is
STOCHASTIC + multi-robot (congestion, picker waits, rendezvous delays) -> a least-slack task
MISSES the moment any delay hits. Value-first, since value is UNCORRELATED with deadline,
grabs AVERAGE-slack tasks (measured ~94 steps buffer vs EDF's ~39) -> survives the random
delays -> MORE land on time (count) AND less-late when late (decay-wtd). So value-first isn't
targeting deadlines; by NOT chasing the tightest, it accidentally gets more slack = robust.
CAVEAT: partly LUCK — value helps count only BECAUSE value is uncorrelated with deadline (high
value accidentally => average slack). If high-value == tightest-deadline, value-first would
HURT count. Principled fix = value x P(on-time): prefer high-value tasks LIKELY to finish in
time (slack on purpose, not by accident). P(on-time) = the delay head (smooth, replaces the
hard makeable/doomed cutoff). One-liner: deadline-first chases least-slack (fragile); value-
first accidentally grabs higher-slack (robust); real fix makes "accidental" into "on purpose".

## 2026-07-11 — dum-dum: why value-first beats deadline-first on ON-TIME COUNT + decay-weighted

Both shed the impossible (Moore-Hodgson); difference = ORDER among makeable: deadline-first
(EDF, do soonest-due) vs value-first (do most valuable with comfortable time).
WHY VALUE-FIRST LANDS MORE ON-TIME (count, not just value): a task due right-now is EASY to
miss (no slack); a task with lots of time is HARD to miss (buffer absorbs hiccups). EDF
deliberately works the buzzer-beaters (least slack) -> one hiccup = miss -> more misses.
Value-first works roomy tasks -> robust -> more actually land on-time. Student analogy: EDF =
always cramming the next-hour assignment (one interruption -> missed deadline); value-first =
do the important one you still have comfy time for (finishes calmly, buffer absorbs
interruptions). Comfortable tasks land; nail-biters don't.
WHY DECAY-WEIGHTED TOO: value-first (1) delivers high-value tasks mostly on-time = full value,
and (2) its misses are rare + small (dropped ones were truly impossible; worked ones had
buffer so slip little -> ~full decayed value). Big value on time + tiny straggler loss = top
decay score.
HONEST FOOTNOTE: part of the win size in OUR data = value uncorrelated with deadline (high-
value tasks happen to be the roomy ones = luck). GENERAL reason holds anyway: comfortable
tasks easier to land on time than buzzer-beaters -> value-first (among makeable) more robust
than racing the clock. (This is the EDF-edge-fragility finding.)

## 2026-07-11 — CORRECTION: our "Moore-Hodgson split" is a crude proxy; real M-H doesn't fit here

User: I thought M-H was FOR maximizing on-time count — so why doesn't the split win? Honest
correction (I over-called it "Moore-Hodgson"):
1. WE DIDN'T BUILD REAL MOORE-HODGSON. Real M-H: line jobs up by deadline, add one at a time,
   whenever the set becomes infeasible KICK OUT THE LONGEST job -> biggest all-on-time set.
   OURS: single blunt cutoff "deadline closer than avg window -> doomed, shove down." A proxy
   inspired by M-H, NOT the algorithm -> no optimality guarantee.
2. REAL M-H ONLY OPTIMAL FOR A SIMPLER WORLD: single machine, fixed known job times,
   deterministic, maximizes COUNT (weighted version is NP-hard even on 1 machine). Our
   warehouse breaks ALL of these: many robots, congestion-dependent travel, rendezvous,
   randomness, and we care about VALUE not count. So M-H's guarantee DOESN'T APPLY.
WHY value-first still wins on-time count: the decider HERE = surviving DELAYS, which is
INVISIBLE to M-H's deterministic model (no delays -> tight & roomy look identical). Under
congestion: EDF works TIGHTEST makeable tasks (fragile); value-first works ROOMIER ones
(robust) -> more land. M-H can't reward robustness it can't see. So our "split" is just a
rough safety filter; the real on-time winner is decided by robustness-under-delay -> favors
value-first. (Ties to EDF-edge-fragility finding.)

## 2026-07-11 — KEY: value-first's on-time-COUNT win is LUCK; value x P(on-time) is the real fix

User caught the hole: does value filtering help on-time if high-value tasks are TIGHT? Answer:
NO. Value filtering does NOT inherently give on-time count. Two INDEPENDENT things got tangled:
  VALUE decides WHICH tasks you do; ROOMINESS (slack) decides WHETHER they land on time.
In our data value & deadline are UNCORRELATED -> high-value tasks aren't the tightest -> value-
first happens to pick roomy tasks -> more on-time. LUCK of the data.
Flip it (high-value = tight): value-first grabs tight high-value tasks -> fragile -> STILL wins
on-time VALUE (grabbed the valuable ones) but NO on-time-COUNT win (ties/trails deadline-first).
SCORECARD: on-time VALUE win = FUNDAMENTAL (always prioritizes value); on-time COUNT win = LUCK
(only when value != tightness). The count win came from the roominess riding along with value,
not from value itself.
REAL FIX (why the plan wants the delay head): score value x P(on-time) per task. high-value+roomy
-> high*high -> do; high-value+TIGHT -> high*LOW -> SKIP (probably miss, don't burn a robot);
low+roomy -> low*high -> only if nothing better. Handles BOTH worlds, no reliance on the value/
deadline correlation. THAT is why smooth P(on-time) (delay head) > our blunt makeable/doomed
cutoff: the cutoff only works when luck is on your side; value x P(on-time) works always.

## 2026-07-11 — Part A DOES top-rank fragile barely-makeable high-value tasks (binary-cutoff hole)

Q: does current Part A prioritize high-value+ROOMY, or (via the fake M-H split) high-value+TIGHT?
ANSWER: the makeable/doomed split is BINARY -> "makeable" is a FLAT tier. A barely-makeable task
(finishes with 1 step to spare) gets the SAME 1000+value as a super-roomy one (200 steps spare).
Roominess is INVISIBLE inside makeable. So: truly-over-deadline high-value -> doomed (good,
deprioritized); but high-value + TIGHT-yet-just-makeable -> top of makeable (1000+bigvalue) ->
Part A grabs it FIRST, and it's FRAGILE (one delay = miss). So YES, Part A top-ranks fragile
barely-makeable high-value tasks. The cutoff only sheds the TRULY impossible; among "possible"
it gives no defense against fragile picks. Only works for us because value uncorrelated with
deadline (luck), same as before.
CHEAP STOPGAP (no delay head): require a SAFETY MARGIN to count as makeable -- "makeable only if
I finish with X extra steps to spare" -> pushes tight-but-barely-makeable into doomed -> Part A
stops top-ranking the fragile ones. Already have `_window_safety` multiplier (>1 = shed more
conservatively). A crude fixed-buffer version of value x P(on-time); needs no learning.

## 2026-07-11 — RECAP: the RUSH -> Part A arc (why, what, and the honest result)

WHY WE MOVED (the twist): NOT because RUSH had a problem. RUSH is the best scalar policy and
works great. We moved to Part A because the PLAN specifies it, and because Part A is the
FOUNDATION for things RUSH structurally can't do: collision filtering (needs routes), risk
scoring (routes+map), ADG execution (committed routes), Part D (per-robot plan shortlists).
Capability/fidelity, not score.
RUSH = scalar: one number per task (makeable-via-global-window, then value, decay for late),
sort queue, assign nearest AGV; pickers to nearest urgent AGV. NO routes.
PART A = per-robot funnel: cross-off -> cheap screen (~15) -> Yen's k-routes -> filter -> score
(value×decay + rendezvous SYNC) -> rank by best route -> commit robot->task->ROUTE. Same for
pickers (which AGV-rendezvous to serve). Generates + commits real routes.
WHAT GOT BUILT: cheap screen, Yen's (AGV grid + picker highway graph), the funnel, sync-up
(penalize partner-wait), return-to-free, picker funnel, committed routes.
HONEST RESULT: Part A did NOT beat RUSH. on-time value 198.8 vs 205.5 (~3% behind), slightly
MORE deliveries (35.3 vs 34). The picker sync-up was the one measurable in-Part-A gain (~23.7
-> ~26 on-time). Ceiling ~= RUSH.
WHY THE GAP: Part A judges makeable/doomed from a per-task rollout FINISH (traffic-BLIND);
RUSH uses a global window MEASURED from real runs (traffic-calibrated). Blind-per-task <
crude-calibrated. That gap = the delay head's job (Stage 3).
BOTTOM LINE: Part A's point was never to beat RUSH's number -- it's to replace the scalar
shortcut with the plan's real route-aware per-robot machine so filters/risk/ADG/Part D have a
foundation. Matches RUSH on value while carrying that structure. Score gains come LATER.

## 2026-07-11 — confirm: "shed-then-value" == "value-then-shed" (filter+sort commute)

User: is "sort by value then cross off deadline" == "cross off deadline then value"? YES, same.
WHY: "cross off deadline" = a FILTER (makeable/doomed, looks at DEADLINE); "sort by value" = a
SORT (looks at VALUE). Independent dimensions -> filter & sort COMMUTE -> identical final order:
makeable-by-value on top, doomed at bottom, same task picked. (Holds because our shed is
deadline-based, independent of value; if shedding depended on value it wouldn't commute.)
THE THING THAT ACTUALLY MATTERS (don't confuse): not the ORDER of filter-vs-sort, but WHAT key
you sort the makeable survivors by -- VALUE (Value/Rush) vs DEADLINE/EDF (Deadline policy).
Those differ (value-first landed more on-time in our data). Once you pick value as the sort
key, shed-before or shed-after gives the identical list.

---
## 2026-07-15  DELAY HEAD trained to plateau (Stage 3, learned head #1)
GOAL (user): train the delay head until MAE and RMSE plateau, then compare efficacy to baselines.
NOT value x P(on-time) yet -- just the regressor: features -> delay the traffic-BLIND rollout missed.
  label = actual_finish - pred_finish (clean empty-world rollout estimate logged at each COMMIT).
DATA: PartAController(DIARY=True), 30 seeds x 500 steps -> 1047 delivered-task rows.
  delay mean 16.9, std 17.4, range [-10, 150] steps. Heavy right tail (jams).
MODEL: LightGBM, objective=L1 (optimises MAE), early-stopping on a 20%-holdout val split ->
  trained UNTIL PLATEAU, not a fixed round count. Plateau/best_iteration = 92 rounds.
  curve: val MAE 11.83(r1) -> 11.40(r50) -> 11.35(r92, best) -> 11.41(r150, overfits). Flat = real plateau.
RESULT (val set):        MAE     RMSE
  formula (predict 0)   17.02   24.31   <- the raw traffic-blind rollout's implicit assumption
  mean    (predict avg) 12.54   17.89   <- constant; beating THIS proves the features carry signal
  HEAD    (LightGBM)    11.35   17.86
  head beats formula: MAE +33.4%, RMSE +26.5%  (ship gate >=15% -> PASSES on both)
  head beats mean   : MAE  +9.5%, RMSE  +0.2%
top features (gain%): dl_slack 25, pred_finish 18, picker_eta 15, my_wait 12, dock 11.
READ (honest): the head is a solid, calibrated win over the thing it must beat -- the raw rollout
  (+33% MAE). But most of that is just "delays exist, ~17 steps on average"; the situational
  features add only +9.5% MAE and ~0 RMSE over a constant. RMSE ~= the mean baseline -> the head
  does NOT predict the big-delay tail (the jams that blow up RMSE); those are ~unpredictable from
  these 10 features. So: good enough to de-bias the rollout's optimistic finish (kills the +17 bias),
  weak at flagging WHICH task will hit a jam. Saved results/delay_head.pkl {model, cols, best_iteration}.
NEXT (not done): wire delay_head into Part A's scoring hook (finish_s = finish + head(feat)),
  then bake off Part A+head vs RUSH on on-time value -- that tests whether de-biasing the finish
  fixes Part A's traffic-blindness. Richer features (local density map, per-corridor occupancy) if
  we want the tail.

---
## 2026-07-15  DELAY HEAD wired into Part A + 4-way bake-off (FIFO/RUSH/Part A/Part A+head)
Wired results/delay_head.pkl into PartAController.delay_head (hook line 348:
finish_s = finish + max(0, head(feat))). 10 seeds, 500-cap, same deadlines+values.
MEAN over 10 seeds:
  policy        deliveries  on_time  late  on_time_value
  fifo             31.1      17.4    13.7      97.5     <- naive baseline, far behind (sanity OK)
  rush             34.0      27.4     6.6     205.5     <- still the leader
  parta            35.3      26.7     8.6     198.8
  parta_head       35.1      26.5     8.6     198.7     <- head made NO difference (198.8 -> 198.7)
VERDICT: the head is accurate (de-biases the rollout finish by +33% MAE) but wiring it in
  does NOT close Part A's ~3% on-time-value gap to RUSH. Head-on ~= head-off, within noise.
WHY (ties back to training): the head beats the CONSTANT-mean baseline by only +0.2% RMSE ->
  it captures the ~17-step AVERAGE bias but NOT the variance (which task hits a jam). In Part A
  the finish only enters via the makeable/doomed SPLIT (completion=finish_s); value-ranking among
  makeable is pure value. A near-constant +17 shifts all candidates ~equally -> argmax barely moves;
  the split reclassifies some borderline tasks but that reshuffle nets ~0. RUSH's GLOBAL window is a
  LOW-VARIANCE empirical mean; per-task finish (even bias-corrected) is still HIGH-VARIANCE. Removing
  bias doesn't remove variance -> RUSH's classifier still wins. Exactly the RolloutRushController
  result (per-task window LOST to global window) restated: congestion/picker-wait dominates, so a
  per-task estimate is noisier than the fleet mean. The head fixes optimism, not noise.
  Also reconfirmed: Part A more deliveries (35.3>34.0) but fewer on-time (26.7<27.4) = syncs to
  finish more total, RUSH's calibrated window catches more of them on time. Head didn't change it.
IMPLICATION for value x P(on-time): a delay-MEAN head won't help; you need a head that predicts
  the VARIANCE / P(late) per task (jam probability), not the mean delay. That needs richer features
  (local corridor occupancy, congestion map) — the current 10 features can't see the tail.
Wrote results/delayhead_bakeoff.csv, scripts/verify_delayhead.py.

---
## 2026-07-15  Gave Part A RUSH's own doability filter -> STILL didn't close the gap (key result)
Tested the user's hypothesis: "make Part A choose tasks it can do, like Rush." Added policy
parta_window = PartAController(USE_GLOBAL_WINDOW=True) -> Part A's routing/sync/value scoring but
RUSH's CALIBRATED global window as the makeable/doomed split (identical doability test to RUSH).
MEAN over 10 seeds (same harness):
  policy         deliveries  on_time  late  on_time_value
  rush              34.0      27.4     6.6     205.5
  parta             35.3      26.7     8.6     198.8
  parta_head        35.1      26.5     8.6     198.7
  parta_window      35.8      26.3     9.5     197.4   <- Rush's filter, NO help (197.4 <= 198.8 < 205.5)
CONCLUSION: the doability FILTER was never the gap. Both Part A variants now classify doable tasks
  exactly as RUSH does, and still trail RUSH by ~8 on-time value. So the gap lives DOWNSTREAM of the
  split, in Part A's own scoring machinery (its supposed advantage). Signature holds across every
  Part A row: MORE deliveries (35-36 > 34), FEWER on-time (26 < 27). Part A's sync-up term
  (score -= W_SYNC*my_wait, W_SYNC=0.3) optimizes for FAST CYCLES (prefers low picker-wait tasks) ->
  pumps throughput; RUSH is PURE value-first among doable tasks. Under a jammed queue value-first ->
  on-time VALUE, cycle-speed-first -> more deliveries that are lower-value / late.
NEXT LEVER (not yet run): Part A makeable score is already value-first (1000+v) but the sync penalty
  pulls it off pure value. Setting W_SYNC=0 makes parta_window's makeable ranking IDENTICAL to RUSH's
  (pure value) while keeping routing feasibility. Clean isolation: if parta_window+W_SYNC=0 snaps to
  ~205, the ENTIRE Part A<RUSH gap = the sync/throughput bias. Awaiting user go.
Files: scripts/verify_delayhead.py (5 policies), results/delayhead_bakeoff.csv.

---
## 2026-07-15  W_SYNC tune -> OVERFIT to noise; Part A vs RUSH gap is WITHIN NOISE (definitive)
Swept W_SYNC on parta_window (RUSH filter), objective = on_time_value, grid {0,0.1,0.2,0.3,0.5},
10 tuning seeds. Curve ZIGZAGGED (0.1=192 worst, 0.2=205.8 best, 0.3=197.4) -> non-monotonic =
noise signature (spread 14 < per-seed swing +-29). Validated the "winner" on HELD-OUT seeds 10-29:
                 seeds 0-9 (tune)   seeds 10-29 (holdout)
  RUSH               205.5               194.1
  W_SYNC=0.0         201.9               185.7
  W_SYNC=0.2         205.8  <-picked     187.4   <- COLLAPSED, now 6.7 behind RUSH
  W_SYNC=0.3(deflt)  197.4               196.6   <- best on holdout, EDGES RUSH (196.6>194.1)
VERDICT: ranking fully REORDERED across seed sets. The tuned optimum (0.2) was pure luck and
  evaporated out-of-sample; the default 0.3 won held-out and even beat RUSH there. So:
  (1) DO NOT ship a W_SYNC tuned on 10 seeds -- textbook overfitting.
  (2) The entire Part A vs RUSH ~3-8 pt on_time_value "gap" is WITHIN NOISE. seeds0-9: RUSH +8;
      seeds10-29: Part A(0.3) +2.5. Neither policy is reliably better at this sample size.
      SE(on_time_value) ~ 17/sqrt(N): ~5.4 @10 seeds, ~3.8 @20 -> the gaps are ~1 SE = not significant.
  We were chasing a ghost. To make ANY Part A-vs-RUSH or W_SYNC claim you need FAR more seeds
  (50-100+) to shrink SE below the ~3 pt effect. The delay head, Rush's-filter swap, and W_SYNC
  tune all land inside the noise band -> none is a real, reproducible win.
PRACTICAL TAKEAWAY: stop optimizing on_time_value at 10-20 seeds; the metric's noise floor (~+-5)
  exceeds every effect we've chased today. Either (a) run 100+ seeds to get real signal, or (b)
  accept Part A ~= RUSH and move on. Keep default W_SYNC=0.3.
Files: scripts/tune_wsync.py, results/wsync_sweep.csv, results/wsync_holdout.out.

---
## 2026-07-15  VARIANCE (congestion-aware) delay head vs BASELINE, 100 seeds -> tail is IRREDUCIBLE
Built a 2nd head alongside the baseline. VARIANCE head = baseline features + 9 LIVE congestion
features: temporal (delay_ema=EMA of realized delays, dur_recent, dur_trend, deliv_rate) +
normalized/size-agnostic (busy_frac, free_pk_frac, q_per_agv, local_density, path_stretch). All
tracked continuously as the sim runs (added always-on delivery bookkeeping to PartAController).
100 seeds -> 3464 delivered-task rows. delay mean 16.9, std 18.2, range [-14, 221].
                        MAE     RMSE   tail-RMSE (delay>median=jams)
  formula (predict 0)  17.22   24.57    34.14
  mean (predict avg)   12.82   18.10    21.94
  BASELINE head        11.61   18.05    23.91
  VARIANCE head        11.54   17.81    23.51
  variance vs baseline: MAE +0.6%, RMSE +1.3%, tail-RMSE +1.7%  (all negligible / within noise)
  var-head top features (gain%): dl_slack 14, picker_eta 12, dock 10, delay_ema 10, pred_finish 9,
    dur_recent 8, my_arrival 7  -> the congestion features (delay_ema, dur_recent) DO rank, but add ~0.
DAMNING TAIL RESULT: on the jam tail, BOTH heads (23.9 / 23.5) are WORSE than just predicting the
  CONSTANT mean (21.94). The models regress toward feature-correlated values and MISS the big delays.
  -> The per-task jam tail is UNPREDICTABLE from commit-time observables, EVEN with live congestion.
WHY: a task's jam is set by stochastic interactions that happen AFTER commit (which other robots
  cross its path, picker contention that emerges later). Commit-time state doesn't determine them.
  Delay = population MEAN + irreducible noise. delay_ema/dur_recent capture the drifting mean level,
  not which task spikes.
BIG IMPLICATION (paper-worthy): P(on-time) is ~CONSTANT across tasks (~= base rate), so value x
  P(on-time) CANNOT differentiate tasks with these observables -> a learned per-task risk head is a
  dead end here. This is exactly WHY nothing beats RUSH's single calibrated-mean window: the mean is
  all there is to know; the variance is unforecastable. RUSH already uses the mean optimally.
100-seed baseline also CONFIRMS the 30-seed head (MAE 11.35->11.61, RMSE 17.86->18.05) = stable.
Kept both: results/delay_head.pkl (baseline), results/delay_head_var.pkl (variance).
Files: scripts/train_variance_head.py; PartAController now logs congestion features always-on.
NEXT (open): 100-seed POLICY bakeoff to finally resolve Part A vs RUSH with real power (the "hundred
  sheets") -- but the head result predicts it'll confirm ~tie, since the differentiating signal
  (per-task risk) provably isn't there.

---
## 2026-07-15  REROUTE (congestion) comparison, 30 seeds -> first metric where policies DIFFER
Added reroutes = sum of env info["clashes"] (each counted clash triggers find_path around the
blocker; warehouse.py:474-479, code labels clash_pairs "for each reroute this step"). 30 seeds.
                 median  mean   max   #storms(>150)   otv    rr/deliv
  fifo             34    32.4    46        0          92.5     1.0
  rush             60    76.8   277        2         197.9     2.7
  parta            68   141.6  1286        4         195.1     5.4
  parta_window     69   106.8  1258        1         196.8     4.0
KEY FINDINGS:
1. MEAN is fat-tail-dominated (Part A mean 141.6 vs median 68 = 2x) -> report MEDIAN. Reroutes are
   a heavy-tailed process: mostly moderate, occasionally a gridlock STORM (max 1286).
2. Typical (median) churn: FIFO 34 << RUSH 60 < Part A 68 ~= parta_window 69. Among productive
   policies, Part A reroutes ~13% more per typical seed than RUSH, and 2x per delivery (5.4 vs 2.7).
3. STORM FREQUENCY is the real differentiator: FIFO 0, RUSH 2, Part A 4, parta_window 1 (of 30).
   Part A gridlocks TWICE as often as RUSH. Giving Part A RUSH's calibrated global window
   (parta_window) HALVES+ the storms (4->1) -> the window prevents Part A's per-task traffic-blind
   finish from clustering robots into congestion. (Seed 24 stormed for ALL aggressive policies incl
   parta_window 1258 -> some seeds are pathological regardless = substrate property.)
4. FIFO reroutes least but only because it moves less productively (otv 92 vs ~197) -> low churn is
   not virtue here, it's under-utilization.
SYNTHESIS (ties to the delay head): the unpredictable DELAY TAIL (variance head couldn't forecast)
   IS these reroute storms -- the tail of the delay distribution. You can't PREDICT which task jams
   (irreducible from commit-time state), but you CAN pick a policy that STORMS LESS: RUSH's global
   window storms half as often as Part A's per-task finish. So the answer to "can't we do anything
   about the tail?" is REDUCE it structurally (calibrated-window assignment), not forecast it.
   This is the first dimension where RUSH is not just ~tied but genuinely MORE ROBUST than Part A.
Files: scripts/verify_reroutes.py, results/reroutes_bakeoff.csv.

---
## 2026-07-15  CONGESTION FORECAST works: eliminates reroute STORMS, best mean value (30 seeds)
Built the congestion-forecast planner (scripts/congestion_policies.py). PartACongestionController:
each step builds a per-cell traffic FORECAST from 3 sources -- (1) busy robots' remaining paths,
(2) FINISHING robots (within FINISH_HORIZON=40 of target): predict their NEXT task (same cheap-screen
scoring) + route from where they finish [the future-aware part], (3) FRESH: each free robot's route
stamped as it commits (prioritized = robots assigned one-at-a-time, each dodging prior). Route pick
(Piece A): min(len + 0.3*forecast-congestion) over the k Yen routes. Reroute (Piece C): env.find_path
adds the same forecast to cell costs (congestion_weight=0.3) so detours dodge predicted traffic too.
Adherence drives the chosen route. Also RushYenController = Rush + Yen route + adherence (no forecast).
Env changes: find_path now composes CONGESTION (congestion_grid/weight) + ADHERENCE (prefer_committed
+ agent.committed_cells, off-route cost 1.5); PartAController got hooks _pre_dispatch/_order_free_agvs/
_pick_route/_on_commit (default = plain Part A).
30 seeds (paired: seed N = identical world for all policies):
  policy             deliv on_time late  otv   reroutes rr/deliv stucks | otv_med rr_med rr_max storms>150
  fifo               31.4  17.1  14.3   92.5    32.4    1.0    2.1  |   97     34     46      0
  rush               33.2  26.9   6.3  197.9    76.8    2.7   10.2  |  200     60    277      2
  rush_yen           33.0  26.3   6.7  190.2    83.4    3.0    5.4  |  192     62    761      1
  parta              34.9  26.0   8.9  195.1   141.6    5.4   12.0  |  198     68   1286      4
  parta_congestion   36.1  26.7   9.4  201.4    61.1    1.7    4.5  |  196     61     94      0
HEADLINE: parta_congestion ELIMINATES the reroute storms -- 0 storms, max 94 reroutes, vs parta's 4
  storms/max 1286, rush's 2/277, rush_yen's 1/761. On the 4 seeds that gridlocked plain Part A
  (3,7,17,24) the forecast held every time: seed24 (broke ALL others) parta rr1286/otv107, rush
  rr277/otv92 -> parta_congestion rr86/otv176.
- BEST mean on-time value (201.4 > rush 197.9 > parta 195.1) AND best deliveries (36.1) AND lowest
  rr/deliv (1.7) AND lowest stucks (4.5) of the productive policies.
- HONEST NUANCE: on a TYPICAL seed it's ~tied (otv median 196 vs rush 200, rr median 61 vs 60 -- both
  within the ~+-5 noise band). The mean-value EDGE and the reroute-mean win come ENTIRELY from not
  cratering on storm seeds. So: same on calm seeds, dramatically more robust on bad ones, best on avg.
- rush_yen (adherence WITHOUT forecast) is WORSE than rush (190.2<197.9) and stormed once (761) ->
  driving committed routes is only safe WITH the congestion spreading; adherence alone is risky.
This closes the session arc: delay head couldn't predict the tail (irreducible) -> the tail IS the
  reroute storms -> can't forecast WHICH task jams, but CAN forecast where traffic builds and route
  around it -> storms eliminated structurally. The lever was REDUCE the tail, not predict it.
Cost: forecast is per-step (predict + Yen + grid) -> ~2x slower than plain Part A. Next: 100-seed
  confirm of storm frequency; tune CONG_LAMBDA/weight/horizon; time-indexed (space-time) forecast.
Files: scripts/congestion_policies.py, scripts/verify_congestion.py, results/congestion_bakeoff.csv.

---
## 2026-07-15  Congestion policies: 62/30/15-seed bake-offs + new variants + the throughline
### 62-seed 5-policy bake-off (results/bakeoff_100.csv; run stopped at 62/100 on teardown)
  policy            otv_mean otv_med rr_mean rr_med rr_max storms>150
  parta_congestion    199.8   198     74.5    60     582      3   <- WINS (value + robustness)
  rush                197.4   200     92.4    61     923      5
  parta_varhead       194.9   200    134.6    66    1311      6
  rush_congestion     194.8   196     93.5    59    1311      3
  parta_head          193.8   199    132.0    66    1311      5
- parta_congestion best on value AND robustness (lowest reroutes, mildest max). Delay heads WORST;
  parta_head ~= parta_varhead (variance head as a POLICY gives nothing over baseline head, both storm).
- On MEDIANS all ~196-200 = tied; the whole separation is the storm tail (robustness), not typical value.
- rush_congestion stormed on seed 24 (1311) where parta_congestion didn't (86): congestion map on RUSH's
  selection is NOT robust -- it needs Part A's PRIORITIZED machinery (order + finishing-prediction) to
  actually break gridlock. Same map, but Rush can only steer the ROUTE, not the destinations; adherence
  then locks Rush INTO the jam it couldn't avoid.

### New variants built (scripts/congestion_policies.py)
- RushCongestionFullController (rush_cong_full): Rush's global window + full congestion funnel
  (task+route+soft reroute). 15-seed: 197.1 otv = WORST of the four. Rush's window is a WORSE per-task
  cutoff than Part A's per-task finish INSIDE a funnel that already has richer info -> the window is
  Rush's good part *as a scalar policy*, not an upgrade inside the funnel.
- PartACongestionTaskController (parta_cong_task): + congestion-aware TASK score (penalize task by its
  best route's congestion). 15-seed: 203.5 ~= champion 203.0 (within noise) but MORE reroutes/stucks +
  a mild seed-5 storm the champion dodged. No clean win.
- PartACongestionFinishController (parta_cong_finish): CONGESTION-AWARE FINISH -- add k*route-congestion
  to the empty-world finish BEFORE the makeable/doomed deadline check (the rules-based version of the
  delay head). 30-seed check (K=2.0, incl storms): 199.2 vs champion 201.4 = -2.2, PAIRED 4 wins/10
  losses/16 ties -> DOES NOT HELP (slightly worse). Probe: NO stable K (inert <=1, destabilizing >=3,
  seed24 craters at K=8). Storm seeds identical to champion.

### THE THROUGHLINE (paper-worthy)
- THREE attempts to feed a per-task DELAY ESTIMATE into decisions all failed: (1) learned delay head,
  (2) variance head (congestion features), (3) rules-based congestion-finish. The problem was never HOW
  the delay is estimated -- the makeable/doomed classification just doesn't benefit from a per-task delay
  estimate; injecting one (learned OR computed) causes erratic task abandonment, adding churn not signal.
- Congestion map's power is ENTIRELY in AVOIDANCE (routing around the jam), NOT PREDICTION (deadline est).
  Use traffic to AVOID the delay (route), not to PREDICT it (deadline filter). Deadline filter best left
  simple (empty-world finish). => champion pipeline: cheap screen (value-Manhattan, traffic-BLIND prefilter)
  -> traffic-AWARE least-congested route -> plain empty-world deadline check -> drive w/ congestion soft reroute.
- Compute-vs-learn principle: congestion/occupancy is COMPUTABLE from known movement rules (a mini rollout),
  so compute it -- don't learn it. Per-task delay is neither computable nor cleanly learnable -> don't predict
  it, AVOID it with rules. Learned heads only earn their place for things that are irreducibly uncertain AND
  have learnable structure; here neither the rollout (rules) nor a head could beat routing-around.
- Variance head vs Rush window (why Rush's aggregate wins): the head's INPUTS update (delay_ema/dur_trend live,
  even had Rush's window signal) but its MODEL is frozen and it targets the CHAOTIC individual delay -> noise.
  Rush's window is a self-updating NON-PARAMETRIC aggregate (running mean of real completion times) used
  directly as the doability threshold -> reliable (chaos averages out). Same info, aggregate-answerable vs
  individual-unanswerable. The head literally HAD the window's data + more and still couldn't beat a constant.
### Infra
- Cached the AGV graph (sim_priority _assign_tasks: build_agv_graph once, not per step) -> big speedup.
- Added hooks to PartAController: _pre_dispatch/_order_free_agvs/_pick_route/_on_commit/_task_score_adjust/
  _finish_delay (all default no-op -> plain Part A unchanged; congestion controllers override).
- env.wait_not_reroute (reverted approach), env.prefer_committed + committed_cells (adherence),
  env.congestion_grid/weight (find_path steers around forecast). Files: verify_100/variants/finish.py.

---
## 2026-07-15  Is the congestion map a "world model"? YES. Why is the TIME part so noisy? (idiot terms)
YES it's a world model: we roll POSSIBLE FUTURES forward -- each robot's path + a prediction of what
the about-to-finish ones will do next -- and accumulate them into a congestion map of where the crowd
will be. That's a (lightweight, one-pass) rollout of the future. It models SPACE (where) reliably and
skips TIME (exactly when / how many steps late), which is the noisy part.

WHY THE TIME/DELAY PART IS SO NOISY -- the highway analogy (idiot terms):
  Predicting WHERE the traffic is = predicting the highway will be jammed at 5pm. Dead easy and
  reliable: you know where all the cars are going, so you know which roads fill up. You can route
  around it without ever knowing a single exact number.
  Predicting a task's DELAY = predicting exactly how many minutes YOUR specific car will lose in that
  jam. That depends on which lane you happen to pick, whether the guy in front taps his brakes, whether
  you catch or miss each light, and a fender-bender at exit 12 you couldn't see coming -- a hundred tiny
  coin-flips that pile on top of each other. Nobody can call that number to the minute.
  SAME TRAFFIC, two questions: "is the highway busy?" (a MAP you steer by -- reliable) vs "how many
  minutes late will I be?" (a DICE ROLL -- hopeless). The crowd is predictable; your personal wait is
  a stack of coin-flips.
WHY: WHERE is an AGGREGATE (many cars average out to a smooth, knowable pattern). HOW-LATE is one
  INDIVIDUAL threading a chaotic chain of micro-events (each collision/wait depends on exact timing,
  and small timing differences swing the total). Aggregates are smooth; individual chaotic chains are
  noise. So: use the map to AVOID the jam (needs only "busier vs emptier" = survives noise), never to
  READ OFF a delay (needs a precise number = destroyed by noise). A field you steer around, not a gauge.

---
## 2026-07-15  SOFT P(on-time) vs champion (30 seeds incl storms) -> WORSE; deadline wants a HARD cliff
Built the one open lever: replace the HARD makeable/doomed cut with a SMOOTH weight
score = 1000*P(on-time) + v, P(on-time)=sigmoid(margin/sigma), sigma WIDENED by route congestion
(soft, congestion-aware, degrades gracefully). scripts/congestion_policies.py::PartACongestionSoft;
added _deadline_score hook to PartAController. 30 seeds (0-29):
  policy             otv_mean otv_med rr_mean rr_max
  parta_congestion    201.4    196    61.1    94   <- champion (HARD cliff) WINS
  rush                197.9    200    76.8   277
  parta_cong_soft     191.1    189    58.0    93
- soft vs champ PAIRED: -10.3 value, 5 wins / 25 LOSSES. Decisive loss.
- STORM note: on seeds 0-29 NEITHER congestion policy storms (max ~93); seeds 22/24 storm only for
  rush/non-congestion policies. So there was NO robustness deficit for soft to fix -> it just bled
  value everywhere with nothing to trade for. (Smoke-test seed-24 edge 184>176 was real but irrelevant.)
- WHY soft loses: the HARD 1000+v tier is PROTECTIVE -- every makeable task outranks every doomed one,
  so on-time work is never displaced. Softening lets barely-makeable / risky high-value tasks bleed into
  the ranking and jump the queue -> more missed deadlines -> less on-time value. The cliff protects the
  metric; smoothing breaks that protection.
THROUGHLINE -- 4th confirmation, closes value x P(on-time): (1) learned delay head, (2) variance head,
  (3) rules-based congestion-finish (hard), (4) soft P(on-time) -- ALL fail to beat the simple hard cut.
  The deadline decision wants a SIMPLE HARD CUTOFF; every attempt to make it smarter (predict delay,
  soften, make traffic-aware) hurts. Congestion belongs in ROUTING (avoidance); deadline = clean binary
  tier. CHAMPION parta_congestion stands. File: scripts/verify_soft.py, results/soft_bakeoff.csv.

---
## 2026-07-15  PROBABILISTIC forecast (spread top-K) vs concentrated top-1 -> WORSE (counterintuitive)
Tried Q1's "improvement": spread each finishing-robot prediction over its top-K likely next tasks
(rank-weighted 0.5/0.3/0.2) instead of committing to top-1 -> a true "distribution of possible
futures." scripts/congestion_policies.py::PartACongestionProbController. 10 MIXED seeds
(calm 0,5,9,20 + chaotic 3,7,15,17,22,24):
  policy             otv_mean rr_mean rr_max storms>150
  parta_congestion    199.4    65.4    86      0    <- champion (concentrated top-1) WINS
  rush                191.5    99.0   277      2
  parta_cong_prob     190.2   170.5   893      2    <- STORMS on seeds 7(322) & 24(893)
- prob vs champ: -9.2 value, 4 wins/6 losses, reroute mean 2.6x, storms the chaotic seeds the champion
  holds. DECISIVELY WORSE. (I had predicted prob would be MORE robust -- WRONG.)
- WHY (corrected theory): robustness comes from SUMMING over MANY robots (the known-paths backbone,
  full weight -- preserved in both). But the finishing PREDICTION is a CONTROL SIGNAL, and control
  needs CONTRAST to steer. Concentrated commits 0.5 to ONE route (sharp "avoid HERE"); spreading smears
  0.25/0.15/0.10 (mushy "maybe one of these") -> weak peaks -> weak steering -> robots cluster -> storm
  on heavy-traffic seeds. The map's power is being a CONCENTRATED, DECISIVE field to steer against, NOT
  a soft probability distribution.
- UNIFYING PATTERN (this + soft-P(on-time), both same day): softening a DECISIVE signal to "reflect
  uncertainty" makes control WORSE, twice. soft deadline cliff -> worse; spread forecast -> worse. The
  planner wants DECISIVE signals: HARD deadline tier + SHARP concentrated forecast. Commit to the best
  guess and steer hard; get robustness from AGGREGATING over many agents, not from hedging any one.
File: scripts/verify_prob.py, results/prob_bakeoff.csv. CHAMPION parta_congestion stands.

---
## 2026-07-15  Probabilistic-forecast: 30-seed CONFIRMATION (refines the 10-seed claim)
top-K = top-3, rank-weights [0.5,0.3,0.2] (vs champion's top-1 all-0.5). 30 seeds (0-29):
  policy            otv_mean otv_MED rr_mean rr_max storms>150
  parta_congestion    201.4   196    61.1    94      0    <- champion WINS
  rush                197.9   200    76.8   277      2
  parta_cong_prob     196.1   200    98.0   893      2
- prob vs champ: -5.3, 13W/17L. Champion wins BUT prob's MEDIAN (200) >= champ's (196).
- REFINED LESSON (better than the 10-seed "just worse"): dispersion is HARMLESS-to-slightly-BETTER on
  calm/typical seeds (median tied/up), and CATASTROPHIC on chaotic seeds (storms 7->322, 24->893 that
  the concentrated champion prevents). The whole loss = the storms. So the concentrated/DECISIVE signal
  earns its keep SPECIFICALLY UNDER STRESS: calm -> hedging is free; jammed -> you need the sharp
  "avoid HERE" to keep control, and a diffuse forecast loses grip -> gridlock. Worst kind of cost:
  the hedge fails exactly when you need it. Champion parta_congestion confirmed at 30 seeds.
  File: results/prob_bakeoff30.out.

---
## 2026-07-15  Routes don't need deadline/time-ranking -- congestion-ranking IS the realistic time-rank
Q: do you need to time-rank a task's candidate routes against the deadline? A: NO.
- Yen's k-shortest routes for a task are all NEAR-shortest (differ by a few cells) -> they arrive at
  ~the same time -> they SHARE the deadline verdict (all makeable or all doomed). Time-ranking routes
  by deadline is meaningless -- they're tied on time. The DEADLINE is a TASK-level decision, settled
  once you pick the task; routes inherit the verdict.
- What DOES separate routes = CONGESTION. And congestion-ranking IS the realistic time-rank: a
  "shortest" route through a jam is SLOWER than a slightly-longer empty route (waits/reroutes). So
  length-rank = time-rank in an EMPTY world (routes tied, useless); congestion-rank = time-rank in
  REAL traffic (the true fastest-to-arrive). You're not skipping time-ranking routes -- congestion
  IS your time-ranking, via the traffic proxy instead of naive distance.
- Champion already does exactly this: _pick_route = min(length + LAMBDA*congestion) (realistic
  fastest), deadline checked ONCE at task level on the chosen route. No per-route deadline check.
- BONUS: congestion-ranking helps the deadline FOR FREE (picks the actually-faster route -> more
  likely on time) without any extra computation. ARCHITECTURE: route = congestion; deadline = task.

---
## 2026-07-16  DISTURBANCES: random blockages + why they CAN'T be predicted + Beta rumor map (Part 2)
### Part 1 -- random disturbance spawning (env)
Added opt-in random disturbances to wwm_sim.Warehouse: env.disturb_rate (per-step spawn prob) +
env._disturb_rng (seeded RandomState). Each step maybe spawns a 1-3 cell blob on HIGHWAY cells for
20-60 steps, then despawns. find_path treats disturbed cells as obstacles (never blocks an agent's
own start/goal); agents whose committed path crosses a new blob re-plan around it
(_reroute_around_disturbance, counted as disturb_reroutes). Schedule is POLICY-INDEPENDENT (only rng
+ static highway mask) -> IDENTICAL for every policy on a seed (paired). 30-seed ranking check
running (scripts/verify_disturb.py): if the ranking HOLDS under disturbances, we DON'T need a
disturbance-prediction feature.

### WHY DISTURBANCES CAN'T BE PREDICTED (the thing to write down)
Disturbances are EXOGENOUS RANDOM NOISE. Unlike congestion -- which is a rollout of KNOWN robot
futures (where robots are headed), so it's forecastable and steerable -- a disturbance depends on
NOTHING we can observe ahead of time: not on the robots, not on the tasks, not on prior state. It
has NO ranking, NO inferable structure, NO "probability of disturbance HERE vs THERE" you could
compute in advance. You could only forecast them if you had a full model of the warehouse's failure
layout (which cells break, when) -- and building/assuming that global layout model is EXACTLY what
this project is trying to AVOID (we want a planner that works without a hand-built world map). So:
congestion = predict-and-avoid (rollout); disturbance = observe-and-remember (no prediction possible).
This is why the delay/congestion machinery does NOT extend to disturbances -- there's nothing to roll
forward.

### Part 2 -- Beta rumor map (wwm_sim/rumor_map.py) -- BUILT, not yet acted on
Because you can't PREDICT disturbances, you can only OBSERVE them into a calibrated, decaying belief.
Per cell Beta(alpha,beta): SIGHTING (disturbance seen within sensing radius of a robot) -> alpha+=1;
CLEAN traversal (robot on a non-disturbed cell) -> beta+=1; DECAY each step toward the uniform prior
(stale evidence fades -> non-stationary-friendly). belief = alpha/(alpha+beta). It is NOT reliant on
other robots (unlike congestion); it's a backward-looking OBSERVATION map, not a forward rollout.
Demo (scripts/demo_rumor.py, champion + disturb_rate 0.15, 500 steps): 112 cells ever disturbed;
top-10 hotspots all high true-disturbance; PRECISION@20 = 20/20 -> the map lands belief exactly where
disturbances actually were, from sightings alone. ACTING on it (Part B support tier + general task
selection) is deliberately LEFT FOR LATER.

---
## 2026-07-16  Disturbance 30-seed ranking result (Part 1) -> robustness HELD, value wobbled
30 seeds, disturb_rate=0.1, paired schedule. WITH disturbances:
  policy            otv_mean otv_med rr_mean dr_mean rr_max
  parta_head          198.2   200    105.3   8.3    1155
  parta_congestion    194.0   191     61.7   8.1     207   <- uniquely STORM-PROOF (max 207 vs 937-1296)
  rush_congestion     190.0   194    137.5   8.1    1296
  rush                186.3   192     99.1   8.3     937
- ROBUSTNESS ranking HELD (the key one): parta_congestion is the ONLY non-storming policy (max 207);
  everyone else gridlocks HARDER under disturbances (937-1296). The congestion machinery's storm-
  prevention holds and matters MORE under disturbances.
- VALUE ranking WOBBLED (within noise): parta_head nudged ahead on value (198.2 vs 194.0); without
  disturbances parta_congestion led value + parta_head was near-worst, so disturbances flipped those
  two on value. MECHANISM: adherence is mildly counterproductive vs disturbances it can't forecast --
  the champion commits routes for ROBOT-congestion; a random blockage on the committed route makes
  adherence tug the robot back toward the blocked path (friction), while parta_head (no committed
  routes) reroutes freely. Small, within-noise, but sensible.
- CONCLUSION (answers "do we need disturbance prediction?"): NO. (1) can't predict disturbances anyway
  (exogenous noise); (2) champion handles them REACTIVELY (find_path routes around observed blockages)
  and stays storm-proof. The value wobble argues NOT for a predictive head but for making ADHERENCE
  disturbance-aware (drop the committed route when a disturbance blocks it, don't fight to rejoin) --
  small tuning, candidate follow-up. Files: scripts/verify_disturb.py, results/disturb_bakeoff.csv.

---
## 2026-07-16  DISTURBANCE-AWARE ADHERENCE tweak -> STRICT improvement (user's idea, validated)
Tweak (env.disturb_drop_adherence): when a disturbance lands on an agent's COMMITTED route, RELEASE
adherence (clear committed_cells) so the reroute takes the SHORTEST path around it instead of fighting
to rejoin the blocked route. "If you can do shorter, do shorter." warehouse.py:_reroute_around_disturbance.
30-seed (disturb_rate=0.1):
  policy         otv_mean otv_med rr_mean rr_max
  champ_rigid      193.7   187    62.3    207
  champ_release    195.2   195    61.7    207   <- strict improvement, same robustness
  parta_head       197.7   199   106.6   1155   (higher value BUT storms)
- release vs rigid: +1.4 value, 1 WIN / 0 LOSSES / 28 ties. Never hurts; occasionally helps big
  (seed 2: +42). IDENTICAL robustness (max 207, rr slightly lower). Median 187->195.
- WHY mostly ties + rare big win: adherence is a gentle 1.5x preference and committed~=shortest, so
  "rejoin blocked route" ~= "shortest detour" usually -> tie. But when a disturbance makes rejoining
  genuinely costly, rigid fights it (value loss) and release re-optimizes (recovers) -> the seed-2 win.
  It's free insurance: neutral almost always, a save when it matters.
- vs parta_head: parta_head has higher value MEAN (197.7) but STORMS (max 1155 vs release 207). So
  release keeps the champion's storm-proofing AND recovers value -> the better ROBUST choice.
RECOMMENDATION: make disturb_drop_adherence the DEFAULT (strict improvement, zero robustness cost).
File: scripts/verify_disturb_adhere.py, results/disturb_adhere_bakeoff.csv.

---
## 2026-07-16  Deadline-ETA feature (congestion -> deadline) under disturbances -> NEUTRAL; refutes the realism hypothesis
User hypothesis: parta_head edges the champion under disturbances because its ~constant delay makes
the makeable/doomed check REALISTIC (champion uses the raw optimistic empty-world finish -> over-
commits). Test: parta_congestion + release + DEADLINE-ETA (inflate finish by K*route-congestion = the
"most likely single future" ETA) before the deadline check. K=1.0. 29 seeds, disturb_rate=0.1:
  policy            otv_mean otv_med rr_mean rr_max storms
  champ_rigid         193.7   187    62.3   207    1
  champ_release       195.2   195    61.7   207    1
  champ_release_dl    195.5   195    62.3   207    1   <- deadline-ETA: DEAD NEUTRAL
  parta_head          197.7   199   106.6  1155    2   (higher value BUT storms; seed24 craters 116/1155)
- deadline-ETA vs release: +0.3, W3/L3/T23 = NEUTRAL. Using congestion for BOTH routing AND the
  deadline = redundant double-count, adds nothing. (5th deadline-tinkering negative: delay head,
  variance head, congestion-finish, soft P(on-time), now congestion-ETA-under-disturbances.)
- REFUTES the deadline-realism hypothesis: if parta_head's edge were deadline realism, ADDING realism
  to the champion would close the gap -- it didn't (neutral). Plus we already knew the head's constant
  is INERT (parta_head ~= plain parta, 198.7 vs 198.8). So parta_head's edge is NOT deadline realism --
  it's having NO congestion machinery (more value-greedy on calm seeds, +2.6 mean) at the cost of
  STORMS (max 1155 vs champion 207). Same value-vs-robustness tradeoff, not a deadline effect.
- RELEASE still a strict win over rigid (195.2 vs 193.7, zero robustness cost) -> keep it.
DECISION: drop the deadline feature (neutral/redundant); keep release; champ_release is the robust
  champion. File: scripts/verify_deadline_eta.py, results/deadline_eta_bakeoff.csv.

---
## 2026-07-16  Congestion -> DEADLINE-ONLY (dl_cong): validates the double-count hypothesis
User idea: use congestion for the DEADLINE ONLY (inflate finish -> makeable/doomed), NOT proactive
route steering, NOT a score term. Reactive rerouting (env, around real blockers) still happens.
scripts/congestion_policies.py::PartADeadlineCongController (shortest routes, no adherence, no cong
score; _finish_delay = K*route-congestion, K=1.0). 30 seeds, NO disturbances:
  policy            otv_mean otv_med rr_mean rr_max storms
  parta_congestion    201.4   196    61.1    94     0   <- route-steer: most storm-proof
  dl_cong             199.7   198   116.9   789     3   <- deadline-only: ties value, less robust
  parta_head          196.2   198   131.1  1303     3   (= plain; head inert)
  plain_parta         195.1   198   141.6  1286     4
- dl_cong vs champ (value): -1.7, W15/L14/T1 = TIED (medians both 198). dl_cong cuts plain's reroutes
  ~20% (116.9 vs 141.6) and storms (3 vs 4) -> the congestion->deadline mechanism WORKS.
- BUT route-steering is clearly MORE storm-proof (0 storms max 94 vs dl_cong 3 storms max 789). WHY:
  the deadline penalty DETERS taking jammed tasks (task-level avoidance) but doesn't PHYSICALLY SPREAD
  the robots it does dispatch, so it still gridlocks occasionally; route-steering literally moves them
  onto different aisles -> never storms.
- DOUBLE-COUNT HYPOTHESIS CONFIRMED + mechanism: the two congestion uses are ALTERNATIVES, need exactly
  ONE. Route->cong (spread) and deadline->cong (deter) each work alone. Combining (the earlier deadline-
  ETA test) is NEUTRAL because once route-steering picks congestion-AVOIDING routes, route-congestion is
  low -> the deadline penalty has nothing to flag -> INERT. Whichever dodges congestion first neutralizes
  the other. Champion (route-steering) remains best all-rounder (tied value, 0 storms); dl_cong is a
  validated alternative (congestion can drive the deadline instead of the route). Files:
  scripts/verify_dl_cong.py, results/dl_cong_bakeoff.csv.

---
## 2026-07-16  100-SEED disturbance comparison -> settles the parta_head "fluke" question
Ran 100 seeds (disturb_rate=0.1) to cut the variance. Policies: champ_rigid, champ_release,
parta_head, dl_cong (updated = deadline-CONDITIONAL route ranking). ~97/100 (essentially final):
  policy         otv_mean otv_med rr_mean rr_max storms
  champ_rigid      194.5   192    64.4    385     2   <- WINS value + robustness
  champ_release    194.4   192    64.0    385     2
  parta_head       192.2   197   124.3   1311    10
  dl_cong          191.1   193   123.2   1316    10
- parta_head vs champ_release (value): mean -2.3, but W52/L43 head-to-head. NUANCE: parta_head wins
  MORE seeds (52 vs 43) + higher MEDIAN (197 vs 192) -> on a TYPICAL seed it edges the champion (no
  congestion machinery = more value-greedy). BUT it wins small and loses CATASTROPHICALLY: 10 storms
  (max 1311) crater its value -> its MEAN falls below champ (192.2 vs 194.5) and its robustness is 5x
  worse (10 storms vs 2). So parta_head's edge is a HIGH-VARIANCE illusion of the median; champion is
  the better BET (higher expected value + far more robust). NOT a pure fluke, but not actually better.
- dl_cong (updated, deadline-conditional route): WORST -- lowest value (191.1), tied-most storms (10).
  Deadline-conditional routing does NOT hold up under disturbances; explicit route-STEERING is what
  prevents storms. (Confirms: congestion belongs in ROUTING for robustness.)
- champ_rigid ~= champ_release at 100 seeds (194.5 vs 194.4) -> the release tweak's value benefit
  shrank to ~0 at scale (was +1.4 @30), but never hurts (same robustness). Keep it; it's free.
VERDICT: champion (route-steering) is best under disturbances on value AND robustness. 100 seeds
  needed -- 30-seed variance was misleading. File: scripts/verify_100_disturb.py, results/disturb_100.csv.

---
## 2026-07-16  Why dl_cong is the most disturbance-fragile + why a disturbance FEATURE would worsen it
- dl_cong pipes congestion STRAIGHT INTO THE DEADLINE (finish inflation -> makeable/doomed). So anything
  that inflates congestion (disturbances -> robots bunch around blockages) hits the deadline decision
  DIRECTLY. Contrast: the champion uses congestion to STEER (a bad estimate = a slightly worse aisle),
  dl_cong uses it to CLASSIFY (a bad estimate flips a good task to "doomed" -> it gets shed). Direct
  translation into a HARD cut = most noise-exposed policy -> disturbances hurt it most (over-shedding
  doable tasks). And it still doesn't route-avoid, so it STILL storms -> pays the shed cost w/o robustness.
- Would adding DISTURBANCES AS A FEATURE (into the delay/deadline estimate) help? NO -- it would make it
  WORSE. (1) CURRENT disturbances are already counted: find_path treats a disturbed cell as an obstacle,
  so the route already detours -> longer -> later finish. Re-adding them = double-count. (2) FUTURE
  disturbances are UNPREDICTABLE (exogenous random noise). A feature that anticipates them is not signal,
  it's noise -> piping more noise into an already noise-fragile HARD makeable/doomed cut worsens the
  over-shedding. Fully consistent with the throughline: disturbances are OBSERVED & REACTED TO (rumor
  map + reactive find_path reroute), NEVER PREDICTED & fed into decisions.

---
## 2026-07-16  Filters + checklist pruning (user directives)
- HARD ADG execution = drive EXACT committed cells + WAIT (no reroute). Pure wait-no-reroute DEADLOCKS
  (tested) -> only sensible WITH a deconfliction layer that orders the waits (Part D). Soft adherence
  (current) is the sensible middle. #3 done: disturb_drop_adherence now DEFAULT ON in the champion.
- HARD COLLISION FILTER: no-op on this substrate -- the env never CRASHES (reroutes/waits), so there are
  no colliding plans to delete. Only meaningful once we drive EXACT routes (ADG execution).
- DISTURBANCE-MAP FILTER (avoid rumor-map-suspected cells): buildable + the right idea, BUT disturbances
  currently spawn UNIFORMLY AT RANDOM (no spatial pattern) and are temporary -> the rumor map only shows
  where they WERE (expired), not where they'll be. It'd be dodging NOISE. It only pays off if disturbances
  CLUSTER spatially (some zones failure-prone). Proposed: make disturbances clustered -> then the rumor
  filter has a real pattern to exploit. Pending user go.
- CHECKLIST: (a) Analytic formulas CUT -- delay unpredictable (4 ablations), risk = random disturbances
  (unforecastable); (b) Interrupt tier (Part B: rumor-disturbance-probability threshold + battery-floor
  abort) deferred to LATER; (c) battery-floor filter already done, collision filter needs ADG.

---
## 2026-07-16  *** SAVED FOR USER TO REVISIT: ADG / hard-execution explanation (they'll ask again) ***
Hard ADG means: drive your exact committed cells, and when blocked, wait for it to clear -- no reroute
at all. And your instinct is dead-on: pure wait-no-reroute deadlocks (we tested it -- it gridlocked,
worse than everything). So a purely-hard version isn't sensible on its own; it only works with a
deconfliction layer that orders the waits so they can't cycle. That's exactly why I keep flagging Part D
as a prerequisite. Soft adherence (what you have) is the sensible middle: drive your route, reroute only
around real blockers.

---
## 2026-07-16  Zone-clustered (spill/human-flavored) disturbances -- PER-SEED zones (structure to learn)
Added opt-in clustered spawning (env.disturb_clustered): per-seed HOTSPOT zones (3 by default, from the
seeded rng), disturbances spawn Gaussian-near a random zone (sigma 1.5). Zones DIFFER per seed so the
rumor map must re-learn each episode (no cross-seed memorization). Still policy-independent schedule.
Motivation (user): real disturbances aren't uniform -- spills cluster near busy/dock areas, humans
linger in certain corridors -> spatial AUTOCORRELATION, which is what makes the rumor map (and a
routing filter on it) actually useful (uniform-random has none to exploit).
- Concentration ~2x uniform: top-10 cells hold 35-41% of disturbed-steps (vs 19% uniform), ~48-60
  distinct cells (vs 84). Per-seed zones confirmed distinct. Rumor map precision@20 = 20/20 -> it
  captures the structure. Params: disturb_n_zones (3), disturb_zone_sigma (1.5).
- NEXT (the payoff): wire the rumor map into the controller routing (high-belief cells cost more in
  find_path, like congestion) = the DISTURBANCE-MAP FILTER -> "avoid learned hotspots". Now a FAIR test
  (there's a real pattern). = first thing that ACTS on the rumor map.
- Scouts (user Q): meaningful = active sensing to resolve belief uncertainty. Observable disturbances
  -> map is MEMORY, scouts REFRESH stale/unobserved areas; hidden/inferred (struggle) -> map is a GUESS,
  scouts VERIFY. Cost vs info => curiosity taper. Datasets for realistic human/spill behavior: none on
  hand from this session; can research-search if wanted (niche, modest expectations).

---
## 2026-07-16  Deep-research: simulator landscape + demand model (20 sources, 23 verified claims)
GAP CONFIRMED (positioning): no warehouse sim optimizes ON-TIME VALUE under per-task deadlines+values
with disturbances + realistic exogenous demand. Two camps both miss it: physics/perception (Isaac Sim,
scheduling = cuOpt bolt-on) and grid/algorithmic throughput (RWARE, TA-RWARE, MAPF/LMAPF, League of
Robot Runners ICAPS'24, LSMART). Demand = uniform-resample (RWARE) or endogenous 1:1 replace (LoRR).
Even decision-layer RL (RTAW, DC-MRTA, MRTAgent AAMAS'25) uses SOFT delay, no hard deadlines/values.
KEY NEW REFS: (1) WareRover arXiv 2602.13999 (Feb'26) -- holistic order-scheduling+MAPF sim w/ realistic
e-commerce demand (waves/hotspots/bursts); closest competitor but not on-time-value/disturbances/
interpretable-congestion. (2) "Bursty Arrivals, Smooth Sojourns" arXiv 2607.04866 -- EMPIRICAL real-
warehouse data: inter-arrivals heavy-tailed/bursty, incompatible w/ homogeneous Poisson -> grounds
Hawkes over Poisson. (3) LMAPF organizers (2404.16162) admit uniform task sampling is unrealistic.
REFUTED (kept nuanced): Isaac "no decision layer" (cuOpt exists); LoRR "only path planning" (has a
task-assignment track).
RECOMMENDED DEMAND MODEL: NHPP base λ(t)=λ_base·diurnal(t) + Hawkes bursts (α/β≈0.3-0.5) ; SKU/shelf ~
Zipf(s≈1.0-1.2) clustered into hot zones (spatial corr); per-order value~lognormal/tiers, deadline=
arrival+slack. START simple (Dehghan Beta(5,2) volume + normalized-Poisson spatial), ADD Zipf + Hawkes.
Closed-form (thinning + discrete sampling) -> cheap. CAVEATS: WareRover/LSMART are 2026 preprints (stated
design, not benchmarked); NO single turnkey public dataset surfaced (Instacart-2017 / Swiggy-Kaggle
mentioned, unverified fit) -> calibrate, don't dataset-fit. OPEN: how value correlates w/ deadline &
popularity (no source answers -> we choose a sensible joint). Full report: results (task wnsw9bc64.output),
paper related-work updated.

---

## 2026-07-21 — Realistic demand stream built (wwm_sim/demand.py)

WHY: deep-research (2026-07-16) confirmed the toy env uses uniform-resample-on-delivery = always-full
queue, no time structure, uniform popularity. Real arrivals are bursty + popularity-skewed + diurnal.
We had NO real order dataset (the *_example.txt are static task ATTRIBUTES; legs/steps.csv are our own
SIM LOGS -> calibrating on them is circular). So the stream is generated synthetically from the
research-recommended model, calibratable later.

MODEL (DemandModel): non-homogeneous Poisson base lambda(t)=rate*diurnal(t) [diurnal=1+0.5*sin, ~0.5..1.5,
period 250] + Hawkes self-exciting bursts (excite*=0.90 each tick, +0.4 jump w.p. 0.006). Ordered shelf
drawn by ZIPF(s=1.1) popularity, boosted near n_hot=3 spatial hot centers (popular SKUs cluster). Per
order: value~U(1,15), deadline=now+U(60,170). Orders accumulate in request_queue, retired on delivery
(NO resample) -> queue ebbs & flows.

INTEGRATION (warehouse.py): opt-in env.demand_model; step() calls demand_model.step(env,now) each tick;
delivery block gated -> if demand_model set, retire delivered shelf (else old uniform resample). Runner:
after reset, env.request_queue=[]; env.demand_model=DemandModel(env,seed); seed_initial(n=12).

TUNING: first pass (rate 0.09, hawkes_p .008 jump .5) -> Hawkes steady-state (p*jump/(1-decay)=0.05/step)
DOMINATED base -> effective 0.12-0.17/step >> ~0.074/step delivery capacity -> monotonic backlog (queue
only grew). Retuned to rate=0.05, hawkes_p=0.006, jump=0.4, decay=0.90 (steady hawkes ~0.024) -> mean
arrival ~= capacity -> TRUE ebb & flow: queue drains to single digits in diurnal troughs, builds on
bursts. This is the anticipation-relevant regime (vs permanent overload where always work to do).

SMOKE TEST (scripts/demo_demand.py, champion policy, 3 seeds): 42-49 arrivals/500 steps; queue min/mean/max
~4-8/8-13/16-19, frac steps at max ~0.01-0.02 (NOT always-full); peak lambda 0.48 vs base 0.05 (~10x
Hawkes burst), ~119 steps lambda-elevated; popularity top shelf 8-10% vs uniform ~3%; deliveries 30-36,
on-time value 207-281. Queue-depth sparkline shows peak->drain->peak; lambda sparkline shows diurnal sine
+ sharp burst spikes.

NEXT: (a) demand-aware anticipation (position idle robots toward hot zones / near-future arrivals during
lulls -- Part C, now MEANINGFUL since queue ebbs); (b) danger-aware routing (rumor map) under this stream;
(c) re-run champion bakeoff under demand stream (vs uniform) to quantify the regime change.

---

## 2026-07-21 — Congestion map explained; queue layer was DEAD (bug); demand-in-congestion verdict
### + USER CORRECTION: the deadline distribution is unrealistic (nothing is born urgent)

CONGESTION MAP (recap, champion PartACongestionController): float grid cong[y][x], REBUILT FROM SCRATCH
each dispatch (no memory). 3 layers: (1) KNOWN = every busy robot's remaining path, +1.0 (near-certain);
(2) FINISHING = robots within FINISH_HORIZON=40 of target -> guess next task (cheap_screen top-1, `taken`
set prevents two robots onto same task) -> stamp shortest finish->shelf route at +0.5 (half = it's a
guess); (3) FRESH = robots plan in priority order (_order_free_agvs, highest value first) and each commit
is stamped +1.0 BEFORE the next robot plans -> sequential deconfliction for free. 3 consumers: _pick_route
min(len + 0.3*sum cong) over k=3 Yen routes (MAIN LEVER); env.find_path reroute cost +0.3*cong; adherence
off-route 1.5x. Properties: forecast (where robots WILL be) not history heatmap; zero learned params;
SHARP + DIFFERENTIAL -> only changes a decision when competing routes have DIFFERENT congestion sums.

BUG FOUND + FIXED: PartACongestionQueueController (champion + layer 4 = unclaimed pending orders stamp
their shelf->workstation leg, QUEUE_WEIGHT 0.25, rank-decayed, TOP_K 6) was SILENTLY DEAD. results/
bakeoff_demand.csv showed parta_queue BYTE-IDENTICAL to parta_cong on every metric -> traced: 226/226
route lookups returned []. Cause: env.goals stores (x,y) [e.g. (2,34) = x2,y34 bottom-row workstation on
a 35x22 grid], but the layer's comment claimed (y,x) and SWAPPED -> (34,2), x=34 off-grid (W=22) -> not a
node -> empty path -> zero mass. rollout.py:36 unpacks goals UN-swapped, confirming convention. Fixed;
layer now live (cong mass 89.7 -> 98.0, +9%). => that CSV row is a DUPLICATE OF THE CHAMPION, NOT A
RESULT. Re-run needed before any claim about the queue layer.

VERDICT ASKED: fold demand forecast into the congestion map? Split: (a) KNOWN pending orders = legit, not
prediction; the shelf->workstation leg is ROBOT-INDEPENDENT (whoever wins the task walks that leg), same
soundness as layer 2. (b) FORECAST of not-yet-arrived orders = argued NO, on 3 grounds: (1) horizon
mismatch, (2) diffuse mass doesn't change decisions, (3) hot zones are STATIC -> a constant field is
terrain, not a forecast, and perversely penalizes the region holding the valuable shelves.

*** USER CORRECTION (accepted) ***: "Would there not be tasks that arrive that would need to be done
within the next 30 to 60 steps?" -> YES. Reason (1) was TOO STRONG. An order arriving at t+10 with 40
steps of slack must be served inside the window a route committed NOW actually occupies -> the horizons
DO overlap. Reason (1) demotes from a STRUCTURAL objection to a QUANTITATIVE one: the overlap is real but
sits at the tail, and the forecast mass there is discounted by a product of uncertainties -- P(order
arrives in that area) x P(it is urgent) x P(some robot serves that leg inside this window) -- each < 1.
So the residual mass is small AND smeared, which hands the argument back to reason (2) (diffuse mass
doesn't flip an argmin over 3 near-shortest routes to the SAME shelf through the SAME neighbourhood).
NET: reasons (2) and (3) now carry the verdict; (1) is a weak supporting point, not a proof.

*** MODEL DEFECT EXPOSED (the real prize of that question) ***: DemandModel sets deadline = now +
U(60,170). Typical task duration is ~30-60 steps, so MINIMUM SLACK EXCEEDS TYPICAL SERVICE TIME =>
EVERY order is comfortably makeable the moment it lands. NOTHING IS EVER BORN URGENT. Consequences:
(i) unrealistic -- real fulfilment has rush/expedited tiers, cutoff times, SLAs already tight on arrival;
(ii) it DEFANGS the makeable/doomed hard tier, which currently only ever fires because of QUEUEING DELAY,
never because of genuine intrinsic urgency -- so the deadline machinery is being tested on an easy case;
(iii) it biases every deadline-vs-route experiment we have run under the demand stream.

IMPLIED FIX (pending, not yet built): make slack a MIXTURE, not uniform -- e.g. ~20% RUSH with slack
~U(25,60) (a real chance of being tight or even doomed at arrival) + ~80% STANDARD ~U(80,200). Likely
also correlate VALUE with URGENCY (rush orders worth more), which finally CLOSES THE OPEN QUESTION the
2026-07-16 deep research explicitly left unanswered ("how value correlates w/ deadline & popularity -- no
source answers -> we choose a sensible joint"). NOTE: a rush tier also re-opens (b) somewhat -- forecast
urgent arrivals are horizon-compatible by construction -- but reason (2) still applies unless the
forecast mass is spatially SHARP.

---

## 2026-07-21 (b) — Rush tier added; queue-layer ranking redesigned (USER'S DESIGN); demand
## forecast hits a HARD ESTIMABILITY WALL

RUSH TIER BUILT (wwm_sim/demand.py): deadline/value are now a MIXTURE, not uniform. rush_frac=0.20,
rush slack ~U(25,60), std slack ~U(80,200), rush value x1.6 (rush_value_mult). Draw counts are
branch-independent so the arrival stream stays policy-independent (paired comparison preserved).
shelf.is_rush set per order. VERIFIED (seed 3, 400 steps): rush_frac observed 0.15, rush slack median
48 vs std 138, 15% of orders have slack < 60 against a ~30-60 step service time -> orders are now
genuinely TIGHT AT ARRIVAL. This closes the value/urgency joint the 2026-07-16 research left OPEN, and
un-defangs the makeable/doomed tier (previously it only ever fired via queueing delay).

QUEUE-LAYER RANKING REDESIGNED (user's design, supersedes my imminence-only idea):
  - I had proposed weighting the queue layer by IMMINENCE (exp(-slack/tau)). USER CORRECTED: rank
    pending orders "the same way you would rank other tasks for choosing, based on both deadline AND
    value". CORRECT, and my version was wrong: the funnel's hard tier means MAKEABLE orders all clear
    the bar and then VALUE decides among them. Imminence-only would stamp a tight LOW-value order above
    a high-value makeable one the planner would actually take first.
  - PartACongestionRankQueueController: weight = the funnel's OWN criterion. Robot-independent service
    estimate est = PACE(1.35) * (nearest-AGV->shelf + shelf->nearest station); makeable (est<=slack) ->
    MAKEABLE_BONUS(1000)+v, else v*DECAY_G(0.98)^(est-slack). Top-8, rank-decayed, stamps the cached
    STATIC haul leg. Self-consistent: the forecast now predicts what the planner will actually do.
  - Kept PartACongestionUrgentQueueController as the ABLATION (imminence-only) to test whether the
    ranking criterion actually matters.

*** DEMAND FORECAST: HARD NEGATIVE (sample-size wall, found BEFORE spending bakeoff compute) ***
User's idea: for not-yet-arrived orders, estimate from "which shelves have been served before" and stamp
estimated LEGS (not regions). Built it as an ONLINE observer (diff request_queue each dispatch; a shelf
newly appearing = an arrival) -- same "observe don't predict" idiom as the rumor map, so it adapts
instead of being static terrain. MEASURED (seed 3, full 500 steps): 49 arrivals across 49 DISTINCT
shelves out of 240. EVERY per-shelf count is EXACTLY 1. frac(count==1) = 1.00. There is NO frequency
signal to estimate. Pooling to blocks barely helps: 6x6 blocks -> max 5 vs median 2 over 20 blocks
(~1.6 sigma on Poisson noise), and that estimate only exists by the END of the episode -- far too late
to act on.
STRUCTURAL CAUSE (not just small n): one shelf = one order, so a popular shelf SITTING IN THE QUEUE
CANNOT generate another arrival until delivered. Popularity makes a shelf wait longer, which SUPPRESSES
the very repeat-rate signal we would need. The mechanism is self-censoring.
=> The idea is sound in principle; this warehouse simply does not emit enough data in 500 steps.
Would need much longer episodes (2000+), or a demand model where an order names an SKU that can repeat
independently of shelf occupancy. Tested anyway (parta_fcast) to confirm it is noise, not assumed.

---

## 2026-07-21 (c) — USER'S P(arrive) x P(taken) forecast design; velocity slotting; the SELF-CENSORING
## ceiling; queue-layer bakeoff = NOISE

USER'S DESIGN (correct, and better than what I had): for FUTURE orders the forecast weight should be a
PRODUCT of (a) P(an order arrives in that area within the task window) and (b) P(it is then SNAPPED UP
| value, deadline) -- "if unlikely it changes by little but if super likely to come in and THEN be
taken". WHY THIS IS THE RIGHT STRUCTURE: the quantity a congestion cell wants is EXPECTED TRAVERSALS =
P(arrive) x P(assigned soon) x leg. Multiplying two sub-1 factors is a SHARPENING operator -- it crushes
the diffuse background to ~0 and leaves mass only where BOTH are high, which is precisely the fix for
the "diffuse mass cancels in the argmin" objection (reason 2). It FILTERS rather than ADDS. Factor (b)
is already computable from the makeable/doomed rank built for PartACongestionRankQueueController, and in
an overloaded queue most orders are NOT taken quickly, so (b) genuinely discriminates.

MY OWN DEMAND MODEL WAS FLAWED (self-critique, found while trying to build (a)): popularity was
Zipf(1/rank^1.1) over a RANDOM PERMUTATION times a spatial boost (1+2.5*exp(-d/4)). Zipf spans ~400x
top-to-bottom; the spatial term spans <=3.5x. So the DOMINANT variation was spatially WHITE NOISE and
the "hot zones" were nearly COSMETIC -- "which area is hot" had almost no signal even with infinite
data. FIXED: added slotting="velocity" (default) -- Zipf RANK assigned by proximity to hot centres
(+jitter 6.0), mirroring real VELOCITY-BASED SLOTTING (fast movers stored near dispatch). slotting=
"random" preserves the legacy behaviour.

*** THE SELF-CENSORING CEILING (hard negative, quantified) ***: velocity slotting BARELY HELPED --
top-3-block concentration went 1.94x -> 2.11x only. Diagnosed on seed 0: INTENDED top-20 shelves hold
0.66 of demand mass; REALIZED only 0.34 of arrivals landed on them; CAUSE = on average 13.1 OF THE 20
HOT SHELVES ARE ALREADY PENDING (hence un-orderable) at any moment, so demand SPILLS OVER to cold
shelves. Max per-shelf count is still 1 (53 arrivals, 53 distinct shelves).
THE PERVERSE PART: the MORE concentrated the intended popularity, the HARDER it self-censors, because
concentration keeps the hot shelves permanently occupied. The realized distribution is dragged toward
UNIFORM no matter how skewed the intended one is. This is a CEILING, not a tuning issue -- it cannot be
fixed by reweighting.
ROOT CAUSE = REPRESENTATION: env.request_queue is a SET OF SHELVES (one pending order per shelf), so an
order is identified WITH its shelf. REAL FIX (deferred): make request_queue a list of ORDER OBJECTS each
NAMING a shelf/SKU, allowing multiple concurrent orders for one shelf. Worth doing for FIDELITY (real
fulfilment has many concurrent orders per SKU) and for Part C anticipation -- NOT to rescue this
congestion layer.

BAKEOFF (demand stream + rush tier, run under slotting="random"; 13 seeds at time of writing):
  parta_queue 254.0 | parta_fcast 253.2 | parta_cong 252.0 | parta_urgent 249.5 | parta_rank 248.7
Spread 5.3 pts against per-seed swings of +/-45 => ALL INSIDE NOISE. No queue-layer variant beats the
champion; the deadline+value rank (the principled one) sits at the BOTTOM, though not significantly.
=> CONSISTENT WITH REASON 2: stamping pending/forecast legs does not move an argmin over near-shortest
routes. TWO INDEPENDENT REASONS TO STOP this direction: the layer does not change decisions, AND its
input signal is structurally suppressed. Demand belongs in Part C POSITIONING (a different decision with
a matching horizon), not in the congestion map.

---

## 2026-07-21 (d) — ORDER OBJECTS + BATCHING: the self-censoring ceiling is BROKEN

BAKEOFF UNDER OLD (shelf==order) REPRESENTATION, 30 seeds, FINAL: parta_rank 259.0 | parta_fcast 258.4 |
parta_cong 257.7 | parta_urgent 256.2 | parta_queue 256.1. Spread 2.9 pts, head-to-heads ~15-15
(rank 17W-13L, queue 16W-14L, urgent 14W-16L, fcast 16W-13L-1T). DEFINITIVELY TIED => the congestion-
forecast direction is a confirmed dead end under that representation, exactly as reason 2 predicted.

SIM MECHANICS ANSWERED (user asked: can multiple robots use one shelf at once?): NO. _execute_load
requires the AGV and a PICKER on the SAME CELL as the shelf, and on load the shelf is ERASED from the
SHELVES grid layer and moves onto the robot -- it is off the floor entirely until _execute_unload sets
it back down on an empty non-highway cell. So a shelf is touched by exactly ONE AGV + ONE PICKER, and
multi-stop routes are impossible (an AGV carries one shelf at a time). BATCHING therefore needs NO
grouping logic and NO robot changes: same shelf == same route, automatically.

ORDER OBJECTS BUILT (wwm_sim/demand.py): new Order(shelf, value, deadline, is_rush, t_arrive).
DemandModel.pending = {shelf id -> [Order]}; MANY orders may name one shelf (the SKU idea). _inject no
longer excludes already-queued shelves (only CARRIED ones -- off the floor mid-trip). _refresh() derives
the shelf's task attributes from its pending orders: value = SUM (batching: one trip serves them all,
so a 4-order shelf really is worth 4x), deadline = EARLIEST (the trip must satisfy the tightest),
is_rush = any, n_orders = count; and syncs env.request_queue (still a list of DISTINCT shelves, so ALL
existing policy code works UNCHANGED and exploits batching automatically). fulfill() clears every order
on the shelf in one trip. warehouse.py: delivery calls demand_model.fulfill and appends to
env.fulfilled_this_step; bakeoff now scores PER ORDER (own deadline, own value).

*** RESULT: SELF-CENSORING GONE (seed 0, 500 steps) ***
  INTENDED top-20 demand share 0.66 -> REALIZED 0.68  (was 0.34 under shelf==order)
  max orders fulfilled from ONE shelf over the episode: 13 (was 1)
  batch size per trip: {1:20, 2:2, 3:2, 7:1}  -- one trip cleared SEVEN orders
  53 arrivals, 37 fulfilled, 14 shelves still pending at end (loaded regime retained)
Realized concentration now MATCHES intended => "orders are spatially random" is NO LONGER TRUE.

WHY THIS MATTERS MORE THAN FORECASTING (the key reframing): a shelf carrying 7 stacked orders is a
PRESENT, OBSERVABLE FACT sitting in the queue -- worth 7x a normal shelf, so it WILL be fetched soon and
its leg WILL be walked. Same certain-knowledge character as forecast layer 1; NO prediction involved.
The order-objects change converts an unforecastable FUTURE quantity into an observable PRESENT one --
the project's "observe / compute, don't predict" principle applying yet again. It also explains why the
old bakeoff was tied: under shelf==order EVERY shelf looked identical (exactly one order), so the queue
layer had literally nothing to discriminate on.

USER ASKED: "specific cells of congestion instead of legs?" ANSWER: shape is not the blocker. (1)
REDUNDANCY -- the cells that actually choke are the workstation approaches, and if they will be jammed
within the route horizon it is because robots are ALREADY en route, which layer 1 knows with CERTAINTY
at full weight; a probabilistic forecast on top of a certain measurement is strictly dominated. (2)
HORIZON -- the only congestion a demand forecast adds beyond layer 1 is 60+ steps out, and routes last
30-60 steps. Both arguments are shape-independent, so points do not beat lines.

RE-RUN LAUNCHED under the new representation (results/bakeoff_orders.out): the old "all tied" verdict
was measured in a world where every shelf was identical, so it does not settle whether the queue layer
helps now that shelves genuinely differ.

---

## 2026-07-21 (e) — PARTIAL-CREDIT BATCH SCORING: the first SIGNIFICANT win of the day

THE BUG (user found it by reasoning, not by running anything): with order batching, _refresh sets
shelf.deadline = MIN of its orders' deadlines and shelf.value = SUM. So the funnel scored a batch
ALL-OR-NOTHING -- the instant ONE order in a stack became unreachable, the WHOLE shelf was scored doomed
(v*g^lateness) and deprioritised, abandoning the other four orders that were perfectly makeable. The
METRIC already scored per order; the PLANNER did not. Planner and metric were optimising different
things, biased toward abandoning valuable batches. Smoke test: 100% of multi-order shelf observations
have MIXED deadlines, so this misfired constantly.

THE FIX (_PartialCreditMixin._deadline_score): at the projected finish T, on_time = sum of values of
orders with deadline >= T; salvage = sum of the rest decayed by g^(T - deadline_o). Score = 1000 +
on_time + salvage if on_time > 0 else salvage. Preserves the hard TIER where it matters (delivering
SOME value on time outranks delivering none -- "sharp beats soft") while giving partial credit within
it. ZERO prediction: every order and deadline already exists.

BAKEOFF (30 seeds, demand stream + rush tier + batching), paired vs parta_cong:
  parta_rank_p  283.3  diff +26.3  t=4.07  23W-7L   SIGNIFICANT
  parta_unified 282.2  diff +25.2  t=3.24  25W-5L   SIGNIFICANT
  parta_partial 272.6  diff +15.6  t=3.27  21W-5L   SIGNIFICANT
  parta_cong    256.9  (control)
INCREMENTS (this is the real story):
  rank_p  vs partial  +10.7  t=1.56  18W-12L  NOT sig
  unified vs partial   +9.6  t=1.11  18W-12L  NOT sig
  unified vs rank_p    -1.1  t=-0.25 11W-17L  NOT sig  <-- FUTURE-ORDER LEGS ADD NOTHING
=> The CONFIRMED, SIGNIFICANT win is PARTIAL CREDIT (+15.6, t=3.27) -- the ONLY change today that
touched TASK SELECTION rather than routing. The queue/routing layers STILL cannot demonstrate an effect
on top of it, and the future-order (forecast) half is a clean NULL. Fully consistent with the day's
pattern: routing tiebreakers do not move an argmin over near-shortest routes; scoring the right
objective does.

METHOD NOTE (self-correction): I twice called a result from partial seed data and was wrong both times
(claimed "champion now last, real separation" at 13 seeds; the gap then shrank toward zero as n grew).
Shrinking-with-n is the signature of noise. RULE ADOPTED: no result claim without a PAIRED t-test on the
completed run. All numbers above are paired, n=30, t-threshold 2.045.

OPEN (bakeoff running, results/bakeoff_exact.out): user's point that KNOWN queued tasks deserve EXACT
ROUTES, not bare haul legs. Built PartAExactRoutePartialController: predicts WHICH robot (best-positioned
of those idle-or-finishing-within-FINISH_HORIZON, each consumed once), then stamps BOTH the fetch leg
(robot->shelf) and haul leg (shelf->station), each chosen from Yen k-routes by the congestion-aware
_pick_route -- i.e. the route the funnel would ACTUALLY pick, made in rank order against the map built
so far (layer 3's prioritised logic pushed one step further out). Plus PartAPropPartialController as the
CONTROL that separates the bundled weighting change (positional 1-i/n vs proportional eff/eff_top;
positional gives a DOOMED task at position 2 ~87% weight, proportional gives it ~0).

---

## 2026-07-21 (f) — Layer 2 EDITED IN PLACE (fetch+haul); future-arrival layer built; run in flight

USER'S ARCHITECTURAL CORRECTION (accepted, and it is the right call): do NOT bolt a second predictor on
top of layer 2 -- EDIT layer 2. Layer 2 always had the correct IDEA (robots freeing up within ~a task
duration -> cheap-screen their most likely next task -> stamp the route); its only flaw was stamping
HALF the journey (fetch leg, finish->shelf) and never the shelf->station haul. The alternatives each got
one half: champion = fetch only; rank/queue layers = haul only with NO robot behind them. Stacking a
second layer (parta_exact) DOUBLE-BOOKS ROBOTS -- layer 2 predicts robot R does task X while the new
layer predicts R does task Y -> a phantom leg on the map. Editing layer 2 makes that impossible by
construction.
=> PartAFullLegController: layer 2 unchanged in every respect (robot-anchored, cheap_screen top-1, one
prediction per freeing robot, `taken` set) EXCEPT it now stamps FETCH **and** HAUL at FUTURE_WEIGHT.
Haul legs cached (static: shelves and stations never move).

BAKEOFF IN FLIGHT (results/bakeoff_fullleg.out, 30 seeds). All four share the Part A funnel, PARTIAL-
CREDIT scoring, and layers 1+3; they differ ONLY in how pending orders reach the map:
  parta_partial    fetch only (layer 2 as originally written)          -- CONTROL
  parta_fullleg    fetch + haul, ONE integrated layer (user's design)
  parta_exact_only layer 2 replaced by task-anchored top-6 by funnel rank, robot paired, fetch + haul,
                   congestion-aware Yen routes
  parta_rank_p     fetch (layer 2) + haul (separate layer 4) -- TWO DISCONNECTED layers, different task
                   sets
ISOLATES: fullleg vs partial = does the haul leg help; fullleg vs rank_p = integrated vs disconnected;
exact_only vs fullleg = task-anchored+funnel-rank vs robot-anchored+cheap-screen.

FUTURE-ARRIVAL LAYER BUILT (_FutureArrivalMixin, composable so the question is asked IDENTICALLY of
every architecture rather than confounded with one). Robot-anchored, full cycle, per user's spec: for
each robot that will free up (idle, or finishing within FINISH_HORIZON, taken at its STOPPING POINT),
rank observed-hot shelves not currently queued by (order frequency / max) / (1 + 0.04*distance) -- the
distance discount matters, without it every robot stamps the same globally-hot shelf and the mass piles
onto one corridor; with it each robot ranks ITS OWN likely next job. Top-3 per robot, stamp stopping
point -> shelf (fetch) AND shelf -> station (haul), weight 0.20 * likelihood * rank decay (below
QUEUE_WEIGHT 0.25 and layer-2's 0.5 -- these orders do not exist yet). PURELY OBSERVATIONAL: reads no
demand-model internals (lambda, popularity weights, hot-zone centres, Hawkes state all stay hidden);
counts arrivals only by diffing the request queue.
Variants ready: PartAPartialFuture / PartAFullLegFuture / PartAExactOnlyFuture / PartARankPFuture.
PLAN: round two = same four policies + the mixin, same seeds -> each X_future pairs directly against its
X counterpart, isolating "does future-arrival prediction help" per architecture.
PRIOR ON RECORD: expect NULL again -- parta_unified tested -1.1 (t=-0.25) under already-favourable
conditions (order objects had restored concentration to 0.68). Robot-anchoring + full-cycle stamping are
genuine improvements over that attempt so it deserves the run, but the day's pattern is that predicting
OUR OWN DISPATCHER works and predicting THE WORLD does not.

STATE OF PLAY (end of day): the ONE significant, confirmed win is PARTIAL-CREDIT BATCH SCORING
(+15.6, t=3.27, 21W-5L) plus the ORDER-OBJECTS/BATCHING representation fix that made it possible
(realized demand concentration 0.34 -> 0.68; one trip clears up to 7 orders). Both came from the user's
reasoning, not from a search. Every routing-layer variant remains unproven.

---

## 2026-07-18b — Layer-2 audit, queue-layer bug, demand retune

TRIGGER: user asked whether congestion layer 2 ("predict next task for robots about to free up") really
runs, since it is integral. Audit found it RUNS but is mis-specified, plus a sibling layer was dead.

BUG 1 (queue layer, FIXED): PartACongestionQueueController stamped shelf->workstation legs of unclaimed
pending orders. 226/226 route lookups returned []. Cause: it did `[(gx,gy) for (gy,gx) in env.goals]`
claiming goals are (y,x). They are (x,y) -- e.g. (2,34) on a 35x22 grid; the swap gave x=34 >= W=22,
off-graph. rollout.py:36 unpacks goals as (gx,gy) un-swapped, confirming. results/bakeoff_demand.csv's
parta_queue column was therefore a DUPLICATE of parta_cong, not a result. Fixed -> layer now adds ~9%
map mass. NOTE: whole-grid AGV graph means any in-bounds pair is reachable, so [] always means off-grid.

LAYER 2 AUDIT (champion): route lookups 1677, EMPTY 0 -> mechanically healthy, 33.4% of total map mass,
27 distinct shelves predicted. But three defects:
  (a) FINISH_HORIZON=40 is INERT: remaining path len mean 11.2, p95 27, max 41, only 0.1% exceed 40.
      So "FINISHING" = every busy robot. The gate never excluded anyone.
  (b) WRONG ANCHOR: path[-1] is the robot's OWN SHELF for 36.9% of busy AGVs (fetching; 100% of them).
      Those are not finishing -- the haul is still ahead -- so the next-task route was drawn from a cell
      they merely pass through. Carrying AGVs: path[-1] is a workstation only 49.4% of the time.
  (c) len(path) UNDERESTIMATES time-to-free ~2.5x. Ground truth (2315 obs): actual time-to-free mean
      27.1, p50 22, max 125.

ESTIMATOR BAKEOFF vs ground truth: A len(path) MAE 15.23 r .453 | B len(path)+load+dock(path_end) MAE
13.81 r .500 (BEST) | C phase-aware (carry?len:len+load+dock) MAE 15.21 r .306 (WORSE -- carrying robots
are not free at path end either). Time-to-free is NOISY (MAE ~14 on mean 27) -> a literal 1-2 step tag
would select on noise. And the map has NO time dimension, so the ANCHOR matters more than the threshold.

FIX BUILT (PartACongestionFreeL2Controller): t_free = est B; skip if t_free >= FREE_HORIZON(30); anchor
the next-task prediction at the NEAREST DOCK to path end (where the robot actually frees up); stamp
weight = FUTURE_WEIGHT*(1 - t_free/FREE_HORIZON) so confidence and weight track together (decay rather
than hard gate, because the estimator is noisy). Behaviour: tags 2.42 robots/round (was ~5.6 = all busy),
layer-2 mass share 33% -> 16%, total map mass 100.8 -> 75.3.

DEMAND RETUNE (my earlier tuning was WRONG): I set rate=0.05 by optimising queue-depth ebb and never
checked SELECTION LEVERAGE. At that rate a freed robot had only 1.8 unclaimed candidates (the Part A
funnel is a selection machine -> nothing to select), idle AGVs 1.09/8, and layer 2 found NO candidate
47.6% of the time. Queue depth IS selection leverage, so "drains to empty" and "many candidates" pull
opposite ways. Fix: base rate 0.075 (~= delivery capacity) + WIDE diurnal amp 0.8 (0.2x..1.8x, was 0.5).
Result: queue 16.1 (9-24), unclaimed 11.4, idle 0.28/8, layer-2 no-candidate 47.6% -> 9.1%. Caveat:
backlog LAGS demand (peak unclaimed 10.0 vs trough 13.0) -- normal queueing lag, so the trough is a
catch-up period, not a quiet one.

FETCH vs HAUL (asked): route ranking (_pick_route, congestion lambda, Yen k=3) is FETCH-leg only
(sim_priority.py:392 routes agv->shelf); task SCORING is BOTH legs (sim_priority.py:518 finish =
rendezvous + LOAD_TIME + nearest_dock_dist); cheap_screen is fetch-only. The haul is replanned by
find_path (which does read congestion_grid) but is never Yen-ranked among alternatives.

## 2026-07-18c — Layer-2 rebuild is a NULL result (30 seeds, demand stream)

bakeoff_demand, 30 paired seeds, demand stream (rate .075 amp .8), on-time VALUE:
  rush 279.5 | parta 305.9 | parta_cong 311.6 | parta_freel2 311.7
Paired: freel2 vs cong +0.15 SE 4.31 t=+0.04 wins 13/30  <- DEAD FLAT
        cong vs parta  +5.63 SE 6.36 t=+0.89 wins 20/30  <- congestion edge much WEAKER than under
                                                             uniform demand (was the clear champion)
        parta vs rush +26.40 SE 12.30 t=+2.15 wins 22/30
Per-seed otv std 54.3 (211-412) -> a real effect must clear ~+9 to be visible at 30 seeds.

INTERPRETATION: the layer-2 rebuild fixed VERIFIED defects (anchor wrong for 37% of robots, inert gate,
2.5x underestimate of time-to-free) and changed the map materially (mass 100.8->75.3, tagged 2.42 vs
5.59/round) yet moved the outcome by nothing. Hypothesis: layer 2 is MASS WITHOUT LEVERAGE -- anchored
at shelf or dock, it is a soft 0.5 stamp on cells that the k=3 near-shortest routes to the SAME shelf
largely share, so it rarely flips the argmin. Same "diffuse mass does not change decisions" principle
used to argue against a demand-prior layer, now applying to a layer we assumed load-bearing.
NEXT: ablation (FUTURE_WEIGHT=0, scripts/ablate_l2.py) -- if removing layer 2 entirely is ALSO null,
layer 2 is decoration and the champion's edge is layers 1+3 (known paths + fresh prioritized commits).

HAUL RANKING (asked): the pickup moment ALREADY re-ranks all 10 docks (sim_dashboard.py:164-170) but by
`argmin len(path)` -- RAW LENGTH, congestion-blind -- while discarding the congestion-weighted cost the
same find_path call computed. Meanwhile the haul ROUTE is already congestion-optimised over the WHOLE
graph (find_path adds w*cong), i.e. a wider search than the fetch leg's k=3 Yen. So copying Yen-ranking
onto haul routes would NARROW the search and add little. The real gaps: (a) dock CHOICE ignores
congestion (discrete, 10-way, sharp -> good congestion-map target); (b) the known shelf->dock leg of
in-progress FETCHES is never stamped into the forecast (robot-independent + near-certain, stronger than
layer 2's guess since the shelf is already known). NOT YET BUILT - awaiting go.

## 2026-07-18d — Layer 2 is NOT integral (120-seed ablation). Retraction.

120 paired seeds, demand stream, on-time VALUE:
  cong_l2on 320.2 | cong_l2off 319.0 | diff -1.17 SE 3.43 t=-0.34 wins 58/120 (48.3% = coin flip)
  95% CI on the layer-2 effect: [-7.9, +5.6] otv = [-2.5%, +1.7%] of the mean.

At 30 seeds the ablation read -5.16 (t=-1.07) and I wrote that layer 2 might be carrying the WHOLE
congestion edge (since -5.16 ~ the +5.63 cong-vs-parta gap). At 4x power the effect SHRANK to -1.17 and
t fell to -0.34. RETRACTED: that reading was an artefact of 30-seed noise. Layer 2 -- the "future-aware"
part of the world model, the piece we assumed was load-bearing -- contributes nothing measurable.

Consistent picture across three tests, all null:
  - rebuild layer 2 with a CORRECT anchor (freel2): +0.15, t=+0.04  -> correctness does not matter
  - DELETE layer 2 entirely:                        -1.17, t=-0.34  -> presence does not matter either
  - (earlier) queue layer, once unbugged:            untested at power
So layer 2 is neither predictor nor regulariser: it is inert. The forecast's decisions are made by
layer 1 (known remaining paths) + layer 3 (fresh prioritized commits), both CERTAIN and sharp.

This is the 6th negative result for SOFT/UNCERTAIN mass changing route decisions (learned delay head,
variance head, congestion-finish, soft P(on-time), congestion-deadline-ETA, now layer 2). The pattern
holds without exception: only SHARP, CERTAIN, DIFFERENTIAL signal moves an argmin over k near-shortest
routes. Predicted/soft mass gets shared by the competing routes and cancels.

OPEN + RUNNING: cong_l2on vs parta at 120 seeds. At 30 seeds the congestion forecast beat plain Part A
by only +5.63 (t=0.89, NOT significant). Given how the layer-2 effect evaporated under power, the
CHAMPION'S ENTIRE EDGE under the demand stream is now in question. If that too is null, the congestion
map does not pay in this regime (it DID under uniform always-full demand, 62-seed 199.8) and the honest
conclusion is that the regime, not the map, was doing the work.

## 2026-07-18e — The congestion MAP itself is null under the demand stream (120 seeds)

cong_l2on vs parta (map vs NO map at all), 120 paired seeds, demand stream, on-time VALUE:
  cong_l2on 320.2 | parta 318.8 | map effect +1.36 SE 3.31 t=+0.41 wins 51/120
  95% CI on the map: [-5.1, +7.8] otv = [-1.6%, +2.5%]. Bounded, and centred on zero.

DECOMPOSITION of the +32 gap over rush (why parta_cong "beat rush so hard"):
  rush 279.5 -> parta 305.9   = +26.4  t=2.15  SIGNIFICANT   <- the FUNNEL (82% of the gap)
  parta -> parta_cong          = +5.6 @30 seeds, +1.4 @120   t=0.41  NULL  <- the MAP
  layer 2 inside the map       = -1.17 @120                  t=0.34  NULL
So the win over rush was ALWAYS the Part A funnel (deadline-aware makeable/doomed task selection,
value x deadline scoring, rollout feasibility, prioritized dispatch) -- never the congestion forecast.
Layer 2's null was a sub-null of a component that does nothing here. I had been calling parta_cong "the
champion" in a way that implied the MAP earned it; it did not.

PRINCIPLE (7th confirmation): SHARP + CERTAIN signal on TASK SELECTION wins big (the hard deadline
tier). SOFT + PREDICTED signal on ROUTE SELECTION does nothing (delay head, variance head,
congestion-finish, soft P(on-time), congestion-deadline-ETA, layer 2, now the whole map).

POWER WARNING (systemic): per-seed otv std ~54, paired SE ~3.3-4.3 at n=120. Anything under ~+8 needs
120+ seeds. Several past claims were made at 30-62 seeds at effect sizes of 2-6 -- e.g. the 100-seed
disturbance result had champion 194.6 vs parta_head 192.7 (~2 pts = well inside noise). Those claims
are NOT established. RUNNING: cong_l2on vs parta under the LEGACY UNIFORM always-full regime at 120
seeds -- decides whether the map ever worked, or whether the original 62-seed champion margin was noise.
(Uniform smoke test reproduces the historical ~200 otv range, so the regime is faithfully restored.)

ALSO RUNNING: cong_dock (option A, congestion-aware dock choice) vs cong_l2on, 120 seeds. At n=32 it
read +5.47 t=1.30 -- the same size as effects that evaporated twice today, so NOT called yet.

## 2026-07-18f — CORRECTION: the map's value is REGIME-DEPENDENT (user was right)

I claimed from demand-stream data that "the funnel beat rush, the map never mattered". WRONG as a
general claim. Checked the notes (2026-07-1x uniform 30-seed bakeoff): rush 197.9 | parta 195.1 |
parta_congestion 201.4 -> under UNIFORM, Part A ALONE LOSES TO RUSH and only the congestion map pulls
it ahead. Exactly what the user remembered. The demand stream INVERTS this:
  UNIFORM: rush 197.9 | parta 195.1 (loses) | cong 201.4   -> the MAP does the work
  DEMAND : rush 279.5 | parta 305.9 (wins)  | cong 311.6   -> the FUNNEL does the work
My decomposition was demand-stream-specific and I stated it as general. Corrected.

RE-RUN (uniform, 120 seeds, in progress) at n=39: cong 200.9 vs parta 190.0, map effect +10.87 SE 4.61
t=+2.36 wins 25/39 -> the map IS real under uniform, and reproduces the historical margin. Compare
demand stream 120 seeds: +1.36 t=0.41 CI [-5.1,+7.8]. So the map is worth ~+7..11 under uniform and
~0 under the demand stream.

MECHANISM (already in the old notes, I had forgotten): the map's edge is NOT typical-seed gain -- the
median was ~tied -- it is ELIMINATING REROUTE STORMS (parta 4 storms/max 1286 rr; parta_cong 0/max 94).
So a MEAN t-test is the wrong instrument for it: a benefit concentrated in ~13% of seeds is diluted by
the mean, and the storms themselves inflate the SE that makes the t-test say "null". My demand-stream
"CI [-5.1,+7.8] therefore bounded null" conclusion was over-stated for that reason.
storm_check (demand, interim): storms DO still occur -- seed 6 parta rr=428 otv=235 vs cong rr=67
otv=245. So the mechanism is live; but the OTV COST of a storm is smaller under demand (thinner queue
= less work in flight to lose), which plausibly explains why the map's mean edge shrinks to ~0 there.

OPTION A (congestion-aware dock choice) — NULL under demand: 120 seeds, -1.23 SE 2.71 t=-0.45, wins
60/120, CI [-6.5,+4.1]. Evaporation curve n=32 +5.47 -> n=97 +1.57 -> n=120 -1.23 (3rd time today a
~+5 effect at n~30 regressed to zero). BUT that test is UNINFORMATIVE: it measured a map refinement in
the regime where the whole map is worth 0. Re-running A under UNIFORM (in progress).
METHOD RULE going forward: test map/forecast changes in the UNIFORM regime (where the map has a
measurable effect) and report TAIL statistics (storms, worst-decile), not just mean + t-test.

OPEN (proposed, not built): user argues future ROUTES are predictable because the policy is
deterministic -- simulate robot B's own decision under predicted conditions (a policy rollout, i.e.
extending layer 3 forward in TIME rather than guessing like layer 2). Valid: layer 2 was never a
simulation, just cheap_screen top-1 from a wrong anchor, so its null does not refute this. Obstacle is
not the policy but the STATE at the future decision point (measured time-to-free MAE 14 on mean 27;
argmax over a queue that turns over; timing errors flip collision resolutions). PROPOSED FIRST TEST:
ORACLE stamping -- record what robots ACTUALLY did next, stamp that true future into the map, two-pass.
If perfect foresight is also null, prediction quality was never the lever and the idea closes cheaply;
if it wins, we know the size of the prize before building a rollout.

## 2026-07-18g — Option A (dock choice) is a WIN under uniform; oracle test launched

ablate_dock_uniform, 120 paired seeds, UNIFORM regime, on-time value:
  cong_l2on 198.9 | cong_dock 204.2 | +5.32 SE 2.19 t=+2.43 CI [+1.0,+9.6] wins 67/117 (57.3%)
  Distribution shifts uniformly: p10 178->182, median 200->204, p90 223->225 (not tail-driven).
  Sign test z=+1.57 p=0.116 -> effect is MAGNITUDE-driven, unlike the map (sign-driven). 
TRAJECTORY: n=20 -6.35 (t-2.26) -> n=40 -3.67 -> n=80 +2.16 -> n=120 +5.32 (t+2.43). FULL SIGN FLIP.
  I reported "trending harmful" at n=20 AND invented a mechanism (longer haul -> missed deadline ->
  deadline tier dominates). Pure noise-fitting, after warning about this exact trap twice in-session.
  RULE ADDED: never narrate a mechanism for an unresolved effect; the story makes noise feel like signal.
Under DEMAND the same change was -1.23 (t=-0.45) -- uninformative, since the map is worth ~0 there.
So dock choice joins the map as REGIME-DEPENDENT: real under uniform, absent under the demand stream.

FINAL map numbers (120 seeds each): UNIFORM +3.44 SE 2.80 t=1.23 wins 57.6% | DEMAND +1.38 SE 3.31
t=0.42 wins 57.6% | POOLED 236 paired seeds 57.6% wins, sign-test z=+2.34 p=0.019. The map is SMALL,
REAL and regime-robust in FREQUENCY; the t-test was the wrong instrument (storms inflate the SE that
the t-test divides by; the sign test ignores outlier magnitude). Historical published +6.3 (30 seeds)
is really +3.44 at 120 -> winner's curse, ~2x inflation.

LAUNCHED: scripts/oracle_test.py (120 seeds, UNIFORM). Pass 1 PartACongestionRecordController logs every
commit (timestep, agv_id, route); pass 2 PartACongestionOracleController replaces layer 2's GUESS with
the recorded TRUE next route per robot. Upper-bounds what any predictor (incl. the user's policy-rollout
idea) could be worth. Null => prediction is not the lever, question closes; win => that gap is the prize.
Caveat: stamping truth changes behaviour so pass 2 drifts from the recording -> NEAR-oracle.

## 2026-07-18h — ORACLE TEST: perfect next-task knowledge is worth NOTHING

scripts/oracle_test.py, 120 paired seeds, UNIFORM regime (the regime where the map measurably works).
Pass 1 (PartACongestionRecordController) logs every commit; pass 2 (PartACongestionOracleController)
replaces layer 2's GUESS with the recorded TRUE next route per robot.
  champion 198.9 | oracle-layer2 196.4 | effect -2.51 SE 1.56 t=-1.60 CI [-5.6,+0.6] wins 50/120
  oracle lookup hit rate 83.6% (miss = robot never commits again in the episode)

DECISIVE VIA THE CI UPPER BOUND, not via significance: the best case for ANY next-task predictor is
+0.6 on-time value. So prediction QUALITY was never the lever. This closes the user's policy-rollout
proposal (simulate robot B's own decision forward) WITHOUT building it: the rollout would be an
expensive way to approximate an answer that is worth ~0 even when supplied exactly. Layer 2 is dead in
every form -- as written (+0.15 to fix), deleted (-1.17), and with perfect information (-2.51).

WHY (interpretation, not measurement): the map pays by SPREADING TRAFFIC (density), not by knowing who
goes where. Layers 1+3 already supply enough mass to spread routes; extra mass -- even exact -- does not
flip an argmin over 3 near-identical Yen routes, and may slightly over-deter cells that were fine.
Caveat: NEAR-oracle only (83.6% hit; stamping truth perturbs behaviour so the recording drifts). The
drift cuts the right way: better info than any real predictor could have, still nothing.

METHOD NOTE: the oracle/ceiling pattern (value-of-perfect-information) should be the DEFAULT first step
before building any predictor here. It would have pre-empted the delay head, the variance head and
layer 2 -- all built, all null.

## 2026-07-18i — Layer-2 table completed (all UNIFORM, 120 paired seeds, same baseline)

  champion (normal guess)  198.9   --
  layer 2 DELETED          197.9   -0.95  SE 1.92  t -0.49  CI [-4.7,+2.8]  wins 63/120
  layer 2 ORACLE (truth)   196.4   -2.51  SE 1.56  t -1.60  CI [-5.6,+0.6]  wins 50/120
(demand-regime rows for reference: freel2 rebuild +0.15 t=+0.04 @30; l2off -1.17 t=-0.34 @120)

Whole band is 2.5 pts on a base of 199 (~1%), everything inside noise. CONCLUSION: leave layer 2 as is,
delete it, or make it PERFECT -- same result within measurement error. The accuracy dial does nothing.

WHY (now evidence-backed, not speculation): TIMING MISMATCH, not prediction difficulty (the oracle rules
difficulty out -- exact truth changed nothing). The map has NO CLOCK. Measured today: the route being
CHOSEN right now is ~11 steps long (p95 27); a future robot does not free up and start its next trip for
~27 steps (median 22). The current trip is OVER before the future trip BEGINS -- same roads, different
times. So layer 2 is not wrong, it is EARLY: it marks traffic occurring after the journey you are
deciding about has finished. Layers 1+3 mark robots on the road DURING your trip, which is why they work.

IMPLICATION for the checklist's "[ ] (lower) time-indexed forecast (space-time occupancy)": that is the
ONLY thing that would make future-robot marks matter -- but the oracle bounds the entire prize at +0.6
on-time value, so the complexity is not justified. Direction CLOSED, with a ceiling, not just a null.

FRAMING CORRECTION (user pushed back, correctly): I had been writing "layer 2 is dead/inert/disproved",
which reads as "delete it". The measurements do NOT support deletion -- deleting it is -0.95 (uniform) /
-1.17 (demand), i.e. very slightly WORSE. Correct actionable statement: KEEP IT (harmless, small compute
cost); do NOT invest in improving it. "Stop spending effort here", not "remove this".

## 2026-07-18j — WHY future tasks can never help: the information gradient (user's insight)

PER-ROUTE ORACLE (user's exact spec: a future trip counts only if it STARTS before THIS route ENDS --
no fixed horizon, the window is the length of the journey being scored), 120 paired seeds, UNIFORM:
  champion 198.9 | per-route oracle 198.6 | -0.33 SE 1.90 t=-0.17 CI [-4.0,+3.4] wins 62/120
  (32% of future trips counted, 68% dropped as too-late)
This REPLACES the retracted "+0.6 ceiling" (which was measured with the filter disabled). Corrected
ceiling on future-task knowledge, correct spec, full power: centred -0.33, best case +3.4.

THE STRUCTURAL REASON (user, unprompted -- cleaner than any explanation I offered):
future robots will reroute around YOU, so you never needed to cover them.
  Information only grows with time. When I plan, B's next trip is a GUESS. When B plans, my route is a
  FACT (layer 1). So the LATER planner always knows more about the earlier one than the earlier could
  ever know about the later. Every now-vs-later conflict is therefore better resolved by the LATER
  decision -- free, certain, no forecasting. Layer 2 asked the WORSE-informed decision to do the
  avoiding; accuracy cannot fix an inverted information gradient. Hence perfect foreknowledge = 0.

UNIFIES LAYER 3 AND LAYER 2 (same mechanism, different time scale):
  L3: robots planning in the SAME round have no natural ordering -> we IMPOSE one (sequential planning,
      each stamps so the next avoids it). Manufacturing later-avoids-earlier where time gave none. WORKS.
  L2: robots planning in DIFFERENT rounds already have that ordering from time itself. REDUNDANT.
PRINCIPLE: coordination flows from the better-informed decision to the worse-informed one; information
only grows with time; therefore avoidance points BACKWARDS, never FORWARDS.

COROLLARY -- what belongs in the map: things TRUE NOW that nobody else will handle for you.
  layer 1 (robot is on that road, won't move for you) YES | layer 3 (we removed the ordering, restore
  it) YES | PICKERS (on the floor now, 37.7% of moving traffic, currently INVISIBLE) YES, still a gap |
  future tasks NO -- time was already solving them.

RETRACTED: my "double avoidance" mechanism from earlier (both robots detour around the same phantom
conflict). It was fitted to the fixed-horizon sweep's NEGATIVE rows at n=40, which I had already flagged
as unreliable. At n=120 on the correct spec the effect is ZERO, not negative -- so the premise "why is it
doing worse" was itself an artefact. Third time today I explained an underpowered number; discard it.

## 2026-07-22 — Rollout audit + LOAD_TIME calibration sweep

ROLLOUT AUDIT. Three claimed gaps; MEASUREMENT KILLED TWO:
 1. "use A* not Manhattan for the haul" -> VACUOUS. build_agv_graph is grid_2d_graph over ALL cells
    (AGVs drive UNDER shelves, Kiva-style), so Manhattan IS the shortest path. Measured diff exactly
    -1 on 60/60 shelves = the endpoint convention. Long-standing checklist TODO, deleted not built.
 2. "return leg goes to nearest EMPTY storage, not back to origin" -> TRUE in the env but the proxy is
    ACCURATE: actual return 16.4 mean / 15 median vs assumed (=haul dist) 15.5 / 15. Not a gap.
 3. LOAD_TIME=5 -> the only real item. The env has NO loading delay (_execute_load sets carrying_shelf
    the same step both robots share a cell); the only true cost is TOGGLE_LOAD being a micro-action = 1
    step. Also VERIFIED: the rollout's assumed dock == the dock actually chosen, 32/32.

LOAD_TIME SWEEP (30 seeds, uniform, ties broken out, sign test on DECIDED seeds):
  champion(=5) 201.4 | lt1 198.1 -3.27 ties14 W-L 3-13 p=0.021 | lt3 199.8 -1.60 p=0.388
  | lt5 201.4 +0.00 ties 30/30 <- SANITY PASS | lt8 199.6 -1.80 p=0.096 | lt11 203.5 +2.17 p=0.210
  | lt15 199.6 -1.80 p=0.845
CONCLUSION: HAVING a pad matters (removing it: p=0.021 here, p=0.009 at n=52 earlier -- replicated).
Its SIZE does not, anywhere in 3..15. KEEP LOAD_TIME=5; stop tuning. The honest fix is a RENAME: it is
padding for un-modelled delay, not loading physics. Root cause: `finish` is EMPTY-WORLD (zero delay) and
used RAW -- `per_task_window()`, written to calibrate geometry against observed durations, is DEAD CODE,
never called; USE_GLOBAL_WINDOW=False in Part A.

FAILED HARNESS (worth keeping as a lesson): first sweep split the pad into LOAD_TIME=1 + a new
DELAY_ALLOWANCE routed through the _finish_delay hook. INVALID -- LOAD_TIME is consumed in THREE places
(AGV rollout finish, the PICKER funnel's own finish, and free_again -> others' partner_eta case-3), and
the hook reaches only the first. The planted SANITY ARM (pad 5, must equal champion) differed on 9/30
seeds and caught it. Cause: I let a RENAME change the MECHANISM. Sweep the existing knob instead.

BATTERY. Found the step-4 battery filter has NEVER EXECUTED: battery_feasible lives in the Part A funnel
but no Part A controller has a BatteryTracker (bcfg/blevel None -> returns True); the only controller
WITH a battery (BatteryAwareController) is Rush-derived and never enters that funnel. Checklist recorded
this as DONE + "wired into rollout". Built PartACongestionBatteryController (tracker + step() + ported
charge management -- attaching a tracker alone leaves every level pinned at 1.0). Now live: levels drain
(min .15 mean .34 after 300 steps), charging works. BUT battery_feasible still deletes 0/345 plans --
GO_CHARGE=0.35 diverts robots before they can ever fail. Filter is a backstop behind a rule that never
lets it fire. Needs battery RECOMPRESSION (steps_per_charge 300 -> ~120) rather than 1000-step episodes:
same effect, keeps episodes at 500 so baselines stay comparable and runs stay fast.

REACHABILITY RESERVE (user's design, built): replaced the fixed floor (0.10) with
`charger_reserve` = dist(end position -> nearest charger) * drive_drain, floor set to 0. A flat floor is
a scalar answer to a spatial question -- too strict beside a charger (refuses safe tasks), too lenient
far from one (strands). End position now `nearest_empty_storage(nearest_dock(shelf))` = the slot the AGV
actually drops the shelf at, NOT the dock (measured 27 steps apart in one sample = ~9% of a battery,
about the size of the whole old floor). Verified: mid-run 4 carried shelves -> exactly 4 empty slots.

STILL OPEN in the rollout: picker battery is not rolled out at all (AGV energy only, and the picker
funnel has no battery check); load/unload micro-action steps unmodelled (absorbed by the pad anyway).
PROPOSED NEXT (not built): ORACLE ON COMPLETION TIME -- record each task's true finish, replay it to the
planner in place of the estimate. Bounds what ANY delay model (incl. a fleet-rollout world model) could
buy, before building one. Unlike layer 2 this has a real prior: the makeable/doomed cutoff is a HARD
threshold proven sensitive to ~4 steps, and NOBODY ELSE resolves your missed deadline -- so the
avoidance-points-backwards principle does NOT transfer here.

## 2026-07-22b — PARKED IDEA (user): world model as the JOINT PLAN EVALUATOR (Part D and beyond)

IDEA: grow the world model into the evaluator for Part D -- or replace the Part A / Part D split
entirely. Instead of greedily scoring one robot->task->route at a time, SIMULATE CANDIDATE JOINT PLANS
forward (after preliminary shortlisting) and score the whole outcome: throughput, deadline meeting,
sync-up, collisions -- for this task AND across future tasks -- then pick the best plan SEQUENCE, which
simultaneously determines the task assignment for every robot.

WHY IT IS STRUCTURALLY SOUNDER THAN LAYER 2 (the key point): the self-reference / fixed-point problem
that killed layer 2 DISAPPEARS under joint planning. Layer 2 had to PREDICT what robot B would do, and
acting on the prediction invalidated it (the oracle recording went stale the moment you used it). When
you CO-DECIDE B's plan as part of the same joint plan, there is nothing to predict and no fixed point to
chase. The avoidance-points-backwards principle does not apply either -- it is about which of two
SEQUENTIAL decisions should do the avoiding; joint planning removes the sequencing.

PAIRS WITH ADG (built, parked, Stage 1): joint planning only pays if execution FOLLOWS the plan. Today
the env runs its own A* + reroute, so a jointly-deconflicted plan decays on contact. ADG execution
(exact routes, delay absorbed as waiting, 0 collisions by construction) is the natural executor, and
Part D deconfliction was already listed as ADG's prerequisite. So: joint world-model planner -> Part D
deconfliction -> ADG execution is one coherent chain, not three separate items.

COSTS / OPEN: combinatorial blow-up (needs the shortlisting the user specified, plus beam search or
LNS past ~5 robots); a fleet rollout per candidate plan is a sim inside the sim; and the env's own
reroute/stuck resolution adds stochasticity unless ADG drives execution.
SEQUENCING: bound it FIRST with the completion-time ORACLE (see 2026-07-22) -- that measures whether
better timing knowledge changes decisions AT ALL, cheaply, before anything this large gets built.

>>> USER ASKED FOR THIS SUMMARY TO BE REPEATED AT THE START OF THE NEXT SESSION. <<<

## 2026-07-22c — COMPLETION-TIME ORACLE: NULL. The delay direction is CLOSED, and rung 3 gets cheap.

scripts/oracle_delay.py, 30 paired seeds, UNIFORM, disturbances OFF:
  champion 201.4 | delay-oracle 201.7 | +0.37 SE 1.65 t=+0.22 ties 7/30 W-L 15-8 sign p=0.210
  95% CI [-2.9,+3.6].  Lookup coverage 52% (tasks never delivered in pass 1 fall back to the estimate).
  REALIZED DELAY: mean +15.8, median +11.2, p10 +0.8, p90 +36.0 -- against a pad of 5.
=> The estimate is wrong by ~16 steps on average (36 at p90) and correcting it EXACTLY is worth +0.37.

DECOMPOSITION (planned in advance, per the user's objection) resolves as NEITHER branch:
  LEVEL     : true delay shifts estimates +15.8 on average; the LOAD_TIME sweep showed the pad is FLAT
              from 3..15, so a level shift is ~neutral. Consistent.
  VARIATION : per-task differences worth ~0 -- exactly what the delay head found (9% MAE over a
              constant, ~0 on the tail). Consistent.
Both ~0 -> total ~0. All five delay results now agree (learned head, variance head, congestion-finish,
per-task window, completion-time oracle).

THE PAYOFF (this is why the test was worth running even though the user correctly predicted the null):
ROLLOUT COMPLETION ITEM 6 -- the interference / empty-world model -- IS UNNECESSARY. That was the
step-simulate-the-whole-fleet piece, the weeks-vs-days item. If PERFECT timing knowledge is worth +0.37,
a simulator that computes timing more accurately has nothing to sell. So a rung-3 joint plan evaluator
can CHAIN CHEAP ANALYTIC ESTIMATES instead of simulating contention, and rung 3 collapses to plumbing:
items 1-5 + 8-9 (end position, state object, composition, objective accumulator, pickers first-class,
charging prefix, demand arrivals). Days, not weeks.

CAVEATS: 52% coverage; near-oracle drift (acting on truth changes behaviour); 30 seeds. BUT
disturbances were OFF -- the friendliest possible world for prediction -- so a NULL GENERALISES UPWARD.
With random disturbances timing is strictly less predictable, never more.

USER'S OBJECTION, recorded because it was right and sharpened the analysis: "you can never estimate
proper completion time, especially with disturbances -- this is a redo of the LightGBM head." Half
right. NOT a redo (the head measured PREDICTOR QUALITY; the oracle measures WHETHER QUALITY MATTERS --
a bad predictor says nothing about the value of a good one). But correct that the test is ASYMMETRIC: a
null is decisive, a positive would only have bounded a prize we likely could not collect. Frame future
oracles that way.

## 2026-07-22d — LOOKAHEAD DEPTH x FREE-HORIZON grid: ALL NEGATIVE

User's idea: greedy assignment maximises per-robot value, not TOTAL value -- a robot can grab the task
that was the only good option for the robot behind it. Added an opportunity-cost term: when scoring
candidate X, simulate the next robots taking their best remaining task from a pool WITHOUT X, and add
the value they collect. Two SEPARATE knobs (after a design fix, below):
  LOOKAHEAD_DEPTH  = how many CURRENTLY-FREE robots (certain, competing this round), full weight
  FREE_HORIZON     = how far ahead to also count SOON-TO-FREE busy robots, DISCOUNTED by (1-t_free/H)
                     (a robot freeing in 3 steps competes hard; one at 40 barely does -- a hard cutoff
                     must answer 0 or 1 and both are wrong). Anchored at the DOCK where it frees up,
                     NOT path[-1] (which is the robot's own shelf for 37% of busy AGVs = layer 2's bug).

RESULT (30 seeds, uniform, ties + sign test on decided seeds):
  champion 201.4 | depth1 +0.00 ties 30/30 <- SANITY PASS
  d2h0  196.3  -5.07 ties17 W-L 2-11 p=0.022   <- cleanest arm, clearly WORST
  d2h20 195.3  -6.07 ties 8 W-L 6-16 p=0.052
  d3h0  196.8  -4.60 ties10 W-L 6-14 p=0.115
  d3h20 196.2  -5.17 ties 3 W-L 9-18 p=0.122
NO arm positive; best arm's upper CI bound is +1.2 -> no meaningful gain available. The HORIZON knob is
consistently worse than h0 (d2h20<d2h0, d3h20<d3h0), as the timing-noise argument predicted
(time-to-free MAE ~14).

CAVEAT THAT MATTERS: the lookahead guesses what OTHERS would take using the CHEAP SCREEN
(value - 0.15*dist), not their real funnel score. So this may indict the PROXY, not the CONCEPT. Exact
bipartite matching does not guess -- it optimises the REAL score matrix the funnel already computes and
currently discards by taking greedy row-maxima. So: weakened, not killed. Still worth the ~20-line test,
BECAUSE this was negative -- if matching on true scores also fails, the assignment layer is done.

DESIGN FIX made mid-experiment (user caught it): the first implementation put free and soon-free robots
in ONE list truncated at DEPTH-1, so soon-free were only reached when free robots ran out (48% of calls)
-- the horizon knob's reach was hostage to the depth knob, defeating the separation. Now they have
SEPARATE budgets. Detected from the raw per-seed lines showing h0 and h20 arms producing IDENTICAL
numbers. Same detection pattern as the calibration sweep's failed sanity arm: identical outputs mean the
mechanism is not reaching the decision, and no number of seeds fixes that.

## 2026-07-22e — TRUE-FUNNEL lookahead grid: still negative. The proxy was not the problem.

User's correct objection to 2026-07-22d: the lookahead guessed others' wants with the cheap screen,
not the real funnel score. Rebuilt (PartACongestionTrueDepthController): others' value = their TRUE
funnel score (Yen k-routes -> congestion route pick -> rollout partner ETA/sync -> makeable/doomed
tier). Affordable via a per-turn cache: another robot's SCORES do not depend on which task I take --
only its argmax does (one task removed from the pool) -- so the table (TOP_K=5 x DEPTH-1 robots) is
built once per dispatch turn and each of my candidates re-maxes with one exclusion. Cache keyed to a
per-turn token (_look_seq) because layer-3 stamping DOES change scores between turns. Recursion guard:
_true_score omits _task_score_adjust.

RESULT (30 seeds, uniform): t1 sanity 30/30 ties PASS | t2h0 -6.30 (W-L 9-14, p=0.405) | t3h0 -7.50
(13-15, 0.851) | t2h20 -2.90 (11-18, 0.265). No arm positive. Combined with the proxy grid (d2h0 -5.07
p=0.022), the opportunity-cost lookahead FAILED WITH TWO DIFFERENT VALUE FUNCTIONS -> the concept, not
the proxy, is what does not pay. Individual sign tests here unresolved, so no mechanism claimed; the
resolved statement is "no gain available anywhere in either grid".
IMPLICATION: bipartite matching (parked) now looks UNLIKELY -- both grids approximated the exact
objective matching optimises. Its untested distinction is simultaneous-vs-sequential only.

## 2026-07-22f — ASSIGNMENT HINDSIGHT ORACLE (uniform): first LARGE POSITIVE of the project

User's spec: best-of-M randomized assignment schedules on the SAME seed lower-bounds the
hindsight-optimal assignment; if best-of-hundreds barely clears the champion, the assignment ceiling is
close and smarter assignment (matching/learned/search/rung-3) is dead. Built: _pick_winner hook in the
funnel (default argmax; explorer samples uniform among top-K scored candidates, K in {2,3,4}, half of
rollouts also shuffle robot order). Everything else (routes, map, tiers, sync) untouched.
scripts/oracle_assign.py, 5 seeds x 120 rollouts, uniform regime.

RESULT: gap +25.8 mean (+12.8%), EVERY seed double-digit:
  s0 193->224 (+31, beat-rate 57/120!) | s1 207->233 (+26, 46/120) | s2 209->228 (+19, 17/120)
  | s3 213->239 (+26, 31/120) | s4 195->222 (+27, 40/120)
Scale: 5x the dock win (+5.3), 7x the whole congestion map (+3.4). And ~1/3 of PURELY RANDOM shuffles
beat the champion outright -- greedy-by-priority-order is not on a peak (on s0 the champion is barely
above the MEAN random rollout).

CONFOUND (why day-list rerun is REQUIRED before believing it): every rollout's value is a true outcome
(no measurement noise), but assignment decisions and the task-spawn stream vary TOGETHER -- in the
uniform regime each delivery draws the replacement task from the RNG, so different schedules get
different task sets. Best-of-120 selects for spawn LUCK as well as coordination SKILL. Day-list mode
(all orders drawn at t=0, before any robot moves) freezes the world completely -> surviving gap = pure
assignment headroom. RUNNING (5 seeds x 120, parallel).

LEADING HYPOTHESIS for where the gap lives (user's, testable, NOT asserted): the makeable score is
1000 + v - W_SYNC*wait + 0.01*survivors -- TRAVEL TIME APPEARS NOWHERE. Value-greedy, not value-RATE-
greedy: a v=12 task 40 steps away beats a v=11 task 10 steps away, every time, though robot-minutes are
the scarce resource. The explorer's perturbation ("take a slightly-lower-value task instead") is
sometimes exactly "take the nearer one". If true, capturable by score = 1000 + v - alpha*finish
(alpha ~0.05-0.2) -- a ONE-LINE arm to screen right after the day-list verdict. Yen routes are NOT
implicated (near-shortest to whichever task is chosen; the gap is WHICH task, one level up).

## 2026-07-22g — DAY-LIST assignment oracle: the headroom is REAL. ~+5.6% pure assignment skill.

Day-list mode (all orders drawn at t=0 BEFORE any robot moves -> world identical across rollouts, zero
spawn luck), 5 seeds x 120 rollouts:
  s0 448.9->463.1 (+3.1%, beat 31/120) | s1 471.2->496.4 (+5.3%, 49/120) | s2 301.7->313.5 (+3.9%,
  30/120) | s3 337.4->373.8 (+10.8%, beat 93/120 -- champion BELOW the mean random rollout, 345.3)
  | s4 546.3->572.2 (+4.7%, 40/120).  MEAN +22.7 pts = +5.6% (range 3.1-10.8), beat-rate ~41%.
(Day-list scores ~2x uniform because per-ORDER scoring with batching; compare %, not points.)

VERDICT: the uniform oracle's +12.8% splits ~half/half: ~7% spawn luck (unrecoverable by any policy),
~+5.6% GENUINE assignment headroom -- a LOWER bound (random search != optimum), reproducible on every
seed, and 2x the best shipped improvement (dock +2.7%, map +1.7%). Greedy value-argmax-in-priority-order
is not near a peak: ~41% of RANDOM top-K shuffles beat it in a fixed world (78% on s3).

This is the FIRST measured positive ceiling after: delay (5x null), route-level future info (layer 2,
3x null), one-ply considerate lookahead (2 grids <= 0). The decision layer's open axis is ASSIGNMENT --
specifically WHICH task, since routes are near-shortest and timing knowledge is proven worthless.

RUNNING: value-rate screen (user's hypothesis: makeable tier ranks 1000+v, travel time NOWHERE in the
final score; rank instead by RATE = v/completion, RATE_SCALE in {20,40,80}). Also measured: the cheap
screen EXCLUDES the #1-value task from a robot's shortlist 60.8% of the time (avg 2.29 of top-3 value
excluded; pool ~32 -> keep 15) -- an independent flaw (cannot explain the oracle gap: the explorer drew
from the SAME shortlists), second arm to test (screen by pure value) after the rate verdict.

## 2026-07-22h — VALUE-RATE (rate80) CONFIRMED: +10.78 on 120 fresh seeds. Largest win in project history.

User's one-line idea: makeable tier ranks by VALUE PER STEP (1000 + 80*v/completion) instead of raw
value (1000 + v). Full protocol, three INDEPENDENT seed sets:
  TUNING (0-29):       rate20 +0.3 | rate40 +6.97 (t=3.01, p=0.005) | rate80 +9.30 (t=3.24) | rate160
                       +5.67 -> clean dose-response hill peaking ~80.
  HELD-OUT (100-129):  rate40 +2.93 (shrank -- winner's curse hit the CONSISTENT arm) | rate80 +10.30
                       (t=1.99, CI [+0.2,+20.4]) | blend40 +5.47 but LOSING 14-16 (magnitude only).
  CONFIRMATION (200-319, n=120): +10.78 SE 2.47 t=+4.36 CI [+5.9,+15.6], W-L-T 75-43-2, sign p=0.004.
  BOTH instruments significant. NO shrinkage across sets (9.3 -> 10.3 -> 10.8).
= ~+5.4% on-time value. 2x dock (+5.3), 3x the whole map (+3.4). ONE METHOD OVERRIDE.

CHARACTER (n=120): median +4; FIVE seeds rescued +50..+127; ONE crater -106. Tail-dominated: rate
pricing avoids disasters that value-chasing walks into (same signature as the map's storm prevention,
~3x the payoff). The "monster win" repeated on all three seed sets -> property, not luck.

BLEND verdict (user's question "does rate mishandle tiny-value tasks?"): pure rate CAN prefer a v=3
quickie over a v=15 haul -- but empirically the blend (v + S*v/c, keeps absolute value on the ticket)
was WORSE than pure rate everywhere tested. Dilution, not protection.

WHY IT WORKS (and why the assignment oracle found headroom): the scorer maximised value per PICK while
the scarce resource is robot-MINUTES. v=12 at 40 steps beat v=11 at 10 steps every time. Rate pricing
fixes the currency. NOTE the +5.6% day-list assignment ceiling and this +5.4% uniform win are
suspiciously similar sizes -- the DECOMPOSITION run (day-list oracle vs rate80 baseline, RUNNING) tells
whether rate80 ATE the assignment ceiling (residual ~0 -> coordination machinery stays dead) or the
ceiling remains (residual fat -> true robot-awareness prize exists).
CAUTION pending: day-list rate80 BASELINES look mixed vs value champion (up s1, down s2-s4 early) ->
possible REGIME-DEPENDENCE (rate philosophy = "grab quick stuff, there's always more" fits the
always-full uniform buffet; day-list's finite shrinking queue may differ). Do not crown outside uniform
until that lands. Champion status: rate80 = PartACongestionRateController(RATE_SCALE=80) is the new
UNIFORM-regime champion, pending the day-list read.

## 2026-07-22i — FINAL 120-SEED MATRIX (stream + day-list, uniform RETIRED): plain value holds.

User's spec: all of today's tactics x the two REALISTIC regimes, 120 seeds, uniform regime retired
("generating tasks at random -- that's stupid"). 12 arms x 2 regimes x 120 = 2880 episodes, 8 parallel.

STREAM (baseline value 320.2): NOTHING beats plain value. Best arm rate160 +0.51 (noise). rate80 -3.41.
adapt2 SIGN-SIGNIFICANTLY WORSE (41-64, p=0.031). explore-as-policy -32.3 (-10.1%, t=-7.75).
DAY-LIST (baseline 391.4): blends mildly POSITIVE -- blend40 +2.38 (+0.6%, 62-37, sign p=0.015),
blend20 +2.05 (56-35, p=0.035); whole blend family positive. ALL rates negative. explore -36.5 (-9.3%).

VERDICTS:
1. rate80's +10.78 (t=4.36, 3 independent sets, no shrinkage) was REAL BUT REGIME-BOUND to the retired
   uniform world. In both realistic regimes it is mildly negative. METHOD LESSON (add to the rules):
   VALIDATE IN THE REGIME YOU INTEND TO DEPLOY IN. We ran tuning/held-out/confirmation flawlessly and
   still nearly crowned the champion of a world we do not care about.
2. PLAIN VALUE is the realistic-regime champion -- unbeaten by 11 scorer variants (rate x4, blend x4,
   adaptive x2, explore). The SCORER was never the problem in the regimes that matter.
3. Load-adaptive pricing (my proposal): dead on arrival (adapt2 significantly worse on stream). Buried
   same day it was born.
4. Explorer-as-policy -10%: its oracle glory was pure best-of-120 SELECTION, never a usable strategy.
5. THE STANDING PRIZE: the day-list assignment ceiling (+5.6% over value / +7.8% over rate80,
   best-of-120 schedules on FIXED worlds) is unreachable by every per-task pricing variant we own.
   Strongest evidence yet that the remaining headroom is SCHEDULE-SHAPED (sequencing/coordination) --
   the rung-2/3 direction. That is the only measured, uncollected money on the board.
BLEND on day-list (+0.6%, sign-significant): real but tiny; keep as a day-list-only note, not a crown.

## 2026-07-22j — URGENCY BONUS (urg8): FIRST CONFIRMED REALISTIC-REGIME WIN. Day-list only.

Origin: the champion-vs-oracle DIFFER (scripts/diff_champ_oracle.py) itemised the day-list ceiling's
+113 (5 seeds) into RESCUED +84 (valuable orders delivered 2-10 steps LATE -- within-tier ranking is
value-only, deadline a mere tie-break), CAPTURED +59 (low-value orders STARVED forever), LOST -30
(the oracle sacrifices almost nothing; 0 on two seeds). The gap is 2-5 orders per day, not broad error.

FIX (user-approved design, guarding against the EDF error): BOUNDED additive urgency bonus WITHIN the
makeable tier only: score = 1000 + v + URG_W*max(0, 1 - spare/40). Not EDF -- the hard feasibility
fence runs FIRST; hopeless-urgent tasks never enter. Not a re-sort -- capped at URG_W, so tight-v14
beats loose-v15 but tight-v3 never jumps loose-v12. Distinct from soft-P(on-time), which pushed the
OPPOSITE way (discounted tight tasks) and failed.

SCREEN (30 seeds): day-list clean dose-response +1.47/+3.30/+7.13 (urg8 t=3.12, sign p=0.043); STREAM
INVERTS at urg8 (-7.57) -- the pre-declared boundary-optimism signature (stream's rush tier arrives
already tight; boosting near-deadline tasks there chases secretly-doomed ones). REGIME-GATED, not
overfit: which regime you are in is known at runtime (you have the morning order sheet or you don't).

ACCEPTANCE (order-level, seeds 0-4): fix-rescued +16.1 vs fix-lost -5.9 (~3:1) -> does what it claims;
LOST nonzero (one displaced order, seed 4) -> the boundary cost exists, small. Captures only ~19% of
the oracle's rescued pool: a pick-order bonus cannot START a task earlier -- the rest is SEQUENCING.

CONFIRMATION (120 FRESH day-list seeds 200-319): +3.54 (+0.9%) SE 1.10 t=+3.22 CI [+1.4,+5.7],
W-L-T 62-26-32, sign p<0.001. Screen-to-confirm shrinkage +7.1->+3.5 as expected; survived BOTH tests.

DEPLOYED CONFIG: stream -> champion unchanged (urg8 unconfirmed-negative there); day-list -> urg8.
LEDGER after this fix: day-list oracle ceiling was +5.6%; urg8 banks ~+0.9%; the remaining ~4.5%
(most of RESCUED + all of CAPTURED) is SCHEDULE-SHAPED -- the sequencer's measured prize.
(Optional untested combo: urg8 + blend40, both individually positive on day-list at 120 seeds.)

## 2026-07-22k — Latent env crash found by the prox sweep (fixed)

sim_dashboard.py RETURNING logic crashed (`argmin of empty sequence`) when an AGV finished delivering
and ZERO free storage slots existed -- all claimed by other simultaneously-returning AGVs. Never fired
in hundreds of prior runs; the proximity-sweep behaviour synchronises short trips enough to hit it.
FIX: if no free slot, hold at the dock one step and retry (only changes a state that previously
crashed the process, so no completed result is affected). Prox screen chunk A relaunched.

## 2026-07-22l — CAPTURED fix via proximity bonus: FAILS. The residual is officially scorer-proof.

Design: flat capped proximity bonus on top of urg8 (PROX_W*max(0,1-fetch/15)) -- the urg8 pattern
aimed at the CAPTURED category (+59: starved cheap orders the oracle sweeps when convenient). Screen
(30 daylist seeds): urg8 +7.13 | u8p2 +6.83 | u8p4 +5.00 | u8p8 +5.43 | p4 alone +1.10 (noise).
MARGINALS of prox over urg8: -0.30 / -2.13 / -1.70 -- all <=0. Proximity adds NOTHING; mildly negative.
(Seed-3 teaser u8p8=374 ~ oracle ceiling: one-seed mirage, killed by the marginal. Third time this week
the wait-for-the-table rule ate a pretty number.)

WHY (hypothesis): bonus fired on 45% of makeable scorings -- too broad, de facto distance re-pricing
(the rate80 failure mode), and the oracle does not collect starved orders via at-the-moment proximity;
it FITS THEM INTO THE SEQUENCE where they cost least. Wrong observable for an en-route economy.

LEDGER (final for the scorer era): day-list ceiling +5.6% | urg8 banks +0.9% (confirmed) | remaining
~+4.5% now tested against EVERY scorer lever we own (rate x4, blend x4, adaptive x2, screens x2,
urgency x3, proximity x4, explore) -> SCHEDULE-SHAPED, SCORER-PROOF. The sequencer's measured prize.
Deployed config unchanged: stream = champion; day-list = champion + urg8.

## 2026-07-22m — SEQUENCER v0 (rollout re-ranking): TIES urg8, does not beat it. Depth curve mapped.

Build: Bertsekas-style rollout -- champion funnel shortlists top-5 first moves; each is scored by
simulating the FLEET forward (state advances: queue consumed, deadlines ticked, robots re-freed at
estimated time/position via estimator B, day-end capped; base policy inside = the champion's own rule
incl urg8; currency = banked on-time value). Only the first move commits. Sanity sq0==urg8: 30/30.

DEPTH SWEEP (30 daylist seeds, horizon = DEPTH*75 steps):
  vs champion: sq1 -0.10 | sq2 +4.57 | sq3 +7.70 | sq5 +8.20 (t=3.67, sign p=0.013) | sq8 +8.20
  MARGINAL over urg8 (+7.13): sq1 -7.23 (t=-1.98) | sq2 -2.57 | sq3 +0.57 | sq5/sq8 +1.07 (15-15)
FLATTENING ANSWER (user's question): rises through depth 5, EXACTLY flat 5->8 -- depth 5 (~375 steps)
already reaches day end; the useful horizon is the remaining day. LOW end is the warning: sq1 is
actively harmful -- a 1-task-ahead sim is noisy enough to MISRANK moves the scorer got right.
sq5==sq8 bit-identical (horizon saturation), and NO downward bend: the compounding-estimate-error
disease did NOT appear at deep horizons.

VERDICT: the world model (now genuinely one: state, transition, composition, objective, rules-based
agents inside) MATCHES the best scorer but does not collect the ~4.5% residual. HYPOTHESIS (flagged):
v0 branches only over MY single first move; the greedy tail washes out most first-move differences,
and the oracle's winning schedules differ in MANY coordinated moves. The missing dimension is
BRANCHING WIDTH -- JOINT first moves for the chunk of simultaneously-free robots (the user's original
spec, deferred from v0) -- and possibly sim fidelity (no partner wait inside; +-14/task timing).
NEXT CANDIDATE: v1 = joint combos over free robots' top-3 each (<=27 branches/round when 3 free),
same simulation core, same sanity discipline.

## 2026-07-22n — Deviation gates (user's two families): no significant winner; sequencer capped ~+2 via single-robot re-ranking

User asked: gate the sim's deviations from Part A's pick by (a) THROUGHPUT margin (sim advantage >= M)
and (b) UTILITY tolerance (only alternatives within T of the incumbent's funnel score; any finite T
forbids crossing the ~1000-pt deadline-tier gap). 30 daylist seeds, marginals over urg8:
  raw sq5 +1.07 (15-15) | M=2 +1.97 (t=1.13, 14-8-8) | M=5 -1.27 | M=10 -1.03 (24 ties -- over-gated
  back into urg8) | T=2 +1.80 (15-12) | T=5 +0.67 | T=10 -2.30
NO significance anywhere; best arms ~11-12% of the residual. SHAPE: tightest gate helps slightly
(trims worst sim noise), heavier gating kills good deviations with the bad. VERDICT: deviation
discipline is worth ~+2 max -- the single-robot re-ranking sequencer is CAPPED there however gated.
Missing dimension remains branching width (joint moves) and/or sim fidelity (pickers), not deviation
hygiene. sq5 reproduced its prior values exactly after the _pick_winner refactor (regression sanity).

LAUNCHED (stream, 30 seeds): (a) _SA5 = sequencer w/ SYNTHETIC ARRIVALS inside the horizon (demand
model's statistical shape; one shared imagined future per dispatch round across branches -- fairness;
INFO FLAG: reads true model params, deployment would estimate them online) vs _Sq5S frozen-arrival
control (URG_W=0 on stream); (b) user's FETCH-LEG RE-DECISION rule: release a robot only if still
traveling to the shelf (never carrying/delivering/at-rendezvous) when a NEW arrival beats its task by
SWITCH_MARGIN {0,3,6} (cheap-screen from current position); funnel re-decides. Env-side release
(busy=False, path=[]) to avoid zombie walks.

## 2026-07-22o — Stream screen: frozen-arrival prediction CONFIRMED; arrivals rescue to par; preemption null

30 stream seeds: sq5s (sequencer d5, frozen arrivals) -15.73 t=-2.01 <- the pre-flagged failure mode,
CONFIRMED (plans for the end of a queue that keeps refilling). sa5 (+synthetic arrivals in horizon,
true-model-params info gift, one shared imagined future per round) = -1.53 vs champion: the repair is
worth +14.20 isolated (t=1.61, 16-14) but only reaches PAR. Stream champion remains unbeaten by
everything ever tested. User's fetch-leg re-decision rule (release only while traveling, never
carrying/delivering, margin {0,3,6}): -0.80/-2.80/-2.73 -- null at every margin.
STREAM LEDGER: no mechanism has ever beaten plain champion there. DAY-LIST remains the only regime
with measured, collectable headroom (~4.5% residual, schedule-shaped).
NEXT (user-confirmed design): JOINT first-moves -- when k robots are free in the same round, enumerate
conflict-free combos of their top-3s (<=27), evaluate with the SAME sim core (all k pinned, everyone
else base-policy), commit all k first moves, receding horizon beyond. KNOWN SANITY WEAKNESS found at
design time: a perfect tie-arm is impossible because predicting OTHER robots' top-1 (for combo
generation) can differ from what the sequential funnel would have picked for them (stamping order,
battery filter) -> sanity = JOINT_OFF code-path tie + mechanism counters + k>=2 round stats, stated
honestly rather than faked.

## 2026-07-22p — JOINT first-moves controller built (beam-search combos). Two design findings.

Build: PartACongestionJointController -- when k>=2 robots free in the same round, candidates per robot
scored with the TRUE funnel (_true_score), combos evaluated with the shared sim core (all k firsts
pinned, base policy tail, receding horizon), winning combo steers each robot's _pick_winner; k=1 and
out-of-plan robots fall through to sq5 (strict superset). Sanity: JOINT_ON=False ties sq5 exactly
(verified); bit-identical tie for k>=2 impossible (predicting others' candidates != sequential funnel
picks) -- counters instead.

FINDING 1: naive product-then-filter enumeration SELF-DESTRUCTS on preference overlap: at t=0 all 8
robots' top-3s draw from the same ~5 favourites -> every 8-tuple has a duplicate -> 6561 combos, ZERO
valid. Exactly when coordination matters most. FIX: beam search over robots (extend partials with each
robot's top-K UNUSED tasks from a WIDENED shortlist, keep JOINT_BEAM=16 by true-score sum, simulate
survivors). After fix: 25 combos simulated, plan honored 10, missed 0 (300-step probe).

FINDING 2: with per-step dispatch, k>=2 occurs ~2 rounds/day on day-list (t=0 opening + coincidences).
JOINT here is mostly an OPENING-BOOK optimizer -- it sets the day's initial geography jointly, then
sq5 governs. Screen (30 daylist seeds, arms cong_l2on/urg8/sq5/joff/j2/j3) RUNNING.

## 2026-07-22q — JOINT first-moves: NULL. Sequencing campaign closed at this sim fidelity. REVISION of the item-6 verdict.

Joint screen (30 daylist seeds): sanity joff==sq5 30/30 | j2 -0.50 vs urg8 | j3 +0.17 | JOINT marginal
over sq5 = -0.90 (12-16-2). Optimizing the ~2 coordination rounds/day (mostly the t=0 opening) jointly
adds nothing.

CAMPAIGN LEDGER (all marginals over urg8, 30 daylist seeds): raw rollout +1.07 | best gate (M=2) +1.97
| joint +0.17 | oracle residual ~+17 pts. Every search idea evaluated with the COARSE ANALYTIC SIM caps
at +1-2; the oracle, whose evaluator is the REAL ENV, reliably finds +17.

REVISION (honest correction of 2026-07-22c): the delay oracle only proved timing precision worthless
for CLASSIFICATION (makeable/doomed). It did NOT prove evaluator fidelity worthless for RANKING WHOLE
SCHEDULES -- a different use of accuracy. Evidence now: same search ideas, two evaluators, 5x different
outcome. Most parsimonious reading: the +4.5% schedules EXIST but the analytic sim (+-14/task, no
pickers, dock-anchored positions) cannot distinguish them from average ones. Rollout item 6 (evaluator
fidelity: pickers first-class, possibly env-fidelity short rollouts) is UN-RETIRED for the specific
purpose of schedule ranking. Candidate next steps (not launched): (a) pickers inside the sim (item 5 --
the largest known omission, 37.7% of traffic); (b) real-env short-horizon evaluation of a few branches
(expensive, forkable-env question open); (c) accept +0.9% banked and close the assignment arc.

## 2026-07-22r — EVALUATOR FIDELITY WAS THE WALL. Same search, hi-fi sim: +1 -> +8 over urg8 (screen).

Three certain-information fidelity fixes to the sim core (_sim_core, shared by branch & joint):
  FIX 1 PICKERS AS RESOURCES: rendezvous = max(AGV arrival, best picker's ready time); pickers carry
        (free_time, pos) state updated per simulated assignment -- the SHARED-STATE coupling schedule
        ranking needs, and the dominant unmodeled delay.
  FIX 2 FREED-POSITION: robots re-enter at nearest_empty_storage(dock) (real re-entry geography,
        ~16-27 steps from the dock the old sim used) with the return leg in the clock.
  FIX 3 LIVE BIAS: every simulated completion += _delay_ema (the fleet's measured predicted-vs-realized
        bias, computed on every delivery, previously unused) -- the sim tracks TODAY'S actual pace.

SCREEN (same 30 daylist seeds, same arms as the coarse-sim runs -- fidelity is the ONLY variable):
  sanity sq0==urg8 30/30 | sq5: +1.07 (15-15) -> +7.97 (t=2.95, 20-8, sign p=0.036)
  | s5m2: +1.97 -> +7.60 (t=4.00, 21-7, sign p=0.013) | j3: +0.17 -> +0.23 (joint stays null, cleanly).
STACKED vs champion: urg8 +7.1 + ~8 = ~+15 of the ~+21.5 oracle ceiling => ~70% of the measured
hindsight ceiling captured by a deployable, rules-computed, zero-learned-parameter policy.
The 2026-07-22q hypothesis is CONFIRMED at screen level: the +17-vs-+1 evaluator gap was fidelity, not
search. Joint null persists (k>=2 ~2 rounds/day; same-instant coordination was never the prize).
CAUTION: screen seeds 0-29 are where depth/gate knobs were originally chosen -> winner's-curse risk
live. CONFIRMATION RUNNING: 120 fresh seeds (200-319), arms cong_l2on/urg8/sq5/s5m2, 4 parallel chunks.
No tears of joy until it lands.

## 2026-07-22s — HI-FI SEQUENCER CONFIRMED on 120 fresh seeds (sign p=0.001). Gate obsolete. Tails noted.

Confirmation (fresh daylist seeds 200-319, arms cong_l2on/urg8/sq5/s5m2):
  sq5 vs urg8: +3.58 SE 1.95 t=1.84 CI [-0.2,+7.4] W-L-T 73-38-9 sign p=0.00115
  s5m2: statistically identical (+3.58, 72-38) -> the DEVIATION GATE IS A PASSENGER under hi-fi
  physics (it filtered evaluator noise; fixing the evaluator dissolved its job). DROP IT.
  Stack vs plain champion: +7.12 (+1.8%) on fresh worlds ~= 1/3 of the oracle ceiling banked.
INSTRUMENT SPLIT (report both, per method rules): win-rate emphatic (73-38, strongest sign result of
the project); MEAN marginal (t=1.84) because tails are fat BOTH ways (best +79/+86, worst -79/-101,
median +3). Character: wins most days by a little, sometimes big, rarely loses big. Screen-to-confirm
shrinkage +7.97 -> +3.58, as always.
DEPLOYED CONFIG (day-list): champion + urg8 + hi-fi sequencer (sq5, no gate). Stream: champion,
unchanged. RUNNING: component ablation (sqnb/sqnp/sqnf) to attribute the fidelity gain (early smoke
hint: bias load-bearing, pickers possibly passenger -- the INVERSE of my guess).

## 2026-07-22t — ABLATION: the LIVE PACE BIAS is the entire fidelity win. User's suspect confirmed as the engine.

Component ablation (30 daylist seeds, marginals over urg8; full sq5 +7.97):
  minus BIAS  -> +1.07 (bias worth +6.90 = ~the whole effect)
  minus PICKERS -> +7.83 (worth +0.13, passenger) | minus FREED-POS -> +7.67 (worth +0.30, passenger)
The user questioned exactly this component ('isn't that just adding an average delay, which has been
failing all week?'). Answer: it IS the engine. Both verdicts stand simultaneously: per-task delay
PREDICTION for choosing tasks = dead (5 nulls + oracle); a measured GLOBAL pace correction keeping the
SIM'S deadline arithmetic honest = +6.9 by itself. Same data (_delay_ema), different USE.
SIMPLIFICATION AVAILABLE: bias-only sim (drop picker loop + freed-pos) ~ full performance at lower
compute; one 30-seed verification arm when convenient.

RE-ORACLE vs the NEW STACK (stored old-explorer ceiling, screen seeds 0-4): old mean gap +22.7 (+5.6%)
-> new mean gap +3.4 (~+0.8%); on seed 1 the stack BEATS the old best-of-120 (499.3 > 496.4). Differ:
captured ~EMPTY (chaining collected the starved orders as designed), rescued ~1 order/seed, seed-3
near-misses 0. Caveats: screen seeds (inflated); stored ceiling is the OLD explorer's -- fresh
_StackExplore oracle over the new stack RUNNING (seeds 0/1/3).

## 2026-07-22u — CRATER AUTOPSY -> PER-ORDER BANKING FIX: strict improvement. Ceiling above stack collapses to ~1-2%.

AUTOPSY (4 fresh-seed craters, all diverged at commit #0): shared signature = BATCHED SHELVES. The sim
banked a batch ALL-OR-NOTHING against its EARLIEST deadline (miss by 1 step -> credit 0 for a 47-value
stack) while reality pays PER ORDER. The sim therefore deferred slightly-tight batches forever (shelf
70: 6 orders/47.8 deferred t=82->319, all dead; shelves 111/221/236 same story).
FIX (_sim_bank): per-order banking from dm.pending -- sim now pays exactly as the world pays.
CRATER RECHECK: -79->-6, -60->-40, -51->-31, -41->-24 (halved, not cured -- a second, smaller
mechanism remains unidentified). GENERAL RE-SCREEN (seeds 0-29): +7.97 -> +9.47 (t=3.27, 20-7-3,
sign p=0.019) -- the fix helps the general case TOO. Strict Pareto improvement.

FRESH-EXPLORER ORACLE OVER THE STACK (baseline = stack minus the banking fix; seeds 0/1/3):
  gaps +2.4% / ~+0.4% / +1.8% (was +3.1/+5.3/+10.8 above the old champion); on seed 3 only 4/120
  random schedules beat the stack (was 93/120 beating the old champion). Perturbation-findable
  headroom is down to ~1-2%, measured against a baseline one fix stale.
PIPELINE THAT DID IT (repeatable): oracle -> differ (itemize) -> targeted fix -> order-level
acceptance -> fresh-seed confirmation -> crater autopsy -> structural fix -> re-validate everywhere.

## 2026-07-22v — FINAL CONFIRMATION: banking-fixed stack +6.07 over urg8 (t=3.59, sign p=0.00006), +2.46% total.

120 fresh daylist seeds (200-319): champion 390.6 -> urg8 394.2 -> sq5-FIXED 400.2.
  vs urg8: +6.07 SE 1.69 t=+3.59 CI [+2.8,+9.4], W-L-T 78-35-7, sign p=0.00006. BOTH instruments
  emphatic -- strongest confirmed result of the project. vs pre-fix stack on the SAME seeds: +3.58
  t=1.84 -> the per-order banking fix DOUBLED the confirmed effect and repaired the mean instrument
  (worst tail -79 -> -40; biggest crater mechanism gone).
STACK TOTAL: +9.61 (+2.46%) over plain champion on fresh worlds; measured ceiling above the stack
~1.5% (2-4/120 shuffles beat it on re-measured worlds).
DECAY-CREDIT experiment (user): -2.90 (9-14-7, n.s.) -> NOT adopted; the imagination must pay exactly
what the world pays -- under-payment (banking bug) deferred goldmines, over-payment (decay credit)
chases unpaid deliveries; both misrank. Flag off; would flip ON iff the business metric ever pays
partial late credit.
DEPLOYED (day-list): champion + urg8 + hi-fi sequencer (live pace bias + per-order banking; pickers &
freed-pos passengers, gate dropped). Stream: plain champion. OPEN: residual crater mechanism (worst
-40 remains), stream ceiling never measured, simplification arm (bias-only sim) unverified.

## 2026-07-22w — ERROR-SEED AGGREGATE SIGNATURE -> OPENING-ROUND COLD-CLOCK BUG -> WARM-START PRIOR

Aggregate autopsy, worst 8 losing seeds of the fixed-stack confirmation (-218 total):
  8/8 DIVERGE IN THE OPENING ROUND (t=0). Lost: 24 orders/254 value; 51% on batched shelves (batch
  story only half now); 20 LATE vs 4 NEVER (starvation ~gone -- it's timing).
MECHANISM: the live pace bias (_delay_ema) -- the component carrying the whole fidelity win (+6.9) --
initializes from OBSERVED deliveries. At t=0 none exist -> bias=0 -> THE SIM RUNS ON FANTASY TIME AT
THE DAY'S HIGHEST-LEVERAGE JOINT DECISION (the 8-robot opening allocation). By mid-day the clock is
honest but the geography is locked.
FIX: BIAS_PRIOR warm-start = measured historical realized-delay mean (+15) until the live EMA takes
over. TARGETED CHECK (the 8 selected-for-failure seeds): -218 -> +5; three flipped to wins; one
holdout worsened (304: -20 -> -25).
DISCIPLINE: selection-tainted by construction -> FULL 120-fresh validation RUNNING (4 chunks, arms
cong_l2on/urg8/sq5/sqp15). Adopt only if the general marginal holds without robbing the winning seeds.

## 2026-07-22x — Checklist pruned (user): sync-up parked block REMOVED, delay head REMOVED from plan.
Sync-up upgrades (global matching / convex sync / accumulated stall) deleted from the checklist --
largely superseded: matching's premise was weakened by both lookahead grids and the joint-first-moves
null; the rest were never-tested micro-knobs. Recoverable from git/NOTES history if ever wanted.
Delay head formally removed; Stage-3 learned slot reassigned to the PACE MODEL. Fidelity boxes checked
with verdicts (bias=engine +6.9; pickers/freed-pos=passengers).

## 2026-07-22y — Warm-start KILLED (user); branch-width experiment running with striking interim.

WARM-START constant (BIAS_PRIOR=15) abandoned per user before its 120-validation completed (chunks
orphaned at ~21/30 in a session restart; partial data in results/warm_[abcd].out, unread). It was never
deployed (shipped sq5 runs BIAS_PRIOR=0). The OPENING COLD-CLOCK problem it addressed (8/8 worst error
seeds diverge at t=0 while the pace EMA is uninitialized; targeted check showed -218 -> +5) REMAINS
OPEN; its designated fix is now solely the PACE MODEL (day-long pacing profile across warehouse
conditions), not a hardcoded constant.

BRANCH-WIDTH screen (user: 'try without the Manhattan screening, all tasks'): sqwide = simulate all 15
finalists (was top 5); sqall = no screen at all, every candidate simulated (~25/decision; episode cost
only 3.1s -> 4.2s). INTERIM n=11: sq5 +9.55 over urg8 | sqwide +15.55 (+6.00 over sq5!) | sqall +16.18
(+6.64). Zero ties. If it holds at 30: the funnel's top-5 was STARVING the simulator of its best
options, and most of the gain is 5->15 (removing the screen entirely adds only ~+0.6 more). UNRESOLVED
-- week's rules apply; do not adopt before full screen + fresh-seed confirmation.

## 2026-07-22z — BRANCH WIDTH: audition all 15 finalists, keep the screen. Confirmation launched.

Full 30-seed screen (user's question: 'try without the Manhattan screening, all tasks'):
  sq5(top-5) +9.47 | sqwide(all 15 finalists) +14.93 (t=3.77, 23-7-0, sign p=0.005)
  | sqall(no screen, everything) +10.33.
MARGINALS: sqwide over sq5 +5.47 (t=1.99, 20-9-1, sign p=0.061) | sqall over sqwide -4.60 with 20/30
EXACT TIES -> the beyond-screen candidates almost never change a pick and slightly hurt when they do.
SPLIT VERDICT (user half-right): the SCREEN is fine (removal no benefit -- consistent with the vscreen
no-op); the TOP-5 CUTOFF into the simulator was the hidden throttle -- funnel ranks 6-15 win the sim
often enough to matter. RULE: let the screen do its job, then simulate everything that survives it.
Cost: 3.1s -> 3.4s per episode. sqall DROPPED. 120-fresh confirmation of sqwide RUNNING (4 chunks,
seeds 200-319, arms cong_l2on/urg8/sq5/sqwide). If it holds, deployed day-list config becomes
champion + urg8 + hi-fi sequencer @ 15 branches.

## 2026-07-22aa — sqwide CONFIRMED + width grid: 15 branches adopted. Stack now +3.3%.

CONFIRMATION (120 fresh seeds): sqwide vs urg8 +9.28 (t=3.24, 83-33-4, sign p<0.00001); width marginal
over sq5 +3.22 (t=1.19 weak mean, but sign p=0.018, 69-43 -- adopted on win-rate + topline). Usual
screen->confirm halving (+5.5 -> +3.2).
WIDTH GRID (30 tuning seeds, vs urg8): 8:+5.3 | 12:+11.7 | 15:+14.9 | 20:+12.3 | 25:+12.9 -> sharp
cliff below 12, FLAT PLATEAU 12-25, 15 nominal peak. Pre-declared rule applied: flat top -> take 15,
stop tuning. Matches the optimizer's-curse account (coverage saturates at the screen's finalists;
wider = noise lottery).
DEPLOYED (day-list): champion + urg8 + hi-fi sequencer @ SEQ_TOPK=15 (SCREEN_KEEP=15 unchanged) =
+12.8 pts (+3.3%) over plain champion on fresh worlds. Note the background-jobs 'stopped' scare:
session restart orphans child processes and loses completion records, but runs write per-seed lines
continuously -- all 6 'stopped' jobs had actually finished; data recovered from files.

## 2026-07-22ab — CLARIFICATION (user question): is the ranker value-rate or plain value?

BY LAYER: funnel score & sim-internal choices = PLAIN VALUE + urgency (rate80 formula dropped --
negative in both realistic regimes). FINAL PICK among the 15 finalists = SIMULATED TOTAL BANKED VALUE
over the remaining day -- which IS value-per-robot-minute optimization, computed correctly instead of
by formula.

WHY THE FORMULA DIED AND THE IDEA LIVES: rate80 priced time at a FIXED exchange rate (a saved minute
always worth the same) -- right in a bottomless queue (uniform, +10.8 confirmed), wrong when the day
runs out of work (day-list, negative). The simulation prices time CONTEXTUALLY: it saves the minutes
in imagination and watches what the rest of the imagined day buys with them -- another task in a rush,
idle standing at day-end. The sim agrees with the rate formula exactly when the formula is right and
disagrees exactly when it is wrong.
ONE-LINER: the wage (value/robot-minute) was always the right objective -- the FORMULA assumed the
wage rate; the WORLD MODEL looks it up. The user's wage argument was correct economics; a static
scorer was too crude an instrument to hold it.

## 2026-07-22ac — OPEN-LOOP EXPERIMENT: the re-planning benefit isolated. +11.3 (t=3.75, sign p=0.004).

User caught that the imagined-vs-real GIF conflated forecast error with re-planning value and that
commit-the-whole-branch was never actually tested. Built _OpenLoop: compute the winning branch, extract
its FULL per-robot schedule (owner-tagged sim traces), execute WITHOUT re-scoring; re-plan only when a
robot's scripted task is unavailable or its script runs out.
30 daylist seeds, paired: closed (sqwide) 406.0 vs open 394.7 -> RE-PLANNING BENEFIT +11.30 (t=+3.75,
22-6-2, sign p=0.00372) -- both instruments significant at n=30 (effect cleared the +8 bar).
CONTEXT ROW: open-loop vs urg8 (no lookahead) = +3.63 n.s. => THE PLAN IS WORTH ~NOTHING; THE
RE-PLANNING IS WORTH ~EVERYTHING (blind execution discards ~3/4 of the sequencer's value). Mechanism:
scripts break constantly -- seed-3 probe: 7 scripted follows vs 12 forced re-plans; the committed plan
cannot stay executable for two decisions on average. GIF: results/openloop.gif (real closed vs real
open curves, re-plan ticks). Bertsekas's receding-horizon prescription now has a clean in-house
measurement; the earlier +10.7 imagined-vs-real figure is superseded for this purpose (it bundled
forecast error).

## 2026-07-23 — Map-off ablation: does the sequencer make the congestion map redundant? (user question)
User asked: the sequencer already simulates all tasks with the deadline filter — do we still need
the congestion map? Noted blind spot: the map's value (+3.4 uniform / +1.4 stream weak) predates
the sequencer and was NEVER measured on day-list. Built _NoMap = full deployed stack (sqwide)
minus every map touchpoint: forecast grid, congestion-weighted route pick + reroute, and adherence
(adherence without the map measured harmful long ago — rush_yen). 30 seeds day-list, paired.

| arm | vs champion | nomap − sqwide |
|:---|:---:|:---:|
| sqwide (map on) | +22.0 | — |
| nomap (map off) | +14.6 | −7.46 (t=−1.10, 10W/14L, sign p=0.54) |

Mean n.s. — but the distribution is the story: 29/30 days the map is worth ~nothing (mean without
seed 19 ≈ −1.6 ≈ 0), and on seed 19 map-off collapsed the fleet: 29 deliveries vs 53, value 245
vs 422 (−177). Both map-on arms fine on that seed. Throughput halved = gridlock day, exactly the
reroute-storm mechanism the map was built for (p90 reroute −24% in original measurement).
VERDICT: the map is not a ranking device (sequencer owns that) — it is INSURANCE against rare
gridlock, ~1-in-30 days at ~−180. Expected value ≈ its small mean. KEEP. Conceptual note logged:
the imagination contains zero traffic, so the map is the only traffic awareness in the system;
the two are orthogonal (task choice vs road choice).

## 2026-07-23 — Where the sequencer sits relative to AlphaZero / MuZero (user Q&A)
Same skeleton: pick the move whose IMAGINED continuation scores best, commit one move,
re-imagine from scratch every decision (receding horizon). Mapping:
| ours | AlphaZero/MuZero equivalent |
|:---|:---|
| champion funnel shortlist (15) | policy network narrowing the search |
| one straight-line imagined day per candidate | MCTS tree with thousands of guided visits |
| known handwritten dynamics + measured delay bias | AlphaZero: known game rules; MuZero: fully LEARNED dynamics |
| traffic/clocks as "opponent" | adversarial opponent |
Our version is the textbook "rollout" (Bertsekas) — the ancestor MCTS was built on.
Key shared property (user articulated it): the model is NOT reliable in details — all sketches
are wrong roughly the same way, so only the RANKING is trusted, and only for one step
(bathroom-scale-5-lbs-heavy analogy: wrong number, right comparison). Measured: imagined day
off by ~10 pts absolute, yet first-move ranking earns real +3.3%.
Planned pace model = one small step from the AlphaZero end (handwritten model) toward the
MuZero end (learned model): learn how days tend to unfold instead of hand-measuring slowness.

## 2026-07-23 — How the single playout per candidate is chosen (user Q&A)
It is not sampled or searched — it is the deterministic "everyone plays the champion" future:
pin the candidate as my first move, fast-forward; every imagined robot that frees up picks via
the same funnel rules (makeable-first, prize order, urg8) on the queue AS IT STANDS at that
imagined moment, travel = pocket-calculator math + measured slowness pad. No randomness: same
snapshot -> same sketch. Textbook rollout (Bertsekas), with the classic guarantee: rollout over
a base policy is at least as good as the base policy — the +3.3% is that guarantee cashed.
Deliberate omission: imagined robots use the cheap rules, NOT the sequencer (no nested
imagination — 15x cost per level for detail we wouldn't trust).

## 2026-07-23 — Delay autopsy GIF: WHERE the ~15-step pad actually comes from (user request)
Built scripts/viz_delay.py: champion+urg8 on 10 day-list seeds with a per-step execution tracer.
Every task logs (commit step, predicted finish) at _on_predict, then position+carrying each step
until delivery; actual time split into named segments (moved / stationary-at-shelf-unloaded /
stationary-mid-route / stationary-carrying-near-dock). Output results/delay_causes.gif.

256 tasks / 10 seeds, mean delay vs estimate = +16.0 steps/task — independently confirms the
honest clock's EMA (~15.8) with a completely different instrument. Per-seed means +11..+21, ALL
positive: the delay is universal, not a crater artifact. Cause table (mean steps/task):

| cause | steps | note |
|:---|:---:|:---|
| picker wait (stationary at shelf, unloaded) | 16.5 | THE DOMINANT CAUSE (est's wait+load pad absorbs ~10 of it) |
| traffic block (stationary mid-route) | 7.4 | the map's domain |
| dock queue (stationary carrying, <=2 of dock) | 1.6 | minor |
| drive beyond straight-line (detours) | +1.0 | Manhattan is nearly exact — routes barely detour |

HEADLINE: the delay is NOT mostly traffic — it's mostly WAITING FOR PICKERS (4 pickers vs 8
AGVs; you arrive, the shelf can't load until a helper walks over). Traffic is the #2 cause at
less than half the size. Squares with the earlier ablation: modeling pickers in the sim was a
passenger (+0.13) because the honest-clock pad already absorbs the AVERAGE picker wait; but this
now names picker availability as the prime feature family for the future pace model (and explains
the occasional +140 outlier task: a shelf that waited an age for any free picker).

## 2026-07-23 — Block autopsy: what's actually inside the 7.4-step "traffic block" bucket
scripts/viz_blocks.py: every stationary mid-route step classified by inspecting the wanted
square's occupant at the moment the move was denied (10 seeds, 256 tasks, ~1,844 stopped steps).
Env fact verified first: AGVs and pickers are on SEPARATE collision layers — helpers can never
physically block carriers; all blocks are AGV-vs-AGV. Output results/block_causes.gif (real
5-step standoff animated on the grid + aggregate chart).

| cause | steps/task | share | note |
|:---|:---:|:---:|:---|
| turning in place | 4.3 | 59% | NOT congestion — rotation steps Manhattan ignores; deterministic geometry |
| mutual yield / standoff | 2.2 | 30% | brief two-robot simultaneous-request resolutions |
| crossing traffic | 0.4 | 5% | blocker passing through, gone within a step |
| stopped loaded carrier (chain) | 0.2 | 3% | queue behind a stopped hauler |
| parked-for-helper + dock spill | ~0.1 | 1% | negligible |

Chained blocks (blocker itself blocked): 2% of events — NO gridlock on normal days. So genuine
congestion on a typical day is ~2.8 steps/task; the biggest "traffic" cost is TURNING, a
per-route computable constant (count the corners), currently absorbed by the honest-clock pad.
Squares with the map-off ablation: the map buys nothing on 29/30 days (there's almost no real
congestion to dodge) and everything on the rare cascade day (seed 19) — insurance, not a
daily-traffic tool. Also consistent with delay-oracle null: per-task wiggle beyond the pad is
mostly turn-count variation + brief standoffs, worth +0.4 even when known perfectly.

## 2026-07-23 — Pace model STEP 1 (offline physics validation): premise FAILS at task level
User directed: start the pace model, physics-based (read the trajectory from mechanics, adapt).
Built scripts/pace_physics.py: 11 seeds (0-9 + crater seed 303), 279 tasks. Tested: does
turns + picker-queue-physics(contention) predict per-task delay better than the trailing EMA?

RESULT 1 — contention carries NO per-task signal. corr(pick-wait, X): inflight at commit -0.05,
at arrival +0.03; free pickers -0.05; queue len +0.10. The funnel's own sync estimate (est_wait,
+0.29) is already the best available signal. Per-task wait is decided by fine assignment
structure, not by counts — same lesson as the delay heads.

RESULT 2 — per-task |error|: trailing EMA 16.09 (the WORST), flat constant 13.17, flat+turns
12.81. The deployed EMA is a bad per-task predictor yet earns +6.9 in value: its value channel
is LEVEL-SETTING (shared pessimism that shapes rankings), not per-task accuracy.

RESULT 3 — seed-303 surprise: its OPENING truth is only +4.8. Bias-0 (EMA cold read) was nearly
RIGHT; the killed warm start (+15) was factually WRONG (physics +19.5, wronger still) — yet warm
start fixed the crater (-218->+5). So the cold-open rescue was not a calibration fix. Hypothesis:
the bias is really an OPTIMISM/PESSIMISM KNOB — bias 0 makes the imagination believe every
far-future banking, deferring urgent value; pessimism discounts far-future banks and secures
near-term value. A value-level mechanism, not a forecast. (8/8 error seeds fixed by pessimism is
too many for coin flips.)

NEXT (running): the decisive value test — does the EMA's TRACKING add value over a fixed
calibrated LEVEL? Arm _PaceFlat = sqwide with _sim_delay_bias() = 15.8 always (no EMA). If flat
matches sqwide and fixes 303, the pace model's real job is choosing the LEVEL (incl. opening),
not tracking drift.

## 2026-07-23 — Pace model, CORRECTED altitude: physics predicts the LEVEL, not the task (user)
User correction: never asked for per-task delay — asked for a physics estimate of the AVERAGE
pick-wait/pace that reads the trajectory. Per-task corr ~0 does NOT preclude a level signal;
averaging over a time window cancels the micro-noise. Retested at WINDOW altitude
(scripts/pace_level.py, 30 seeds + 303, 40-step bins, leave-one-seed-out so physics never sees
its own day). Features = mean board contention per window (inflight-unloaded, free pickers,
queue len, delivery rate).

WINDOW-LEVEL |error| (steps):
| predictor | overall | OPENING (cold) | ACCELERATING |
|:---|:---:|:---:|:---:|
| lagging EMA (deployed) | 13.20 | 21.10 (reads 3.1, truth 23.7) | 22.06 |
| PHYSICS (contention) | **8.70** | **8.59** | **12.52** |
| flat global constant | 9.65 | — | — |

Physics cuts pace error ~34% overall, ~60% at the cold open (the seed-303 disease), and clearly
tracks accelerating rushes the rearview-mirror EMA lags. Window corr with truth: free_pk +0.25,
qlen +0.26 (vs per-task +/-0.10 — averaging exposed the level). VINDICATES the user's thesis.

Supporting value fact: killing EMA tracking entirely (_PaceFlat, fixed 15.8) costs -6.65 over 30
seeds (hurts 19/30, -122 on seed 10) — so pace TRACKING is worth real value; the only question is
whether physics tracks better than the EMA in VALUE terms.

BUILT _PacePhysics: _sim_delay_bias returns beta.contention (beta FROZEN from seeds 0-29 fit),
clamped [0,45]. Value confirmation running on HELD-OUT seeds (30-59) + crater block (294-313).
Adoption gated on that, not on MAE.

## 2026-07-23 — Physics pace model: VALUE VERDICT = NULL (well-diagnosed). Do not adopt raw.
Built _PacePhysics: _sim_delay_bias returns beta.contention (beta frozen on seeds 0-29), clamped
[0,45]. Held-out VALUE (seeds 30-149, 120 unbiased):

| test set | pacephys - sqwide | note |
|:---|:---:|:---|
| unbiased 120 (30-149) | +1.73 (SE 2.15, t 0.81, p 0.78, 55W/59L) | NULL |
| crater block (294-313) | +11.37 (13W/7L) | rescues known craters (303 +83, 312 +46) |
| general 30-59 | -3.40 (n.s.) | slight cost on ordinary days |

Offline pace-accuracy: physics 8.70 vs EMA 13.20 window MAE (-34%), cold open 8.6 vs 21.1 (-60%).
So a 34% better pace forecast bought ZERO value. Diagnosis (the payoff):

ROOT CAUSE — the delay pad is a RISK-POSTURE knob, not a forecast. Decomposed the opening bias on
seed 303 (physics RESCUES, +83) vs seed 55 (physics CRATERS, -92): both have near-identical
opening contention (qlen~25, inflight~6, free_pk small) so physics reads BOTH at ~+22-28. Same
pessimism, opposite value outcome. More pessimism secures near-term value & abandons tight tasks;
whether that helps depends on each day's task structure, which contention CANNOT see. Value
depends on POSTURE; contention predicts LEVEL; level != posture except trivially. That is why
better pace accuracy did not convert.

Secondary: raw physics is high-variance at the open (clamps to 45 on busy days -> imagination
declares everything doomed -> deadline-chase collapse = the seed-55/141 new craters). A CONSTANT
warm-start (killed earlier) is strictly more robust at the open than physics, and physics does not
beat it. Mid-day drift that physics tracks better is a regime the value function is ~insensitive to.

STATUS: _PacePhysics, _PaceHybrid, _PaceFlat retained as arms; NONE adopted. The pace-model premise
(predict pace better -> more value) is FALSIFIED in the deployment regime. The only residual signal
is cold-open pessimism (any nonzero > EMA-0), best served by a robust constant, not physics.
Open question for user: pursue posture-selection (a DIFFERENT target than pace) or shelve.

## 2026-07-23 — Posture sweep + the JAGGED SURFACE finding (resolves the whole pace saga)
User: "do the posture thing on day-list just to see." Built _Post0.._Post30 (fixed pad = posture
knob, low=optimistic/chase-far, high=pessimistic/secure-near) and swept, computing per-day VPI.

Coarse sweep (grid 0..30):
| set | best single posture vs EMA | per-day ORACLE (VPI) | best-posture spread |
|:---|:---:|:---:|:---|
| general 0-29 | p24 -1.6 (none beats EMA) | +10.6 | scattered p0..p30 |
| crater 294-313 | p18 +25.7 | +33.1 | centered p18 |
seed 303 by posture: p0=213 p6=428 p12=453 p18=458 p24=453 (EMA=219). Cold-open crater = LOW
posture (optimism) systematically; ANY mild pessimism rescues it.

THEN caught a contradiction: _PaceFlat(15.8)->303=217 but post12/post18->453/458. 15.8 is BETWEEN
12 and 18 yet 240 pts below both. Fine sweep on 303 revealed WHY -- the value(posture) surface is
VIOLENTLY JAGGED:
  bias:  10  12  14  15  15.5  15.8  16   16.5 17  18  20  24
  val:  453 453 458 451  205   217  222  444 453 458 302 453
Razor-thin craters at 15.5-16 and at 20; peaks ~455 either side. _PaceFlat's 15.8 fell in a
crater by luck. => the earlier "_PaceFlat doesn't fix 303" conclusion was CONTAMINATED (bad-luck
sample), not evidence about flat-vs-EMA.

Universality check (fine sweep, general seeds): spreads seed0=50, seed1=23, seed7=23 (SMOOTH),
seed4=164 (narrow crater at bias 18). So:
- MOST days: posture is a smooth, forgiving knob; exact value ~irrelevant; mild pessimism ~12-14 broadly good.
- ~10-20% of days: a NEEDLE-NARROW crater at a per-day-random posture (pivotal task tipped across
  the makeable/doomed cliff -> cascade). Same chaos as per-task delay, unpredictable.

UNIFIES the whole saga:
1. Why physics pace craters (seed 55/141): a continuous predictor can land IN a narrow crater on
   the wrong day. Precision is a LIABILITY on a cliff-riddled surface.
2. Why no smooth posture predictor captures the +10-33 VPI: the VPI is real but the good postures
   are needles between craters; predicting the region isn't enough, a 0.5-step error tips the cliff.
   The best-of-grid oracle also INFLATES VPI by cherry-picking non-crater grid points.
3. Why the cold open is special & FIXABLE: low posture (0-8) is a BROAD, SYSTEMATIC bad region
   (optimism defers urgent value), not a needle -- so a posture FLOOR robustly fixes it.
ACTIONABLE next idea (not built): posture ENSEMBLE -- score each candidate at several postures
(e.g. 10/14/18) and average, so no single per-day crater dominates. This is the session's core
lesson (average beats the point estimate) applied to the posture knob instead of to delay.

## 2026-07-23 — Value-loss autopsy (user: "biggest causes of LOSS of value, not delay")
Built scripts/viz_value_loss.py -> results/value_loss.png (3 graphs). Per-ORDER accounting (orders
batch on shelves, each its own value+deadline). On day-list all orders visible at t=0, so
"unmakeable" is planner-independent: deadline < best physically-possible delivery from t=0
(geom_completion, robots at start). Every non-banked order -> exactly one bucket. 10 seeds, champ+urg8.

KEY DISTINCTION (why this differs from the delay autopsy): value is lost ONLY at deadline cliffs.
Most delayed tasks bank full value (had slack). So the money picture != the steps picture.

| bucket | $/day | share of potential | addressable? |
|:---|:---:|:---:|:---|
| banked on time | 384 | 91% | — |
| doomed from start | 0 | 0% | no (but there's none) |
| missed at the cliff | 30 | 7% | YES — execution delay |
| never served | 10 | 2% | YES — capacity/sequencing |

HEADLINES:
1. We bank 91% of all potential value. Total leak is ~9% (~40/day), and NONE of it is
   truly impossible ("doomed from start" = 0: from t=0 everything is reachable in time). So the
   whole gap is in-principle addressable — but recall the oracle already showed only ~1.5% is
   actually capturable above the stack, so most of this 9% is addressable-in-theory / traffic-noise
   in practice.
2. Of the cliff loss (the execution slice, 30/day): 75% is PICKER WAIT, 25% traffic block,
   0% dock queue. Same verdict as the delay autopsy in a different currency — the binding
   constraint is picker availability (4 pickers : 8 AGVs), not congestion.
3. Never-served (10/day) is NOT dominated by cheap orders — high+mid tiers each ~4/day, low ~2.
   The capacity limit drops valuable orders too, so it's not simply "we correctly skipped junk."

IMPLICATION: both instruments (steps and dollars) now point at the same lever — pickers. The map
governs only ~25% of the addressable cliff loss (~7/day); picker rendezvous governs ~75% (~22/day).
Strengthens the pace model's feature priority (picker-availability trajectory) and suggests the one
structural knob worth a real experiment is the AGV:picker RATIO, which no controller change can move.

## 2026-07-23 — AGV:picker ratio sweep, 30-seed confirmation (user: prove picker is the constraint)
Built scripts/exp_ratio.py + exp_ratio_plot.py -> results/ratio_sweep.png. Value-loss autopsy across
8 robot configs, 30 day-list seeds each, demand fixed (potential 431/day always). Env ids
pre-registered for any AGV(1-19)/picker(1-9) count. VERDICT: picker availability confirmed as the
binding constraint on value.

PICKER sweep (fixed 8 AGV) -- add pickers, loss collapses:
| cfg | banked | picker-wait | traffic | never-served |
|:---|:---:|:---:|:---:|:---:|
| 8x2 | 350 (81%) | 25 | 4 | 52 (starvation) |
| 8x4 | 391 (91%) | 25 | 4 | 10 |
| 8x6 | 399 (93%) | 13 | 8 | 10 |
| 8x8 | 400 (93%) | 15 | 10 | 5 |

AGV sweep (fixed 4 pickers) -- add AGVs, loss barely moves:
| cfg | banked | picker-wait | traffic | never-served |
|:---|:---:|:---:|:---:|:---:|
| 4x4 | 365 (85%) | 23 | 12 | 30 |
| 6x4 | 388 (90%) | 21 | 11 | 11 |
| 8x4 | 391 (91%) | 25 | 4 | 10 |
| 10x4 | 393 (91%) | 20 | 4 | 14 |

SIGNATURE (all three are the picker-bound fingerprint):
1. LEVER ASYMMETRY: pickers 2->8 lift banked +50 (350->400); AGVs 6->10 lift banked +5 (388->393).
   ~10x more value per picker added than per AGV added.
2. PICKER-WAIT tracks PICKER supply, not AGV supply: falls 25->13 as pickers 4->6; flat ~20-25
   across 6/8/10 AGV at fixed pickers.
3. FAILURE MODE SHIFTS with scarcity: too few pickers (8x2) -> never-served explodes to 52
   (can't even reach shelves); adequate pickers -> residual is picker-WAIT at the cliff.
4. SATURATION ~6 pickers for 8 AGV (8x6~=8x8; traffic RISES at 8x8 from crowding). Sweet spot
   ~1.3 AGV:picker vs shipped 2.0. NOTE: ratio change is a STRUCTURAL/hardware lever, not a
   controller change -- out of scope for the planner but frames the ceiling.

IMPLICATION FOR PACE MODEL (confirmed go): the quantity worth predicting from live state is
picker-driven rendezvous delay. Feature families: free-picker count + geometry, AGV:picker
contention (busy-AGV:free-picker), day-arc position. On day-list demand is known, so pace ~= picker
physics almost entirely. Reroute only addresses the ~25% traffic slice; picker delay is fixed by
better TASK CHOICE (honest makeable/doomed) + ratio, not steering.

## 2026-07-23 — PACE MODEL: offline results + the feature idea (user recap)
Built the pace model = a STATE-CONDITIONAL replacement for the sequencer's flat-EMA delay bias
(_sim_delay_bias). Two variants trained on 120 day-list seeds (3066 delivery rows, realized delay
mean 17.2, std 17.9):
  - PACE-PICKER   : picker-availability state only (q_per_agv, q_size, busy_frac, free_pk_frac...)
  - PACE-COMBINED : picker + DIURNAL day-curve (day_frac, sin_t, cos_t) + traffic (delay_ema,
                    deliv_rate, dur_trend, dur_recent). <-- the "combined for demand" model.

OFFLINE delay-prediction (20% holdout), MAE:
| model | MAE | vs EMA |
|:---|:---:|:---:|
| predict-0 | 17.88 | — |
| predict-mean (flat const) | 13.17 | +15% |
| EMA (incumbent, live) | 15.58 | — |
| PACE-picker | 12.57 | +19.3% |
| PACE-combined | 12.39 | +20.5% |

KEY POINTS:
1. Both pace models beat the incumbent EMA by ~20% MAE. Combined slightly beats picker (12.39 vs
   12.57) -- comparable, combined marginally ahead. Comparable-or-slightly-better is the goal:
   the combined model carries the diurnal signal we NEED for the demand/stream regime to generalize.
2. THE FEATURE IDEA (user framing): triangulate delay from (a) day-curve POSITION -- encodes both
   where the day has been and where it's going -- plus (b) picker contention. Combined's top gain%:
   day_frac=33, dur_recent=14, delay_ema=11, dur_trend=10, q_per_agv=9, sin_t=8. So ~41% of the
   signal is the day-arc (day_frac+sin_t) = ANTICIPATION the lagging EMA structurally cannot do.
   Picker model leans on q_per_agv=56 (queue-per-AGV contention) + q_size=22.
3. Notable: predict-MEAN (flat 17-ish constant) beats the live EMA offline (13.17 vs 15.58). The
   EMA's lag/noise makes it WORSE than a constant at forecasting -- a flat-constant bias arm is a
   cheap thing to also try in the online ranking.
4. STATUS: offline gate PASSED. Online 30-seed paired ranking (sqwide=EMA vs pacepick vs pacecomb,
   sqwide=sanity anchor) RUNNING -- online value is the real verdict; offline accuracy has
   historically NOT converted to value here (per-task delay head: perfect knowledge worth +0.4).
   Graph (offline accuracy + online value vs EMA) pending the online numbers.

## 2026-07-23 — PACE MODEL online ranking (day-list, 30 paired seeds) + graph
results/pace_vs_ema.png (2 panels: offline MAE win, online value null). Old=sqwide (flat EMA),
new=pacepick/pacecomb. Means: sqwide 405.9, pacepick 405.5, pacecomb 407.1 (champion 383.9).

| vs sqwide (EMA) | mean Δ | t | sign |
|:---|:---:|:---:|:---:|
| pacecomb − sqwide | +1.12 | +0.31 | p=1.00 |
| pacepick − sqwide | −0.40 | −0.11 | p=0.20 |
Sanity anchors hold: sqwide +22.0 / pacecomb +23.1 over champion (both t>5).

VERDICT: on day-list the pace model is a NULL-BUT-NOT-WORSE lateral move. The +20% offline MAE
win did NOT convert to value -- same disconnect as the per-task delay head (perfect knowledge
worth +0.4). WHY expected: day-list demand is fully known, the flat EMA already captures the
day-average, and the bias is one scalar applied uniformly to all 15 imagined futures (moves the
makeable/doomed threshold, does not re-rank candidates). So a better central delay estimate has
almost no channel to change the first move here.

NOT A FAIL (user frame: "comparable is good, slightly better is good, we were falling behind"):
pacecomb is +1.1 (n.s.) and carries the diurnal day-curve signal (day_frac+sin_t ~41% of model)
that the picker-only and EMA versions lack. That signal is INERT on day-list (arrivals all at t=0)
but is the whole point on STREAM, where arrivals FOLLOW the diurnal curve. So day-list
comparable-not-worse = green light to test pacecomb on the stream, its actual home.
NEXT: run pacecomb vs sqwide vs champion on STREAM (the regime the diurnal feature targets).
Also cheap: a flat-constant bias arm (predict-mean beat EMA offline 13.2 vs 15.6).

## 2026-07-23 — "Redundancy" explainer GIF (user request)
scripts/viz_redundancy.py -> results/redundancy.gif. Defines the redundancy that makes the pace
model's diurnal/clustering feature value-neutral on day-list. Same real orders (seed 4, 65 orders)
in both panels; deadline-clustering curve IDENTICAL; only VISIBILITY differs:
- DAY-LIST: every deadline visible at t=0 -> the planner can DERIVE the clustering itself ->
  a clustering feature is REDUNDANT (adds nothing it doesn't already simulate against).
- STREAM: a deadline is hidden until its order arrives -> clustering ahead is NOT derivable from
  what's visible -> a FORECAST of it (from the day-curve) is genuine new info = INFORMATIVE.
Redundancy defined: a feature helps only if the planner cannot already derive it from what it holds.
This is why direct-deadline-density would likely stay a lateral move on day-list but should pay on
stream. Companion to pace_vs_ema.png.

## 2026-07-23 — Per-completion pace bias ("split all the way") 3-way ladder (user request)
Built the per-completion state-conditional bias: _sim_step_bias(t, npending, pickers) hook in
_sim_core (default returns the flat _const_bias -> all existing arms bit-identical, sanity sqwide
still 484/505). Override _PaceStepMixin/_SqPaceStep evaluates a compact sim-reconstructable model
(pace_sim.pkl: sin_t,cos_t,day_frac,q_size,q_per_agv,free_pk_frac; MAE 12.50 = +19.8% vs EMA;
day_frac 41% + sin_t 19% + cos_t 14% dominate) at EACH imagined completion from the imagined fleet
state, memoized by (t//6, npending, n_free). New arm _SqWideNB = wide + SIM_BIAS off (no delay).

30 day-list seeds, the ladder:
| arm | banked | vs prev |
|:---|:---:|:---:|
| no-delay (fantasy clock) | 400.5 | — |
| flat-EMA (deployed) | 405.9 | +5.43 (t=2.17, W/L 19/9, sign p=0.087) |
| per-step (split all the way) | 404.1 | -1.89 (t=-0.50, W/L 13/16, sign p=0.71) |
All +16.6/+22.0/+20.1 over champion (t>4).

VERDICT: adding delay helps (no-delay->flat +5.4); SHARPENING delay does not (flat->per-step -1.9,
null, slightly negative). The per-completion/time-varying version -- the user's proposed fix, which
IS non-redundant in principle (rollout's cheap clock doesn't otherwise slow completions in an
imagined rush) -- is still value-neutral on day-list. Redundancy runs one level deeper: the
makeable/doomed STRUCTURE the delay feeds is already fully determined by the explicit deadlines the
imagination simulates against. Confirms day-list is the wrong regime to prove the pace model; the
test is the stream. NEXT: build the honest WHY explainer (measured value vs fixed-bias curve:
climb=engine, plateau=why sharpening~0, downslope=why overshoot loses) + take per-step/combined to
the stream.

## 2026-07-23 — WHY the delay bias is value-neutral to sharpen (honest explainer)
First attempt (synthetic misclassification metric) MISFIRED: gave b*=0, implying no-bias is best,
which contradicts the confirmed engine result -- DISCARDED (dominated by the many on-time tasks).
Second attempt (measured value vs fixed-bias curve, 12 seeds) too NOISY: between-seed variance
SE~25 >> bias effect; even paired/centered it's jagged (peaks at 15 AND 24, dips at 6/18/28) -- 12
seeds can't resolve it. Did NOT ship dramatic plateau annotations onto noise.
SHIPPED: results/why_negative.gif -- the makeable/doomed CLIFF-SLIVER mechanism, grounded in 427
real committed tasks (slack = deadline - empty-world finish on x; dot color = TRUE on-time outcome;
bias line sweeps). The honest why: a bias flips a task only if its slack ~ b, so only a thin sliver
can flip; and that sliver is a MIX of truly-on-time (green) and truly-late (red) tasks -- they are
intermixed across ALL slack values -- so NO bias value cleanly sorts them. Sharpening b just
reshuffles the sliver (~0); pushing b too high sweeps genuinely-winnable green tasks into 'doomed'
(abandon -> loss). This is why flat-EMA->per-step was -1.9 and why the measured curve is flat/noisy:
the empty-world finish is a poor enough per-task predictor that delay is not separable at the cliff.
Companion to the 3-way ladder + redundancy.gif + pace_vs_ema.png.

## 2026-07-23 — "How is the cliff-irreducibility supposed to be fixed?" (user Q&A)
Answer: NOT by a sharper delay predictor -- that door is closed (VoPI: true per-task delay worth
+0.4). The green/red sliver mixing is IRREDUCIBLE per-task variance, not a modeling gap. Three real
responses (not predictor fixes), ranked:
1. ABSORB via re-planning -- already deployed; it's WHY the sequencer works. Receding horizon refuses
   to commit to the cliff; reality resolves it, re-decide. Nets +3.3% despite a bad per-task predictor.
2. REDUCE variance at source -- 75% of delay is picker rendezvous (resource contention, not noise).
   Predictable part (shelf-picker geometry) already in the funnel estimate; residual (which picker
   you win / when one frees) is the stochastic part mixing the sliver. Shrink it via picker
   coordination or the AGV:picker RATIO (~10x lever). Don't forecast the wait -- shorten it. Partly
   hardware.
3. CHANGE REGIME -> stream. Day-list has ~1.5% left (over-determined; all deadlines visible), so
   nothing to fix. On stream the uncertainty is UNKNOWN ARRIVALS, not per-task delay; fix = demand
   forecast of clustering + SAMPLED-FUTURES rollout, VoPI-gated (perfect-demand-foresight test first).
Only #3 is unbuilt = the concrete next step. #1 done, #2 partly hardware.

## 2026-07-23 — Deadline-CLUSTERING feature (user's direct-density idea): offline + 30-seed online
Built dl_soon40/80/160 = direct count of pending tasks with deadlines within 40/80/160 steps of now
(near-due density), added to feat dict + _pace_ctx (sanity: sqwide still 484/505, inert). Trained
pace_comb_dl (COMBINED + dl_soon*). New arm _SqPaceCombDL.

OFFLINE (120-seed collection, 20% holdout):
- comb+dl MAE 12.37 vs comb 12.39 = +0.16% (negligible). BUT the model REACHED FOR the new feature:
  deadline-clust total gain 11.9% (dl_soon160=4.7, dl_soon80=4.1, dl_soon40=3.1); it HALVED day_frac
  (33%->18.9%) and near-KILLED the old queue proxy q_size (->1.3%). So the model PREFERS deadline
  pressure over both time-of-day and pile-height -- the user's mechanism is correct -- but on day-list
  clustering is ~deterministic in the clock, so it's a better REPRESENTATION of the SAME info, not new
  info -> MAE flat.

ONLINE (30 day-list seeds, paired):
| arm | banked | vs prev |
|:---|:---:|:---:|
| pacecomb | 407.1 | — |
| pacecomb+dl | 403.0 | -4.08 (t=-0.73, W/L 13/14, sign p=1.00) |
Both +23.1 / +19.1 over champion. NULL: deadline-clustering adds no value on day-list.

VALUE-WEIGHTING discussion (user Q): weighting near-due count by value = "tasks that will actually be
CHOSEN" -- conceptually sharper, BUT the fleet is CAPACITY-BOUND (8 AGV/4 pk work ~8 at a time
regardless of how much valuable work waits), so demand-side value predicts NEVER-SERVED (throughput
shortfall), NOT per-task DELAY (a supply/picker-ratio phenomenon). Value->delay only via spatial
correlation (popular shelves velocity-slotted together -> convergence -> the 25% traffic slice),
already captured by local_density. Verdict: not worth a day-list delay-model run; try on stream or
against a never-served target.

STANDING CONCLUSION: every demand-side clustering feature (deadline count, value-weighted) is
redundant-on-day-list because (a) the imagination already sees all deadlines and (b) the fleet is
capacity-bound. The pace model's diurnal/clustering signal can only pay where demand is HIDDEN = the
STREAM. Next real experiment: pacecomb / pacecomb+dl / pacestep vs champion on the STREAM regime.

## 2026-07-23 — Picker-wait decomposition: is there a cause beyond "not enough pickers"? (user)
Built scripts/viz_picker_wait.py -> results/picker_wait.png. Classified every picker-wait step (AGV
parked on shelf cell, not yet loaded) by picker state: CONTENTION (no free picker & none assigned to
me = all busy), TRAVEL (a picker IS assigned to my cell, still walking), DISPATCH GAP (free picker
exists but not sent). 12 day-list seeds, champion+urg8, at deployed 8x4 and ratio-optimal 8x6.

| cause (steps/task) | 8x4 | 8x6 |
|:---|:---:|:---:|
| contention (add pickers fixes) | 5.4 | 0.4 |
| travel (picker walking = positioning) | 22.7 | 17.2 |
| dispatch gap | 0.0 | 0.0 |

HEADLINE: picker wait is DOMINATED by TRAVEL (picker walking to the shelf), ~80-95% of it. Adding
pickers kills CONTENTION (5.4->0.4) but barely touches travel (22.7->17.2). Cross-validates the
delay autopsy (picker wait ~16-22 steps/task). Worst-banked seeds at OPTIMAL 8x6 are almost pure
travel (crater s8 banked 223 = ~48 steps/task travel). So the residual picker wait -- the bigger
half all along -- is a POSITIONING / JOINT-ASSIGNMENT problem, NOT a picker-count problem, and more
pickers cannot fix it. OPEN LEVERS (genuinely new, unlike the delay-bias nulls): nearest-free-picker
selection; pre-position idle pickers toward demand hotspots; picker-aware AGV task choice (prefer a
shelf with a picker nearby) = the deferred joint AGV<->picker matching (Part D). This is the most
promising open optimization surfaced so far.

## 2026-07-23 — Clustering-ONLY pace (no physics), 60-seed vs EMA (user request)
pace_clust = diurnal (sin_t,cos_t,day_frac) + deadline-clustering (dl_soon40/80/160), NO fleet
physics. Arm _SqPaceClust. OFFLINE: MAE 12.52 = +19.6% vs EMA, ~tied with full combined (12.39) --
pure demand-timing captures nearly all predictable delay on day-list; physics adds ~nothing.
ONLINE 60 day-list seeds (well-powered):
| vs | mean Δ | t | sign |
|:---|:---:|:---:|:---:|
| paceclust − sqwide(EMA) | -0.18 | -0.09 | p=0.89 (27W/29L) |
Both +20 over champion. DEAD-EVEN with EMA (SE 2.14 = confident tie, not underpowered). KEY vs
user's worry: clustering-only does NOT underperform EMA (picker-only slightly did) -> clustering is
the SAFE/useful pace signal, physics is the redundant/occasionally-harmful part. Confirms offline.

DAY-LIST PACE MODEL = EXHAUSTED. Five variants now all value-neutral vs EMA on day-list:
picker(−0.4), combined(+1.1), per-step/sim(−1.9), comb+dl(−4.1 vs comb), clustering-only(−0.18 vs EMA).
Unanimous null for the same two reasons: (a) imagination already sees every deadline (clustering
clock-derivable) and (b) fleet capacity-bound. Offline all beat EMA ~20% MAE; none converts to value.
CONCLUSION: the pace model can only be rewarded where demand is HIDDEN and the fleet is NOT always
saturated = the STREAM. Every day-list run has been the control group. Next: STREAM comparison
(champion vs sqwide/EMA vs paceclust/pacecomb) -- the one regime left to test.

## 2026-07-23 — STREAM comparison: sequencer + pace models vs champion (user request)
30 stream seeds, paired. Arms: cong_l2on (plain champion), sqwide (sequencer+flat EMA),
pacecomb, paceclust (pace models trained on DAY-LIST, deployed on stream).
MEANS: champion 311.6, sqwide 336.7, pacecomb 326.1, paceclust 323.6.

| vs champion | mean Δ | t | sign |
|:---|:---:|:---:|:---:|
| sqwide (seq+EMA) | +25.10 | +3.55 | p=0.099 (20/10) |
| pacecomb | +14.52 | +1.60 | p=0.36 |
| paceclust | +12.08 | +1.40 | p=0.20 |
| pacecomb − sqwide | −10.58 | −1.54 | — |
| paceclust − sqwide | −13.02 | −1.79 | — |

FINDING 1 (NEW, promising): the SEQUENCER beats the plain champion on the STREAM by +25 (+8%,
t=3.55) -- the FIRST thing to beat champion on stream (prior 17+ nulls were SCORERS, not the
sequencer). Re-planning benefit TRANSFERS and may be larger here: the stream world changes (arrivals)
so re-deciding every step has more to react to. CAVEAT: sign test marginal (p=0.099) at 30 seeds;
needs 120-seed confirm before banking.
FINDING 2 (confirms user prediction): pace models do NOT help on stream -- they HURT vs the flat EMA
(−10 to −13). Cause: trained on day-list, deployed on stream = distribution shift; the live EMA
self-calibrates to the current regime, a stale pretrained forecaster loses to an adaptive scalar.
Pace model now NULL-TO-NEGATIVE in BOTH regimes -> flat EMA wins everywhere; pace model = dead end
(unless retrained per-regime, and even then the adaptive EMA is a strong baseline).
NEXT: 120-seed confirm of sqwide vs champion on STREAM (the live positive).

## 2026-07-23 — Picker-unconstrained ORACLE (pickers never absent): 30-seed (user request)
Added env.pickers_free flag (warehouse.py _execute_load): AGV loads instantly on arrival, zero
picker wait (travel AND contention). scripts/exp_picker_oracle.py, 30 day-list seeds, _Urg8.
| | on-time value |
|:---|:---:|
| real 8x4 | 391.0 |
| free pickers | 414.6 |
GAIN +23.6 (+6.0%), SE 2.8, t +8.6, wins 29/30. CAUSE: deliveries 48->49 (FLAT), on-time count
43->47 (+4), value/delivery unchanged. So the picker-wait cost is TIMING (same work finishes sooner
-> beats the cliff), NOT throughput. Since ~80% of picker wait is TRAVEL (picker-wait decomp), most
of this +6% ceiling is unreachable by adding pickers -> it is the PICKER-POSITIONING prize (nearest-
picker / pre-positioning / joint AGV-picker matching). Biggest addressable number of the session.

## 2026-07-23 — Three explainer GIFs (user request): delay causes / small value effect / noise
1. results/gif_causes.gif (scripts/viz_gif_causes.py): builds a task's time budget cause by cause
   (picker travel +13, contention +3, traffic +7, dock +2) with the STRUCTURAL reason each is
   unavoidable (scarce pickers, shared aisles, few docks). Point: delay is structural, not a bug.
2. results/gif_smalldiff.gif (scripts/viz_gif_smalldiff.py): of the day's total value, at a ±14-step
   delay error only ~6% is even IN PLAY at the makeable/doomed cliff (91% locked makeable); within
   that slice on-time & late are mixed so a perfect call nets ~1%. Calculated from 427 real tasks.
   This is WHY a 20%-better delay forecast banked ~0.
3. results/gif_noise.gif (scripts/viz_gif_noise.py): estimate (x) vs actual delay (y) for 427 real
   tasks. A single estimate slice (~44 steps) spans actual delay −5 to +57 -- identical plan, wildly
   different reality, because delay is set by the other 11 AGVs + 4 pickers you don't control. So a
   committed plan aims at a moving target (open-loop −11.3); the cure is re-planning, not a better guess.

## 2026-07-24 — Sources of completion NOISE (user: why can't we get timing right?)
scripts/viz_noise_sources.py -> results/noise_sources.png. Per-task distribution of each delay
component (extra steps vs estimate), 305 tasks day-list:
| component | mean | std | |
|:---|:---:|:---:|:---|
| driving (vs distance) | +0.9 | 1.5 | PREDICTABLE (committed path + Manhattan near-exact) |
| picker wait | +17.3 | 17.4 | THE NOISE (std ≈ mean; spreads 0..60+) |
| traffic yield | +7.3 | 3.8 | moderate |
| dock queue | +1.6 | 2.4 | small |
ANSWER: a committed route fixes DISTANCE (driving std 1.5 = ~deterministic) but not the WAITS. All
completion noise is waiting on OTHER agents: picker rendezvous dominates (std 17.4 -- picker is a
separate robot, dynamically assigned, walking from wherever it is; NOT on your path), then traffic
yielding (must stop for occupied cells), then dock queue. The thing you control (the road) is
predictable; the thing the fleet collectively controls (the waits) is not -> timing is unknowable at
commit -> rollout is for ranking, not schedule. NOTE: the picker-positioning lever cuts BOTH the
delay AND its variance (same root cause). Ties: gif_noise.gif, picker_wait.png, picker oracle +6%.

## 2026-07-24 — Picker path-commit + value-rate scoring, 120-seed (user request)
Refactored _dispatch_pickers to a _picker_score hook. Arms (all on champion+urg8, no pace/sequencer,
so picker change isolated): urg8 (baseline) / _PkCommit (pickers soft-adhere to route, committed_cells
like AGVs) / _PkRate (commit + score serve by value/Tp, Tp=rendezvous+LOAD absorbs both waits, marginal
via taken-set). 120 day-list seeds.
| vs urg8 (395.3) | mean Δ | t | sign |
|:---|:---:|:---:|:---:|
| pkcommit | +0.06 | +0.03 | p=0.77 (dead null) |
| pkrate | +2.58 | +1.92 | p=0.087 (65W/46L, borderline) |
| pkrate − pkcommit | +2.52 | +1.88 | p=0.125 |
FINDINGS: (1) committing picker PATHS = ZERO (pickers weren't drifting harmfully). Drop it.
(2) VALUE-RATE scoring = +2.6 (~0.65%), the FIRST picker-side positive, but BORDERLINE (t just under
2, sign p=0.087) -> suggestive not confirmed by the two-instrument rule. Smoke's +13 was 3-seed luck.
Captures only ~10% of the +6% (~+24) picker oracle ceiling -> the simple per-AGV value-rate leaves
most of the prize on the table. The taken-set only blocks SAME-SHELF overlap, not same-AREA; and the
assignment is greedy-per-AGV, not truly zone/joint. NEXT to strengthen: sweep W_RATE (value-vs-
distance knob); stronger marginal (penalize serving an AREA already covered, not just a shelf); or
joint AGV<->picker matching. GIF: results/picker_zones.gif (marginal spreading explainer).

## 2026-07-24 — Value-loss causes vs picker oracle (user request): results/oracle_gap.png
Per-order value-loss autopsy, 3 arms, 16 day-list seeds:
| arm | banked | picker-wait | traffic | never | doomed | total lost |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| current (urg8) | 394 | 28 | 7 | 8 | 1 | 44 |
| pkrate (value-rate) | 397 | 27 | 5 | 7 | 1 | 40 |
| oracle (free pickers) | 420 | 0 | 13 | 1 | 1 | 16 |
READINGS:
1. picker-wait (28/day) is the dominant addressable loss.
2. pkrate BARELY dents picker-wait (28->27); its +3 banked comes from small traffic/never trims, NOT
   from attacking picker-wait head-on -> confirms value-rate captures ~none of the core picker prize.
3. ORACLE erases picker-wait (->0), banked +26. BUT ~half the recovery leaks into TRAFFIC (7->13:
   free pickers = faster fleet = more crowding) while never-served collapses (8->1). So the NET picker
   prize is ~+26, not the full 28, because removing picker-wait partly converts to congestion.
4. GAP: ~27/day of picker-wait loss still on the table between pkrate and the oracle -> the value-rate
   fix isn't reaching it. The prize needs area-level marginal spreading / joint matching, not the
   per-AGV value-rate, AND will partly re-leak to traffic (the map may need to re-tighten under a
   faster fleet).

## 2026-07-24 — PICKER value-rate distance-sensitivity sweep (RATE_ALPHA): a REAL win
Corrected the knob: W_RATE (a multiplier) is INERT (scale-invariant ranking within a tier). The real
value-vs-distance knob is the distance exponent: picker serve-score = tier + eff_v / Tp^ALPHA.
Swept ALPHA, 60 day-list seeds, paired vs urg8 (391.6):
| alpha | Δ vs urg8 | t | W/L |
|:---:|:---:|:---:|:---:|
| 0.0 (pure value) | +0.9 | 0.31 | 24/33 |
| 0.5 | +3.2 | 1.11 | 30/26 |
| 1.0 (value-rate) | +4.8 | 2.04 | 37/21 |
| 1.5 | +7.8 | 2.88 | 42/14 |
| 2.0 | +8.9 | 3.00 | 42/16 |
| 3.0 | +8.1 | 3.48 | 42/17 |

VERDICT: distance-weighting is a REAL, monotone lever, plateauing ALPHA~2-3 at +8..+9 (~+2.3% over
urg8), significant on BOTH instruments (t~3, sign 42/16 p<0.001). RECOVERS ~+9 of the ~+24 picker
oracle ceiling (~37%). My prior ("reactive score tapped out, need positioning") was FALSIFIED.
MECHANISM: in a SATURATED fleet, minimizing picker TRAVEL beats chasing value -- far valuable AGVs
still get served by whatever picker ends up near them, so serving everyone travel-cheap banks more on
time. Value-chasing made pickers walk past nearby work. NOTE: pkcommit (path commit) still ~0; the win
is the distance-weighted value-rate alone. Set _PkRate.RATE_ALPHA default = 2.0. 120-seed confirm
running (pkrate_sweep_120.log). If confirmed: first real decision-lever win of the picker era, and it
composes with the ~90% still in area-marginal / positioning / more pickers.

## 2026-07-24 — PICKER value-rate α sweep CONFIRMED (120 seeds)
120 day-list seeds, paired vs urg8 (395.3):
| alpha | Δ | t | W/L |
|:---:|:---:|:---:|:---:|
| 1.0 | +2.71 | 2.02 | 69/48 |
| 1.5 | +5.17 | 3.36 | 79/35 |
| 2.0 | +6.10 | 3.60 | 81/36 |
| 3.0 | +6.67 | 4.84 | 82/35 |
CONFIRMED: monotone climb with distance-weight; α=3 best (+6.67 ~+1.7%, t=4.84, 82/35, both
instruments). MORE MODEST than 60-seed teaser (+8.9 → +6.7 = regression to mean; 60s was a lucky
draw). Still the FIRST real picker/decision-lever win of the era. Default RATE_ALPHA set 3.0.
MECHANISM (confirmed by user reasoning): distance-weight = emergent Voronoi zoning (each picker holds
its nearest patch, no zone machinery). Pure value clustered all pickers on the velocity-slotted hot
corner → far zones starved → lost more than the marginal corner gain. Distance breaks the clustering
pull. Gain is ~all TIMING (same serves land earlier → more on-time) + a sliver of never-served rescue
(serve count AGV-capped, oracle 48→49). pkcommit (path pin) = null; the win is distance-weighted
value-rate alone. IMPLICATION: emergent zoning may make explicit area-marginal partly redundant.
OPEN: α still rising at 3 (probe 4-5?); confirm transfers onto the sequencer stack; measure α=3
never-served-vs-cliff split; congestion-aware rate (user idea).

## 2026-07-24 — Picker value-rate: STACKING + FIDELITY (closing the arc)
STACKING (120 day-list seeds): sqwidepr (sequencer + value-rate pickers α=3) − sqwide (sequencer
alone) = +1.40 (t=0.70, 66/46, sign p=0.072). The +6.7 isolated picker win LARGELY OVERLAPS with the
sequencer (~80% redundant): both recover picker-wait cliff-misses (sequencer via AGV task choice +
honest clock; pickers via shorter waits) -> can't rescue the same value twice. On the deployed stack,
value-rate pickers add ~nothing measurable.
FIDELITY (120 seeds): sqwidepr (imagination picker-model ON) − sqwideprnp (OFF) = +0.19 (t=0.34,
10/6, sign p=0.45; identical on 104/120 seeds). The imagination's picker model adds ~0 under value-
rate pickers. WHY (by construction): the sim already (1) reads real picker positions each decision,
(2) selects the SOONEST picker = the value-rate-optimal picker per task, (3) moves imagined pickers to
served cells (emergent zoning), (4) calibrates the mean via live EMA. So it was already value-rate-
aligned; no headroom. My "it'll stack cleanly" prediction was WRONG (2nd wrong picker prediction:
too-pessimistic on the sweep, too-optimistic on stacking).
ARC SUMMARY: value-rate α=3 pickers = a REAL +6.7 (~1.7%) lever on the champion (confirmed t=4.84),
but REDUNDANT with the deployed sequencer (+1.4 n.s.) and needs no imagination changes (+0.19 n.s.).
Net for the deployed system: keep the sequencer; the picker fix is the win you'd want if you DIDN'T
have the sequencer. Default RATE_ALPHA=3 kept (harmless, tiny positive lean). OPEN (unattacked): the
~63% of the picker-oracle ceiling still needs area-level marginal / MORE pickers (ratio) / joint
matching -- levers the sequencer does NOT already capture, unlike the value-rate which it does.

## 2026-07-24 — DIP ANALYSIS overturns the "redundant pickers" conclusion (user's idea)
120 seeds, cong_l2on / sqwide / pkrate(alpha=3), same seeds. Head-to-head: sequencer +15.9 over
champion, picker-fix +10.6; sequencer − picker-fix = +5.36 (t=2.14, p=0.047) -> sequencer is the
bigger single lever. BUT the dip analysis (results/dip_rescue.png) flips the stacking story:
- Sequencer's worst-8 seeds and picker-fix's worst-8 seeds: ZERO overlap. corr of per-seed deltas
  vs champion = +0.25. They CRATER ON DISJOINT SEEDS (different failure modes).
- On the SEQUENCER's 10 worst days, adding value-rate pickers RESCUES +29.0 avg (seed 85 +96, 64
  +47, 42 +37) while being ~flat (−1.1) on good days. corr(seq-vs-champ, picker-rescue) = −0.33.
CORRECTION: the +1.4 stacking "null" was a MISLEADING MEAN -- ~0 on good days, big rescue on crater
days. The value-rate pickers are NOT redundant with the sequencer; they are COMPLEMENTARY CRATER
INSURANCE: the sequencer's failure mode (bad task-choice days) is exactly where the pickers help most,
because those days have a picker-wait pattern the sequencer's task choice can't dodge but shorter
picker walks can. => Deploy value-rate pickers WITH the sequencer for VARIANCE reduction / tail-cut,
not for mean lift. My "redundant, same seeds" call was WRONG (3rd wrong picker prediction); the dip
analysis was the right instrument. This matches the user's earlier tail-cutting intuition exactly.
NEXT: confirm the variance/tail reduction formally (std, worst-decile); pkratenosync (AGV sync off)
test running.

## 2026-07-24 — AGV sync redundant with value-rate pickers (user hypothesis) -- WASH
120 seeds: pkratenosync (value-rate pickers, W_SYNC=0) − pkrate (W_SYNC=0.3) = +0.56 (t=0.48, 59/52,
sign p=0.57). A clean WASH. With value-rate pickers accommodating (coming to nearest AGV), the AGV-side
sync penalty (−W_SYNC*my_wait) is INERT -- drop it, same result, simpler controller. User's "double
accommodation is redundant" = correct; it's inert-redundant (no cost to remove), not harmful-redundant
(removing doesn't free value). 3-seed smoke (−5,−24,−9) was noise. So: value-rate pickers make the AGV
sync term deletable. A cleanup, not a win. (Left W_SYNC in place by default; deletable for the
value-rate stack.)

## 2026-07-24 — PICKER CEILING on the sequencer (user request): picker problem is FAR from solved
results/picker_ceiling.png. 120 seeds, same seeds: champion 391 -> sequencer(stupid pk) 407 (+16) ->
+value-rate pk 409 (+1.4 mean) -> +FREE pickers (zero picker wait ceiling) 420.
| gap | Δ | t | W/L |
|:---|:---:|:---:|:---:|
| picker problem LEFT (ceiling − now) | +11.43 | 5.82 | 94/15 |
| total picker headroom (ceiling − sequencer) | +12.82 | 8.36 | 92/19 |
| value-rate captured (now − sequencer) | +1.40 | 0.70 | 66/46 |
FINDING: the picker problem is NOT largely solved -- +11.4/day (~2.8%) of on-time value still locked
behind picker handling, ~as big as the sequencer's entire contribution. Value-rate captured only ~11%
of the +12.8 total picker headroom; ~89% unclaimed. My earlier "ceiling not far above / largely
solved" was WRONG (narrated from a 2-seed smoke + the misleading +1.4 stacking mean; user pushed and
was right to). The +11.4 lives largely in the crater tail (free pickers rescue more than value-rate).
CAVEAT: free-pk is an upper bound + confounded (sequencer re-ranks under faster physics -> may
undershoot); split of +11.4 between decision-addressable (better 4-picker ASSIGNMENT) vs physics
(more pickers) unknown. But value-rate captured so little that substantial DECISION headroom in picker
assignment is likely. STRATEGIC: picker handling = the biggest remaining lever. REVIVES area-level
marginal spreading + JOINT AGV<->picker matching as the highest-value direction (picker assignment is
a decision axis the sequencer's task-choice doesn't touch and value-rate only nibbled). Corrects the
earlier value-ledger which undercounted decision headroom (that was task-choice hindsight oracle ~1.5%;
picker-ASSIGNMENT is separate and much larger).

## 2026-07-24 — Picker 2x2: HEADCOUNT vs ASSIGNMENT (user 1:1 test). results/ratio_2x2.png
120 seeds, sequencer, demand identical across picker counts (verified potential 490.5/526.9).
|        | 2:1 (8x4) | 1:1 (8x8) |
|:---|:---:|:---:|
| stupid pickers | 407.4 | 417.8 |
| smart (value-rate) | 408.8 | 417.7 |
| (free-picker ceiling) | | 420.2 |
DECOMP: headcount (double pickers) = +8.9..+10.5 (t 4-7). smart assignment @ 2:1 = +1.40 (n.s.).
smart assignment @ 1:1 = -0.16 (t=-0.09, 45/45 -- EXACTLY ZERO). 1:1 vs ceiling = +2.5 residual
(crowding: 16 agents). VERDICT: the picker gap is a HEADCOUNT problem. Smart (reactive) assignment is
a pure SCARCITY PATCH -- worth +1.4 with 4 pickers, worth ZERO with 8. To close the gap you need more
pickers (physics), not a smarter rule.
IMPLICATION FOR AREAS-OF-FOCUS: reactive assignment ruled out as a big lever (this 2x2). Anticipatory
area-focus (use KNOWN future deadlines to pre-position, untested here) is a DIFFERENT lever that could
beat reaction on demand-SHIFT craters -- but its MEAN ceiling is bounded by the assignment lever being
small; it's a crater/VARIANCE play, not a mean gap-closer. Decision layer (sequencer + value-rate) is
NEAR MAXED on the mean; remaining picker gap ~ +9 headcount (hardware) + ~2.5 crowding + ~1.4 assignment
(captured). Recommend: if building area-focus, target the crater tail explicitly + measure on crater
seeds; don't expect mean lift.

## 2026-07-24 — Picker RATE_ALPHA extended sweep 3->8 (user: "go further"): peak at 5
120 seeds, champion base, paired vs urg8 (395.3):
| alpha | Δ | t |
|:---:|:---:|:---:|
| 3.0 | +6.67 | 4.84 |
| 4.0 | +7.50 | 4.20 |
| 5.0 | +7.72 | 3.92 |  <- peak
| 6.0 | +7.54 | 3.84 |
It KEPT CLIMBING past 3 (we'd stopped too early). Monotone 3->4->5, turns down at 6. Peak alpha~5,
+7.7 vs urg8 (~+1 over alpha=3). Default RATE_ALPHA 3->5. Confirms the "order by speed not value"
mechanism holds even harder than we thought -- very heavy distance weighting (Tp^5) still wins because
in a saturated fleet all makeable tasks get served, so travel-minimizing order banks the most on time.
(alpha=8 pending to confirm downslope.) Also: user's AGV-value-rate idea = rate80, already tested --
biggest win in project history (+10.78) but REGIME-BOUND to retired uniform; negative in day-list/stream
(AGVs SELECT from a finite queue, so speed-over-value strands value). Sequencer = its evolved form.

## 2026-07-24 — CORRECTION: alpha sweep is a PLATEAU (5-8), not a peak at 5
alpha=8 landed +8.06 (t=4.33) -- HIGHER than alpha=5 (+7.72). So the curve rises 3->~5 then PLATEAUS
flat through 8 (5/6/8 = +7.7/+7.5/+8.1, differences ~noise at SE~2). My "peak at 5, turns down at 6"
was premature (called it before alpha=8, which bounced back up -- same pre-judging error as the ceiling).
Even alpha=8 (near "pure nearest, ignore value") wins = the strongest confirmation of "serve all -> order
by speed": value-within-makeable is ~irrelevant for pickers. Keeping default RATE_ALPHA=5 (robust
mid-plateau; not chasing the noisy +8.06 extreme). Anywhere 5-8 equivalent.

## 2026-07-24 — PICKER JOURNEY summary graph (user wrap-up). results/picker_journey.png
120 day-list seeds, champion base, vs baseline urg8 (395.3). Demand identical 8x4/8x8 (verified).
| step | value | Δ vs baseline | t |
|:---|:---:|:---:|:---:|
| baseline (stupid pickers) | 395.3 | — | — |
| + commit paths ("make sure") | 395.4 | +0.06 (n.s.) | 0.03 |
| + value-rate α=3 (before) | 402.0 | +6.67 | 4.84 |
| + value-rate α=5 (now) | 403.1 | +7.72 | 3.92 |
| + 1:1 ratio (8 pickers) | 409.9 | +14.55 | 8.29 |
| free pickers (ceiling) | 417.3 | +21.96 | 10.71 |
READS: path-commit = 0 (drop it). Value-rate = the real decision lever (+6.7→+7.7, α5>α3). 1:1 ratio
(headcount) = +14.6, bigger than any scorer. Free-picker ceiling = +22. So value-rate α=5 captures
~35% of the ceiling by decision alone; doubling pickers gets ~66% (hardware); the rest is crowding/
teleport-only. Confirms: decision layer near-maxed on the picker mean; the big remaining lever is
headcount, not a smarter rule. Default RATE_ALPHA=5. Paper updated (§5.12 + principles 8,9).

## 2026-07-25 — pickers-in-map, spread/urgency picker terms, STREAM validation
Guidebook written: docs/STRATEGY_GUIDE.md (plain-language glossary of every strategy + verdicts).

PICKERS-IN-MAP (user idea: pickers were 37.7% of moving traffic, invisible to the forecast). Two arms
already existed (cong_pktraffic = AGVs dodge pickers; cong_picker = + pickers dodge traffic).
 - Champion, 120 seeds day-list: cong_pktraffic +2.00 (t=2.32, sign 55/31/34 p=0.013). REAL but small.
 - cong_picker (full) NOT > cong_pktraffic -> the lever is purely "pickers visible to AGVs"; picker-
   side route/rendezvous dodging adds 0 (picker highways are clear -> speed isn't the problem).
 - MECHANISM: the map works by PHYSICAL steering (find_path avoids real blocking), not by improving the
   ESTIMATE (delay EMA already carries that). Equal-length routes -> identical arrival -> value moves
   only when a jam is physically dodged. (I wrongly called it "inert" on 2 tie seeds; user was right.)
 - Sequencer transfer (sqwideprmap vs sqwidepr, 60 seeds): +2.36 but t=1.01, sign 27/22/11 p=0.57 =
   N.S. Washes on the deployed stack (sequencer already reroutes AGVs). PARKED.

PICKER SPREAD (_PkCovMixin, COV_W=3: dock a rendezvous near an already-committed picker). 120 seeds:
 - 8x4 -0.78 (n.s.), 8x8 +0.79 (n.s.), both-with-urgency slightly negative. DEAD. User's reasoning:
   demand clusters, so crowding = where the makeable value IS, not redundancy; spreading trades a sure
   makeable for a shakier far one. Confirmed.

PICKER URGENCY (_PkUrgMixin: mirror AGV urg8, +8·max(0,1-spare/40) in the makeable tier). The picker
score had NO urgency (user caught this). Value is double-countable for pickers (static; AGV already
chose valuable) but urgency ISN'T (dynamic: slack shrinks while the AGV sits parked waiting -> fresh
info the AGV's dispatch-time urg8 couldn't supply). 120 seeds day-list:
 - 8x4 +2.07 (t=1.74, sign 59/45/16 p=0.20) — drifted +2/+1.1/+3.2/+2.07 across 16/62/91/120 seeds;
   a consistent small positive that never clears significance at 120. UNCONFIRMED, not null, not a win.
 - 8x8 +0.89 (n.s.) — flat when pickers abundant (ordering moot). Both (cov+urg) doesn't beat urg alone.

STREAM VALIDATION (user: apply the fixes to the demand stream; compare sequencer with/without). 60 seeds
each, REGIME=stream, both worlds. Chain champion->+urg8->+sequencer->+value-rate. Graph:
results/stream_stack.png.
 - SEQUENCER TRANSFERS BIG: +14.3 (8x4, t=2.60), +14.5 (8x8, t=2.15) vs champion. Full stack sqwidepr
   +15.8 (8x4, sign p=0.01) / +16.3 (8x8, sign p=0.0004). Comparable to day-list's +16. The rollout is
   the portable win.
 - VALUE-RATE PICKERS DON'T TRANSFER: sqwidepr-sqwide = +1.5 (8x4) / +1.8 (8x8), both n.s. (vs +7-8
   day-list). Not worse, just stops mattering.
 - urg8 (AGV urgency, standalone) flat/neg on stream (-5.2 8x4 n.s., +1.7 8x8). Deployed stack uses the
   sequencer's forward model, not raw urg8, so no cost.
 - urgency-on-stream (sqwideprurg vs sqwidepr): +3.5 (8x4) / +1.8 (8x8), both n.s. Doesn't clearly help.

WHY VALUE-RATE DOESN'T TRANSFER — OPEN. First hypothesis "stream never gives the picker a choice" was
TESTED (diag_queue_depth.py) and REFUTED: P(>=2 AGVs waiting = a choice) ~0.50 in BOTH regimes (daylist
valrate 0.50, stream valrate 0.49). Same opportunity to choose. Likely reason is the loss STRUCTURE
differs (more never-served/doomed-on-arrival on the stream, less picker-wait sitting at a cliff), so a
better picker choice rarely converts to on-time value — NOT YET CONFIRMED. Flagged, not faked.

METHOD NOTE: got burned pre-judging small effects 3x this session (pickers-in-map "inert" on 2 seeds;
urgency "null" at 62 then "significant" at 91 then n.s. at 120). Lesson reinforced: a ~+2 effect drifts
across the significance line below ~150 seeds; report both instruments and don't declare at n<120.

DISTANCE FROM PERFECT (free-picker oracle sqwidefree = pickers never a constraint, instant load).
% below perfect = (oracle - deployed)/oracle, paired by seed. scripts/gap.py.
 - DAY-LIST 8x4 (120s): deployed 408.8, oracle 420.2 -> gap 11.4 = 2.7% below perfect (banks 97.3%).
 - STREAM  8x4 (60s):  deployed 332.4, oracle 370.6 -> gap 38.2 = 10.3% below perfect (banks 89.7%).
 - Stream is ~4x further from perfect than day-list.
KEY: free pickers beat CHAMPION by +54/day on the stream (t=7.3) vs +29 day-list; the deployed stack
beats champion by only +16 in both. So on the stream the picker constraint is the DOMINANT loss, far
more binding than day-list. MECHANISM: stream arrives in BURSTS -> AGVs pile up at shelves faster than
4 pickers can serve -> picker-wait -> missed deadlines; day-list spreads the same work evenly so 4
pickers keep pace. This RESOLVES the earlier open question (why value-rate doesn't transfer to stream):
the stream picker problem is CAPACITY/timing, not ASSIGNMENT. Free pickers (capacity) buy +54, smart
ordering of the 4 real pickers (value-rate) buys ~0 -- during a burst no ordering conjures more picker-
seconds. Can't assign your way out of a capacity shortage. (Cleaner than the refuted "no choice on the
stream" story, and supported by the +54 free-picker gap.) Data-backed hypothesis, not yet fully proven.

## 2026-07-26 — ANTICIPATION / future-demand in the rollout: NULL (all forms)
User idea (Part-C): feed estimated future arrivals into the sequencer rollout so stream decisions
anticipate incoming demand. Machinery already existed (_SA5 = synthetic random arrivals; rollout
consumes them via _future_arrivals). Built two on the DEPLOYED stack (sqwidepr), stream 8x4:
 - sqwideprsa (SA5-style, ONE random future draw/round): 30 seeds, d=-1.4 vs champion, t=-0.22, 15/15,
   sign p=1.0. WASH with HUGE variance (SE 6.1; single-sample swings +92/-42).
 - sqwideprev (DETERMINISTIC expected-demand field + trust knob EV_TRUST=beta; emits phantom orders at
   the expected rate to top-3 hot cells, value=E[v]*beta, deadline=t+E[slack]). 30 seeds stream 8x4:
   beta=0 EXACT tie champion (0/0/30, sanity PASS); beta=0.25 +2.4 (n.s.); beta=0.5 +2.0 (n.s.);
   beta=1.0 -13.0 (10/20, p=0.10 -- over-trust hurts). Early 11-seed +16..18 was OUTLIER-driven (seeds
   8,1) and REGRESSED to +2 at 30 -- did not call it early.
VERDICT: anticipation is a NULL on the current stack in all forms (random sample ~0, mean field ~0,
trust knob doesn't rescue; full trust hurts). WHY: honest clock + reactive re-planning already capture
the available anticipation value (VoPI = day-list - stream is mostly structural, not foresight). MCTS-
style sampling (K futures averaged) was GATED on EV showing a positive -- it didn't -> not worth K x
compute for a cleaner wash. Untested upside = sample-based burst/tail HEDGING the mean field can't
express; VoPI-bounded + speculative; parked, not pursued.
MECHANISM: rollout is non-preemptive -- only FREE robots are (re)assigned at their free-up events
(sim_priority.py:389); committed robots keep their task, so anticipation can only bias FREE-robot
assignments -> ceiling bounded. Our rollout = the "rollout" half of MCTS (1 deterministic forward
sim/first-move); SA5 = 1 MC sample; EV = certainty-equivalent mean.
K-SWEEP (MCTS chance nodes, 30 seeds stream 8x4, true-param ceiling): K1 -15.4, K2 -9.3, K4 -20.0 vs
champion (all NEGATIVE, sign p<0.05). Even the CEILING (perfect params) hurts -> anticipation dead;
empirical (estimate-from-observed) version would be <= this, so not built/run.

QUEUED IDEA (user, 2026-07-26, tired): re-test MCTS but REFOCUS ranking on urgency/deadline, with value
"contingent on capacity" (anticipatory makeable/doomed). ASSESSMENT: (1) premise "foresight helps ~7%"
is weak -- the day-list-stream gap is mostly STRUCTURAL (backlog batching), and all foresight tests
washed. (2) urgency + foresight likely SUBSTITUTES not complements: day-list (full foresight) -> urgency
HURTS (best URG_W=0), so MCTS foresight should make urgency redundant on the stream too. (3) The one new
angle: urgency as robust INSURANCE on top of IMPERFECT foresight, + capacity-aware doomed tier -- both
VoPI-bounded and both need the foresight layer to show life first (it doesn't). NOT worth running until
foresight shows a signal; parked.
RAN IT ANYWAY (user): MCTS K=2 x urgency sweep, 30 seeds stream 8x4 vs champion: URG_W=0 -1.5 (n.s.,
best), URG_W=8 -9.3 (p=0.005), URG_W=16 -14.5. MORE urgency -> MONOTONICALLY WORSE. Refutes "urgency
rescues MCTS." CONFIRMS urgency+foresight are SUBSTITUTES not complements: MCTS supplies foresight ->
urgency redundant/distorting, exactly like day-list (full foresight -> best URG_W=0, urgency hurts).
Unified picture: no-foresight+urgency HELPS (stream champ); foresight(day-list OR MCTS)+urgency HURTS;
foresight any form ties-to-worse than champion. ANTICIPATION DEAD on this stream, all forms/combos.
Also corrected the "reactive re-planning covers anticipation" claim: it's too glib -- reactive is
non-preemptive so latency ~= 1 task (~75 steps) > burst duration (~tens of steps), so reactive DOES lag
bursts. The real reasons anticipation still fails: (a) bursts rare (~0.6%/step)+short -> holding capacity
idle costs more than it saves; (b) picker CAPACITY caps what being-ready can clear (+54 gap). Would pay
only under frequent/long bursts OR abundant pickers.
EV 120-SEED CONFIRM (keep/drop, stream 8x4): beta=0.25 -3.5 (n.s.), beta=0.35 -10.1 (t=-2.18, p=0.043
SIG WORSE), beta=0.5 -4.7 (n.s.). ALL NEGATIVE. The 30-seed +2.4 was noise (regressed to negative, same
as the MCTS early +18). DROP EV -- would add a demand-model dependency + variance for a negative effect.
Anticipation line CLOSED AT POWER: SA5, EV(all beta @120), MCTS(all K +/- urgency) all wash-to-negative.
Champion stays clean (sequencer + value-rate pickers, no future-guessing). Lesson reinforced: 30-seed
"slight positives" here are coin flips; the 120-seed rule caught two false positives this session.

## 2026-07-28 — spatial-temporal demand DRIFT: evidence + dataset (queued as ROADMAP M3b)
Anticipation is dead on our STATIC-hotspot demand. It can only pay off if the hotspot MOVES. Web-checked
whether real demand drifts spatially (not asserted): YES.
 - Warehouses re-slot high-demand SKUs HOURLY because demand shifts by hour/season/promotion (wedosupplychain).
 - Seasonal/promotional spikes need dynamic ops (parcelplanet).
 - Instacart Market Basket dataset (2017, ~3M orders, 200k users): strong diurnal (peak 10am-3pm), reorder
   cycles (day 7/30), per-order department/aisle labels (Towards Data Science).
DATASET to calibrate the demand-model drift = INSTACART MARKET BASKET. Gives hour-of-day + day-of-week
(-> diurnal rate) + department/aisle popularity (-> map department->warehouse zone) + reorder timing. KEY
spatial-drift signal to extract = department popularity BY HOUR (does the hot mix shift AM->PM?). CAVEAT:
Instacart is product taxonomy, not physical shelf coords -> map department->zone; and the by-hour shift is
the specific thing to verify in the data (not yet confirmed -- that's the calibration step).
Sources: wedosupplychain.com (slotting), parcelplanet.com (seasonal), towardsdatascience.com (Instacart).
NOTE: drift is ADDITIVE -> does NOT change the M1 knobs (they rank/route/deadline; drift moves WHERE, not HOW).

## 2026-07-28 — M1 DONE: URG_W (deadline weight) tuned across the AGV x picker ratio grid
72 cells (AGV 4-9 x picker 4-9 x daylist/stream), comb {0,4,8}, 120 seeds, on the sequencer champion.
(viz argmax was contaminated by stale 12/16 values at n=20-50 from earlier runs; recomputed clean on
{0,4,8}@120 -- viz_urg_grid now filters n>=120.) CLEAN RESULT:
 - DAY-LIST: best URG_W = 0 in 32/36 ratios (4 exceptions +0/+1/+2 = noise). UNIVERSAL: urgency hurts on
   the sequencer in day-list (full foresight -> deadline bump redundant/distorting).
 - STREAM: best URG_W ~= 8 in 20/36 (7 at 4, 9 at 0), real positive deltas +3..+14 (8agv/4pk +13). Urgency
   HELPS on the stream (rollout blind to future arrivals -> deadline bump adds info).
FINDING: deadline weight is REGIME-dependent (0 daylist / ~8 stream), NOT ratio-dependent. Earlier
"urgency helps only when pickers abundant" hypothesis NOT supported -- stream wants urgency broadly incl.
picker-scarce. Regime is the whole axis. Mechanism confirmed: urgency = patch for the rollout's missing
foresight. ACTIONABLE M1 WIN: deployed champion runs URG_W=8 everywhere; set URG_W=0 on day-list (recovers
~4-12/day ~1% that urgency was silently costing), keep 8 on stream. Graph: results/urg_best_URG_W.png.

## 2026-07-29 — M1 step 2: W_SYNC tuned on the full ratio grid = NULL (default 0.3 stands)
Coordinate-ascent step 2: W_SYNC {0, 0.15, 0.3, 0.5} across all 72 cells (AGV 4-9 x picker 4-9 x
daylist/stream), 120 seeds = 34,560 runs, on `_SqWidePkRateAdaptive` (best URG_W baked in: 0 daylist /
8 stream).
RESULT — no value beats the 0.3 default. Pooled paired (n=8,640 per contrast):
  W_SYNC=0     mean d = -0.38  t = -1.63
  W_SYNC=0.15  mean d = -0.03  t = -0.18
  W_SYNC=0.5   mean d = -0.30  t = -1.84
Per-cell argmax splits 23/10/21/18 across the four values (= coin flip). Only 4/72 cells reach |t|>2,
about what a max-of-4 per cell yields under the null. By regime: daylist W_SYNC=0.5 is t=-2.19 (worse);
nothing else separates.
KILLED HYPOTHESIS — "W_SYNC=0 wins when pickers are abundant" (from the earlier flat-run +7 at stream
8x8). Two reasons it's dead:
 1. That +7 was NEVER independent evidence. For STREAM, `_SqWidePkRateAdaptive` sets URG_W=8, identical
    to `_SqWidePkRate`'s URG_W=8, and both runs used seeds 0-119 -> the "replication" is the SAME
    experiment re-run. It reproduced exactly (+7.0, t=2.14) because it is literally the same measurement.
    CAUTION for future sweeps: adaptive-vs-fixed bases are only distinguishable on DAY-LIST.
 2. The predicted ratio structure is absent. W_SYNC=0 vs 0.3 pooled by picker/AGV ratio:
      pk<agv  n=3600  d=-0.65  t=-1.61
      pk~agv  n=1440  d=+0.14  t=+0.28
      pk>agv  n=3600  d=-0.31  t=-0.96   <- mechanism predicted a WIN here; it's negative.
ACTION: W_SYNC stays at default 0.3 everywhere; no base change. URG_W remains the only knob that has
moved the needle in M1. Step 3 (CONG_LAMBDA / CONG_WEIGHT / SEQ_DEPTH) runs on the plain adaptive champion.

### WHY W_SYNC is null — mechanism (diagnostic, 8x8 seed 0 + 6-seed trace check)
W_SYNC penalises the AGV's sync-up idle: `my_wait = max(0, t_partner - t_fetch)`,
`score -= W_SYNC * my_wait` (sim_priority.py:518).
ROOT CAUSE = DOUBLE-COUNTING, and the second count is ~1000x weaker than the first:
 - rollout.py:174 `rendez = max(t_fetch, t_partner)` -> `finish = rendez + load + dock`. Every step of
   sync wait is ALREADY inside `finish`, and `finish` sets `proj_late` -> the makeable(1000+v) /
   doomed(v*g^late) TIER. The wait is already charged at full strength there.
 - `- W_SYNC*my_wait` is a SECOND invoice for the same quantity, sized:
     my_wait == 0 in 63.7% (daylist) / 50.6% (stream) of task evaluations -> penalty exactly 0
     when >0: median 6.0 / 4.0 steps -> penalty at W_SYNC=0.3 = 1.80 / 1.20 pts (p90 3.7/3.3, max 7.5/5.6)
   vs a 1000-pt tier gap and task values ~tens. It can NEVER move a task across the tier boundary;
   it can only reorder tasks WITHIN a tier whose values differ by <~2 pts.
BEHAVIOUR CHECK: W_SYNC=0 vs 0.3 gave IDENTICAL assignment traces in 0/6 seeds -> the knob really does
change which tasks are chosen. But it only flips NEAR-TIES, where both options are worth ~the same, so
the value washes out. The null is "it changes decisions that don't matter", not "it does nothing".
(6-seed dValue -3.0 daylist / +9.7 stream = noise; the 34,560-run grid is the authority.)
KNOWN PATHOLOGY (sim_priority.py:216): for an AGV already PARKED at the rendezvous, agv_eta=0 so the sync
term charges it the picker's FULL travel -> degenerates into a disguised distance penalty in exactly the
case sync exists for. STALL_BONUS (=0.0) was written to fix that and is off. So some of its small
influence is actively mis-aimed.
GENERALISABLE RULE: any knob that is an ADDITIVE score nudge on a ~1-pt budget cannot compete with the
1000-pt tier cliff -> expect null. CONG_LAMBDA / CONG_WEIGHT are in that same class (predict null).
SEQ_DEPTH is NOT -- it changes how many candidate futures the sequencer evaluates, i.e. it alters the
TIER CLASSIFICATION itself rather than nudging within it. That is the one with a real mechanism.

## 2026-07-30 — URG_W comb WIDENED to {0,4,8,12,16} on all 72 cells (paper fix) = 43,200 runs
WHY: the original comb {0,4,8} put the chosen value (8) at the grid EDGE -> could not show the response
curve turn over, and 8 stray cells had leftover 12/16 arms at n=120 (best-of-5 vs best-of-3 = biased
argmax). Filled 12 and 16 to 120 seeds in ALL 72 cells; base kept at `sqwidepr` to match the original.
Audit: 72/72 cells, every value on exactly seeds 0-119, 0 duplicate/conflicting rows.
RESPONSE CURVE (paired vs URG_W=0, 36 cells per regime):
  URG_W      4        8        12       16
  daylist  -2.84   -4.38    -6.53    -6.90     (t = -7.8, -11.4, -15.7, -16.7)
  stream   +0.24   +1.87    +0.26    -0.16     (t = +0.4, +2.78, +0.38, -0.23)
 - DAYLIST: MONOTONIC DECLINE. Optimum = 0 = the deadline term SWITCHED OFF. That is a NATURAL
   boundary (cannot test "less than none"), not an artificial grid edge -> no extension needed below.
 - STREAM: clean INTERIOR PEAK at 8, both neighbours resolvably lower (8 vs 4 t=+2.69; 12 vs 8 t=-2.99).
   The regime-conditional rule (0 daylist / 8 stream) is now properly bracketed on both sides.
REFINEMENT (test 6 and 10?) — REJECTED ON POWER, not on principle. Near a smooth peak the response is
locally quadratic, so halving the grid gains ~1/4 of the adjacent-step difference = ~1.6/4 = 0.4 pts,
against SE 0.54 -> t~0.7. Resolving it needs SE~0.2 = (0.54/0.2)^2 ~ 7x the seeds (~875/cell) to chase
0.4 pts on a 336-pt baseline (0.1%). 120 seeds already supports the finest grid worth running.
METHODS NOTE (per-cell argmax is NOISE-DRIVEN, use pooled tests as primary):
  stream argmax with 3-value comb: 8 wins 20/36
  stream argmax with 5-value comb: 8 wins 14/36  (0:5, 4:5, 8:14, 12:5, 16:7)
Adding grid points DILUTED the per-cell winner while the pooled evidence for 8 got STRONGER. Daylist
barely moved (32/36 still pick 0) because its effect is huge (t=-16.7). Present per-cell maps as
exploratory; pooled paired tests (n=4,320/regime) are the confirmatory instrument.
GRID-DESIGN RULE (for the paper): choose values to BRACKET the default; extend only where the optimum
lands at a boundary; refine only where adjacent points are resolvable AND the peak location is uncertain.
Bracketing status: W_SYNC 0.3 (of 0..0.5), CONG_LAMBDA 0.3, CONG_WEIGHT 0.3, SEQ_DEPTH 5 (of 3..8) all
INTERIOR; URG_W fixed by this run. RATE_ALPHA now sweeping {3,4,5,6,7} on the grid (was set to 5 by an
early deployment-fleet-only sweep -> was the last untested-at-grid-scale knob).

## 2026-07-30 — TEST FOR "IS THE PER-CELL MAP REAL?" = SPLIT-HALF REPRODUCIBILITY. All maps = PATCHWORK.
METHOD: compute each cell's argmax TWICE on independent seed halves (0-59, 60-119). Real per-cell
structure reproduces; noise does not. Baseline = chance agreement implied by the observed marginal
(so a map that is "mostly one value" gets no credit for agreeing by default).
RESULT (72 cells per knob, 36/regime):
  knob     regime    agree   chance      z
  URG_W    daylist    53%      59%    -0.80
  URG_W    stream     22%      23%    -0.05
  W_SYNC   daylist    25%      27%    -0.27
  W_SYNC   stream     28%      25%    +0.35
NONE show per-cell structure. Note the daylist URG_W map LOOKS clean (32/36 zeros) but that is a
REGIME-level fact (0 wins nearly everywhere), not per-cell structure -- once the marginal is accounted
for, cell-to-cell variation does not replicate. CONFIRMS: use regime/group rules, never per-cell argmax.
APPLY THIS TEST TO RATE_ALPHA when it completes (early hint: alpha=3 beat 5 by +5.7 t=3.41 at stream
4x4 -- if "alpha=3 in small fleets" is real the halves will agree above chance; if it is the argmax
lottery they will not).

## 2026-07-30 — CONFOUND FOUND: daylist vs stream are NOT workload-matched (affects VoPI, not the knobs)
VERIFIED: `daylist` and `stream(warm=0)` generate BIT-IDENTICAL order sets (seeds 0,1,2) -- the NHPP+
Hawkes arrival process and every deadline are the same, exactly as seed_day_list's docstring claims.
THE ONLY DIFFERENCE is stream's `seed_initial(n=12)` warm start (so robots aren't idle on a cold start),
which daylist never receives:
  seed 0:  daylist 60 orders / value 490 / mean deadline 380
           stream  75 orders / value 652 / mean deadline 325
IMPACT:
 - SAFE: all knob tuning. Within a regime every arm sees identical demand on identical seeds, so the
   paired contrasts (URG_W, W_SYNC, RATE_ALPHA) are unaffected.
 - CONFOUNDED: any CROSS-REGIME claim. The "100% makeable (daylist) vs 64.8% (stream)" gap mixes
   INFORMATION (rollout blind to arrivals) with LOAD (+25% orders). Cannot be separated as-is.
 - PAPER-CRITICAL: seed_day_list bills daylist-minus-stream as the PERFECT-FORESIGHT bound / VoPI
   ("whatever a demand predictor could be worth"). That number currently includes a 12-order load
   difference and is NOT a clean information bound.
FIX (cheap, targeted -- does NOT need the knob grid re-run): champion in both regimes with the warm
start MATCHED (give daylist n=12 too, or run stream at warm=0), a few fleets x 120 seeds.
WHAT STILL SUPPORTS the information story for URG_W (workload held fixed, so not confounded): giving the
STREAM rollout foresight via the MCTS arms made urgency stop helping (K2U0/K2U16). Urgency and foresight
are SUBSTITUTES. Mechanism table: the rollout's `_future_arrivals` returns [] in BOTH regimes -- that
assumption is exactly TRUE on daylist (step() is a no-op after t=0) and exactly FALSE on stream.

### VALIDATION: the REGIME rule passes the same split-half test that KILLED the per-cell map
Q (user, 2026-07-30): "if the splits barely agree, how do we know our values are best?"
A: split-half was applied PER CELL (120 runs = a tiny sample). Apply it at the REGIME level (pooling all
36 cells = 4,320 paired runs) via 200 RANDOM half-splits -- how often does the same value still win?
                        full-data best   half-splits agreeing
  URG_W  daylist              0            200/200 = 100%
  URG_W  stream               8            187/200 =  94%
  W_SYNC daylist              0.15         124/200 =  62%
  W_SYNC stream               0.3          116/200 =  58%
 - URG_W's regime rule is ROCK SOLID under resampling; the per-cell map is chance. Same data, different
   sample size -- one cell = asking one person, one regime = running a poll.
 - The test is NOT a rubber stamp: W_SYNC fails it even POOLED (58-62%, winner bounces 0/0.15/0.3), which
   is exactly why we kept the default rather than "tuning" it to whatever the full data happened to favour.
KEEP AS THE STANDARD: report (a) pooled delta + t, (b) regime-level half-split reproducibility %. A rule
ships only if the pooled test AND the resampling stability both hold. Applies to RATE_ALPHA/CONG/SEQ_DEPTH.

## 2026-07-31 — RATE_ALPHA = 5 CONFIRMED (both regimes) + the SPACE-vs-FUTURE principle for knobs
RATE_ALPHA swept {3,4,5,6,7} x 72 cells x 120 seeds (43,200 runs), base = adaptive champion.
POOLED (34 cells/regime at time of writing, 68/72 complete -- verdict stable since 52%):
  alpha        3       4      5      6      7
  daylist   -0.19   -0.34    0    -0.20  -0.26     (t: -0.74, -2.20, --, -1.20, -1.10)
  stream    -1.23   -0.26    0    -0.64  -0.75     (t: -2.41, -0.75, --, -1.74, -1.76)
EVERY alternative is negative in BOTH regimes -> alpha=5 is a properly BRACKETED interior optimum.
Stability 54%/62% (low, but that only reflects neighbours 4 and 6 being within noise of 5 -- the peak
LOCATION is not in doubt; decision rule says keep the incumbent and the pooled test agrees).
VALUE OF THE RESULT: alpha=5 came from an early DEPLOYMENT-FLEET-ONLY sweep. It is now validated across
72 fleet configurations. Stronger paper claim than a null: a real response curve peaking at the incumbent.
LOTTERY WATCH (worth reporting as a methods example): alpha=3 on the stream opened at +5.7 (t=3.41) in a
single early cell, and I called it "mechanism-shaped". Pooled trajectory as cells accumulated:
  +0.60 -> +0.34 -> -0.66 -> -1.23 (t=-2.41).  It ended SIGNIFICANTLY WORSE than the incumbent.
Textbook per-cell argmax lottery, caught by pooling before it reached the paper.

### PRINCIPLE (predictive, derived 2026-07-31): SPACE knobs are regime-INVARIANT, FUTURE knobs are not
WHY RATE_ALPHA is the same in both regimes but URG_W is not. RATE_ALPHA is the picker's exchange rate
between distance and value (`score = tier + eff_v / Tp^alpha`), so the optimal exponent is set by the
RELATIVE SPREAD of log-value vs log-time among the candidates. MEASURED (8x8 seed 0):
                          daylist   stream
  Tp mean                   21.4     23.5
  SD log(Tp)                0.540    0.493
  SD log(value)             0.991    0.842
  ratio SDlogV/SDlogT       1.84     1.71     <- within 7% -> same optimal exponent
The warehouse does not change between regimes (same grid, same hot centres, and the order sets are
BIT-IDENTICAL) -- pickers walk the same distances either way. URG_W by contrast encodes the assumption
"nothing more will arrive", which is 100% TRUE on daylist and 100% FALSE on stream -> the optimum flips.
(Caveat: daylist value spread IS larger, CV 1.53 vs 0.83, because all orders are visible at once so
shelf batching accumulates more. But it moves the governing ratio only 7% -- too small to shift a peak
flat enough that 4 and 6 sit within noise of 5.)
FALSIFIABLE PREDICTION for the queued knobs (recorded BEFORE running them):
  CONG_LAMBDA / CONG_WEIGHT -> congestion+routing = SPACE  -> predict regime-INVARIANT
  SEQ_DEPTH                 -> lookahead horizon  = FUTURE -> predict regime-DEPENDENT (like URG_W)
=> argues for running SEQ_DEPTH and SKIPPING the CONG pair: it is the only remaining knob that TESTS
the principle rather than confirming it a third time.

### RATE_ALPHA FINAL — 72/72 cells, 43,200 runs, seeds 0-119 everywhere
  alpha        3       4      5      6      7
  daylist   -0.24   -0.30    0    -0.15  -0.20     (t: -0.95, -2.02, --, -0.94, -0.86)
  stream    -1.27   -0.19    0    -0.63  -0.67     (t: -2.57, -0.55, --, -1.74, -1.61)
VERDICT: alpha=5 best in BOTH regimes, every alternative negative, bracketed on both sides.
Regime-level stability 50% (daylist) / 56% (stream) -- low only because neighbours 4 and 6 sit within
noise of 5; the peak LOCATION is not in doubt. Decision rule -> KEEP INCUMBENT (no champion change).
Per-cell split-half: daylist z=-0.35, stream z=+0.66 -> patchwork, as with every other knob.
M1 KNOB SCOREBOARD so far (3 of 5 done, 121k runs):
  URG_W       -> REGIME RULE (0 daylist / 8 stream). The only knob that changed the champion.
  W_SYNC      -> NULL (flat noise, no winner even pooled). Default 0.3 kept.
  RATE_ALPHA  -> INCUMBENT CONFIRMED (real bracketed curve peaking exactly at 5). No change.
Consistent with the standing "decision layer is near-maxed (~1.5-2% from the hindsight oracle)" finding.

## 2026-08-01 — CLEAN VoPI: the documented figure was WRONG BY 2x, and in the FAVOURABLE direction
Ran `scripts/exp_vopi.py` -- 4 arms x 6 fleets x 120 seeds = 2,880 runs, champion, warm start MATCHED.
  contaminated (docs quote)  daylist(w0) - stream(w12) = +69.89   (21.0%)  t=+22.5
  WORKLOAD-MATCHED           daylist(w0) - stream(w0)  = +142.91  (54.9%)  t=+60.8
  WORKLOAD-MATCHED           daylist(w12)- stream(w12) = +135.47  (40.6%)  t=+53.8
The 12-order warm start was HIDING the gap, not inflating it: it is worth +73.0 to the stream
(t=-28.1) because those orders land at t=0 when robots are otherwise idle on a cold start. Comparing
daylist-WITHOUT against stream-WITH understated the true gap by half.
Per fleet (matched, w0): 4x4 58.3% | 4x8 63.0% | 6x6 49.5% | 8x4 57.7% | 8x8 51.2% | 9x9 51.8%.

### ...BUT day-list minus stream IS NOT AN INFORMATION BOUND (important -- do not quote it as VoPI)
MECHANISM: `seed_day_list()` puts EVERY order into `env.request_queue` at t=0 while its deadline stays
`t_arrive + slack`. So day-list can SERVE work before it arrives -- an order due at 480 whose arrival
time is 400 is fetchable from step 0. Each task gets the FULL 500 steps of robot-time instead of
`500 - t_arrive`. That is CAPACITY, not knowledge, and NO predictor can grant it (a forecast tells you
what is coming; it cannot let you fetch a shelf for an order that does not exist yet).
The flatness across fleets (49-63%, no capacity trend) is itself the signature of a STRUCTURAL effect
rather than an informational one. => the seed_day_list docstring's "only VISIBILITY changes" is WRONG:
visibility AND AVAILABILITY change, and availability does most of the work.
=> This is why 100% of daylist task evaluations are makeable vs 64.8% on stream. Not a smarter planner
-- vastly more usable robot-time per task.

### THE TEST THAT ACTUALLY ISOLATES INFORMATION -> `scripts/exp_true_vopi.py` (RUNNING)
Stream physics held fixed (orders become SERVABLE at t_arrive), but the sequencer's rollout is handed
the TRUE upcoming arrivals instead of []. Gap vs plain stream = the real ceiling on any demand
predictor -- the number the SA5/EV/MCTS nulls must be judged against.
TWO-PASS + CAVEAT: `DemandModel._inject` excludes shelves in transit, so the arrival stream is mildly
POLICY-DEPENDENT and cannot be pre-generated exactly. Pass 1 runs the plain champion and RECORDS what
arrived; pass 2 replays that as the foresight signal. Once pass 2 acts differently the recorded future
drifts slightly from what would truly occur -> this BOUNDS the information value, does not measure it
exactly (standard hindsight-oracle construction).
SMOKE TEST (24 runs): 24/24 differ -> the signal genuinely reaches the rollout. Early mean = -9.35,
i.e. perfect information came out WORSE. If that holds at 720 paired runs it is a strong result: the
anticipation nulls would be "there is nothing to get", not "our estimator was too weak".

## 2026-08-01 — SIMULATOR FIX: demand was ENDOGENOUS TO THE POLICY. Added `exogenous=True` (opt-in).
FOUND WHILE building the true-VoPI arm. `DemandModel._inject` picks a shelf from those NOT currently in
transit (`avail = [s for s in self.shelfs if s not in carried]`), so WHICH shelf gets ordered depends on
what the robots happen to be carrying. Consequences, measured (18 runs, 3 fleets x 6 seeds):
 - Two policies on the same seed get the SAME NUMBER and TIMES of arrivals (Poisson draws are shared)
   but only **22.2% exact / 27.7% (time,shelf) overlap**. ~75% of orders land on different shelves.
 - => v1 of `exp_true_vopi.py` was INVALID and its **-11.39 result is RETRACTED**: the "known future"
   recorded under the no-foresight policy was ~78% wrong under the foresight policy. It measured STALE
   information, not perfect information.
 - => every paired comparison in the project is only PARTIALLY paired (same counts/times/value draws,
   different shelf identities). Does NOT overturn anything -- SEQ_DEPTH's -33.9 (t=-28.7) and URG_W's
   regime rule (t=-16.7) are orders of magnitude beyond this -- but error bars are slightly wider than
   reported and it belongs in the methods section.
 - It is also UNREALISTIC: customers do not avoid ordering a product because a robot is mid-trip with
   its pod. The exclusion is a simulator convenience that leaks the policy into the demand process.
FIX (`wwm_sim/demand.py`, OPT-IN so no existing result changes meaning):
  `DemandModel(..., exogenous=True, horizon=500)` pre-draws the ENTIRE arrival schedule from the seed
  alone -- times, shelves, values, deadlines -- via `_build_schedule` (uses a derived RNG so it does not
  disturb `self.rng`). `step()` replays it; `_place()` records without an env-dependent choice;
  `future_arrivals(after, until)` exposes the genuine future (returns [] unless exogenous, so no caller
  can silently obtain a policy-contaminated "future"). `_refresh` now guards against queueing a shelf
  that is mid-trip (no-op on the legacy path, where carried shelves are never chosen).
ACCEPTANCE TESTS -- ALL PASS:
  A) REGRESSION: legacy path reproduces previously-banked stream_w12 values EXACTLY (6/6).
  B) THE POINT: with exogenous=True two DIFFERENT controllers (`_SqWidePkRateAdaptive` vs `_PkRate`)
     see BIT-IDENTICAL arrival streams (45/45, 56/56, 53/53...) while still producing different values.
  C) `future_arrivals()` overlap with what actually lands = **100%** (was 22%).
=> `exp_true_vopi.py` v2 is SINGLE-PASS and exact. Smoke (36 runs): mean **-12.89**, 36/36 differ.
SCOPE NOTE (user checkpoint): the perfect-information arm is a MEASURING INSTRUMENT, deliberately
impossible -- it reads the pre-drawn schedule. It is never a proposed controller. The point of a VoPI
ceiling is to settle the question for EVERY possible estimator at once: any real predictor's information
is a strictly degraded version of what this arm gets free, so if the ceiling is <= 0, no averager can
help. Deployable arms (EV field, M3c staging) remain history-only estimators.

## 2026-08-01 — **TRUE VoPI MEASURED: PERFECT DEMAND INFORMATION HAS NEGATIVE VALUE (-3.4%)**
`scripts/exp_true_vopi.py` v2 (single-pass, exogenous demand so both arms face IDENTICAL orders and the
foresight arm gets the GENUINE schedule). Champion vs champion+`future_arrivals`, 6 fleets x 120 seeds.
  n = 720 paired   baseline 326.9
  mean delta = **-11.23  (-3.43%)   t = -5.98   95% CI [-14.91, -7.55]   W/L/tie 278/441/1**
NEGATIVE IN ALL SIX FLEETS, with a clear CAPACITY GRADIENT:
  4x4 -6.0% (t=-4.10) | 4x8 -5.5% (-3.84) | 6x6 -4.4% (-3.14) | 8x4 -2.3% (-1.60) | 8x8 -1.9% (-1.47) | 9x9 -1.0% (-0.75)
MECHANISM: knowing valuable work is coming makes the rollout prefer branches that keep robots free or
well-positioned for it -> it SACRIFICES CERTAIN PRESENT VALUE. But only the FIRST MOVE commits, and by
the time that future work lands, reactive re-planning would have taken it anyway. The sacrifice buys
nothing and costs real value now. TIGHTER CAPACITY = LESS AFFORDABLE TO HOLD BACK = MORE DAMAGE, which
is exactly the observed gradient (and is itself evidence for the mechanism rather than noise).
NOTE ON THE RETRACTION: the corrected -11.23 lands almost exactly on the invalid v1 -11.39. v1's
conclusion happened to be right, but was reached via a ~75%-wrong future -- agreeing with a broken
experiment is not evidence. The fix was still required.
=> **WHAT THIS SETTLES.** The SA5 / EV / MCTS anticipation nulls were NEVER an estimator-quality
problem. A literal oracle loses. No forecast, however good, can help -- any real predictor's information
is a strictly degraded version of what this arm got free. A string of nulls becomes ONE principled
finding with a measured bound. This is the anticipation chapter's headline.
=> **WHAT IT DOES NOT SETTLE** (keep both gated, but raise the bar):
  - M3b (demand DRIFT): measured on STATIC hotspots only; the drift premise is untested.
  - M3c (idle-AGV staging): acts through a DIFFERENT CHANNEL -- *where a spare robot waits*, not *which
    task to take*. Not covered by this result.

## 2026-08-01 — FORESIGHT WINDOW SWEEP: there is NO useful prediction horizon (closes demand forecasting)
`scripts/exp_foresight_window.py`. The true-VoPI test was ALL-OR-NOTHING; this asks whether a SHORT
window is actionable while a long one merely distorts. Exogenous demand, 6 fleets x 120 seeds, W=0 is
the plain champion control. 720 paired runs per arm, baseline 326.9.
  W=10   -0.10  (-0.03%)  t=-0.07     <- EXACTLY ZERO
  W=25   -1.65  (-0.51%)  t=-0.93
  W=50   -3.91  (-1.20%)  t=-2.17
  W=100  -5.32  (-1.63%)  t=-2.61
  W=999 -11.23  (-3.43%)  t=-5.98
MONOTONIC. No positive region anywhere. A PERFECT 10-step forecast is worth exactly nothing, and the
damage scales with how far ahead you look.
=> The anticipation chapter is now closed on three independent legs: (1) every estimator arm was null;
(2) PERFECT information is negative (-3.4%); (3) there is no HORIZON at which it pays. It is not
"our estimator was too weak" and not "we forecast at the wrong horizon" -- knowing future orders does
not help this system at any accuracy or any range.
STILL UNTESTED (do not over-claim): drifting demand (M3b premise) and the POSITIONING channel (M3c).

## 2026-08-01 — PART D revisited: windowed joint first moves, NO IDLING (user's original spec)
PRIOR: "coordinate simultaneously-free robots jointly" = worth 0, because robots almost never free at
the same instant. USER'S FIX: don't require simultaneity and don't WAIT for it -- pair with the AGV
freeing within W steps, branch over my top-3 x its top-3, commit only MY move now.
BUILT `_SqWidePkRateJoint` (+W10/W20/W30). Needed a `_sim_core` change: pins may carry an optional 5th
element = the pinned robot's FREE TIME, so a still-busy partner is not evaluated as if free at `now`
(a few steps of optimism straddles the 1000-pt makeable/doomed cliff). Backward compatible.
TWO BUGS FOUND BY SMOKE TEST (both produced silent identical-to-champion output):
  1. partner filter excluded `a in self.assigned_agvs` -- which holds every robot EXECUTING a mission,
     i.e. exactly the busy robots about to free. Partner set was permanently empty (0 hits/episode).
  2. two more sites unpacked pins as fixed 4-tuples.
INSTRUMENTED REALITY CHECK (8x8 seed 0) -- why the original Part D was worth 0, sharper than "rare":
  `_pick_winner` fires only **17x per 500-step episode**, 7 of them at t=0 with nothing busy to pair.
  Partner free-gaps at the other 10: 6,7,7,12,13,14,21,22,25,33.
  => W=5 CANNOT FIRE (min gap 6). W=10 -> 3/17, W=20 -> 6/17, W=30 -> 9/17.
  There are only ~10 joint-eligible decisions in an entire day. (NB my earlier headroom estimate of
  27-48% at W=5 counted FREE EVENTS, ~46/episode -- not decision points. It overstated the opportunity.)
SMOKE (24 runs, stream): w10 -7.30, w20 -12.98, w30 -13.00; 18-21/24 differ. NEGATIVE.
LIKELY MECHANISM: the joint branch optimises A's move for a pairing that never happens -- B is NOT
committed, so when B actually frees it re-runs its own funnel and may take something else. A pays a
real cost for coordination that evaporates. Wider window = staler assumption = worse, which matches.
Rhymes with the graveyard entry "obeying the whole imagined plan (open-loop) costs +11.3".
FULL 120-seed x 6 fleets x 2 regimes RUNNING (`results/joint_partd.csv`).

## 2026-08-02 — PART D FINAL (non-binding) + a THIRD silently-inert arm + deadlock scan
PART D, 720 paired runs per cell, champion baseline:
              W=10              W=20              W=30
  daylist   -0.59 (t=-1.16)  -4.71 (t=-7.18)  -6.91 (t=-10.79)
  stream    -1.62 (t=-1.55)  -5.48 (t=-4.20)  -5.81 (t=-4.43)
Zero at W=10, monotonically harmful beyond. WHY: the rollout ALREADY co-decides the partner inside every
branch, so joint optimisation adds no coordination -- it only HARDENS an assumption that evaporates when
the partner re-decides on freeing. Wider window = staler assumption = worse. VERDICT: no headroom.

### BINDING VARIANT = STILL UNTESTED (do NOT quote its number)
The run finished and produced output BIT-IDENTICAL to joint_w20 (-4.71/-5.48, same t) across 1,440 runs
-> the reservation never fired. Cause: hooked `_task_order()`, but the champion's funnel iterates
`finalists` from the cheap screen (sim_priority.py:455) and never calls it. Correct hook = filter
`finalists` (or the queue feeding the screen).
**THIRD silently-inert arm this session.** The other two: (1) the Part D partner filter excluded
`a in self.assigned_agvs` -- which holds every robot EXECUTING a mission, i.e. exactly the busy robots
about to free, so the partner set was permanently empty; (2) binding reservations written into
`assigned_items` clobbered the partner's CURRENT task, releasing a carried shelf back into the pool
(that one at least crashed). All three produced PLAUSIBLE numbers, not errors.
=> **STANDING RULE: before believing any new arm's null, verify it DIFFERS FROM ITS PARENT on some
seeds.** A null from an arm that never ran is the most expensive kind of wrong answer.

## 2026-08-02 — DEADLOCK / STALL SCAN: robots do sit still for a very long time
Instrumented consecutive steps where a robot has a path (or is busy) and does not move. 4 seeds/cell:
  fleet  regime    stall>=3  >=5   >=10   LONGEST
  4x4    stream      2095   1633   920      52
  8x8    daylist     6063   5542  4746     485   <- of a 500-step episode
  9x9    daylist     9303   8656  7671     364
CAVEAT ON MY OWN MEASURE: this conflates true blocking with LEGITIMATE waiting at a rendezvous for a
picker. Counts are therefore overstated. But a 485-step stationary spell cannot be partner-waiting, and
stalls scale sharply with FLEET SIZE (4x4 -> 9x9), which is the signature of contention. Needs the
refined check (mid-route blocked vs parked-at-target) before any number is quoted.
WHY IT MATTERS: the makeable/doomed verdict -- the 1000-pt cliff that dominates every ranking -- is
computed from an EMPTY-WORLD estimate. Verified on the champion: `_finish_delay` resolves to
PartAController's (returns 0.0), `delay_head` is None, FINISH_CONG_K unset. No traffic term at all.
The live delay EMA enters ONLY inside the imagined rollout, never the real deadline check.
RELATED (user's proposal: put estimated delay INTO the deadline check) -- it is ALREADY there, disguised:
LOAD_TIME=5 is not loading physics (the env has no loading delay) but a PAD for un-modelled delay, and
the 2026-07-22 sweep showed HAVING a pad matters (lt1 -3.27 p=0.021, replicated p=0.009) while its SIZE
does not, anywhere in 3..15. So a constant pad is settled. UNTESTED: an ADAPTIVE pad -- `_finish_delay`
returning the live `_delay_ema`, which VARIES over the day (bigger in a rush) as a constant cannot.
Dead code already exists for this: `per_task_window()` was written to calibrate geometry against
observed durations and is NEVER CALLED.

## 2026-08-02 — PART D DELETED (code removed, result kept) + DEFERRED COMMITMENT killed by measurement
PART D: removed `_SqWidePkRateJoint*` from congestion_policies.py (144 lines) and deleted
`scripts/exp_joint.py`. Evidence retained: `results/joint_partd.csv` + the 2026-08-02 NOTES entry.
Cut because there is no headroom in any form and the reason is structural (the rollout already
co-decides the partner inside every branch). KEPT from the work: `_sim_core` pins may carry an optional
5th element = a pinned robot's free time (backward compatible; useful for any future multi-robot branch).

### DEFERRED COMMITMENT -- STRUCTURALLY DEAD, closed WITHOUT a full run
Idea (user): leave a task unassigned when a robot freeing soon would serve it much better. Only robots
free RIGHT NOW can be assigned (`available = [not busy ...]`), so a badly-placed free robot always beats
a well-placed one freeing in 3 steps -- the rollout knows when everyone frees, the assignment loop just
cannot say "wait". Added a `_defer_commit` hook (defaults False) + `_DeferMixin` (DEFER_W, DEFER_M).
SMOKE: 0/24 seeds differed at W=10 AND at W=30/60 -> instrumented instead of guessing.
GATE MEASUREMENTS (12 runs, 4x4 + 8x8, both regimes):
  t_free of busy AGVs: min 6, p10 11, median 28, p90 53, max 77
     within W=10 -> 8.8% | W=20 -> 31.1% | W=30 -> 54.9% | W=45 -> 81.5% | W=60 -> 96.5%
     (first draft's W=10 was below the practical floor -- same class of error as Part D's W=5)
  BEST (theirs - mine) per assignment, 309 assignments with a candidate in W=60:
     min -1021.0 | p25 0.0 | median 0.0 | p75 0.8 | p90 5.4 | MAX 8.0
     gap > 10 : 0.00%   gap > 50 : 0.00%   gap > 250 : 0.00%
WHY IT CANNOT WORK: both robots compete for the SAME task, so both score `1000 + v` -- identical. The
only term that can differ is urgency, capped at URG_W = 8. So the margin is bounded by 8 points and any
threshold above that is unreachable BY CONSTRUCTION. Worse, the 28.8% of POSITIVE gaps are positive
because the later robot has LESS SLACK, so the urgency term rewards it for being nearer its deadline --
the opposite of a reason to wait. And min = -1021 is a tier flip the other way (deferring loses the task).
ROOT CAUSE: t_free floor ~6 / median 28 vs grid distances 15-30 -> freeing later almost always means
FINISHING later. A position advantage cannot outrun the time penalty. Not a bug; the premise is false.

### PICKER-SIDE SEQUENCER -- built, and its CEILING is measured before the full run
`_PkSeqMixin` (+ `_SqWidePkSeq0/2/5`): keep `_picker_score` as the cheap screen, re-simulate the top-K
rendezvous with that picker PINNED, rank by banked value. Depth 0 = greedy funnel (control).
SANITY PASS: pkseq0 ties the champion on 24/24 seeds.
CEILING (749 picker dispatches): the picker has only ONE candidate rendezvous **86.9%** of the time.
   1 cand 86.9% | 2 cands 6.5% | 3 1.7% | 4 1.7% | 5 0.8% | 6+ 2.3%
   -> the rollout can only fire in **13.1%** of picker decisions (smoke: 1/24 seeds differed).
INTERPRETATION (matters for the paper): the picker side is not under-OPTIMISED, it is under-CONSTRAINED
-- most of the time there is no choice to make. That is exactly consistent with the standing finding
that the binding limit is picker HEADCOUNT (free-picker ceiling +11..22). You cannot decide your way out
of not having enough pickers. Running the full sweep anyway since 13% is not 0.

## 2026-08-02 — ROLLOUT FIDELITY closed: the imagination IS wrong about pickers, and fixing it buys nothing
`_SqWideHonestPin`. THE DEFECT (real, verified in code): `_simulate_branch` passes the funnel's heuristic
finish as `fov`, so `_sim_core` takes the fov path -> `jj = None` -> the pinned FIRST MOVE picks no
picker and CONSUMES none. Every imagined task in the tail therefore believes all pickers are still free.
The imagination is optimistic by EXACTLY ONE PICKER, for the whole horizon, in every branch -- on the
resource that is the measured bottleneck (free-picker ceiling +11..22; binding limit = picker headcount).
Corroborating measurement: 26.1% of the rendezvous a picker actually evaluates come out DOOMED, i.e. the
AGV's "makeable" verdict -- computed against an AVERAGE picker via `partner_eta` -- is wrong ~1/4 of the
time. FIX: pass fov=None so the pinned move goes through `rendezvous()` like every other imagined task
(real picker chosen, contention-aware finish, picker marked busy).
SMOKE: 24/24 seeds differ -> the arm genuinely fires (unlike the three silently-inert arms earlier today).
RESULT (720 paired runs per regime):
  daylist  +1.48 (+0.37%)  t=+1.81  95% CI [-0.12, +3.07]  W/L 347/297
  stream   -0.31 (-0.09%)  t=-0.21  95% CI [-3.16, +2.55]  W/L 322/319
=> NULL. Neither clears the t>=3 bar; stream is a 322/319 coin flip. DOES NOT SHIP.
CONSEQUENCES:
 1. `URG_W` does NOT need re-validating -- the optimism I suspected was inflating it is not load-bearing.
    THE M1 KNOB TABLE STANDS EXACTLY AS SWEPT and M1 can close honestly.
 2. THE WHOLE FIDELITY GROUP CLOSES WITH IT. This was deliberately gated on the cheapest item:
    honestpin hands the first move the SIMULATION'S OWN picker assignment, which is strictly better
    information than any heuristic could produce. It did not pay, so the unbuilt variants cannot either:
      - `partner_eta` matched-picker (predict which picker will actually come) -- CLOSED unbuilt
      - adaptive delay pad (`_finish_delay` -> live `_delay_ema`)               -- CLOSED unbuilt
      - contention-aware funnel tier                                            -- CLOSED unbuilt
 3. PATTERN (now four independent instances): per-task delay prediction null even with an oracle; layer-2
    null even with true answers; perfect demand information NEGATIVE; and now a MEASURABLY WRONG
    imagination whose correction is worth nothing. **This system does not reward better prediction. It
    rewards acting well on the present.** That is the paper's through-line, and it is now well-evidenced.
NOTE ON THE DAYLIST +1.48 (t=1.81): tempting, fails the decision rule (t>=3 AND >=80% stability), and
this session has repeatedly shown marginal early positives decay (RATE_ALPHA alpha=3: +5.7 -> -1.27).
Not taken.

## 2026-08-02 — PICKER-SIDE work all closes: sequencer null, claimed-picker null. FREEZE CHECK launched.
### PICKER SEQUENCER (`pkseq`) -- NULL, and for a STRUCTURAL reason
720 paired runs/cell. pkseq0 (control) ties champion 0/720 differ in BOTH regimes -> harness honest.
  pkseq2 daylist +0.01 (t=+0.68, 2/720 differ) | pkseq5 daylist +0.00 (0/720)
  pkseq2 stream  -0.06 (t=-1.33, 2/720)        | pkseq5 stream  -0.06 (t=-1.33, 2/720)
The mechanism changed the outcome in **2 seeds out of 720**. Cause measured BEFORE the run: 86.9% of
picker dispatches have only ONE candidate rendezvous, so the rollout can fire in at most 13.1% of
decisions, and among those the top-3 usually re-rank to the same pick.
=> THE PICKER SIDE HAS ALMOST NO DECISIONS TO MAKE. The AGV sequencer is worth 7.2% because AGVs choose
among 15 finalists; a picker usually has exactly one AGV waiting. You cannot re-rank a list of one.
Same conclusion the free-picker ceiling (+11..22) has always pointed at: the picker constraint is
HEADCOUNT, not allocation. No decision machinery on that side can move it.

### CLAIMED-PICKER (`_SqWideClaimedPicker`) -- NULL (v2, after fixing my own model)
IDEA (user's, and correctly specified): feed PICKER REALISM into the AGV's rollout. `rendezvous()` hands
each imagined task its SOONEST picker; reality is that picker may be off serving something richer.
Measured: value-rate winner != soonest winner **33.5%** of the time, real rule accepts median 4 (p90 15,
max 36) extra steps, and **51.9% of those disagreements cross the makeable/doomed tier**.
BUILD: walk pickers in arrival order, take the first for which THIS task is its best option. Touches
ONLY `_sim_choose_picker` inside `_sim_core` -- real picker behaviour is untouched (that was `pkseq`).
TWO OF MY BUGS, both caught by the differs-from-parent rule:
  v0: compared a RELATIVE denominator for `sh` against ABSOLUTE sim times for rivals -> `mine` ~5 vs
      rivals ~hundreds -> every picker always claimed -> silently identical to champion (0/24).
  v1: omitted the TIER. Real `_picker_score` is `tier + eff_v/Tp^alpha` with tier 1000/500/0; value-rate
      differences are fractions. Without it the AGV imagined pickers abandoning it for fat DOOMED tasks
      no picker would ever take -> finishes pushed late for no reason. Result was -0.63 daylist.
  v2 (correct, mirrors `_picker_score` exactly):
      daylist -0.14 (-0.03%) t=-0.51, 129/720 differ | stream -0.38 (-0.11%) t=-1.08, 55/720 differ
      Fixing the tier moved daylist -0.63 -> -0.14, i.e. straight toward zero: THE v1 NEGATIVE WAS MY BUG.
=> Genuinely firing (129 and 55 seeds), genuinely null. Picker realism in the AGV rollout is worth zero.
=> FIDELITY GROUP NOW CLOSED ON TWO INDEPENDENT LEGS: the imagination is measurably wrong about pickers
in two distinct ways (first move consumes none; soonest != who actually comes) and correcting EITHER is
worth nothing.

### FREEZE CHECK RUNNING (`scripts/exp_freeze_check.py`, 5,040 runs)
Every shipped knob re-validated under EXOGENOUS demand (bit-identical orders across arms), 3 fleets x 2
regimes x 120 seeds. Arms each move ONE knob off the champion: urg8all / urg0all (does the REGIME RULE
still beat a single global value?), alpha4 / alpha6, seq3, wsync015. Expectation: the shipped value wins
or ties every contest -- this confirms rather than corrects, and lets the paper state the table was
verified under fully-paired demand. If it holds, THE M1 KNOB TABLE IS FROZEN.

## 2026-08-02 — **M1 KNOB TABLE FROZEN** (freeze check passed) + a scoping correction
`scripts/exp_freeze_check.py`, 5,040 runs, EXOGENOUS demand (bit-identical orders across arms),
3 fleets x 2 regimes x 120 seeds. Each arm moves ONE knob off the champion.
STREAM (the only regime the endogenous bug ever applied to) -- champion holds every contest:
  urg8all   0.00  --      identical to champion (champion already runs 8 on stream) -- SANITY PASS
  urg0all  -0.87  t=-0.97 champion holds
  alpha4   +0.20  t=+0.19 tie
  alpha6   +0.86  t=+0.90 tie
  seq3      0.00  --      identical to champion -- INDEPENDENT re-confirmation that stream depths
                          3/5/8 are bit-identical (queue empties before the horizon binds)
  wsync015 -0.60  t=-0.62 champion holds
SCOPING CORRECTION (worth recording, I nearly mis-read this): DAY-LIST NEVER HAD THE BUG.
`seed_day_list` generates every order at t=0 BEFORE any robot has moved, so nothing is in transit and
the shelf choice was already policy-independent. The endogenous-demand problem applied ONLY to stream.
Re-validating day-list under exogenous demand adds noise and answers nothing -- and it initially LOOKED
alarming: urg8all daylist came back +0.39 (t=+2.41), i.e. URG_W=8 beating 0, contradicting the sweep.
Diagnosis: (a) restricted to 3 fleets the ORIGINAL sweep is itself only -2.83 (t=-2.29) vs -4.38
(t=-11.44) across all 36 -- the subset throws away 92% of the evidence; (b) `exogenous=True` consumes an
RNG draw in `_build_schedule`, so the day-list orders are a DIFFERENT realisation, not the same
experiment. Two marginal t~2.3 readings in opposite directions on 1/12th the data is noise, not a flip.
The day-list rule rests on 4,320 paired runs, t=-11.44, and 100% stability over 200 resamples.
=> **FROZEN: URG_W 0/8 (regime rule) | W_SYNC 0.3 | RATE_ALPHA 5 | SEQ_DEPTH 5 | CONG_* 0.3 |
   LOAD_TIME 5.** M1 IS CLOSED.

## 2026-08-02 — STALL DIAGNOSIS: my earlier "485-step stall" was mostly a measurement artefact
Split stationary time three ways (3 seeds/cell): PARKED (no path -- standing at a rendezvous waiting for
a partner, legitimate) vs BLOCKED (has a path, did not move) and, for blocked, whether the next cell is
occupied.
  fleet/regime      parked   blocked   by-robot   next-cell-FREE   longest   steps-with-cycle
  4x4 stream          3627      2168        530             1638        49          76
  8x8 daylist        12768      3893        729             3164       326          43
  9x9 daylist        13564      6060       1654             4406       311         426
 1. 60-70% of stationary time is LEGITIMATE PARKING. My earlier scan counted it as stalling, which is
    what produced the alarming 485 figure. Correction on record.
 2. REAL DEADLOCK EXISTS AND SCALES WITH FLEET SIZE: circular waits (A blocked by B, B blocked by A)
    detected in 426 of ~1500 steps at 9x9 daylist vs 76 at 4x4. This is exactly the failure mode a
    congestion COEFFICIENT cannot see and a tick-level rollout could -- but note our rollout is
    ANALYTIC (Manhattan + scalar delay EMA), so it cannot see it either.
    CAVEAT: the detector counts STEPS CONTAINING a cycle; a 2-cycle may be a swap that resolves next
    tick. Transient vs stuck is NOT yet separated.
 3. UNEXPLAINED AND DOMINANT: 72-80% of genuine blocking is "has a path, next cell EMPTY, did not move".
    Not congestion. Candidates: the TOGGLE_LOAD micro-action burning a step; a stale `path` attribute
    that is not the executed route; the env's own collision filter. MUST be identified before any
    blocking number is quoted -- if it is mostly a micro-action artefact, real blocking is far smaller
    than the table suggests.

## 2026-08-04 — M2 groundwork: REALISTIC disturbance types (literature-calibrated) + they BITE
CRITICAL CONTEXT FIRST: **ALL OF M1 RAN WITH DISTURBANCES OFF.** They are opt-in (`env.disturb_rate>0`
AND `env._disturb_rng` set) and NO `scripts/exp_*.py` touches either. So ~200k runs -- the sequencer
ablation, all four knob sweeps, VoPI, Part D, the picker arms -- were on a CLEAN FLOOR. The knob table
is valid *for an undisturbed warehouse*; whether it transfers is now an open question (URG_W prices
deadline pressure and disturbances add unpredictable delay; SEQ_DEPTH plans deep into a floor that now
changes underneath it). The sequencer's +7.2% is "worth 7.2% on an unobstructed floor".
=> PAPER: disclose plainly, then either show transfer or re-tune under M2/M3 conditions.

### TWO REALISTIC TYPES BUILT (`env.disturb_kind`: blob | human | spill | mixed)
LITERATURE (searched 2026-08-04):
 - HUMAN/drift: mean pedestrian walking speed 1.25 m/s (typical 1.2-1.4); warehouse AGVs ~1-2 m/s, so a
   person crosses at ~robot speed. Indoor trajectories are "more intricate and with more abrupt changes"
   than outdoor. Datasets: JRDB (arXiv:1910.11792), THOR, THUD++ (arXiv:2412.08096).
 - **THOR-MAGNI Act (arXiv:2412.13729) is the on-point one** -- human motion in robot-SHARED INDUSTRIAL
   spaces recorded with a **Robotnik RB-KAIROS+ base (DARKO)**, Orebro. Classes are warehouse work:
   Carrier-Box, Carrier-Bucket, Carrier-Large Object, Visitors-Alone/Group. Findings used:
     * "WalkBox and WalkBucket involve higher velocities compared to WalkLO or WalkStorageBin, where
       participants move alongside the robot" -> small-load carriers move at full pace; large objects
       and robot-accompanied walking are slower.
     * "static actions such as picking up or delivering an object result in small negative
       accelerations" -> people STOP mid-route. Implemented as `disturb_human_pause` (default 0.20).
     * Large objects are carried "in pairs of two" -> some human obstacles are 2 CELLS WIDE and slower.
       **NOT IMPLEMENTED -- documented simplification** (4 arms were silently inert this week from
       over-building; add deliberately once the 1-cell version is validated).
 - SPILL/pile: "spilled liquids, loose packaging, cluttered walkways", "pallets in aisles, maintenance
   equipment" named as temporary obstructions needing route adjustment. NO quantified incidence rate
   found -> spread rate and duration are STATED ASSUMPTIONS, not fitted.
MODEL: duration sets the type. human = 1 cell, dur 20-60, drifts ~1 cell/step with P(turn)=0.35 and
P(pause)=0.20. spill = seeded cell, dur 150-400, GROWS outward at 4%/cell/step, capped ~9 cells locally.

### DO THEY BITE? (8x6 stream, 12 seeds, clean floor = 379.0)
  kind    rate    value    cost      %     cells | reroutes
  blob    0.06    354.2   -24.8   -6.5%      3.8 | 6     (t=-2.08)
  human   0.06    369.6    -9.4   -2.5%      1.9 | 76    (t=-1.10)
  human   0.15    355.0   -24.0   -6.3%      4.5 | 193   (t=-2.75)
  spill   0.06    258.7  -120.3  -31.7%     52.1 | 12    (t=-3.67)   <- MIS-CALIBRATED, unusable
  spill   0.015   346.5   -32.5   -8.6%     18.9 | 6     (t=-2.04)
  mixed   0.06    334.3   -44.7  -11.8%     17.4 | 140   (t=-2.34)
 - Disturbances cost **2.5-8.6% at sane rates -- LARGER THAN EVERY M1 KNOB COMBINED.** Real money.
 - spill@0.06 blocks 52 cells and destroys a third of all value: same spawn rate x 5x lifetime x growth
   compounds. USE 0.015. My assumption was wrong and the measurement caught it.
 - **KEY CONTRAST FOR M2's PREMISE:** matched at ~6% cost, a STATIC blob causes 6 reroutes while
   DRIFTING HUMANS cause 193. Static obstacles are dodged once and forgotten; a human walks into your
   new plan. If a belief map can beat reactive re-routing anywhere, it is against the MOVING kind.
RECOMMENDED M2 SETTINGS: human@0.15, spill@0.015 (each ~6-9%, stressing different things); mixed ~0.03.

### SEQUENCING DECISION (user's, and it is right)
Both M2 (disturbances) and M3 (battery) change the world the knobs were tuned in. Re-validating after
each pays twice and staleness the first answer. So: M2 wire+ablate -> M3 charging -> **ONE** knob
revalidation with disturbances AND battery both on (~3,000 runs) -> freeze again.
Corollary: M2's headline ablation must hold knobs FIXED, or a "map win" could be a disguised knob effect.
ALSO: "hard rules for when to abandon a current task -- every margin tested: nothing" is in the
graveyard, but that was measured on a CLEAN FLOOR where tasks only go doomed via queueing delay. With
disturbances they go doomed because the world physically changed -- different cause, possibly different
answer. Retest rather than inherit.

## 2026-08-05 — **M1 CLOSED**: deferred knobs null, scale claim CONFIRMED, valid oracle ceiling at last
Three open items closed overnight (8,400 + 2,880 + 960 runs, chained unattended).

### A) DEFERRED DEADLINE KNOBS -- ALL NULL, champion unchanged (5 fleets x 120 seeds)
  arm        regime    n     delta       t
  s0_20      stream   600    +1.49    +0.94     URG_S0 = 40 HOLDS (the 10-seed smoke's +18/+26 was noise)
  s0_80      stream   600    +1.86    +1.13     (day-list skipped: URG_W=0 there, so S0 cannot bite)
  pkurg_4    daylist  600    -1.44    -1.89
  pkurg_8    daylist  600    -1.44    -1.89     <- IDENTICAL at 4/8/16
  pkurg_16   daylist  600    -1.44    -1.89
  pkurg_*    stream   600    -2.00    -1.06     <- IDENTICAL at 4/8/16
  pks0_20/80 both     600  -0.64..-1.87  -0.45..-1.46
FINDING inside the null: picker urgency gives BIT-IDENTICAL results at weights 4, 8 and 16. With 86.9%
of picker dispatches having a single candidate, the weight almost never changes the pick -- and when it
does, ANY nonzero weight flips it the same way. The knob has two states (off / on), not a magnitude.

### B) SCALE / GENERALISATION -- the size-agnostic claim HOLDS AND STRENGTHENS
champion vs `cong_l2on` (previous champion), 3 fleets x 120 seeds, exogenous demand:
  map          regime    n     delta        t      %
  medium       daylist  360   +14.64    +9.17   +3.6%
  medium       stream   360   +12.60    +3.52   +3.5%
  extralarge   daylist  360   +16.05   +10.50   +4.2%
  extralarge   stream   360   +14.81    +5.66   +5.0%
All four significant. **The advantage GROWS with map size** (3.5% -> 5.0%): a bigger warehouse gives the
sequencer more to reason about. Strongest form of the claim -- not "it transfers" but "it transfers
better". Closes the reviewer question that every M1 number came from one map.

### C) ASSIGNMENT ORACLE -- FIRST VALID CEILING: **+4.0%** (and it is CONCENTRATED, not uniform)
`_ChampExplore` v2 finally measures the right thing (v1 discarded -- it replaced the sequencer and
sampled the top 2-4 by FUNNEL score while the champion simulates all 15, a strict SUBSET of the
baseline's search space, so it could not bound it). v2 runs the sequencer and DEVIATES from its winner
with p=0.25 to a random top-K simulated branch -> every rollout is a competent policy with
perturbations, and best-of-M explores the neighbourhood ABOVE the champion. 12 seeds x best-of-80, 8x6
day-list. Still a LOWER bound (random search finds no adversarial schedules).
  seed  0 +20.6 (72/80) | 1 +6.6 (33/80) | 2 +14.1 (18/80) | 3 **+45.9 (+13.9%, 70/80)**
  seed  4  +0.0 (1/80)  | 5 +9.9 (6/80)  | 6 +28.4 (58/80) | 7  +0.0 (9/80)
  seed  8  +1.2 (21/80) | 9 +10.8 (32/80)| 10 +0.0 (12/80) | 11 **+43.4 (+10.8%, 77/80)**
  MEAN GAP +15.1 otv (+4.0%)
=> **THE HEADROOM IS NOT UNIFORM.** 3 of 12 seeds are EXACTLY optimal (gap 0.0, beat-rate 1-12/80) while
seeds 3 and 11 give up 10-14% with beat-rates of 70/80 and 77/80. On good days random deviation cannot
beat the champion at all; on bad days it wins nearly every time -- i.e. the champion falls into a poor
schedule and has nothing to pull it out. That is a MORE actionable finding than a flat 2%: the value is
in a minority of episodes, which is exactly where restart-and-take-best, or a smarter tie-break, would
pay. Consistent with the tie discovery (48.6% of decisions are ties, mean tie size 5.09): on some seeds
the tie-break sends you down a bad path with no correction.
=> Note this SUPERSEDES the standing "~1.5-2% from the hindsight oracle" guiding fact, which was
measured on the OLD stack at 8x4 on a clean floor. New figure: **+4.0% at 8x6 day-list**, champion-based.

### M1 FINAL STATE
FROZEN: URG_W 0/8 · W_SYNC 0.3 · RATE_ALPHA 5 · SEQ_DEPTH 5 · URG_S0 40 · CONG_* 0.3 · LOAD_TIME 5 ·
picker urgency OFF. Verified under exogenous (fully-paired) demand; every knob has a split-half verdict
(all patchwork per-cell, all rules pooled); scale-tested on 3 maps. ~220,000 runs total.
STILL DEFERRED BY DESIGN: one revalidation with disturbances AND battery on, after M2/M3.

## 2026-08-05 — what the funnel actually contributes, and why the cliff is inert

**Q (user): if all 15 shortlisted tasks are simulated regardless of value, what carries over from
before the sequencer to after it?**

Four things survive the funnel. Value-*ordering* is not the main one:

1. **Admission.** `SCREEN_KEEP = 15` — the funnel decides which 15 of all pending tasks are simulated
   at all. Everything else is invisible to the sequencer. This is the funnel's real job: gatekeeping,
   not ranking.
2. **The route.** `K_ROUTES = 3`, funnel picks one; `feat["pred_finish"]` derives from it.
3. **`pred_finish` -> `fov`** — the only funnel number that enters the simulation's arithmetic.
4. **Ties.** `_pick_winner` returns `scored[vals.index(mx)]`, the FIRST index of the max. Measured:
   **48.6% of calls end tied, mean tie size 5.09**. So the funnel score silently decides ~half of all
   commitments. "Ordering means nothing because all 15 are simulated" holds only for the ~51% where
   the rollout actually separates the candidates.

**Why TIER_GAP is inert (smoke, 3 seeds x 5 fleets x 2 regimes):**

    gap_100  2/30 seeds differ   gap_300  0/30   gap_3000  0/30   gap_10000  0/30

The gap can only change the shortlist by letting a DOOMED task interleave with a MAKEABLE one. Task
values are in the tens; at 1000 the tiers never interleave, and within-tier ordering is by value
regardless of gap size -- so the shortlist is **bit-identical** for any gap >> max task value. It is a
**gate, not a weight**. The shipped 1000 is arbitrary-but-correct; documenting it as "any large
constant". Sweep moved to {20, 50, 100, 200} to find where it starts to bite.

**Q (user): why a constant pad if we have the adaptive EMA? "ema is an average anyway".**

They are a **prior and a posterior**, and they live in different steps:
- The EMA is only in **step 6** (`_sim_core` -> `_sim_step_bias`). Step 5's `_finish_delay` returns
  **0.0** and `delay_head` is None, so the makeable/doomed call is made on raw geometry + `LOAD_TIME`.
- `BIAS_PRIOR = 0.0`, so the EMA is **zero until the first delivery completes**. Nothing to average
  yet. NOTES already records all 8 worst-error seeds diverging at t=0 with bias 0 ("fantasy time").
  The constant pad is what covers the cold start; the EMA takes over once calibrated.
- They do not double-count: the EMA is calibrated against a prediction that ALREADY contains the pad,
  so it only ever corrects the residual.

This explains the otherwise-odd LOAD_TIME sweep result -- *having* a pad matters (-3.27, p=0.021 when
removed) but its *size* is irrelevant 3..15. What matters is that the t=0 estimate is not zero-biased.

**Bug caught while building the `emapad` arm.** `_finish_delay` is consumed at TWO sites: the funnel
score AND `fov`, the pinned first move handed to the sim. Since `_sim_core` then adds `_sim_step_bias`
on top of `fov`, a naive override corrects **the same number twice**. Fixed by overriding
`_simulate_branch` to drop `_finish_delay` from `fov`, isolating the change to step 5. The +0.90 from
the first smoke is discarded as uninterpretable. (Same failure family as the four silently-inert arms:
the arm ran, produced plausible numbers, and was measuring something other than its label.)

## 2026-08-05 — TIER_GAP FULLY SWEPT: the makeable/doomed cliff is DECORATIVE

Two sweeps, 1,200 paired runs per arm (120 seeds x 5 fleets x 2 regimes), champion = GAP 1000.

ABOVE the value range (max task value measured at 18.5, median 8.1):
    gap_20  4.8% differ  +0.03 (t +0.16)   gap_50  0.7%  +0.04 (t +1.80)
    gap_100 0.2%         +0.01 (t +1.27)   gap_200 0.0%  +0.00  <- BIT-IDENTICAL to 1000
    (smoke: gap_300 / gap_3000 / gap_10000 all 0/30)
  => any GAP > max task value gives an identical shortlist. It is a GATE, not a weight.
     My first sweep {20..10000} was mis-sized: every arm sat above the value ceiling, so the gate
     never opened. Should have measured the value distribution FIRST. Cost a 7,000-run round trip.

INSIDE the value range (where tiers genuinely interleave):
    gap_0  68.1% differ  +0.56 (t +0.57)   gap_3  42.5%  -0.50 (t -0.64)
    gap_6  31.2%         +0.45 (t +0.74)   gap_10 19.4%  +0.49 (t +1.01)
    gap_15  9.4%         +0.32 (t +0.99)
  ALL NULL. `gap_0` removes the tier ENTIRELY, changes 68% of episodes, and banks the same value.
  Not monotonic (gap_3 negative), so there is no trend to read either.

PREDICTION MADE BEFORE THE RUN AND FALSIFIED: I argued from Moore-Hodgson (1||sum w_j U_j) that all
low-gap arms must be NEGATIVE -- a doomed task banks exactly zero under a strict on-time objective, so
robot-time spent on it is pure loss. The argument is right about the PROBLEM and wrong about the LAYER:
**the rollout already ranks branches by simulated banked ON-TIME value**, which scores a late delivery
as zero by construction. Doom is therefore priced correctly in step 6 regardless of what step 5 says.
The tier is REDUNDANT with the downstream value accounting, not load-bearing.

VERDICT: keep TIER_GAP = 1000 (nothing beats it; most headroom if task values ever grow), but report it
as a structural constant -- "any value exceeding max task value" -- NOT as a tuned hyperparameter.
PAPER VALUE: this is a clean ABLATION, stronger than a tuning result. A prominent reasoning stage can be
deleted outright and 68% of decisions change with zero net effect. Sixth leg on the central finding, and
the sharpest form of it: not "better prediction doesn't help" but "a whole stage is subsumed by the rollout."

### Companion result: EMAPAD (live delay-EMA added to step 5) = -1.13, t -2.57, 168 L / 125 W, 24.4% differ
Below the |t|>=3 shipping bar but the sign test agrees; this is NOT a null. Mechanism: the EMA is positive
(things finish later than geometry predicts), so feeding it into the step-5 deadline check makes it more
accurate AND more pessimistic -> marginal tasks reclassify makeable->doomed -> never attempted. The
optimistic raw-geometry estimate leaves them in, the robot goes, and SOMETIMES MAKES IT.
=> OPTIMISM IN THE ADMISSION FILTER BEATS ACCURACY. A correct forecast of lateness causes premature
abandonment of still-winnable tasks. First leg where better prediction measurably HURTS.
NB the first `emapad` smoke (+0.90) was confounded -- `_finish_delay` feeds BOTH the funnel score AND
`fov`, and `_sim_core` adds `_sim_step_bias` on top of `fov`, so the pinned first move got the EMA twice.
Fixed by overriding `_simulate_branch` to drop `_finish_delay` from `fov`. Discarded the +0.90.

### Why the constant pad is still needed (user Q: "ema is an average anyway")
Prior vs posterior, living in different steps. `BIAS_PRIOR = 0.0` -> the EMA is ZERO until the first
delivery completes, so it cannot cover the cold start; step 5's `_finish_delay` returns 0.0 and
`delay_head` is None, so there is no EMA in the funnel at all. They do not double-count: the EMA is
calibrated against a prediction that already contains the pad, so it only corrects the residual.
Explains the odd LOAD_TIME sweep result -- HAVING a pad matters (-3.27, p=0.021) but its SIZE is
irrelevant 3..15: what matters is that the t=0 estimate is not zero-biased.

## 2026-08-05 — "long deadlocks" are NOT deadlocks: a single-robot silencing defect in the base simulator

USER Q: what happens in these long stalls -- do robots sit there forever? ANSWER: yes. There is no
resolution. A frozen robot holds its task, its path and `busy=True` until the episode ends.

### The old stall scan was measuring the wrong thing
Refined classification of every stationary step (8x8 day-list seed 0), which the 2026-08-02 scan
flagged as needed and never got:
    IDLE_unassigned                 3344  62.2%   <- no task at all (STARVATION, not blocking)
    TOSHELF_mid_route                789  14.7%
    TOSHELF_at_goal_waiting_picker   695  12.9%   <- legitimate rendezvous wait
    CARRY_mid_route                  274   5.1%
    CARRY_at_goal                    272   5.1%
62% of the old scan's "stalls" were idle robots with nothing to do -- which is why they scaled with
fleet size. That was starvation being read as contention.

### The real failure: permanent freeze, and it is NOT robot-vs-robot
Scan (6 seeds x 3 fleets x 2 regimes), "busy + path + zero movement for >=50 steps to episode end":
    daylist 4x4 0.83/ep | 8x6 2.67/ep | 8x8 1.33/ep      stream 8x6 1.50/ep | 8x8 2.00/ep
Worst case = daylist 8x6 seed 3: THREE of six pickers frozen ~315 steps each, work outstanding the
entire time. Traced picker id=9 (8x8 seed 0), frozen t=317..499:
  - target cell (12,26) EMPTY on ALL THREE collision layers (SHELVES, AGVS, PICKERS) all 183 steps
  - agent already facing RIGHT toward it; `get_next_micro_action` correctly returns FORWARD
  - req_action histogram t>=317: {NOOP: 181, RIGHT: 2}  -- it never even attempts the move
NO SECOND ROBOT IS INVOLVED. This is not a deadlock, not contention, and no MAPF deadlock-resolution
scheme (PIBT / priority victim-selection) would fire on it.

### ROOT CAUSE (warehouse.py:524-527, base TA-RWARE) -- NOT yet fixed
    commited_agents = set([...])
    failed_agents = set(agent_list) - commited_agents
    for agent in failed_agents: agent.req_action = Action.NOOP   # blanket silencing
`commited_agents` is populated ONLY from graph cycles + **one `dag_longest_path` per weakly-connected
component**. Every agent in a component but off that single path is silenced regardless of whether
anything blocks it. Measured on the frozen picker: **FORWARD -> NOOP on 144 of 183 steps**.
=> when start/target cells chain into a large blob, only agents along one path may move.
(NB: the `compsize=1` values in my first probe were an ARTIFACT -- I rebuilt the graph after the
original call had already set req_action=NOOP, making req_location a self-loop. Before/after counts
are sound; ignore those component sizes.)

### Secondary defect -- FIXED: stuck-counter livelock, warehouse.py:543-555
`_STUCK_THRESHOLD=5`, `column_height=8` -> release needs count > 15. But the recovery branch reset the
counter to 0 on EVERY successful replan, so it sawtoothed 0->6->0 forever and `busy=False` was
unreachable. Verified: counter max = 5 across 183 frozen steps.
FIX APPLIED: reset only when `new_path != agent.path`, so a futile replan lets the counter reach the
release. Re-measured, 6 seeds/cell:
    daylist 4x4 0.83->0.17 | 8x6 2.67->1.50 | 8x8 1.33->1.33 | stream 8x6 1.50->2.33 | 8x8 2.00->2.33
Total 50 -> 46. NET ~NEUTRAL at n=6. Confirms the counter was a SYMPTOM; the blanket silencing is the
cause. KEPT (user's call): the knobs govern task/route SELECTION, the livelock is EXECUTION -- different
decision points -- and a change this small cannot have moved knob optima. The frozen M1 table stands.

### Impact on existing results -- comparisons survive, absolute levels do not
Every arm was handicapped identically and all sweeps are paired-by-seed, so the knob table and the
champion-vs-arm deltas stand. What is NOT safe: absolute on-time value, and any claim resting on
capacity. **The fleet-ratio result (8x6 > 8x8, +25) deserves re-examination** -- larger fleets build
larger connected components, so they may lose proportionally more robots to the silencing. That could
be part of why more robots stopped helping.
SUGGESTIVE (n=6, do NOT quote as established): correlation of robot-steps-frozen-while-work-outstanding
with the 8x6 day-list ORACLE GAP = **+0.805** (seed 3 worst on both: 948 frozen-steps, gap +45.9; seed 4
best on both: 78, gap 0.0). This reframes the earlier bad-seed diagnostic -- efficiency at -0.977 was the
EFFECT (banked/available is near-tautological with the gap); frozen-with-work is upstream of it.

### Literature reviewed for the eventual resolution scheme
PIBT [IJCAI'19] commits only the NEXT cell per timestep and negotiates locally -- destination-aware,
path-blind (= the user's option B) -- deadlock-free **on bi-connected graphs only**; the guarantee fails
on dead-ends / tree-shaped paths, i.e. exactly shelf aisles + in-rack rendezvous. PIWTP
[arXiv 2205.12504] restores it for Multi-Agent Pickup & Delivery via priority INHERITANCE, which is what
stops static value-priority from starving the lowest-value robot. Standby-based avoidance
[arXiv 2201.06014] targets the dead-end case. CONCLUSION: A and B are not alternatives -- B is the
mechanism, A is the priority function it consumes, inheritance bounds the yielding. Citations added to
docs/PAPER_DRAFT.md section 2. NOT BUILT: still ZERO measured instances of a true multi-robot deadlock.

## 2026-08-05 — BASELINE VIOLATES THE COLLISION INVARIANT (rare, but real)
Found incidentally while instrumenting the priority-yield experiment (`scripts/exp_yield.py` counts
same-type co-location every step of every run).
  357 same-type collisions across the first 800 runs -- **ALL in the `champion` (unmodified) arm**;
  the priority-yield arms produced none. Concentrated: daylist 8x6 = 310, daylist 9x9 = 35.
RARITY: only **2 of 800 runs** collide at all (seed 48: 309, seed 104: 1). The 309 is NOT 309 events --
it is ONE pair overlapping continuously:
  8x6 daylist seed 48 -> AGV id=4 and AGV id=8 BOTH at (3,9) from t=191 onward, neither carrying.
So the failure is a stuck PAIR that never separates, not repeated collide-and-recover. Almost certainly
the same family as the freeze defect (agents that stop emitting FORWARD never move apart again).
SCOPE CORRECTION for the paper: "Collisions = 0 absolute" holds for *committed routes* by construction
(section 6.1's actual claim) but NOT for executed positions -- two agents can end up co-located. State it
as the route-level guarantee it is, and cite this measurement as the execution-level exception.

### Methodological note (my error): interleave arms in sweeps
`exp_yield.py` builds jobs arm-by-arm, so `imap_unordered` finishes all 1,200 champion runs before the
first treatment run -> NO paired comparison exists until the sweep is ~half done. Build the job list
seed-major (or shuffle) so partial results are readable throughout. `exp_cliff.py` has the same flaw.

## 2026-08-05 — PRIORITY-ORDERED CLASH YIELDING: DEAD (4,800 runs). Static execution priority HURTS.

DESIGN (user's): the base sim picks the rerouter by nested-loop order (`if other.fixing_clash == 0`),
which can flip between steps -> both robots reroute, re-collide, dance. FIX = rank the pair; higher
priority keeps its route, loser reroutes (`Warehouse._yields_to`, gated on `env.commit_priority`,
default None so the champion is untouched).

RESULT -- 1,200 paired runs per arm, 5 fleets x 2 regimes x 120 seeds, champion mean 376.8:
  arm         n      mean d      pct        t       W/L      collisions
  arbitrary  1200    -1.47    -0.39%    -1.44   441/531        377
  value      1200    -5.71    -1.52%    -5.06   436/641        871   <- DOUBLES collisions
  deadline   1200    -6.45    -1.71%    -5.40   427/647        400
  (champion baseline collisions 431)   daylist -0.76/-3.37/-4.46 | stream -2.19/-8.06/-8.45

**THE RANKING-FREE CONTROL IS THE LEAST BAD, AND THE MORE PRINCIPLED THE RANKING THE MORE IT COSTS.**
MECHANISM = STARVATION, exactly as the MAPF literature predicts for static priority without inheritance.
Under a static key the low-value / slack-rich robot loses EVERY clash it enters, accumulates delay, and
eventually crosses its OWN deadline -- converting a task that would have banked into a ZERO. Arbitrary
(by id) spreads the victimhood across pairs; value/deadline concentrate it on a fixed subset.
Same asymmetry as the emapad result: systematically deprioritising the "less urgent" makes it doomed.

### AND IT DOES NOT FIX THE PATHOLOGY (the gate question, 20 episodes/mode, 8x6 + 8x8, both regimes)
  mode        frozen  per-ep   frozen-with-work
  None            40    2.00        6313
  arbitrary       38    1.90        5913
  value           37    1.85        4428
  deadline        37    1.85        6278
Freezes essentially UNCHANGED. So we pay up to -1.7% and buy nothing. REASON: the clash rule only fires
when two robots are ADJACENT AND CONTENDING, but the freezes are SINGLE robots failing to move into
EMPTY cells, silenced upstream by resolve_move_conflict's commited_agents filter. The yield rule was
never touching the actual failure -- a fact already measured (target cell empty on all 3 layers, 183
steps) before the arm was built. Weight that kind of evidence more heavily next time.

### WHAT THE RESEARCH SAYS THE RIGHT KEY IS -- NEITHER VALUE NOR DEADLINE
PIBT [IJCAI'19] sets `p_i(t) = eta_i(t) + eps_i` where **eta_i = timesteps since agent i last reached a
goal** and eps_i is a small unique per-agent constant. Priority RISES while waiting and RESETS on
arrival, so every agent eventually becomes top priority -> **starvation is structurally impossible**.
Note WHERE task attributes belong in that scheme: as the TIEBREAK eps_i, not the primary key. The
literature-backed design is therefore
    priority = (steps since this robot last completed a task) + normalized(deadline urgency)
aging dominant, deadline breaking ties. CAVEAT: PIBT's guarantee holds on BI-CONNECTED graphs and fails
on dead-ends / tree-shaped paths = shelf aisles + in-rack rendezvous. PIWTP [arXiv 2205.12504] and
standby-based avoidance [arXiv 2201.06014] exist to close exactly that gap.

### PREDICTIONS ON RECORD (for calibration)
Smoke (3 seeds, 8x6 daylist) said deadline **+11.7**; at 1,200 paired runs it is **-6.45**. Fourth time
a marginal early positive decayed (RATE_ALPHA a=3 +5.7->-1.27; emapad +0.90->-1.13; deadline +11.7->-6.45).
I put deadline's chance of being good at 10% when it stood at -3.52/n=200 -- too generous; the sign and
t were already informative. Blend-of-value-and-deadline estimate revised 15% -> 5%: a better key for a
rule that fires in the wrong place is still the wrong place.
STATUS: code retained but DORMANT (`env.commit_priority` defaults None). Champion unchanged.

## 2026-08-05 — **SELF-LOOP FIX: ROOT CAUSE OF THE FREEZES, AND IT SHIPS** (+0.65%, collisions -87%)

### ROOT CAUSE (verified, warehouse.py:452-455)
`resolve_move_conflict` built its conflict graph with `G.add_edge(start, req_location())` for EVERY
agent. But `req_location()` returns the agent's OWN cell for any non-FORWARD action -- so every
STATIONARY agent added a **self-loop**. `nx.find_cycle` reported that as a cycle, the code took the
rotation branch, committed only the agents named in the self-loop, and **`dag_longest_path` NEVER RAN**
-- so every genuinely-moving agent in that weakly-connected component fell into `failed_agents` and was
NOOPed. ONE PARKED ROBOT POISONED ITS ENTIRE COMPONENT.
SELF-SUSTAINING: a silenced agent is stationary next step, so it re-creates the self-loop that silences
it. That is why a robot which stopped once NEVER restarted.
MEASURED (8x6 day-list seed 3, picker 11, probe rebuilding the graph from PRE-call req_actions):
    (cycle-branch, not-on-longest-path, silenced) on **320 of 320 frozen steps**, target cell EMPTY.
    vs (DAG, on-longest-path, not-silenced) 88 steps when it was moving normally.
NB the decision layer is INNOCENT -- the robot emitted FORWARD into a verified-empty cell every time;
the movement referee overwrote it. Nothing "decided" the block.

### THE FIX -- and the wrong version first
WRONG (do not repeat): simply skipping the self-edge. `req_location()` also returns the own cell for
**TOGGLE_LOAD**, so those agents left the graph entirely, fell into `failed_agents`, and were NOOPed ->
no robot could load or unload a shelf. Freezes went 1.5 -> **13.7 per episode** (15 of 16 agents frozen
at 8x8). The self-loop was doing TWO jobs: poisoning cycle detection (bad) AND keeping
stationary-but-ACTING agents in `commited_agents` (essential).
RIGHT: keep them OUT of the graph but add them DIRECTLY to `commited_agents`.
    if start != target: G.add_edge(start, target)
    else:               commited_agents.add(agent.id)

### RESULTS -- 1,200 paired runs (5 fleets x 2 regimes x 120 seeds), baseline = champion rows in
### results/yield.csv (livelock fix on, self-loop fix off). Both fixes are active in the treatment.
  VALUE       mean **+2.44 (+0.65%)  t=+3.02**  W/L 419/322  differs on 62% of seeds
              daylist +0.99 | stream +3.89   (stream keeps robots busier -> a silenced robot costs more)
  COLLISIONS  431 -> **55  (-87%)**   <- arguably the bigger result; those were pairs permanently
              co-located because NEITHER could move. Unpoisoning the component lets them separate.
  FREEZES     50 -> 27 across the 36-episode scan (4x4 cells now completely clean)

### VERIFICATION -- passes the full shipping protocol
  regime stability (200 half-splits): daylist 82% | stream 100% | pooled 99%   (bar 80%)  PASS
  split-half: seeds 0-59 +2.68 (t=+2.55) | seeds 60-119 +2.20 (t=+1.79)  same sign, same size  PASS
  per-cell: 9/10 positive; the lone negative (daylist 8x8, -1.38) is t=-0.34 = noise. Not carried by
  one fleet -- dropping the two largest cells (stream 6x6 +7.05, stream 9x9 +7.31) does not flip it.
=> **SHIPPED.** First positive result of the session, after a run of nulls and negatives.

### FRAMING FOR THE PAPER -- this is a TESTBED fix, not a smarter world model
The +0.65% is value that a referee bug was destroying, recovered. It is NOT evidence the decision layer
improved. Report as an environment correction. All prior M1 numbers were measured UNDER the defect;
the sweeps are paired and the knobs live in a different layer so the comparisons stand, but absolute
levels shift. **RE-EXAMINE THE FLEET-RATIO RESULT (8x6 > 8x8, +25):** larger fleets build larger
weakly-connected components, so they were poisoned more often -- part of "more robots stopped helping"
may have been this bug, not saturation.
RESIDUAL: freezes are halved, not eliminated (27 remain). A second source exists; not yet traced.

## 2026-08-05 — PRIORITIZED REROUTE (both robots replan, utility order): DECISIVELY NEGATIVE
USER DESIGN: on an impending collision BOTH robots reroute, ordered by combined utility
(value + deadline importance) -- higher utility picks its route first, the other plans around it.
Distinct from the yield rule already killed, where only the LOSER rerouted and the winner kept its path
(that failed by starvation, -5.71 / -6.45). Here the loser still gets a route, just planned second, so
the starvation mechanism should not have applied.
IMPLEMENTED: `Warehouse._utility` = v + 8.0*max(0, 1 - spare/40) -- the SAME combination the controller
uses in `_deadline_score` (URG_W=8, URG_S0=40), so corridor priority and task priority share one scale.
`_prioritized_reroute` behind `env.prioritized_reroute` (default off).

SMOKE (20 episodes, 8x6 + 8x8, both regimes):
  self-loop fix only      value 7879.7   collisions 0   frozen 25
  + prioritized reroute   value 6302.0   collisions 0   frozen 80     <- -20% value, 3x freezes

WHY -- STRUCTURAL, NOT A TUNING PROBLEM. A robot must SIT OUT the tick on which it replans:
`_execute_forward` takes the MOVE from `req_action` but pops the PATH, so replanning a robot already
committed to move desynchronises position from path and the next step requests a cell two squares away
(KeyError in `get_next_micro_action` -- crashed twice before I found this). Therefore "both reroute"
costs TWO robot-ticks per clash instead of one, and at warehouse clash frequencies that compounds into
robots standing still -> freezes tripled.

**THE DECISIVE COLUMN IS COLLISIONS: 0 in BOTH arms.** The self-loop fix already drove collisions to
zero in these cells (they were 431/1200 before it). A collision-avoidance component has nothing left to
arbitrate -- the impending collisions it would resolve have largely stopped happening. The idea is sound
(it is prioritized planning, a standard MAPF technique) but its target was removed by the earlier fix.
STATUS: retained but DORMANT. Champion unchanged.

### RUNNING TALLY OF EXECUTION-LAYER PRIORITY ARMS -- ALL NEGATIVE
  yield: value ranking          -5.71 (t -5.06)      yield: deadline ranking  -6.45 (t -5.40)
  yield: arbitrary control      -1.47 (t -1.44)      prioritized reroute      -20% (smoke)
Consistent story: the ranking-free control is the least bad, and every ranking we impose costs value.
Execution-layer priority does not pay in this system.

## 2026-08-05 — **FLEET-RATIO CLAIM REVALIDATED UNDER THE SELF-LOOP FIX: half of it is refuted**
Re-ran the fleet curve with the fixed movement referee. 8 AGVs x pickers 4..9 x 2 regimes x 120 seeds,
paired by seed (1,440 runs). Motivation: bigger fleets build bigger weakly-connected components, so the
silencing bug hit them harder -- "more robots stopped helping" may have been the bug, not saturation.

STREAM (the effect is real here)                DAYLIST (the effect is GONE here)
  pk 4  325.3   +0.0                              pk 4  417.5  +0.0
  pk 5  345.1  +19.8 (+6.1%)                      pk 5  421.3  +3.8 (+0.9%)
  pk 6  352.6  +27.4 (+8.4%)                      pk 6  420.1  +2.7 (+0.6%)
  pk 7  351.2  +25.9                              pk 7  424.2  +6.7 (+1.6%)
  pk 8  356.7  +31.4 (+9.7%)                      pk 8  418.9  +1.5 (+0.4%)
  pk 9  350.3  +25.0                              pk 9  419.9  +2.4 (+0.6%)
  8x4->8x6 paired: **+27.37  t=+6.09**            8x4->8x6 paired: +2.67  t=+1.36  **NULL**
  8x6 vs 8x8:      -4.03   t=-0.90  NO DIFF       8x6 vs 8x8:      +1.21  t=+0.25  NO DIFF

### SURVIVES: 4 -> 6 pickers is worth **+8.4% on stream** (t=+6.09). Magnitude matches the original
+25 / +7.3%. This is still the largest actionable result in the project.

### REFUTED: **"8x6 beats 8x8 with two fewer robots."** No difference in EITHER regime (t=+0.25,
t=-0.90). The curve is a **PLATEAU, NOT A PEAK** -- it climbs to ~6 pickers and flattens through 9.
The apparent superiority of the smaller fleet was a **BUG ARTIFACT**: larger fleets formed larger
weakly-connected components and so lost proportionally more robots to the self-loop silencing, which
depressed 8x8 relative to 8x6. Predicted before the run; confirmed.
=> DO NOT claim an optimal ratio or a cost-saving "fewer robots is better" story. Claim DIMINISHING
RETURNS WITH A KNEE AT ~6 PICKERS PER 8 AGVs.

### NEW SCOPE LIMIT: the ratio effect is **STREAM-ONLY**. Day-list is flat across the entire 4..9 range
(+0.6%, null). Mechanism: day-list releases every order at t=0, so the binding constraint is total AGV
throughput over the episode, not picker availability; in stream, work arrives over time and picker
responsiveness is what limits banked value. The original claim did not carry this qualifier.

### PAPER ACTION
Restate the fleet result as: "picker count shows diminishing returns with a knee near 6 per 8 AGVs, and
ONLY under streaming arrivals; under a released-at-once day list, picker count is immaterial over 4..9."
Report the plateau, not a peak. Note the prior peak was an artifact of a since-fixed simulator defect.

## 2026-08-05 — M2 INFORMATION MODEL (user's spec) + a gap between spec and implementation
SPEC (user): "you should know robots' paths but nothing else." Robots broadcast the route they CHOSE at
each decision point (a pick or a reroute) -- so intent is always shared, outcome is not -- while
disturbances must be SENSED. Principled split: information that already exists in a computer is
shareable for free; information that exists only in the physical world must be observed.

AS IMPLEMENTED:
  disturbances .............. observed only (belief routing + line-of-sight)      MATCHES SPEC
  other robots' POSITIONS ... fully shared (`find_path` adds AGVS+PICKERS layers) MATCHES SPEC
  other robots' PLANNED PATHS  shared at the DECISION layer ONLY                  **GAP**
`committed_cells` is set per AGV (sim_priority.py:563, congestion_policies.py:76/266/2271) and feeds the
congestion forecast + partner ETA, and the sequencer's rollout simulates every robot forward -- so TASK
CHOICE does reason about where others are going. But `find_path` sees only CURRENT POSITIONS; the
`committed_cells` it reads (warehouse.py:358) is the agent's OWN route (route adherence), not others'.
=> a robot routes around where others ARE, not where they WILL BE. Under the spec it should be able to
plan around a broadcast route before that robot physically arrives.

FIX (agreed, DEFERRED until M2 resolves): have `find_path` treat other agents' `committed_cells` as SOFT
obstacles -- a cost penalty, not a hard block, since a stale plan must not make a cell unreachable. This
is what prioritized planning in MAPF actually does.
DEFERRED BECAUSE it changes the COORDINATION channel and would perturb the M1 baseline; M2's disturbance
results must land against a stable stack first.
COUNTER-ARGUMENT ON RECORD (may make it null): the decision layer already prices inter-robot interference
via the congestion forecast, so a router-level penalty is a SECOND INVOICE for the same thing -- exactly
the mechanism that made W_SYNC null (my_wait already inside `finish`). Predict a small or null effect.
PAPER NOTE: until this lands, "robots know each other's paths" OVERSTATES the router. State it precisely.

## 2026-08-06 — **THE TIMESCALE BUG**: the simulator ran two incompatible clocks (user caught it)

### THE CONTRADICTION
A step is ONE CELL of robot travel. That pins its real duration: `step = cell_size / robot_speed`.
  ROBOT CLOCK (grounded): Robotnik RB-KAIROS+ 1.5 m/s, 1 m cells, ~52 m task cycle -> ~60-65 s/task
    (docs/FINDINGS.md:209). MEASURED task duration = ~50 steps.  => **1 step ~ 1.2 s**
  DEMAND CLOCK (assumed): `DemandModel(period=250)` claims 250 steps = one day  => **1 step ~ 5.8 min**
**They disagree by ~280x, and both were live in the code.**
Consequences of the demand clock: a robot crawls 1 m every 6 min (~250x below spec), or cells become
259 m and the "large" warehouse is 9 km x 5.7 km. Neither survives the Robotnik grounding.

### WHY GEOMETRY CANNOT FIX IT (all three user proposals checked)
  bigger cells   -> warehouse becomes kilometres wide (physical size is fixed at ~35x22 m)
  more/smaller cells or partial crossings -> steps get SHORTER, episode covers LESS time
  bigger warehouse -> tasks take more steps, but step duration is unchanged -> still 10 min
Robot speed is the only free variable and it is the one thing properly calibrated. The constraint is
forced by the research question: cell-level routing IS the contribution, so a step must be ~1 cell.
  ARITHMETIC: a real day = 86,400 s / 1.2 s = **72,000 steps** = 144x the episode. A 500-step episode
  holds 500/50 = **10 task cycles**; a real day holds ~1,400. An episode is ~0.7% of a day.

### THE FIX -- put the day ACROSS episodes, not inside one
`DemandModel(window_index=i, n_windows=144, day_steps=72_000)`: seed i = the i-th 10-minute slot of a
24 h day; the diurnal term advances over `day_steps`, drifting only **0.69%** within an episode (flat,
which is what 10 minutes of a real day looks like). Within-episode variation is carried by the HAWKES
burst process -- the mechanism the literature actually measures at this timescale (arXiv 2607.04866,
"Bursty Arrivals, Smooth Sojourns"). Each mechanism now runs at the timescale it was measured at.
  **144 x 500 steps x 1.2 s = 86,400 s = EXACTLY 24 h** (user's arithmetic -- 144, not 120).
  VERIFIED: legacy path (window_index=None) bit-identical; new path rate 1.000->1.035 within an
  episode, 0.200..1.800 across windows; warm start scales 2 (6 p.m.) .. 22 (6 a.m.).

### WARM START, and why episodes are NOT chained
`warm_start_n()` scales the opening backlog by time of day, derived from the seed/phase ONLY.
Chaining episodes end-to-start (user's suggestion) was rejected: it would reintroduce POLICY-DEPENDENT
state -- a policy that clears more backlog hands itself an easier next window -- which is exactly the
failure that forced `exogenous=True` and invalidated a VoPI run. It would also destroy sample
independence (144 chained windows = one autocorrelated trajectory, not 144 observations), inflating
every |t| in the project.

### CONSEQUENCES TO PROPAGATE
1. **RETRACTED**: my "deadlines are realistic (8-20 min)" claim used the wrong clock. Report deadlines
   as the SCALE-FREE RATIO instead: window / task_duration = **2.56 day-list, 1.94 stream** (measured),
   vs a real ~2-4 (18-23 min pick SLA over a 3-8 min pick + travel). Sim is inside the band, stream at
   the demanding end. Never quote deadlines in minutes.
2. **SPLIT-HALF MUST BECOME EVENS vs ODDS.** With seeds tiling the day, 0-71 vs 72-143 is two halves of
   the DAY, not two random halves. Silently invalidates the verification protocol if not changed.
3. **"day-list" is now a misnomer** at a 10-minute episode. The regime (whole batch released at once,
   fully known) is real practice: **WAVE PICKING**. Rename day-list -> wave.
4. **Seed count 120 -> 144** becomes physical, not conventional: "each experiment simulates one full
   day as 144 ten-minute windows."
5. Base rate should be expressed as `utilisation x fleet_capacity / horizon` (currently ~46%
   utilisation) rather than a bare 0.075 -- utilisation is a number operations publish.

### THE GATE, RUNNING NOW (`scripts/exp_urgw_newclock.py`, 5,760 runs)
`URG_W = 8` on stream is the ONLY behavioural rule M1 produced, and it was tuned under the mis-scaled
sinusoid -- it exists BECAUSE stream's future is uncertain. Sweeping URG_W {0,4,8,12} x 5 fleets x 144
seeds under BOTH clocks, paired. If 8 survives, the timescale fix is a free realism upgrade. If not,
the headline regime rule was an artifact of a mis-scaled parameter.

## 2026-08-06 — DESIGN PROPERTY: the stack predicts carefully to CHOOSE, optimistically to ADMIT
Where the delay EMA is and is not applied is not an oversight -- it is a coherent asymmetry, and the
measurements support it.
  STEP 6 (rollout, `_sim_core`): `_sim_step_bias` IS applied at all three completion sites -- every
    imagined task completion (line 1707), the pinned first move (1722), and the rendezvous (1750). The
    imagined trajectory therefore runs on a CALIBRATED clock, not an empty-world one.
  STEP 5 (funnel makeable/doomed): `_finish_delay` returns **0.0** on the champion (the congestion
    subclass would return FINISH_CONG_K * route_cong, but FINISH_CONG_K is unset). So admission is
    decided on RAW GEOMETRY plus the flat LOAD_TIME=5 pad.
=> **The system predicts carefully when deciding WHICH task, and deliberately optimistically when
deciding WHETHER a task is possible.** The rollout wants realism because it is comparing options; the
admission filter wants optimism because being wrong in the pessimistic direction is UNRECOVERABLE -- a
task never attempted banks zero for certain, whereas one attempted and missed banks zero anyway. The
asymmetry is empirical, not just theoretical: the `emapad` arm (EMA added to step 5) measured **-0.3%**
because accurate pessimism reclassified marginal tasks as doomed so they were never attempted.

## 2026-08-06 — REALISM AUDIT: parameters DELIBERATELY NOT CHECKED (recorded so they can be revisited)
Split that governs this list: **WORLD parameters** define the environment being measured and must be
realistic; **PLANNER parameters** are the design being tuned and realism does not apply to them.

### DEFERRED BY DECISION (user, 2026-08-06) -- not errors, just unexamined
| parameter | value | what it controls | why deferred |
|---|---|---|---|
| `zipf_s` | 1.1 | SKU popularity skew | mechanism literature-backed, magnitude tuned |
| `hawkes_p / jump / decay` | .006 / .4 / .90 | arrival burstiness | same -- shape cited, values chosen |
| `n_hot` | 3 | number of spatial hot zones for fast movers | real practice (velocity slotting); count arbitrary |
| `slot_jitter` | 6.0 | how IMPERFECT velocity slotting is (0 = perfect) | real slotting is imperfect; blur amount arbitrary |
| `rush_frac` | 0.20 | share of orders in the expedited tier | real concept (same-day vs standard); share a guess |
| `rush_value_mult` | 1.6 | expedited orders are worth more | plausible, uncited |
| battery constants | steps_per_charge 300 etc. | charge/discharge | USER: explicitly out of scope |
| AGV : shelf ratio | 1 : 30 (large map) | travel distance + SKU diversity | no public figure; and see objection below |

**OBJECTION ON RECORD to fixing the AGV:shelf ratio.** The fleet-size experiments vary AGVs 4..9 on a
FIXED map. If shelf count scales with AGV count the map changes with the fleet and fleet comparisons
become uninterpretable -- the +8.4% ratio result would be void. Capacity is now dialled by
`utilisation`; shelf count controls travel distance and SKU diversity, NOT capacity. Keep the map fixed.

### NOT A REALISM QUESTION AT ALL -- planner-side, these are the thing being tuned
`DECAY_G` 0.98 · `URG_S0` 40 · `SCREEN_KEEP` 15 · `K_ROUTES` 3 · `LOAD_TIME` 5 (a planner PAD, not
physical time) · `SEQ_DEPTH` · `CONG_*` · `W_SYNC` · `RATE_ALPHA` · `TIER_GAP`.

### STATION COUNT -- derived, not cited (no public ratio exists; searched 2026-08-06)
Sized by THROUGHPUT BALANCE, which is how warehouses are actually specced:
  measured ~52 deliveries / 500-step episode (8 AGVs, utilisation 0.80)
  at ~0.8 s/step -> 400 s -> **468 pods/hour**; ~1.5 orders/pod -> **~700 picks/hour**
  station rate 300-600 picks/hour (manufacturer figures, docs/FINDINGS.md)
  => **1.2-2.3 stations required. The large map has 10 -- over-provisioned ~5x.**
CONSEQUENCE: stations can never bottleneck, so the ONLY place a robot can wait is the picker handoff --
which is very likely why the value-loss autopsy attributes **75% of loss to picker wait**. That headline
may be an artifact of station over-provisioning, not a property of the problem.

### VALUE SPREAD -- flagged as MATTERING, contra first impression
Absolute scale is irrelevant (linear objective). The SPREAD is not: banked value is a SUM OF DISCRETE
TASK VALUES, so a narrow 1-15 range makes different task orderings produce IDENTICAL sums. Measured:
**48.6% of `_pick_winner` calls end TIED, mean tie size 5.09.** Wider/skewed values -> fewer sum
collisions -> the rollout separates candidates more often -> the arbitrary funnel tie-break decides
fewer commitments. Ties are where the **+3.6% oracle headroom** was localised (high beat-rates on bad
seeds = champion in a poor basin). Real e-commerce order values are lognormal over orders of magnitude,
not 15x. So this is not cosmetic -- it plausibly moves the largest measured headroom in the project.

## 2026-08-06 — GEOMETRY + SERVICE TIME: two world constants that were wrong, both now fixable

### A) MAP GEOMETRY — the floor was less than half as dense as a real pod field
RESEARCH (Kiva/Amazon Robotics pod fields):
  * pod ~ **1 x 1 m**; drive unit 75 x 60 cm and travels UNDERNEATH the pod
    -> our 1 m cell and one-robot-per-cell are CORRECT, no change needed
  * pods arranged in **clusters of 3x6, 3x7, 4x6, 4x7** with **one-way lanes** between them
  * storage space utilisation **~65%** (robots do not need human-width aisles)
OURS (measured): `column_width` and `_highway_lanes` were HARDCODED at 2 -> 2-wide blocks with 2-cell
lanes everywhere -> **31% storage, 69% open aisle.**
=> A floor that is 69% aisle makes congestion trivially avoidable and one-cell debris free to route
around. This is a plausible contributor to the M2 disturbance nulls and to congestion knobs measuring
weak: there is nearly always a parallel lane.

FIX: both parameterised (defaults unchanged, so every existing map and result is bit-identical).
New `*dense-*` env ids registered alongside: `column_width=4, highway_lanes=1, column_height=6`
= a 4x6 Kiva cluster. Verified: **large 35x22 / 240 shelves / 31% storage -> largedense 25x26 /
360 shelves / 55% storage.** (55% not 65% because the station apron and border lanes are fixed cost.)

FIRST MEASUREMENT, 3 seeds, day-list, champion:
  sparse 31%   value 1416.4   deliveries 171
  dense  55%   value  835.7   deliveries  91      <- throughput HALVES
Narrow lanes create real congestion the sparse floor never had. That is the regime the congestion
forecast was designed for, so the contribution may be worth much more on a realistic map.

**REMAINING GEOMETRY GAP: lanes are BIDIRECTIONAL; real pod fields use ONE-WAY lanes.** Dense + 2-way
1-cell lanes is HARSHER than reality, because real systems design head-on conflicts out. Do not quote
the dense throughput drop as a realism result until one-way routing exists -- some of it is an artifact
of a traffic rule real warehouses do not use.

### B) SERVICE TIME — the simulator spent ZERO time on every physical operation
Three operations, all instantaneous before today:
| operation | was | real | source |
|---|---|---|---|
| picker load (arm cycle) | 0 s | ~5-10 s | RB-KAIROS+ = base + UR arm; pick-and-place cycle |
| pod handoff / unload | 0 s | 10-15 s | Robotnik cycle (OUR estimate, not published) |
| station pick per item | 0 s | 6-12 s | manufacturer station rates 300-600 picks/hour |
The picker one matters most in principle: picker rendezvous is **75% of all lost value**, yet the one
operation a picker exists to perform cost nothing -- its throughput was effectively infinite and only
its TRAVEL was priced.
FIXED (opt-in): `env.picker_service_steps` (holds BOTH picker and AGV for the arm cycle) and
`env.station_service_steps` (holds the AGV for service_steps x items, since one pod trip serves every
order pending on that shelf).

MEASURED, 3 seeds, day-list:
  sparse  no service 1416.4/171 | +picker8 1396.4/170 (-1.4%) | +picker8+station6 1272.1/156 (-10.2%)
  dense   no service  835.7/ 91 | +picker8  850.0/ 92 (+1.7%) | +picker8+station6  885.9/ 94 (+6.0%)
SURPRISE (n=3, DO NOT QUOTE): on the DENSE map service time slightly IMPROVES value. Plausible
mechanism -- on a congested floor, forced pauses act as traffic METERING: fewer robots moving at once
means less mutual blocking. Needs a proper run before it is believed.
NOTE picker service at 8 steps is a modest load: ~57 deliveries/episode over 6 pickers = ~9.5 handoffs
each x 8 steps = ~15% of picker time. It would need to be larger to bind hard.

### C) STATION COUNT still unresolved
Dense map has 20 stations for 360 shelves. Throughput balance says **1.2-2.3 stations** suffice for an
8-AGV fleet. Station count is DERIVED FROM THE LAYOUT (bottom-row non-highway cells), so it cannot be
set independently without a generator change. Until then stations cannot bottleneck on either map.

## 2026-08-06 — ONE-WAY LANES built + measured; and the DENSITY TARGET was the wrong reference class

### CORRECTION: 65% was Kiva's number, and Kiva is not our system
Kiva/Amazon pod fields hit ~65% because NO PICKING HAPPENS IN THE FIELD -- robots drive under pods and
everything is picked at stations. Ours has IN-AISLE RENDEZVOUS (a picker robot meets the AGV at the
shelf), which is a COLLABORATIVE PICKING system. Correct benchmark:
  conventional racking w/ access aisles   **40-60% storage** (aisles = 40-50% of floor)
  aisle widths: forklift 3.7 m · VNA 1.8 m · omnidirectional AMR **1.1 m** · narrow-aisle AMR 2.1 m
  Kiva pod field (no in-field picking)     ~65%
  ASRS (no aisles at all)                  80-90%
=> TARGET FOR US IS 40-60%. The dense map at **55% is squarely inside it**; the original **31% was
BELOW the realistic range**. The fix was right, my justification was borrowed from the wrong system.
Also validates the cell size: 1 m cell -> 1-cell lane = 1 m ~ the omnidirectional AMR minimum (1.1 m);
2-cell lane = 2 m ~ the narrow-aisle figure (2.1 m). Both are REAL configurations -- they just describe
DIFFERENT warehouses, so the paper must state which is being claimed.

### ONE-WAY LANES: implemented, and they COST 16% on this map
`env.one_way` + `_build_lane_directions()` + `_astar_directed()`. Alternating Manhattan scheme:
consecutive highway columns run +y/-y, consecutive rows +x/-x, intersections omnidirectional so robots
can always turn. `pyastar2d` scores NODES and cannot express a one-way EDGE, so this needed a small
heapq A* with a per-move direction test (grid is ~650 cells; cost is irrelevant next to the rollout).
MEASURED (3 seeds, day-list, champion):
  sparse 31% bidirectional  1416.4 / 171 deliveries
  dense  55% bidirectional   835.7 /  91
  dense  55% ONE-WAY         708.2 /  76      <- a FURTHER -16%
WHY IT LOSES: one-way trades CONFLICT cost for DETOUR cost. A robot wanting to travel against a lane
must go around. Real pod fields make that trade because at THEIR robot density head-on conflicts
dominate. At **8 robots on 650 cells** conflicts are rare, so we pay the detours and get nothing back.
=> The RULE is realistic; the BENEFIT needs a robot density we do not have. Do not enable it by default
and do not claim "we model one-way lanes" without this caveat -- it would be true and silently cost 16%.
REVISIT at high fleet density (the crossover is where conflict cost exceeds detour cost).

### STATUS OF THE GEOMETRY FIXES
  parameterised `column_width` / `highway_lanes`   DONE, defaults unchanged, `*dense-*` maps registered
  one-way lanes                                    DONE, opt-in `env.one_way`, measured, NOT default
  station count (10-20 vs 1.2-2.3 derived)         BLOCKED: derived from the layout's bottom row
  bidirectional vs one-way choice                  now a documented modelling decision, not an omission

## 2026-08-06 — REALISM PASS COMPLETE: every world CONSTANT checked, fixed, or documented

### STEP DURATION -- computed from kinematics, not read off a spec sheet
Straight runs between turns measured from real episodes: **p25 1 · MED 3 · p75 8 · max 34 cells**.
Runs are SHORT, so a robot rarely reaches cruise. Trapezoidal/triangular profile per run with
`a = 0.8 m/s^2` (published typical AMR decel) and `vmax = 1.2 m/s` (laden; RB-KAIROS+ 1.5 m/s unladen,
max drops with payload; an AGV under a pod carries up to 450 kg):
    => **1 tick = 1.069 s per cell crossed**   vs my earlier naive 0.667 s (= 1 m / 1.5 m/s)
**The earlier figure was 38% too fast** because it assumed every metre was driven at top speed. With
turns every ~3 m most of a run is accelerating and braking.
CONSEQUENCE for seed arithmetic: episode = 500 x 1.069 = 535 s = **8.9 min** at 1 m cells ->
**162 seeds ~ 1 day**; 108 seeds ~ 0.67 day. At 4 m cells 108 seeds ~ 2.4 days (no longer clean).
NB ignore any "seconds per agent-step" figure that divides drive time across idle agents -- a tick
lasts one cell-crossing regardless of how many robots are waiting.

### VALUE SPREAD -- fixed, but MY MECHANISM CLAIM WAS OVERSTATED
`value_dist='lognormal'` (+ `value_median`, `value_sigma`); uniform remains the default.
  uniform 1-15     p10 2.5  MED 8.1  p90 13.6  max  18.5   p90/p10  5.3
  lognormal s=1.0  p10 2.4  MED 7.9  p90 23.4  max 177.9   p90/p10  9.6
  lognormal s=1.3  p10 1.7  MED 7.8  p90 32.3  max 200.0   p90/p10 19.0
TIE-RATE TEST (5 seeds) -- the whole justification:
  uniform 55.0% (mean size 4.78) | lognormal s=1.0 **45.7%** (4.75) | lognormal s=1.3 50.0% (4.94)
It helps but is **NOT MONOTONIC**, and ties stay ~half of all decisions. So most ties are NOT caused by
coarse value granularity -- they are STRUCTURAL: the rollout banks the same SET of tasks whatever the
first move, because the horizon completes the same work either way. Fix it for realism; do NOT expect
it to unlock the tie-break headroom, which is what I implied.

### STATION COUNT -- fixed via `n_stations`, and adding robots was the WRONG lever
Station count was an ACCIDENT of the layout (every non-highway bottom-row cell became a station) ->
10 (large) / 20 (dense). Throughput balance: ~52 deliveries/episode -> ~468 pods/hour -> ~700
picks/hour at ~1.5 orders/pod, against 300-600 picks/hour per station => **1.2-2.3 stations suffice**.
`n_stations` now evenly subsamples the bottom row; dense map set to **3**.
**REJECTED: raising robot count to saturate stations.** Saturating 10 stations needs ~35-70 AGVs;
20 needs ~70-140. On ~290 lane cells that is ~24% occupancy -> gridlock. Congestion would bind long
before stations, and it would void the fleet-ratio study and every knob tuned at 8x6.

### CUMULATIVE EFFECT OF THE REALISM PASS (3 seeds, day-list, champion)
  ORIGINAL      31% storage, 10 stations, uniform values, no service   1416.4 value / **171 deliveries**
  + geometry    55% storage, 3 stations                                 861.9 /  95
  + lognormal values                                                   1231.6 /  76
  + service times (picker 8, station 6/item) = FULLY REALISTIC          937.4 /  **58**
**Throughput falls 171 -> 58 deliveries, a 66% reduction.** (Value is NOT comparable across value
distributions -- lognormal has a longer tail, so use deliveries as the throughput metric.)
=> The simulator was roughly **3x too productive**. Every M1 number -- knob table, fleet ratio, oracle
ceiling, disturbance nulls -- was measured on that world. None of them transfer. The realism work has
invalidated the baseline rather than improved it, and the next step is re-establishing the champion on
the corrected world BEFORE any weight is re-tuned.

## 2026-08-06 — LIMITATION ON RECORD: the corrected-world knob re-run is 3 fleets, not the 36-cell grid
M1's original sweeps: **36 cells (AGV 4-9 x picker 4-9) x 120 seeds = 4,320 paired runs per arm.**
The corrected-world re-run:  **3 fleets (4x4, 8x6, 9x9) x 2 regimes x 162 seeds = 486 per arm.**
=> ~9x less data per arm, and only 3 of 36 ratio cells.
REASON: the corrected world is ~3x slower per run (directed A* for one-way lanes, denser grid). The full
36-cell grid at 162 seeds is ~110,000 runs ~ 68 h per knob set. Accepted for now on timeline grounds
(user, 2026-08-06).
TWO CONSEQUENCES THAT MUST BE STATED IN THE PAPER:
 1. **Ratio-dependence is undetectable at 3 cells.** URG_W's regime rule and the whole space-vs-future
    principle came from seeing behaviour ACROSS the ratio grid. A knob worth +5% at 4x9 and -5% at 9x4
    reads as null when pooled over three cells.
 2. **Underpowered vs the original.** 486 vs 4,320 paired runs is ~3x worse resolvable effect size, so
    "no knob clears |t|>=3 on the corrected world" partly reflects LESS DATA, not only smaller effects.
    Do not report the corrected-world nulls as equally strong evidence to M1's nulls.
PLANNED IF TIME ALLOWS: run only the CONFIRMED knobs across the full ratio grid (2 knobs x 2 values x
36 cells x 162 seeds ~ 23,000 runs ~ 14 h) rather than re-sweeping everything.

## 2026-08-08 — the "deadlock" was one robot refusing an open door

**The freeze detector was wrong.** It counted position changes across ALL agents, and pickers keep
shuffling during a jam, so a total AGV deadlock registered as "moving". Measured per-seed:

| seed | delivered | total moves | longest zero-move run | moving-but-not-delivering |
|------|-----------|-------------|-----------------------|---------------------------|
| 13   | 2         | 1084        | 17 steps              | 119 steps                 |
| 14   | 3         | 2248        | **2 steps**           | 90 steps                  |

Seed 14 moves 6.67 robots/step for the whole tail with ZERO frozen steps and still delivers 3. So
there are TWO distinct failures, and eight previous fixes all targeted the wrong one:
  * seed 13 = true AGV deadlock (7 of 8 carrying AGVs, distance-to-target CONSTANT at 26/37/36/36/40/
    37/38 for 150 steps, zero retargets)
  * seed 14 = livelock/churn (AGVs move constantly, drop paths 23-57 times, distance oscillates)

**Root cause of the deadlock (seed 13, t=400, stations at (1,24),(5,24),(11,24)):**
AGV 1 stood ON station (5,24) with its path insisting on exit cell (5,23), held by AGV 7, which wanted
the station. Nose-to-nose. AGVs 3/5/6/8 were correctly held off the approach cells by the headway rule,
AGV 2 behind them. **Cells (4,24) and (6,24) were FREE the entire time** — AGV 1 had two open doors and
never looked, because `find_path` runs once and a robot only replans when the stuck counter trips.

Not a blocked warehouse. A robot refusing an open door.

**FIX (`env.station_exit_priority`).** The station occupant is the one robot that MUST move — everyone
else is waiting on it — so give it first claim on a free neighbour: replan around the blocker, else
step SIDEWAYS along the station row. Horizontal only (user's call, and correct): the stations occupy one
row and are approached from the aisle above, so a perpendicular sidestep puts the robot off the station
line and its route continuation becomes DIAGONAL, which is not executable. It crashed with
`KeyError: (-1,-1)` on the first run for exactly that reason. The desync trap also bit a FIFTH time —
prepending the sidestep leaves `[sidestep, old_first]` diagonal; the continuation must be rebuilt from
the sidestep cell.

**Result (48 paired seeds, dense map, on-time value):**
    baseline (headway)        906.57   frozen AGVs 61   dead episodes 9/48
    + station exit priority   951.94   frozen AGVs 12   dead episodes 3/48
    +5.00%, t=+2.65, 22 wins / 6 losses / 20 ties

**NEGATIVE — no-seal-in (`env.station_no_seal`), rejected.** Refusing to enter a station with no free
neighbour: 638 -> 444 value, frozen AGVs 23 -> 89. Too strict — the queue is legitimately occupied most
of the time, so nobody ever delivers. The escape must be guaranteed at EXIT time, not demanded at entry.
Kept opt-in and off.

## 2026-08-08 (cont.) — permanent deadlock ELIMINATED: the unload rule

**Root cause.** `_execute_unload` (wwm_sim/warehouse.py, inherited verbatim from upstream
tarware/warehouse.py:554) lets an AGV put a pod back into storage ONLY while a picker stands on that
exact cell:

    if not self._is_highway(agent.x, agent.y):
        if (agent.type == AgentType.AGV and picker_id) or agent.type == AgentType.AGENT:

If no picker is ever dispatched to that RETURN rendezvous, the AGV requests TOGGLE_LOAD every step for
the rest of the episode and the unload silently does nothing. It holds the pod forever, busy=True,
plen=0, and is never reassigned.

MEASURED (seed 100, peak demand, t=460-462): AGVs 1 and 6 parked on storage cells (7,1) and (8,3) with
no picker present, requesting TOGGLE_LOAD every step to the end of the episode. The other six AGVs were
each co-located with a picker and had unloaded normally. Episode delivered 1 order, queue_left=0 --
the queue had drained by EXPIRY, not delivery.

Also unphysical: a Kiva-class drive unit lifts and lowers its own pod; the picker exists to transfer
ITEMS. Setting a pod down is a drive-unit operation. `env.free_pod_return` keeps the picker requirement
for the PICK (the real rendezvous constraint) and drops it for the return.

**Result (144 paired seeds, dense map):**
                        on-time value   frozen AGVs   dead episodes
    baseline                   727.82           138        67/144
    + free_pod_return          727.55             0         0/144
    paired t = -0.10 (-0.04%, null)   deliveries 476 -> 493

PERMANENT DEADLOCK IS GONE (0/144) AT ZERO VALUE COST. Value is flat because stranded AGVs mostly
stranded late, after the queue had drained by expiry -- the freeze cost liveness, not measured value,
which is exactly why eight earlier fixes chasing value never located it.

### Three hypotheses killed on the way (all measured, all negative)
1. **Dock capacity** -- n_stations 3/4/5/6 at peak: frozen AGVs 119/121/120/122, dead 62/62/61/64.
   No effect on deadlock whatsoever. Value +2.25 t at 6 stations (throughput only).
2. **Aisle width / passing places** -- lanes1 119 frozen, lanes2 114, lanes2+one-way 110, width1 136.
   Doubling lane width (+60% cells) buys 4%. The jam was never about room to pass.
3. **WIP cap (CONWIP)** -- cap concurrent released work below fleet size. Deadlock falls monotonically
   (frozen 119 -> 85 -> 48 -> 53 -> 41; dead 62 -> 55 -> 36 -> 30 -> 25 of 72) but on-time value falls
   monotonically too (500 -> 486 -> 471 -> 440 -> 414, t = -2.98 to -6.21) and deliveries collapse
   199 -> 64. Rejected as a fix, but it was the decisive CLUE: the only lever that moved deadlock was
   the number of LOADED robots, which is what led to the stranded-carrier discovery.

### Method note
The old freeze detector counted position changes across ALL agents. Pickers keep shuffling during a
jam, so a fully deadlocked AGV fleet registered as "moving" -- the true rate was 51% of episodes, not
2/24. Every fix screened before this was screened against a blind instrument. Measure the failing
SUBSYSTEM, not the aggregate.

**STANDING CONFIG:** station_headway + SIM_DOCK_RES + station_exit_priority + free_pod_return.

## 2026-08-08 (cont.) — after the fix: what is left, and what does not work

**Both liveness rules are still load-bearing** (peak, free_pod_return ON in every arm):

    arm                     mean value  stalled-steps  frozen AGVs  dead episodes      t
    standing                    499.69          93275            0        0/72          -
    no headway                  379.05         154750          242       33/72      -6.51
    no exit prio                493.02          97576            8        1/72      -2.10
    neither                     361.87         168551          285       40/72      -7.44
    pickers_free (oracle)       506.87          73907            0        0/72      +1.76

Removing headway brings deadlock straight back (33/72) EVEN WITH free_pod_return. So there are TWO
independent permanent-deadlock mechanisms and both fixes are required:
  1. station nose-to-nose (occupant sealed in by an arrival) -> station_headway + station_exit_priority
  2. stranded carrier (no picker at the return rendezvous)   -> free_pod_return

**The picker constraint has stopped being the bottleneck.** The pickers_free oracle is now worth only
+1.4% (t=+1.76) at peak. Historically picker rendezvous was ~75% of all lost value. At peak demand the
system is now EXPIRY-bound (queues drain by deadline, not delivery), so relieving the picker does
almost nothing. Re-measure the oracle off-peak before trusting any picker-side investment.

### Where the stalled time actually goes (24 peak episodes, standing config)
61.2% of working AGV-time is spent not moving, but most of that is real work:

    load/unload (real action)                13963  31.5%
    service (picker/station dwell)           12358  27.9%
    held by rule (headway / exit priority)    5798  13.1%
    rotating (real action)                    5676  12.8%
    referee silenced (next cell taken)        2500   5.6%
    referee silenced (next cell FREE)         2279   5.1%
    no path: carrying, idle                   1407   3.2%
    held: next cell occupied                   364   0.8%

CAVEAT on the top row: an AGV waiting at a pod for a picker re-requests TOGGLE_LOAD every step, and
`_execute_load` silently does nothing while no picker is present -- so part of that 31.5% is picker
WAITING misfiled as action. The oracle above bounds what fixing it could be worth (+1.4% at peak).

### Negative results this session (all measured, none shipped)
* `station_no_seal` (refuse to enter a station with no free neighbour): 638 -> 444 value, frozen 23 -> 89.
  Too strict; the queue is legitimately occupied most of the time so nobody delivers.
* `blocked_replan` / `stuck_avoid_agents` (generalise exit priority to any blocked AGV, and repath
  stuck-released agents around robots): inert while deadlock dominated, and NEGATIVE after the fix
  (t = -0.84 / -2.09 / -1.02 / -1.81); stalled steps unchanged or worse.
* `commit_priority` (priority-ordered commit replacing the legacy cycle+DAG resolver) RETESTED on the
  repaired world: arbitrary -1.04, value -2.22, deadline -1.51; stalled steps 93275 -> 97-103k, and it
  reintroduces 1-2 dead episodes. This replicates the earlier negative with the confounds removed, so
  it is now a much stronger result: the legacy resolver's blanket silencing costs 2279 steps per 24
  episodes, and every attempt to reclaim them costs more elsewhere.

## 2026-08-08 (cont.) — the stall ceiling: pod-waiting is picker TRAVEL, not dispatch

**Correction to the entry above.** The decomposition filed 31.5% of non-moving AGV-time under
"load/unload (real action)". That was wrong. Checking whether each TOGGLE_LOAD actually changed the
carrying state: **91.2% of those steps are no-ops** -- an AGV parked at a pod re-requesting a load that
does nothing because no picker is present. So AGVs waiting at pods is ~29% of ALL non-moving AGV-time,
the single largest addressable stall cause, not legitimate work.

**Oracle headroom is regime-dependent** (pickers_free, 72 seeds per half):

    OFF-PEAK   baseline 955.41 -> oracle 991.10   +3.74%  t=+4.22   waiting toggles 43295 -> 2348
    PEAK       baseline 499.69 -> oracle 506.87   +1.44%  t=+1.76   waiting toggles 29595 -> 1538

So the earlier claim "the picker constraint has stopped being the bottleneck" was drawn from the PEAK
number alone and is wrong off-peak, where it is worth 3.74% and clearly significant. At peak the queue
drains by deadline expiry, so relieving any bottleneck buys little -- that is a property of the regime,
not of the picker.

**Why re-scoring cannot capture it.** `_picker_score` is called only ~94 times per 500-step episode,
all at task-creation time. Picker assignment is ONE-SHOT and never revisited, so by the time an AGV has
been parked for 40 steps there is no decision left to influence. Confirmed by instrumenting a
sunk-wait-boosted scorer (`_WaitAwarePicker`, opt-in `WAIT_W`, left at 0/inert): of 94 scoring calls,
only 3 saw any AGV already waiting, max 2 steps. Value and waiting-toggle counts were unchanged.
Filed as a NEGATIVE with a mechanism: the lever was in the right place, the cadence was wrong.

**What the waiting actually is** (24 off-peak episodes, 16494 pod-waiting AGV-steps):

    A: a picker IS committed and travelling   15319  92.9%   n=1134  median 4   p90 34  max 205
    B: NO picker assigned at all               1175   7.1%   n=32    median 32  p90 72  max 136

>>> SUPERSEDED: these two rows used the contaminated "waiting" test and counted idle robots. The
>>> corrected split is 98.7 / 1.3 -- see "CORRECTION: pod-wait split is 98.7 / 1.3" further down. The
>>> qualitative conclusion (travel dominates) survives and strengthens; the case-B figure does not.

So 92.9% is picker TRAVEL TIME -- a capacity/geometry property, irreducible by dispatch policy, and
mostly short (median 4 steps). Case B is a genuine dispatch gap and the waits are long (median 32), but
it is only 7.1% of the loss and just 32 occurrences per 24 episodes.

**Conclusion.** The pickers_free oracle's +3.74% is essentially the value of abolishing picker travel,
which no assignment policy can do. The addressable slice is the 7.1% dispatch gaps plus better ETA
matching in the case-A tail (p90=34 vs median=4). Any picker-side work should be aimed at those two,
and should be measured OFF-PEAK -- at peak the regime hides everything.

## 2026-08-08 (cont.) — the clash rerouter: why a committed picker never arrives

**Trace.** Worst genuine pod-wait in seeds 1-24: seed 11, AGV 2, **138 consecutive steps** requesting a
load at (1,13). Picker 13 was committed to that exact cell for 166 of the 169 steps -- not a dispatch
gap. Its path END was (1,13) on 139/139 sampled steps, so it was always correctly targeted. It moved on
78% of steps and was silenced on only 5%. It simply never arrived.

Cause: **all four of its reroutes came from the clash handler at `resolve_move_conflict`** (the live
one at ~line 1028, NOT the flag-gated `_prioritized_reroute`):

    t=365  path 10 -> 30      t=391  path 10 -> 46
    t=438  path  6 -> 36      t=463  path 18 -> 22        (+90 steps of detour total)

Three times it was 6-10 steps from the waiting AGV and was sent 30-46 steps away. `find_path` there
runs with care_for_agents=True, which treats every robot as a PERMANENT wall -- a robot that will step
aside in two ticks is routed around like a shelf, and pickers are confined to the sparse highway
network, so "around" is most of the way across the warehouse. It walks the detour, returns, clashes,
repeats.

**NEGATIVE: wait-vs-reroute ranked by value rate (`env.clash_choose`), rejected.**
USER IDEA, and the right formulation -- rank the two options by v/T rather than capping the detour with
an arbitrary ratio (T_reroute = len(new route); T_wait = blocker clearance + len(existing route)); it
also gives Part B the comparison it needs to price a support action. Verified to FIRE: with it on, all
four of picker 13's catastrophic reroutes are suppressed. But measured over 144 seeds x 4 arms:

    arm                 mean value  delivered  pod-wait steps  frozen AGVs      t
    off (always reroute)    727.55        493           67571            0      -
    clash_wait_est 8        718.35        471           80922           18  -1.84
    clash_wait_est 20       718.75        469           81108           18  -1.76
    clash_wait_est 60       718.75        469           81108           18  -1.76
    (peak half: t = -2.96)

Pod-waiting goes UP (67.5k -> 81k) and permanent deadlock RETURNS (0 -> 18 frozen AGVs). The ugly
detour is load-bearing: rerouting is what breaks clashes apart, and when robots wait instead they sit
in each other's way and the standoffs re-form.

DIAGNOSIS of why: the three wait_est values give near-identical results, so the decision never actually
depends on the blocker-clearance guess -- it is dominated by `len(agent.path)`. When a robot is close to
its goal T_wait beats T_reroute almost always, so the rule degenerates into "wait whenever near", which
is exactly when yielding matters most. The RANKING is sound; the weak term is the wait-side ETA, which
assumes a blocker holding a path clears next tick when that blocker may itself be blocked. A
blocked-blocker-aware clearance estimate is the thing to try before discarding the idea.

Kept opt-in and OFF. Standing config unchanged.

## 2026-08-08 (cont.) — one-waiter clash rule (USER IDEA): polarity settled, still not shippable

Refinement of the wait-vs-reroute idea: **exactly one robot waits, not both** -- pick by proximity.
This diagnosed a real bug in the first version. Ranking wait-vs-reroute INDEPENDENTLY per robot let
BOTH sides of a clash choose "wait" (each is near its own goal, so each prefers holding its route), and
waiting resets `fixing_clash`, so nothing stopped the second robot reaching the same conclusion.
Standoff. That, not the idea, is what drove pod-waiting to 81k and put 18 frozen AGVs back.

Second implementation bug, caught by instrumenting instead of trusting the null: ranking on PATH LENGTH
is not stable within a step -- once the first robot reroutes its path changes, so the second compares
against a different number and both hold (both-waited 84 -> 128 on seed 11). Positions do not change
until `execute_micro_actions`, so MANHATTAN DISTANCE TO GOAL gives both robots the same answer and the
predicate stays antisymmetric. Exactly one waits.

Both polarities measured, 144 seeds:

    arm                     mean value  delivered  pod-wait steps  frozen AGVs      t
    off (always reroute)        727.55        493           67571            0      -
    ON: closer waits            726.25        467           65470           10  -0.45
    ON: farther waits           723.46        464           71971            5  -0.99
    (off-peak, closer waits: pod-wait 40093 -> 37277, -7%, t=+0.33)

**Closer-waits beats farther-waits on every column**, so the user's polarity instinct was right, and so
was the prediction that waiting would not inflate total wait -- it is the only arm that REDUCES
pod-waiting. But it is value-null (t=-0.45), costs 26 deliveries, and reintroduces 10 frozen AGVs after
the session had reached 0/144. Deadlock-freedom is worth more than a 3% pod-wait reduction.

Kept opt-in and OFF (`env.clash_choose` = 'near' | 'far'). Standing config unchanged.

**Why the detour is load-bearing:** rerouting is what physically separates two robots. Holding one still
keeps the pair adjacent, so the clash re-forms next step and the pair can re-enter the standoff -- and
near a station that is exactly the sealed-in geometry `station_headway` exists to prevent. Any future
version of this rule has to guarantee separation, not just pick a waiter.

**Process note (twice this session):** a mechanism that measures inert should be checked for whether it
FIRES before the null is believed. `clash_choose` first went into `_prioritized_reroute`, which is gated
behind a flag that is off; the WIP cap first went into `congestion_policies` classes that are not on the
champion's MRO. Both produced bit-identical results, which is the tell -- a real effect is never
bit-identical.

### Sidestep variant (`clash_choose='step'`): separation theory confirmed, still not shippable

Hypothesis from the note above -- what the detour actually buys is SEPARATION, and separation costs one
cell, not forty-six -- so make the designated yielder step ONE cell out of the way instead of holding
(the same trick that worked for station exit priority, rebuilding the route from the sidestep cell).

    arm                     mean value  delivered  pod-wait steps  frozen AGVs      t
    off (always reroute)        727.55        493           67571            0      -
    ON: closer HOLDS            726.25        467           65470           10  -0.45
    ON: closer SIDESTEPS        727.48        482           66336            8  -0.03
    (peak: holds -1.87 / 182 delivered; sidesteps -1.05 / 228 delivered vs 212 for off)

The theory is CONFIRMED: one cell of separation recovers nearly all the loss (t -0.45 -> -0.03, dead
level with baseline) and at peak it beats baseline on deliveries. But it still leaves 8 frozen AGVs, and
value-neutral is not worth trading the 0/144 deadlock-free property for. Kept opt-in and OFF.

Three variants of this idea now measured (value-rate ranking, one-waiter hold, one-waiter sidestep).
All opt-in, all default off. Stopping the thread: the remaining gap is 8 frozen AGVs of unknown origin
for ~0 value, which is a worse trade than leaving the rerouter alone.

### `require_reroute` pairing: standoff diagnosis CONFIRMED, value still peak-negative

Predicted cause of the 8-10 frozen AGVs left by the one-waiter rule: when the designated waiter holds,
the OTHER robot calls `find_path`, and if that returns [] it sets `fixing_clash = 0` and does nothing
either -- both hold, standoff. `require_reroute` already existed for exactly this: it drops the
already-fixing gate and falls back to an agent-blind replan so the yielder ALWAYS produces a route.

    arm                        mean value  delivered  pod-wait  frozen AGVs   t(pooled)  t(off-pk)  t(peak)
    off (always reroute)           727.55        493     67571            0           -          -        -
    closer HOLDS                   726.25        467     65470           10       -0.45      +0.33    -1.87
    HOLDS + require_reroute        725.54        468     68497            4       -0.67      +0.75    -3.09
    STEPS + require_reroute        726.09        463     64434            0       -0.48      +0.42    -2.00

Mechanism CONFIRMED: frozen AGVs 10 -> 4 -> 0. The sidestep+require_reroute arm is deadlock-free AND
has the lowest pod-waiting of any arm tested (-4.6% vs baseline).

Still NOT shippable, and the reason is a clean REGIME SPLIT: helps off-peak (+0.42, not significant),
hurts at peak (-2.00, significant). Under congestion the forced yield pushes robots into occupied space
via the agent-blind fallback, and peak deliveries drop 212 -> 199. The rule needs slack that peak does
not have. A load-gated variant is conceivable (the project already has a regime rule for URG_W), but it
would have to be gated on an OBSERVABLE (queue length / utilisation), pre-registered, not on the seed
index -- otherwise it is fishing.

**Remaining options for the path freeze, ranked.** The defect is that nothing guarantees PROGRESS: every
reroute is local and instantaneous, and no one counts how often a robot has been displaced, so it can be
bounced indefinitely (picker 13: distance 10 -> 20 -> 46 -> 35 -> 21 -> 9 -> 30 -> 18 -> 13 -> 1).
  1. force the non-waiter to move -- SETTLED above: mechanism works, value peak-negative.
  3. reroute budget -- likely inherits the same peak problem; it also ends in "stop rerouting this one".
  2. progress-aging priority -- STILL OPEN, and cheap: `_yields_to` currently returns True under the
     legacy mode, so whoever the loop reaches first yields and nothing stops the same robot yielding
     forever. Rank by steps-since-last-distance-reduction so the longest-failing robot outranks
     everyone. Changes only WHO yields, forces nobody into occupied space -- so it should not carry the
     peak penalty that 1 and 3 do.
  4. space-time reservations -- the real fix. `care_for_agents=True` is wrong in kind: a robot three
     cells ahead and moving away is not an obstacle at the time I arrive. Every robot's full `path` is
     already stored, so a (cell, time) reservation table is directly constructible (cooperative A*).
     Should behave BEST at peak, since congestion is exactly where the static approximation is worst.

All clash variants remain opt-in and OFF. Standing config unchanged: station_headway +
station_exit_priority + free_pod_return + SIM_DOCK_RES, deadlock 0/144.

### NEGATIVE: progress aging (option 2) -- prediction wrong, and the pattern is now conclusive

Rank clash yielding by starvation instead of loop order: `_staleness(agent)` = steps since the robot
last improved on its best-ever distance to its own goal; the longest-starved robot holds and the others
route around it. PREDICTION was that this would avoid the peak penalty that sank `require_reroute`,
because it changes only WHO yields and never forces anyone into occupied space.

    arm            mean value  delivered  pod-wait  frozen AGVs  t(pooled)  t(off-pk)  t(peak)
    off                727.55        493     67571            0          -          -        -
    aging              725.79        440     72473            0      -0.85      -0.39    -1.55
    aging+step         727.01        487     64593            8      -0.16      +0.45    -1.32

PREDICTION WRONG. Aging is peak-negative too (-1.55) and pod-waiting goes UP 7% (67571 -> 72473) with 53
fewer deliveries. The mechanism does fire -- picker 13's reroutes drop 7 -> 1 -- but letting the starved
robot hold means the OTHER robot detours, and that robot may be equally close to its own goal. Aging
does not reduce total displacement, it relocates it.

**Pattern across the whole thread, five variants, all null-to-negative:**
    value-rate ranking, one-waiter HOLD, one-waiter SIDESTEP, forced yielder (`require_reroute`),
    progress aging.
Every rule that RATIONS rerouting loses, because rerouting is how the system separates robots, and
separation is what keeps it live. That is the result to report, not five separate failures.

Option 3 (reroute budget) shares the same failure mode -- it also ends in "stop rerouting this robot" --
so it has a low prior and is not worth the run.

Option 4 (SPACE-TIME RESERVATIONS) is the only remaining candidate, and the failure pattern is the
argument for it: it does not ration reroutes, it removes the modelling error that makes them necessary.
`care_for_agents=True` treats a robot three cells ahead and moving away as a permanent wall; every
robot's full `path` is already stored, so a (cell, time) reservation table is directly constructible
(cooperative A*, Silver-style windowed prioritised planning). It should behave BEST at peak, which is
exactly where all five local rules failed, because congestion is where the static approximation is worst.
NOT built -- it touches every `find_path` call in the system and needs scoping with the user first.

All variants opt-in and OFF. Standing config unchanged: station_headway + station_exit_priority +
free_pod_return + SIM_DOCK_RES, 727.55 mean on-time value, deadlock 0/144.

### CORRECTION: pod-wait split is 98.7 / 1.3, not 92.9 / 7.1

The earlier decomposition used the contaminated "waiting" test (not carrying + no path + on a shelf
cell), which also counted robots with NO TASK parked on a shelf cell. Recomputed with the corrected test
(`req_action == TOGGLE_LOAD` while not carrying), 24 off-peak episodes:

    kind                              steps   share   n waits  median   MEAN   p90   max
    A: picker committed, travelling   13316   98.7%      1106       3   11.1    30   138
    B: NO picker assigned               178    1.3%        30      34   41.0    75   135
    overall mean wait = 11.9 steps

Total genuine pod-waiting 16494 -> 13494 steps; ~18% of what was previously counted was idle robots.
The typical wait is trivial (median 3, mean 11); all the damage is in the tail (p90 30, max 138).

Consequence: the dispatch gap (case B) is 1.3%, not 7.1% -- 30 occurrences across 24 episodes. The
picker re-dispatch / preemption work previously flagged as "the addressable slice" is therefore chasing
1.3% of a prize already capped at +3.74% off-peak. Not worth building.


## 2026-08-08 (final) --- space-time negative, picker-free-move adopted as champion, thread closed

**SPACE-TIME RESERVATIONS (cooperative A*), NEGATIVE.** Plans over (cell, time) from every robot's
published `path`, with edge constraints; waits kept in the plan and consumed as NOOP.

    window            8       16      32
    pooled t       -2.09    -1.07   -1.39
    frozen AGVs        5        5       2      (baseline 0/144)

FAILURE MODE (measured, seed 14 AGV 3): stood still 488 of 500 steps with NOTHING blocking it -- 0 of
488 steps had another robot in its next cell -- every plan beginning with a planned WAIT. Without a
priority ordering every robot respects every other's reservations symmetrically and a stationary robot
reserves its own cell for the whole horizon, so "everybody waits" is a consistent solution and A* finds
it because waiting is cheap. With space-time on: 37 frozen carrying AGVs over 24 seeds vs 0 without.
Prioritised planning (EDF and value-rate, the textbook fix) did NOT rescue it: smoke t=-1.08 / -1.83,
still 1 frozen AGV.
PROBE BUG worth remembering: an earlier diagnostic reported "next cell blocked 100%" for that robot. The
check counted the robot's OWN cell as an occupant, so a planned wait registered as a blockage. Corrected,
it was the exact opposite -- nothing was ever in its way.

**PICKER FREE MOVE (USER RULE) -- adopted as champion in the 'committed' form.** A picker whose next cell
is clear is committed to move, bypassing the referee's blanket sweep (which was NOOPing pickers with
empty cells ahead of them on 144 of 183 steps).

    24 seeds (off-peak)  value 886.18 -> 887.18  pod-wait 13494 -> 11405  frozen 0 -> 0   t=+0.18
    144 seeds (pooled)   value 727.55 -> 721.76  pod-wait 67571 -> 64031  frozen 0 -> 8   t=-1.33
    72 seeds (PEAK)      value 499.69 -> 496.16  pod-wait 27478 -> 25595  frozen 0 -> 0   t=-1.53
    72 seeds (PEAK, committed-only)              pod-wait -> 26998        frozen 0        t=-1.07

Wait TAIL, 24 seeds: max 138 -> 85, p99 80 -> 59, p90 33 -> 27, median 3 -> 3, n waits 1136 -> 1130.
It does not prevent rendezvous waits, it TRUNCATES the long ones -- exactly the right target.
ADOPTED by user decision in the 'committed' form (fire only when an AGV is already parked at the
destination pod). Value is slightly negative and not significant; the tail cut and 0-frozen-at-peak are
the reasons to keep it. QUOTE THE CAVEAT with any headline number.

METHOD FAILURE ON MY PART: I screened this on seeds 1-24 (the off-peak half), reported "your rule works"
off t=+0.18, and the 144-seed run reversed it. Same screening mistake that cost eight fixes earlier in
this session, already recorded in memory, made again anyway.
CORRECTION: I attributed the 8 frozen AGVs to pickers crowding AGV lanes via the shared collision layers.
NOT supported -- at peak, frozen AGVs are 0 in every arm. The 8 are off-peak only and remain unexplained.

**PICKER GEOMETRY (why reroutes are structurally expensive).** Pickers are confined to highways (55% of
cells) and cannot cross shelf blocks; they may only step onto their own rendezvous pod from an adjacent
lane. Vertical movement exists but only in the 1-cell lanes between blocks (174 vertical adjacencies).
Reaching the neighbouring lane means walking to a cross-aisle (every 7 rows), over and back: ~14 steps to
move 3 cells sideways. AGVs drive under pods and have no such constraint. So a 30-46 step picker reroute
is the graph, not a planner defect.

**THREAD CLOSED.** Deadlock: 0/144, held under every configuration tested. Livelock: DIAGNOSED, not
eliminated -- the 138-step pod-wait still exists in the shipped config; the ceiling is +3.74% off-peak
(pickers_free oracle) and three variants cut the tail without gaining value.
Standing config: station_headway + station_exit_priority + free_pod_return + SIM_DOCK_RES +
picker_free_move="committed". All other experimental flags opt-in and OFF.

## 2026-08-09 — NEW CHAMPION: station discipline stack. +6.79% (t=+6.78), 0 frozen across 144 seeds

The user's two station rules, plus two targeted fixes their failures exposed, produced the first
configuration all session to clear the |t|>=3 shipping bar — while ALSO restoring 0 deadlock:

    arm                          value   delivered  pod-wait   frozen     t
    off (old champion)          727.55       493      67571        0      -
    committed+final             732.29       526      47835       11  +1.07
    + side-keepout + divert     770.39       511      49648        2  +5.69
    CHAMPION (all four)         776.95       577      51723        0  +6.78

THE STACK (all opt-in flags, set by the runner):
  picker_free_move="committed"  picker whose next cell is clear and whose AGV is waiting is committed
  picker_final_step=True        picker one cell from its rendezvous goes IN and waits ON the pod
  station_side_keepout=True     never enter a station side cell while the OPPOSITE flank is occupied
                                (USER RULE: "keep a side cell free -- ALL the time");
                                the OCCUPANT IS EXEMPT -- the free flank is its escape route
  station_divert=True           carrying AGV <=6 cells out seeing >=2 other carriers within 2 of its
                                station retargets to the next nearest station (USER RULE), 10-step cooldown
  swap_return_drop=True         two carrying AGVs cross-assigned to each other's drop slots SWAP
                                missions and drop where they stand (zero movement needed)
  + station_headway, station_exit_priority, free_pod_return, SIM_DOCK_RES (unchanged)

ABLATION FINDING: keepout ALONE is catastrophic (147 frozen, t=-3.23) -- one-sided queueing with no
outlet. Divert is the drain that makes it work. The pair is a genuine complement, not two independent
improvements. This also REVISES the session's "rationing reroutes always loses" rule: it holds for
CLASH-LEVEL rationing, but station-level discipline (structured queueing + load-shedding to another
station) is where the value actually was.

RESIDUAL FREEZES FIXED ON THE WAY (each measured, each 2 AGVs):
  seed 139: side-keepout pinned the STATION OCCUPANT itself (next cell free 99/99 steps, never moved)
            -> occupant exemption
  seed 83:  cross-assigned swap -- each AGV standing on the OTHER's empty drop slot, plen=1 both,
            physical swap correctly forbidden forever -> swap_return_drop
  seeds 50/65 (earlier): station pile-up under parked pickers -> cured by keepout+divert themselves

Honest caveats: pod-wait is 51.7k vs 47.8k for cf alone (divert adds travel; still -23% vs baseline).
The frozen-AGV counts quoted all session are SUMS OVER ALL EPISODES, not per-episode counts.

## 2026-08-09 (cont.) — the 448-step wait: traced, explained, fixed. Side-access stack verified 0/144

**TRACE (seed 144, AGV 4, 448-step wait).** A picker WAS committed to its pod for 449/449 steps -- not
a dispatch gap. Pickers 9 and 10 stood frozen in one-wide lane x=9 for 400+ steps: p10 at (9,15) needed
(9,17) to enter pod (10,17); p9 at (9,17) needed (9,16) to enter pod (10,16). Each picker's ONLY doorway
lay past the other -- a swap in a 1-wide lane, physically impossible -- and the clash replan found no
alternative because with the other picker as a wall there WAS none. Both NOOPed every tick for 448 steps.
Root geometry: only the goal pod itself was unblocked in the picker grid, so most pods had exactly ONE
legal doorway.

**FIX 1 (`env.picker_side_access`, USER RULE: "no reason the picker should keep the AGV waiting -- it
can access from the side").** Lift the static highway wall on the four cells adjacent to a picker's goal
pod -> every pod has up to four doorways; one blocker can no longer seal a rendezvous.
Seed 144: max wait 448 -> 21.

**FIX 2 (`env.slot_divert`).** Side access surfaced seed 15: AGV 7 parked permanently on AGV 6's drop
slot. Same principle as station_divert on the return leg: blocked >= 8 steps on final approach to a
drop slot -> re-pick the nearest free slot.

**FIX 3 (swap_return_drop tightened + impossible-return repair).** Slot divert surfaced seed 29: my
swap_return_drop had swapped missions without checking the cells were shelf-free, leaving AGV 2 with a
RETURNING mission to its own cell where a shelf already sat -- find_path(own->own) is empty, so it never
went busy and NOOPed for 100 steps, silently. Swap now requires both landing cells shelf-free, and a
repair pass reassigns any RETURNING mission whose slot has acquired a shelf.

**FINAL, 144 seeds:**

    arm                 value   delivered  pod-wait  MAX wait  frozen
    champion           776.95       577      51723       448       0
    FULL (all fixes)   771.48       590      39242       104       0     t=-1.17 vs champion

The two configs are statistically indistinguishable on value (t=-1.17); FULL is strictly better on every
stall metric: max wait -77%, total pod-wait -24%, +13 deliveries, and the frozen audit stays 0/144.
Whack-a-mole note: each fix surfaced ONE new 1-in-144 instance (15 -> 29) -- rare-event fixing perturbs
dynamics; always re-run the full audit after each fix, never assume locality.

## 2026-08-09 (final) — side access retired for realism; lock-gated picker swap replaces it. CHAMPION.

**REALISM MEASUREMENT that killed side access.** Storage runs 97.1% full mid-episode (only carried pods
leave gaps), and of all picker side-access traversals, **98% passed through a cell holding a parked
pod** (217 occupied vs 5 empty). Crossing an EMPTY floor slot is realistic (Kiva storage is floor
parking); walking through a ~1 m pod tower is not, and that is where the benefit came from. Retired.

**REPLACEMENT 1: `env.picker_swap` (lock-gated rendezvous swap; USER-approved, USER-gated).** Fires
ONLY on a proven unremovable lock: both pickers stationary >= `picker_swap_patience` (10) steps AND
their errands CROSS (each strictly closer to the other's pod than its own -- the geometric signature of
an impossible pass in a one-wide lane). Then swap the two rendezvous missions: each picker's new pod is
on its own side. Dispatch decision, zero physics change -- the picker analogue of `swap_return_drop`.
Seed 144: max wait 448 -> 74.

**REPLACEMENT 2: `env.agv_free_move`.** The picker-free-move sweep pathology, observed on an AGV (seed
92): carrying to station, requesting FORWARD into a FREE cell, silenced by the referee's blanket sweep
100/100 consecutive steps. Same rule, same guard, applied to AGVs: a robot moving into a free unclaimed
cell is committed. (First patch landed in dead code -- wrong anchor -- and the smoke test caught it via
seed 92 still frozen: the bit-identical tell again.)

**FINAL CHAMPION, 144 seeds, all-realistic mechanics:**

    arm                       value   delivered  pod-wait  MAX wait  frozen
    previous champion        776.95       577      51723       448       0
    CHAMPION (realistic)     779.03       577      48875       119       0    t=+0.87

Champion env stack (runner-set): station_headway, station_exit_priority, free_pod_return,
picker_free_move="committed", picker_final_step, station_side_keepout, station_divert,
swap_return_drop (shelf-free-checked + impossible-return repair), picker_swap, agv_free_move.
`picker_side_access` and `slot_divert` remain available as opt-in flags but are NOT in the champion
(side access is unrealistic at 97% occupancy; slot_divert existed to patch a side-access-induced case).

## 2026-08-09 (coda) — the seed-48 loop-around: diagnosis right, extension gated off

**TRACE (seed 48, AGV 8, 119-step wait — the champion's worst case).** The committed picker (p11) was
TWO CELLS from the pod the entire time and already HELD the loop-around route (out to lane x=3, around
the block, in via the far doorway at (0,9)) — the user's proposed manoeuvre, already planned by A*. It
executed it at t~199 and the wait ended. What cost 90+ steps: BOXED IN on a pod cell by two stationary
pickers — p10 in the lane at (3,10) whose mission was (2,10), THE CELL P11 STOOD ON (chase cycle:
"I'm on your target, you're on my exit"), and p13 FREE, parked-on-pod, sealing the other exit.

**SQUAT swap gate (experimental, `env.picker_swap_squat`, default OFF).** Extending the rendezvous swap
to the squat shape (one picker standing ON the other's target) fixes seed 48 (119 -> 51): the squatter
serves the pod it occupies and the other picker does the loop-around. But it entered CASCADE territory:
every 144-seed sweep with it on produced exactly one new frozen instance of a DIFFERENT shape — seed 3
(AGV parked on drop slot), patched with slot_divert, then seed 2 (impossible-return, pathless). Gain on
the sweep: MAX wait 119 -> 114 only, value slightly down. Reverted; the flag stays for future work.

**Cascade lesson (now observed 5 times: 15 -> 29 -> clean -> 3 -> 2):** at the 1-in-144 rarity level,
any perturbation of movement dynamics relocates the residual rare event rather than removing it. A fix
is only worth shipping at this level if its measured gain exceeds the cost of re-verifying the whole
sweep — and 5 steps of max-wait does not.

**CHAMPION (final, re-audited 0/144 after the revert):**
    value 779.03 · deliveries 577 · pod-wait 48875 · MAX single wait 119 (seed 48) · frozen 0/144
    stack: station_headway, station_exit_priority, free_pod_return, picker_free_move="committed",
           picker_final_step, station_side_keepout, station_divert, swap_return_drop(+repair),
           picker_swap (crossed-only), agv_free_move
    experimental flags OFF: picker_swap_squat, slot_divert, picker_side_access

### CORRECTION to the coda above — squat KEPT (user decision), cascade closed by the dead-zone nudge

The user overrode the revert: keep the squat fix if max is lower. Chasing its one residual instance
(seed 2) found a REPAIRABLE dead zone, not another relocation: a carrying AGV whose RETURNING mission is
its OWN cell, cell SHELF-FREE (drop legal), but path=[] and busy=False -- the not-busy branch needs a
path to set busy, find_path(own->own) is empty, and TOGGLE_LOAD only fires when busy. The robot stands
on its own valid drop slot, NOOPing forever. Nudge: set busy=True, which routes it into the path==[]
TOGGLE_LOAD branch and it drops in place. With that, the cascade CONVERGED (unlike the earlier
relocations) -- full sweep + audit clean.

**CHAMPION v2 (final, user-directed, verified 0/144):**
    value 778.34 · deliveries 576 · pod-wait 48611 · MAX single wait 114 (seed 34) · frozen 0/144
    stack adds to v1: picker_swap_squat=True, slot_divert=True, dead-zone nudge (in swap_return_drop
    repair). Reference GIF: results/worst_wait_CHAMPION_v2.gif.

### CHAMPION v3 — rendezvous re-election (USER RULE), max wait 114 -> 83

USER RULE: "if pickers are leaving an AGV waiting and all stuck, choose based on (a) proximity and
(b) ability to legally move in." Implemented as `env.picker_reelect` (patience 12): when an AGV is
parked at its rendezvous and the committed picker has made no progress, re-elect the server among ALL
pickers by actual route length (a), candidates only if `find_path` with robots-as-obstacles returns a
route NOW (b). Winner with a mission -> swap (coverage conserved); free winner -> takes over, loser
re-tasked. The general form of the swap family: the shapes (crossed/squat) fall out as special cases.

    arm            value   delivered  pod-wait  MAX wait  frozen
    v2            778.34       576      48611       114       0
    v3 (+reelect) 775.77       540      46424        83       0     t=-1.23 (n.s.)

Kept per the user's standing criterion (max lower + frozen 0). CAVEAT on the record: deliveries drop
576 -> 540 (-6%) while on-time value is statistically unchanged -- re-election trades some completions
for keeping valuable ones on time. If raw throughput ever becomes the metric, revisit this flag first.
Champion stack = v2 + picker_reelect. Beat 775.77 (or 778.34 without reelect) without breaking 0/144.

### CHAMPION v4 — trajectory-simulated wait-vs-detour (USER DESIGN), first non-negative deliberation

USER DESIGN: at a collision point, be aware of the published trajectories of whatever blocks you and of
whoever will block you along the way — the chain ("sequence of four pickers") resolved by simulation.
`env.clash_sim`: at each clash where a detour exists, score BOTH options by simulated arrival time
(`_sim_eta`: deterministic cellular walk of every robot along its published path, fixpoint per tick so
chains cascade; parked robots never move; ties go to the detour). EVALUATION, not constraint — a wrong
prediction degrades an estimate instead of freezing a robot, which is precisely how it avoids both the
space-time fixed point and the clash_choose garbage-estimate failure.

    arm            value   delivered  pod-wait  MAX wait  frozen      t
    v3            775.77       540      46424        83       0       -
    v4 (+sim)     777.23       557      44608        92       0   +0.76

The SAME decision scored with a guessed blocker model was t=-1.76; with simulated trajectories it is
t=+0.76 — a ~2.5 sigma swing from estimate quality alone. Revises the movement-layer conclusion: it was
never "deliberation loses", it was "badly-informed deliberation loses". Saved as champion per user.
Tail caveat: MAX 83 -> 92 (stale-path waits run long); staleness haircut being tested next.

### CHAMPION v5 — progress-triggered re-election + encounter hysteresis (both USER-diagnosed)

Seed-134 trace (v4's 92-step worst case): the committed picker was assigned and MOVING the whole time —
closed to 3 cells, displaced, pushed to 6, four times. The ORBIT livelock. Every prior gate (swap,
reelect) keys on STILLNESS, which an orbiter never trips: motion without progress is invisible to
stillness gates.

Two fixes raced, 144 seeds:
    arm                          value  delivered  pod-wait  MAX  frozen
    v4                          777.23     557       44608    92    0
    hysteresis alone            774.63     553       45578   127    0    t=-1.24  REJECT alone
    progress-reelect alone      777.99     572       38262    70    1    t=+0.22
    BOTH (= v5)                 775.35     570       38280    70    0    t=-0.54  <- champion

`picker_reelect="progress"`: re-elect on NO-PROGRESS (best-ever route distance to current mission not
improved in K=12 steps) instead of no-motion — catches orbiting AND parking. `clash_hysteresis=20`:
the first robot of a pair to replan owns the replanning for 20 ticks; partner holds course (one dancer
leads). USER's flip-flop diagnosis was correct as a mechanism; per-pair memory alone is inert against
partner-changing orbits (seed 134: 92 -> 92) and negative overall, but as a COMPANION it closes the one
frozen residual progress-reelect leaves. Complement pair, same shape as keepout+divert.

v5 audited per-instance: frozen 0/144. Records: pod-wait 38,280 (-14% vs v4, -43% vs deadlock-free
baseline), MAX single wait 70. Value statistically unchanged across v2..v5 (all within |t|<=1.24).
BEAT 775.35 WITHOUT BREAKING 0/144.

### CHAMPION v6 — RATE_ALPHA=7 (USER DECISION, ship bar reset to t>=2)

Extended sweep found a monotone alpha climb on the v5 dense map (5.5/6/6.5/7/8 all positive, peak 7-8,
all frozen 0) reversing the old standard-map "6 turns down" -- the v5 picker layer is efficient enough
that sharper distance-discounting pays. Pre-registered 288-seed confirmation: +0.61%, pooled t=+2.71,
split-halves +1.37/+2.52, frozen 0/288 (champion alpha5 itself had 1 on the extended range). Below the
old |t|>=3 bar; USER reset the ship bar to t>=2 and alpha=7 ships. SEQ_DEPTH: 4/7/9 flat, horizon
saturated at 5; seq3 carries a frozen instance -- do not go below 5.

v6 REFERENCE (canonical 144 seeds): value 782.03, delivered 581, pod-wait 38187, MAX wait 69,
frozen 0/144. ALPHA=7 IMPROVES EVERY COLUMN AT ONCE -- the v2..v5 tail-vs-throughput trade dissolves:
best value, most deliveries (beats v2's 576), least waiting, best tail, zero frozen, simultaneously.
RATE_ALPHA=7.0 is now the class default on _VRPicker (propagates to all champion-stack scripts).
BEAT 782.03 WITHOUT BREAKING 0/144.

## 2026-08-11/12 — M1 CLOSED: stream ladder + stream weights + route verdict

STREAM LADDER (dense, v6 stack, 144 seeds): FIFO 398.66, rush 526.43 (+32.0% vs FIFO), champion
583.59 (+46.4% vs FIFO, +10.9% vs rush). Pairwise t: rush-FIFO +9.18, champ-rush +6.29,
champ-FIFO +12.62 (largest effect in the project). Frozen: FIFO 8, rush 4, champion 0 — the
decision-layer-is-part-of-liveness claim reproduces on stream. DAY-LIST pairwise for the record:
rush-FIFO +2.71, champ-rush +10.15, champ-FIFO +9.24.

ROUTE VERDICT: A*-shortest vs Yen's k=3 REVERSES across regimes — day +0.68% (t=+1.67), stream
-1.42% (t=-1.30), pooled t=-0.41. Pre-stated rule -> KEEP Yen's k=3 both regimes. Route diversity at
dispatch earns its keep exactly when arrivals are bursty.

STREAM WEIGHTS (one knob from v6, 144 seeds): ALL FLAT at the t>=2 bar. alpha 5/6 negative trends,
alpha8 +1.06 -> alpha=7 validated in its second regime. urg0all -1.01 -> first weak support for the
stream urgency rule (URG_W_STREAM=8), which is provably unused on day-list. SEQ_DEPTH=3 BIT-IDENTICAL
to 5 on stream: arrivals keep the queue shorter than the rollout horizon, so depth cannot bind.

Paper: §5.15 added with all four tables + pairwise significance matrix; next-steps rewritten (M2 gate
first). M1 verdict: closed on both regimes — ladder significant everywhere, weights flat on top,
liveness 0/144, champion v6 = 782.03 day / 583.59 stream.

## 2026-08-12 — M2 GATE under v6: perfect disturbance information is HARMFUL. M2 closes as a signed negative.

Bounding pair only (user directive), day-list 8x6, 144 paired seeds, v6 stack, both rates:

    rate 0.002 (calibrated):  clairvoyant 781.85   ignore 782.15   VoPI -0.04%   t=-0.18
    rate 0.037 (10x):         clairvoyant 775.49   ignore 784.76   VoPI -1.18%   t=-2.60
    frozen 0 in every arm -- liveness is debris-proof at 10x.

At 10x debris the fleet that CANNOT SEE obstacles beats the fleet with perfect knowledge of every one,
significantly at the project's t>=2 bar. THIRD independent perfect-information-is-harmful result
(demand foresight -3.43%, accurate admission -0.3%, now disturbance clairvoyance -1.18%).

MECHANISM (hypothesis, consistent with the v6 arc): debris amnesties in ~27 steps; clairvoyant routing
treats it as a WALL the tick it spawns -- preemptive fleet-wide detours around obstacles that are gone
before most robots arrive. The same permanent-wall-from-transient-state error the clash rerouter made
with robots. v6's contact-driven machinery (clash_sim wait-vs-detour, hysteresis, swaps) absorbs
transient blockage discovered by collision at near-zero cost; clairvoyance bypasses that machinery and
pays avoidance costs for phantoms.

M2 VERDICT: gate shut and inverted. The belief map is doubly dead -- its premise was "cheaply
approximate clairvoyance", and there is no value in approximating a signal whose PERFECT form costs
1.2%. No belief_los arm needed: ignore is best AND free. M2 closes as a strengthened, signed negative.

### M2 scope caveat (USER challenge, correct): the negative is conditional, and the boundary is the coda

USER: "in reality you should be able to account for disturbances even though slightly less accurate."
Right -- the harmful-VoPI result rides on three modeling choices: debris is TRANSIENT (amnesty ~27
steps ~ detour cost), POINT-SIZED (1 cell, uncorrelated, cheap to sidestep), and COLLISIONS ARE FREE
(discover+replan ~ a tick). Real disturbances persist, correlate (a dead robot seals a 1-wide lane),
and real collisions cost damage/safety stops. As persistence or collision cost grows past detour cost,
VoPI must cross zero. So the honest claim: for transient/point/cheap-collision disturbances, a
contact-robust executor makes advance information worthless-to-harmful -- robustness substitutes for
information IN THAT REGIME. Designated M2 coda: sweep amnesty rate x collision penalty, map the VoPI
phase boundary, audition the belief map on the informed side. ORDER (user decision): M3 first, coda after.

### CORRECTION (audit prompted by the user's collision question): debris has NO execution-layer existence

Verified in code: `self.disturbed` is consulted ONLY by the spawner and find_path. Nothing at
execution blocks movement through a disturbed cell -- a debris-blind robot drives straight through.
`_reroute_around_disturbance` fires on spawn but, for a blind planner, reproduces the same path.
So the M2 measurements (old and new) quantify PURE AVOIDANCE OVERHEAD of planner-only obstacles;
VoPI <= 0 is close to structural, and my "contact-driven machinery absorbs blockage" mechanism story
in the first draft of 5.16 was wrong -- there is no contact. The REAL disturbance question (physical
blockage cost + information value) has never been tested. M2 coda now: (i) execution-level enforcement,
(ii) persistence x collision-cost sweep, (iii) belief-map audition on the informed side.

COLLISION FACTS (user question): robot-robot collisions impossible by referee construction (unique
targets, swaps forbidden, uncommitted -> NOOP; free-move rules preserve the guard). Picker+AGV
co-occupancy at rendezvous = sanctioned load handshake. Historical exception: 2/800 co-located pairs
from the since-fixed silencing defect. AGVs drive under pods; pickers never plan into racks.

### keepout_top (USER question, 2026-08-13): top side was NOT policed -- and policing it is provably redundant

AUDIT: headway covers the top cell (any-adjacent check); side-keepout and the exit sidestep were
flanks-only. The sidestep's horizontal restriction was a leftover from the pre-rebuild crash, no longer
needed. Implemented `env.keepout_top`: entering a station's TOP cell held when BOTH flanks occupied
(never take the last free neighbour) + upward escape enabled for the occupant.

MEASURED: bit-identical to champion over 30 seeds (0/0 wins). Fires-check: AGVs approach top cells
constantly (3400/2625 steps per 15 episodes) but both-flanks-occupied occurs ~1 station-step per
episode and never coincides with a top entry. REASON: the flanks-only keepout already enforces "at
most one flank ever occupied" -- its own invariant makes both-flanks-occupied nearly impossible, so
the top cell can never become the last free neighbour. The user's escape guarantee holds with the top
uncovered BECAUSE the flank rule guarantees a free flank. Flag kept, not in champion (no effect).
Windows note: mp.Pool cannot run from stdin heredocs (spawn re-imports <stdin> -> OSError loop);
always write experiment scripts to real files.

### M3 battery: why the frozen-73 happened and the five-layer fix (2026-08-13/14)

USER QUESTION: "why is it getting frozen? how do we fix freezes?" (m3 arm, 144 seeds, SPC=1500,
midday start levels: frozen 73). Final answer after per-instance tracing, five distinct mechanisms,
all rooted in ONE design decision -- chargers sit on storage (shelf) cells:

1. ZOMBIE CARRIERS (dominant, ~7/12 residual after the first pod-drop fix): warehouse.py:1040 makes
   ANY busy AGV whose path empties request TOGGLE_LOAD -- so a robot ARRIVING at a shelf-bearing
   charger LIFTED the stored pod. Released, it became a carrying robot with NO mission (assigners
   only feed empty robots) standing on the plug forever; its now-bare charger cell then lured other
   carriers to drop there (walls: seeds 93/96/121). FIX: act() suppresses the arrival toggle for
   CHARGING robots at their charger (busy=False + NOOP; _manage_charging owns release).
2. AT-DEST DEAD-ZONE (seeds 125/126 v1): carrier ON its mission cell with path=[] busy=False can
   never fire (not-busy branch cannot path own->own; toggle branch needs busy). FIX: persistence-
   gated nudge (>=12 ticks, RETURNING/DELIVERING only). CASCADE LESSON: ungated, the nudge fired on
   the transient PICKING-arrival state and toggled freshly-loaded pods back down -- value 0.00 across
   144 seeds, carriers 5->0 by t=50. A "repair" must never match a state normal flow passes through.
   Same lesson for the zombie repair: "carrying+missionless" alone matches the one-tick window after
   PICKING completes; it must be narrowed to on-charger+idle.
3. CHARGE-SIMULTANEITY DEATH SPIRAL (seeds 82/125): midday start levels sent 4/8 AGVs charging in
   the opening window; deliveries lagged; orders piled onto hot pods (goods-to-person batching);
   station dwell (6 x items) exploded to 100-180 steps; the day died with ~1 delivery, ending in
   storage SATURATION (0 bare slots warehouse-wide -- measured) with carriers legally unable to drop.
   FIX: charge concurrency cap (<=2 planned trips, lowest level first, emergencies exempt). This is
   the user's "best TIME to charge" in fleet form: not all at once.
4. CHARGER CELLS AS FAKE DROP SLOTS: bare charger cells passed every free-slot search, so carriers
   were assigned to drop onto plugs where robots park (walls). FIX: charger keepout in the
   sim_priority return-repair + env-level slot_divert (opt-in `env.charger_keepout`, set by the m3
   controller; empty set for the champion -> bit-identical), and controller-level searches; plus a
   YIELD rule -- an idle missionless robot squatting a carrier's dest cell is sent off to charge.
5. DOCK STARVATION AT SATURATION (seed 126 endgame): the LAST bare slot in the warehouse was a
   charger cell occupied+claimed by a charging robot, so a delivered carrier held its station forever
   (sim_dashboard dock-flip `continue`s without an unclaimed bare slot). FIX: dock-starvation relief
   -- if a carrier is dock-held, evict the highest-level charging/idle squatter from a bare storage
   cell to a different charger (never an emergency clinger).

FINAL 144-SEED TABLE (SPC=1500, midday levels U(0.15,1.0), champion v6 env stack):
  nobat  782.03  frozen 0   stranded 0    (ceiling)
  stage0 747.14  -4.5%  frozen 0 (was 44) stranded 9   trips 63493
  m3     773.40  -1.1%  frozen 0 (was 73) stranded 12  trips 75941
M3 charge-to-need beats Stage-0 thresholds by +3.5%; battery physics itself costs -1.1% at this
compression. The frozen bar (0/144, per-instance audited) is met on BOTH battery arms.
OPEN RESIDUAL: stranded (hard-dead, lvl<=0.02 at end) 12/144 episodes-sum, min lvl 0.000 -- robots
still occasionally die en route despite pessimism 1.5 + trip-aware trigger; next M3 work item.
Also: probes that only measure the failure metric can "pass" on a broken run (the value-0.00 cascade
showed frozen 0 because NOTHING carried); every liveness probe must also check value/throughput.

### Dedicated shelf-free charger bays (USER RULE 2026-08-14: "charger cells realistically should have no shelf")

Implemented `setup_bays(env)` (scripts/m3_battery.py): the 8 charger cells lose their pods at
reset -- SHELVES grid cleared, the 8 shelf ids dropped from the DemandModel universe (env.shelfs
untouched; shelfs[id-1] indexing is pervasive, never delete/renumber). All arms incl. nobat share
the bay map (the bays exist physically regardless of battery modeling), keeping comparisons paired.
Bay cells are excluded from every return-slot chooser (new guard in the sim_dashboard dock-flip;
existing keepouts in sim_priority repair, env slot_divert, controller searches) -- all opt-in,
champion bit-identical when no bays are set.

One new freeze appeared and was traced (seed 91): below the emergency pod-drop trigger the drop
RE-FIRED EVERY TICK, wiping path/busy each time -- the router replanned forever and the robot
never executed a step (livelock at lvl~0.08, valid 14-step path, 100 ticks motionless). Masked
before bays because the nearest bare slot was usually adjacent; with bays it can be 14 cells away.
Fix: fire once per carry (`_emg_dropped` set, cleared on drop).

FINAL 144-SEED TABLE, bay map (SPC=1500, midday levels, champion v6 stack):
  nobat  783.97           frozen 0  stranded 0
  stage0 759.81  -3.1%    frozen 0  stranded 13  trips 71146
  m3     784.41  +0.1%    frozen 0  stranded 17  trips 83782
HEADLINE: with dedicated bays + charge-to-need + concurrency cap, battery physics costs ~NOTHING
(+0.1% = noise) vs the no-battery ceiling; Stage-0 thresholds still cost -3.1%. The bays also
recovered most of the old -1.1%: the battery "cost" was largely the slot-liquidity tax of chargers
squatting storage cells. Frozen 0/144 audited. OPEN: stranded 17 (up from 12; more charge trips at
the same trigger) -- the remaining M3 work item.

### MPC-over-parameters: the sim as its own world model (USER DESIGN 2026-08-14/16)

Design: every 50 real steps, deepcopy-fork the live (env, controller), roll each candidate setting
(battery pessimism, picker threshold, charge concurrency cap) 100 steps forward on the true physics,
score futures by on-time value -100/hard-dead -20/new-floor-breach, adopt the winner. Candidates
come from a per-episode UCB1 bandit over parameter MOVES (Pinductor-style guided proposal; ~40%
cheaper than brute enumeration). Every candidate + adoption logged to results/mpc_replay.csv (the
future context->constants training set). Precedent: clash_sim (simulation flipped t=-1.76 -> +0.76).

FIRST SWEEP (8 configs x 36 mixed seeds x fixed-vs-mpc, results/mpc_campaign.csv):
  small-4-3 -0.03% (t=-0.54, stranded 0 both -- battery trivial on small maps)
  medium-5-4 +0.14% (t=+1.25) | medium-8-6 +0.32% (+1.01) | large-5-4 +0.30% (+1.59, P drifts UP
  to 1.56: sparse fleet buys insurance) | large-8-6 +0.15% (+1.52) | large-12-8 +0.53% (+1.62,
  stranded 4->2) | extralarge-12-8 +0.59% (+1.42) | extralarge-16-9 +1.15% (+1.92).
POOLED (Stouffer over 8 independent batches): z = +3.5 -- MPC beats fixed constants GLOBALLY,
past the user's t>=2 bar. Effect scales with fleet density; on dense fleets 37% of replans adopt
non-shipped settings, BIMODALLY (P down to 1.30 when the future is safe, theta up to 0.50 ahead of
crunches) -- the optimal charging policy is time-varying and the forward simulation times the
switches. Averages hide this (mean adopted P ~= 1.52).

CAMPAIGN NOW SELF-UPDATING (scripts/mpc_campaign_step.py, USER RULE): each step either DEEPENS the
most promising uncertain config (0.8<=|z|<2) with a fresh disjoint 36-seed block, or EXPLORES the
next frontier config (fleet extremes, dual-carriageway geometry). Per-config verdicts at |z|>=2:
MPC ADOPTED / FIXED RETAINED; auto-status in results/mpc_status.md.

### MPC INTEGRATED into the shipped m3 stack (2026-08-16, per user standing instruction)

Campaign evidence at integration: 5/8 first-sweep cells MPC ADOPTED (extralarge-16-9 z=+2.82,
extralarge-12-8 +2.46, medium-5-4 +2.20, large-5-4 +2.03, large-12-8 +2.02), 0 negative, overall
pooled z=+4.8. Arm "m3mpc" in scripts/m3_battery.py: the controller itself forks (env, self) every
50 steps, rolls UCB-chosen candidate settings 100 steps, adopts the winner; `_in_fork` guard stops
fork-in-fork recursion; MPC auto-disabled on maps with <100 storage cells (small-4-3 measured flat,
stranded 0 -- nothing to tune). Integration smoke (6 seeds): m3mpc 827.35 vs m3 825.57, frozen 0.
Campaign continues via mpc_campaign_step.py (deepen/explore loop, results/mpc_status.md).

### MPC campaign round 2 complete (2026-08-16, overnight autonomous run)

Frontier exhausted at 20 configs (5 geometries x fleet mixes; results/mpc_status.md is the live
scoreboard). ADOPTED (11): extralarge-16-9 +2.82, large-16-9 +2.71, mediumdual-5-4 +2.52,
extralarge-12-8 +2.46, medium-12-8 +2.32, largedual-8-6 +2.22, medium-5-4 +2.20, extralarge-19-9
+2.16, large-3-2 +2.11, large-5-4 +2.03, large-12-8 +2.02. FLAT (2): largedual-12-8,
extralargedual-12-8 (2-cell opposing lanes remove the congestion the tuner exploits). PARKED at
max seed budget, unresolved: tiny-4-3 +1.88, large-8-6 +1.56, medium-8-6 +1.50, small-8-6 +0.20,
small-4-3 -0.54, and the one negative-lean cell extralarge-8-6 -1.40 (sparse fleet, huge map --
never significant, 4 blocks). OVERALL pooled z = +6.6 across 20 configs.

REVISED MECHANISM READ: the tuner pays wherever CHARGING IS A REAL LOGISTICAL DECISION -- long
bay trips or charger contention -- regardless of fleet size (large-3-2, a 3-AGV skeleton fleet,
ADOPTED at +2.11). It is inert where chargers are always near (small/tiny maps) and where dual
carriageways erase congestion. Campaign now in resolution phase (deepening least-sampled
unresolved cells), continuing indefinitely per standing instruction.

### Tuner v2 (USER RULE 2026-08-16): champion decision weights join the MPC candidate space

"They shouldn't be fixed constants -- it's like a slider on agvs, on pickers, on dimension."
M1's weight-flatness was measured on ONE map; v2 lets each warehouse test its own values. New
tunables (conservative moves, clamped around shipped champion values): RATE_ALPHA (+-2, [1,15]),
SEQ_DEPTH (+-1, [0,8]), URG_W_DAYLIST (+-2, [0,12]), env.clash_hysteresis (+-10, [0,40]) -- on top
of pessimism/theta/cap. 15 UCB moves; replay rows now carry the full 7-field setting (trailing
fields; old rows remain parseable). Applied to BOTH the campaign harness (m3_mpc.py) and the
integrated m3mpc arm. Campaign batches from this point are tuner v2; per-config Stouffer pooling
now mixes v1/v2 blocks -- still a valid test of "MPC-class beats fixed", noted for heterogeneity.

### Bays are FLOOR infrastructure (USER CATCH 2026-08-16: "charger locations shouldn't change")

My bay rule tied COUNT to fleet (max(4, #AGVs)); since positions are an even stride over the slot
list, changing count re-spaced every bay -- so charger locations differed across fleet configs on
the same map (and danced under the sandbox sliders). Physically wrong: bays are installed with the
building. Fixed: `floor_bays(n_slots)` (<=80:4, <=140:6, <=220:8, else 12), fleet-independent;
large=8 matches the shipped M3 reference exactly. Applied to m3_battery.setup_bays default, the
campaign harness, and the sandbox. Within-cell stats were never affected (paired arms always shared
bays); cross-fleet comparisons on one floor are cleaner from here. Cells tested pre-fix with
fleet-scaled bays (e.g. large-12-8 had 12, extralarge-16-9 had 16) are all RESOLVED and stand as
measured; noted as infra-v1 rows.

### v2 answer: do the champion weights move across contexts? NO -- they are context-robust (2026-08-16)

Across 4,572 v2 adoptions spanning ~12 configs (all geometries, fleet mixes incl. extremes):
RATE_ALPHA moved in 0.2% of adoptions, SEQ_DEPTH 0%, URG_W 0%, clash_hysteresis 1% (scattered both
directions -- noise). Given full freedom to test them, the forward simulation keeps the shipped
champion weights essentially always; the knobs that DO move remain the battery trio. So M1's
weight-flatness result GENERALIZES beyond the map it was measured on: the champion's decision
weights are context-robust sliders that every tested warehouse leaves where they are, while the
battery thresholds are the genuinely context-sensitive parameters. (Caveat: within-day timescale,
100-step lookahead; a cross-day drift could still exist but nothing here motivates hunting it.)

### STRANDED = 0 CLOSED (2026-08-17): pickers were being worked to death; enforcement at the action layer

Forensics (probe_stranded.py, 144 seeds): ALL 17 hard-dead robots were PICKERS, 0 AGVs, 0 en route
to a bay; 11 died holding PICKING missions after 50+ steps below 5%. Root cause: the picker charge
rule fired only when IDLE (`p not in ap`) -- busy days never idle a picker, so it sails through
theta=0.40 and dies metres from a bay. Fix attempt 1 (mission preemption in _manage_charging):
STOMPED same-tick by the dispatcher/reelect machinery -- tick trace showed the dying picker's dest
cycling between rendezvous while draining. Fix attempt 2 (projected-death penalty in MPC rollouts):
value up, strandings ~unchanged -- tuner knobs don't control this failure. FINAL FIX: enforcement
at the ACTION layer in act(): any picker below 0.5*theta off-bay has its CHARGING mission restored
and its ACTION forced toward the bay every tick -- the dispatcher may rewrite the mission, not the
move. Charge-to-need for pickers too (target theta+0.10, not 0.90: 0.90 was a ~315-step outage).
Line calibration: 0.25 -> stranded 0 but -0.8%; 0.20 -> stranded 0 AND value back.

FINAL M3 TABLE (144 seeds, bay map, SPC=1500, midday levels):
  nobat 783.97 | m3 779.27 (-0.6%) frozen 0 stranded 0 | m3mpc 784.49 (+0.1%) frozen 0 stranded 0,
  fleet min level 0.077. THE M3 AUDIT BAR IS MET IN FULL: battery free at zero casualties.
  (The earlier "+0.1% free" number silently ran pickers to death; the honest free number is this one.)

### Context prior AUDITIONED AND CUT (2026-08-17)

LOO A/B (prior built excluding large-8-6, tested on large-8-6, 72 seeds, identical fork budget):
cold start 1054.31 vs warm start 1053.40 (-0.1%). The per-episode UCB explores all 14 moves within
~27 trials/day, so a neighbour-derived knob ordering saves a handful of early forks and no value.
Verdict per the user's ship rule: DOES NOT EARN ITS SEAT. Machinery kept as opt-in arm "m3mpcprior";
the shipped m3mpc starts cold. (This also settles the LightGBM question for now: if even a k-NN
prior over 10 contexts is flat, a fitted proposer has nothing to predict -- the within-day search
is simply not the bottleneck.) results/context_prior.json rebuilt over the full 10 configs as a
dataset artifact.

### STREAM-REGIME MPC SHIPPED (2026-08-17, USER DESIGN: "just the tasks you see" vs belief)

Setup: live stream (arrivals invisible until they land; dm.step drives them), battery SPC=1500,
midday levels, m3mpc vs fixed m3. KEY MECHANICAL FACT: the fork never calls dm.step, so rollouts
naturally contain ONLY currently-visible tasks -- there was never a clairvoyance leak to plug.
Arms: mpc_a = visible-tasks forks; mpc_b = belief forks (arrivals sampled inside the rollout from
the demand statistics the robots legitimately own: base rate x diurnal curve, hot-pod weights,
common random numbers across candidates).

RESULTS. Head-to-head (36 seeds, large-8-6): mpc_a +1.85% vs mpc_b +0.79% -- THE HONEST MYOPIC
FORKS BEAT THE BELIEF FORKS. Even statistically-legitimate future knowledge diluted the tuner:
"honest about the present, silent about the future" (SS5.3) now confirmed at the parameter-tuning
layer. mpc_b dropped; compute went to resolving mpc_a.
mpc_a vs fixed, 6 independent 36-seed blocks (3x large-8-6 incl. the peak-heavy half, 2x
large-12-8, 1 earlier): +1.85, +0.43, +1.78, +0.84, +2.67, +3.12 percent; every block positive;
POOLED z = +2.76 over 216 paired days -- SHIPPED for stream. Mean effect ~+1.8%/day, roughly
DOUBLE the day-list effect (+0.98% post-enforcement) -- the unknown future leaves more
time-variation for the tuner to exploit. Also: block 5 fixed arm froze 2 carriers, mpc_a froze 0 --
on stream the tuner doubles as a liveness aid. Stranded 0 everywhere.
Harness: scripts/exp_mpc_stream.py (CONFIG/ARMS/SEEDLIST env vars).

### CAMPAIGN ERA 1 COMPLETE (2026-08-17): the grid is saturated

Every one of 30 configs resolved or at full 144-seed budget. FINAL SCOREBOARD (99 blocks, ~7,100
paired days): 16 MPC ADOPTED / 4 flat / 10 parked-at-budget (positive-lean or noise; the one
negative-lean cell extralarge-8-6 never reached significance) / 0 RETAINED-FIXED. Overall pooled
z = +8.4; mean effect +0.31%/day lifetime, +0.50%/day within adopted cells, ~+1%/day on the final
(post-picker-enforcement) controller whose blocks flipped several formerly-flat cells (medium-3-2
+2.65%, extralargedual-12-8 +2.57%, extralarge-16-6 resolved ADOPTED). Combined with the stream
result (z=+2.76, ~+1.8%/day, visible-forks-only), the tuner is shipped on BOTH regimes.
Era 2 frontier opens with the remaining fleet/geometry permutations.

### M2 CODA (i)+(ii) DONE (2026-08-18): debris enforcement built; the VoPI phase boundary mapped

ENFORCEMENT: `env.debris_hold_steps` -- entering a disturbed cell immobilizes the robot k steps
(recovery). First execution-layer existence for debris; fires-check exact (20 entries x 10 steps =
200 held agent-steps). Implemented in _execute_forward + a hold check in the macro attribution loop.

PHASE BOUNDARY (blind b_hard=1.1 vs clairvoyant, rate 0.02, m3, 4 blocks x 24 seeds/cell):
pooled z by cell -- day/hold0 z=-2.22 (INFORMATION PROVABLY HARMFUL when debris is consequence-
free; the SS5.16 negative now past the bar), transient/hold0 -1.85; hold5 cells +0.45..+0.70
(transition); transient/hold20 z=+2.83 (INFORMATION PROVABLY VALUABLE), day/hold20 +1.58.
VoPI is monotone in collision cost in every block; persistence is second-order. The boundary sits
at hold ~5-20 recovery steps at this rate. Harness: scripts/exp_m2_boundary.py.
Remaining coda part (iii): belief-map audition on the valuable side (transient/hold20).

### M2 CODA (iii) DONE -- M2 FULLY CLOSED (2026-08-19): the belief audition

Cell transient/hold20 (the proven-valuable side), arms blind / belief (b_hard=0.5 + line-of-sight
sensing, decaying fleet-shared rumor map) / clairvoyant; 2 blocks x 48 seeds.
Block 1 (calm): clairvoyant +4.04 (t=+0.84), belief +3.50 (t=+0.66) -> capture 87%.
Block 2 (peak): clairvoyant +12.03 (t=+3.13!), belief +6.90 (t=+1.57) -> capture 57%.
POOLED: clairvoyant VoPI z=+2.81 (significant, independently confirming the boundary), belief
z=+1.58; CAPTURE ~65%. Collisions: blind 479-728/block -> belief 169-236 -> clairvoyant 29-47.
Belief lags most when debris turnover is fast (staleness) -- the physically sensible signature.
ANSWER to the user's founding M2 question ("in reality you should be able to account for
disturbances even though slightly less accurate, right?"): YES, wherever information is worth
anything at all, honest sensing captures ~2/3 of perfect information's value and cuts collisions
~3x. Harness: scripts/exp_m2_belief.py. M2 is now closed END TO END: harmful side proven (z=-2.2),
boundary mapped (crossing at hold ~5-20), valuable side proven (z=+2.8), belief auditioned (65%).

### UNTIL-AMNESTY enforcement (USER DESIGN 2026-08-19: "spin your treads UNTIL amnesty")

`debris_hold_steps = -1`: a robot entering debris is stuck for as long as the debris persists
(released the tick the cell is cleaned). Cost = the hazard's remaining lifetime; the cost and
persistence axes merge. Fires-check: 5 hits -> 640 stuck agent-steps, longest single spell 230.

RESULTS (blind/belief/clairvoyant, 48 seeds each, rate 0.02):
  transient: clairvoyant VoPI +24.1 (t=+3.97), belief +6.8 (t=+1.70) -> capture 28%
  day-long:  clairvoyant VoPI +68.1 (t=+5.51) -- LARGEST VoPI EVER MEASURED in this project
             (+8.7%/day); belief +29.9 (t=+3.89, significant alone) -> capture 44%
CAPTURE GRADIENT across severity (fixed-20 calm/peak -> until-amnesty transient/day):
87% -> 57% -> 28% -> 44%: as a single mistake becomes catastrophic, honest sensing keeps a smaller
FRACTION of the oracle's value (one unseen spill = one robot-day) even as its ABSOLUTE value grows
(+3.5 -> +29.9). Sensing goes from nice-to-have to independently significant; an oracle would still
be worth ~2x more. Harness: exp_m2_belief.py (M2HOLD=-1, M2DUR=day).

### CAMPAIGN ERA 2 SATURATED (2026-08-20)

38 configs, 122 blocks (~8,800 paired days): 22 MPC ADOPTED / 4 flat / 12 parked / 0 negative.
Overall pooled z = +9.96, lifetime mean +0.40%/day. Era-2 highlights: tiny-8-6 ADOPTED at the
buzzer (final block t=+2.31 -> pooled z=+2.00) -- even a 36-slot floor adopts when 8 AGVs congest
it, reinforcing the mechanism read (charging-as-logistics, not map size); mediumdual-8-6 and
extralargedual-16-9 also positive under the final controller. Era 3 frontier: remaining
permutations (tinydual, smalldual-8-6, extreme dual fleets, picker-starved cells).

### CAMPAIGN COMPLETE (2026-08-21): the driver reports "all configs resolved"

Three eras, 46 configurations -- the full meaningful permutation space of the registry (5 sizes x
dense/dual x informative fleet mixes 3-2..19-9): 148 blocks, ~5,300 paired days x 2 arms.
FINAL: 27 MPC ADOPTED / 4 flat / 15 parked-at-budget / 0 FIXED-RETAINED. Overall pooled
z = +11.24; lifetime mean +0.42%/day (early-controller blocks included; ~+1%/day on the final
controller). Plus stream: z=+2.76, ~+1.8%/day. The remaining unexplored permutations are
degenerate (e.g. mega-fleets on tiny floors); per the project's own discipline (a run must beat
the cost of re-verifying), the campaign is PARKED as a complete dataset rather than mining noise.
Restart anytime: extend FRONTIER in scripts/mpc_campaign_step.py and invoke it -- the driver,
seed-block bookkeeping, and status machinery are all intact.

### JANITOR (USER DESIGN 2026-08-21: "you should have a cleanup robot") -- and the M2 punchline

`env.janitor=True`: ONE human cleaner, summoned by the fleet's SIGHTINGS (rumor-map evidence; no
map -> reported instantly), walks highways at 1 cell/step ignoring robot traffic (humans step
around; no collision layer), mops `janitor_clean_steps`=20 on arrival; timed amnesty DISABLED
(spill dur=1e9) -- cleanup latency = discovery + travel + mopping, so unseen spills persist.
Fires-check: 11 spills -> 8 cleaned + live backlog; stuck agent-steps 640 -> 238.

AUDITION UNDER JANITOR PHYSICS (until-amnesty holds, 48 seeds): blind 855.71 (hits 176) / belief
863.58 (+7.87, t=+1.77, hits 153) / clairvoyant 863.23 (+7.53, t=+1.73, hits 13).
**BELIEF CAPTURES ~105% OF CLAIRVOYANT VoPI -- honest sensing MATCHES the oracle.** Mechanism:
responsive cleanup shortens spill lifetimes so avoidance knowledge loses value (blind rose
826->856 purely from summoning); the residual value of information is SUMMONING, which sightings
do as well as omniscience. Full capture arc: 87% -> 57% -> 44% -> 28% (stakes rise, timer amnesty)
-> ~100% (earned amnesty). THE ORACLE PREMIUM IS A SYMPTOM OF SLOW RESPONSE, not of ignorance.
Harness: exp_m2_belief.py with M2JANITOR=1.

### Janitor returns to base + sight-radius sweep (2026-08-21)

Janitor now walks HOME (base = first station) after mopping when no spill is reported (USER:
"should not disappear, it should go back like normal"); verified 8 cleans / 2 full round trips.
SIGHT-RADIUS SWEEP (until-amnesty transient, timer world, 48 seeds, belief arm): capture 19.4% (r2)
/ 31.0 (r3) / 28.2 (r5) / 28.8 (r8) / 35.9 (r12) -- FLAT for r in 3..12 (diffs ~ noise); only
extreme myopia hurts. OCCLUSION, NOT RANGE, is the binding constraint: the cross-shaped visible
set is nearly radius-invariant past the aisle scale. Radius now tunable (M2RADIUS; BetaRumorMap
sight_radius). Under janitor physics radius matters even less (belief ~= oracle regardless).

### Disturbance STYLE learning v1 (user 2026-08-23) -- honest negative, then the scout pivot

USER: rerouting should have a component that learns the STYLE and SPREAD of disturbances (cells
per spill, where they go). Built: (1) opt-in multi-cell events `disturb_event_cells=(lo,hi)`
(contiguous blob; single-cell default stays -- it is the physically defended case); (2)
BetaRumorMap(learn_style=True): learns event-size (fires-check: est 2.43 vs true 2.1) + spatial
spawn_prior from first confirmations only. v1 ROUTING USES: (a) neighbor-suspicion bump on fresh
sightings, (b) slower forgetting in learned hot zones (resting belief capped at prior -- no
permanent no-go zones).

AUDITION (multi-cell 1-3, until-amnesty, 48 seeds): blind +0 / belief +20.74 (t=+1.81, 38%
capture) / style +17.59 (t=+1.54, 32%) / clairvoyant +55.29 (t=+5.33). Style vs belief paired
-3.15 (t=-1.64), hits UP 236->248. The learning is accurate but spending it on MORE AVOIDANCE
loses -- the M2 boundary lesson again (unverified fear = paid detours).

PIVOT (user design): spend the learned hazard map on LOOKING, not fearing. SCOUT DETOURS: no
dedicated scout robots; `env.scout_weight` prices information into A* free-cell costs --
uninformative cells cost up to +w extra, max-info cells +0, so a k-step detour is accepted only
when it sweeps ~k/w worth of hazard-prone evidence-starved cells (rumor_map.info_gain_map = disc
sum of hazard x uncertainty within sight radius, cached per step; composes with congestion +
adherence). Ablation flags style_bump / style_slowmem isolate why v1 lost. Audition running:
belief / bump / slowmem / scout(0.3) / clairvoyant -- exp_m2_scout.py.

### Scout audition verdict (2026-08-23): the whole style/scout family is CUT

Ablation (48 paired seeds, multi-cell 1-3, until-amnesty): bump-only -0.40 (t=-1.00, flat),
slowmem-only -3.18 (t=-1.64) <- v1's entire loss (-3.15), scout w=0.3 -5.72 (t=-0.85, noisy
negative), clairvoyant +34.55 (t=+4.18). WHY SCOUTING FAILS: at realistic spill rates the fleet's
ordinary traffic already sweeps ~the whole floor (fires-check: 400/400 cells hold evidence), so
paid detours buy information routine driving collects free; the oracle gap is spills nobody has
REACHED yet, whose discovery timing detours barely move. Same family as rationing-reroutes: a
plausible use of a correct model, killed by measurement. Code kept flag-gated (learn_style,
style_bump, style_slowmem, scout_weight all default OFF); plain belief remains shipped.

### World Runner (user 2026-08-23) -- separate live page + a stress-day invariant finding

New standalone page (artifact https://claude.ai/code/artifact/a7e85e22-20a9-4cf3-aec7-daaf8a50ed6d,
also served at http://127.0.0.1:8734/world by race_server): one button rolls a RANDOM world
(size/dual, 6-16 AGVs, matched pickers, day 1-144, 25% stress, 30% stream) and runs fixed-vs-MPC
on the identical day. Shows: value race + final delta, the MPC's adopted-changes feed (7 fields
decoded to plain names, diffs only), lowest-robot battery curves with 10%/2% floor lines, and
PER-ARM stranded counters (MPC must be 0). CORS added to race_server JSON endpoints so the
artifact page can reach the local app; /world route added; raceapp entry in .claude/launch.json.

FIRST ROLL FINDING (large-8-6@30, stress+stream): fixed constants STRANDED one AGV (started 46%,
dead t=431) and MPC stranded ZERO (adopted pessimism 1.5->1.8 @t=50, threshold 0.40->0.33 @t=100,
cap 2->3 @t=350; one robot grazed 2% and recovered via the hard-floor gate). Value +74.3% MPC.
The audited stranded-0/144 invariant was established at standard compression (M3SPC=1500); on
stress days (300 + low starts) the FIXED arm's constants charge too late -- the self-tuner is what
upholds the invariant out-of-regime. This is the project thesis in one screenshot; the page
attributes it per arm with an explanatory note.

### World Runner INTEGRATED into sandbox (user 2026-08-23) -- build r15

1. Roll random world is now a button in the Race tab: randomizes the EXPLORER state itself
   (size 2-4, 25% dual, 6-16 AGVs, matched pickers, day 1-144, 25% stress, 30% stream) then runs
   -- preserving the settings-apply-everywhere invariant. startRun() gained a seed param
   (/run?seed= passthrough).
2. Playback speeds 0.25x / 0.5x added, DEFAULT now 0.5x (user: watch side-by-side at slowish
   speed); R.t is fractional, drawRace floors it.
3. World-page panels folded into the race view: MPC decision feed (7 fields decoded, diffs only)
   + battery-health chart (lowest-robot curves, 10%/2% floor lines, time cursor) + stranded
   counters. SYMMETRIC framing (user: neither arm has a hard never-strand requirement; both try
   equally hard, same machinery): counters shown identically for both arms, note + glossary
   updated -- zero is an earned goal, not a scripted guarantee. Code was already symmetric (both
   arms are the same m3 controller class with identical act-layer protections; MPC only retunes
   knob values), so this was a framing fix, not a code fix.
4. Standalone World Runner artifact replaced with a pointer page to the sandbox (URL kept alive);
   janitor pre-positioning audition earlier today: FLAT (-0.27, t=-0.46) -- even at zero
   opportunity cost, WHERE-prediction buys nothing measurable; final word on the prediction front.

### Sight-gated spread avoidance v2 (USER DESIGN 2026-08-23): fixes v1's harm, flat on value

USER: estimated spread should be avoided only BEFORE it enters sight radius; sight overrides
estimate instantly. Implemented as PLACEHOLDERS not evidence (rm.style_suspect: suspect dict,
any observation of the cell deletes it, 150-step expiry; believed_blocked() unions live
placeholders). Fires-check: 13 placeholders/day, all resolved, peak 4 concurrent.
AUDITION (48 paired seeds, same world as v1): sightgate +0.60 vs belief (t=+0.54), hits 236->229.
v1 was -3.15 -- a +3.75 swing, CONFIRMING the user's diagnosis: the harm was lingering fear after
cells were visibly clean, not the avoidance itself. Not significant (below t>=2 ship bar) because
exposure is tiny at rate 0.02 (~13 brief placeholders/day). Verdict: harmless + mildly
hit-reducing; kept flag-gated OFF; FIRST arm to re-audition if spill rate/event size ever rises.

### EPISTEMIC ACCURACY: peak reached (user question 2026-08-23 "how accurate vs clairvoyant?")

New metric harness exp_m2_epistemic.py: per-step recall/precision of believed_blocked vs TRUE
disturbed set + detection latency, against the per-run SENSING CEILING (perfect-memory oracle fed
the identical LOS stream -- best possible given where robots actually drove). Multi-cell 1-3,
until-amnesty, 24 seeds, active shipped routing.

ARC: shipped (decay .99, +1 evidence) recall 60.9% / ceiling 83.6% / precision 80.7% / latency 59.
SLOWER decay is WORSE (1.0 -> recall 38.4%): busy cells hold ~100 "clean" votes at equilibrium and
new dirty sightings must outvote them one pebble at a time -- forgetting exists to erase the CLEAN
mountain, not the spills. Uniform evidence scaling (obs_gain both ways) provably changes nothing
(posterior odds invariant). Faster decay .98 -> 70.9%, .96 -> 77.7%.
**RESET MODE (rm.obs_reset: a look REPLACES cell evidence, 26:1, noiseless-sensor
last-observation-wins + decay): recall 84.7% vs ceiling 84.9% = 99.8% OF THE PHYSICS LIMIT,
precision 95.3%, latency 19, 417/468 events.** Dirty-reset belief stays >0.5 until seen clean;
no phantom zones because drive-by SIGHT clears cells nobody traverses. Remaining ~15% is
clairvoyance-only (never in anyone's sight while dirty). Value audition of reset-mode routing
running (must not repeat the slowmem value loss); ship decision pending that.

### RESET-MODE SHIPPED (2026-08-23): accuracy peak = value peak, no tension

Value audition (48 paired seeds, multi-cell 1-3, until-amnesty): belief 821.30 / RESET 850.05
(+28.75, t=+4.05, hits 236->80) / clairvoyant 855.84 (+34.55). Honest sensing now captures 83%
of clairvoyant VoPI (was 38%). PAST SHIP BAR -> rm.obs_reset defaults True (legacy incremental
votes = False, exp_m2_epistemic sets it explicitly for its baseline arms).
THE LESSON (user's question led here): the oracle gap was mostly a BAD UPDATE RULE, not bad eyes
-- incremental Beta votes let ~100 stale "clean" observations outvote a fresh dirty sighting;
replacement (last-observation-wins for noiseless sensors) + decay hits 99.8% of the sensing
ceiling AND -66% debris hits. Chain of findings in one line: slower memory hurts -> uniform
evidence scaling is provably inert -> replacement is optimal. Remaining 15% recall / 5.8 value
vs clairvoyant is physics: dirt nobody's sight crosses while dirty.

### Reset-mode applies to MPC too + honest-fork RNG guard (2026-08-23)

The belief map is FLEET infrastructure: any disturbance world gives BOTH arms (fixed and MPC)
the same reset-mode map -- no controller favoritism. While confirming, closed a latent honesty
bug: MPC forks deepcopy the env INCLUDING the disturbance RNG state, so imagined rollouts would
have replayed the TRUE future spill spawns (clairvoyance inside imagination, violating the
visible-only-forks principle that won on stream). Guard added at both fork sites (m3_mpc
rollout_score + m3_battery embedded tuner): forks reseed _disturb_rng so imagined futures SAMPLE
the spawn process instead of reading the answer key. Fires-check: MPC rollout in a
belief-routed disturbance world runs clean, real-env RNG untouched.

### The 2x2 closed: reset fix measured THROUGH the MPC (user request 2026-08-23)

value @48 paired seeds (multi-cell 1-3, until-amnesty): fixed/oldmap 821.30 (hits 236) |
fixed/reset 850.05 (80) | MPC/oldmap 825.74 (224, 45 adoptions) | MPC/reset 852.16 (88, 33).
Sanity anchor: oldmap fixed reproduced 821.30 exactly (deterministic cross-run pairing valid).
RESET FIX WORTH +26.4 THROUGH MPC (+28.75 through fixed) -- map upgrade is infrastructure,
carries ~additively through either controller; full stack +30.9. Second-order: MPC's own edge
DOUBLED on the bad map (+4.44 vs +2.11; 45 vs 33 adoptions) -- the tuner was compensating for
phantom-belief damage; fixing the map correctly made the tuner quieter. Also: 9-knob corrected
rerun (ucb_pick bug fixed -- it iterated the MOVES constant, belief arms unreachable) landed
+1.85 (t=+1.18, 23 adoptions): the tuner EXPLORED trust moves and declined them -- shipped
constants (b_hard 0.5, decay 0.99) certified by forward simulation, held by evidence not fiat.

### M2 LETTER GAPS CLOSED (user 2026-08-23): risk term + calibration -- full clause accounting

RISK TERM (Part A step 5): built (env.belief_risk_w, graded max(0,b-0.5) cost on
sub-threshold suspicion in find_path, flag-gated off) and proven VACUOUS under the shipped
reset map: 0 cell-steps of gray-zone belief in a full day (reset beliefs are binary; the
clause presupposed the old map's fuzzy beliefs). Closed: measured null-by-construction.
CALIBRATION (spec +/-10%, exp_m2_calibration.py, 24 seeds, ~2.6M cell-step samples):
PASSES in the decision bins -- seen-dirty stated 95.8% vs observed 97.9% (+2.1pp), seen-clean
4.3% vs 0.27% (-4.0pp), together ~96% of mass and all routing decisions. FAILS in prior +
transitional bins (uninformed cells claim 50% vs ~0.3% base rate, -49pp) -- STRUCTURAL AND
CHOSEN: a base-rate-honest prior = resting beta-mountain = the slow-detection pathology reset
mode exists to kill. Overconfident where idle, calibrated where it acts.

M2 LETTER FINAL SCORE: ablation centerpiece exceeded; b_hard done; risk term built+null;
interrupt tier absorbed into continuous replanning; specificity pass; calibration pass-where-
it-decides; sensitivity 84.7% vs spec 90% = PHYSICALLY UNATTAINABLE (ceiling 84.9% at radius-5
occluded sight -- spec predates the occlusion model); latency 19 vs 15 near-miss (was 59).
Every clause now delivered, measured-null, or proven unattainable as written.

### SIGHT=CERTAINTY / OUT-OF-SIGHT=PREDICTION (USER DESIGN 2026-08-23, shipped)

User: "once seen it should be 100%; if it's not in the sight radius, then you do predictions."
Implemented: rumor_map tracks _live (cells observed THIS step); belief() reads exact truth
(1.0/0.0) for live cells, decaying alpha/beta PREDICTION otherwise. Fires-check: zero routing
mismatches off live cells (threshold decisions unchanged); one run separated ~98k certainty
cell-steps from 1.2k believed-by-prediction. CALIBRATION IMPROVED TO EXACT in the decision bin:
[0.9,1) stated 98.0% vs observed 97.9% = -0.0pp (was +2.1pp); seen-clean -2.0pp (was -4.0).
Transitional prediction bins unchanged (documented structural overconfidence of the prior).
belief_physics.gif regenerated with regime labels (panel title flips IN SIGHT: certainty /
out of sight: PREDICTION); sandbox r18 caption updated with the two-regime explanation + the
98.0-vs-97.9 honesty stat.

### M1's LAST DEFERRED ITEM CLOSED (2026-08-23): full-world knob revalidation

exp_knob_reval.py, full world (standard battery + multi-cell 1-3 until-amnesty spills +
reset-mode belief routing), champion vs brackets, 24 paired seeds: alpha5 -1.73 (t=-0.29) /
alpha9 -9.88 (-1.25) / depth3 -23.85 (-1.63) / depth7 -14.07 (-1.92) / urg2 +0.00 BIT-IDENTICAL
(URG_W inert here -- echoes the picker-urgency two-state finding) / hyst10 -1.26 (-0.72) /
hyst30 -1.02 (-0.32). ALL CONSTANTS HOLD; SEQ_DEPTH=5 is a two-sided local optimum. NB the
champion mean (800.22) differs from the 48-seed audits (850.05) only because this used the
24-seed subset -- pairing is within-run, verdicts unaffected. M1 -> M3 now have ZERO open gates;
remaining anywhere: two optional assembler-plumbing boxes, M3b (gated on the drift-VoPI probe),
M5/M6 paper work, and the "tune later" MPC cadence sweep.

### Assembler boxes CUT (user 2026-08-23)

Verified before cutting: delay_head=None in the shipped champion (sim_priority.py:236); only
congestion_policies.py experimental arms ever load a trained head, and the champion beat those
arms in the M1 scale study. feat["pred_finish"] feeds a rule-based delay EMA, not a model. So
"add belief/battery fields to the state assembler" served a consumer that lost its audition --
both boxes CUT per user. FINAL MILESTONE TALLY: M2 4/4 surviving boxes + done-when met; M3 2/2
surviving boxes + done-when met; M1 fully closed incl. the deferred full-world revalidation.

### SIGHT vs PREDICTION DECOMPOSITION (user question 2026-08-23) + a retroactive credit

New arm "sightonly" (decay=0: dodge only what is currently in someone's view, zero memory), same
48 days: blind 800.56 (hits 364) -> sightonly 837.25 (182) -> shipped predictive map 850.05 (80)
-> clairvoyant 855.84 (22). DECOMPOSITION: eyes +36.7 (74% of sensing value), out-of-sight
PREDICTION +12.8 (26%, t=-1.96 for removing it vs the old+override map), physics-only +5.8.
Memory halves the hits sight alone cannot stop (182->80). Prior prediction that memory would
dominate was WRONG: 14 robots x radius-5 keeps much of the floor in view, so dodging the visible
carries most of the value; prediction owns the un-substitutable remainder.
BONUS FINDING: the sight=certainty override (user design) retroactively repaired the OLD
incremental map from 821.30 -> 843.50 (+22 of its -29 deficit, hits 236->125): its worst sin was
slow belief in its own eyes, which the override bypasses for in-view cells. The reset rule's
remaining +6.6 is purely out-of-sight memory quality.

### RADIUS KNOB + THE PREDICTION INVERSION (user 2026-08-23)

WWM_SIGHT_RADIUS is now a global WORLD knob (rumor_map constructor default; explicit args win;
deliberately NOT an MPC move -- hardware is not policy, and forks imagining better cameras =
cheating). Price list (48 seeds, multi-cell): r1 48.5% of oracle / r2 70% / r3 86% (~free vs r5)
/ r5 89.5%. Realism: r1 = camera-less Kiva-style drive units (near-contact); r3 = modest depth
camera; r5 = good camera / human spotters.
PREDICTION ABLATION AT r=1: blind 800.56 (hits 364) / sightonly-r1 807.03 (286) / pred-r1
827.35 (175). PREDICTION WORTH +20.32 (t=+2.28 -- first prediction-isolating result past the
ship bar). THE INVERSION: r5 world = eyes 74% / prediction 26% of sensing value; r1 world =
eyes 24% / prediction 76%. The worse the sensors, the more the world model IS the sensor.
Belief-mass split at r5: ~70% of believed-blocked cell-steps live sight / ~30% prediction.

### M3b CUT BY ITS OWN GATE (2026-08-23): drift-calibrated VoPI probe

Built for the probe (kept, opt-in): real Instacart sample under data/instacart/ (3,221 orders /
30,121 item-lines from billyrohh/instacart_dataset -- best publicly-fetchable hour-resolved
order stream; e-grocery IS robotic-fulfillment demand, and no Kiva/Amazon order-to-pod dataset
exists publicly); drift_curves.json (3 zone-groups, daytime hours 7-21 smoothed, 11-17% swings);
DemandModel(drift=...) making hot-zone weights phase-dependent (fires-check: zone shares shift
7-9pp between day-halves, arrival count unchanged).
PROBE (exp_drift_vopi.py, W in {0,25,999}, 8x8 exogenous): block 1 (seeds 1-48) W25 +4.63
(t=+0.91 -> deepen band per campaign rule); block 2 DISJOINT (seeds 49-144, n=96) W25 -5.28
(t=-1.19). POOLED -1.98, z=-0.45 FLAT; W999 -2.22 flat. GATE SHUT -> M3b CUT, staging never
built. The split-half lesson held again: exploratory leans die on disjoint blocks. Anticipation
null now rests on FOUR legs (estimators null / perfect info harmful / no horizon pays / real
drift changes nothing). M3c headroom probe remains available.

### M3c CUT BY ITS OWN GATE (2026-08-24): pre-positioning headroom = 2.4% ceiling

exp_m3c_headroom.py (24 stream seeds, champion stack, accounting not policy): 927 pickups
(38.6/day, 94% preceded by idle), idle-approach travel 2285 steps total = 95/day = 2.38% of the
AGV step-budget = 5.9% of moving steps, i.e. 2.6 STEPS PER PICKUP. Below the 3% ship bar at the
TELEPORTATION ceiling (real policy pays walk-to-waiting-spot + guess error -> realistic prize
<1%). MECHANISM: an AGV idles where its last delivery ended (stations/hot racks) = where new
orders name shelves; finishing a task IS pre-positioning. Micro-level confirmation of the
static-world self-positioning story. BOTH gated milestones (M3b, M3c) now dead by their own
gates in one day; remaining roadmap: M4 pace-model gate, M5 benchmarks, M6 paper.

### M4 CLOSED (2026-08-24): pace head CUT by its own gate; EMA stands; endogeneity finding

exp_m4_pace.py (wave, champion stack, 24 seeds, 16 train / 8 held-out; 252 test tasks; target =
realized delay at assignment): zero 31.28 / EMA 23.45 / LightGBM head 19.83 (+15.4% MAE, slope
0.43 FAIL) / sim-pace fork arm (USER IDEA: read the EMA inside the MPC's own 50-step forks)
22.33 (+4.8%, slope -0.19). Train-fitted linear recalibration made TEST WORSE (+7.8%, slope
0.33): the head's edge is partly train-regime fit, does not transfer. GATE FAIL -> no challenger
ships. KEY FINDING: EMA calibration slope NEGATIVE (-0.23) -- prediction is ENDOGENOUS to
control (high forecast -> conservative dispatch -> forecast falsified; self-defeating prophecy).
This explains the five historical delay-prediction nulls at the mechanism level. Sim-pace's
+4.8%: 50-steps-fresher helps but a fork completes too few tasks per window (noisy EMA sample).
M4 milestone CLOSED: the decision layer ships with ZERO learned components, by measurement.
Data kept: results/m4_pace_data.csv. Remaining roadmap: M5 (benchmarks + TA-RWARE head-to-head),
M6 (paper assembly), + the tune-later MPC cadence sweep.

### M4 FULL-SCALE CONFIRMATION (user-requested 144-seed protocol, 2026-08-24)

Rerun at 96 train / 48 held-out seeds (forks off -- the 15% bar applies to HEADS only, per the
roadmap's own wording; sim-pace's verdict stands from the 24-seed round): zero 26.96 / EMA 20.78
(slope -0.09) / head 17.97 = +13.5% (BELOW the 15% bar) with slope 0.14 (calibration COLLAPSED
further with 6x data). Both gate criteria fail AT SCALE -> the miscalibration is structural
(control-loop endogeneity), not sampling noise. M4 verdict FINAL: EMA stands, zero learned
components ship. Data: results/m4_pace_full.csv.

### M4 FINAL, both challengers at full 144-seed scale (2026-08-24) -- + a self-caught reporting bug

CORRECTION FIRST: the earlier "144-seed" table printed a simpace row while forks were DISABLED
(scored a zero-vector: 26.96/-29.7%/nan). That row was meaningless and should never have been
printed; exp_m4_pace.py now refuses to score the sim arm unless FORKS=1. The head's numbers in
that run WERE valid (verified: 3836 rows / 144 seeds / 811 held-out tasks).

FULL-SCALE TABLE (96 train / 48 held-out seeds, 811 test tasks, 416 with a live fork reading):
  zero (no correction)  MAE 26.96  -29.7%   slope n/a
  EMA (shipped)             20.78    0.0%   slope -0.09
  learned head              17.97  +13.5%   slope  0.14   FAIL (bar 15% + slope 0.7-1.3)
  sim-pace fork arm         20.60   +0.9%   slope -0.08   FAIL (no better than the EMA)
The 24-seed sim-pace lead (+4.8%) DISSOLVED at scale -- the split-half law again. Why: a 50-step
fork completes only a handful of tasks, so its EMA is a noisier read of the same quantity the
real EMA already tracks; simulation cannot beat measurement when the thing measured is the
system's own recent behavior (contrast: forks DO win for BATTERY futures, which are physics the
present doesn't reveal). M4 CLOSED: EMA stands, zero learned components ship. Both challenger
datasets kept (m4_pace_full.csv, m4_pace_full_forks.csv).

### M4 DEFINITIVE (2026-08-24): pace can't matter -- the decision rule ignores finish time

FOUR-ARM VALUE RACE (held-out seeds 97-144, 48 paired days; the champion applies NO pace
correction today -- _finish_delay()==0, delay_head None):
  champion (nothing)          388.75    --            0W/48T/0L
  emapad (live EMA as pad)    388.12   -0.63 (t=-1.01) 3W/38T/7L
  simpace (fork-measured)     385.65   -3.10 (t=-1.43) 3W/36T/9L
  head (per-candidate LGBM)   388.33   -0.42 (t=-1.00) 0W/47T/1L
ALL FLAT-TO-NEGATIVE. No arm ships.

THE MECHANISM (the real M4 finding, sim_priority._deadline_score): the deadline score is a HARD
TIER -- makeable (proj_late<=0) scores 1000+value with FINISH TIME ABSENT FROM THE SCORE; doomed
scores value*decay^lateness. So a pace estimate can only change a decision by flipping a task
ACROSS the makeable/doomed boundary; within a tier it is invisible. Verified directly: the
per-candidate head is live and discriminating (predictions vary ~26 steps between candidates in
the same step) yet changed 0 of 68 assignment decisions across 4 seeds. Also measured: only ~9
of 200 steps present MORE THAN ONE candidate (matches the 86.9% single-candidate finding), so
even reordering power has few chances to act.
=> The five historical delay-prediction nulls were never about delay being unpredictable. THE
CONTROLLER WAS DESIGNED NOT TO CARE: it asks "will it make it?", not "how fast?", then ranks by
value. Pace accuracy is worthless to a step function. IF we ever wanted pace to pay, the change
is in the SCORER, not the predictor (a soft P(on-time) score -- the override hook already exists
in _deadline_score's docstring) -- and that is a decision-layer redesign, not a Stage-3 head.
M4 CLOSED: EMA stays as a tracker/feature; zero learned components ship; slot stays empty.

### M5 BENCHMARK TABLE (2026-08-24 overnight, 1152 runs = 4 arms x 2 regimes x 144 seeds)

exp_m5_bench.py, large-8-6, exogenous demand, champion stack + battery + bays. NB fifo/rush run
WITHOUT battery physics (drain lives in the m3 controller's act) -- free energy is an ADVANTAGE
to the baselines, so every champion win below is conservative.

WAVE      value   deliv   hit%   tardMean  tardP95  strand  frozen
  fifo    643.5   24.1   81.9%    112.2     198.7      0      4
  rush    684.8   26.4   78.5%    153.0     244.9      0     12
  champ   779.3   26.6   86.4%    114.6     206.4      0      0
  mpc     782.9   26.7   86.7%    114.1     204.3      0      0
  fifo vs champ -135.81 (-17.4%, t=-9.13) | rush -94.44 (-12.1%, t=-9.21)
  MPC vs champ +3.60 (+0.5%, t=+2.41)  <- PASSES the t>=2 bar at 144 seeds, wave
STREAM    value   deliv   hit%   tardMean  tardP95  strand  frozen
  fifo    368.0   27.5   65.4%     56.1     106.3      0      9
  rush    492.7   30.1   78.5%     63.6     120.5      0     13
  champ   547.8   30.5   77.8%     58.7     129.8      0      2
  mpc     557.4   30.8   78.3%     59.0     126.0      0      2
  fifo vs champ -179.82 (-32.8%, t=-11.28) | rush -55.10 (-10.1%, t=-4.94)
  MPC vs champ +9.54 (+1.7%, t=+1.90)  <- just under the bar, same sign as the campaign

HEADLINES: champion beats the vendored FIFO by +21.1% (wave) and +48.9% (stream) -- the
roadmap's ">= FIFO clean, target +10%" met twice over, while PAYING the energy tax the baselines
skip. Champion also dominates on SAFETY: 0 stranded in all 1152 runs; frozen carriers 4/12 (fifo/
rush wave) and 9/13 (stream) vs 0 and 2 for champ/mpc -- the baselines wedge robots, the
champion's repair layer does not. Energy/task 0.079-0.083 (mpc slightly cheaper on stream).
HONEST EXCEPTION: seed 125 stream has 2 carriers frozen for the last 100 steps under BOTH champ
and mpc (574/576 runs clean). The audited "frozen 0/144" was the WAVE regime; stream has this one
instance -- open item, same forensic method as the M3 freeze work.

### M5: MovingAI MAPF INNER-LOOP SANITY -- PASS (2026-08-24)

exp_m5_mapf.py runs OUR planner (pyastar2d, the same call find_path makes) on the standard
MovingAI benchmarks (data/mapf/, maps + scen-even from movingai.com), 600 scenario rows per map,
1800 cases: SOLVED 100.00% (bar >=98% -> PASS), unreachable 0.
Optimality vs BFS-computed 4-CONNECTED ground truth (MovingAI's own optimal_length column is
8-connected octile and is NOT the right bar for a non-diagonal planner):
  warehouse-10-20-10-2-1  100.0% optimal  <- OUR DOMAIN: structured aisles, always optimal
  empty-32-32             100.0% optimal
  random-32-32-20          91.0% optimal  <- scattered clutter
FINDING (small, real): in randomly-cluttered maps pyastar2d returns paths averaging +0.22 steps
long (19/200 cases suboptimal; excesses of exactly 2 or 4, max 4) -- its heuristic is not tight
for 4-connected movement. IRRELEVANT TO US IN PRACTICE: on aisle-structured maps (warehouse
benchmark AND our own layouts) optimality is 100%, because corridor topology leaves no room for
the heuristic to mis-order equal-cost frontiers. Plumbing validated; no action.

### M5 SAFETY METRICS -- MEASURED, and a placeholder caught (2026-08-24)

CORRECTION: the bench table's `collisions` column read env._collisions, WHICH DOES NOT EXIST --
every row silently recorded 0. That was a placeholder, not evidence (same failure class as the
forks-off simpace row). Replaced by exp_m5_safety.py, which measures collisions directly.
DETECTOR SUBTLETY (also measured, not assumed): AGVs and PICKERS legally share a cell -- that IS
the rendezvous, ~1 per step. Counting any shared cell as a collision reported ~300/300 steps of
false positives. Only SAME-TYPE overlap is a collision.
RESULT (4 arms x 48 seeds, disturbances ON, 500 steps each = 96k agent-steps/arm):
  arm     vertex-coll  swap-coll  replans/day  replans/spill  stuck-steps/day
  fifo         0           0         74.5         8.97          293.2
  rush         0           0        112.4        13.75          304.6
  champ        0           0        121.2        14.28          276.0
  mpc          0           0        117.8        13.95          299.3
ZERO collisions of either kind for every controller -- the env referee's guarantee is now
EMPIRICALLY VERIFIED rather than assumed. Replans/disturbance ~9-14 (the roadmap's missing
metric): the champion replans MORE than FIFO (14.3 vs 9.0 per spill) and that is the mechanism
working -- belief-driven rerouting is exactly what buys the +24%/+38% margins under disturbances,
and it converts into the LOWEST stuck-steps (276 vs 293-305).

### M5 HEAD-TO-HEAD UNDER DISTURBANCES (2026-08-24, 1152 runs) -- target met 3-6x over

exp_m5_bench.py DISTURB=1 (multi-cell spills, stuck-until-cleaned, shipped belief map; every arm
sees identical hazards on identical days).
WAVE      value   deliv   hit%   tardMean  tardP95  strand  frozen*
  fifo    580.6   20.6   81.0%    108.4     186.5      0     32
  rush    659.7   24.4   79.9%    155.4     240.6      0     34
  champ   764.0   24.5   86.9%    104.8     186.0      0     18
  mpc     764.1   24.5   87.2%    105.6     184.5      0     19
STREAM    value   deliv   hit%   tardMean  tardP95  strand  frozen*
  fifo    302.4   22.9   61.3%     76.4     144.3      0     25
  rush    434.8   26.5   76.6%     77.8     138.2      0     31
  champ   490.8   27.7   75.5%     63.1     131.2      0     40
  mpc     491.7   27.8   75.7%     64.0     131.1      0     26
CHAMPION vs FIFO: +31.6% (wave, t=10.95) and +62.3% (stream, t=11.81) -- the roadmap's
">=FIFO clean, +10% under disturbances" bar cleared 3-6x. vs RUSH: +15.7% / +12.9%. Margins are
LARGER than without spills (+21.1%/+48.9%): the belief map + repair layer are worth more exactly
when the floor is hazardous, and the champion also wins deadline hit-rate and BOTH tardiness
percentiles while paying an energy tax the baselines skip.
*frozen under DISTURB is NOT the wedged-robot metric: a robot immobilized in a spill it is
waiting out counts as "never moved while carrying". Comparable across arms, not to the
disturbance-free table.
NEW FINDING -- THE TUNER GOES QUIET UNDER NOISE: mpc vs champ is +0.0% wave (t=+0.06) and +0.2%
stream (t=+0.22), versus +0.5% (t=+2.41) and +1.7% on clean floors. Mechanism: forks now SAMPLE
spill futures (the honest-fork fix), so rollout scores carry hazard noise the candidate settings
cannot beat -- the UCB comparison drowns. Consistent with the campaign's own lesson (ties are
honest); the tuner pays where the signal is clean (battery/charging) and abstains where it is
not. NOT a regression: the champion's own margins are what grow under disturbances.

### MARL LEARNED DISPATCHER (2026-08-24): loses to the rules, lands between FIFO and Rush

Built scripts/marl_dispatch.py (torch installed for this): shared-parameter policy
MLP(24->64->64->1) scoring the SAME candidate set the champion scores, plugged into
_pick_winner; softmax sampling in training, argmax at eval; dense per-decision credit (each
decision credited with the on-time value its chosen task actually earned); REINFORCE + running
baseline + entropy bonus; 40 iters x 24 episodes = 960 episodes on seeds 1-96.
LEVEL CHOSEN DELIBERATELY: task-selection, not primitive moves. RWARE-standard move-level MARL
would mostly learn locomotion and is known to trail greedy heuristics at this scale; scoring the
same candidates isolates the DECISION layer, which is the claim under test.
TRAINING: mean episode value 895 -> ~930 over 40 iters (it DOES learn: +4%).
HELD-OUT EVAL (seeds 97-144, greedy): marl 368.20 vs champion 388.75 = -5.3%, t=-5.57, wins 7/48.
CONTEXT ON THE SAME SEEDS: fifo 357.30 | MARL 368.20 | rush 370.24 | champ 388.75 | mpc 389.42.
=> the learned policy beats the vendored FIFO heuristic and ties the value+urgency rule, but
loses to the rule stack by 5.3%. Consistent with M1's flatness result: the decision layer is
near-maxed for this information set, and a policy-gradient learner with IDENTICAL inputs cannot
find headroom the rules leave behind.
HONEST CAVEATS: REINFORCE (not PPO), ~960 episodes, no hyperparameter search, single fleet/map.
A tuned PPO with 10-100x the budget might close or invert the 5.3%; this is evidence, not proof
of impossibility. NB seed ranges differ in richness (window_index=seed maps to diurnal phase:
seeds 1-96 mean 974.5 vs 97-144 mean 388.8 for the champion) -- all comparisons above are
within-seed paired, so the split is harmless, but raw values across ranges are NOT comparable.

### M5 COMPLETE (2026-08-24): consolidated ablation table + MARL baseline

MARL LEARNED DISPATCHER (marl_dispatch.py, policy gradient, shared-parameter policy over the
champion's own candidate set + 24 assembler features, 960 training days, greedy eval on held-out
seeds 97-144): champion 388.75 / MARL 368.20 = -5.3% (t=-5.57, 7 wins/48). For reference on the
same seeds: fifo 357.30, rush 370.24, mpc 389.42. So the learned policy BEAT the vendored FIFO
and matched the Rush rule, but lost to the champion given identical information -- closing the
"baselines are in-house heuristics" caveat. Caveat kept: modest budget, simple algorithm.
CONSOLIDATED ABLATION TABLE -> docs/ABLATION.md: 10 mechanisms shipped, 21 measured and cut,
each with its number, its bar, and its mechanism. Sandbox r28 carries a layman version.
M5 IS NOW COMPLETE: metric suite, safety metrics (measured), TA-RWARE head-to-head clean AND
under disturbances, MovingAI MAPF sanity, MARL baseline, ablation table. Remaining: M6 paper
assembly, the MPC cadence sweep, and the seed-125 stream freeze.

### M5: BRIER + PR CURVES (proposal's stated metrics; 2026-08-24)

exp_m5_brier.py -- belief map scored as a per-cell probabilistic detector over EVERY highway cell
at EVERY step, 24 seeds x 2 arms (~4.8M predictions/arm), 1000-bin score histograms.
  arm      Brier    skill vs base rate   AUPRC (random 0.032)   detection latency
  reset    0.0204        +0.351               0.367              mean 20.4 / median 2
  legacy   0.0310        +0.013               0.260              mean 18.8 / median 1
HEADLINE: the OLD map had essentially NO probabilistic skill (+0.013 -- barely better than
always predicting the base rate) despite being useful for routing; the reset rule is a real
forecaster (+0.351 skill, AUPRC 11x random). Brier 34% lower.
SUBTLE + IMPORTANT: DETECTION LATENCY IS UNCHANGED (median 1-2 steps both arms). The fix was
never about seeing spills sooner -- both maps notice immediately. It is about SUSTAINING the
belief afterwards: the old map's fresh sighting was outvoted back below threshold within a few
steps, so it kept forgetting what it had already seen. That is why value rose (+28.8) while
latency stayed flat, and it is the cleanest statement of the mechanism yet.
Figure: results/m5_belief_curves.png (PR / reliability / latency CDF, both arms overlaid).
Reliability panel shows near-binary beliefs: mass at 0 and 1, with the uninformed 50% prior
sitting well below the diagonal (documented, deliberate -- a base-rate prior would rebuild the
stale-clean mountain the reset rule exists to remove).

### CHARGING FORESIGHT (the one untested channel) -- FORESIGHT NULL, but a REAL tuning finding

exp_charge_foresight.py, STRESS days (M3SPC=300 + low starts, where charging binds), 48 paired
seeds, threshold re-evaluated every 25 steps with a 0.03 deadband:
  arm    value    vs base           stranded  mean threshold
  base   742.30    +0.00            123        0.400
  fore   771.62   +29.33 (t=+1.34)  108        0.377   <- TRUE oracle preview of arrivals
  shuf   792.57   +50.27 (t=+3.15)  104        0.377   <- SCRAMBLED preview (wrong half of day)
  hi     761.04   +18.74 (t=+0.84)  112        0.460   <- constant higher threshold
  const 0.377      744.25 (+0.3%, t=+0.10)     117     0.377   <- constant at the dynamic mean
VERDICT: FORESIGHT DOES NOT PAY ON THE CHARGING CHANNEL EITHER. The scrambled arm BEATS the
informed one; a constant threshold at the same mean gives nothing. The information content is
worthless -- the 6th independent leg of the anticipation null.
THE REAL FINDING (mechanism, measured not guessed): what pays is THRESHOLD VARIATION, and the
cause is an ASYMMETRY. Raising a charge threshold CAUSES a charge event; lowering one merely
POSTPONES. So an oscillating threshold ratchets charge frequency up (22.8 trips/day vs 20.0) even
though its MEAN is lower (0.377 vs 0.400), and it buys the safety benefit intermittently rather
than paying for it all day like a constant-high threshold (23.5 trips but only +2.5%).
Desynchronization was TESTED AND REJECTED as the explanation: the varying arm clusters charge
starts MORE (3.8 vs 2.5 within 3 steps), with identical concurrency.
=> Actionable: on stress days the fleet is under-charging (123 strandings at the shipped fixed
threshold). A time-varying threshold recovers ~7% and a third of the strandings WITHOUT any
forecast. Candidate for the tuner's move set (it already owns theta) -- as OSCILLATION, not level.
BUG FOUND EN ROUTE (fixed): sim_dashboard.py:210 `assigned_items.pop(agv)` raised KeyError when a
charge decision preempted a RETURNING mission. The MPC retunes theta every 50 steps, so this was
a live crash risk in production MPC runs, not just in this experiment. Now pop(agv, None).

### MPC CADENCE/HORIZON SWEEP (the tune-later item) -- HORIZON was too short (2026-08-24)

exp_mpc_cadence.py, stress days, 48 paired seeds, vs the fixed-constant control:
  cadence/horizon   value    vs fixed   t      adoptions  imagined steps/day  stranded
  fixed (no MPC)    742.30    +0.00   +0.00        0            0             123
  25 / 50           789.02   +46.72   +2.51      129         2909              88
  25 / 100          815.35   +73.05   +3.73      211         5543              69
  50 / 100 SHIPPED  799.87   +57.57   +3.23      127         2952              95
  50 / 200          838.99   +96.69   +5.86      137         5770              66
  100 / 200         817.64   +75.34   +5.07       90         3000              63
FINDING: the shipped 50/100 is NOT the optimum. HORIZON is the lever, not cadence: doubling the
horizon at the same cadence (50/200) is worth +39 more value and cuts strandings 95 -> 66; it is
the best cell tested. Cadence barely matters (25/100 vs 50/100 differ by +16 for 2x the forks;
100/200 nearly matches 50/200 at HALF the compute and the FEWEST strandings, 63).
BEST VALUE-PER-COMPUTE: 100/200 (+75.3, t=+5.07, 3000 imagined steps/day -- the same budget as
the shipped setting). BEST ABSOLUTE: 50/200 (+96.7, t=+5.86, 2x compute).
WHY: a charge round-trip plus its productive tail does not fit in 100 steps, so the shipped
horizon scores candidate settings before their cost or benefit has landed -- exactly the failure
mode the horizon was designed to avoid, just mis-sized. Rollouts were never wrong, just short.
=> RECOMMEND: 100/200 as the new default (same compute, +3.5% over shipped on stress days).
Needs a wave/stream re-check before shipping since this cell is stress-only.

### SANDBOX r33 + PAPER DRAFT BROUGHT CURRENT (2026-09-05)

USER ASK: (a) explain in the sandbox what the Brier curves mean; (b) update the paper draft with
all info.
(a) SANDBOX r33 (template + rebuild + republished to the same artifact URL,
https://claude.ai/code/artifact/9864307f-92ef-4239-8f5a-ddb72795c963). New Scoreboard section
"9 - How to read those three charts", directly under the m5_belief_curves figure: what a Brier
score is (squared miss, averaged; 0.9-on-blocked costs 0.01, 0.9-on-clean costs 0.81, hedging at
0.5 always costs 0.25); why the raw number is misleading (3.2% base rate -> a lazy "3.2%
everywhere" forecaster already scores 0.031) and what SKILL fixes (+0.351 shipped vs +0.013 old);
then one card per panel -- PR (threshold sweep, recall/precision, 0.367 vs 0.032 random),
reliability (claimed vs observed, near-binary mass at the ends, 98.0 vs 97.9, the deliberate 0.5
sag for unlooked cells), and the latency CDF (identical curves = the fix was memory, not
perception). Closing note: the three panels answer three different questions and the old map
passed only the third. Added glossary entry #25 "Brier score", wired the two bare Brier mentions
to it, and fixed the stale glossary superscripts (fork/mpc were swapped; mapf/worldmodel/
modelfree/belief were off by one). Verified in-browser: heading + 3 cards render, glossary popup
fires, no horizontal overflow.
(b) PAPER_DRAFT.md 54.6k -> 73.0k chars. Everything from M5 onward was missing. Added:
  5.19 heading (M4/pace was buried inside 5.18); moved the "improving the clock" coda there.
  5.20 heading for the existing benchmark/safety/MAPF prose.
  5.21 NEW -- MARL learned dispatcher (960 days, -5.3% t=-5.57, FIFO 357.3 < MARL 368.2 <
       Rush 370.2 < champ 388.8), with the REINFORCE/budget caveats stated.
  5.22 NEW -- the belief map graded as a forecaster: Brier/skill/AUPRC/latency table, the
       base-rate argument, calibration, and the identical-latency mechanism claim. The three
       Brier sentences were CUT out of 5.20 and expanded here.
  5.23 heading for the existing sight-vs-prediction decomposition.
  5.24 NEW -- consolidated ablation ledger (10 shipped / 21 cut).
  5.25 NEW -- charging foresight: the 6th VoPI leg, scrambled beats true (+50.3 vs +29.3), the
       raise-causes / lower-postpones asymmetry, ~7% and a third of the strandings available.
  5.26 NEW -- MPC cadence/horizon sweep: horizon is the lever, 100/200 recommended at equal compute.
  Abstract rewritten around the TA-RWARE head-to-head + safety + 6-leg null + forecaster metrics.
  Contributions 3 -> 5. Discussion +5 principles (grade beliefs as forecasters; look for the panel
  where nothing changes; use a SCRAMBLED control not just an uninformed one; a learner is the right
  control for "your baselines are heuristics"; size a lookahead against the decision it judges).
  Limitations: the debris-planning-layer-only and disturbances-off items marked RESOLVED, and six
  new honest ones added (seed-125 zero-spare-slots, MARL budget, 24-seed forecaster grading,
  stress-day-only charging/horizon results, pyastar sub-optimality on cluttered maps).
  Conclusion rewritten; next-steps list re-prioritised (M5 closed; horizon 200, spare slots,
  threshold oscillation, figures, release).
Backups of both pre-edit files are in this session's scratchpad.
