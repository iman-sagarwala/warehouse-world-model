"""Realistic order-arrival stream (replaces the toy uniform-resample demand).

Research-backed (docs/NOTES 2026-07-16): real warehouse arrivals are bursty and popularity-skewed, not
uniform Poisson. This model draws order ARRIVALS from a non-homogeneous Poisson base (diurnal rate)
with a Hawkes self-exciting burst term, picks the ordered shelf by ZIPF popularity (a few spatially-
clustered "hot" SKUs get most demand), and attaches a per-order VALUE and DEADLINE drawn from a RUSH /
STANDARD mixture (an expedited tier lands already tight, and is worth more). Orders accumulate
in the request queue and are removed on delivery (no auto-resample) -> the queue ebbs and flows, which
is what makes anticipation (preparing for future demand) meaningful.

Usage (runner): after env.reset(), do
    env.request_queue = []
    env.demand_model = DemandModel(env, seed)
    env.demand_model.seed_initial(env, n=12)
The env's step() then calls demand_model.step(env, now) each tick (opt-in; no effect if unset).
"""
from __future__ import annotations

import math

import numpy as np


class Order:
    """One customer order naming a shelf. MANY orders may name the SAME shelf concurrently.

    This is the SKU idea: a shelf holds a product, and several customers can want that product at once.
    The robots never change -- one AGV + one picker, and the shelf leaves the floor while carried -- but
    ONE TRIP of that shelf to a station fulfils EVERY order pending on it (exactly how goods-to-person
    picking works: the pod arrives and the worker picks several orders' items off it).
    """

    __slots__ = ("shelf", "value", "deadline", "is_rush", "t_arrive")

    def __init__(self, shelf, value, deadline, is_rush, t_arrive):
        self.shelf = shelf
        self.value = value
        self.deadline = deadline
        self.is_rush = is_rush
        self.t_arrive = t_arrive


class DemandModel:
    def __init__(self, env, seed, rate=0.075, amp=0.8, zipf_s=1.1, period=250, n_hot=3,
                 hawkes_p=0.006, hawkes_jump=0.4, hawkes_decay=0.90,
                 value_lo=1.0, value_hi=15.0,
                 rush_frac=0.20, rush_slack=(25, 60), std_slack=(80, 200), rush_value_mult=1.6,
                 slotting="velocity", slot_jitter=6.0, exogenous=False, horizon=500,
                 window_index=None, n_windows=144, day_steps=72_000,
                 utilisation=None, task_steps=50,
                 value_dist='uniform', value_median=8.0, value_sigma=1.0, drift=None):
        # TIMESCALE FIX (2026-08-06). The old default `period=250` claimed one DAY = 250 steps, i.e.
        # ~5.8 min per step. But a step is ONE CELL of robot travel, and the Robotnik grounding
        # (RB-KAIROS+ 1.5 m/s over 1 m cells, ~62 s per measured 50-step task) puts a step at ~1.2 s.
        # The two clocks disagreed by ~280x, and the sinusoid was swinging demand +-80% inside what is
        # really a TEN-MINUTE window. Diurnal variation happens over HOURS, so it cannot live inside an
        # episode -- it has to live ACROSS episodes.
        #   500 steps x 1.2 s   = 600 s   = 10 min per episode
        #   144 episodes x 500  = 72,000 steps x 1.2 s = 86,400 s = EXACTLY 24 h
        # So pass `window_index=i` to make seed i the i-th 10-minute slot of the day; the diurnal term
        # then advances over `day_steps` instead of `period`, drifting only ~0.7% within an episode.
        # Within-episode variation is carried by the HAWKES burst process, which is the mechanism the
        # literature actually measures at this timescale. Leave `window_index=None` for the legacy
        # `period` behaviour so existing experiments reproduce bit-for-bit.
        self.window_index = window_index
        self.n_windows = n_windows
        self.day_steps = day_steps
        # UTILISATION-ANCHORED ARRIVAL RATE (2026-08-06). `rate` was a bare constant (0.075/step) with
        # no operational meaning. Fleet capacity is n_agvs x (horizon / task_steps); at the measured
        # ~50-step task and 8 AGVs that makes 0.075 imply ~47% utilisation, whereas real distribution
        # centres run far busier. Passing `utilisation` derives the rate instead:
        #     rate = utilisation * n_agvs / task_steps
        # so the parameter is a number operations actually publish, and it is sweepable on a meaningful
        # axis. Leave it None to keep the legacy constant.
        self.task_steps = task_steps
        self.utilisation = utilisation
        if utilisation is not None:
            n_agv = sum(1 for a in env.agents if a.type.name == "AGV") or len(env.agents)
            rate = float(utilisation) * n_agv / float(task_steps)
        self.implied_utilisation = rate * float(task_steps) / max(
            1, sum(1 for a in env.agents if a.type.name == "AGV"))
        self.phase = (2.0 * math.pi * (window_index % n_windows) / n_windows
                      if window_index is not None else 0.0)
        self.rng = np.random.RandomState(seed)
        self.shelfs = list(env.shelfs)
        n = len(self.shelfs)
        # ZIPF popularity over shelves (random rank), then boost a few spatial HOT clusters so popular
        # SKUs are spatially correlated (hot zones), not scattered.
        hot = [self.shelfs[int(self.rng.randint(n))] for _ in range(n_hot)]
        dist = np.array([min(abs(s.x - h.x) + abs(s.y - h.y) for h in hot) for s in self.shelfs],
                        dtype=float)
        # DEMAND DRIFT (M3b probe, 2026-08-23; opt-in): hot zones' relative intensity follows
        # REAL hour-of-day curves (calibrated from the Instacart sample -- produce peaks ~10h,
        # snacks/bakery/deli ~13-14h). drift = {"curves": [n_hot lists of 24 mean-1 values],
        # "gain": 1.0}. The 24-hour profile is mapped onto the existing diurnal phase (one
        # `period` = one day-cycle); shelf weights become phase-dependent: wt_t = wt * curve of
        # the shelf's NEAREST hot zone. Only WHERE demand is hot changes -- rate, values,
        # deadlines, Hawkes bursts are untouched.
        self.drift = drift
        self._zone = np.array([int(np.argmin([abs(s.x - h.x) + abs(s.y - h.y) for h in hot]))
                               for s in self.shelfs], dtype=int)
        if slotting == "velocity":
            # VELOCITY-BASED SLOTTING (real practice: fast movers are stored near dispatch). Zipf RANK
            # is assigned by proximity to a hot centre, so popularity is genuinely spatially CLUSTERED.
            # Without this, ranks are a random permutation and the Zipf spread (~400x top-to-bottom)
            # swamps any spatial term (<=3.5x) -> popularity is spatially white noise and "which area
            # is hot" is unestimable in principle. Jitter keeps slotting imperfect, as in reality.
            key = dist + self.rng.uniform(0.0, slot_jitter, size=n)
            order = np.argsort(key)
            ranks = np.empty(n, dtype=float)
            ranks[order] = np.arange(1, n + 1, dtype=float)
        else:                                   # "random": legacy, spatially unstructured popularity
            ranks = self.rng.permutation(n).astype(float) + 1.0
        w = 1.0 / ranks ** zipf_s
        self.wt = {s.id: float(w[i]) for i, s in enumerate(self.shelfs)}
        self.rate = rate
        self.amp = amp
        self.period = period
        self.hawkes_p, self.hawkes_jump, self.hawkes_decay = hawkes_p, hawkes_jump, hawkes_decay
        self.value_lo, self.value_hi = value_lo, value_hi
        self.value_dist, self.value_median, self.value_sigma = value_dist, value_median, value_sigma
        self.rush_frac, self.rush_slack, self.std_slack = rush_frac, rush_slack, std_slack
        self.rush_value_mult = rush_value_mult
        self._excite = 0.0
        self.mode = "stream"       # or "daylist" (see seed_day_list)
        self.pending = {}           # shelf id -> [Order]; MANY orders may name one shelf
        self.arrivals = 0
        self.rush_arrivals = 0
        self.rate_log = []          # instantaneous lambda each step (for inspection)
        # EXOGENOUS demand (opt-in; default OFF so every existing result keeps its meaning).
        # WHY: `_inject` picks a shelf from those NOT currently in transit, so WHICH shelf gets ordered
        # depends on what the robots happen to be carrying -> demand is ENDOGENOUS TO THE POLICY.
        # Measured 2026-08-01: two policies on the same seed produce the same NUMBER and TIMES of
        # arrivals but only ~22% of the same (time, shelf) pairs. That makes paired comparisons only
        # partially paired, and makes a true perfect-information experiment impossible (the "known
        # future" recorded under one policy is ~75% wrong under another). It is also unrealistic:
        # customers do not avoid ordering a product because a robot is mid-trip with its pod.
        # exogenous=True pre-generates the WHOLE arrival schedule from the seed alone -- times, shelves,
        # values, deadlines -- so demand is identical under every policy.
        self.exogenous = exogenous
        self._sched, self._sched_i = None, 0
        if exogenous:
            self._build_schedule(horizon)

    def _drift_mult(self, t):
        """Per-shelf weight multiplier at time t (1.0 everywhere when drift is off)."""
        if not self.drift:
            return None
        curves = self.drift["curves"]
        gain = float(self.drift.get("gain", 1.0))
        hr = (float(t) % self.period) / self.period * 24.0
        i0, frac = int(hr) % 24, hr - int(hr)
        m = np.empty(len(self.shelfs))
        for z in range(len(curves)):
            c = curves[z % len(curves)]
            cz = c[i0] * (1 - frac) + c[(i0 + 1) % 24] * frac
            m[self._zone == z] = 1.0 + gain * (cz - 1.0)
        return np.maximum(m, 0.05)

    def _build_schedule(self, horizon):
        """Pre-draw every arrival from the seed alone (no env state) -> policy-independent demand."""
        saved = self.rng
        self.rng = np.random.RandomState(int(saved.randint(0, 2 ** 31 - 1)))
        try:
            w = np.array([self.wt[s.id] for s in self.shelfs], dtype=float)
            w /= w.sum()
            excite, sched = 0.0, []
            for t in range(int(horizon)):
                excite *= self.hawkes_decay
                if self.rng.random() < self.hawkes_p:
                    excite += self.hawkes_jump
                lam = self.rate * self._diurnal(t) + excite
                dm = self._drift_mult(t)
                if dm is not None:
                    wt_t = w * dm
                    wt_t = wt_t / wt_t.sum()
                else:
                    wt_t = w
                for _ in range(int(self.rng.poisson(max(0.0, lam)))):
                    s = self.shelfs[int(self.rng.choice(len(self.shelfs), p=wt_t))]
                    v, dl, rush = self._sample_order(t)
                    sched.append((float(t), s, v, dl, rush))
        finally:
            self.rng = saved
        self._sched = sched

    def _place(self, env, shelf, v, dl, rush, now):
        """Record a pre-scheduled order (exogenous path -- no shelf choice, no env-dependent draw)."""
        self.pending.setdefault(shelf.id, []).append(Order(shelf, v, dl, rush, now))
        self._refresh(env, shelf)
        self.arrivals += 1
        self.rush_arrivals += int(rush)

    def future_arrivals(self, after, until):
        """The TRUE upcoming orders in (after, until] -- only meaningful when exogenous=True, where the
        schedule is fixed in advance and therefore genuinely knowable. Used by the perfect-information
        arm; returns [] otherwise so no caller can silently get a policy-contaminated 'future'."""
        if not self.exogenous:
            return []
        return [(t, s, v, dl) for (t, s, v, dl, _r) in self._sched if after < t <= until]

    def _diurnal(self, t):
        """Day/night wave. WIDE swing (amp=0.8 -> 0.2x..1.8x) is deliberate: with base rate ~= delivery
        capacity, peaks build a real backlog (the planner gets many candidates to choose among) and
        troughs drain toward idle. A narrow swing just parks the system at one fixed load, which is
        either permanent overload or permanent starvation -- neither exercises anticipation."""
        if self.window_index is not None:
            # Diurnal across episodes: this window sits at `self.phase` on the daily curve and
            # advances only 500/72000 = 0.7% of the cycle during the episode -- effectively flat,
            # which is what ten minutes of a real day looks like.
            return 1.0 + self.amp * math.sin(self.phase + 2.0 * math.pi * t / self.day_steps)
        return 1.0 + self.amp * math.sin(2.0 * math.pi * t / self.period)

    def warm_start_n(self, base=12):
        """Backlog to open the window with, scaled by TIME OF DAY. A 3 a.m. slot opens near-empty; a
        mid-afternoon slot opens with a real queue. Derived from the seed/phase only -- never from a
        previous run -- so every arm sees the identical opening state and pairing survives.
        (Chaining episodes end-to-start would have reintroduced POLICY-DEPENDENT state, the same
        failure that forced `exogenous=True`, and would have destroyed sample independence.)"""
        if self.window_index is None:
            return base
        return max(0, int(round(base * self._diurnal(0))))

    def _sample_order(self, now):
        """Draw (value, deadline, is_rush) as a MIXTURE.

        Real fulfilment has an expedited tier: some orders land already tight (or even unmakeable),
        rather than every order arriving with more slack than a task takes to serve. Rush orders are
        also worth more -- that is the value/urgency joint the demand research left open. Draw counts
        are branch-independent so the arrival stream stays policy-independent (paired comparison).
        """
        is_rush = bool(self.rng.random() < self.rush_frac)
        lo, hi = self.rush_slack if is_rush else self.std_slack
        # VALUE DISTRIBUTION (2026-08-06). Uniform(1, 15) is wrong in SHAPE, not just range: real
        # order values are LOGNORMAL -- most orders small, a long right tail of large ones. The scale
        # is irrelevant here (the objective is linear), but the SPREAD and SHAPE are not: banked value
        # is a SUM OF DISCRETE TASK VALUES, so tightly-packed uniform values make different task
        # orderings produce IDENTICAL sums. Measured consequence: **48.6% of `_pick_winner` calls end
        # TIED**, mean tie size 5.09 -- and ties are where the +3.6% oracle headroom was localised,
        # because the funnel's arbitrary tie-break then picks the branch. A long-tailed distribution
        # collides far less often. `value_dist="uniform"` keeps the legacy behaviour exactly.
        if getattr(self, "value_dist", "uniform") == "lognormal":
            mu = math.log(max(1e-9, self.value_median))
            v = float(self.rng.lognormal(mu, self.value_sigma))
            v = float(min(max(v, self.value_lo), self.value_hi))
        else:
            v = float(self.rng.uniform(self.value_lo, self.value_hi))
        slack = int(self.rng.randint(lo, hi))
        if is_rush:
            v *= self.rush_value_mult
        return v, now + slack, is_rush

    def _refresh(self, env, shelf):
        """Re-derive the shelf's task attributes from its pending orders, and sync the request queue.

        BATCHING: value = SUM of pending order values (one trip serves them all, so a shelf with four
        orders really is worth four times as much to fetch); deadline = EARLIEST pending deadline (the
        trip has to satisfy the tightest one). The planner needs no changes to exploit this.
        """
        lst = self.pending.get(shelf.id)
        if lst:
            shelf.value = sum(o.value for o in lst)
            shelf.deadline = min(o.deadline for o in lst)
            shelf.is_rush = any(o.is_rush for o in lst)
            shelf.n_orders = len(lst)
            # A shelf ordered while it is MID-TRIP must not enter the queue (a second AGV would be
            # dispatched to a pod that is off the floor). Its orders sit in `pending` and are served by
            # the trip already underway -- `fulfill` pops every pending order for the shelf. In the
            # legacy (endogenous) path carried shelves are never chosen, so this guard is a no-op there.
            if shelf not in env.request_queue and not any(
                    a.carrying_shelf is shelf for a in env.agents):
                env.request_queue.append(shelf)
        else:
            shelf.n_orders = 0
            if shelf in env.request_queue:
                env.request_queue.remove(shelf)

    def _inject(self, env, now):
        # A shelf already in the queue MAY be ordered again -- that is the whole point. Only a shelf
        # currently in transit is excluded (it is off the floor mid-trip).
        carried = {a.carrying_shelf for a in env.agents if a.carrying_shelf}
        avail = [s for s in self.shelfs if s not in carried]
        if not avail:
            return
        w = np.array([self.wt[s.id] for s in avail], dtype=float)
        dm = self._drift_mult(now)
        if dm is not None:
            idx = {s.id: i for i, s in enumerate(self.shelfs)}
            w = w * np.array([dm[idx[s.id]] for s in avail])
        w /= w.sum()
        s = avail[int(self.rng.choice(len(avail), p=w))]
        v, dl, rush = self._sample_order(now)
        self.pending.setdefault(s.id, []).append(Order(s, v, dl, rush, now))
        self._refresh(env, s)
        self.arrivals += 1
        self.rush_arrivals += int(rush)

    def fulfill(self, env, shelf, now):
        """Shelf delivered: EVERY order pending on it is fulfilled by this one trip. Returns them."""
        lst = self.pending.pop(shelf.id, [])
        self._refresh(env, shelf)
        return lst

    def seed_initial(self, env, n=12, now=0):
        """Warm-start with n orders so robots aren't idle on a cold start."""
        for _ in range(n):
            self._inject(env, now)

    def seed_day_list(self, env, horizon=500):
        """DAY-LIST mode: pre-generate the whole day's orders and release them ALL at t=0.

        Real fulfilment runs both ways -- a wave/batch release where the day's work is known up front,
        and a live stream. This is the batch case. Arrival TIMES are still drawn from the same NHPP +
        Hawkes process, and each order's deadline is still t_arrive + slack, so DUE TIMES stay staggered
        across the day; only VISIBILITY changes -- the planner can see all of it from step 0.

        That makes this the PERFECT-FORESIGHT bound on demand knowledge: whatever a demand predictor
        (Part C) could ever be worth is bounded by day-list minus stream, measured with no predictor
        built. After this the model injects nothing further (step() is a no-op).
        """
        self.mode = "daylist"
        excite = 0.0
        for t in range(horizon):
            excite *= self.hawkes_decay
            if self.rng.random() < self.hawkes_p:
                excite += self.hawkes_jump
            lam = self.rate * self._diurnal(t) + excite
            self.rate_log.append(lam)
            for _ in range(int(self.rng.poisson(max(0.0, lam)))):
                self._inject(env, t)          # deadline = t + slack: due-times stay spread over the day
        return self.arrivals

    def step(self, env, now):
        if self.mode == "daylist":
            return                        # whole day was released at t=0; nothing arrives later
        if self.exogenous:                # replay the pre-drawn schedule -> identical under any policy
            while self._sched_i < len(self._sched) and self._sched[self._sched_i][0] <= now:
                t, s, v, dl, rush = self._sched[self._sched_i]
                self._sched_i += 1
                self._place(env, s, v, dl, rush, t)
            return
        # Hawkes excitation: decays each tick, occasionally jumps (a promotional burst)
        self._excite *= self.hawkes_decay
        if self.rng.random() < self.hawkes_p:
            self._excite += self.hawkes_jump
        lam = self.rate * self._diurnal(now) + self._excite      # non-homogeneous rate
        self.rate_log.append(lam)
        k = int(self.rng.poisson(max(0.0, lam)))
        for _ in range(k):
            self._inject(env, now)
