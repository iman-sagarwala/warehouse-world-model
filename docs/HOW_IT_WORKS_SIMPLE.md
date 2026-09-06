# How the Robot Warehouse Brain Works — explained from zero

*Every component of the system, in plain words. No prior knowledge needed. Each part says
what it is, what it does, and where it lives in the code.*

---

## 1. The world (the game being played)

The warehouse is a grid of squares, like a chessboard, 35×22.

- **Shelves** — squares holding products. There are 240 of them.
- **AGVs** ("carrier robots") — 8 robots that drive around, pick up a whole shelf, and carry
  it to a delivery station. They can drive *under* other shelves, so the floor is open to them.
- **Pickers** ("helper robots") — 4 robots that walk the aisles. A carrier can't load a shelf
  alone: a helper must be standing at the same square at the same moment. Then the shelf pops
  onto the carrier instantly.
- **Docks** (delivery stations) — gold squares at the bottom edge. Bringing a shelf here
  delivers the orders on it. Afterwards the carrier must lug the shelf back to an empty spot
  before it's free again.
- **Orders** — "someone wants the product on shelf 47." Every order has:
  - a **value** (prize money, roughly 1–15),
  - a **deadline** (a due time — deliver after it and the prize is **zero**).

**The goal of the whole system: earn the most prize money from on-time deliveries in one
500-step day.** That single number — *on-time value* — is the score every experiment measures.

*Code: the world is `wwm_sim/warehouse.py` (a modified copy of a public simulator called
TA-RWARE).*

---

## 2. The two kinds of day (regimes)

- **Day-list** — you get the *entire* day's order sheet at the first moment of the morning.
  Nothing new arrives later. (Like a bakery with all its pre-orders printed at 6am.)
- **Stream** — orders trickle in all day, with busy rushes and quiet lulls, and some
  products far more popular than others. More realistic.

There used to be a third kind ("uniform" — the queue magically always full) but it was
unrealistic and we retired it. A painful lesson lived there: a change can look great in one
kind of day and be useless in another, so **everything must be tested in the kind of day it
will actually be used in.**

*Code: both day types come from `wwm_sim/demand.py`.*

---

## 3. The order generator (the demand model)

The machine that invents the day's orders. It's built to be realistic:

- **Popularity** — a few "famous" shelves get ordered constantly, most rarely (like how a few
  songs get most of the plays). Famous shelves also cluster near each other.
- **Rushes** — sometimes a burst of orders lands at once.
- **Rush orders** — 1 in 5 orders arrives with very little time left, but pays extra.
- **Batching** — several orders can pile onto the *same* shelf. One trip delivers all of
  them, and each order is judged against **its own** deadline: if the trip is late for the
  first order but on time for the other four, you still collect four prizes.

*Code: `wwm_sim/demand.py` — `DemandModel`, `Order`, `seed_day_list` (day-list mode).*

---

## 4. The decision brain, step by step (what happens when a robot needs a job)

When a carrier finishes a task, it asks: *what should I do next?* The answer flows through a
pipeline. Each stage below is one component.

### 4a. The shortlist (the "cheap screen")

There might be 30 waiting orders. Scoring all of them carefully is slow, so first a quick
filter keeps the best-looking **15**: each order rated by *prize minus a little bit for
distance*. (We tested removing the distance part — it changed almost nothing, because the
next stages catch what it misses. We also tested letting everything through — no better.)

*Code: `wwm_sim/routing.py` — `cheap_screen`.*

### 4b. Route options (Yen's routes)

For each finalist, find **3 different roads** from the robot to the shelf — the shortest and
two alternates. Having options matters when one road is jammed.

*Code: `wwm_sim/routing.py` — `k_shortest_routes`.*

### 4c. The pocket calculator (the rollout engine)

A quick math estimate of *how long this task will take*: drive there + wait for a helper +
load + haul to the dock. No fancy physics — just distances and a known load time. It also
checks the battery would survive the trip (with the reserve measured as "enough to reach a
charger from where the task ends" — not a fixed percentage).

*Code: `wwm_sim/rollout.py` — `rollout_task`, `partner_eta`, `charger_reserve`.*

### 4d. The deadline sorter (makeable vs doomed)

The heart of the old champion. Every task goes in one of two buckets:

- **Makeable** — the calculator says it can finish before its deadline. These always come
  first, ranked by prize money.
- **Doomed** — can't possibly finish on time. Never allowed to displace makeable work, but
  ordered by *decayed* prize (barely-late valuable ones first) — worth doing if there's
  nothing better, partly because a "doomed" batch often still has later orders alive.

This one split — don't chase the impossible, don't ignore the valuable — is the biggest
single reason the system beats naive strategies.

*Code: `scripts/sim_priority.py` — `_deadline_score`, the tier logic.*

### 4e. The urgency bonus (urg8)

Inside the makeable bucket, ranking used to be by prize only — so a task about to expire
could lose to a slightly bigger prize with hours of slack, and miss by two steps. Now tasks
whose spare time is running low get a **small, capped bonus** (up to 8 points, ramping in
during the last ~40 steps of slack). Capped so a tiny prize can never jump a big one; and it
only applies to *makeable* tasks, so it can't cause deadline-chasing of hopeless ones.
Confirmed worth about **+0.9%**.

*Code: `scripts/congestion_policies.py` — `PartACongestionUrgencyController`.*

### 4f. The sync-up term

A carrier and a helper must meet at the shelf. If one would stand around waiting for the
other, the score is docked a little. Keeps the two fleets arriving together.

*Code: `scripts/sim_priority.py` — the `W_SYNC` terms; `wwm_sim/rollout.py` — `partner_eta`.*

### 4g. The traffic map (the congestion forecast)

A grid where every square counts *how many robots are about to drive through it*. Built
fresh every step from two certain things: the remaining path of every busy robot, and routes
just handed out this round. Route choice prefers roads with low counts; mid-trip re-routing
does too. Worth a small amount (~2%), mostly by preventing rare traffic-jam meltdowns.

(There was a third layer that *guessed* what robots would do next. Massive testing — including
feeding it the literally correct answers — showed it's worth nothing: other robots re-plan
around you anyway, so guessing their future is redundant. The code remains but does no work.)

*Code: `scripts/congestion_policies.py` — `PartACongestionController._pre_dispatch`.*

### 4h. Sticking to the road (adherence) and dock choice

Once a route is chosen the robot prefers to stay on it (off-route squares cost extra), but a
sudden blockage releases it to detour freely. The delivery dock is chosen by path length.

*Code: `wwm_sim/warehouse.py` — `find_path` extras; `scripts/sim_dashboard.py` — dock pick.*

---

## 5. The imagination (the world model / sequencer) — the newest and biggest piece

Everything above produces a *ranked list* of 15 candidate tasks. The old champion just took
the top one. The new brain does something better: **it imagines the rest of the day, 15
times — once per candidate — and picks the candidate whose imagined day earns the most.**

One imagined day works like this:

1. Freeze a snapshot: every robot's position and when it will free up, every helper, every
   waiting order, the clock.
2. Pin the candidate: "I take shelf X first."
3. Fast-forward: whenever any robot (me included) frees up *inside the imagination*, it picks
   its next task by the normal rules, from the queue *as it is at that imagined moment* —
   tasks get used up, deadlines tick, helpers get busy. Every delivery that lands before its
   deadline banks its prize.
4. At the end of the imagined day, read the total. That's this candidate's score.

Crucially, **only the first move is obeyed**. The imagined rest of the day is thrown away,
and the next real decision re-imagines from scratch. We measured this directly: obeying the
whole imagined plan instead loses **+11.3** — the plans break within about two decisions
(reality never quite matches), and nearly all the value is in the *constant re-imagining*,
not the plan. (This matches a famous result by Bertsekas.)

The imagination is cheap math, not a full physics run — about 4 milliseconds per imagined
day. What makes it *accurate enough* took real work:

- **The honest clock** (the engine — worth +6.9 of the +8): the imagination listens to real
  deliveries during the day, measures "tasks are running about 15 steps slower than the
  math says," and slows its own clock to match. Without this, it plans in fantasy time.
- **The honest cashier** (fixed a family of disaster days): batched shelves pay out
  *per order* in the imagination, exactly like reality — before this fix, the imagination
  wrote off any slightly-late batch as worthless and kept postponing goldmines until they
  died.
- **Helpers and return-trips are modeled** too (honest physics, though measured to matter
  only slightly).
- **All 15 finalists get imagined**, not just the top 5 — candidates ranked 6th–15th win the
  imagination often enough that widening was worth ~+3 more.

Confirmed total for the whole stack: **+3.3% over the old champion** on fresh test days, with
only ~1.5% of measurable headroom left above it.

*Code: `scripts/congestion_policies.py` — `PartACongestionSeqController` (`_sim_core` is the
imagined day; `_sim_bank` the cashier; `_sim_delay_bias` the clock), `_SqWide` = the deployed
version.*

---

## 6. The graveyard (things we built, tested, and buried — and why)

Each of these was a reasonable idea. Each was killed by measurement, not opinion.

| Idea | One-line reason it died |
|:---|:---|
| Predicting each task's delay (5 different ways, incl. machine learning) | per-task delay is basically random; even *perfect* knowledge of it was worth +0.4 ≈ nothing |
| Guessing other robots' next moves (layer 2) | they re-plan around you anyway; even the true answers helped zero |
| Value-per-minute as a formula (rate80) | assumed a saved minute is always worth the same; only true when work is endless — the imagination now prices time correctly instead |
| Blends, adaptive pricing, proximity bonuses | all coin-flips or worse in the days that matter |
| Paying imaginary partial credit for late orders in the sim | the imagination started buying things the real cashier never pays for |
| Obeying the whole imagined plan (open-loop) | plans break within ~2 decisions; costs +11.3 |
| Coordinating simultaneous free robots jointly | robots almost never free up at the same instant (~2 rounds/day); worth 0 |
| Hard rules for when to abandon a current task | every margin tested: nothing |

The one *pattern* behind most of the graveyard: **guessed information about the future is
worth nothing here; honest information about the present is worth everything.**

---

## 7. How we know any of this (the measuring tools)

- **Paired days** — every comparison runs both brains on the *identical* day (same orders,
  same everything), so the only difference is the decision-making. 30 days for a quick look,
  **120 for a verdict** (small effects at 30 days flipped sign more than once).
- **Two rulers** — the average gain *and* the win-rate (how many days it wins). Both must
  agree before anything ships.
- **The oracle** — replay one day 120 times with randomized choices and keep the best. That
  best is the "ceiling": how much a perfect decision-maker could earn. The gap between the
  brain and the ceiling is the money still on the table (currently ~1.5%).
- **The differ** — compares two runs of the same day *order by order*: which exact orders one
  brain banked that the other missed. Turns "we're 5% behind" into a named shopping list.
- **Ablation** — remove one component, re-measure. How we learned the honest clock was the
  engine and the helper-modeling was a passenger.
- **Sanity arms** — every experiment includes a setting that *must* exactly equal the old
  behavior. If it doesn't, the experiment's plumbing is broken and its numbers are ignored.
  This caught two silently-broken experiments before they could mislead us.

---

## 8. The scoreboard today

| Day type | Deployed brain | Confirmed gain |
|:---|:---|:---:|
| Day-list | old champion + urgency bonus + imagination (15 branches, honest clock & cashier) | **+3.3%** |
| Stream | old champion, unchanged | 0 — nothing has ever beaten it there |

Still open: a learned "pace model" (predicting how the day's tempo evolves, to replace the
measured clock constant — the one place machine learning has a proven job), the stream's
never-measured ceiling, and one small unexplained family of bad days (worst is now −40,
down from −101).

---

## 9. Tiny glossary

| Term | Meaning |
|:---|:---|
| AGV | carrier robot (carries shelves) |
| Picker | helper robot (must be present to load) |
| On-time value | prize money from deliveries that beat their deadlines — THE score |
| Makeable / doomed | can / cannot possibly finish before its deadline |
| Rollout | a quick imagined run-through of the future |
| Sequencer / world model | the component that imagines 15 rest-of-days and picks the best first move |
| Regime | which kind of day (day-list or stream) |
| Seed | one specific reproducible day (same seed = same day, replayable exactly) |
| Oracle | the best-of-120-replays ceiling measurement |
| Ablation | removing one part to see what it was worth |
| Sanity arm | the must-be-identical control that proves an experiment isn't broken |
