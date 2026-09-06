"""ARCHIVED 2026-07-21 — controller variants built during the congestion-map session.

All of these tested NULL against their controls (see docs/NOTES.md 2026-07-21). Moved out of the
active codebase at the user's request; kept rather than deleted because this project has no git
history to recover them from. Nothing imports this file.
"""


class PartACongestionRankQueueController(PartACongestionQueueController):
    """Queue layer ranked by the PLANNER'S OWN criterion: deadline AND value.

    WHY (better than ranking by value alone, and better than ranking by imminence alone): a pending
    order's leg gets walked when the funnel ASSIGNS that order, so the stamping weight should be the
    probability the funnel picks it -- and the funnel's criterion is the hard tier. Makeable orders all
    clear the bar and then VALUE decides among them; doomed orders collapse by g^lateness. Ranking by
    slack alone would stamp a tight low-value order above a high-value makeable one the planner would
    actually take first; ranking by value alone ignores that a far-future order's leg is not walked
    soon. Using the funnel's own rank makes the forecast self-consistent with the decision it feeds.

    Robot-independent service estimate (no rollout available here, and no robot is chosen yet):
    PACE * (nearest-AGV -> shelf + shelf -> nearest station). Still ZERO prediction: every order
    ranked here already exists in the queue.
    """

    QUEUE_TOP_K = 8
    PACE = 1.35              # steps per cell (congestion / picker-wait overhead vs pure Manhattan)
    MAKEABLE_BONUS = 1000.0  # mirrors the funnel's hard tier
    DECAY_G = 0.98           # mirrors the funnel's doomed decay

    def __init__(self, env):
        super().__init__(env)
        self._goals_xy = [(gx, gy) for (gx, gy) in env.goals]
        self._leg_cache = {}   # shelf id -> haul leg (STATIC: shelves and stations never move)

    def _haul_leg(self, G, s):
        leg = self._leg_cache.get(s.id)
        if leg is None:
            g = min(self._goals_xy, key=lambda g: abs(g[0] - s.x) + abs(g[1] - s.y))
            leg = self._shortest(G, (s.x, s.y), g)
            self._leg_cache[s.id] = leg
        return leg

    def _rank_from(self, s, v, slack, refs):
        """Funnel-criterion rank for a shelf, given an assumed value and slack."""
        d_fetch = min((abs(r[0] - s.x) + abs(r[1] - s.y)) for r in refs) if refs else 0
        d_haul = min(abs(g[0] - s.x) + abs(g[1] - s.y) for g in self._goals_xy)
        est = self.PACE * (d_fetch + d_haul)
        if est <= slack:
            return self.MAKEABLE_BONUS + v          # makeable -> value decides
        return v * (self.DECAY_G ** (est - slack))  # doomed -> collapses

    def _order_rank(self, s, now, refs):
        slack = (s.deadline - now) if s.deadline is not None else 10 ** 6
        return self._rank_from(s, task_value(s), slack, refs)

    def _rank_pending(self, now):
        claimed = set(self.assigned_items.values()) | self._predicted
        refs = [(a.x, a.y) for a in self.agvs]
        out = []
        for s in self.env.request_queue:
            if s.id in claimed:
                continue
            out.append((self._order_rank(s, now, refs), s))
        out.sort(key=lambda t: -t[0])
        return out

    def _pre_dispatch(self, free_agvs, G):
        self._predicted = set()
        PartACongestionController._pre_dispatch(self, free_agvs, G)   # layers 1-3
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        now = getattr(self.env, "_cur_steps", 0)
        ranked = self._rank_pending(now)[:self.QUEUE_TOP_K]
        n = len(ranked)
        for i, (_r, s) in enumerate(ranked):
            w = self.QUEUE_WEIGHT * (1.0 - i / n)
            for (x, y) in self._haul_leg(G, s):
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w


class PartACongestionForecastController(PartACongestionRankQueueController):
    """+ layer 5: EMPIRICAL demand forecast, stamped as LEGS (not regions).

    Which shelves get ordered is learned by OBSERVATION, not by a model: each dispatch we diff the
    request queue against the last one, and a shelf that newly appeared means an order arrived for it.
    That online frequency estimate is the same "observe, don't predict" idiom as the Beta rumor map --
    it adapts if demand shifts, unlike a fixed spatial prior (which would just be terrain).

    The top-N most-ordered shelves that are NOT currently queued are the ones most likely to be
    ordered next. We stamp their HAUL LEG -- a 1-cell-wide line -- rather than smearing their
    neighbourhood, because only mass that one candidate route hits and another misses can change an
    argmin over near-shortest routes.
    """

    FORECAST_WEIGHT = 0.20   # lighter than QUEUE_WEIGHT: the order does not exist yet
    FORECAST_TOP_N = 6

    def __init__(self, env):
        super().__init__(env)
        self._seen_ids = set()
        self._demand = {}        # shelf id -> observed arrival count

    def _observe_demand(self):
        cur = {s.id for s in self.env.request_queue}
        for sid in cur - self._seen_ids:      # newly appeared => an order arrived for it
            self._demand[sid] = self._demand.get(sid, 0) + 1
        self._seen_ids = cur

    def _pre_dispatch(self, free_agvs, G):
        self._observe_demand()
        super()._pre_dispatch(free_agvs, G)   # layers 1-4
        cong = self._cong
        if cong is None or not self._demand:
            return
        H, W = cong.shape
        queued = {s.id for s in self.env.request_queue}
        cands = [(c, sid) for sid, c in self._demand.items() if sid not in queued]
        if not cands:
            return
        cands.sort(key=lambda t: -t[0])
        cands = cands[:self.FORECAST_TOP_N]
        cmax = float(cands[0][0])
        for c, sid in cands:
            w = self.FORECAST_WEIGHT * (c / cmax)      # expected-arrival proxy
            for (x, y) in self._haul_leg(G, self.env.shelfs[sid - 1]):
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w


class PartACongestionUrgentQueueController(PartACongestionQueueController):
    """Queue layer weighted by IMMINENCE instead of value.

    WHY: the congestion map's implicit horizon is the length of the route being committed (~30-60
    steps) -- mass only changes a decision if the cell is busy INSIDE that window. Ranking pending
    orders by VALUE (the parent class) says nothing about WHEN their leg gets walked: a high-value
    order with 200 steps of slack may sit unserved for 150 steps, while a rush order with 30 steps of
    slack is served now or never. So weight by remaining slack, and gate out orders too far out to
    land in the window. Still ZERO prediction -- every order used here already exists in the queue.

    Orders already past their deadline are skipped: the score's doomed tier deprioritises them, so
    their leg is the LEAST likely to be traversed soon.
    """

    QUEUE_TAU = 50.0       # imminence decay: weight ~ exp(-slack / TAU)
    QUEUE_GATE = 150       # ignore orders with more slack than this (outside any route horizon)
    QUEUE_TOP_K = 8

    def _pre_dispatch(self, free_agvs, G):
        self._predicted = set()
        PartACongestionController._pre_dispatch(self, free_agvs, G)   # layers 1-3
        env = self.env
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        now = getattr(env, "_cur_steps", 0)
        claimed = set(self.assigned_items.values()) | self._predicted
        scored = []
        for s in env.request_queue:
            if s.id in claimed or s.deadline is None:
                continue
            slack = s.deadline - now
            if slack <= 0 or slack > self.QUEUE_GATE:
                continue
            scored.append((math.exp(-slack / self.QUEUE_TAU), s))
        if not scored:
            return
        scored.sort(key=lambda t: -t[0])
        goals = [(gx, gy) for (gx, gy) in env.goals]
        for imm, s in scored[:self.QUEUE_TOP_K]:
            w = self.QUEUE_WEIGHT * imm
            g = min(goals, key=lambda g: abs(g[0] - s.x) + abs(g[1] - s.y))
            for (x, y) in self._shortest(G, (s.x, s.y), g):
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w


# ============================================================================
# PARTIAL-CREDIT BATCH SCORING + UNIFIED (known-exact / future-possible) leg ranking
# ============================================================================
class _PartialCreditMixin:
    """Score a BATCHED shelf by PARTIAL credit instead of all-or-nothing.

    THE BUG THIS FIXES: with order batching, shelf.deadline is the EARLIEST of its orders' deadlines and
    shelf.value is their SUM, so the funnel scored the whole stack as doomed the moment ONE order in it
    became unreachable -- and then abandoned the other four, which were perfectly makeable. The metric
    already scores per order; the planner did not. This aligns them.

    Arriving at T satisfies exactly those orders with deadline >= T; missed ones keep a decayed salvage
    value. The hard TIER is preserved where it matters: delivering SOME value on time outranks
    delivering none. No prediction: every order and deadline used here already exists.
    """

    def _deadline_score(self, v, proj_late, shelf, best_r):
        dm = getattr(self.env, "demand_model", None)
        orders = dm.pending.get(shelf.id) if dm is not None else None
        if not orders or shelf.deadline is None:
            return super()._deadline_score(v, proj_late, shelf, best_r)
        finish = shelf.deadline + proj_late          # shelf.deadline == min order deadline
        g = self.DECAY_G if shelf.hardness is None else shelf.hardness
        on_time = salvage = 0.0
        for o in orders:
            if finish <= o.deadline:
                on_time += o.value
            else:
                salvage += o.value * (g ** (finish - o.deadline))
        if on_time > 0.0:
            return 1000.0 + on_time + salvage        # delivers something on time -> top tier
        return salvage


class PartACongestionPartialController(_PartialCreditMixin, PartACongestionController):
    """Champion + partial-credit batch scoring ONLY (isolates the scoring fix from any queue layer)."""


class PartARankPartialController(_PartialCreditMixin, PartACongestionRankQueueController):
    """Ranked queue layer (known orders, exact haul legs) + partial-credit batch scoring."""


class PartAUnifiedPartialController(_PartialCreditMixin, PartACongestionRankQueueController):
    """ONE ranked list of "how likely is this leg to be walked soon" -- known AND future together.

    KNOWN orders (already in the queue) get their EXACT route: the shelf->workstation haul leg is fully
    determined no matter which robot wins the task, so it is stamped at full confidence, weighted by the
    funnel's own rank (makeable-and-valuable => near 1.0, doomed => near 0).

    FUTURE orders (not ordered yet, but this shelf has order HISTORY) cannot have an exact route -- we
    know neither the shelf for certain nor the robot. So they get a POSSIBLE route: pair the candidate
    shelf with the robots that will actually be FREE in time (idle AGVs, plus busy ones within
    FINISH_HORIZON of finishing, taken at their finish position), use the nearest such robot, and stamp
    that fetch leg PLUS the haul leg. Weighted down by FORECAST_CONF (the order may never arrive) and by
    how often that shelf is ordered.

    Both compete on ONE scale, so a frequently-ordered shelf can legitimately outrank a low-value known
    order, and every leg is stamped in proportion to its likelihood.
    """

    FORECAST_CONF = 0.45      # a predicted order is worth less than a real one
    TOP_K = 10
    FUTURE_TOP_N = 5

    def __init__(self, env):
        super().__init__(env)
        self._seen_ids = set()
        self._demand = {}

    def _observe_demand(self):
        cur = {s.id for s in self.env.request_queue}
        for sid in cur - self._seen_ids:
            self._demand[sid] = self._demand.get(sid, 0) + 1
        self._seen_ids = cur

    def _free_in_time(self):
        """Positions where a robot will actually be available to start a future task."""
        out = []
        for a in self.agvs:
            path = getattr(a, "path", None)
            if not a.busy:
                out.append((a.x, a.y))                       # idle now
            elif path and len(path) <= self.FINISH_HORIZON:
                out.append(path[-1])                         # frees up soon, at its finish point
        return out

    def _pre_dispatch(self, free_agvs, G):
        self._observe_demand()
        self._predicted = set()
        PartACongestionController._pre_dispatch(self, free_agvs, G)      # layers 1-3
        env = self.env
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        now = getattr(env, "_cur_steps", 0)
        refs = [(a.x, a.y) for a in self.agvs]
        claimed = set(self.assigned_items.values()) | self._predicted
        queued = {s.id for s in env.request_queue}

        cands = []                                   # (effective likelihood, shelf, extra_leg)
        for s in env.request_queue:                  # KNOWN -> exact haul leg, full confidence
            if s.id not in claimed:
                cands.append((self._order_rank(s, now, refs), s, None))

        if self._demand:                             # FUTURE -> possible route, discounted
            starts = self._free_in_time()
            if starts:
                vs = [task_value(s) for s in env.request_queue] or [8.0]
                sl = [s.deadline - now for s in env.request_queue if s.deadline is not None] or [100.0]
                exp_v, exp_slack = sum(vs) / len(vs), sum(sl) / len(sl)
                cmax = float(max(self._demand.values()))
                fut = sorted(((c, sid) for sid, c in self._demand.items() if sid not in queued),
                             key=lambda t: -t[0])[:self.FUTURE_TOP_N]
                for c, sid in fut:
                    s = env.shelfs[sid - 1]
                    st = min(starts, key=lambda p: abs(p[0] - s.x) + abs(p[1] - s.y))
                    r = self._rank_from(s, exp_v, exp_slack, [st])
                    fetch = self._shortest(G, st, (s.x, s.y))      # the robot->shelf leg
                    cands.append((r * self.FORECAST_CONF * (c / cmax), s, fetch))

        if not cands:
            return
        cands.sort(key=lambda t: -t[0])
        cands = cands[:self.TOP_K]
        top = cands[0][0] or 1.0
        for eff, s, extra in cands:
            w = self.QUEUE_WEIGHT * (eff / top)      # stamp in proportion to likelihood
            cells = list(self._haul_leg(G, s))
            if extra:
                cells += list(extra)
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w


class PartAPropPartialController(_PartialCreditMixin, PartACongestionRankQueueController):
    """CONTROL: rank_p's haul-leg stamping, but weighted PROPORTIONALLY to rank instead of by position.

    Exists only to separate two changes that were otherwise bundled: positional decay (1 - i/n) gives a
    DOOMED task at position 2 about 87% weight, while proportional weighting (eff/eff_top) gives it
    ~0 because doomed scores collapse. Comparing this against parta_rank_p isolates the weighting rule;
    comparing parta_exact against THIS isolates exact routes vs bare legs.
    """

    def _pre_dispatch(self, free_agvs, G):
        self._predicted = set()
        PartACongestionController._pre_dispatch(self, free_agvs, G)
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        ranked = self._rank_pending(getattr(self.env, "_cur_steps", 0))[:self.QUEUE_TOP_K]
        if not ranked:
            return
        top = ranked[0][0] or 1.0
        for r, s in ranked:
            w = self.QUEUE_WEIGHT * (r / top)
            for (x, y) in self._haul_leg(G, s):
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w


class PartAExactRoutePartialController(_PartialCreditMixin, PartACongestionRankQueueController):
    """Known queued tasks get their EXACT PREDICTED ROUTE, not a bare leg.

    A task sitting in the queue is not a vague future possibility -- we know its shelf, so we can
    reconstruct the whole journey the way the funnel actually would:
      1. WHICH ROBOT: pair the task with the best-positioned robot that will really be free (idle now,
         or within FINISH_HORIZON of finishing, taken at its finish point). Each robot is consumed
         once, so two predicted tasks never claim the same robot -- the funnel's own pairing rule.
      2. FETCH LEG: robot -> shelf, chosen from Yen k-routes by the congestion-aware _pick_route.
      3. HAUL LEG: shelf -> nearest station, chosen the same way.
    Both legs are stamped, so the map carries the FULL predicted path rather than half of it.

    Self-consistent by construction: predictions are made in rank order and each one sees the map
    including the ones already stamped -- exactly what layer 3 does for real commits, pushed one step
    further into the future. Still zero demand prediction: every task here already exists in the queue.
    """

    EXACT_TOP_K = 6

    def _free_in_time(self):
        out = []
        for a in self.agvs:
            path = getattr(a, "path", None)
            if not a.busy:
                out.append((a.x, a.y))
            elif path and len(path) <= self.FINISH_HORIZON:
                out.append(path[-1])
        return out

    def _pre_dispatch(self, free_agvs, G):
        self._predicted = set()
        PartACongestionController._pre_dispatch(self, free_agvs, G)      # layers 1-3
        cong = self._cong
        if cong is None:
            return
        H, W = cong.shape
        now = getattr(self.env, "_cur_steps", 0)
        ranked = self._rank_pending(now)[:self.EXACT_TOP_K]
        if not ranked:
            return
        pool = self._free_in_time()
        top = ranked[0][0] or 1.0
        for r, s in ranked:
            if not pool:
                break
            st = min(pool, key=lambda p: abs(p[0] - s.x) + abs(p[1] - s.y))
            pool.remove(st)                                   # one robot, one predicted task
            w = self.QUEUE_WEIGHT * (r / top)
            goal = min(self._goals_xy, key=lambda g: abs(g[0] - s.x) + abs(g[1] - s.y))
            cells = []
            fetch = _rt.k_shortest_routes(G, st, (s.x, s.y), k=3)
            if fetch:
                cells += self._pick_route(fetch, s, now)      # congestion-aware, like the real pick
            haul = _rt.k_shortest_routes(G, (s.x, s.y), goal, k=3)
            if haul:
                cells += self._pick_route(haul, s, now)
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w


class PartAExactOnlyPartialController(PartAExactRoutePartialController):
    """Exact-route prediction REPLACES layer 2 instead of stacking on top of it.

    Layer 2 (FINISHING -> guess next task -> stamp finish->shelf at 0.5) is a strictly weaker version of
    the exact-route layer: one task per finishing robot, FETCH LEG ONLY, naive shortest path, and it
    knows nothing about the exact layer's robot pairing. Running both double-books ROBOTS -- layer 2
    predicts robot R does task X while the exact layer predicts R does task Y, so the map carries a
    phantom fetch leg. Here layer 2 is disabled and the exact layer owns all task prediction: it picks
    the robot, both legs, and congestion-aware routes.
    """

    def _predict_next(self, finish_xy, taken):
        return None          # disable layer 2; the exact-route layer supersedes it


class PartAFullLegController(_PartialCreditMixin, PartACongestionController):
    """LAYER 2, EDITED -- the right shape, done in place instead of as a parallel layer.

    Layer 2 always had the correct IDEA: find the robots that will free up within about a task's
    duration (FINISH_HORIZON ~= one task), cheap-screen their most likely next task, and stamp the
    route. Its flaw was stamping only HALF the journey -- the fetch leg (finish -> shelf) -- so the
    shelf -> workstation haul was never on the map at all.

    The alternative attempts each got one half and missed the other: the champion stamps fetch only;
    the rank/queue layers stamp haul only, with no robot behind them at all. Bolting a second layer on
    top (parta_exact) double-books robots -- layer 2 predicts robot R does task X while the new layer
    predicts R does task Y -- so the map carries a phantom leg.

    Fix: keep layer 2's robot-anchored cheap-screen prediction exactly as it was, and stamp BOTH legs.
    One layer, one prediction per freeing robot, the whole route. No extra layer, no double-booking.
    """

    def __init__(self, env):
        super().__init__(env)
        self._goals_xy = [(gx, gy) for (gx, gy) in env.goals]
        self._haul_cache = {}          # shelf id -> haul leg (static: shelves and stations never move)

    def _haul(self, G, shelf):
        leg = self._haul_cache.get(shelf.id)
        if leg is None:
            g = min(self._goals_xy, key=lambda g: abs(g[0] - shelf.x) + abs(g[1] - shelf.y))
            leg = self._shortest(G, (shelf.x, shelf.y), g)
            self._haul_cache[shelf.id] = leg
        return leg

    def _pre_dispatch(self, free_agvs, G):
        env = self.env
        H, W = env.grid_size
        cong = np.zeros((H, W), dtype=np.float32)
        taken = set(self.assigned_items.values())

        def stamp(cells, w):
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w

        for a in self.agvs:
            path = getattr(a, "path", None)
            if a.busy and path:
                stamp(path, 1.0)                                  # 1. KNOWN remaining path
                if len(path) <= self.FINISH_HORIZON:              # 2. frees up within ~a task duration
                    finish = path[-1]
                    nt = self._predict_next(finish, taken)        # cheap screen, as before
                    if nt is not None:
                        taken.add(nt.id)
                        stamp(self._shortest(G, finish, (nt.x, nt.y)), self.FUTURE_WEIGHT)   # FETCH
                        stamp(self._haul(G, nt), self.FUTURE_WEIGHT)                         # HAUL
        self._cong = cong
        env.congestion_grid = cong


class _FutureArrivalMixin:
    """LAYER 5 -- FUTURE ARRIVALS, robot-anchored, stamped as a FULL FETCH+HAUL CYCLE.

    Composable filter: it can be mixed into ANY of the policies so the future-arrival question is asked
    once, identically, of every architecture.

    For each robot that will free up (idle now, or within FINISH_HORIZON of finishing, taken at its
    STOPPING POINT), rank the shelves demand has actually been concentrating on -- observed order
    frequency, counted by diffing the request queue each dispatch, discounted by distance from that
    robot so a shelf across the warehouse is not treated as its likely next job. Then stamp the whole
    cycle that robot would fly if such an order appeared: stopping point -> shelf (fetch), then
    shelf -> nearest station (haul).

    Purely observational -- it reads no demand-model internals (lambda, popularity weights, hot-zone
    centres and Hawkes state are all hidden). Weighted well below real orders, because these do not
    exist yet. Shelves already in the queue are skipped: those are real, and the other layers own them.
    """

    FUTURE_REF_W = 0.25      # ceiling for an UNARRIVED order: equals the PREDICTED-task weight, so
                             # even a near-certain arrival (p->1) only matches a predicted task and
                             # stays below a known queued one (0.5). Typical p 0.08-0.65 -> 0.02-0.16.
    FUTURE_ARR_N = 3         # candidate shelves considered per freeing robot
    FUTURE_POOL = 12         # how many observed-hot shelves to rank against

    def _observe_arrivals(self):
        cur = {s.id for s in self.env.request_queue}
        if not hasattr(self, "_arr_cnt"):
            self._arr_cnt, self._arr_seen = {}, set()
        for sid in cur - self._arr_seen:            # newly appeared => an order arrived for it
            self._arr_cnt[sid] = self._arr_cnt.get(sid, 0) + 1
        self._arr_seen = cur

    def _free_points(self):
        out = []
        for a in self.agvs:
            p = getattr(a, "path", None)
            if not a.busy:
                out.append((a.x, a.y))
            elif p and len(p) <= self.FINISH_HORIZON:
                out.append(p[-1])
        return out

    def _future_haul(self, G, shelf):
        if not hasattr(self, "_fa_haul"):
            self._fa_haul = {}
            self._fa_goals = [(gx, gy) for (gx, gy) in self.env.goals]
        leg = self._fa_haul.get(shelf.id)
        if leg is None:
            g = min(self._fa_goals, key=lambda g: abs(g[0] - shelf.x) + abs(g[1] - shelf.y))
            leg = self._shortest(G, (shelf.x, shelf.y), g)
            self._fa_haul[shelf.id] = leg
        return leg

    def _stamp_future(self, G):
        cong = self._cong
        cnt = getattr(self, "_arr_cnt", None)
        if cong is None or not cnt:
            return
        env = self.env
        H, W = cong.shape
        queued = {s.id for s in env.request_queue}
        pool = sorted(((c, sid) for sid, c in cnt.items() if sid not in queued),
                      key=lambda t: -t[0])[:self.FUTURE_POOL]
        if not pool:
            return
        elapsed = max(int(getattr(env, "_cur_steps", 0)), 1)
        for st in self._free_points():
            def likelihood(t):
                # P(an order for this shelf ARRIVES within the horizon) x P(THIS robot is the one to
                # serve it). A real probability, expressed as a fraction of a KNOWN order's weight --
                # so a shelf ordered 13 times scores ~0.65 while a once-ordered shelf scores ~0.08,
                # instead of both getting the same arbitrary constant.
                c, sid = t
                s = env.shelfs[sid - 1]
                rate = c / elapsed                                   # observed arrivals per step
                p_arrive = 1.0 - math.exp(-rate * self.FINISH_HORIZON)
                d = abs(st[0] - s.x) + abs(st[1] - s.y)
                return p_arrive / (1.0 + 0.04 * d)                   # x P(this robot serves it)
            best = sorted(pool, key=lambda t: -likelihood(t))[:self.FUTURE_ARR_N]
            for s_i, (c, sid) in enumerate(best):
                s = env.shelfs[sid - 1]
                w = self.FUTURE_REF_W * likelihood((c, sid)) * (1.0 - s_i / max(len(best), 1))
                cells = list(self._shortest(G, st, (s.x, s.y))) + list(self._future_haul(G, s))
                for (x, y) in cells:
                    if 0 <= y < H and 0 <= x < W:
                        cong[y, x] += w

    def _pre_dispatch(self, free_agvs, G):
        self._observe_arrivals()
        super()._pre_dispatch(free_agvs, G)       # whatever the base policy does
        self._stamp_future(G)                     # then the future-arrival cycle on top


class PartAPartialFutureController(_FutureArrivalMixin, PartACongestionPartialController):
    """control + future arrivals"""


class PartAFullLegFutureController(_FutureArrivalMixin, PartAFullLegController):
    """edited layer 2 (fetch+haul) + future arrivals"""


class PartAExactOnlyFutureController(_FutureArrivalMixin, PartAExactOnlyPartialController):
    """task-anchored exact routes + future arrivals"""


class PartARankPFutureController(_FutureArrivalMixin, PartARankPartialController):
    """disconnected haul layer + future arrivals"""


class PartACongDelayController(PartACongestionPartialController):
    """Congestion finally reaches TASK SELECTION -- via the finish estimate, not the route tiebreak.

    Until now the map only steered ROUTE choice and reroutes; _finish_delay returned 0.0 in every
    policy tested, so congestion never touched proj_late and therefore never changed WHICH TASK was
    picked. That confined it to the low-leverage lever: picking route B over A saves a few steps, while
    picking task B over A decides whether ~15 points of value are banked or lost.

    Here the projected finish absorbs congestion delay along BOTH legs of the job -- fetch (robot ->
    shelf) and haul (shelf -> station). A task whose whole cycle runs through traffic is then correctly
    judged slower, tips into doomed sooner, and loses to a cleaner task. Note the haul leg's congestion
    was previously never priced anywhere: _pick_route only ever scored the fetch route.
    """

    FINISH_CONG_K = 0.3

    def _route_cong(self, route):
        cong = self._cong
        if cong is None or not route:
            return 0.0
        H, W = cong.shape
        return sum(float(cong[y, x]) for (x, y) in route if 0 <= y < H and 0 <= x < W)

    def _pick_route(self, routes, shelf, now):
        self._cur_shelf = shelf                    # so _finish_delay can reach this task's haul leg
        return super()._pick_route(routes, shelf, now)

    def _haul_cells(self, shelf):
        if not hasattr(self, "_cd_haul"):
            self._cd_haul = {}
            self._cd_goals = [(gx, gy) for (gx, gy) in self.env.goals]
        leg = self._cd_haul.get(shelf.id)
        if leg is None:
            g = min(self._cd_goals, key=lambda g: abs(g[0] - shelf.x) + abs(g[1] - shelf.y))
            leg = self._shortest(_rt.build_agv_graph(self.env), (shelf.x, shelf.y), g)
            self._cd_haul[shelf.id] = leg
        return leg

    def _finish_delay(self, best_r):
        d = self._route_cong(best_r)                          # FETCH leg congestion
        sh = getattr(self, "_cur_shelf", None)
        if sh is not None:
            d += self._route_cong(self._haul_cells(sh))       # HAUL leg congestion (never priced before)
        return self.FINISH_CONG_K * d


class PartACongDelayStrongController(PartACongDelayController):
    """Same, with a stronger congestion->delay conversion (brackets the magnitude)."""
    FINISH_CONG_K = 1.0


# ============================================================================
# SPEC BUILD: congestion from predicted TASK/ROUTE COMBOS of robots that free up in time.
# Champion + batching ONLY -- no partial credit, no queue layer, no future-arrival layer.
# ============================================================================
class PartACongPredTop1Controller(PartACongestionController):
    """Layer 2 rebuilt to spec: predicted TASK/ROUTE COMBOS, with EXACT routes (fetch AND haul).

    For each robot that will FREE UP IN TIME (busy, within FINISH_HORIZON of its target, taken at the
    point where it finishes), rank the live queue by VALUE AND DEADLINE -- the funnel's own criterion,
    not the old cheap-screen which ignored deadlines entirely -- and take its most likely task. Then
    stamp the whole route that combo would fly: FETCH (finish point -> shelf) and HAUL (shelf ->
    station), each chosen the way the robot actually would, from Yen k-routes scored against the map
    built so far. The old layer 2 stamped only the fetch half, so the haul was never predicted at all.

    N=1 bets all the mass on the single most likely task. The N=3 subclass spreads the SAME total mass
    across the three most likely, hedging which task the robot really ends up taking.
    """

    PRED_N = 1
    PRED_SHARES = (1.0,)
    PACE = 1.35
    DECAY_G = 0.98

    def __init__(self, env):
        super().__init__(env)
        self._goals_xy = [(gx, gy) for (gx, gy) in env.goals]

    def _rank_for(self, s, start, now):
        """Funnel criterion: makeable -> value decides; doomed -> collapses. Deadline AND value."""
        v = task_value(s)
        slack = (s.deadline - now) if s.deadline is not None else 10 ** 6
        d = (abs(start[0] - s.x) + abs(start[1] - s.y)
             + min(abs(g[0] - s.x) + abs(g[1] - s.y) for g in self._goals_xy))
        est = self.PACE * d
        return (1000.0 + v) if est <= slack else v * (self.DECAY_G ** (est - slack))

    def _pre_dispatch(self, free_agvs, G):
        env = self.env
        H, W = env.grid_size
        cong = np.zeros((H, W), dtype=np.float32)
        self._cong = cong                     # set early so _pick_route scores against the live map
        env.congestion_grid = cong
        taken = set(self.assigned_items.values())
        now = getattr(env, "_cur_steps", 0)

        def stamp(cells, w):
            for (x, y) in cells:
                if 0 <= y < H and 0 <= x < W:
                    cong[y, x] += w

        for a in self.agvs:                                   # 1. KNOWN remaining paths
            p = getattr(a, "path", None)
            if a.busy and p:
                stamp(p, 1.0)

        for a in self.agvs:                                   # 2. robots that FREE UP IN TIME
            p = getattr(a, "path", None)
            if not (a.busy and p and len(p) <= self.FINISH_HORIZON):
                continue
            start = p[-1]
            cands = [s for s in env.request_queue if s.id not in taken]
            if not cands:
                continue
            cands.sort(key=lambda s: -self._rank_for(s, start, now))
            picks = cands[:self.PRED_N]
            taken.add(picks[0].id)                            # its top choice is spoken for
            for i, s in enumerate(picks):
                w = self.FUTURE_WEIGHT * self.PRED_SHARES[i]
                fetch = _rt.k_shortest_routes(G, start, (s.x, s.y), k=3)
                if fetch:
                    stamp(self._pick_route(fetch, s, now), w)          # EXACT fetch route
                g = min(self._goals_xy, key=lambda q: abs(q[0] - s.x) + abs(q[1] - s.y))
                haul = _rt.k_shortest_routes(G, (s.x, s.y), g, k=3)
                if haul:
                    stamp(self._pick_route(haul, s, now), w)           # EXACT haul route


class PartACongPredTop3Controller(PartACongPredTop1Controller):
    """Same, but the three most likely task/route combos share the same total mass (0.5 / 0.3 / 0.2)."""
    PRED_N = 3
    PRED_SHARES = (0.5, 0.3, 0.2)


class PartACongestionOrigController(PartACongestionController):
    """The HISTORICAL champion: FUTURE_WEIGHT pinned at its original 0.5.

    The base class now carries 0.25 (certainty ordering: a predicted task must sit below a known queued
    one). This subclass preserves the configuration that was actually crowned, so the audit -- does the
    congestion map beat no congestion map at all -- is run against the policy whose claim is in question,
    without reverting the deliberate change to the base.
    """
    FUTURE_WEIGHT = 0.5


class PartACongPredTop1PCController(_PartialCreditMixin, PartACongPredTop1Controller):
    """pred1 + PARTIAL-CREDIT batch scoring."""


class PartACongPredTop3PCController(_PartialCreditMixin, PartACongPredTop3Controller):
    """pred3 + PARTIAL-CREDIT batch scoring."""
