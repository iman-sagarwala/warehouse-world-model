"""WAGE-CURVE EXTRACTION + DECISION-POINT ANIMATION (three probes).

At every real decision of one day (seed 3, day-list, deployed sequencer):
  w_solo    = loss/step from delaying the DECIDING robot 10 steps   (marginal robot wage)
  w_fleet   = loss/step from delaying the WHOLE FLEET 10 steps      (system time wage)
  w_contrib = total loss from REMOVING the deciding robot outright  (its remaining-day worth)
Outputs: results/wage_curve.png, results/wage_decisions.gif
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

frames = []
orig_pw = c._pick_winner


def pick_winner(scored):
    me = c._cur_agv
    cands = []
    for tup in scored[:c.SEQ_TOPK]:
        v = c._simulate_branch(tup)
        cands.append((tup[1].x, tup[1].y, float(tup[1].value or 1.0), v, tup[1].id))
    chosen = orig_pw(scored)
    v0 = c._sim_core([], include_free=True)
    w_solo = (v0 - c._sim_core([], include_free=True, probe_delay=(me.id, 10.0))) / 10.0
    w_fleet = (v0 - c._sim_core([], include_free=True, probe_delay=(-1, 10.0))) / 10.0
    w_contrib = v0 - c._sim_core([], include_free=True, probe_delay=(me.id, 99999.0))
    frames.append({
        "t": int(c.timestep), "me": (me.x, me.y),
        "w_solo": w_solo, "w_fleet": w_fleet, "w_contrib": w_contrib,
        "cands": cands, "chosen_id": chosen[1].id,
        "agvs": [(a.x, a.y, bool(a.busy)) for a in c.agvs],
        "picks": [(p.x, p.y) for p in c.pickers],
        "qlen": len(env.request_queue),
    })
    return chosen


c._pick_winner = pick_winner
t = 0
done = False
while not done and t < 500:
    _, _, term, trunc, _i = env.step(c.act())
    t += 1
    done = all(term) or all(trunc)
print(f"episode done: {len(frames)} decision points")

ts = [f["t"] for f in frames]
ws = [f["w_solo"] for f in frames]
wf = [f["w_fleet"] for f in frames]
wc = [f["w_contrib"] for f in frames]

fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
ax.plot(ts, ws, "o-", color="#2c6fbb", lw=1.5, ms=4, label="one robot delayed 10 (marginal wage)")
ax.plot(ts, wf, "s-", color="#c0392b", lw=1.5, ms=4, label="WHOLE FLEET delayed 10 (system wage)")
ax.axhline(0, color="grey", lw=0.5)
ax.set_ylabel("banked value lost per\nstep of delay")
ax.legend(fontsize=8)
ax.set_title(f"Warehouse wage curves — seed {SEED}")
ax.grid(alpha=0.3)
ax2.plot(ts, wc, "d-", color="#7d3c98", lw=1.5, ms=4)
ax2.axhline(0, color="grey", lw=0.5)
ax2.set_ylabel("deciding robot's TOTAL\nremaining-day contribution")
ax2.set_xlabel("step in the day")
ax2.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("results/wage_curve.png", dpi=110)
plt.close(fig)

goals = set(map(tuple, env.goals))
shelf_xy = [(s.x, s.y) for s in env.shelfs]
from matplotlib.animation import PillowWriter
fig = plt.figure(figsize=(13, 6.5))
gs = fig.add_gridspec(2, 2, width_ratios=[1.15, 1], hspace=0.35, wspace=0.25)
axg = fig.add_subplot(gs[:, 0])
axb = fig.add_subplot(gs[0, 1])
axw = fig.add_subplot(gs[1, 1])
writer = PillowWriter(fps=2)
with writer.saving(fig, "results/wage_decisions.gif", dpi=90):
    for i, f in enumerate(frames):
        axg.clear(); axb.clear(); axw.clear()
        sx, sy = zip(*shelf_xy)
        axg.scatter(sx, sy, marker="s", s=14, c="#dddddd", zorder=1)
        gx, gy = zip(*goals)
        axg.scatter(gx, gy, marker="s", s=30, c="gold", zorder=2, label="docks")
        vals = [cd[3] for cd in f["cands"]]
        vmin, vmax = min(vals), max(vals)
        for (x, y, v, sv, sid) in f["cands"]:
            frac = 0.0 if vmax == vmin else (sv - vmin) / (vmax - vmin)
            col = plt.cm.RdYlGn(0.15 + 0.7 * frac)
            edge = "black" if sid == f["chosen_id"] else "none"
            axg.scatter([x], [y], marker="s", s=90, c=[col], edgecolors=edge, linewidths=2, zorder=4)
        for (x, y, busy) in f["agvs"]:
            axg.scatter([x], [y], c="#2c6fbb" if busy else "#7fc4ff", s=55, zorder=5)
        px, py = zip(*f["picks"])
        axg.scatter(px, py, c="#2ca05a", s=45, marker="^", zorder=5, label="pickers")
        axg.scatter([f["me"][0]], [f["me"][1]], c="red", marker="*", s=220, zorder=6, label="deciding robot")
        axg.set_title(f"decision {i+1}/{len(frames)} · step {f['t']} · queue {f['qlen']} · "
                      f"fleet wage {f['w_fleet']:+.2f}/step · my worth {f['w_contrib']:+.0f}")
        axg.set_xlim(-1, 23); axg.set_ylim(36, -1)
        axg.legend(loc="lower left", fontsize=7)
        order = sorted(f["cands"], key=lambda cd: -cd[3])
        ys = np.arange(len(order))
        cols = ["black" if cd[4] == f["chosen_id"] else "#2c6fbb" for cd in order]
        axb.barh(ys, [cd[3] for cd in order], color=cols)
        axb.set_yticks(ys)
        axb.set_yticklabels([f"shelf({cd[0]},{cd[1]}) v={cd[2]:.0f}" for cd in order], fontsize=6)
        axb.invert_yaxis()
        axb.set_title("imagined end-of-day total per candidate (black = chosen)", fontsize=8)
        axw.plot(ts[:i + 1], ws[:i + 1], "o-", color="#2c6fbb", ms=3, lw=1, label="one robot")
        axw.plot(ts[:i + 1], wf[:i + 1], "s-", color="#c0392b", ms=3, lw=1, label="whole fleet")
        axw.plot([f["t"]], [f["w_fleet"]], "r*", ms=12)
        lo, hi = min(min(ws), min(wf)), max(max(ws), max(wf))
        axw.set_xlim(0, 500); axw.set_ylim(lo - 0.1, hi + 0.1)
        axw.axhline(0, color="grey", lw=0.5)
        axw.legend(fontsize=6)
        axw.set_title("wage curves so far", fontsize=8)
        axw.grid(alpha=0.3)
        writer.grab_frame()
plt.close(fig)
print("wrote results/wage_curve.png and results/wage_decisions.gif")
print(f"SOLO   wage: open {ws[0]:+.2f}  max {max(ws):+.2f}  close {ws[-1]:+.2f}  mean {np.mean(ws):+.2f}")
print(f"FLEET  wage: open {wf[0]:+.2f}  max {max(wf):+.2f}  close {wf[-1]:+.2f}  mean {np.mean(wf):+.2f}")
print(f"CONTRIB    : open {wc[0]:+.0f}  max {max(wc):+.0f}  close {wc[-1]:+.0f}  mean {np.mean(wc):+.1f}")
