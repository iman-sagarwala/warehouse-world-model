"""wwm_sim.battery — battery rulebook (Stage 0).

A KNOWN-RULE energy model layered on the wwm_sim substrate. This is plain,
deterministic physics (drain = rate x steps; charge = rate x steps), so the
rollout engine can replay these SAME functions on *believed* state later — that
shared rulebook is what makes rollout predictions exact.

Grounding (real AMR specs; see docs/NOTES.md for the full trail)
---------------------------------------------------------------
Platform: Robotnik. TA-RWARE's two robot roles map onto one Robotnik platform:
  * AGV  (carrier)  -> RB-VOGUI  : 48 V x 15 Ah = 720 Wh Li-ion, ~6 h working
                                   runtime (QVIRO; conservative vs Robotnik's
                                   best-case "up to 12 h"), 1.5-2.5 m/s.
  * Picker (loader) -> RB-KAIROS+ : an RB-VOGUI base + a UR arm (UR7e/12e/16e,
                                    7.5-16 kg). The picker is literally the
                                    carrier + an arm, so drive/battery physics
                                    are shared and the ONLY per-type differences
                                    are: AGV pays a carrying penalty, Picker pays
                                    a per-pick penalty (arm work ~ m*g*h).

Realistic runtime (~6 h at ~1 step/s ~= 21,600 driving-steps per charge) is far
larger than a 500-step episode, so battery would never bind. We therefore
COMPRESS (option b) via `steps_per_charge`, keeping the physical ratios intact.
Compression is a clean uniform scaling of an exactly-computed quantity, so it
costs no model accuracy; it only makes battery a meaningful constraint within an
episode. Every constant below is PROVISIONAL and tunable.
"""
from __future__ import annotations

from dataclasses import dataclass

from wwm_sim.warehouse import AgentType


def default_chargers(env, n: int = 8):
    """Dedicated charger cells as a set of (x, y), spread across the map and reachable
    by BOTH robot types. The goals sit on the bottom row that Pickers are barred from,
    so goals cannot serve as picker chargers; shelf-cells CAN (Pickers reach all 240 of
    them for loading). We therefore designate a spread of shelf-cell action-targets as
    charging bays — deliberate charge trips, distinct from delivery docks.

    If the harness has already dedicated bays via `env._charger_bays` (shelf stripped,
    demand filtered — USER RULE 2026-08-14: charger cells realistically have no shelf),
    those are the chargers."""
    bays = getattr(env, "_charger_bays", None)
    if bays:
        return set(bays)
    goals = set(env.goals)  # (x, y)
    cells = sorted((x, y) for (y, x) in env.action_id_to_coords_map.values()
                   if (x, y) not in goals)
    if not cells:
        return set(goals)
    step = max(1, len(cells) // n)
    return set(cells[::step][:n])


@dataclass
class BatteryConfig:
    """Tunable, provisional constants. Battery level is a fraction in [0, 1]."""

    # --- primary tunables (Robotnik-anchored, compressed to episode scale) ---
    steps_per_charge: float = 300.0  # driving-steps a full battery lasts (realistic ~21,600; compressed here)
    carrying_penalty: float = 0.5    # AGV: extra drain while carrying, as a fraction of drive drain
    pick_penalty_steps: float = 0.3  # Picker: cost per pick, in driving-step equivalents (UR-arm m*g*h est.)
    idle_fraction: float = 0.25      # idle drain as a fraction of drive drain (standby electronics)
    charge_fraction: float = 0.30    # full recharge takes this FRACTION of full-discharge time (Robotnik ~1-2 h charge vs ~6 h run). Defined relative to steps_per_charge so the charge:discharge RATIO is preserved under compression.
    floor: float = 0.10              # battery-floor hard constraint (fraction); at/below this away from a charger = stranded
    start_level: float = 1.0

    # --- derived per-step deltas (fractions of a full battery) ---
    @property
    def drive_drain(self) -> float:
        return 1.0 / self.steps_per_charge

    @property
    def idle_drain(self) -> float:
        return self.idle_fraction * self.drive_drain

    @property
    def carry_extra(self) -> float:
        return self.carrying_penalty * self.drive_drain

    @property
    def pick_cost(self) -> float:
        return self.pick_penalty_steps * self.drive_drain

    @property
    def charge_steps(self) -> float:
        # Scales WITH steps_per_charge so charge:discharge stays fixed under compression.
        return self.charge_fraction * self.steps_per_charge

    @property
    def charge_gain(self) -> float:
        return 1.0 / self.charge_steps


class BatteryTracker:
    """Tracks per-robot battery over a run by observing the env each step.

    Additive layer: it reads what each robot did (moved / carried / picked / sat
    on a charger) and applies the BatteryConfig rules. It does NOT yet gate
    movement (a flat robot isn't forced to stop) — that is a planner-level
    integration for when Part A exists. For now it exposes levels + a `stranded`
    set so the battery-floor hard constraint is observable.
    """

    def __init__(self, env, config: BatteryConfig | None = None, charger_locations=None):
        self.env = env
        self.cfg = config or BatteryConfig()
        # Dedicated charger cells reachable by BOTH robot types (spread of shelf-cells;
        # see default_chargers). Goals can't serve pickers (bottom row is barred to them),
        # so we no longer default to goals — both AGVs and Pickers can now recharge.
        self.chargers = (set(charger_locations) if charger_locations is not None
                         else default_chargers(env))
        self.reset()

    def reset(self) -> None:
        self.level = {a.id: self.cfg.start_level for a in self.env.agents}
        self.stranded: set = set()
        self.picks_charged = 0
        self.t = 0
        self.history: list = []  # (t, {id: level})
        self._pos = {a.id: (a.x, a.y) for a in self.env.agents}
        self._carrying = {a.id: bool(a.carrying_shelf) for a in self.env.agents}

    def _at_charger(self, a) -> bool:
        return (a.x, a.y) in self.chargers

    def step(self) -> None:
        cfg = self.cfg
        agents = self.env.agents
        pickers = [a for a in agents if a.type == AgentType.PICKER]

        # 1) drive / idle / carry / charge, per agent
        for a in agents:
            if self._at_charger(a):
                self.level[a.id] += cfg.charge_gain
            else:
                moved = (a.x, a.y) != self._pos[a.id]
                if moved:
                    self.level[a.id] -= cfg.drive_drain
                    if a.type == AgentType.AGV and a.carrying_shelf:
                        self.level[a.id] -= cfg.carry_extra
                else:
                    self.level[a.id] -= cfg.idle_drain

        # 2) pick events: an AGV going not-carrying -> carrying means a shelf was
        #    just loaded; charge the pick cost to the nearest picker (the helper).
        for a in agents:
            if a.type == AgentType.AGV:
                now = bool(a.carrying_shelf)
                if now and not self._carrying.get(a.id, False) and pickers:
                    helper = min(pickers, key=lambda p: abs(p.x - a.x) + abs(p.y - a.y))
                    self.level[helper.id] -= cfg.pick_cost
                    self.picks_charged += 1
                self._carrying[a.id] = now

        # 3) clamp + strand detection
        for a in agents:
            self.level[a.id] = min(1.0, max(0.0, self.level[a.id]))
            if self.level[a.id] <= cfg.floor and not self._at_charger(a):
                self.stranded.add(a.id)

        # 4) snapshot for next step
        self._pos = {a.id: (a.x, a.y) for a in agents}
        self.t += 1
        self.history.append((self.t, dict(self.level)))

    # --- convenience readouts ---
    def levels_by_type(self):
        agv, pick = [], []
        for a in self.env.agents:
            (agv if a.type == AgentType.AGV else pick).append(self.level[a.id])
        return agv, pick

    def min_level(self) -> float:
        return min(self.level.values()) if self.level else 1.0

    # --- planner-level hooks (charge decisions + movement gating) ---
    def needs_charge(self, robot, threshold: float) -> bool:
        """True if the robot's battery has fallen below the go-charge threshold."""
        return self.level.get(robot.id, 1.0) < threshold

    def is_full(self, robot, threshold: float = 0.95) -> bool:
        """True once a charging robot has topped back up (release threshold)."""
        return self.level.get(robot.id, 1.0) >= threshold

    def is_flat(self, robot) -> bool:
        """At/below the battery floor and NOT on a charger -> stranded, must be gated."""
        return (self.level.get(robot.id, 1.0) <= self.cfg.floor
                and (robot.x, robot.y) not in self.chargers)

    def nearest_charger(self, robot):
        """Closest charger cell (x, y) to the robot, or None if no chargers."""
        if not self.chargers:
            return None
        return min(self.chargers, key=lambda c: abs(c[0] - robot.x) + abs(c[1] - robot.y))
