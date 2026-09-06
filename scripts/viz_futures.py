"""GIF: how the world model grows total value across competing imagined futures.

Picks the most interesting real decision of a real day (largest spread among branch outcomes),
records the FULL simulated trajectory of the top-5 candidate futures, then animates simulated time:
each future's cumulative banked value grows as its imagined actions fire; the action log for each
future prints beneath its curve. The chosen future is highlighted.
Output: results/futures.gif
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
        branches.append({"shelf": (tup[1].x, tup[1].y), "sid": tup[1].id,
                         "val": float(tup[1].value or 1.0), "total": v, "trace": tr})
    chosen = orig_pw(scored)
    branches.sort(key=lambda b: -b["total"])
    decisions.append({"t": int(c.timestep), "me": me.id, "branches": branches,
                      "chosen_sid": chosen[1].id})
    return chosen


c._pick_winner = pick_winner
t = 0
done = False
while not done and t < 500:
    _, _, term, trunc, _i = env.step(c.act())
    t += 1
    done = all(term) or all(trunc)

cand = [d for d in decisions if 40 <= d["t"] <= 380 and len(d["branches"]) >= 5]
target = max(cand, key=lambda d: d["branches"][0]["total"] - d["branches"][min(4, len(d["branches"])-1)]["total"])
top = target["branches"][:5]
t0 = target["t"]
print(f"decision chosen: step {t0}, robot {target['me']}, spread "
      f"{top[0]['total']-top[-1]['total']:.1f} across top-5")

labels = ["A", "B", "C", "D", "E"]
colors = ["#1a9641", "#2c6fbb", "#e08214", "#a05aa0", "#d7191c"]
from matplotlib.animation import PillowWriter
fig = plt.figure(figsize=(13, 7.5))
gs = fig.add_gridspec(2, 5, height_ratios=[1.45, 1], hspace=0.32, wspace=0.35)
axc = fig.add_subplot(gs[0, :])
axs = [fig.add_subplot(gs[1, i]) for i in range(5)]
Ts = np.arange(t0, 505, 6)
writer = PillowWriter(fps=4)
with writer.saving(fig, "results/futures.gif", dpi=90):
    frames_list = list(Ts) + [Ts[-1]] * 8          # hold the ending
    for T in frames_list:
        axc.clear()
        for k, b in enumerate(top):
            ev = sorted(b["trace"])
            xs, ys = [t0], [0.0]
            cum = 0.0
            for (ft, sid, bank, ridx) in ev:
                if ft > T:
                    break
                xs += [ft, ft]
                ys += [cum, cum + bank]
                cum += bank
            xs.append(min(T, 500)); ys.append(cum)
            chosen = (b["sid"] == target["chosen_sid"])
            axc.plot(xs, ys, color=colors[k], lw=3.2 if chosen else 1.6,
                     alpha=1.0 if chosen else 0.75,
                     label=f"{labels[k]}: first→shelf{b['shelf']} v={b['val']:.0f}"
                           f"  ⇒ {b['total']:.0f}" + ("  ← CHOSEN" if chosen else ""))
        axc.axvline(T, color="grey", lw=0.7, ls=":")
        axc.set_xlim(t0, 505); axc.set_ylim(0, top[0]["total"] * 1.12)
        axc.set_xlabel("simulated time (steps)")
        axc.set_ylabel("cumulative banked value (imagined)")
        axc.set_title(f"One real decision (step {t0}, robot {target['me']}): five imagined rest-of-days, "
                      f"value growing as simulated actions fire")
        axc.legend(loc="lower right", fontsize=8)
        axc.grid(alpha=0.25)
        for k, (ax, b) in enumerate(zip(axs, top)):
            ax.clear(); ax.axis("off")
            chosen = (b["sid"] == target["chosen_sid"])
            ax.set_title(f"Future {labels[k]}" + (" ★" if chosen else ""),
                         color=colors[k], fontsize=10,
                         fontweight="bold" if chosen else "normal")
            ev = [e for e in sorted(b["trace"]) if e[0] <= T][-9:]
            lines = [f"t={ft:3.0f}  R{ridx}→sh{sid}  " + (f"+{bank:.1f}" if bank > 0 else "late +0")
                     for (ft, sid, bank, ridx) in ev]
            ax.text(0.0, 0.98, "\n".join(lines) if lines else "(imagining…)",
                    va="top", ha="left", fontsize=6.5, family="monospace",
                    transform=ax.transAxes)
        writer.grab_frame()
plt.close(fig)
print("wrote results/futures.gif")
for k, b in enumerate(top):
    print(f"  Future {labels[k]}: first shelf{b['shelf']} v={b['val']:.0f} -> total {b['total']:.1f}, "
          f"{len(b['trace'])} imagined actions" + ("   CHOSEN" if b['sid']==target['chosen_sid'] else ""))
