"""GIF: closed-loop (re-plan every decision) vs open-loop (commit the whole imagined plan) —
REAL executed days, same world (seed 3). The gap between the curves IS the re-planning benefit,
cleanly isolated. Orange ticks mark where the open-loop's script broke and forced a re-plan.
Output: results/openloop.gif
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
from congestion_policies import _SqWide, _OpenLoop

SEED = int(os.environ.get("SEED", "3"))


def episode(factory, tag):
    env = gym.make("wwm_sim-large-8agvs-4pickers-globalobs-v1").unwrapped
    env.reset(seed=SEED)
    env.request_queue = []
    env.demand_model = DemandModel(env, seed=SEED)
    env.demand_model.seed_day_list(env, horizon=500)
    c = factory(env)
    events = []
    replans = []
    if tag == "open":
        orig = c._pick_winner
        def pw(scored, _o=orig):
            before = c._replans
            r = _o(scored)
            if c._replans > before:
                replans.append(int(c.timestep))
            return r
        c._pick_winner = pw
    t = 0
    done = False
    while not done and t < 500:
        _, _, term, trunc, _i = env.step(c.act())
        t += 1
        for o in getattr(env, "fulfilled_this_step", []):
            on = o.deadline is not None and t <= o.deadline
            events.append((t, o.shelf.id, o.value if on else 0.0))
        done = all(term) or all(trunc)
    stats = (getattr(c, "_follows", None), getattr(c, "_replans", None))
    return events, replans, stats


closed_ev, _, _ = episode(_SqWide, "closed")
open_ev, open_replans, (fol, rep) = episode(_OpenLoop, "open")
ct = sum(e[2] for e in closed_ev)
ot = sum(e[2] for e in open_ev)
print(f"closed-loop {ct:.1f} | open-loop {ot:.1f} | re-planning benefit {ct-ot:+.1f}")
print(f"open-loop: {fol} scripted follows, {rep} forced re-plans")


def cum(events, T):
    xs, ys = [0], [0.0]
    s = 0.0
    for (tt, sid, bank) in sorted(events):
        if tt > T:
            break
        xs += [tt, tt]
        ys += [s, s + bank]
        s += bank
    xs.append(T)
    ys.append(s)
    return xs, ys, s


from matplotlib.animation import PillowWriter
fig, (axc, axg) = plt.subplots(2, 1, figsize=(11, 6.8), height_ratios=[2.2, 1],
                               gridspec_kw={"hspace": 0.35})
writer = PillowWriter(fps=4)
top = max(ct, ot) * 1.1
Ts = list(np.arange(0, 505, 6)) + [500] * 8
with writer.saving(fig, "results/openloop.gif", dpi=90):
    for T in Ts:
        axc.clear(); axg.clear()
        xc, yc, sc = cum(closed_ev, T)
        xo, yo, so = cum(open_ev, T)
        axc.plot(xc, yc, color="#1a9641", lw=2.6,
                 label=f"CLOSED-LOOP (re-plan every decision)  ⇒ {ct:.0f}")
        axc.plot(xo, yo, color="#e08214", lw=2.0,
                 label=f"OPEN-LOOP (execute the committed plan)  ⇒ {ot:.0f}")
        for rt in open_replans:
            if rt <= T:
                axc.axvline(rt, color="#e08214", lw=0.6, alpha=0.35)
        axc.axvline(T, color="grey", lw=0.7, ls=":")
        axc.set_xlim(0, 505); axc.set_ylim(0, top)
        axc.set_ylabel("cumulative banked value (REAL)")
        axc.set_title(f"The re-planning benefit, isolated — seed {SEED} · both days real, same world · "
                      f"orange ticks = script broke, forced re-plan ({rep} total)")
        axc.legend(loc="upper left", fontsize=9)
        axc.grid(alpha=0.25)
        gxs = np.arange(0, min(T, 500) + 1, 4)
        gys = [cum(closed_ev, g)[2] - cum(open_ev, g)[2] for g in gxs]
        axg.fill_between(gxs, gys, color="#1a9641", alpha=0.35)
        axg.axhline(0, color="grey", lw=0.6)
        axg.set_xlim(0, 505)
        axg.set_ylim(min(min(gys) - 3, -3), max(max(gys) + 3, 3))
        axg.set_xlabel("step in the day")
        axg.set_ylabel("closed − open")
        axg.set_title("running re-planning benefit", fontsize=9)
        axg.grid(alpha=0.25)
        writer.grab_frame()
plt.close(fig)
print("wrote results/openloop.gif")
