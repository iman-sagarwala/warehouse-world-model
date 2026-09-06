# What we did on 2026-07-18 — the short version

**Today was not a building day. It was a checking day.**

It started as one: the demand stream got built — orders now arrive over time, in busy and quiet
stretches, instead of the queue being magically always full. That's the one genuinely new thing.

Then a small question — *does layer 2 actually work?* — ate the rest of the day, because the answer was
no, and finding that out exposed something bigger.

**The bigger thing:** our testing was too weak. We'd been running 30 simulated days and treating the
result as fact. You need about 120 before a small difference is trustworthy. So several things written
down as "this works" were partly luck. The congestion map's advantage is about half what we recorded.

---

## The shape of the day

- **Built:** the demand stream, plus day-list mode (whole day's orders known up front).
- **Disproved:** the guessing layer. The map works the same without it.
- **Found broken:** a feature that had silently never run at all — x and y were swapped, so every one of
  its 226 lookups failed. Its "result" in our spreadsheet was a fake duplicate of another policy.
- **Found working:** letting robots pick a delivery station by traffic instead of pure distance (+5.3).
- **Lost confidence in:** several older numbers, including the headline one.

---

## What "the guessing layer" means

The congestion map is built by stamping routes onto a grid. Three sources:

| | What it stamps | Real or imagined? |
|---|---|---|
| **Layer 1** | a busy robot's **remaining path** — cell by cell | real, already being driven |
| **Layer 3** | routes we **just assigned** this round | real, we chose them ourselves |
| **Layer 2** | for a robot with **no next task yet**: a made-up guess at which task it'll grab, and the route there | **imagined — the trip doesn't exist** |

**Layer 2 is the guessing layer, and only layer 2.** It's the one describing a journey nobody has been
given. We rebuilt it correctly → no change. Deleted it → no change. A third of the map's ink, doing
nothing.

**We keep the route part, and it is still a forecast.** Layer 1 is the *remaining* path — where a robot
**will be** over the next ~10–25 steps. So the map still predicts congestion from routes. It just only
contains journeys someone is actually committed to, instead of invented ones.

**Size check:** the map is worth ~2% more on-time value, winning ~58% of days. Real and worth keeping,
but small. Nothing in the map is currently a big win.

---

## What the oracle test was — RESULT: nothing to chase

It's about the **guessing layer**, not the part we kept.

Layer 2 guessed badly — so maybe a *good* guess would pay. Rather than build a clever predictor first,
we cheat: run the day, write down what each robot **actually** did next, rewind, and feed layer 2 the
true answers. Now it is never wrong.

- If even the **true** answer changes nothing → guessing quality was never the issue, imagined trips
  just don't matter however accurate, and no predictor (including a policy-rollout) is worth building.
- If it helps a lot → that gap is the **maximum prize**, and building a real predictor is justified.

**Result: perfect knowledge is worth nothing.** Champion 198.9, oracle 196.4 — an effect of −2.5, with
a confidence range of −5.6 to +0.6. The number that matters is that upper end: **the best case for any
predictor is +0.6**, i.e. negligible. So no predictor is worth building — not a cleverer guess, not a
policy-rollout, not a learned model. We handed it the literal correct answer and the map got no better.

That is exactly what this kind of test is for: it cost a few hours instead of the days a real predictor
would have taken, and the answer doesn't depend on how well that predictor would have been built.

Caveat: feeding it the truth changes what the robots do, so the recording drifts — it's *near*-oracle
(83.6% accurate lookups). That cuts the reassuring way: better information than any real system could
ever have, and still nothing.

---

## Two rules that came out of today (both from mistakes made today)

1. **Anything under about +8 needs 120+ runs.** Five effects moved a lot between 30 and 120 runs — four
   shrank to nothing, one flipped sign completely.
2. **Don't explain a mechanism for an unresolved effect.** The dock change looked harmful at 20 runs and
   got a tidy explanation invented for it; by 120 runs it was a solid win. The explanation made noise
   feel like signal, and made it harder to abandon.

---

## Where the project stands

Formally still **Stage 0** (foundation), about two-thirds through. Today closed one Stage 0 item (a
deadline-generation model), pulled a Stage 4 item forward (the Hawkes demand model), and revived
**Part C** — which had been cut *only* because the always-full queue left no lulls to prepare for. There
are lulls now, so that reasoning no longer holds.
