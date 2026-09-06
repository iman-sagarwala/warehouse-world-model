"""viz_blocks -- inside the 'traffic block' bucket: WHY exactly does a robot stop mid-route?

For every stationary mid-route step of a tracked task AGV, classify the cause:
  turning          -- rotating in place (a Manhattan-estimate shortfall, not congestion)
  crossing traffic -- the intended next square holds another AGV that IS moving
  parked-for-helper-- next square holds an AGV parked on a shelf, unloaded: it is waiting for
                      a picker (picker scarcity spilling into the roads)
  stopped loaded   -- next square holds a stationary loaded AGV (chain / queue)
  dock spill       -- that stationary loaded blocker is within 2 of a dock (dock queue overflow)
  mutual yield     -- next square is empty but the step was denied (swap/crossing standoff)
Chain flag: the blocker is itself blocked.

Output: results/block_causes.gif -- an animated real example block (grid zoom) followed by the
10-seed aggregate cause chart. Same tracer as viz_delay; AGVs and pickers are on separate
collision layers (verified), so helpers never physically block carriers.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from wwm_sim.warehouse import CollisionLayers, AgentType
from wwm_sim.rollout import _manhattan
from congestion_policies import _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "10"))))
GIF_SEED = 0

C1, C2, C3, C4, C5, C6 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"
C_INK, C_MUT, C_GRID = "#40403e", "#8a8a82", "#d6d5cd"
CAUSES = ["turning", "crossing traffic", "parked carrier (waiting for helper)",
          "stopped loaded carrier (chain)", "dock-queue spill", "mutual yield / standoff"]
CCOL = dict(zip(CAUSES, [C1, C2, C3, C4, C5, C6]))


class _Tracer(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.tasks = {}

    def _on_predict(self, shelf, now, pred_finish):
        agv = getattr(self, "_cur_agv", None)
        if agv is None:
            return
        self.tasks[shelf.id] = {"sid": shelf.id, "aid": agv.id, "t0": int(now),
                                "sx": shelf.x, "sy": shelf.y, "t_end": None}


def snapshot(env, ctrl):
    """Per-step state of every agent: enough to classify any block post-hoc."""
    out = {}
    for a in ctrl.agents:
        p0 = a.path[0] if getattr(a, "path", None) else None
        shelf_here = bool(env.grid[CollisionLayers.SHELVES, a.y, a.x]) if a.type == AgentType.AGV else False
        out[(a.type == AgentType.AGV, a.id)] = (a.x, a.y, str(getattr(a, "dir", "")),
                                                bool(a.carrying_shelf), p0, shelf_here)
    return out


def run_seed(seed, keep_world=False):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _Tracer(env)
    snaps, world = [], []
    t, done = 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        snaps.append(snapshot(env, ctrl))
        if keep_world:
            world.append(([(s.x, s.y) for s in env.shelfs],
                          [(a.x, a.y, bool(a.carrying_shelf), a.id) for a in ctrl.agvs],
                          [(p.x, p.y, p.id) for p in ctrl.pickers]))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            r = ctrl.tasks.get(sid)
            if r is not None and r["t_end"] is None:
                r["t_end"] = t
        done = all(term) or all(trunc)
    recs = [r for r in ctrl.tasks.values() if r["t_end"] is not None]
    return env, recs, snaps, world


def classify_blocks(env, recs, snaps):
    """Return a list of block events: (t, aid, x, y, cause, chain, nxt)."""
    events = []
    for r in recs:
        for t in range(r["t0"] + 1, r["t_end"]):
            i, j = t - 1, t - 2                       # snaps[i] = state AFTER step t
            if i < 1 or i >= len(snaps):
                continue
            me = snaps[i].get((True, r["aid"]))
            prev = snaps[j].get((True, r["aid"]))
            if me is None or prev is None:
                continue
            x, y, d, carry, p0, _sh = me
            px, py, pd, pcarry, _pp0, _psh = prev
            if (x, y) != (px, py):
                continue                              # moved -> not a block
            if not carry and (x, y) == (r["sx"], r["sy"]):
                continue                              # picker wait, already counted elsewhere
            if carry and min(_manhattan(x, y, gx, gy) for (gx, gy) in env.goals) <= 2:
                continue                              # dock queue, already counted elsewhere
            if d != pd:
                events.append((t, r["aid"], x, y, "turning", False, p0)); continue
            if p0 is None:
                events.append((t, r["aid"], x, y, "mutual yield / standoff", False, p0)); continue
            nxt = (int(p0[0]), int(p0[1]))
            if nxt == (x, y):                         # repath just landed; path head is own cell
                events.append((t, r["aid"], x, y, "mutual yield / standoff", False, None)); continue
            # who held the wanted square at the START of the step (when the move was denied)?
            blocker = None
            for (is_agv, aid2), st in snaps[j].items():
                if is_agv and aid2 != r["aid"] and (st[0], st[1]) == nxt:
                    blocker = (aid2, st); break
            if blocker is None:                       # nobody at start -> did someone WIN it mid-step?
                won = any(ia and a2 != r["aid"] and (s2[0], s2[1]) == nxt
                          for (ia, a2), s2 in snaps[i].items())
                events.append((t, r["aid"], x, y,
                               "crossing traffic" if won else "mutual yield / standoff",
                               False, nxt))
                continue
            baid, (bx, by, bd, bcarry, bp0, bsh) = blocker
            bnow = snaps[i].get((True, baid))
            bmoved = bnow is not None and (bnow[0], bnow[1]) != (bx, by)
            chain = False
            if not bmoved and bp0 is not None:        # blocker itself waiting on someone?
                bn = (int(bp0[0]), int(bp0[1]))
                chain = any(ia and a2 != baid and (s2[0], s2[1]) == bn
                            for (ia, a2), s2 in snaps[j].items())
            if bmoved:
                cause = "crossing traffic"            # it was passing through and left this step
            elif not bcarry and bsh:
                cause = "parked carrier (waiting for helper)"
            elif bcarry:
                cause = ("dock-queue spill"
                         if min(_manhattan(bx, by, gx, gy) for (gx, gy) in env.goals) <= 2
                         else "stopped loaded carrier (chain)")
            else:
                cause = "mutual yield / standoff"
            events.append((t, r["aid"], x, y, cause, chain, nxt))
    return events


def find_example(events):
    """Longest consecutive same-agent non-turning block run: (aid, t_start, t_end, cause)."""
    best = None
    ev = sorted([e for e in events if e[4] != "turning"], key=lambda e: (e[1], e[0]))
    run = []
    for e in ev:
        if run and e[1] == run[-1][1] and e[0] == run[-1][0] + 1:
            run.append(e)
        else:
            run = [e]
        if best is None or len(run) > best[0]:
            best = (len(run), list(run))
    return best[1] if best else None


def draw_world_frame(world, env, t, focus, cause, k, n, chain):
    shelves, agvs, pickers = world[t - 1]
    fx, fy, nxt, faid = focus
    W = 8
    x0, x1 = max(0, fx - W), min(env.grid_size[1] - 1, fx + W)
    y0, y1 = max(0, fy - 5), min(env.grid_size[0] - 1, fy + 5)
    fig, ax = plt.subplots(figsize=(10.4, 5.6), dpi=110)
    fig.patch.set_facecolor("white")
    for (sx, sy) in shelves:
        if x0 <= sx <= x1 and y0 <= sy <= y1:
            ax.add_patch(plt.Rectangle((sx - 0.45, sy - 0.45), 0.9, 0.9,
                                       color="#e8e7e0", zorder=1))
    for (gx, gy) in env.goals:
        if x0 <= gx <= x1 and y0 <= gy <= y1:
            ax.add_patch(plt.Rectangle((gx - 0.45, gy - 0.45), 0.9, 0.9,
                                       color="#f5d78e", zorder=1))
    for (px, py, pid) in pickers:
        if x0 <= px <= x1 and y0 <= py <= y1:
            ax.scatter([px], [py], marker="^", s=140, color=C3, zorder=4,
                       edgecolors="white", linewidths=1.5)
    blocker_pos = nxt
    for (axx, ayy, carry, aid) in agvs:
        if not (x0 <= axx <= x1 and y0 <= ayy <= y1):
            continue
        col = "#1c5eb0" if carry else C1
        ring = None
        if aid == faid:
            ring = "#e34948"
        elif (axx, ayy) == blocker_pos:
            ring = C2
        ax.scatter([axx], [ayy], marker="s", s=210, color=col, zorder=5,
                   edgecolors=ring or "white", linewidths=2.5)
    if nxt is not None:
        ax.annotate("", xy=nxt, xytext=(fx, fy),
                    arrowprops=dict(arrowstyle="->", color="#e34948", lw=2), zorder=6)
    ax.set_xlim(x0 - 0.6, x1 + 0.6)
    ax.set_ylim(y1 + 0.6, y0 - 0.6)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(C_GRID)
    ch = "  (blocker is ALSO blocked -> chain)" if chain else ""
    ax.set_title(f"a real block, step {t} ({k+1}/{n}): red carrier wants the arrowed square - "
                 f"{cause}{ch}", color=C_INK, fontsize=10, loc="left")
    ax.text(0.01, -0.05, "squares = carriers (dark = loaded)   triangles = helpers   "
            "grey = shelves   gold = docks   red ring = blocked   orange ring = blocker",
            transform=ax.transAxes, color=C_MUT, fontsize=8)
    fig.tight_layout()
    return fig


def draw_agg_frame(per_seed_counts, per_seed_tasks, chain_frac):
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(10.4, 5.6), dpi=110,
                                   gridspec_kw={"width_ratios": [1.35, 1]})
    fig.patch.set_facecolor("white")
    tot_tasks = sum(per_seed_tasks)
    means = [sum(c.get(cz, 0) for c in per_seed_counts) / tot_tasks for cz in CAUSES]
    ypos = np.arange(len(CAUSES))[::-1]
    axL.barh(ypos, means, height=0.55, color=[CCOL[c] for c in CAUSES],
             edgecolor="white", linewidth=2)
    for y, v in zip(ypos, means):
        axL.text(v + 0.04, y, f"{v:.1f}", va="center", color=C_INK, fontsize=9)
    axL.set_yticks(ypos)
    axL.set_yticklabels(CAUSES, color=C_INK, fontsize=8.5)
    for s in ("top", "right", "left"):
        axL.spines[s].set_visible(False)
    axL.spines["bottom"].set_color(C_GRID)
    axL.tick_params(colors=C_MUT, labelsize=8)
    axL.set_xlabel("mean stopped steps per task", color=C_MUT, fontsize=9)
    axL.set_title(f"inside the 'traffic block' bucket ({len(per_seed_counts)} seeds, "
                  f"{tot_tasks} tasks)", color=C_INK, fontsize=10, loc="left")
    tot_ev = [sum(c.values()) for c in per_seed_counts]
    axR.scatter(range(len(tot_ev)), [e / t for e, t in zip(tot_ev, per_seed_tasks)],
                s=42, color=C1, edgecolors="white", linewidths=1.5, zorder=5)
    axR.axhline(np.mean([e / t for e, t in zip(tot_ev, per_seed_tasks)]),
                color=C2, lw=1.5, ls="--")
    axR.set_xticks(range(len(tot_ev)))
    axR.set_xticklabels([str(s) for s in SEEDS], fontsize=8)
    for s in ("top", "right"):
        axR.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        axR.spines[s].set_color(C_GRID)
    axR.tick_params(colors=C_MUT, labelsize=8)
    axR.set_xlabel("seed", color=C_MUT, fontsize=9)
    axR.set_ylabel("stopped steps per task", color=C_MUT, fontsize=9)
    axR.set_title(f"per seed  |  chained blocks: {chain_frac:.0%}", color=C_INK,
                  fontsize=10, loc="right")
    fig.tight_layout()
    return fig


def fig_to_img(fig):
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    per_seed_counts, per_seed_tasks = [], []
    chain_n = ev_n = 0
    example, gif_world, gif_env = None, None, None
    for s in SEEDS:
        env, recs, snaps, world = run_seed(s, keep_world=(s == GIF_SEED))
        events = classify_blocks(env, recs, snaps)
        counts = {}
        for e in events:
            counts[e[4]] = counts.get(e[4], 0) + 1
            chain_n += bool(e[5]); ev_n += 1
        per_seed_counts.append(counts)
        per_seed_tasks.append(max(1, len(recs)))
        if s == GIF_SEED:
            example, gif_world, gif_env = find_example(events), world, env
        print(f"seed {s}: {len(recs)} tasks, {len(events)} stopped steps -> " +
              "  ".join(f"{c}:{n}" for c, n in sorted(counts.items(), key=lambda kv: -kv[1])),
              flush=True)
    frames = []
    if example:
        n = min(len(example), 10)
        for k in range(n):
            t, aid, x, y, cause, chain, nxt = example[k]
            frames.append(fig_to_img(draw_world_frame(
                gif_world, gif_env, t, (x, y, nxt, aid), cause, k, n, chain)))
    agg = fig_to_img(draw_agg_frame(per_seed_counts, per_seed_tasks,
                                    chain_n / max(1, ev_n)))
    frames += [agg] * 10
    durs = [650] * (len(frames) - 10) + [800] * 10
    frames[0].save("results/block_causes.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/block_causes.gif  ({len(frames)} frames)  "
          f"chain fraction {chain_n / max(1, ev_n):.0%}")


if __name__ == "__main__":
    main()
