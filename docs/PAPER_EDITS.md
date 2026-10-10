# Paper edits after the corrected-floor rerun and the baseline campaign

Everything below is keyed to the draft dated 2026-10-09. Each item says **where**, **what is wrong**,
and **what to write**. Paste-ready text is in blockquotes.

Measurements behind these edits: `results/m5_bench_retired*.csv` (headline, 144 paired seeds),
`results/mapd/` (literature baselines and the parity-split learner), `results/missing/` (the five
re-measured experiments), `results/retired/mpc_campaign.csv` (the 46-configuration sandbox).

---

## Priority 0 — internal contradictions

These make the paper disagree with itself, so a reader finds them without checking any data.

### 0.1 Picker count
§2.1 says "four pickers". §4.5 says "eight AGVs, six pickers". The simulator instantiates **six**
picker agents for the `large-8-6` configuration. Fix §2.1 to six.

### 0.2 The learner's train/test split
§2.5 says *"Seed parity, rather than sequential halves, is used for split-half checks because seeds
tile a daily demand profile"* — then four paragraphs later, *"trained … on seeds 1–96. Seeds 97–144
are reserved for evaluation."* That is the sequential split the same section rules out, and it
matters: seed difficulty is monotone in the index. Use the §2.5 rewrite in item 2.1 below.

### 0.3 Whether the charger-bay rerun happened
§4.4 now correctly reports it as done. §5's future work still says *"the charger-bay world-model
defect should be corrected and the complete benchmark rerun for every method and baseline."*
Delete that sentence from §5.

### 0.4 Scope of the sandbox
§4.5 opens with "one map family, one fleet size" and four lines later describes a sandbox spanning
different fleet sizes, picker counts and map sizes. Rewrite the opening as item 4.3.

---

## Priority 1 — sections not yet revised

### 1.1 §3.4, learned dispatcher comparison — replace entirely

The current text uses the superseded sequential split, describes the two arms incorrectly ("the
constants were learned from the start … versus the dispatcher where they were tuned over time"), and
states that the sandbox tested the learner. The sandbox has no learner arm; it compares the planner
with its tuner on against the same planner with fixed constants.

> The learned dispatcher was retrained and evaluated on a parity split — even seeds for training,
> the 72 odd seeds for evaluation — because seed difficulty is monotone in the seed index and the
> original sequential split tested it on days roughly 2.5 times harder than those it trained on. It
> was then evaluated in all four benchmark conditions rather than one.
>
> The planner led in every condition: by 4.0% on the clean wave regime (t = 3.38), 0.1% on clean
> stream (t = 0.08), 2.1% on disturbed wave (t = 1.41), and 1.7% on disturbed stream (t = 0.77).
> Only the first is statistically distinguishable from zero. The comparison isolates candidate
> selection: both systems receive the same candidate set and the same 24 features, and routing,
> battery handling, and execution are identical.
>
> The learned dispatcher was nevertheless the strongest comparator in the study, exceeding FIFO by
> 11.9–29.3%, the optimal myopic assignment by 12.0–27.5%, and the weighted-tardiness heuristic by
> 6.0–12.9% across the four conditions. A learned scorer with matched inputs therefore reaches
> approximately the same decision quality as the rollout planner on this map and fleet, while
> requiring 960 training episodes to do so. The planner's settings transfer across the 46 sandbox
> configurations without retraining; the learner's transfer was not tested.

### 1.2 §3.5, disturbance belief map — every number is pre-correction

| Claim | Draft | Corrected |
|---|---|---|
| Brier skill, pre-correction map | +0.013 | **+0.126** (Brier 0.02745) |
| Brier skill, shipped map | not stated | **+0.472** (Brier 0.01660) |
| Clairvoyant VoPI captured | 38% → 83% | **74%** |
| Median detection latency | 2 steps | **0** (mean 15.9) |
| Phantom hard blocks | 9.8 / 1,000 | **5.8 / 1,000** |
| Perfect-memory floor | 9.2 / 1,000 | **5.7 / 1,000** |
| Shipped map vs that floor | "within 7%" | **1.01×** |

Two claims need more than a number swap.

**The reliability sentence is cherry-picked.** The draft quotes "98.0% stated probability and 97.9%
observed frequency", and the corrected figure for that bin is 98.1% / 98.2% — it holds. But only two
of nine belief bins meet the registered ±10% specification. The rest are overconfident toward
"blocked": −20.6pp at [0.2, 0.3), −29.7pp at [0.3, 0.45), and −47.9pp at the unobserved 0.5 prior.
Quoting the one passing bin implies the map is calibrated. Say instead that it is calibrated where
confident and overconfident elsewhere, which is consistent with the phantom-block result.

**The 74% figure is seed-sensitive.** On the paper's own seed list (1–24, 73–96) the map captures 74%
of clairvoyant value and both arms are significant. On seeds 1–48 it captures 45% and neither arm
reaches significance. Report 74% with that caveat stated — anyone re-running on a different draw
will find the 45%.

### 1.3 §3.6, tuner and rollout horizon — all three numbers stale

- Horizon matching: 3.5% → **+13.2%** over the no-tuner arm (t = 4.36).
- Hindsight capture: 39% → **48%**.
- "tied the best fixed setting … in 24 of 48 head-to-head episodes (t = +0.39)" → superseded: the
  tuner reaches **105% of the best deployable fixed constant** (+84.77 vs +80.65).

The surviving qualitative claims are that horizon is the lever and cadence is not, and that the
tuner's contribution is adaptation across regimes rather than a uniform gain.

### 1.4 Abstract — seven stale items

1. "Removing the rollout stage reduced value by 7.2%" → **−3.93% on wave, −5.53% on stream**.
2. The learner sentence → the parity split, four conditions, planner ahead in all four, significant
   in one.
3. "only disturbance-location information exceeded the preregistered 3% threshold (+3.4%)" → at 144
   seeds it is **+2.66% (t = 2.86)**, which is *below* the threshold. **No channel exceeded it**, so
   the original claim is restored.
4. "perfect order-stream foresight reduced value" → **null** at every horizon tested.
5. "Brier skill score was +0.013" → **+0.126**.
6. "from 38% to 83%" → **74%**.
7. "approximately 96,000 robot-steps" → **9.2 million** (2,304 × 500 × 8). §3.1 is already fixed;
   the abstract is not.

The abstract also never mentions the literature baselines, which are now the strongest empirical
claim in the paper. Add one sentence, e.g.:

> Against established task-assignment methods implemented on the same execution layer, the planner
> improved on-time value by 7.9–18.3% over weighted-tardiness dispatching and by 16.3–43.7% over an
> optimal myopic assignment on the same objective.

### 1.5 §5, conclusion

- "approximately 96,000 robot-steps" → **9.2 million**.
- "Removing the rollout stage reduced on-time value by 7.2%, demonstrating that forward simulation
  was the principal source of improvement" → corrected figures, and **drop "principal source."**
  The candidate funnel alone recovers +41.7 of the +50.0 points over FIFO on stream and +13.9 of
  +18.6 on wave; the rollout adds the remainder.
- "A policy-gradient dispatcher … performed 5.8% worse on held-out episodes, indicating that
  replacing the decision rule with a learned scorer was not sufficient to improve performance" →
  it **matched** the planner. The defensible claim is that a learned scorer did not beat the rule,
  not that it underperformed.
- "all six tested future-information channels were null or harmful … full demand foresight reduced
  value by 3.4%" → none cleared the 3% threshold; demand foresight was null; one *sensing* channel
  was significantly positive but sub-threshold.
- "The map achieved **only** a Brier skill score of 0.126 before correction" → 0.126 is real skill
  over the base rate, so "only" is now the wrong word.
- The final thesis clause — *"it does nothing to estimate actions but only complete them at
  estimated time since it is similar to acting on the present"* — is garbled and unsupported.
  Replace with the present/future distinction:

> In this deadline-cliff setting a planner benefits from simulating the consequences of actions over
> orders, robots and resources that already exist. Perfect knowledge of events that have not yet
> entered the system was worth nothing across five tested channels. Perfect sensing of present but
> unobserved state — the locations of obstacles already on the floor — was worth 2.66%, positive and
> statistically distinguishable from zero but below the retention threshold. The distinction is
> between imagining consequences and predicting arrivals, not between information and its absence.

---

## Priority 2 — Methods

### 2.1 §2.5 — full replacement

> Comparisons are paired by seed. Each seed fixes the demand schedule, so the policies face the same
> order times, values, deadlines, and shelf assignments. Comparisons report paired *t*-statistics on
> episode-level on-time value together with sign counts for the number of episodes won.
>
> Seed parity, rather than sequential halves, is used wherever a split is required. Seed difficulty
> is monotone in the seed index: the FIFO dispatcher averages 879.57 on seeds 1–48, 754.10 on seeds
> 49–96, and 348.32 on seeds 97–144. A sequential split therefore trains and tests on different
> difficulty distributions, while a parity split places easy and hard days on both sides.
>
> A mechanism was retained if it improved on-time value by at least 3%; otherwise it was cut. The
> threshold was registered before testing and applied to 32 mechanisms, of which 10 were retained and
> 22 removed. A typical comparison contains 144 paired episodes. The benchmark comprises 4,608 runs
> across eight arms on the full grid of two demand regimes and two disturbance conditions, with a
> further 288 runs for the learned dispatcher on its parity split and 288 for the rollout ablation.
>
> The FIFO dispatcher and every baseline drawn from the literature are evaluated with free energy,
> meaning they do not enforce the AGV battery constraint. This gives those arms an energy advantage
> over the proposed system, which pays the full charging cost, so the reported margins are
> conservative. Headline comparisons use the shipped configuration with the tuner enabled; results
> from the tuner-ablated variant are distinguished where reported.
>
> Four task-assignment methods were implemented against the same execution layer. **Token Passing**
> [Ma et al.] is the canonical MAPD rule: each free agent in turn claims the task whose pickup is
> nearest to it. **Hungarian assignment** solves the free-AGV × open-task cost matrix exactly each
> tick to minimise total travel cost, the optimal myopic assignment under a travel-cost objective.
> Two **value-form Hungarian** arms use the identical solver with the cost matrix set to projected
> on-time value, so they are optimal myopic assignments under this paper's own objective; the second
> judges feasibility by the same adaptive completion window the heuristic baselines use, so that it
> is not disadvantaged by a more conservative finish estimate, and it is the arm reported in Table 2.
> Travel costs are computed with a two-stage screen — Manhattan distance to select the twenty nearest
> open tasks, then true shortest-path distance within that set — applied identically to all four
> arms. All four subclass the FIFO controller, so routing, picker dispatch, mission sequencing, and
> dock selection are unchanged, and the only difference between an arm and FIFO is which free AGV
> receives which task.
>
> For the learned dispatcher, a shared multilayer perceptron with architecture 24 → 64 → 64 → 1
> scores the same candidate assignments using the same 24 features as the rule-based dispatcher. The
> policy is trained using REINFORCE with a running baseline, an entropy bonus, and dense
> per-decision credit. Training uses softmax sampling; evaluation uses greedy argmax selection. The
> model is trained for 40 iterations of 24 episodes each (960 episodes) on the even-numbered seeds
> and evaluated on the 72 odd-numbered seeds, in all four benchmark conditions. Routing, picker
> sequencing, battery logic, and collision handling are unchanged, so only candidate selection is
> learned.
>
> The learned arm is deliberately placed at the decision layer rather than the action layer. The
> standard multi-agent reinforcement learning setup for this simulator family has each robot emit
> primitive movements, which would not isolate the quantity of interest, since most of the learning
> capacity would be spent on navigation that both systems otherwise share. No end-to-end multi-agent
> reinforcement learning method is evaluated here; that comparison requires a different action
> interface and is left to future work.
>
> Six future-information channels were evaluated with oracle information before any estimator was
> built: full order demand, per-task delay, hotspot drift, idle-robot positioning, disturbance
> locations, and execution-layer priority. The oracle condition provides an upper bound on the
> benefit available to an estimator operating under the same decision rule. A scrambled-information
> condition, supplied with shuffled true future data, separates the value of the information itself
> from value gained through incidental movement of planner parameters.
>
> The rollout sequencer is ablated by setting its simulation depth to zero, which short-circuits the
> stage while leaving the preceding candidate filter and the commit step intact. The ablation is
> measured on the fixed-constant champion rather than the self-tuning configuration, because the
> simulation depth is one of the parameters the tuner selects and would be restored at the first
> tuning step.

### 2.2 §1.1 and §1.3 — name the new comparisons
§1.1 says the planner is "evaluated against FIFO dispatch, a policy-gradient dispatcher with matched
inputs, and oracle versions of candidate forecasting mechanisms." Add the literature baselines.
§1.3 should claim the comparison as a contribution: *"it compares against the standard MAPD and MRTA
assignment rules on identical worlds, including an optimal myopic assignment on the paper's own
objective."*

---

## Priority 3 — Results

### 3.1 §3.1, Table 2 — the body is missing

The draft has only a caption. Insert:

> **Table 2.** On-time value of the shipped planner against every baseline. Each cell gives the
> planner's relative margin and the paired *t*-statistic. Baselines are measured on all 144 paired
> seeds; the learned dispatcher is measured on the 72 odd-numbered seeds of its parity split, with
> the planner rescored on the same seeds.
>
> | Baseline | n | Wave, clean | Wave, disturbed | Stream, clean | Stream, disturbed |
> |---|---|---|---|---|---|
> | FIFO (simulator's own) | 144 | +18.9% (t = 9.9) | +31.2% (t = 11.2) | +51.6% (t = 11.6) | +66.5% (t = 12.8) |
> | Token Passing | 144 | +46.7% (t = 12.9) | +57.7% (t = 13.5) | +31.4% (t = 8.3) | +47.6% (t = 11.2) |
> | Hungarian, travel cost | 144 | +48.2% (t = 13.0) | +56.3% (t = 13.4) | +28.5% (t = 7.8) | +42.7% (t = 10.3) |
> | Hungarian, on-time value | 144 | +32.6% (t = 12.1) | +43.7% (t = 12.3) | +16.3% (t = 7.2) | +29.1% (t = 8.9) |
> | Weighted-tardiness | 144 | +15.3% (t = 9.8) | +18.3% (t = 10.0) | +7.9% (t = 4.4) | +15.1% (t = 5.8) |
> | ATC, as published | 144 | +5.6% (t = 5.0) | +10.4% (t = 6.7) | +10.8% (t = 4.5) | +19.2% (t = 6.8) |
> | ATC, robot-dependent | 144 | +7.6% (t = 5.6) | +10.7% (t = 6.8) | +5.1% (t = 2.6) | +17.7% (t = 6.7) |
> | Policy-gradient learner | 72 | +4.0% (t = 3.4) | +2.1% (t = 1.4) | +0.1% (t = 0.1) | +1.7% (t = 0.8) |
>
> Planner mean on-time value across the four conditions: 785.86, 764.12, 578.34 and 537.96 over 144
> seeds. Baselines are ordered from weakest to strongest.

Also fix the lead sentence, which promises only the FIFO comparison.

**Note on the *n* column.** If every arm is instead rescored on the 72 odd seeds for perfect
consistency, the FIFO margins become +18.1 / +30.3 / +36.9 / +43.7 — the stream cells fall by about
20 points, because the even seeds are where FIFO does worst. Both presentations are honest; do not
mix them without the *n* column.

**Do not use an averaged or minimum "margin over baselines" column.** An average rewards adding weak
baselines, and a minimum silently changes which comparator it refers to between cells.

### 3.1b The three-tier summary sentence

The margins separate cleanly by comparator class, and this is the honest way to state the headline:

> The planner improved on-time value by 18.9-66.5% over the simulator's own FIFO dispatcher, by
> 5.1-19.2% over the strongest established dispatching rule, and by 0.1-4.0% over a learned scorer
> given the same candidate set and features.

ATC detail for 2.5: the look-ahead parameter K was swept over {0.5, 1, 2, 3, 5, 8} on the even seeds
and the best value per demand regime was used (as published: K = 1.0 on wave, 5.0 on stream;
robot-dependent: K = 2.0 on wave, 8.0 on stream). The sweep surface is flat -- 1.3% spread on wave,
10% on stream -- so the comparison does not hinge on tuning. Selection on the even seeds overlaps the
144-seed evaluation, which favours the baseline.

One substantive observation: the published machine-independent rule wins on wave demand (744.2 vs
730.4) while the robot-dependent adaptation wins on the clean stream (550.3 vs 522.2). ATC assumes
processing time is independent of which machine takes the job; in a warehouse the fetch leg makes
that false, and the assumption costs most when orders arrive continuously and robot positions
therefore matter.

### 3.2 §3.1 — the baseline finding is missing entirely

This is the most novel observation in the new data and appears nowhere in the draft.

> On wave demand all three published methods scored below the simulator's own FIFO dispatcher —
> Token Passing by 18.9%, travel-cost Hungarian by 19.7%, and the value-form Hungarian by 10.3%, at
> paired *t* between −3.26 and −8.29. Wave orders are visible at t = 0 and arrive in deadline order,
> so FIFO incidentally approximates earliest-deadline-first, while Token Passing and travel-cost
> Hungarian optimise distance and never read a deadline. Methods developed for service time and
> makespan therefore do not transfer directly to a deadline objective.
>
> On stream demand the published methods did beat FIFO, by 15.3% to 30.4%, and the strongest was the
> value-form Hungarian. Because that arm is an optimal myopic assignment under this paper's own
> objective, no myopic rule can exceed it on that criterion; the planner's remaining margin of 16.3%
> on the clean floor and 29.1% under disturbances is therefore attributable to forward simulation
> rather than to scoring the correct quantity.

### 3.3 §3.1 — latency
"1.3 ms" holds (measured 1.27 ms) but needs its tail and its warm-up:

> Median decision latency at the proposal's stated fleet of five robots — three AGVs and two pickers
> — was 1.27 ms, with a 95th percentile of 8.3 ms, a 99th percentile of 167 ms and a maximum of
> 604 ms, against a one-second budget. The first decision in a freshly started process takes a
> median of 889 ms and exceeds one second on 16 of 48 seeds; this is import and cache warm-up rather
> than deliberation.

### 3.4 §3.1 — the collision claim
The `collisions` column previously read a nonexistent attribute, so every published zero was vacuous;
it is now measured and is still zero. Two repairs: the robot-step count (item 1.4.7), and the fact
that the execution referee intervened 24 times across the benchmark, so "no collisions" is a property
of the execution layer including that referee.

### 3.5 §3.2 — the ablation
Numbers are already corrected in the draft. Still needed:

- the statistics: **t = −4.22** on wave, **−4.07** on stream;
- the win counts: the rollout wins on 94 of 144 and 81 of 144 seeds, so it is a mean effect rather
  than a universal one;
- **drop "produced the largest measured single effect"**;
- the decomposition, which is the substantive finding:

> The candidate funnel without the rollout stage already recovers most of the margin over FIFO:
> +41.7 of the +50.0 percentage points on the stream regime and +13.9 of +18.6 on wave. Forward
> simulation contributes the remainder. The rollout is therefore a real but secondary contributor to
> the margin over FIFO; its distinct contribution is visible against the optimal myopic assignment,
> which the planner exceeds by 16.3% and 29.1% and which no better myopic scoring could close.

### 3.6 §3.3, Table 3 — three rows and two paragraphs

**Full order stream row.** The current text calls positive gains "decreased."

> No measured benefit at any horizon. Gains were positive but within noise: +2.35% at 10 steps
> (t = 2.24), +2.09% at 25 (t = 1.71), +2.02% at 50 (t = 1.48), +0.42% at 100 (t = 0.33), and
> +1.44% for the full episode (t = 1.18). Only the shortest window reaches significance and none
> clears the 3% threshold. At 144 seeds in the combined oracle the channel measured −1.67%
> (t = −1.12).

**Disturbance locations row.** Currently reads +3.4%, t = 2.23, "past the 3% retention bar," and
carries editorial commentary rather than table prose.

> +2.66% (t = 2.86, 144 paired episodes). Significantly positive but below the 3% retention
> threshold. This channel reveals present but unobserved obstacle locations, so it measures sensing
> rather than forecasting; the margin bounds the headroom remaining in the fleet's belief map.

**Idle-robot positioning row.** 2.4% → **2.46%**.

**Hotspot drift row.** −0.14% is correct; add t = −0.14, and −0.21% (t = −0.18) at full foresight.

**Charging foresight paragraph.** 4.0% → **4.1% (t = 1.26)**, and "a shuffled forecast performed
similarly to the true forecast" → the scramble scored **+10.7% (t = 3.67)**, beating the true
forecast and being the only arm to reach significance. This is a stronger version of the same point.

**Delete the "Perfect demand foresight was harmful" paragraph.** Both of its clauses are contradicted
by the corrected table above it. Apply the same deletion to §4.2's second paragraph.

---

## Priority 4 — Discussion

### 4.1 §4.1 — the learner claim and the ablation framing
"improved on-time value over FIFO and over a policy-gradient dispatcher with matched candidate
inputs" → the planner leads the learner in all four conditions but significantly in only one. Soften
accordingly, and let the optimal-myopic comparison carry the argument for forward simulation rather
than the ablation size.

### 4.2 §4.2 — second paragraph
The "harmful demand foresight" mechanism is unsupported now that the channel is null. Replace with
the step-valued-objective argument: a sharper finish estimate can only re-rank candidates whose own
estimate error straddles their deadline, which bounds what any delay predictor can win.

### 4.3 §4.5 — scope
Opening sentence → **46 configurations spanning 4–19 AGVs, 2–9 pickers and four map geometries**, not
"one map family, one fleet size." Sandbox figure → **+0.83%** across 86 paired blocks and 6,192
episodes, 80 of 86 blocks positive, pooled z = **+13.1**, range −0.37% to +3.36%. Keep the honest
reading: the magnitude is below the 3% threshold, so the result is that adaptive tuning transfers
across operating points without loss, not that it is a large effect. Run count 2,304 → **4,608**.

Add the scoping sentence on MARL:

> The learned comparator is a shared-parameter policy-gradient scorer at the decision layer, not an
> end-to-end multi-agent reinforcement learning method. Published MARL approaches to warehouse task
> allocation were not evaluated, because the objective change in this fork makes their reported
> results non-comparable and retraining them is outside the scope of this study.

### 4.4 §4.4 — move the late-order-value paragraph to §5
Delete it from §4.4, where it sits in a reproducibility section, and add to §5's future work:

> A related change concerns the objective itself. Real fulfilment operations do not treat a late
> order as worthless; an order already past its promise date is often prioritised precisely to limit
> further damage to customer satisfaction. The objective used here is a hard cliff, so a late
> delivery banks nothing, and the planner is correspondingly built to shed orders it judges
> infeasible. Replacing the cliff with a decayed late value would therefore change the problem rather
> than the planner, and it would change it in a way that bears directly on this paper's central
> negative result: the delay-prediction null follows from the cliff, because a step-valued objective
> means a sharper finish estimate can only re-rank candidates whose estimate error straddles their
> deadline. Under a decayed objective the projected value becomes a slope rather than a step, every
> candidate's estimate becomes decision-relevant, and better delay prediction would be expected to
> pay. One of the baselines reported here already probes this direction — the weighted-tardiness arm
> scores doomed tasks by value decayed per step overdue — and a full test would re-run the oracle
> information channels against the decayed objective to establish whether the negative results in
> Section 3.3 are properties of the problem or of the deadline cliff.

This item overlaps the existing future-work sentence about a continuous scoring rule. They are
related but distinct — one changes how the estimate enters the score, the other changes what a late
order is worth. Either distinguish them in a clause or merge them into one item about the objective's
shape.

---

## Priority 5 — references and housekeeping

### 5.1 Reference 34 is a note, not a reference
It currently reads: *"Ma, Li, Kumar, Koenig, 'Lifelong Multi-Agent Path Finding for Online Pickup and
Delivery Tasks,' AAMAS 2017 — the Token Passing source. And Kuhn (1955) or Munkres (1957) for the
assignment algorithm."* Split into two numbered entries, renumber, and replace the inline
"[Ma et al. 2017]" in §2.5 with the number.

### 5.2 Verify before citing
The claim that primitive-action MARL underperforms greedy heuristics at this scale originates in a
source-code comment in this project, not in a verified reading of [11] or [12]. Check the sources
before citing them for it, or drop that half of the sentence — the "would not isolate the decision
layer" argument stands on its own.

---

## Still unmeasured

Nothing in the draft now rests on an unmeasured number, with one exception worth noting: the
sensing-ceiling figure in §3.5 is reported on one 48-seed draw and moves to 45% on another. Either
state the caveat, or run it across several draws and report the spread.
