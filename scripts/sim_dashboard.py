"""Side-by-side warehouse dashboard: FIFO heuristic vs. random policy.

Renders BOTH wwm_sim environments in a single window, stepped in lockstep, with:
  * two warehouse grids drawn side by side,
  * a legend explaining every colour/shape,
  * a live task list per policy (which shelf each AGV is fetching + completions),
  * per-robot battery bars (our Stage-0 battery model),
  * a running stats table (collisions, throughput, deadlines).

Runs on `wwm_sim` (our editable simulator) so the battery model is live.
Deadlines do not exist yet (a later rulebook layer), so that row shows "N/A".

The FIFO logic is a step-wise port of the heuristic so we can read out each AGV's
current mission every frame (the vendored loop never exposes per-task state).

Usage
-----
    # Live window (slower = more watchable)
    python scripts/sim_dashboard.py --fps 4 --seed 0

    # Headless: render one composed frame after N steps to a PNG (for checking)
    python scripts/sim_dashboard.py --snapshot out.png --snapshot-step 120
"""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass
from enum import Enum

import numpy as np

import gymnasium as gym
import wwm_sim  # noqa: F401  (registers wwm_sim-* env ids)
from wwm_sim.warehouse import AgentType
from wwm_sim.utils.utils import flatten_list, split_list
from wwm_sim.battery import BatteryConfig, BatteryTracker


# --------------------------------------------------------------------------- #
# Colours (matplotlib 0-1 RGB). Legend is generated from this same table so it
# can never drift from what is actually drawn.
# --------------------------------------------------------------------------- #
C_FLOOR = (1.00, 1.00, 1.00)
C_SHELF = (0.28, 0.24, 0.55)   # dark slate blue - shelf sitting in a rack
C_SHELF_REQ = (0.00, 0.50, 0.50)  # teal - a requested shelf == an open task
C_GOAL = (0.24, 0.24, 0.24)    # dark grey - delivery / pick station
C_AGV = (1.00, 0.55, 0.00)     # orange - AGV not carrying
C_AGV_LOADED = (0.85, 0.10, 0.10)  # red - AGV carrying a shelf
C_PICKER = (0.12, 0.56, 1.00)  # blue - picker (loader)


# --------------------------------------------------------------------------- #
# Step-wise FIFO nearest-agent controller (ported from tarware/heuristic.py)
# --------------------------------------------------------------------------- #
class MissionType(Enum):
    PICKING = 1
    RETURNING = 2
    DELIVERING = 3
    CHARGING = 4


@dataclass
class Mission:
    mission_type: MissionType
    location_id: int
    location_x: int
    location_y: int
    assigned_time: int
    at_location: bool = False


class FIFOController:
    """Reproduces the vendored FIFO heuristic one step at a time."""

    def __init__(self, env):
        self.env = env
        self.location_map = env.action_id_to_coords_map
        self.coords_to_id = {v: k for k, v in env.action_id_to_coords_map.items()}
        non_goal = []
        for id_, coords in env.action_id_to_coords_map.items():
            if (coords[1], coords[0]) not in env.goals:
                non_goal.append(id_)
        self.non_goal_location_ids = np.array(non_goal)

        self.agents = env.agents
        self.agvs = [a for a in env.agents if a.type == AgentType.AGV]
        self.pickers = [a for a in env.agents if a.type == AgentType.PICKER]
        sections = env.rack_groups
        picker_sections = split_list(sections, max(len(self.pickers), 1))
        self.picker_sections = [flatten_list(l) for l in picker_sections]

        self.assigned_agvs: "OrderedDict[object, Mission]" = OrderedDict()
        self.assigned_pickers: "OrderedDict[object, Mission]" = OrderedDict()
        self.assigned_items: "OrderedDict[object, int]" = OrderedDict()
        self.completed: deque = deque(maxlen=12)  # (timestep, shelf_id)
        # --- live task-duration tracking (feeds the adaptive `window`) ---------
        # assign->deliver time for recent tasks, so the doomed-cutoff self-calibrates
        # to the ACTUAL fleet + congestion (8/4 vs 12/8 vs ...) rather than a fixed 83.
        self._assign_step: dict = {}                 # shelf_id -> step first assigned
        self.durations: deque = deque(maxlen=60)     # recent assign->deliver durations
        self.timestep = 0

    def _task_order(self):
        """Order in which unassigned tasks are considered. Base = FIFO (queue order)."""
        return list(self.env.request_queue)

    def _assign_tasks(self):
        """Task-centric assignment: in _task_order(), give each unassigned task to the
        nearest free AGV. Subclasses (Part A) override with a per-robot funnel."""
        env = self.env
        for item in self._task_order():
            if item.id in self.assigned_items.values():
                continue
            available = [a for a in self.agvs if not a.busy and not a.carrying_shelf
                         and a not in self.assigned_agvs]
            if not available:
                continue
            paths = [env.find_path((a.y, a.x), (item.y, item.x), a, care_for_agents=False)
                     for a in available]
            closest = available[int(np.argmin([len(p) for p in paths]))]
            loc_id = self.coords_to_id[(item.y, item.x)]
            self.assigned_agvs[closest] = Mission(MissionType.PICKING, loc_id, item.x, item.y, self.timestep)
            self.assigned_items[closest] = item.id
            self._assign_step.setdefault(item.id, self.timestep)

    def _pick_dock(self, agv, goal_paths):
        """Index of the workstation to deliver the carried shelf to. Hook, like _pick_route.

        Default: the shortest path, by raw cell count. NOTE this discards the congestion-weighted cost
        that find_path already computed, so the dock choice is congestion-blind even though the path to
        it is not. PartACongestionDockController overrides this.
        """
        return int(np.argmin([len(p) for p in goal_paths]))

    def _dispatch_pickers(self):
        """Send pickers to AGVs needing a load/unload. Base = zone-based (original)."""
        assigned_agvs, assigned_pickers, pickers = (
            self.assigned_agvs, self.assigned_pickers, self.pickers)
        for agv, mission in assigned_agvs.items():
            if mission.mission_type in (MissionType.PICKING, MissionType.RETURNING):
                in_zone = [(mission.location_y, mission.location_x) in p for p in self.picker_sections]
                if True not in in_zone:
                    continue
                relevant_picker = pickers[in_zone.index(True)]
                if relevant_picker not in assigned_pickers:
                    assigned_pickers[relevant_picker] = Mission(
                        MissionType.PICKING, mission.location_id, mission.location_x, mission.location_y, self.timestep)
        for picker in pickers:
            if picker in assigned_pickers and picker.x == assigned_pickers[picker].location_x and picker.y == assigned_pickers[picker].location_y:
                assigned_pickers.pop(picker)

    def act(self) -> list:
        env = self.env
        agvs, pickers = self.agvs, self.pickers
        assigned_agvs = self.assigned_agvs
        assigned_pickers = self.assigned_pickers
        assigned_items = self.assigned_items
        actions = {k: 0 for k in self.agents}

        # Assign free AGVs to tasks. Task-centric by default (order tasks, give each to
        # the nearest free AGV); Part A overrides this with a per-robot route-aware funnel.
        self._assign_tasks()  # first-assign time

        # Advance each AGV through its PICKING -> DELIVERING -> RETURNING cycle.
        for agv in agvs:
            if agv in assigned_agvs and agv.x == assigned_agvs[agv].location_x and agv.y == assigned_agvs[agv].location_y:
                assigned_agvs[agv].at_location = True
            if agv not in assigned_agvs or agv.busy:
                continue

            if assigned_agvs[agv].mission_type == MissionType.PICKING and assigned_agvs[agv].at_location and agv.carrying_shelf:
                goal_paths = [env.find_path((agv.y, agv.x), (y, x), agv, care_for_agents=False) for (x, y) in env.goals]
                closest_goal = env.goals[self._pick_dock(agv, goal_paths)]
                goal_location_id = self.coords_to_id[(closest_goal[1], closest_goal[0])]
                assigned_agvs.pop(agv)
                assigned_agvs[agv] = Mission(MissionType.DELIVERING, goal_location_id, closest_goal[0], closest_goal[1], self.timestep)

            if assigned_agvs[agv].mission_type == MissionType.DELIVERING and assigned_agvs[agv].at_location and agv.carrying_shelf:
                # This is the delivery moment -> record the completed task.
                self.completed.append((self.timestep, assigned_items.get(agv)))
                _sid = assigned_items.get(agv)                # measure assign->deliver duration
                if _sid in self._assign_step:
                    self.durations.append(self.timestep - self._assign_step.pop(_sid))
                empty_shelves = env.get_empty_shelf_information()
                empty_ids = list(self.non_goal_location_ids[empty_shelves > 0])
                taken = [m.location_id for m in assigned_agvs.values()]
                empty_ids = [i for i in empty_ids if i not in taken]
                # dedicated charging bays are shelf-free by construction but are NOT drop
                # slots (opt-in `env._charger_bays`; empty/absent -> unchanged)
                _bays = getattr(env, "_charger_bays", None)
                if _bays:
                    empty_ids = [i for i in empty_ids
                                 if (self.location_map[i][1], self.location_map[i][0])
                                 not in _bays]
                empty_yx = [self.location_map[i] for i in empty_ids]
                if not empty_ids:
                    continue          # no free storage slot this step (all claimed by other returners)
                                      # -> hold at the dock one step and retry; previously CRASHED here
                paths = [env.find_path((agv.y, agv.x), (y, x), agv, care_for_agents=False) for (y, x) in empty_yx]
                d = [len(p) for p in paths]
                cid = empty_ids[int(np.argmin(d))]
                cyx = self.location_map[cid]
                assigned_agvs.pop(agv)
                assigned_agvs[agv] = Mission(MissionType.RETURNING, cid, cyx[1], cyx[0], self.timestep)

            if assigned_agvs[agv].mission_type == MissionType.RETURNING and assigned_agvs[agv].at_location and not agv.carrying_shelf:
                assigned_agvs.pop(agv)
                # DEFENSIVE (2026-08-24): a charge decision can preempt a RETURNING mission and
                # clear the item assignment first, so the entry may already be gone. Surfaced by
                # the charging-foresight experiment, but the MPC retunes the same threshold every
                # 50 steps, so a bare pop() was a live crash risk in production runs too.
                assigned_items.pop(agv, None)

        self._dispatch_pickers()

        for agv, mission in assigned_agvs.items():
            actions[agv] = mission.location_id if not agv.busy else 0
        for picker, mission in assigned_pickers.items():
            actions[picker] = mission.location_id

        self.timestep += 1
        return [actions[a] for a in self.agents]

    # human-readable words for each mission state
    _STATE_WORD = {"PICKING": "fetching shelf", "DELIVERING": "carrying to dock",
                   "RETURNING": "returning shelf"}

    def task_lines(self) -> list[str]:
        assigned_ids = set(self.assigned_items.values())

        lines = ["BEING DONE:"]
        any_assigned = False
        for agv in self.agvs:
            if agv in self.assigned_agvs:
                shelf = self.assigned_items.get(agv, "-")
                state = self.assigned_agvs[agv].mission_type.name
                word = self._STATE_WORD.get(state, state.lower())
                lines.append(f"  shelf {shelf}  (AGV{agv.id}, {word})")
                any_assigned = True
        if not any_assigned:
            lines.append("  (none yet)")

        waiting = [s.id for s in self.env.request_queue if s.id not in assigned_ids]
        shown = ", ".join(str(i) for i in waiting[:8])
        if len(waiting) > 8:
            shown += f", +{len(waiting) - 8} more"
        lines.append(f"WAITING (in order): {shown or '-'}")

        recent = ", ".join(str(sid) for _, sid in list(self.completed)[-6:]) or "-"
        lines.append(f"FINISHED (recent): {recent}")
        return lines


class RandomController:
    def __init__(self, env):
        self.env = env

    def act(self) -> list:
        return list(self.env.action_space.sample())

    def task_lines(self) -> list[str]:
        open_ids = [s.id for s in self.env.request_queue]
        shown = ", ".join(str(i) for i in open_ids[:6])
        if len(open_ids) > 6:
            shown += f", +{len(open_ids) - 6} more"
        return [
            "(random policy - no assignment;",
            " AGVs pick random targets, so no",
            " shelf -> AGV mapping exists)",
            f"OPEN tasks ({len(open_ids)}): {shown}",
        ]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def grid_image(env) -> np.ndarray:
    rows, cols = env.grid_size
    img = np.ones((rows, cols, 3), dtype=float)
    img[:, :] = C_FLOOR
    req = set(id(s) for s in env.request_queue)
    for sh in env.shelfs:
        img[sh.y, sh.x] = C_SHELF_REQ if id(sh) in req else C_SHELF
    for (gx, gy) in env.goals:
        img[gy, gx] = C_GOAL
    return img


def agent_scatter(env):
    """Return (agv_xy, agv_colors, picker_xy) for overlay markers."""
    agv_xy, agv_c, picker_xy = [], [], []
    for a in env.agents:
        if a.type == AgentType.AGV or a.type == AgentType.AGENT:
            agv_xy.append((a.x, a.y))
            agv_c.append(C_AGV_LOADED if a.carrying_shelf else C_AGV)
        else:
            picker_xy.append((a.x, a.y))
    return np.array(agv_xy), np.array(agv_c), np.array(picker_xy)


def accumulate(cum: dict, info: dict) -> None:
    cum["deliveries"] += info.get("shelf_deliveries", 0)
    cum["clashes"] += info.get("clashes", 0)
    cum["stucks"] += info.get("stucks", 0)
    cum["steps"] += 1


def throughput_1k(cum: dict) -> float:
    return 1000.0 * cum["deliveries"] / cum["steps"] if cum["steps"] else 0.0


class Dashboard:
    def __init__(self, env_id: str, seed: int, max_steps: int, steps_per_charge: float = 300.0):
        import matplotlib.pyplot as plt

        self.plt = plt
        self.seed = seed
        self.max_steps = max_steps
        self.steps_per_charge = steps_per_charge

        self.env_f = gym.make(env_id).unwrapped
        self.env_r = gym.make(env_id).unwrapped
        self.env_f.reset(seed=seed)
        self.env_r.reset(seed=seed)
        self.ctrl_f = FIFOController(self.env_f)
        self.ctrl_r = RandomController(self.env_r)
        # Battery model (our Stage-0 rulebook) on each env. Created AFTER reset so
        # the tracker snapshots the correct starting positions.
        self.bat_f = BatteryTracker(self.env_f, BatteryConfig(steps_per_charge=steps_per_charge))
        self.bat_r = BatteryTracker(self.env_r, BatteryConfig(steps_per_charge=steps_per_charge))
        self.cum_f = {"deliveries": 0, "clashes": 0, "stucks": 0, "steps": 0}
        self.cum_r = {"deliveries": 0, "clashes": 0, "stucks": 0, "steps": 0}
        # cumulative reroute-pair counts per policy (key = sorted (id, id))
        self.rr_f: Counter = Counter()
        self.rr_r: Counter = Counter()
        self.done_f = self.done_r = False

        self.fig = plt.figure(figsize=(17, 11.5))
        self.fig.suptitle(
            f"Warehouse demo (wwm_sim + battery)  |  env: {env_id}  |  seed {seed}",
            fontsize=13, fontweight="bold",
        )
        gs = self.fig.add_gridspec(4, 3, width_ratios=[1, 1, 0.62],
                                   height_ratios=[2.6, 1.0, 0.95, 0.85], hspace=0.4, wspace=0.12,
                                   top=0.94, bottom=0.09)
        self.ax_f = self.fig.add_subplot(gs[0, 0])
        self.ax_r = self.fig.add_subplot(gs[0, 1])
        self.ax_leg = self.fig.add_subplot(gs[0, 2])
        self.ax_ft = self.fig.add_subplot(gs[1, 0])
        self.ax_rt = self.fig.add_subplot(gs[1, 1])
        self.ax_tbl = self.fig.add_subplot(gs[1, 2])
        self.ax_bf = self.fig.add_subplot(gs[2, 0])
        self.ax_br = self.fig.add_subplot(gs[2, 1])
        self.ax_blg = self.fig.add_subplot(gs[2, 2])
        self.ax_rrf = self.fig.add_subplot(gs[3, 0])
        self.ax_rrr = self.fig.add_subplot(gs[3, 1])
        self._build_legend()
        self._add_footnote()

    def _add_footnote(self):
        note = (
            "How to read this  —  "
            "Shelf numbers are IDs (labels), not order: \"FIFO\" serves the request QUEUE in order, each request to the nearest free AGV.     "
            "Teal = open task (requested shelf), purple = idle shelf; a picked-up task-shelf rides with its red AGV and turns purple once delivered "
            "(a new teal appears elsewhere, keeping the task count constant).     "
            "An AGV (hexagon) + Picker (diamond) sharing one shelf cell is the loading rendezvous — allowed by design, not a conflict.     "
            "A \"reroute\" = one robot steps aside so two never share a cell (collision avoided, at an energy/time cost); the reroute-pairs panels show which robots did this."
        )
        self.fig.text(0.5, 0.03, note, ha="center", va="bottom", fontsize=8,
                      style="italic", color="#333333", wrap=True)

    def _build_legend(self):
        from matplotlib.patches import Patch
        from matplotlib.lines import Line2D

        handles = [
            Patch(facecolor=C_SHELF, edgecolor="k", label="Shelf (in rack)"),
            Patch(facecolor=C_SHELF_REQ, edgecolor="k", label="Requested shelf = a task"),
            Patch(facecolor=C_GOAL, edgecolor="k", label="Delivery station (goal)"),
            Line2D([0], [0], marker="H", color="w", markerfacecolor=C_AGV,
                   markeredgecolor="k", markersize=15, label="AGV (empty)"),
            Line2D([0], [0], marker="H", color="w", markerfacecolor=C_AGV_LOADED,
                   markeredgecolor="k", markersize=15, label="AGV (carrying shelf)"),
            Line2D([0], [0], marker="D", color="w", markerfacecolor=C_PICKER,
                   markeredgecolor="k", markersize=13, label="Picker (loader)"),
        ]
        self.ax_leg.axis("off")
        self.ax_leg.legend(handles=handles, loc="upper center", frameon=True,
                           fontsize=11, title="Legend", title_fontsize=12)

    def _draw_grid(self, ax, env, title):
        ax.clear()
        ax.imshow(grid_image(env), origin="upper", interpolation="nearest")
        agv_xy, agv_c, picker_xy = agent_scatter(env)
        if len(agv_xy):
            ax.scatter(agv_xy[:, 0], agv_xy[:, 1], marker="H", s=260,
                       c=agv_c, edgecolors="k", linewidths=1.2, zorder=3)
        if len(picker_xy):
            ax.scatter(picker_xy[:, 0], picker_xy[:, 1], marker="D", s=150,
                       c=[C_PICKER], edgecolors="k", linewidths=1.2, zorder=3)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xticks([]); ax.set_yticks([])

    def _draw_tasks(self, ax, lines, header):
        ax.clear(); ax.axis("off")
        ax.text(0.0, 1.0, header, fontsize=11, fontweight="bold",
                va="top", ha="left", transform=ax.transAxes)
        ax.text(0.0, 0.86, "\n".join(lines), fontsize=10, family="monospace",
                va="top", ha="left", transform=ax.transAxes)

    def _draw_table(self):
        ax = self.ax_tbl
        ax.clear(); ax.axis("off")
        rows = [
            ["Step", str(self.cum_f["steps"]), str(self.cum_r["steps"])],
            ["Deliveries", str(self.cum_f["deliveries"]), str(self.cum_r["deliveries"])],
            ["Throughput/1k", f"{throughput_1k(self.cum_f):.1f}", f"{throughput_1k(self.cum_r):.1f}"],
            ["Reroutes", str(self.cum_f["clashes"]), str(self.cum_r["clashes"])],
            ["Stucks", str(self.cum_f["stucks"]), str(self.cum_r["stucks"])],
            ["Deadlines met", "N/A", "N/A"],
        ]
        tbl = ax.table(cellText=rows, colLabels=["Metric", "FIFO", "Random"],
                       loc="center", cellLoc="center", colWidths=[0.5, 0.25, 0.25])
        tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.5)
        for c in range(3):
            tbl[0, c].set_facecolor("#333333")
            tbl[0, c].set_text_props(color="w", fontweight="bold")
        ax.set_title("Running totals", fontsize=11, fontweight="bold")

    def _draw_battery(self, ax, bat, title):
        ax.clear()
        agents = bat.env.agents
        labels, vals, colors = [], [], []
        for a in agents:
            tag = "AGV" if a.type == AgentType.AGV else "PCK"
            labels.append(f"{tag}{a.id}")
            lvl = bat.level[a.id] * 100.0
            vals.append(lvl)
            if a.id in bat.stranded:
                colors.append((0.55, 0.55, 0.55))     # grey = stranded
            elif lvl <= 20:
                colors.append((0.85, 0.10, 0.10))     # red = critical
            elif lvl <= 50:
                colors.append((0.95, 0.75, 0.10))      # amber = low
            else:
                colors.append((0.15, 0.65, 0.20))      # green = healthy
        y = list(range(len(labels)))
        ax.barh(y, vals, color=colors, edgecolor="k", height=0.62, zorder=2)
        floor = bat.cfg.floor * 100.0
        ax.axvline(floor, color="red", linestyle="--", linewidth=1.0, zorder=3)
        for yi, (v, a) in enumerate(zip(vals, agents)):
            mark = " STRANDED" if a.id in bat.stranded else ""
            ax.text(2, yi, f"{v:.0f}%{mark}", va="center", ha="left", fontsize=7,
                    color="white" if v > 25 else "black", zorder=4)
        ax.set_xlim(0, 100)
        ax.set_ylim(-0.6, len(labels) - 0.4)
        ax.invert_yaxis()
        ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8)
        ax.set_xticks([0, 50, 100]); ax.tick_params(labelsize=7)
        ax.set_title(title, fontsize=10, fontweight="bold")

    def _draw_batt_legend(self):
        ax = self.ax_blg
        ax.clear(); ax.axis("off")
        cfg = self.bat_f.cfg
        ax.text(0.0, 1.0, "Battery", fontsize=11, fontweight="bold",
                va="top", ha="left", transform=ax.transAxes)
        txt = (
            "green >50%  ·  amber 20-50%\n"
            "red <20%  ·  grey = stranded\n"
            "red dashed line = floor (10%)\n\n"
            f"grounding: Robotnik (compressed)\n"
            f"full charge = {cfg.steps_per_charge:.0f} driving-steps\n"
            "AGV +carry drain · Picker +pick drain"
        )
        ax.text(0.0, 0.82, txt, fontsize=8.5, family="monospace",
                va="top", ha="left", transform=ax.transAxes)

    def _accumulate_reroutes(self, env, counter):
        for a, b in getattr(env, "clash_pairs_this_step", []):
            counter[tuple(sorted((a, b)))] += 1

    def _step(self):
        if not self.done_f and self.cum_f["steps"] < self.max_steps:
            a = self.ctrl_f.act()
            _, _, term, trunc, info = self.env_f.step(a)
            self.bat_f.step()
            self._accumulate_reroutes(self.env_f, self.rr_f)
            accumulate(self.cum_f, info)
            self.done_f = all(term) or all(trunc)
        if not self.done_r and self.cum_r["steps"] < self.max_steps:
            a = self.ctrl_r.act()
            _, _, term, trunc, info = self.env_r.step(a)
            self.bat_r.step()
            self._accumulate_reroutes(self.env_r, self.rr_r)
            accumulate(self.cum_r, info)
            self.done_r = all(term) or all(trunc)

    def _draw_reroutes(self, ax, env, counter, title):
        ax.clear(); ax.axis("off")
        ax.text(0.0, 1.0, title, fontsize=10, fontweight="bold",
                va="top", ha="left", transform=ax.transAxes)

        def lbl(i):
            a = env.agents[i - 1]
            return ("AGV" if a.type == AgentType.AGV else "PCK") + str(i)

        if not counter:
            ax.text(0.0, 0.74, "  (no reroutes yet)", fontsize=9, family="monospace",
                    va="top", ha="left", transform=ax.transAxes)
            return
        lines = [f"  {lbl(a)} <-> {lbl(b)} : {n}" for (a, b), n in counter.most_common(5)]
        if len(counter) > 5:
            lines.append(f"  (+{len(counter) - 5} more pairs)")
        lines.append(f"  total reroute events: {sum(counter.values())}")
        ax.text(0.0, 0.76, "\n".join(lines), fontsize=9, family="monospace",
                va="top", ha="left", transform=ax.transAxes)

    def render_current(self):
        self._draw_grid(self.ax_f, self.env_f, "FIFO nearest-agent (baseline)")
        self._draw_grid(self.ax_r, self.env_r, "Random policy")
        self._draw_tasks(self.ax_ft, self.ctrl_f.task_lines(), "FIFO tasks")
        self._draw_tasks(self.ax_rt, self.ctrl_r.task_lines(), "Random tasks")
        self._draw_table()
        self._draw_battery(self.ax_bf, self.bat_f, "FIFO — battery")
        self._draw_battery(self.ax_br, self.bat_r, "Random — battery")
        self._draw_batt_legend()
        self._draw_reroutes(self.ax_rrf, self.env_f, self.rr_f, "FIFO — reroute pairs")
        self._draw_reroutes(self.ax_rrr, self.env_r, self.rr_r, "Random — reroute pairs")

    def run_live(self, fps: float):
        from matplotlib.animation import FuncAnimation

        interval = max(1, int(1000 / fps)) if fps > 0 else 200

        def update(_frame):
            self._step()
            self.render_current()

        self._anim = FuncAnimation(self.fig, update, interval=interval, cache_frame_data=False)
        self.plt.show()

    def snapshot(self, path: str, step: int):
        for _ in range(step):
            if self.done_f and self.done_r:
                break
            self._step()
        self.render_current()
        self.fig.savefig(path, dpi=110, bbox_inches="tight")
        print(f"saved snapshot after {self.cum_f['steps']} steps -> {path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Side-by-side FIFO vs random warehouse dashboard.",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--env", default="wwm_sim-tiny-3agvs-2pickers-globalobs-v1")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--fps", type=float, default=4.0, help="Animation speed (steps/sec). Lower = slower.")
    p.add_argument("--max-steps", type=int, default=500, help="Cap steps per episode.")
    p.add_argument("--steps-per-charge", type=float, default=300.0,
                   help="Battery: driving-steps a full charge lasts. ~300 = compressed (visible); "
                        "21600 = realistic Robotnik (bars barely move).")
    p.add_argument("--snapshot", default=None, help="Headless: save one composed frame to this PNG and exit.")
    p.add_argument("--snapshot-step", type=int, default=120, help="Steps to advance before the snapshot.")
    return p.parse_args()


def main() -> None:
    import warnings
    warnings.filterwarnings("ignore")
    args = parse_args()
    if args.snapshot:
        import matplotlib
        matplotlib.use("Agg")
    dash = Dashboard(args.env, args.seed, args.max_steps, args.steps_per_charge)
    if args.snapshot:
        dash.snapshot(args.snapshot, args.snapshot_step)
    else:
        print(f"Live dashboard: {args.env} | seed {args.seed} | {args.fps} steps/s")
        print("Close the window to stop.")
        dash.run_live(args.fps)


if __name__ == "__main__":
    main()
