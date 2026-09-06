# The Knobs, Explained — what each weight does, what we found, and why

**Running doc.** One section per tuned weight: what it actually is in code, what the sweep found,
the mechanism behind the result, and an analogy. Add a new section per knob as it lands.

Every result below is from the same protocol: **AGV×picker 4–9 ratio grid (72 cells) × day-list and
stream × 120 paired seeds**, on the champion `_SqWidePkRateAdaptive` (sequencer + value-rate pickers).
"Stability" = how often the same winner survives 200 random half-splits of the seeds. A setting only
ships if the pooled effect **and** the stability both hold.

---

## The one-line summary

| knob | what it controls | day-list | stream | verdict |
|---|---|---|---|---|
| `URG_W` | deadline panic | **0** | **8** | regime rule — *the only champion change* |
| `W_SYNC` | sync-up penalty | 0.3 | 0.3 | **null** — knob does nothing |
| `RATE_ALPHA` | picker travel-greed | 5 | 5 | incumbent confirmed |
| `SEQ_DEPTH` | lookahead horizon | **5** | *any ≥3* | depth matters on day-list, inert on stream — **but the mechanism is worth ~10% on stream** |

---

## `URG_W` — deadline panic  ·  **0 day-list / 8 stream**

**What it is.** For a task that can still make its deadline, the AGV scores it
`1000 + value + URG_W · max(0, 1 − spare/40)`. So `URG_W` decides how much a robot favours *"this one
is about to be late"* over *"this one is worth the most."* Zero = rank purely by value.

**What we found** (paired vs `URG_W=0`, 36 cells/regime, 43,200 runs):

| URG_W | 4 | 8 | 12 | 16 |
|---|---:|---:|---:|---:|
| day-list | −2.84 | −4.38 | −6.53 | −6.90 |
| stream | +0.24 | **+1.87** (t=2.78) | +0.26 | −0.16 |

Day-list declines monotonically — the best setting is the term **switched off**. Stream has a clean
interior peak at 8, resolvably better than both neighbours. Stability **100% / 94%**.

![URG_W best value per fleet ratio](../results/urg_best_URG_W.png)

*Day-list (left) is almost uniformly 0 — that's the regime rule showing through. Stream (right) is
mid-range but patchy; the cell-to-cell variation there is **noise**, not ratio structure (see
[Method notes](#method-notes-worth-keeping)). The table above is the result; the map is illustration.*

**Why.** The planner always assumes *"nothing else is coming."* On day-list that is **exactly true**
(all orders released at t=0; the demand model's `step()` is a no-op afterwards). On stream it is
**exactly false**. So urgency isn't really about deadlines — it's a **correction for a planner that is
too optimistic about how free the future is.** Where the planner can genuinely see the future,
correcting it makes things worse.

> **Analogy — the syllabus vs the inbox.**
> *Day-list* is a professor handing you every assignment for the whole term on day one. You plan it
> out and can see everything fits. Now panic about whatever's due soonest: you'd drop a big project to
> finish a worksheet you'd *already worked out* would fit fine later. The panic saves nothing and
> reorders your term badly. → urgency off.
> *Stream* is assignments arriving by email all term. Your plan says "I'll do this next week, I have
> time" — but next week's inbox isn't empty, it just hasn't arrived. That free time will be eaten. So
> do whatever's closest to due **now**, because "later" is never as free as your plan believes.
> → urgency on.

---

## `W_SYNC` — sync-up penalty  ·  **null, default 0.3 kept**

**What it is.** An AGV that reaches a shelf before any picker sits idle:
`my_wait = max(0, picker_ETA − my_arrival)`. `W_SYNC` penalises tasks where the robot would wait:
`score −= W_SYNC · my_wait`.

**What we found** (paired vs 0.3, 34,560 runs): `0 → −0.38`, `0.15 → −0.03`, `0.5 → −0.30`. Every
\|t\| < 2. Per-cell winners split 23/10/21/18 across the four values — a coin flip. Stability only
**62% / 58%**, so no value wins even pooled. This also killed the hypothesis that `W_SYNC=0` should
win when pickers are abundant: in the picker-rich bucket it's −0.31 over 3,600 paired runs.

![W_SYNC best value per fleet ratio](../results/urg_best_W_SYNC.png)

*This is what a **null knob looks like**: all four values scattered with no structure in either panel.
Compare it to the URG_W map above — that contrast is the clearest visual in the set.*

**Why.** **It's double-counting, and the second count is ~1000× too small to matter.** The rollout
computes `rendezvous = max(my_arrival, picker_ETA)`, so **every step of sync wait is already inside
`finish`** — and `finish` is what decides the 1000-point makeable/doomed tier. The waiting cost is
already charged at full strength. The explicit penalty is a second invoice worth **1–4 points**
(zero in 50–64% of decisions), which can never move a task across the tier boundary. It only reorders
tasks already within ~2 points of each other — decisions that don't matter.

> **Analogy — the double-charged late fee.**
> A courier's quote already includes the time they'd spend waiting at your door, and you decide
> whether to book them purely on whether they arrive before your hard deadline — a pass/fail worth
> £1000. Then you add a separate £2 "waiting fee" to the comparison. You've billed the same waiting
> twice, and the second bill is too small to change any booking that the pass/fail didn't already
> decide.

*Simplification candidate: the term could be deleted outright with no measurable loss (−0.38,
t=−1.63). Not a performance win — a clarity win.*

---

## `RATE_ALPHA` — picker travel-greed  ·  **5, both regimes**

**What it is.** A free picker chooses which AGV rendezvous to serve by
`score = tier + value / Tp^RATE_ALPHA`, where `Tp` is time-to-rendezvous. It's the exponent on time in
a value-per-time rate — i.e. **how hard distance is punished.** α=0 chases the most valuable task
anywhere; α=5 means a task twice as far is 32× less attractive, so pickers barely leave their patch.
High α produces **emergent Voronoi zoning** — territories nobody assigned.

**What we found** (paired vs 5, 43,200 runs):

| α | 3 | 4 | 6 | 7 |
|---|---:|---:|---:|---:|
| day-list | −0.24 | −0.30 | −0.15 | −0.20 |
| stream | −1.27 (t=−2.57) | −0.19 | −0.63 | −0.67 |

**Every alternative is negative in both regimes.** α=5 sits atop a properly bracketed interior peak.

![RATE_ALPHA best value per fleet ratio](../results/urg_best_RATE_ALPHA.png)

*Also patchwork per-cell (split-half z = −0.35 / +0.66) — but unlike W_SYNC the **pooled** curve is a
real peak. A noisy map over a genuine optimum: exactly why the map is not the result.*

**Why the same in both regimes.** α is an exchange rate between distance and value, so the best
exponent is set by the **relative spread of log-value vs log-time** among a picker's candidates.
Measured: that ratio is **1.84 (day-list) vs 1.71 (stream)** — within 7%. And of course it is: the
warehouse doesn't change. Same grid, same hot centres, and the two regimes generate *bit-identical
order sets*. Pickers walk the same distances (21.4 vs 23.5 steps mean) either way.

> **Analogy — the delivery rider's rule of thumb.**
> α is *"how far will I ride for a bigger tip?"* Too low and you cross the city for one fat order while
> your neighbourhood goes unserved. Too high and you never leave your block, so a lucrative order two
> streets over sits there. The right setting depends on the **city layout** and how spread out tips
> are — and the map doesn't change based on whether the orders all land at 9am or trickle in all day.
> That's why this one number works for both regimes.

*Worth noting: α=5 originally came from a small deployment-fleet sweep. It's now validated across 72
fleet configurations — a stronger claim than a null.*

---

## `SEQ_DEPTH` — lookahead horizon  ·  **5 on day-list · any ≥3 on stream · but never 0**

**What it is.** The sequencer re-ranks candidate first moves by *simulating the fleet forward* and
taking total banked on-time value. `SEQ_DEPTH` is that simulation's horizon in task-units of 75 steps:
`horizon = min(now + SEQ_DEPTH·75, 500)`. `SEQ_DEPTH=0` disables the sequencer entirely.

**What we found — day-list** (paired vs 5, 36 cells, 100% stability):

| depth | 1 | 2 | 3 | 5 |
|---|---:|---:|---:|---:|
| day-list | −9.80 (t=−22.5) | −5.63 | −2.44 | **0 — best** |

**What we found — stream:** depths 3, 5 and 8 are **bit-identical** — 0 of 120 seeds differ, in every
cell. But turning the sequencer **off** costs **−24.05 (−7.2%, t=−30.6)** across all 36 cells — the
largest mechanism effect measured anywhere in M1.

![SEQ_DEPTH best value per fleet ratio](../results/urg_best_SEQ_DEPTH.png)

*The one map worth reading directly. Day-list (left) is uniformly 5 — a **real** regime-wide winner,
100% split-half stability, unlike every other knob's patchwork. Stream (right) shows the ablation:
depth 3 everywhere, because the alternative is the sequencer switched off.*

**Why.** **The sequencer's value comes from simulating the visible queue to exhaustion; depth matters
only insofar as it's enough to *reach* exhaustion.** Day-list has a long queue (~60 orders visible at
t=0) so the horizon genuinely binds and deeper is better up to 5. Stream has a short queue and
`_future_arrivals` returns `[]`, so the imagination runs out of tasks well before even depth 3's
225-step horizon — extending it changes nothing. Switching it off is catastrophic in both.

> **Analogy — planning your errands.**
> Depth is *how many errands ahead you think before deciding which to do first.*
> With **20 errands** on your list (day-list), planning 5 ahead genuinely beats planning 1 ahead — the
> order matters and you can see far enough to get it right.
> With **3 errands** visible (stream), planning "5 ahead" and "8 ahead" are the *same plan* — you ran
> out of errands to plan at three. The extra foresight has nothing to look at.
> But in both cases, **not planning at all** — grabbing whichever errand is nearest — is far worse
> than any amount of planning. The horizon can be over-provisioned; the planning itself never is.

⚠️ **Correction on record.** When only the depth result was in, I described the sequencer's lookahead
as "doing nothing in the streaming regime" and floated cutting it there. The depth-0 ablation refuted
that outright: it's carrying *more* value on stream than anywhere else. Inert **depth** is not an inert
**mechanism** — a knob result never licenses cutting the code the knob lives in.

*Saturation note: because the horizon is capped at the 500-step episode end, depths 5 and 8 are
identical from t=125 onward. Max useful depth ≈ 500/75 ≈ 6.7, so the knob is bracketed by construction
at the top — extending above 8 is meaningless. The real curve lives at the short end.*

---

## `FORESIGHT_W` — how far ahead we're told about new orders  ·  **no useful horizon exists**

**What it is.** Not a shipped knob — a measuring instrument. The rollout normally sees zero future
orders (`_future_arrivals` returns `[]`). This arm feeds it the *genuine* upcoming orders out to W
steps, using the exogenous demand schedule. W=0 is the plain champion.

**What we found** (720 paired runs per arm, baseline 326.9):

| W | 10 | 25 | 50 | 100 | 999 |
|---|---:|---:|---:|---:|---:|
| Δ | **−0.10** | −1.65 | −3.91 | −5.32 | **−11.23** |
| t | −0.07 | −0.93 | −2.17 | −2.61 | −5.98 |

Monotonic. A **perfect** 10-step forecast is worth exactly nothing, and the damage grows with reach.

**Why.** Knowing valuable work is coming makes the rollout favour branches that keep robots free or
well-placed for it — **sacrificing certain present value**. But only the first move commits, and by the
time that work lands, reactive re-planning would have taken it anyway. The sacrifice buys nothing and
costs real value now. The damage is largest in tight fleets (4×4 −6.0%) and smallest in slack ones
(9×9 −1.0%), which is exactly what you'd expect if the cost is *holding capacity back*.

> **Analogy — the over-eager waiter.**
> A table is waving at you *now*. You know a party of eight arrives in ten minutes, so you hang back
> near the door to be ready for them. The party would have been seated fine anyway — someone is always
> free by then — but the waving table waited. The busier the restaurant, the worse that trade gets.

*This is the third independent leg closing demand forecasting: every estimator was null, perfect
information is negative, and no horizon pays. Still untested: drifting hotspots, and the positioning
channel (where a spare robot waits, rather than which task to take).*

---

## Joint assignment (Part D) — **no headroom, binding or not**

**What it is.** When I free up, pair with the AGV freeing within W steps and branch over my top-3 ×
its top-3, instead of deciding alone. No idling — only my move commits.

**What we found** (720 paired runs per cell):

| | day-list | stream |
|---|---:|---:|
| W=10 | −0.59 (t=−1.16) | −1.62 (t=−1.55) |
| W=20 | −4.71 (t=−7.18) | −5.48 (t=−4.20) |
| W=30 | −6.91 (t=−10.79) | −5.81 (t=−4.43) |

Zero at W=10, monotonically harmful beyond. The **binding** variant (partner's pick actually reserved)
is worse still.

**Why.** The rollout **already co-decides the partner** inside every branch — it knows when each robot
frees and plays its pick forward. So joint optimisation isn't adding coordination, it's *hardening* an
assumption: A's move gets optimised for a pairing that evaporates when B re-decides on freeing. Wider
window → staler assumption → worse. Binding removes the mismatch but buys two costs instead: a decision
made 10–30 steps before it executes, and a task locked away from every robot that frees sooner.

> **Analogy — agreeing who cooks tomorrow.**
> Deciding tonight that your flatmate will cook tomorrow doesn't help if they get home late and reheat
> something anyway — you shopped for a meal that never happens. Making it *binding* is worse: now the
> ingredients are reserved and nobody else can touch them, even if someone gets home early and hungry.

*Also worth recording: the mechanism only has ~10 eligible decisions per 500-step episode
(`_pick_winner` fires 17×, 7 of them at t=0 with nothing busy to pair), and partner free-gaps run
6–33 steps — so the originally-specified W=5 cannot fire at all.*

---

## The cross-cutting principle

> **Knobs about SPACE are regime-invariant. Knobs about the FUTURE are regime-dependent.**

`RATE_ALPHA` is about the floor plan, and the floor plan doesn't change → one value for both regimes.
`URG_W` and `SEQ_DEPTH` encode assumptions about what's coming → they flip hard between a regime where
the future is fully known and one where it isn't.

> **Analogy — the map and the weather forecast.**
> How far you'll walk for a better shop is a fact about the *map*, and the map is the map. Whether you
> should grab something now or come back later is a fact about the *forecast* — and one regime hands
> you tomorrow's forecast while the other doesn't.

This predicted `CONG_LAMBDA` and `CONG_WEIGHT` (congestion, routing = **space**) would be
regime-invariant and null, which is why they were **skipped** rather than swept.

---

## Method notes worth keeping

- **Pooled tests are confirmatory; per-cell heatmaps are exploratory.** Every knob's per-cell "best
  value" map fails split-half reproducibility (agreement ≈ chance, z ≈ 0). One cell is 120 runs —
  asking one person. A regime pools 4,320 — running a poll.
- **The argmax lottery, worked example.** `RATE_ALPHA=3` on the stream opened at **+5.7 (t=3.41)** in a
  single early cell and looked mechanism-shaped. As cells accumulated: **+0.60 → +0.34 → −0.66 →
  −1.27 (t=−2.57)**. It ended up significantly *worse* than the incumbent.
- **A knob change is free; a mechanism costs complexity forever.** The ≥3%-or-cut bar is for code, not
  for numbers. `URG_W`'s day-list fix is ~1% and worth taking because it costs nothing.
- **Small-n reads overstate, badly and repeatedly.** Part D smoke (24 runs) read −7.3 / −13.0 where the
  720-run answer was −0.6 / −5.5 — off by 5–10×. `RATE_ALPHA=3` opened at +5.7 on one cell and finished
  at −1.27. Nothing below 120 seeds is evidence.
- **A silent null is more dangerous than a crash.** Two Part D bugs produced *champion-identical* output
  rather than errors: the partner filter excluded `assigned_agvs` (which holds every robot currently
  executing a mission — precisely the ones about to free), so the mechanism never fired once in a
  500-step episode. Always verify a new arm actually *changes decisions* before believing its null.
- **Measure the ceiling, not one implementation.** The first true-VoPI run was invalid because demand
  was policy-dependent (~22% overlap between the "known" future and the real one) — it measured stale
  information, not perfect information. Fixed with `DemandModel(exogenous=True)`. A negative from one
  arm bounds that arm; only a ceiling closes a question.
