"""GIF: the chosen imagined future vs WHAT ACTUALLY HAPPENED — same decision, same order pool.

At the same real decision as viz_futures (seed 3, max-spread), records the chosen branch's imagined
trajectory, then lets the real day play out and records actual deliveries FROM THE SAME PENDING POOL
(orders unassigned at the decision moment -- exactly what the sim was scoring). Animates both
cumulative curves with the gap shaded, action logs side by side.
Output: results/imagined_vs_real.gif
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.demand import DemandModel
from congestion_policies import _SqWide

SEED = int(os.environ.get("SEED", "3"))
env = gym.make("wwm_sim-large-8agvs-4pickers-globalobs-v1").unwrapped
env.reset(seed=SEED)
env.request_queue = []
env.demand_model = DemandModel(env, seed=SEED)
env.demand_model.seed_day_list(env, horizon=500)
c = _SqWide(env)

decisions = []
capture = {}
orig_pw = c._pick_winner


def pick_winner(scored):
    me = c._cur_agv
    branches = []
    for tup in scored[:c.SEQ_TOPK]:
        tr = []
        c._sim_pin_agents = {me.id}
        fov = float(c.timestep) + float(tup[4]["pred_finish"]) + c._finish_delay(tup[2])
        v = c._sim_core([(me.x, me.y, tup[1], fov)], trace=tr)
        c._sim_pin_agents = None
        branches.append((v, tup[1].id, tr))
    chosen = orig_pw(scored)
    branches.sort(key=lambda b: -b[0])
    decisions.append({"t": int(c.timestep), "spread": branches[0][0] - branches[min(4, len(branches)-1)][0],
                     "n": len(branches)})
    # capture at the SAME decision viz_futures picked (recompute criterion after run)
    key = (int(c.timestep), me.id)
    capture[key] = {
        "t0": int(c.timestep),
        "chosen_total": next(b[0] for b in branches if b[1] == chosen[1].id),
        "trace": next(b[2] for b in branches if b[1] == chosen[1].id),
        "pool": {s.id for s in env.request_queue} - set(c.assigned_items.values()),
        "horizon": min(int(c.timestep) + c.SEQ_DEPTH * c.TASK_SPAN, 500),
    }
    return chosen


c._pick_winner = pick_winner
real_deliv = []
t = 0
done = False
while not done and t < 500:
    _, _, term, trunc, _i = env.step(c.act())
    t += 1
    for o in getattr(env, "fulfilled_this_step", []):
        on = o.deadline is not None and t <= o.deadline
        real_deliv.append((t, o.shelf.id, o.value if on else 0.0, on))
    done = all(term) or all(trunc)

good = [d for d in decisions if 40 <= d["t"] <= 380 and d["n"] >= 5]
tgt_t = max(good, key=lambda d: d["spread"])["t"]
cap = next(v for k, v in capture.items() if k[0] == tgt_t)
t0, pool, horizon = cap["t0"], cap["pool"], cap["horizon"]
imag = sorted(cap["trace"])
real = [(tt, sid, bank) for (tt, sid, bank, on) in real_deliv if tt >= t0 and sid in pool]
imag_total = cap["chosen_total"]
real_total = sum(b for (_t, _s, b) in real)
print(f"decision at t={t0}, horizon {horizon}, pool {len(pool)} shelves")
print(f"imagined total {imag_total:.1f}  |  actual total (same pool) {real_total:.1f}  "
      f"|  gap {real_total - imag_total:+.1f}")

from matplotlib.animation import PillowWriter
fig = plt.figure(figsize=(12.5, 7))
gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1], hspace=0.3, wspace=0.18)
axc = fig.add_subplot(gs[0, :])
axi = fig.add_subplot(gs[1, 0])
axr = fig.add_subplot(gs[1, 1])


def cum(events, T):
    xs, ys = [t0], [0.0]
    s = 0.0
    for e in events:
        if e[0] > T:
            break
        xs += [e[0], e[0]]
        ys += [s, s + e[2]]
        s += e[2]
    xs.append(min(T, 500)); ys.append(s)
    return xs, ys, s


writer = PillowWriter(fps=4)
Ts = list(np.arange(t0, 505, 6)) + [500] * 8
top = max(imag_total, real_total) * 1.12
with writer.saving(fig, "results/imagined_vs_real.gif", dpi=90):
    for T in Ts:
        axc.clear(); axi.clear(); axr.clear()
        xi, yi, si = cum(imag, T)
        xr, yr, sr = cum(real, T)
        axc.plot(xi, yi, "--", color="#2c6fbb", lw=2.2, label=f"IMAGINED (chosen branch)  ⇒ {imag_total:.0f}")
        axc.plot(xr, yr, "-", color="#1a9641", lw=2.6, label=f"ACTUAL (same order pool)  ⇒ {real_total:.0f}")
        n = min(len(xi), len(xr))
        axc.axvline(T, color="grey", lw=0.7, ls=":")
        if horizon < 500:
            axc.axvline(horizon, color="#d7191c", lw=1, ls="--", alpha=0.6)
            axc.text(horizon + 3, top * 0.05, "sim horizon", color="#d7191c", fontsize=7, rotation=90)
        axc.set_xlim(t0, 505); axc.set_ylim(0, top)
        axc.set_title(f"Imagined vs actual — decision at step {t0} (seed {SEED}) · running gap "
                      f"{sr - si:+.1f}")
        axc.set_ylabel("cumulative banked value")
        axc.legend(loc="upper left", fontsize=9)
        axc.grid(alpha=0.25)
        for ax, ev, name, col in ((axi, imag, "IMAGINED actions", "#2c6fbb"),
                                  (axr, real, "ACTUAL deliveries", "#1a9641")):
            ax.axis("off")
            ax.set_title(name, color=col, fontsize=9)
            shown = [e for e in ev if e[0] <= T][-9:]
            lines = [f"t={e[0]:3.0f}  sh{e[1]:<4}  " + (f"+{e[2]:.1f}" if e[2] > 0 else "late +0")
                     for e in shown]
            ax.text(0.02, 0.98, "\n".join(lines) if lines else "…", va="top", ha="left",
                    fontsize=7, family="monospace", transform=ax.transAxes)
        writer.grab_frame()
plt.close(fig)
print("wrote results/imagined_vs_real.gif")
