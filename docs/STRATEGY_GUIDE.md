# Strategy & Terminology Guidebook

A plain-language reference to every strategy, term, and knob we've tried. Skim the **verdict tags**
to see what actually stuck.

**Legend:** ✅ DEPLOYED (in the shipping stack) · 🟢 real win · 🟡 tiny/unconfirmed · ⚪ null (no effect)
· 🔴 hurts · 📏 measurement/ceiling only (not a policy) · 🗄️ retired.

---

## 1. The world & the goal

| term | what it means |
|:--|:--|
| **on-time value** | The score we maximize: sum of the **value** of every order delivered **before its deadline**. Late = you lose it (see makeable/doomed). Not throughput, not count — *value, on time*. |
| **deadline / value** | Each order has a due-step and a dollar value. Both vary across orders. |
| **makeable / doomed** | A task is **makeable** if it can still finish before its deadline (given an honest time estimate) — these get a huge score bump (tier `1000+v`) so any makeable beats any doomed. **Doomed** = can't make it; scored low (`v·decay^lateness`) so we don't waste robots chasing lost causes. |
| **DECAY_G** | How fast a doomed task's value decays with lateness (0.98). |
| **regime** | *How orders arrive.* This matters enormously (see §7). |
| ‣ **day-list** | All of the day's orders are known at t=0 — a big standing backlog to organize. Our main testing regime. |
| ‣ **stream** | Orders trickle in over the day (realistic). |
| ‣ **uniform** 🗄️ | Old toy demand, always-full queue. Retired — gave misleading results. |
| **potential value** | The max possible if you delivered *everything* on time (~430/day day-list). We bank ~94%. |

---

## 2. AGV strategies — "the CHOOSER" (which task, which robot, when)

The AGV decides *which order is worth chasing*. This is where value/urgency logic belongs.

| strategy | what it does | verdict |
|:--|:--|:--:|
| **FIFO** | Do orders in arrival order. Baseline. | ⚪ baseline |
| **EDF** (earliest-deadline-first) | Chase the most-urgent first. Naively chases doomed tasks. | 🗄️ |
| **Feasible / Moore-Hodgson** | Shed what you can't finish (doomed), do the rest EDF. The makeable/doomed idea. | building block |
| **Rush / Part A** | Score each task by **value × P(on-time)** — the value-weighted core. | building block |
| **champion** (`cong_l2on`) | Part A + congestion map + urgency. The long-standing baseline everything is measured against (~391/day day-list). | ✅ base |
| **urgency** (`urg8`) | Inside the makeable tier, nudge toward tasks near their deadline: `+8·max(0,1−spare/40)`. Small tie-breaker, doesn't chase doomed. | 🟢 day-list; ⚪ stream |
| **proximity** (`prox`) | Bonus for close tasks. Drowned value when strong; capped version neutral. | ⚪ |
| **AGV value-rate** (`rate80`, `blend`) | Rank AGVs by value **per unit time** (like the picker fix, but for AGVs). | 🔴 realistic regimes / 🟢 only in retired uniform — **regime-bound, not adopted** |
| **soft-deadline** | Replace the hard makeable/doomed cliff with a smooth P(on-time); sigma widens with congestion. | ⚪ |
| **sequencer** (`sqwide`) | *The big one — see §4.* | ✅ 🟢 |

---

## 3. The congestion map — "how a robot DRIVES" (routes, not tasks)

A grid of "how crowded is each cell," used to steer robots around jams. **It changes routes, not task
choices.** Its value is *preventing* real physical blocking, not *estimating* delay (the delay EMA
already estimates).

| term | what it means | verdict |
|:--|:--|:--:|
| **the map / forecast** | Stamp every busy robot's remaining path onto a grid; robots route to avoid high-cost cells. | ✅ |
| **layer 1** (known paths) | A robot is on that road now and won't move for you → avoid it. The load-bearing layer. | ✅ |
| **layer 3** (same-round) | Robots planning in the same instant have no natural order; we impose one (each stamps so the next avoids it). | ✅ |
| **layer 2** (predicted next task) | Guess where a finishing robot goes next and avoid that too. **Redundant** — time already orders these. | ⚪ |
| **avoid-don't-predict** | Principle: only put things in the map that are TRUE NOW and nobody else will handle. Avoidance points *backwards* in time, never forwards. | principle |
| **Yen k-routes** | Generate the k shortest routes, pick the least-congested. On a grid most are equal-length, so this only breaks ties. | mechanism |
| **reroute / adherence** | `find_path` reads the map so detours also dodge traffic; a robot sticks to its committed route. | ✅ |
| **NoMap ablation** | Turn the map off to measure its worth: near-zero mean, but prevents a ~1-in-30 **crater** day. It's *insurance*. | 📏 |
| **pickers-in-map** (`cong_pktraffic`, `cong_picker`) | Put pickers on the map so AGVs physically steer around them. | 🟡 +2/day champion (real); ⚪ washes on the sequencer — **parked** |

---

## 4. The sequencer — the deployed AGV brain

| term | what it means | verdict |
|:--|:--|:--:|
| **sequencer** (`_SqWide`) | Instead of a one-shot score, **simulate the whole fleet forward** for each candidate first-move, keep the move that leads to the best imagined rest-of-day, commit only that first move, then re-plan next step. | ✅ 🟢 **+16 day-list, +14–16 stream** |
| **rollout** (Bertsekas) | *The concept the sequencer is an instance of — not a separate strategy.* Take a cheap base policy, simulate it forward from each candidate first move, keep the move with the best simulated future, commit only it, re-decide. The sequencer = this loop with our Part-A/congestion heuristic as the base policy. Cousin of MCTS/AlphaZero without the learned net. | concept (= sequencer) |
| **receding horizon** | Only plan out `SEQ_DEPTH` (5) task-spans ahead, then slide the window forward. | knob |
| **re-planning** | Re-decide every step as reality updates, rather than committing a whole schedule. Beats committing because information only grows with time. | principle |
| **honest clock** (`delay EMA`) | The sim's forward model uses a live running-average of realized delay so its predictions aren't naively optimistic. The single biggest accuracy fix (+6.9). | ✅ |
| **open-loop** (`_OpenLoop`) | Commit the *whole* branch and follow it without re-scoring. Measures the value of re-planning (closed-loop minus this). | 📏 |
| **pace models** | Replace the flat delay EMA with a learned, state-conditional delay predictor (picker/diurnal/traffic features). | ⚪/🔴 mostly — only "combined" ~+1, not adopted |

---

## 5. Picker strategies — "the SERVER" (go load whoever's waiting)

Pickers don't choose *which order matters* — they run to a parked AGV and load it. Their job is
**speed**, not judgment. Key finding: **servers should rank by speed, not value** (see §6).

| strategy | what it does | verdict |
|:--|:--|:--:|
| **nearest** | Send the closest free picker to the most-urgent waiting AGV. Baseline. | ⚪ baseline |
| **value-rate pickers** (`_VRPicker`, `RATE_ALPHA`) | Rank a waiting AGV by `tier + value / Tp^α` (Tp = time-to-rendezvous+load, α=5). Distance dominates → pickers self-organize into tight zones (emergent Voronoi) and waits shrink. | ✅ 🟢 **+7–8 day-list**; ⚪ **+1.5 stream (doesn't transfer)** |
| **RATE_ALPHA (α)** | The distance exponent — *the* real knob. Swept: climbs 3→4→5, plateaus ~5–8. (The W_RATE multiplier is inert/scale-free.) | knob |
| **sync** (`W_SYNC`) | Penalize a rendezvous where the AGV would wait for the picker (or vice-versa). Value-rate's Tp already absorbs it, so the explicit term is ~redundant. | ⚪ |
| **STALL_BONUS** | Extra points to unblock an AGV parked *right now*, so a stalled robot isn't starved. | ✅ small |
| **commit paths** (`_PkCommit`) | Make pickers adhere to a committed route ("make sure"). | ⚪ (+0.06) |
| **spread / coverage** (`_PkCovMixin`, `COV_W`) | Dock a picker for heading where another picker already is, to spread them out / catch strays. | ⚪/🔴 **dead** — demand clusters, so crowding = where the work is, not redundancy |
| **picker urgency** (`_PkUrgMixin`) | Give pickers the deadline-urgency term AGVs have (the one thing the picker score lacked). | 🟡 +2–3 day-list 8×4 but **unconfirmed** (drifts in/out of significance at 120); ⚪ 8×8 & stream |
| **free pickers** (`pickers_free`) | Oracle: a picker is always instantly present (zero wait). Not real — measures the ceiling. | 📏 ceiling |

---

## 6. Big principles (the stuff worth remembering)

1. **Choosers rank by value/urgency; servers rank by speed.** The AGV picks *which* valuable order to
   chase; the picker just needs to reach the parked AGV fast. That's why **value-rate (distance) is
   right for pickers** and adding value/urgency/spread to them mostly doesn't help — it's asking the
   server to redo the chooser's job.
2. **Avoidance points backwards.** Only coordinate around what's true *now*; information only grows
   with time, so the better-informed later decision yields to the worse-informed earlier one — never
   the reverse. (Killed the layer-2 "predict next task" idea.)
3. **Estimate vs. prevent.** The delay EMA *estimates* lateness (for the makeable/doomed call); the
   congestion map *prevents* it (by physically rerouting). Different jobs — not redundant.
4. **Validate in the deployment regime.** Wins on day-list don't automatically transfer to the stream
   (value-rate pickers: +7 → +1.5). Always re-check where it ships.
5. **Some gaps are structural.** Most of our remaining ~5% loss is **headcount/physics** (more pickers,
   more AGVs), not decisions — the decision layer is ~1.5% from its hindsight ceiling.
6. **Two instruments.** Report both a **t-test** (mean effect) and a **sign test** (how many seeds
   improved). They disagree exactly when an effect is a consistent-small-positive with a few craters —
   which is most of our real effects.
7. **The 120-seed rule.** Any effect under ~+8/day needs 120 seeds; small effects drift in and out of
   significance below that (we got burned several times calling +2 effects "significant" or "null" too
   early).

---

## 7. Current scorecard (day-list vs stream, both worlds)

| fix | day-list 8×4 | stream 8×4 | stream 8×8 | status |
|:--|:--:|:--:|:--:|:--:|
| **sequencer** (vs champion) | +16 | **+14** | **+15** | ✅ the portable win |
| **value-rate pickers** (vs stupid) | **+7–8** | +1.5 (n.s.) | +1.8 (n.s.) | ✅ deployed, but day-list-only benefit |
| **picker urgency** | +2 (n.s.) | +3.5 (n.s.) | +1.8 (n.s.) | 🟡 small, unconfirmed |
| **picker spread** | −1 (n.s.) | — | — | 🔴 dead |
| **pickers-in-map** | +2 champ / ⚪ seq | — | — | 🟡 parked |

### 🏆 THE CHAMPION (as of 2026-07-25)
**`champion` = `sqwidepr` = sequencer + value-rate pickers (α=5)**, on the congestion+urgency base.
This is the new reference baseline — **new ideas must beat THIS, not the old `cong_l2on`.**
- day-list 8×4: **408.8/day** (old champion `cong_l2on` = 391.4 → **+17**)
- stream 8×4: **332.4/day** (old `cong_l2on` = 316.6 → **+16**)
- The sequencer does ~all the lifting (+16); value-rate pickers add ~+1.4 on top (crater insurance).
- `cong_l2on` (plain congestion controller) is retained for provenance only. In the runner, set
  `BASE=champion` (now the default) so deltas are measured against the real bar.

### Open question: why value-rate pickers don't transfer to the stream
Honest status: **unresolved.** First guess ("the stream never gives the picker a choice") was **tested
and refuted** — queue depth is nearly identical across regimes (the picker faces a choice ~50% of the
time in both). So it's not lack of *opportunity*; the likely reason is the loss *structure* differs on
the stream (more never-served / doomed-on-arrival, less picker-wait sitting right at a deadline cliff),
so a better picker choice rarely converts to on-time value. Not yet confirmed — flagged, not faked.

---

## 8. Diagnostics & ceilings (tools, not policies)

| term | what it measures |
|:--|:--|
| **oracle** (hindsight shuffle) | Best achievable with perfect decisions & current robots. We're ~1.5–2% under it → decisions are near-maxed. |
| **free-picker ceiling** | Value if pickers were never a constraint (+11–22). The gap is mostly headcount. |
| **VoPI** | Value of perfect information — how much a perfect predictor could ever buy. ⚠️ **The usual "day-list minus stream" estimate is CONTAMINATED** (2026-07-30): the two regimes generate bit-identical orders, but stream additionally gets a `seed_initial(n=12)` warm start (+25% orders, +33% value) that day-list never receives, so the gap mixes information with LOAD. Re-measure with the warm start matched before quoting. |
| **AGV:picker ratio** | Sweep robot counts to find the binding constraint. Doubling pickers ≈ +9–10; the binding limit is picker headcount. |
| **value-loss autopsy** | Split the gap: banked ~94% · picker-wait cliff (dominant) · traffic (~7) · never-served (~8–10) · doomed = 0. |
