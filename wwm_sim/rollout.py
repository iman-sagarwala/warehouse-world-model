"""wwm_sim.rollout — analytic (Stage-0) rollout engine.

The plan's shared movement/time/battery model: given a robot->task assignment, estimate
how it will play out. This is the hand-formula precursor to the learned heads, and the
piece the priority controllers need to replace the single GLOBAL `window` (avg task
duration) with a PER-TASK completion estimate — a task whose shelf is far from the docks
genuinely takes longer, so its doomed cutoff should be larger.

Geometry the estimate captures (a full task = fetch -> rendezvous -> carry -> deliver):
  t_fetch  = distance an AGV travels to the shelf
  t_pick   = distance a picker travels to the shelf (they must meet to load)
  rendez   = max(t_fetch, t_pick)          # both must be present
  finish   = rendez + load_time + distance(shelf -> nearest dock)   # = the DELIVERY moment

Distances use Manhattan (cheap, O(1)) — it underestimates the real A* path through the
racks, so the RAW estimate is CALIBRATED against the empirically-observed mean duration
(the controller's adaptive `window`): the per-task window keeps the right AVERAGE (real,
congestion-aware) while varying by task geometry. `per_task_window` returns that.

Battery/margins are included in `rollout_task` for later Part A scoring; completion time
is what the controllers use now.
"""
from __future__ import annotations

from wwm_sim.warehouse import AgentType

DEFAULT_LOAD_TIME = 5     # steps spent loading at the rendezvous (small, tunable)


def _manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


def nearest_dock_dist(env, x, y):
    """Manhattan distance from (x, y) to the closest delivery station."""
    return min(_manhattan(x, y, gx, gy) for (gx, gy) in env.goals)


def nearest_dock(env, x, y):
    """The dock CELL the AGV would actually deliver to. Manhattan is exact here (AGVs drive under
    shelves, so the routing graph is obstacle-free -- verified 60/60 shelves), and it matches the
    controller's real choice 32/32.

    STATION LOAD BALANCING (2026-08-07, opt-in `env.balance_stations`).
    Plain nearest-dock treats stations as interchangeable and never spreads load, so every AGV in a
    region converges on the SAME cell. Diagnosed on seed 1 @ 8x6: FOUR carrying AGVs all had mission
    location (17,24) -- one station -- and queued nose-to-tail in a 1-cell lane until the episode ended
    with all 14 robots frozen and 39 orders undelivered. That is not deadlock and no routing fix
    reaches it: the robots were legitimately routed to a destination the assignment layer chose badly.
    Invisible with the stock 10-20 stations; fatal once station count was cut to the throughput-balanced
    3. Real facilities queue-balance across pick stations for exactly this reason.
    With the flag, distance is penalised by how many AGVs are already heading to that dock, so a
    slightly-farther free station beats a near one with a queue."""
    if getattr(env, "balance_stations", False):
        w = float(getattr(env, "station_queue_penalty", 6.0))
        load = {}
        for a in env.agents:
            if getattr(a, "carrying_shelf", None) is not None and getattr(a, "path", None):
                tgt = tuple(a.path[-1])
                load[tgt] = load.get(tgt, 0) + 1
        return min(env.goals,
                   key=lambda g: _manhattan(x, y, g[0], g[1]) + w * load.get((g[0], g[1]), 0))
    return min(env.goals, key=lambda g: _manhattan(x, y, g[0], g[1]))


def nearest_empty_storage(env, x, y):
    """The EMPTY storage slot nearest (x, y) -- where the AGV actually ends up after returning the
    shelf, and therefore where charger-reachability should be measured from. The controller picks
    exactly this (nearest empty slot by path, sim_dashboard). Measured ~16 steps from the dock, so
    using the dock instead was a real approximation. Cached per step: the empty set changes slowly."""
    from wwm_sim.warehouse import CollisionLayers
    step = getattr(env, "_cur_steps", 0)
    cache = getattr(env, "_empty_slot_cache", None)
    if cache is None or cache[0] != step:
        goals = {tuple(g) for g in env.goals}
        slots = [(xx, yy) for (yy, xx) in env.action_id_to_coords_map.values()
                 if (xx, yy) not in goals and env.grid[CollisionLayers.SHELVES, yy, xx] == 0]
        cache = (step, slots)
        env._empty_slot_cache = cache
    slots = cache[1]
    if not slots:
        return (x, y)
    return min(slots, key=lambda s: _manhattan(x, y, s[0], s[1]))


def charger_reserve(chargers, x, y, drive_drain):
    """Energy needed to REACH a charger from (x, y).

    This replaces the fixed battery FLOOR. Holding an arbitrary reserve fraction is the wrong
    constraint: what actually matters is whether the robot can still GET to a charger when the task
    ends. A robot finishing beside a charger needs almost nothing; one finishing far away needs more
    than a flat 10% would have demanded. So the reserve becomes a property of WHERE you end up, not a
    constant."""
    if not chargers:
        return 0.0
    d = min(_manhattan(x, y, cx, cy) for (cx, cy) in chargers)
    return d * drive_drain


def geom_completion(env, shelf, agvs, pickers, load_time=DEFAULT_LOAD_TIME):
    """Raw geometric estimate of steps-from-now to DELIVER `shelf`.

    Uses the nearest candidate AGV and nearest candidate picker (pass the FREE ones for
    a queue task; a specific pair for an in-progress one). Falls back gracefully if a
    list is empty (no free robot of that type -> that leg contributes 0 wait)."""
    sx, sy = shelf.x, shelf.y
    t_fetch = min((_manhattan(a.x, a.y, sx, sy) for a in agvs), default=0)
    t_pick = min((_manhattan(p.x, p.y, sx, sy) for p in pickers), default=0)
    rendez = max(t_fetch, t_pick)
    return rendez + load_time + nearest_dock_dist(env, sx, sy)


def per_task_window(env, queue, agvs, pickers, base_window, load_time=DEFAULT_LOAD_TIME):
    """Per-task completion estimates, calibrated to average `base_window`.

    Returns {shelf.id: est_steps}. est = base_window * geom(task) / mean(geom over queue),
    so the mean matches the empirically-observed window (real + congestion-aware) while
    each task varies by its own fetch/rendezvous/dock geometry. Empty queue -> {}."""
    if not queue:
        return {}
    geo = {s.id: geom_completion(env, s, agvs, pickers, load_time) for s in queue}
    mean_geo = sum(geo.values()) / len(geo)
    if mean_geo <= 0:
        return {sid: base_window for sid in geo}
    return {sid: base_window * g / mean_geo for sid, g in geo.items()}


def free_robots(ctrl):
    """(free AGVs, free pickers) from a controller's assignment bookkeeping."""
    assigned = ctrl.assigned_agvs
    apick = ctrl.assigned_pickers
    agvs = [a for a in ctrl.agvs if a not in assigned and not a.carrying_shelf]
    pickers = [p for p in ctrl.pickers if p not in apick]
    # fall back to ALL robots of a type if none are currently free (still a valid estimate)
    return (agvs or list(ctrl.agvs)), (pickers or list(ctrl.pickers))


UNREACHABLE = 10 ** 6   # partner_eta when nobody can ever meet (case 4, UNSERVICEABLE)


def partner_eta(shelf, now, committed=None, free=None, busy=None):
    """The four rendezvous scenarios (docs/NOTES 2026-07-10). Given the partner robots
    grouped by state, return (eta_from_now, reason):
      1 committed to THIS cell -> now + remaining route (EXACT)          reason 'committed'
      2 none here but FREE partners exist -> AVERAGE free-partner ETA     reason 'free_est'
      3 none free, BUSY partners will FREE UP -> AVERAGE (free_again +    reason 'wait_free'
        travel) over them (return-to-free feeds free_again)
      4 no partner prospect at all -> UNREACHABLE (task unserviceable)    reason 'unserviceable'

    Cases 2 & 3 use the AVERAGE, not the nearest/soonest (min): you do NOT control the
    partner assignment, so you are NOT guaranteed to win the closest one under contention
    (more AGVs than free pickers, or you're not top-priority). `min` is an optimistic
    best-case that hides real waits; the average reflects a TYPICAL partner. The exact
    winner is the joint assignment = Part D (could refine with a contention factor
    competing_AGVs / available_partners).

    `committed` = the partner already assigned to this shelf (or None); `free` = list of
    free partners; `busy` = list of (robot, free_again_step, release_x, release_y)."""
    sx, sy = shelf.x, shelf.y
    if committed is not None:
        remaining = len(getattr(committed, "path", None) or [])
        return remaining, "committed"                                    # case 1
    if free:                                                             # case 2: AVERAGE
        etas = [_manhattan(p.x, p.y, sx, sy) for p in free]
        return sum(etas) / len(etas), "free_est"
    if busy:                                                             # case 3: AVERAGE
        etas = [max(0, fa - now) + _manhattan(rx, ry, sx, sy) for (_r, fa, rx, ry) in busy]
        return sum(etas) / len(etas), "wait_free"
    return UNREACHABLE, "unserviceable"                                  # case 4


def rollout_task(env, shelf, agvs, pickers, now=0, load_time=DEFAULT_LOAD_TIME,
                 battery_cfg=None, battery=None, my_arrival=None,
                 partner_arrival=None, chargers=None):
    """Full analytic rollout of delivering `shelf` from `now`. Returns a dict:
      fetch, partner, rendezvous, my_wait = steps-from-now (my_wait = idle time waiting
                                            for the partner to arrive = the sync-up cost)
      finish, finish_step                 = the DELIVERY moment (steps / absolute)
      deadline_margin                     = shelf.deadline - finish_step (None if no dl)
      free_again                          = when the robot is AVAILABLE again (after the
                                            return leg) -> feeds next-availability + others'
                                            case-3 sync estimates
      battery_used, battery_margin        = optional, if battery_cfg + battery given; used
                                            by the step-4 battery-floor FILTER (delete a
                                            route that would strand). Deciding to CHARGE
                                            first (support-then-task) is Part B/C, not here.
    `my_arrival` overrides the fetch estimate with the real route length; `partner_arrival`
    (steps-from-now, from partner_eta) overrides the nearest-free-picker estimate."""
    sx, sy = shelf.x, shelf.y
    t_fetch = my_arrival if my_arrival is not None else min(
        (_manhattan(a.x, a.y, sx, sy) for a in agvs), default=0)
    t_partner = partner_arrival if partner_arrival is not None else min(
        (_manhattan(p.x, p.y, sx, sy) for p in pickers), default=0)
    rendez = max(t_fetch, t_partner)
    my_wait = max(0, t_partner - t_fetch)              # feature 1: sync-up wait
    dock = nearest_dock_dist(env, sx, sy)
    finish = rendez + load_time + dock
    used = margin = None
    if battery_cfg is not None and battery is not None:
        drive = t_fetch + dock * 2
        used = drive * battery_cfg.drive_drain + dock * battery_cfg.carry_extra + battery_cfg.pick_cost
        if chargers:
            # REACHABILITY reserve: enough charge left, at the END of the task, to get to a charger.
            # End position = the empty storage slot the AGV drops the shelf at (measured ~16 steps
            # from the dock), NOT the dock itself.
            dx, dy = nearest_dock(env, sx, sy)
            ex, ey = nearest_empty_storage(env, dx, dy)
            reserve = charger_reserve(chargers, ex, ey, battery_cfg.drive_drain)
        else:
            reserve = battery_cfg.floor          # legacy fixed floor
        margin = battery - reserve - used
    free_again = finish + dock                          # feature 3: return leg -> free again
    out = {
        "fetch": t_fetch, "partner": t_partner, "rendezvous": rendez, "my_wait": my_wait,
        "finish": finish, "finish_step": now + finish,
        "deadline_margin": (shelf.deadline - (now + finish)) if shelf.deadline is not None else None,
        "free_again": now + free_again,
    }
    if used is not None:
        out["battery_used"] = used
        out["battery_margin"] = margin
    return out


def battery_feasible(res) -> bool:
    """Part A step-4 hard filter: would this plan finish at/above the battery floor?
    True if battery wasn't evaluated (no cfg given) or the margin is non-negative.
    A route that would strand the robot is DELETED, never merely scored badly."""
    m = res.get("battery_margin")
    return m is None or m >= 0.0
