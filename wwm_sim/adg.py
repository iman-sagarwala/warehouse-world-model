"""wwm_sim.adg — Action Dependency Graph execution (Stage-1 start).

The plan's execution layer. Instead of re-planning paths every step (what the env does now
via A*+reroute), the planner commits EXACT routes and execution follows them in a fixed
ORDER at every shared cell. Key property (Hönig et al., MAPF schedule execution): if a robot
runs late, the robots planned to cross AFTER it simply WAIT — no collision, no replanning.
Small lateness is absorbed as waiting; only big/compounding lateness triggers a rethink.

Two ingredients:
  build_adg(routes)   -> the ordering dependencies at shared cells (Type-2 edges): for each
                         cell, robots cross in planned-arrival order; a robot may enter a
                         cell only AFTER its predecessor there has left.
  simulate_adg(...)    -> execute respecting those deps (+ each robot's own path order),
                         with optional injected delays; collisions are 0 by construction.

`routes` = {robot_id: [cell_0, cell_1, ...]}, cell_t = planned (x,y) position at time t.
NOTE: this standalone executor handles crossings/waits; follow-chains and edge-swaps are
assumed absent (the committed routes were planned collision-free). Env integration (drive the
micro-action layer from committed routes) is the next step.
"""
from __future__ import annotations


def build_adg(routes):
    """Return (order, pred):
      order[cell] = robots that pass through `cell`, in planned-arrival order.
      pred[(robot, cell)] = the robot immediately before `robot` at `cell` (or None) — the
                            one that must LEAVE `cell` before `robot` may enter it."""
    first_arrival = {}                       # cell -> list of (t_enter, robot)
    for r, path in routes.items():
        seen = set()
        for t, c in enumerate(path):
            if c not in seen:
                seen.add(c)
                first_arrival.setdefault(c, []).append((t, r))
    order = {c: [r for _, r in sorted(v)] for c, v in first_arrival.items()}
    pred = {}
    for c, robs in order.items():
        for i, r in enumerate(robs):
            pred[(r, c)] = robs[i - 1] if i > 0 else None
    return order, pred


def simulate_adg(routes, pred, delays=None, max_ticks=1000):
    """Execute the committed routes under the ADG. `delays` = {robot: stall_until_tick}
    (the robot cannot move before that tick). Returns a dict:
      traj      {robot: [cells actually visited]}
      collisions int (0 by construction — a correctness check, not a score)
      finish    {robot: tick it reached its route end}
      waits     {robot: steps spent waiting vs its route length}"""
    delays = delays or {}
    idx = {r: 0 for r in routes}
    pos = {r: routes[r][0] for r in routes}
    left_at = {}                             # (robot, cell) -> tick the robot LEFT that cell
    traj = {r: [pos[r]] for r in routes}
    collisions = 0
    finish = {}

    for tick in range(1, max_ticks):
        occupied = {pos[r]: r for r in routes}
        want = {}                            # robot -> next cell it wants to enter
        for r in routes:
            if idx[r] >= len(routes[r]) - 1:
                finish.setdefault(r, tick - 1)
                continue
            if tick < delays.get(r, 0):      # injected stall
                continue
            nxt = routes[r][idx[r] + 1]
            if nxt == pos[r]:                # planned wait-in-place
                want[r] = nxt
                continue
            p = pred.get((r, nxt))           # dependency: predecessor must have LEFT nxt
            dep_ok = (p is None) or ((p, nxt) in left_at)
            if dep_ok and nxt not in occupied:
                want[r] = nxt

        # no two robots into the same cell this tick (they'd have a dependency anyway)
        target_count = {}
        for r, nxt in want.items():
            target_count[nxt] = target_count.get(nxt, 0) + 1
        for r, nxt in want.items():
            if nxt == pos[r]:                # planned wait-in-place: consume the step, stay
                idx[r] += 1
                continue
            if target_count[nxt] > 1:
                collisions += 1              # should never happen
                continue
            left_at[(r, pos[r])] = tick
            pos[r] = nxt
            idx[r] += 1

        for r in routes:
            traj[r].append(pos[r])
        if all(idx[r] >= len(routes[r]) - 1 for r in routes):
            for r in routes:
                finish.setdefault(r, tick)
            break

    for r in routes:
        finish.setdefault(r, max_ticks)
    waits = {r: len(traj[r]) - len(routes[r]) for r in routes}
    return {"traj": traj, "collisions": collisions, "finish": finish, "waits": waits}


def simulate_naive(routes, delays=None, max_ticks=1000):
    """No ADG: each robot blindly follows its route (advance one cell/tick unless stalled),
    ignoring dependencies. Used only to CONTRAST — collisions can and do occur here when a
    delay desynchronises a crossing. Returns {traj, collisions}."""
    delays = delays or {}
    idx = {r: 0 for r in routes}
    pos = {r: routes[r][0] for r in routes}
    traj = {r: [pos[r]] for r in routes}
    collisions = 0
    for tick in range(1, max_ticks):
        for r in routes:
            if idx[r] < len(routes[r]) - 1 and tick >= delays.get(r, 0):
                idx[r] += 1
                pos[r] = routes[r][idx[r]]
        # count same-cell overlaps this tick
        seen = {}
        for r in routes:
            if pos[r] in seen:
                collisions += 1
            seen[pos[r]] = r
        for r in routes:
            traj[r].append(pos[r])
        if all(idx[r] >= len(routes[r]) - 1 for r in routes):
            break
    return {"traj": traj, "collisions": collisions}
