# Figure and Table Specifications

Build sheet for the paper. Each entry states the **one claim the figure must make true**, its data
source, its form, its required annotations, and a draft caption. A figure that does not make its
claim legible in isolation is not finished.

**Status audit, 2026-09-06.** Two entries previously marked "exists" were re-inspected and
downgraded. `diag_realism_pass.png` and `champion_architecture.png` are excellent *working*
diagrams but not paper figures: they carry internal class names, references to `docs/NOTES.md`,
work-planning notes ("one revalidation planned after M2+M3"), and aphorisms. The architecture
diagram also predates the self-tuner, so it depicts the champion *without* the layer that makes this
a world model. Both need rebuilding.

| # | Claim it must make | Status |
|---|---|---|
| Fig. 1 | Four decisions are coupled, on one floor | **build** |
| Fig. 2 | Correcting the world cost 66% of throughput | **rebuild** |
| Fig. 3 | The planner is a funnel ending in a rollout, wrapped by a tuner | **rebuild** |
| Fig. 4 | The margin over the vendored dispatcher grows under disturbances | ready |
| Fig. 5 | More future is monotonically worse, and no channel pays | ready |
| Fig. 6 | The map is a calibrated forecaster; the fix was memory, not perception | ready |
| Fig. 7 | The worse the sensors, the more prediction carries | ready |
| Fig. 8 | Everything kept reasons about what exists | ready |
| Fig. 9 | Horizon is the lever; cadence is not | ready |
| Table 1 | Every world constant, corrected or declared | **build** |
| Table 2 | The 24 decision features | **build** |
| Table 3 | Metric suite against pre-registered targets | **build** |

Shared style: `scripts/make_paper_figures.py` holds the palette (categorical slots validated for
colour-vision deficiency, adjacent-pair ΔE 9.1), the recessive grid, tabular numerals, and direct
labelling. New figures go in the same file and inherit it. Greyscale-safe: no claim may rest on hue
alone.

---

## Fig. 1 — The coupled decision *(build)*

- **Claim:** a free robot's next action couples four decisions that are usually studied separately.
- **Form:** labelled schematic of one floor, not a photograph. Single panel, landscape.
- **Content:** the dense-aisle layout at true proportions — 180 storage cells, 8 charger bays,
  3 pick stations, highway lanes. One AGV highlighted mid-decision with four annotated arrows:
  1. *which task* → two candidate pods, one nearer and cheap, one further and high-value near deadline
  2. *which route* → two paths to the same pod, one through a congested aisle
  3. *when to charge* → the battery arc, with the nearest bay and the energy-feasibility radius
  4. *what is unknown* → a spill drawn in ground truth, and the same cell drawn as the fleet believes it
- **Required annotation:** the four arrows numbered and named; a legend distinguishing *true state*
  from *believed state*; a scale bar in metres (cell = 1 m).
- **Do not** include scores, formulae or class names. This figure is the problem, not the method.
- **Source:** layout from `wwm_sim.warehouse` geometry; render alongside the sandbox's floor drawing.
- **Draft caption:** *Figure 1. The four coupled decisions facing a single free robot on the
  dense-aisle floor. Solid outlines mark true world state; dashed outlines mark the fleet's belief.
  The robot must simultaneously choose a task (1), a route through contested aisles (2), whether to
  charge first given its remaining range (3), and how much to trust a hazard nobody has observed
  recently (4). Each is a well-studied problem in isolation; the coupling is what this paper
  addresses.*

## Fig. 2 — The realism audit *(rebuild)*

- **Claim:** correcting the simulator's constants cut measured throughput by 66%, and every result
  taken before the correction was measured on a world three times too productive.
- **Form:** horizontal waterfall, four bars, single panel. Strip everything else from the existing
  dashboard — the constants list becomes **Table 1**, the "what this invalidates" panel becomes prose
  in §2.1, and the "NEXT —" action box is deleted.
- **Encodings:** x = deliveries per three episodes (171 → 95 → 76 → 58); each bar labelled with its
  value and the correction that produced it (`+ geometry`, `+ lognormal values`, `+ service times`).
- **Required annotation:** a bracket spanning first to last reading **−66%**.
- **Source:** the four figures already computed for the dashboard; re-plot at paper scale.
- **Draft caption:** *Figure 2. Cumulative effect of the realism audit on measured throughput.
  Correcting storage density, station count, step duration, order-value distribution and
  per-operation service times reduced deliveries per three episodes from 171 to 58. Every result
  predating this correction was obtained on a simulator approximately three times too productive,
  and is excluded from this paper.*

## Fig. 3 — The planner *(rebuild)*

- **Claim:** decisions come from imagined futures — the funnel prepares candidates, the rollout
  chooses, and the self-tuner re-chooses the funnel's own settings.
- **Form:** two-column flow with an enclosing loop. Left column: the seven AGV stages. Right column:
  the picker path. An outer band, drawn around both, is the self-tuner.
- **Content, and what changes from the working diagram:**
  - **add the tuner** — every 50 steps, deep-copy the warehouse, roll 200 steps forward under
    candidate settings, adopt the winner. Its absence is why the working diagram depicts the
    ablated system.
  - mark step 6 as the **only** decision point; steps 1–5 are preparation that orders a shortlist
  - mark step 7 as commit-first-move-only, with the imagined tail visibly discarded
  - **remove:** internal class names, `docs/NOTES.md` references, the frozen-knob table, the
    "how it was measured" panel, the work-planning note, and the closing aphorism
  - **keep:** the honest annotation that the imagination sees no future orders
- **Required annotation:** one number only — removing the rollout costs **−7.2%** (t = −30.6), the
  largest single mechanism effect in the paper.
- **Draft caption:** *Figure 3. The decision layer. For each free robot, stages 1–5 reduce the task
  set to roughly fifteen legal candidates and order them; stage 6 simulates each candidate forward
  under the fleet's own physics and selects by simulated banked value; stage 7 commits only the
  first move. The enclosing loop is the model-predictive tuner, which re-selects the funnel's own
  settings every 50 steps by the same forward simulation. Stage 6 is the only point at which a
  decision is made: disabling it costs 7.2% of on-time value.*

## Fig. 4 — Benchmark *(ready — `results/fig_benchmark.png`)*

- **Claim:** the shipped system beats the simulator's own dispatcher in every condition, and by more
  when the floor is hazardous.
- **Check before use:** the bracket annotation must point at the **shipped** arm (rules + tuner), not
  the ablated champion. Regenerate after the 2026-09-06 re-lead so the callouts read
  +21.7 / +48.8 / +31.6 / +65.4.
- **Draft caption:** *Figure 4. On-time value per day against the simulator's built-in dispatcher
  (FIFO), a value-and-urgency heuristic (Rush), the rule stack alone, and the shipped system, across
  both order regimes with and without disturbances. Each bar is the mean of 144 paired days; both
  baselines run without battery physics, so every margin shown understates the difference. The
  margin widens under disturbances, from +21.7% to +31.6% on wave days and from +48.8% to +65.4% on
  live-stream days.*

## Fig. 5 — The anticipation null *(ready — `results/fig_anticipation.png`)*

- **Claim:** more of the future is monotonically worse, and no channel pays.
- **Draft caption:** *Figure 5. Left: on-time value as a function of how far ahead the planner is
  given perfect knowledge of future orders, from none to a full day. Damage grows monotonically with
  the horizon. Right: six independent information channels, each supplied with the true future
  before any estimator was built for it. The charging channel is positive but not from information —
  a deliberately scrambled forecast outperformed the true one — so the gain is attributable to
  threshold movement rather than knowledge.*

## Fig. 6 — The belief map as a forecaster *(ready — `results/m5_belief_curves.png`)*

- **Claim:** the map is a calibrated forecaster where it acts, and the improvement over its
  predecessor was memory rather than perception.
- **Draft caption:** *Figure 6. The disturbance belief map scored as a probabilistic detector over
  4.8 million per-cell predictions per arm. Left: precision–recall against a 3.2% base rate. Centre:
  reliability, with the near-binary belief mass at the extremes landing on the diagonal (98.0%
  stated against 97.9% observed); the central sag is the uninformed prior, held at 0.5 by
  convention. Right: detection-latency distributions for the two maps, which are identical — both
  notice a spill immediately, and only the shipped rule continues to believe it afterwards.*

## Fig. 7 — The sensing inversion *(ready — `results/fig_sensing.png`)*

- **Claim:** the worse the sensors, the more of the sensing value prediction carries.
- **Draft caption:** *Figure 7. On-time value above a blind fleet, decomposed into the contribution
  of direct sight and of remembered prediction, across four sensor ranges. At a five-cell range
  sight carries 74% of the benefit; at near-contact range the split inverts and prediction carries
  76%. The dashed line marks a clairvoyant fleet given the true hazard state.*

## Fig. 8 — The keep/cut ledger *(ready — `results/fig_ablation.png`)*

- **Claim:** everything kept reasons about what already exists; everything cut acted on what did not.
- **Draft caption:** *Figure 8. Every mechanism built for this project, judged against a bar fixed
  in advance: at least 3% of on-time value on paired days, or cut. Four kept mechanisms are safety
  or enabling components judged on hard constraints rather than value and carry no bar. The two
  halves separate cleanly by what the mechanism reasons about, not by how sophisticated it is.*

## Fig. 9 — Tuning the tuner *(ready — `results/fig_horizon.png`)*

- **Claim:** the rollout horizon is the lever; how often it re-plans is not.
- **Draft caption:** *Figure 9. Left: on-time value against imagined steps per day for six
  cadence-and-horizon settings on battery-stress days. Doubling the horizon at fixed compute is
  worth more than halving the cadence. Right: robots stranded under each setting. The adopted
  100/200 configuration spends the same fork budget as the shipped 50/100 while stranding half as
  many robots.*

---

## Table 1 — World constants *(build)*

- **Purpose:** make the realism audit auditable. This table is the reason §2.1 is a contribution
  rather than setup.
- **Columns:** Constant · Original value · Corrected value · Source or justification · Status
- **Status vocabulary:** `verified` (was already right) · `corrected` (changed, with a source) ·
  `opt-in` (implemented, off by default) · `declared` (mechanism cited, magnitude chosen) ·
  `assumed` (no public data exists)
- **Rows:** all sixteen from the existing dashboard — cell size, one robot per cell, deadline
  multiple, storage density, station count, step duration, picker service, station service, value
  distribution, arrival rate, diurnal period, one-way lanes, demand-shape parameters, disturbance
  rate, amnesty duration, battery constants.
- **Caption above the table:** *Table 1. Every world constant in the simulator, its original and
  corrected value, and the evidence for the correction. Four constants have no public data and are
  declared as assumptions rather than calibrated.*

## Table 2 — The decision features *(build)*

- **Purpose:** show the learner and the rules saw the same information, which is what makes §3.5's
  negative result a fair test.
- **Columns:** Feature · Group · Units · Available to the rules · Available to the learner
- **Groups:** self (position, battery, current mission) · task (value, deadline slack, distance,
  predicted finish) · fleet (queue depth, busy fraction, picker ETA) · congestion (local density,
  path stretch)
- **The final two columns should be identical throughout** — that is the point of the table.
- **Caption:** *Table 2. The 24 features available at each dispatch decision. The learned dispatcher
  of Section 3.5 receives exactly this set, over exactly the same candidate shortlist, so the
  comparison isolates the selection rule.*

## Table 3 — Metric suite and targets *(build)*

- **Purpose:** report against pre-registered targets rather than chosen ones, including the one that
  is missed.
- **Columns:** Metric · What it grades · Pre-registered target · Measured · Verdict
- **Must include the misses and near-misses honestly:**
  - sensitivity ≥90% → 92.2% by event · **met** *(footnote: recorded as failed for months because
    per-cell-step recall was compared against an event-level target)*
  - specificity ≥90% → 99.87% · met *(footnote: the easy half at a 3.2% base rate)*
  - median detection latency ≤15 → 2 steps · met
  - ≤1 phantom hard-block per 1,000 steps → 9.8 · **not met** *(footnote: a perfect-memory oracle
    on the identical sight stream scores 9.2, so the attainable floor is itself nine times the
    target)*
  - collisions and strandings = 0 → 0 and 0 · met
  - inner loop ≥98% MAPF success → 100% · met
  - decision latency ≤1 s at five robots → 1.3 ms median · met
  - every mechanism ≥3% or cut → applied 32 times · met
- **Caption:** *Table 3. Every success criterion registered before the work began, with its measured
  outcome. One criterion is not met; the accompanying oracle measurement establishes that its target
  was not attainable at this sensing density.*

---

## Build order

1. **Table 3** — cheapest, and it frames every result section.
2. **Fig. 3** — the method figure; the paper cannot be read without it, and the current version
   depicts the wrong system.
3. **Table 1** — split out of the existing realism dashboard.
4. **Fig. 2** — the waterfall left over once Table 1 is extracted.
5. **Table 2** — needs the feature list pulled from the assembler.
6. **Fig. 1** — last, because it is the only purely illustrative figure and the paper survives
   without it if time runs short.

Regenerate Fig. 4 after the shipped-system re-lead so its callouts match the text.
