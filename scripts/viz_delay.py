"""viz_delay -- WHERE does the ~15-step delay come from? (estimate vs execution, per task)

Runs the champion+urg8 on N day-list seeds with a per-step execution tracer. For every task:
  - at COMMIT: assign step + the funnel's predicted finish (the number _delay_ema measures against)
  - every step until DELIVERY: the AGV's position + carrying flag
Post-hoc each task's actual time is split into named segments:
  drive (squares actually moved), traffic block (stationary mid-route), picker wait (stationary
  at the shelf, not yet loaded), dock queue (stationary while carrying within 2 of a dock).
Delay = actual - predicted, attributed to the segment(s) that overran the estimate's allocation.

Output: results/delay_causes.gif -- one frame per task (seed 0) with estimate-vs-actual stacked
bars + accumulating delay scatter, then hold frames with the N-seed aggregate cause breakdown.
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
from wwm_sim.rollout import nearest_dock_dist, _manhattan
from congestion_policies import _Urg8

ENV = "wwm_sim-large-8agvs-4pickers-globalobs-v1"
STEPS = 500
SEEDS = list(range(int(os.environ.get("SEEDS", "10"))))
GIF_SEED = 0

# validated categorical order (dataviz default palette, light): slots 1-4
C_DRIVE, C_BLOCK, C_PICK, C_DOCK = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
C_EST, C_INK, C_MUT = "#b5b4ab", "#40403e", "#8a8a82"


class _Tracer(_Urg8):
    def __init__(self, env):
        super().__init__(env)
        self.tasks = {}          # sid -> record

    def _on_predict(self, shelf, now, pred_finish):
        agv = getattr(self, "_cur_agv", None)
        if agv is None:
            return
        self.tasks[shelf.id] = {
            "sid": shelf.id, "aid": agv.id, "t0": int(now), "pred": float(pred_finish),
            "ax": agv.x, "ay": agv.y, "sx": shelf.x, "sy": shelf.y,
            "value": float(getattr(shelf, "value", 0.0) or 0.0),
            "deadline": shelf.deadline, "trace": [], "t_end": None,
        }


def run_seed(seed):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=seed)
    env.demand_model.seed_day_list(env, horizon=STEPS)
    ctrl = _Tracer(env)
    by_aid = {a.id: a for a in ctrl.agvs}
    t, done = 0, False
    while not done and t < STEPS:
        _, _, term, trunc, _ = env.step(ctrl.act())
        t += 1
        open_tasks = [r for r in ctrl.tasks.values() if r["t_end"] is None]
        for r in open_tasks:
            a = by_aid[r["aid"]]
            r["trace"].append((a.x, a.y, bool(a.carrying_shelf)))
        for sid, _a in getattr(env, "deliveries_this_step", []):
            r = ctrl.tasks.get(sid)
            if r is not None and r["t_end"] is None:
                r["t_end"] = t
        done = all(term) or all(trunc)
    return env, [r for r in ctrl.tasks.values() if r["t_end"] is not None]


def decompose(env, r):
    """Split the task's actual duration into named segments; return None if the trace is odd."""
    prev = (r["ax"], r["ay"])
    loaded = False
    seg = {"drive": 0, "block": 0, "pick": 0, "dockq": 0}
    for (x, y, carry) in r["trace"][: r["t_end"] - r["t0"]]:
        moved = (x, y) != prev
        if not loaded and carry:
            loaded = True
        if moved:
            seg["drive"] += 1
        else:
            if not loaded:
                if (x, y) == (r["sx"], r["sy"]):
                    seg["pick"] += 1          # at the shelf, no shelf on my back yet -> picker wait
                else:
                    seg["block"] += 1         # stationary mid-fetch -> traffic
            else:
                near_dock = min(_manhattan(x, y, gx, gy) for (gx, gy) in env.goals) <= 2
                seg["dockq" if near_dock else "block"] += 1
        prev = (x, y)
    actual = r["t_end"] - r["t0"]
    if sum(seg.values()) != actual:            # first trace entry is post-step; tolerate 1-off
        seg["drive"] += actual - sum(seg.values())
    # the estimate's allocation (same math the funnel used): fetch + wait/load pad + haul
    mf = _manhattan(r["ax"], r["ay"], r["sx"], r["sy"])
    mh = nearest_dock_dist(env, r["sx"], r["sy"])
    est_wait = max(0.0, r["pred"] - mf - mh)   # sync estimate + LOAD_TIME pad, whatever it was
    over = {
        "traffic block": seg["block"],
        "dock queue": seg["dockq"],
        "picker wait beyond pad": max(0.0, seg["pick"] - est_wait),
        "detour drive": seg["drive"] - (mf + mh),
    }
    return {**r, "seg": seg, "actual": actual, "delay": actual - r["pred"],
            "est": (mf, est_wait, mh), "over": over}


def draw_task_frame(env, tasks_done, k, agg_txt):
    r = tasks_done[k]
    fig, (axL, axR) = plt.subplots(
        1, 2, figsize=(10.4, 4.6), dpi=110, gridspec_kw={"width_ratios": [1.25, 1]})
    fig.patch.set_facecolor("white")
    # LEFT: estimate vs actual stacked bars
    mf, ew, mh = r["est"]
    est_segs = [(mf, C_EST, "fetch"), (ew, "#d6d5cd", "wait+load pad"), (mh, C_EST, "haul")]
    act = r["seg"]
    act_segs = [(act["drive"], C_DRIVE, "drive"), (act["pick"], C_PICK, "picker wait"),
                (act["block"], C_BLOCK, "traffic block"), (act["dockq"], C_DOCK, "dock queue")]
    for yy, segs in ((1.0, est_segs), (0.0, act_segs)):
        xx = 0.0
        for (w, c, _lab) in segs:
            if w > 0:
                axL.barh(yy, w, left=xx, height=0.55, color=c,
                         edgecolor="white", linewidth=2)
                xx += w
    axL.set_yticks([1.0, 0.0])
    axL.set_yticklabels(["estimate", "actual"], color=C_INK)
    xmax = max(r["pred"], r["actual"]) * 1.18 + 4
    axL.set_xlim(0, xmax)
    axL.set_ylim(-0.6, 1.75)
    axL.text(r["pred"] + 1, 1.0, f'{r["pred"]:.0f}', va="center", color=C_MUT, fontsize=9)
    axL.text(r["actual"] + 1, 0.0, f'{r["actual"]:.0f}  ({r["delay"]:+.0f})',
             va="center", color=C_INK, fontsize=9, fontweight="bold")
    for s in ("top", "right", "left"):
        axL.spines[s].set_visible(False)
    axL.spines["bottom"].set_color("#d6d5cd")
    axL.tick_params(colors=C_MUT, labelsize=8)
    axL.set_xlabel("steps from commit", color=C_MUT, fontsize=9)
    # legend (fixed order, fixed colors)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (C_DRIVE, C_PICK, C_BLOCK, C_DOCK)]
    axL.legend(handles, ["drive", "picker wait", "traffic block", "dock queue"],
               loc="upper right", frameon=False, fontsize=8, ncol=2, labelcolor=C_INK)
    # caption: the biggest cause of THIS task's overrun
    top = max(r["over"].items(), key=lambda kv: kv[1])
    why = f"mostly {top[0]} ({top[1]:+.0f})" if r["delay"] > 2 and top[1] > 1 else (
        "on estimate" if abs(r["delay"]) <= 2 else "beat the estimate")
    axL.set_title(f'task {k+1}/{len(tasks_done)} - shelf {r["sid"]}, t={r["t0"]}: {why}',
                  color=C_INK, fontsize=10, loc="left")
    # RIGHT: delay scatter accumulating + running mean
    xs = [tt["t0"] for tt in tasks_done[: k + 1]]
    ys = [tt["delay"] for tt in tasks_done[: k + 1]]
    axR.axhline(0, color="#d6d5cd", lw=1)
    axR.scatter(xs[:-1], ys[:-1], s=22, color=C_DRIVE, alpha=0.55, edgecolors="none")
    axR.scatter(xs[-1:], ys[-1:], s=46, color=C_BLOCK, zorder=5, edgecolors="white", linewidths=1.5)
    if len(ys) >= 2:
        rm = [np.mean(ys[: i + 1]) for i in range(len(ys))]
        axR.plot(xs, rm, color=C_INK, lw=2)
        axR.text(xs[-1], rm[-1], f'  avg {rm[-1]:+.1f}', color=C_INK, fontsize=9,
                 va="center", fontweight="bold")
    axR.set_xlim(0, STEPS)
    all_d = [tt["delay"] for tt in tasks_done]
    axR.set_ylim(min(all_d) - 5, max(all_d) + 5)
    for s in ("top", "right"):
        axR.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        axR.spines[s].set_color("#d6d5cd")
    axR.tick_params(colors=C_MUT, labelsize=8)
    axR.set_xlabel("commit step", color=C_MUT, fontsize=9)
    axR.set_ylabel("delay vs estimate (steps)", color=C_MUT, fontsize=9)
    axR.set_title(f"seed {GIF_SEED}: delay per task", color=C_INK, fontsize=10, loc="right")
    fig.text(0.01, 0.012, agg_txt, color=C_MUT, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def draw_agg_frame(all_tasks, per_seed_mean):
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(10.4, 4.6), dpi=110)
    fig.patch.set_facecolor("white")
    delays = [t["delay"] for t in all_tasks]
    # LEFT: mean stationary-time by cause (the raw "where the lost steps sit")
    causes = ["drive beyond straight-line", "picker wait", "traffic block", "dock queue"]
    mf_over = np.mean([t["seg"]["drive"] - (t["est"][0] + t["est"][2]) for t in all_tasks])
    vals = [mf_over,
            np.mean([t["seg"]["pick"] for t in all_tasks]),
            np.mean([t["seg"]["block"] for t in all_tasks]),
            np.mean([t["seg"]["dockq"] for t in all_tasks])]
    cols = [C_DRIVE, C_PICK, C_BLOCK, C_DOCK]
    ypos = np.arange(len(causes))[::-1]
    axL.barh(ypos, vals, height=0.55, color=cols, edgecolor="white", linewidth=2)
    for y, v in zip(ypos, vals):
        axL.text(max(v, 0) + 0.15, y, f"{v:+.1f}", va="center", color=C_INK, fontsize=9)
    axL.set_yticks(ypos)
    axL.set_yticklabels(causes, color=C_INK, fontsize=9)
    axL.axvline(0, color="#d6d5cd", lw=1)
    for s in ("top", "right", "left"):
        axL.spines[s].set_visible(False)
    axL.spines["bottom"].set_color("#d6d5cd")
    axL.tick_params(colors=C_MUT, labelsize=8)
    axL.set_xlabel("mean steps per task vs the estimate's allocation", color=C_MUT, fontsize=9)
    n_seeds = len(per_seed_mean)
    axL.set_title(f"WHY tasks run late ({len(all_tasks)} tasks / {n_seeds} seeds, "
                  f"mean {np.mean(delays):+.1f})", color=C_INK, fontsize=9, loc="left")
    # RIGHT: per-seed mean delay
    axR.axhline(np.mean(delays), color=C_BLOCK, lw=1.5, ls="--")
    axR.text(n_seeds - 0.4, np.mean(delays), f' overall {np.mean(delays):+.1f}',
             color=C_BLOCK, fontsize=9, va="bottom", ha="right")
    axR.scatter(range(n_seeds), per_seed_mean, s=42, color=C_DRIVE, edgecolors="white",
                linewidths=1.5, zorder=5)
    axR.axhline(0, color="#d6d5cd", lw=1)
    axR.set_xticks(range(n_seeds))
    axR.set_xticklabels([str(s) for s in SEEDS], fontsize=8)
    for s in ("top", "right"):
        axR.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        axR.spines[s].set_color("#d6d5cd")
    axR.tick_params(colors=C_MUT, labelsize=8)
    axR.set_xlabel("seed", color=C_MUT, fontsize=9)
    axR.set_ylabel("mean delay vs estimate (steps)", color=C_MUT, fontsize=9)
    axR.set_title("per-seed average delay", color=C_INK, fontsize=10, loc="left")
    fig.tight_layout()
    return fig


def fig_to_img(fig):
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    all_tasks, per_seed_mean, gif_env, gif_tasks = [], [], None, None
    for s in SEEDS:
        env, recs = run_seed(s)
        decs = [d for d in (decompose(env, r) for r in recs) if d is not None]
        decs.sort(key=lambda d: d["t0"])
        per_seed_mean.append(float(np.mean([d["delay"] for d in decs])))
        all_tasks.extend(decs)
        if s == GIF_SEED:
            gif_env, gif_tasks = env, decs
        print(f"seed {s}: {len(decs)} tasks, mean delay {per_seed_mean[-1]:+.1f}", flush=True)
    agg_txt = (f"{len(SEEDS)}-seed mean delay {np.mean([t['delay'] for t in all_tasks]):+.1f} "
               f"steps/task  |  estimate = straight-line fetch + wait/load pad + haul (champion+urg8, day-list)")
    frames = [fig_to_img(draw_task_frame(gif_env, gif_tasks, k, agg_txt))
              for k in range(len(gif_tasks))]
    agg = fig_to_img(draw_agg_frame(all_tasks, per_seed_mean))
    frames += [agg] * 10
    durs = [420] * (len(frames) - 10) + [700] * 10
    frames[0].save("results/delay_causes.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/delay_causes.gif  ({len(frames)} frames)")
    # console summary
    print("\nmean stationary steps/task: "
          f"pick {np.mean([t['seg']['pick'] for t in all_tasks]):.1f}  "
          f"block {np.mean([t['seg']['block'] for t in all_tasks]):.1f}  "
          f"dockq {np.mean([t['seg']['dockq'] for t in all_tasks]):.1f}  "
          f"drive-over {np.mean([t['seg']['drive'] - (t['est'][0] + t['est'][2]) for t in all_tasks]):+.1f}")


if __name__ == "__main__":
    main()
