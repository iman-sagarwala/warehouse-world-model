"""M3 BATTERY on champion v6 -- feasibility-gated, charge-to-need, lookahead-timed (USER DESIGN).

The three pieces, replacing Stage-0's dumb thresholds (GO_CHARGE 0.35 -> FULL 0.95):

1. FEASIBILITY (the never-executed filter, finally wired): every candidate task in the funnel is
   priced for round-trip energy -- fetch + loaded carry + return + RESERVE to reach a charger from
   the end position (rollout_task's existing accounting). Infeasible candidates are DELETED, exactly
   like impossible-deadline tasks.

2. WHEN to charge (the lookahead timing, in its cleanest form): a robot charges exactly when its
   battery-feasible task set is empty but tasks exist. While any feasible task remains, that task
   wins automatically -- charging banks zero value, so its value rate only becomes best when nothing
   else is possible. Opportunistic: a robot idle on an empty queue also drifts to a charger.

3. HOW MUCH (charge-to-need, not charge-to-full): duration = energy(best candidate's round trip +
   reserve) - current level, plus a small margin. Early release: each act(), if the robot's level now
   covers a feasible task, it is released immediately -- charging never outlasts its own purpose.

Safety backstop kept from Stage-0: a robot at/below the floor away from a charger is gated to no-op
(stranded) -- the M3 audit requires stranded = 0.

Smoke arms (compressed battery, steps_per_charge=300, so it binds within an episode):
  nobat    battery physics OFF -- the ceiling
  stage0   champion + BatteryTracker + Stage-0 thresholds (GO_CHARGE/FULL)
  m3       champion + feasibility filter + charge-to-need + early release
"""
import os
import sys
import statistics as st
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, int(os.environ.get("SEEDS", "12")) + 1))
NPROC = int(os.environ.get("NPROC", "8"))
ARMS = os.environ.get("M3ARMS", "nobat,stage0,m3,m3lite").split(",")
MARGIN = 0.02          # charge-to-need safety margin (fraction of full battery)


def floor_bays(n_slots):
    """Charging bays are BUILDING infrastructure (USER RULE 2026-08-16: locations must not
    change with the fleet). Count is fixed per floor by storage capacity; positions follow
    deterministically (even stride over the sorted slot list). large=8 matches the shipped
    M3 reference exactly."""
    if n_slots <= 80:
        return 4
    if n_slots <= 140:
        return 6
    if n_slots <= 220:
        return 8
    return 12


def setup_bays(env, n=None):
    """Dedicate n shelf-FREE charging bays (USER RULE 2026-08-14: charger cells
    realistically have no shelf). Picks the same spread of storage cells default_chargers
    would, then strips the stored pod from the world: SHELVES grid cleared, and the shelf
    ids recorded so the demand model can drop them from its universe (env.shelfs itself is
    NOT touched -- `shelfs[id-1]` indexing is pervasive). Sets `env.charger_keepout` so
    slot_divert never treats a bay as a drop slot in ANY arm. Call after env.reset() and
    BEFORE building the DemandModel; then filter dm.shelfs with `env._charger_bay_ids`."""
    from wwm_sim.battery import default_chargers
    from wwm_sim.warehouse import CollisionLayers as _CL
    if n is None:
        goals = set(env.goals)
        n_slots = sum(1 for (y, x) in env.action_id_to_coords_map.values()
                      if (x, y) not in goals)
        n = floor_bays(n_slots)
    bays = default_chargers(env, n)
    stripped = set()
    for (x, y) in bays:
        sid = int(env.grid[_CL.SHELVES, y, x])
        if sid:
            env.grid[_CL.SHELVES, y, x] = 0
            stripped.add(sid)
    env._charger_bays = set(bays)
    env._charger_bay_ids = stripped
    env.charger_keepout = set(bays)
    return bays


# TUNER v2 (USER 2026-08-16): champion decision weights join the candidate space -- their M1
# flatness was measured on ONE map; on other ratios/sizes the right values may differ.

def _battery_risk(ctrl, env):
    """Projected strandings BEYOND the horizon: level minus pessimistic trip-to-bay cost
    leaves the robot under the floor -> it is already committed to stranding even though
    the fork ended. Catches the slow drains a 100-step horizon cannot see."""
    bat = ctrl.battery
    cfg_ = bat.cfg if hasattr(bat, "cfg") else None
    drain = (1.0 / getattr(cfg_, "steps_per_charge", 1500.0)) if cfg_ else 1.0 / 1500.0
    floor = getattr(cfg_, "floor", 0.10) if cfg_ else 0.10
    risk = 0
    for a in env.agents:
        lvl = bat.level.get(a.id, 1.0)
        if lvl <= 0.02:
            continue                      # already counted as dead
        c = bat.nearest_charger(a)
        trip = (abs(c[0] - a.x) + abs(c[1] - a.y)) * drain * 1.2 if c else 0.0
        if lvl - trip < 0.02:
            risk += 2                     # committed to death: near-full penalty
        elif lvl - trip < floor * 0.5:
            risk += 1                     # deep in the reserve with a long walk home
    return risk

_KNOB_MOVES = {"P": ("P+", "P-"), "th": ("th+", "th-"), "cap": ("cap+", "cap-"),
               "alpha": ("a+", "a-"), "depth": ("d+", "d-"),
               "urgw": ("u+", "u-"), "hyst": ("h+", "h-")}


def _context_prior(env):
    """CONTEXT PRIOR (USER 2026-08-16): a new warehouse starts its tuning where similar
    tested warehouses ended up -- a similarity-weighted blend of neighbours' knob-move
    frequencies from the campaign replay. Returns {knob: freq} or None."""
    import json as _json
    import math as _math
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "results", "context_prior.json")
    if not os.path.exists(path):
        return None
    try:
        prior = _json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if not prior:
        return None
    goals = set(env.goals)
    slots = sum(1 for (y, x) in env.action_id_to_coords_map.values() if (x, y) not in goals)
    dual = 1 if getattr(env, "highway_lanes", 1) >= 2 else 0
    from wwm_sim.warehouse import AgentType as _AT
    agvs = sum(1 for a in env.agents if a.type == _AT.AGV)
    pks = len(env.agents) - agvs
    SLOT_BY_SIZE = [36, 72, 120, 180, 336]
    scored = []
    for cfg, v in prior.items():
        f = v["features"]
        ref_slots = SLOT_BY_SIZE[f["size"]] * (1.7 if f["dual"] else 1.0)
        d = (abs(_math.log(max(1, slots)) - _math.log(max(1, ref_slots))) * 4.0
             + (0 if dual == f["dual"] else 3.0)
             + abs(agvs - f["agvs"]) * 0.3 + abs(pks - f["pickers"]) * 0.3)
        scored.append((d, v))
    scored.sort(key=lambda x: x[0])
    top = scored[:3]
    wsum = sum(1.0 / (1.0 + d) for d, _ in top)
    blend = {}
    for k in _KNOB_MOVES:
        blend[k] = sum((1.0 / (1.0 + d)) * v["freq"].get(k, 0.0) for d, v in top) / wsum
    return blend


_MPC_MOVES = ("stay", "P+", "P-", "th+", "th-", "cap-", "cap+",
              "a+", "a-", "d+", "d-", "u+", "u-", "h+", "h-")
_MPC_DEFAULT = (1.5, 0.40, 2, 7.0, 5, 0.0, 20)  # P, theta, cap, ALPHA, DEPTH, URG_W, hyst


def _mpc_apply_move(cur, mv):
    P, th, cap, al, dp, ur, hy = cur
    return {
        "stay": cur,
        "P+":   (min(3.0, P + 0.3), th, cap, al, dp, ur, hy),
        "P-":   (max(1.0, P - 0.2), th, cap, al, dp, ur, hy),
        "th+":  (P, min(0.6, th + 0.10), cap, al, dp, ur, hy),
        "th-":  (P, max(0.10, th - 0.07), cap, al, dp, ur, hy),
        "cap-": (P, th, max(1, cap - 1), al, dp, ur, hy),
        "cap+": (P, th, cap + 1, al, dp, ur, hy),
        "a+":   (P, th, cap, min(15.0, al + 2.0), dp, ur, hy),
        "a-":   (P, th, cap, max(1.0, al - 2.0), dp, ur, hy),
        "d+":   (P, th, cap, al, min(8, dp + 1), ur, hy),
        "d-":   (P, th, cap, al, max(0, dp - 1), ur, hy),
        "u+":   (P, th, cap, al, dp, min(12.0, ur + 2.0), hy),
        "u-":   (P, th, cap, al, dp, max(0.0, ur - 2.0), hy),
        "h+":   (P, th, cap, al, dp, ur, min(40, hy + 10)),
        "h-":   (P, th, cap, al, dp, ur, max(0, hy - 10)),
    }[mv]


def _mpc_ucb_pick(stats, k=3, c=25.0):
    import math
    N = sum(n for n, _ in stats.values()) + 1
    scored = []
    for mv in _MPC_MOVES[1:]:
        n, mean = stats[mv]
        bonus = float("inf") if n == 0 else c * math.sqrt(math.log(N) / n)
        scored.append((mean + bonus, mv))
    scored.sort(key=lambda x: -x[0])
    return [mv for _, mv in scored[:k]]


def make_controller(arm, env):
    import congestion_policies as cp
    from wwm_sim.battery import BatteryTracker, BatteryConfig
    from wwm_sim import rollout as ro
    from sim_priority import Mission, MissionType

    C = cp._SqWidePkRateAdaptive
    if arm == "nobat":
        return C(env), None

    # COMPRESSION (user 2026-08-13: "we may need to make compression less"): 300 = battery dies
    # inside one episode (70x harsher than the Robotnik ~21,600 anchor); 1500 = battery lasts ~3
    # episodes -- the lightest compression that still exercises charging within a run. Full realism
    # (21,600) cannot bind inside 500 steps (~2.3% drain) and belongs to a day-scale experiment.
    spc = float(os.environ.get("M3SPC", "0")) or (1500.0 if arm == "m3lite" else 300.0)
    cfg = BatteryConfig(steps_per_charge=spc)

    class _BatteryChampion(C):
        GO_CHARGE = 0.35           # stage0 only
        FULL = 0.95                # stage0 only
        BAT_PESSIMISM = 1.5 if arm == "m3" else 1.2   # heavier compression -> more pessimism

        def __init__(self, env_):
            super().__init__(env_)
            self.battery = BatteryTracker(env_, cfg)
            # tell env-level slot_divert that charger cells are not drop slots
            env_.charger_keepout = set(self.battery.chargers)
            self._charge_target = {}          # robot id -> release level (m3 charge-to-need)
            self.n_deleted = 0                # fires-check: candidates deleted for battery
            self.n_charge_trips = 0
            # LEARNED THRESHOLDS (USER 2026-08-14: "robots should learn when to hit the
            # charger -- a threshold that robots should test"). The fixed 1.5x pessimism and
            # the pickers' 0.40 are hand-set guesses; strandings are mispricing events the
            # robots can measure themselves. m3learn: each charge-trip compares REALIZED energy
            # spent (level at dispatch minus level at plug) against the clean Manhattan
            # estimate; AGV pessimism = running mean + 2 sd of that ratio (EMA, clamp [1,3]),
            # and any floor breach away from a plug ratchets it +0.15 (pickers: theta +0.05).
            # INTEGRATED MPC (USER 2026-08-16 "integrate when done": campaign verdict 5/8 cells
            # MPC ADOPTED, 0 negative, pooled z=+4.8 -- results/mpc_status.md). arm "m3mpc":
            # every 50 steps fork (env, self), roll UCB-chosen candidate settings 100 steps on
            # the true physics, adopt the winner. OFF on small maps (<100 storage cells): the
            # small-4-3 cell measured flat with stranded 0 -- nothing there to tune.
            self._mpc = (arm in ("m3mpc", "m3mpccold", "m3mpcprior")
                         and len(env_.action_id_to_coords_map) >= 100)
            if arm in ("m3mpc", "m3mpccold", "m3mpcprior"):
                self.BAT_PESSIMISM = 1.5      # m3's shipped constants are the starting point
                self._pk_override = 0.40
                self._cap_override = 2
                self._mpc_stats = {m: [0, 0.0] for m in _MPC_MOVES}
                # AUDITIONED AND CUT (2026-08-17, LOO A/B on large-8-6, 72 seeds): warm-start
                # 1053.40 vs cold 1054.31 (-0.1%) -- the UCB covers all 14 moves within a day,
                # so neighbours' knob priors save a few early forks and no value. Opt-in arm
                # "m3mpcprior" keeps the machinery honest; the champion starts cold.
                _pr = _context_prior(env_) if arm == "m3mpcprior" else None
                if _pr:
                    # pseudo-observations: every move gets one phantom trial so no move keeps
                    # an infinite first-try bonus; knobs that similar warehouses actually used
                    # start with a positive mean and get simulated first.
                    for _k, _mvs in _KNOB_MOVES.items():
                        for _mv in _mvs:
                            self._mpc_stats[_mv] = [1, 40.0 * _pr.get(_k, 0.0)]
            self._learn = (arm == "m3learn")
            if self._learn:
                self.BAT_PESSIMISM = 1.2      # instance attr shadows the class constant
                self._pk_theta = 0.25         # pickers start LEAN; learning must earn the rest
                self._rat_m, self._rat_v, self._rat_n = 1.0, 0.0, 0
                self._trip_obs = {}           # robot id -> (level at dispatch, predicted cost)
                self._breach = set()

        # NOTE: the step-4 battery filter is BUILT INTO the funnel (sim_priority ~line 608) and
        # activates the moment `self.battery` exists -- attaching the tracker IS the wiring. The
        # first draft duplicated it in _true_score (the joint-planner path) and counted only that
        # copy, reading deleted=0 while the real filter fired uncounted. Real count: self._bat_del.

        def _energy_need(self, a, sh):
            """Round-trip energy for task sh from robot a, incl. reserve from the end slot."""
            res = ro.rollout_task(self.env, sh, [a], [a],
                                  battery_cfg=cfg, battery=1.0,
                                  chargers=list(self.battery.chargers))
            return res["battery_used"] + (1.0 - res["battery_margin"] - res["battery_used"])

        def _manage_charging(self):
            bat, aa = self.battery, self.assigned_agvs
            ap = self.assigned_pickers
            env_ = self.env
            # release: stage0 at FULL; m3 at charge-to-need target or when a task became coverable
            for r, d in ((True, aa), (False, ap)):
                for rob in list(d):
                    if d[rob].mission_type != MissionType.CHARGING:
                        continue
                    lvl = bat.level.get(rob.id, 1.0)
                    if arm == "stage0":
                        if bat.is_full(rob, self.FULL):
                            d.pop(rob)
                    else:
                        tgt = self._charge_target.get(rob.id, self.FULL)
                        if lvl >= tgt:
                            d.pop(rob)
                            self._charge_target.pop(rob.id, None)
            # dispatch to chargers
            if arm == "stage0":
                for a in self.agvs:
                    if a not in aa and not a.carrying_shelf and bat.needs_charge(a, self.GO_CHARGE):
                        self._send(a, aa, self.FULL)
                for p in self.pickers:
                    if p not in ap and bat.needs_charge(p, self.GO_CHARGE):
                        self._send(p, ap, self.FULL)
                return
            # ---- m3: charge exactly when the feasible set is empty ----
            # CONCURRENCY CAP (traced, seeds 82/125: the frozen carriers were END-STAGE of a death
            # spiral that began with 4 of 8 AGVs charging simultaneously in the opening window --
            # deliveries lagged, orders piled onto hot pods, station dwell (6 x items) exploded to
            # 100-180 steps, and the day died with ~1 delivery. "Best TIME to charge" includes not
            # all at once: at most 2 planned charge trips concurrently, lowest level first;
            # emergencies (cannot even reach a charger) are always allowed through.
            _CAP = int(getattr(self, "_cap_override", 2))   # MPC-tunable
            n_charging = sum(1 for m in aa.values()
                             if m.mission_type == MissionType.CHARGING)
            pool = [sh for sh in env_.request_queue
                    if sh.id not in self.assigned_items.values()]
            for a in sorted(self.agvs, key=lambda r: bat.level.get(r.id, 1.0)):
                if a in aa or a.carrying_shelf:
                    continue
                lvl = bat.level.get(a.id, 1.0)
                c0 = bat.nearest_charger(a)
                trip0 = ((abs(c0[0] - a.x) + abs(c0[1] - a.y)) * cfg.drive_drain) if c0 else 0.0
                emergency = lvl < cfg.floor + 2.0 * trip0
                if n_charging >= _CAP and not emergency:
                    continue
                if not pool:
                    # idle on empty queue: opportunistic top-up (released as soon as work appears
                    # and is coverable -- the release check above uses the stored target)
                    if lvl < 0.90:
                        self._send(a, aa, 0.95)
                        n_charging += 1
                    continue
                # cheapest-energy candidate defines the NEED; if the robot can cover ANY task it
                # will simply be assigned one by the funnel and we do nothing here
                needs = sorted(self._energy_need(a, sh) for sh in pool[:12])
                if not needs:
                    continue
                _bp = self.BAT_PESSIMISM
                c = self.battery.nearest_charger(a)
                trip = ((abs(c[0] - a.x) + abs(c[1] - a.y)) * cfg.drive_drain * _bp) if c else 0.0
                # the trip TO the charger costs energy too -- measured: most strandings were robots
                # dispatched only when the feasible set emptied, dying metres from the plug
                if lvl >= needs[0] * _bp + cfg.floor + trip:
                    continue                       # something is feasible -> the funnel handles it
                target = min(1.0, needs[0] * _bp + cfg.floor + MARGIN)
                self._send(a, aa, target)
                n_charging += 1
            # EMERGENCY POD-DROP: a carrying AGV whose level cannot cover reserve + the trip to a
            # charger has no legal future -- convert its mission to RETURNING at the nearest free
            # slot (free_pod_return lets it drop unaided), after which the normal trigger charges it.
            from wwm_sim.warehouse import CollisionLayers as _CL
            # FIRE ONCE PER CARRY (traced, seed 91 on the bay map): below the trigger level the
            # drop re-fired EVERY tick, wiping path/busy each time -- the router replanned forever
            # and the robot never executed a single step (livelock at lvl~0.08, 100 ticks
            # motionless with a valid 14-step path). Masked before dedicated bays because the
            # nearest bare slot was usually adjacent; with bays it can be 14 cells away.
            _emg = self._emg_dropped = getattr(self, "_emg_dropped", set())
            for a in self.agvs:
                if a.carrying_shelf is None:
                    _emg.discard(a.id)
            for a in self.agvs:
                if a.carrying_shelf is None or a not in aa:
                    continue
                if aa[a].mission_type == MissionType.CHARGING or a.id in _emg:
                    continue
                lvl = bat.level.get(a.id, 1.0)
                c = bat.nearest_charger(a)
                trip = ((abs(c[0] - a.x) + abs(c[1] - a.y)) * cfg.drive_drain) if c else 0.0
                if lvl >= cfg.floor + 2.0 * trip:
                    continue
                best = self._nearest_free_slot(a)
                if best is not None:
                    loc = self.coords_to_id.get((best[1], best[0]))
                    if loc is not None:
                        aa[a] = Mission(MissionType.RETURNING, loc, best[0], best[1], self.timestep)
                        # path=[] with busy=True routes into the TOGGLE_LOAD branch -> the robot
                        # tries to unload WHERE IT STANDS, mid-lane, silently failing forever
                        # (measured: 18/18 frozen carriers were exactly this). busy=False makes the
                        # not-busy branch REPATH to the new slot instead.
                        a.path = []
                        a.busy = False
                        _emg.add(a.id)
            # ZOMBIE REPAIR (traced, seeds 49-76: 7/12 residual frozen): chargers sit on shelf
            # cells, and warehouse.py:1040 makes ANY busy AGV whose path empties request
            # TOGGLE_LOAD -- so a robot ARRIVING to charge lifted the pod stored on the charger.
            # Once released it was a CARRYING robot with NO mission: assigners only feed empty
            # robots, so it stood on the plug forever, and the now-bare charger cell doubled as a
            # fake "free slot" that lured other carriers into walls (seeds 93/96/121). The arrival
            # toggle is suppressed in act(); this repairs any orphan carrier that still slips
            # through: give it a RETURNING mission to the nearest legal free slot.
            # NARROW to the traced signature (carrying + missionless + parked ON a charger, idle):
            # "carrying and not in aa" ALONE also matches the legitimate one-tick window between a
            # PICKING completion and the next assignment -- repairing that hijacked every freshly
            # loaded AGV into returning its own pod (measured: value 0.00 across 144 seeds).
            _chg = set(bat.chargers)
            for a in self.agvs:
                if (a.carrying_shelf is not None and a not in aa
                        and (a.x, a.y) in _chg
                        and not getattr(a, "busy", False)
                        and not getattr(a, "path", None)):
                    best = self._nearest_free_slot(a)
                    if best is not None:
                        loc = self.coords_to_id.get((best[1], best[0]))
                        if loc is not None:
                            aa[a] = Mission(MissionType.RETURNING, loc, best[0], best[1],
                                            self.timestep)
                            a.path = []
                            a.busy = False
            # AT-DEST DEAD-ZONE, generic (traced, seeds 125/126): carrying, ON the mission cell,
            # path=[] and busy=False -- the not-busy branch can't path own->own and the toggle
            # branch needs busy, so nothing ever fires. Shelf on the cell -> the drop is illegal,
            # reassign; shelf-free -> busy=True routes into the TOGGLE_LOAD branch and it drops
            # (or, for DELIVERING at a station, hands over). Never nudge CHARGING (the toggle IS
            # the zombie bug).
            # PERSISTENCE-GATED (>=12 ticks in the dead state): a PICKING robot stands on its pod
            # cell at EVERY pickup and a DELIVERING robot holds at its station during service --
            # nudging those transients toggled freshly-loaded pods back DOWN (measured: value 0.00,
            # carriers 5 -> 0 by t=50, all missions pinned at PICKING). Only RETURNING/DELIVERING
            # carriers motionless in the dead state for 12 straight ticks are real dead-zones.
            _dz = self._deadzone_ticks = getattr(self, "_deadzone_ticks", {})
            _live = set()
            for a in list(aa):
                m = aa[a]
                if (a.carrying_shelf is None
                        or m.mission_type not in (MissionType.RETURNING, MissionType.DELIVERING)
                        or (m.location_x, m.location_y) != (a.x, a.y)
                        or getattr(a, "path", None) or getattr(a, "busy", False)):
                    continue
                _live.add(a.id)
                _dz[a.id] = _dz.get(a.id, 0) + 1
                if _dz[a.id] < 12:
                    continue
                if m.mission_type == MissionType.RETURNING and env_.grid[_CL.SHELVES, a.y, a.x]:
                    best = self._nearest_free_slot(a)
                    if best is not None and best != (a.x, a.y):
                        loc = self.coords_to_id.get((best[1], best[0]))
                        if loc is not None:
                            aa[a] = Mission(MissionType.RETURNING, loc, best[0], best[1],
                                            self.timestep)
                            a.path = []
                            a.busy = False
                            _dz.pop(a.id, None)
                else:
                    a.busy = True
                    _dz.pop(a.id, None)
            for _id in list(_dz):
                if _id not in _live:
                    _dz.pop(_id)
            # DOCK-STARVATION RELIEF (traced, seed 126 endgame): a delivered carrier holds at its
            # station (sim_dashboard's dock-flip `continue`s) when every bare slot is claimed or
            # occupied -- and at full saturation the LAST bare slot in the warehouse was a charger
            # cell occupied+claimed by a charging robot. If a carrier is dock-held and one of OUR
            # robots (charging or idle) squats a bare storage cell, evict the highest-level such
            # squatter to a DIFFERENT charger; its cell becomes the drop slot within a tick or two.
            _dock_held = any(
                rob.carrying_shelf is not None
                and m.mission_type == MissionType.DELIVERING
                and (rob.x, rob.y) == (m.location_x, m.location_y)
                for rob, m in aa.items())
            if _dock_held:
                _goalset2 = {tuple(g) for g in env_.goals}
                cands = []
                for a in self.agvs:
                    if a.carrying_shelf is not None:
                        continue
                    m = aa.get(a)
                    if m is not None and m.mission_type != MissionType.CHARGING:
                        continue
                    if (m is not None
                            and (a.x, a.y) != (m.location_x, m.location_y)):
                        continue          # charging but still en route -- not a squatter
                    if (a.x, a.y) in _goalset2:
                        continue
                    if self.coords_to_id.get((a.y, a.x)) is None:
                        continue          # not a storage cell
                    if env_.grid[_CL.SHELVES, a.y, a.x]:
                        continue          # cell not bare -- no slot to liberate
                    lvl = bat.level.get(a.id, 1.0)
                    c = bat.nearest_charger(a)
                    trip = ((abs(c[0] - a.x) + abs(c[1] - a.y)) * cfg.drive_drain) if c else 0.0
                    if lvl < cfg.floor + 2.0 * trip:
                        continue          # emergency clinger -- moving it strands it
                    cands.append((lvl, a))
                if cands:
                    _, ev = max(cands, key=lambda x: x[0])
                    aa.pop(ev, None)
                    self._charge_target.pop(ev.id, None)
                    self._send(ev, aa, min(0.95, bat.level.get(ev.id, 1.0) + 0.05))
            # YIELD THE SLOT (traced, seeds 93/121/126): an IDLE missionless AGV parked exactly on
            # a carrier's drop/dest cell is furniture the clash machinery cannot route around --
            # the destination itself is occupied. Send the squatter off to charge (the one always-
            # harmless macro errand); _send picks a FREE charger, so it necessarily moves away.
            _dests = {(m.location_x, m.location_y)
                      for rob, m in aa.items()
                      if rob.carrying_shelf is not None
                      and m.mission_type in (MissionType.RETURNING, MissionType.DELIVERING)}
            for a in self.agvs:
                if a in aa or a.carrying_shelf is not None or getattr(a, "busy", False):
                    continue
                if (a.x, a.y) in _dests:
                    self._send(a, aa, min(0.95, bat.level.get(a.id, 1.0) + 0.05))
            # pickers keep the simple threshold rule (no round-trips to price); at heavy
            # compression the threshold must lead the drain by more
            _pk_ov = getattr(self, "_pk_override", None)    # MPC-tunable
            _pk_go = (_pk_ov if _pk_ov is not None
                      else (self._pk_theta if getattr(self, "_learn", False)
                            else (0.40 if arm == "m3" else 0.25)))
            for p in self.pickers:
                lvl = bat.level.get(p.id, 1.0)
                if p not in ap and bat.needs_charge(p, _pk_go):
                    self._send(p, ap, 0.90)
                elif (p in ap and ap[p].mission_type != MissionType.CHARGING
                        and lvl < 0.5 * _pk_go):
                    # PREEMPT (stranding forensics 2026-08-16: ALL 17 hard-dead robots were
                    # PICKERS, 11 mid-PICKING -- the idle-only charge rule never fires on busy
                    # days, so a busy picker sails through its threshold and works itself to
                    # death metres from a bay. Deep under threshold: drop the errand and charge;
                    # picker-reelect covers the abandoned rendezvous.)
                    ap.pop(p, None)
                    if hasattr(self, "picker_routes"):
                        self.picker_routes.pop(p, None)
                        self.picker_routes.pop(p.id, None)
                    p.path = []
                    p.busy = False
                    # charge-to-NEED for pickers too: 0.90 was a ~315-step outage at this
                    # compression (most of the remaining day); theta+0.10 covers the day
                    self._send(p, ap, min(0.90, _pk_go + 0.10))

        def _nearest_free_slot(self, a):
            """Nearest legal drop cell: not a goal, not a CHARGER (never park pods on plugs),
            shelf-free, not occupied by another AGV."""
            from wwm_sim.warehouse import CollisionLayers as _CL
            env_ = self.env
            _goalset = {tuple(g) for g in env_.goals}
            _chg = set(self.battery.chargers)
            best, bd = None, 1 << 30
            for (_yy, _xx) in env_.action_id_to_coords_map.values():
                if ((_xx, _yy) in _goalset or (_xx, _yy) in _chg
                        or env_.grid[_CL.SHELVES, _yy, _xx]):
                    continue
                if env_.grid[_CL.AGVS, _yy, _xx] and (_xx, _yy) != (a.x, a.y):
                    continue
                d_ = abs(a.x - _xx) + abs(a.y - _yy)
                if d_ < bd:
                    best, bd = (_xx, _yy), d_
            return best

        def _send(self, robot, d, target):
            # CHARGER CONTENTION (measured: 3578 trips onto 8 contention-blind chargers -> robots
            # drain to zero QUEUEING at an occupied charger). Pick the nearest charger that is
            # neither physically occupied nor already the target of another CHARGING mission.
            from wwm_sim.warehouse import CollisionLayers as _CL
            env_ = self.env
            claimed = {(m.location_x, m.location_y)
                       for dd in (self.assigned_agvs, self.assigned_pickers)
                       for m in dd.values() if m.mission_type == MissionType.CHARGING}
            cands = []
            for (cx, cy) in self.battery.chargers:
                if (cx, cy) in claimed:
                    continue
                occ = env_.grid[_CL.AGVS, cy, cx] or env_.grid[_CL.PICKERS, cy, cx]
                if occ:
                    continue
                cands.append((abs(cx - robot.x) + abs(cy - robot.y), (cx, cy)))
            c = min(cands)[1] if cands else self.battery.nearest_charger(robot)
            if c is None:
                return
            loc_id = self.coords_to_id.get((c[1], c[0]))
            if loc_id is None:
                return
            d[robot] = Mission(MissionType.CHARGING, loc_id, c[0], c[1], self.timestep)
            self._charge_target[robot.id] = target
            self.n_charge_trips += 1
            if getattr(self, "_learn", False):
                pred = (abs(c[0] - robot.x) + abs(c[1] - robot.y)) * cfg.drive_drain
                self._trip_obs[robot.id] = (self.battery.level.get(robot.id, 1.0), pred)

        def _learn_update(self):
            """Close the loop on finished charge trips + ratchet on floor breaches."""
            bat = self.battery
            for d in (self.assigned_agvs, self.assigned_pickers):
                for rob, m in d.items():
                    if m.mission_type != MissionType.CHARGING:
                        continue
                    if (rob.x, rob.y) != (m.location_x, m.location_y):
                        continue
                    ob = self._trip_obs.pop(rob.id, None)
                    if ob is None:
                        continue
                    lvl0, pred = ob
                    if pred < 3.0 * cfg.drive_drain:
                        continue          # sub-3-step trips are all noise
                    realized = max(0.0, lvl0 - bat.level.get(rob.id, 1.0))
                    r = min(realized / pred, 6.0)
                    self._rat_n += 1
                    a_ = 0.1
                    self._rat_m += a_ * (r - self._rat_m)
                    self._rat_v += a_ * ((r - self._rat_m) ** 2 - self._rat_v)
                    self.BAT_PESSIMISM = min(3.0, max(
                        1.0, self._rat_m + 2.0 * self._rat_v ** 0.5))
            chg = bat.chargers
            for rob in self.agents:
                lvl = bat.level.get(rob.id, 1.0)
                if lvl < cfg.floor and (rob.x, rob.y) not in chg:
                    if rob.id not in self._breach:
                        self._breach.add(rob.id)
                        if rob in self.agvs:
                            self.BAT_PESSIMISM = min(3.0, self.BAT_PESSIMISM + 0.15)
                        else:
                            self._pk_theta = min(0.60, self._pk_theta + 0.05)
                elif lvl > cfg.floor + 0.05:
                    self._breach.discard(rob.id)

        def _mpc_setting(self):
            return (self.BAT_PESSIMISM, self._pk_override, int(self._cap_override),
                    float(self.RATE_ALPHA), int(self.SEQ_DEPTH),
                    float(getattr(self, "URG_W_DAYLIST", 0.0)),
                    int(getattr(self.env, "clash_hysteresis", 20)))

        def _mpc_apply(self, s):
            (self.BAT_PESSIMISM, self._pk_override, self._cap_override,
             self.RATE_ALPHA, self.SEQ_DEPTH, self.URG_W_DAYLIST) = s[:6]
            self.env.clash_hysteresis = s[6]

        def _mpc_rollout(self, setting, t0, horizon=100):
            import copy
            env2, c2 = copy.deepcopy((self.env, self))
            # HONEST FORKS (2026-08-23): a deepcopy carries the disturbance RNG state, so an imagined
            # rollout would replay the TRUE future spill spawns -- clairvoyance inside the imagination.
            # Reseed the fork's RNG so imagined futures SAMPLE the spawn process instead of reading it.
            if getattr(env2, "_disturb_rng", None) is not None:
                import numpy as _np
                env2._disturb_rng = _np.random.RandomState(env2._disturb_rng.randint(0, 2**31 - 1))
            c2._in_fork = True                    # forks never replan (no fork-in-fork)
            c2._mpc_apply(setting)
            breach0 = {a.id for a in env2.agents
                       if c2.battery.level.get(a.id, 1.0) < 0.10}
            onv = 0.0
            for h in range(horizon):
                env2.step(c2.act())
                for o in getattr(env2, "fulfilled_this_step", []):
                    if o.deadline is not None and t0 + h + 1 <= o.deadline:
                        onv += o.value
            dead = sum(1 for a in env2.agents
                       if c2.battery.level.get(a.id, 1.0) <= 0.02)
            newb = sum(1 for a in env2.agents
                       if c2.battery.level.get(a.id, 1.0) < 0.10
                       and a.id not in breach0)
            return onv - 100.0 * dead - 20.0 * newb - 50.0 * _battery_risk(c2, env2)

        def _mpc_replan(self):
            cur = self._mpc_setting()
            base = self._mpc_rollout(cur, self.timestep)
            best_s, best = base, cur
            for mv in _mpc_ucb_pick(self._mpc_stats):
                s_ = _mpc_apply_move(cur, mv)
                if s_ == cur:
                    continue
                sc = self._mpc_rollout(s_, self.timestep)
                n, mean = self._mpc_stats[mv]
                self._mpc_stats[mv] = [n + 1, mean + (sc - base - mean) / (n + 1)]
                if sc > best_s:
                    best_s, best = sc, s_
            self._mpc_apply(best)

        def act(self):
            if (getattr(self, "_mpc", False) and not getattr(self, "_in_fork", False)
                    and self.timestep > 0 and self.timestep % 50 == 0):
                self._mpc_replan()
            self.battery.step()
            if getattr(self, "_learn", False):
                self._learn_update()
            # SUPPRESS THE ARRIVAL TOGGLE (root cause of the zombie class): warehouse.py:1040
            # makes any busy AGV with an empty path request TOGGLE_LOAD -- for a CHARGING robot
            # standing on its charger (a shelf cell) that means PICKING UP THE STORED POD. Park
            # it explicitly instead: not busy, no path, and _manage_charging owns its release.
            for a in self.agvs:
                m = self.assigned_agvs.get(a)
                if (m is not None and m.mission_type == MissionType.CHARGING
                        and (a.x, a.y) == (m.location_x, m.location_y)
                        and not getattr(a, "path", None)):
                    a.busy = False
            self._manage_charging()
            actions = super().act()
            # PICKER CHARGE ENFORCEMENT (trace 2026-08-16: the dispatcher/reelect machinery
            # rewrites a preempted picker's CHARGING mission back to PICKING within the same
            # tick -- the dying picker's dest cycled between rendezvous while its level sank).
            # The dispatcher may rewrite the MISSION; it does not get to rewrite the MOVE:
            # any deep-drained picker off a bay has its charge mission restored and its action
            # forced toward the bay, every tick, until it is safe.
            if arm != "stage0":
                _pk_ov = getattr(self, "_pk_override", None)
                _go = (_pk_ov if _pk_ov is not None
                       else (self._pk_theta if getattr(self, "_learn", False)
                             else (0.40 if arm == "m3" else 0.25)))
                chg = self.battery.chargers
                for i, a in enumerate(self.agents):
                    if a not in self.pickers:
                        continue
                    lvl = self.battery.level.get(a.id, 1.0)
                    if lvl >= 0.5 * _go or (a.x, a.y) in chg:
                        continue
                    ap = self.assigned_pickers
                    m = ap.get(a)
                    if m is None or m.mission_type != MissionType.CHARGING:
                        ap.pop(a, None)
                        self._send(a, ap, min(0.90, _go + 0.10))
                        m = ap.get(a)
                    if m is not None and m.mission_type == MissionType.CHARGING:
                        a.path = []
                        a.busy = False
                        actions[i] = m.location_id
            for i, a in enumerate(self.agents):
                m = self.assigned_agvs.get(a) if a in self.assigned_agvs else \
                    self.assigned_pickers.get(a)
                if (m is not None and m.mission_type == MissionType.CHARGING
                        and (a.x, a.y) == (m.location_x, m.location_y)):
                    actions[i] = 0
            for i, a in enumerate(self.agents):
                # gate at HARD-DEAD (2%), not the reserve floor: the floor is a PLANNING reserve.
                # Gating at the floor froze robots 0.002 from the charger -- it manufactured the
                # permanent strandings it existed to prevent.
                lvl = self.battery.level.get(a.id, 1.0)
                if lvl <= 0.02 and (a.x, a.y) not in self.battery.chargers:
                    actions[i] = 0
            return actions

    ctrl = _BatteryChampion(env)
    return ctrl, ctrl


def one(job):
    arm, seed = job
    import gymnasium as gym
    import wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
    from wwm_sim.demand import DemandModel

    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    setup_bays(env)     # ALL arms share the same physical map: 8 shelf-free charging bays
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed,
                     n_windows=162, value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    dm.shelfs = [s for s in dm.shelfs if s.id not in env._charger_bay_ids]
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    env.picker_service_steps = 8
    env.station_service_steps = 6
    env.station_headway = True
    env.station_exit_priority = True
    env.free_pod_return = True
    env.picker_free_move = "committed"
    env.picker_final_step = True
    env.station_side_keepout = True
    env.keepout_top = True
    env.station_divert = True
    env.swap_return_drop = True
    env.picker_swap = True
    env.picker_swap_squat = True
    env.agv_free_move = True
    env.slot_divert = True
    env.picker_reelect = "progress"
    env.clash_sim = True
    env.clash_hysteresis = 20
    ctrl, bc = make_controller(arm, env)
    if bc is not None and os.environ.get("M3STARTLO", "0") == "1":
        # mid-day fleet: per-robot start level U(0.15, 1.0), seeded -- makes the filter and
        # charge-to-need bind at canonical (light) compression
        import numpy as _np
        _rng = _np.random.RandomState(7000 + seed)
        for _a in env.agents:
            bc.battery.level[_a.id] = float(_rng.uniform(0.15, 1.0))
    onv = 0.0
    tail = {}
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            if o.deadline is not None and t + 1 <= o.deadline:
                onv += o.value
        if t > 400:
            for a in env.agents:
                if a.type == AgentType.AGV and a.carrying_shelf is not None:
                    tail.setdefault(a.id, []).append((a.x, a.y))
    frozen = sum(1 for v in tail.values() if len(v) >= 95 and len(set(v)) == 1)
    stranded = (sum(1 for rid, lv in bc.battery.level.items() if lv <= 0.02)
                if bc is not None else 0)   # HARD-DEAD; tracker's floor-breach set is the reserve stat
    deleted = getattr(bc, "_bat_del", 0) if bc is not None else 0
    trips = getattr(bc, "n_charge_trips", 0) if bc is not None else 0
    minlvl = bc.battery.min_level() if bc is not None else 1.0
    pes = float(getattr(bc, "BAT_PESSIMISM", 0.0)) if bc is not None else 0.0
    th = float(getattr(bc, "_pk_theta", 0.0) or 0.0) if bc is not None else 0.0
    return (arm, seed, round(onv, 1), frozen, stranded, deleted, trips, round(minlvl, 3),
            round(pes, 3), round(th, 3))


if __name__ == "__main__":
    with mp.Pool(NPROC) as pool:
        rows = pool.map(one, [(a, s) for a in ARMS for s in SEEDS])
    D = {a: {} for a in ARMS}
    AGG = {a: [0, 0, 0, 0, 1.0] for a in ARMS}   # frozen, stranded, deleted, trips, minlvl
    LRN = {a: [] for a in ARMS}                  # (final pessimism, final picker theta)
    for a, s, v, fr, sd, de, tr, ml, pe, th in rows:
        D[a][s] = v
        AGG[a][0] += fr
        AGG[a][1] += sd
        AGG[a][2] += de
        AGG[a][3] += tr
        AGG[a][4] = min(AGG[a][4], ml)
        if a == "m3learn":
            LRN[a].append((pe, th))
    n_ = len(SEEDS)
    print("M3 BATTERY smoke, %d seeds, COMPRESSED battery (300 driving-steps per charge)\n" % n_)
    print("%-8s %11s %9s %10s %10s %9s %8s %8s" % ("arm", "mean value", "vs nobat",
                                                   "frozen", "STRANDED", "deleted", "trips", "min lvl"))
    for a in ARMS:
        v = [D[a][s] for s in SEEDS]
        base = sum(D.get("nobat", D[ARMS[0]]).values())
        pc = "-" if a == "nobat" else "%+.1f%%" % (100.0 * (sum(v) - base) / base)
        print("%-8s %11.2f %9s %10d %10d %9d %8d %8.3f"
              % (a, sum(v) / n_, pc, AGG[a][0], AGG[a][1], AGG[a][2], AGG[a][3], AGG[a][4]))
    for a in ARMS:
        if LRN.get(a):
            pes = [p for p, _ in LRN[a]]
            ths = [t for _, t in LRN[a]]
            print("\n%s learned end-of-day params over %d episodes: AGV pessimism "
                  "mean %.2f (min %.2f max %.2f, started 1.20) | picker theta mean %.2f "
                  "(max %.2f, started 0.25)"
                  % (a, len(pes), sum(pes) / len(pes), min(pes), max(pes),
                     sum(ths) / len(ths), max(ths)))
