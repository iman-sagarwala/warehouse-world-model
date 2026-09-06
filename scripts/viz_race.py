"""viz_race -- why you can't know your delay even knowing EVERYTHING right now.

Same present moment, shown twice. The only difference: robot B moves one step sooner in the
right-hand future. That one nudge decides which future's robot wins the picker -- and your wait
flips from 3 to 25. The delay was never sitting in the present state; it gets MADE later by a
race, and a hair's difference flips who wins. So perfect knowledge of now can't contain it.

Output: results/why_race.gif
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

INK, MUT, GRID = "#38382f", "#9a9a90", "#e4e3da"
YOU, BOT, PICK, SHELF, HOT, GOOD, BAD = "#2a78d6", "#8a8a82", "#1baf7a", "#e8e7de", "#eb6834", "#1baf7a", "#e34948"
GX, GY = 10, 6


def path(wps, ts, T):
    """position at each of T frames, piecewise-linear through waypoints wps at frames ts, held after."""
    out = []
    for f in range(T):
        if f <= ts[0]:
            out.append(wps[0]); continue
        if f >= ts[-1]:
            out.append(wps[-1]); continue
        for i in range(len(ts) - 1):
            if ts[i] <= f <= ts[i + 1]:
                a = (f - ts[i]) / max(1, (ts[i + 1] - ts[i]))
                x = wps[i][0] + a * (wps[i + 1][0] - wps[i][0])
                y = wps[i][1] + a * (wps[i + 1][1] - wps[i][1])
                out.append((x, y)); break
    return out


T = 16
ARRIVE = 3          # frame your robot reaches its shelf and starts waiting
# YOUR robot: drive to your shelf at (5,3), then wait there
you = path([(1, 3), (5, 3)], [0, ARRIVE], T)
# --- FUTURE A: picker P1 comes straight to you -> loaded fast (wait 3) ---
A = {
    "P1": path([(5, 0), (5, 3)], [0, ARRIVE + 1], T),         # down to your shelf
    "B": path([(2, 5), (2, 5), (7, 5)], [0, 6, 12], T),       # B dawdles, leaves late
    "P2": path([(0, 0), (0, 0)], [0, T], T),                  # P2 idle
}
A_LOAD = ARRIVE + 1
# --- FUTURE B: B moves 1 step sooner, grabs P1 -> you wait for far P2 (wait 25) ---
B = {
    "P1": path([(5, 0), (7, 5)], [0, 10], T),                 # P1 diverts to B's shelf
    "B": path([(2, 5), (7, 5)], [0, 9], T),                   # B leaves early -> wins P1
    "P2": path([(0, 0), (5, 3)], [2, 15], T),                 # P2 crawls over from far corner
}
B_LOAD = 15


def draw_panel(ax, actors, fr, load_frame, wait_num, title, tcol, forked):
    ax.set_xlim(-0.6, GX - 0.4); ax.set_ylim(-0.6, GY - 0.4)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
    for s in ax.spines.values():
        s.set_color(GRID)
    for gx in range(GX):
        for gy in range(GY):
            ax.plot(gx, gy, ".", color=GRID, ms=3, zorder=0)
    # shelves
    ax.add_patch(plt.Rectangle((5 - .42, 3 - .42), .84, .84, color=SHELF, zorder=1))   # your shelf
    ax.add_patch(plt.Rectangle((7 - .42, 5 - .42), .84, .84, color=SHELF, zorder=1))   # B's shelf
    loaded = fr >= load_frame
    # your robot
    yx, yy = actors_you[fr]
    ax.add_patch(plt.Rectangle((yx - .38, yy - .38), .76, .76,
                               color=GOOD if loaded else YOU, ec="white", lw=2, zorder=5))
    ax.text(yx, yy, "YOU", ha="center", va="center", color="white", fontsize=8, fontweight="bold", zorder=6)
    # other robot B
    bx, by = actors["B"][fr]
    ax.add_patch(plt.Rectangle((bx - .36, by - .36), .72, .72, color=BOT, ec="white", lw=2, zorder=4))
    ax.text(bx, by, "B", ha="center", va="center", color="white", fontsize=9, fontweight="bold", zorder=6)
    # pickers
    for nm, col in (("P1", PICK), ("P2", PICK)):
        px, py = actors[nm][fr]
        ax.scatter([px], [py], marker="^", s=190, color=col, ec="white", linewidths=1.6, zorder=5)
    # fork flash on B
    if forked and ARRIVE <= fr <= ARRIVE + 3:
        ax.scatter([actors["B"][fr][0]], [actors["B"][fr][1]], s=900, facecolors="none",
                   edgecolors=HOT, linewidths=3, zorder=7)
    # wait / loaded readout
    if loaded:
        ax.text(0.5, 5.4, f"LOADED  (waited {wait_num})", color=GOOD, fontsize=13,
                fontweight="bold", zorder=8)
    elif fr >= ARRIVE:
        w = int(round((fr - ARRIVE) / max(1, load_frame - ARRIVE) * wait_num))
        ax.text(0.5, 5.4, f"waiting... {w}", color=BAD if wait_num > 10 else MUT,
                fontsize=13, fontweight="bold", zorder=8)
    ax.set_title(title, color=tcol, fontsize=13, fontweight="bold", loc="left")


def frame(fr, present=False):
    global actors_you
    actors_you = you
    fig = plt.figure(figsize=(10.2, 5.2), dpi=115)
    fig.patch.set_facecolor("white")
    axA = fig.add_axes([0.04, 0.08, 0.44, 0.76])
    axB = fig.add_axes([0.53, 0.08, 0.44, 0.76])
    if present:
        banner = "The EXACT same present moment - you know every position, route, and picker."
        draw_panel(axA, A, 0, 99, 3, "one possible future  (A)", MUT, False)
        draw_panel(axB, B, 0, 99, 25, "another possible future  (B)", MUT, False)
    else:
        banner = "Only difference: in B, robot B leaves ONE STEP sooner -> it wins the picker."
        draw_panel(axA, A, fr, A_LOAD, 3, "future A", GOOD, False)
        draw_panel(axB, B, fr, B_LOAD, 25, "future B", BAD, True)
    fig.text(0.5, 0.95, banner, ha="center", color=INK, fontsize=12.5, fontweight="bold")
    fig.text(0.5, 0.9, "green triangle = picker (must reach your shelf to load you)",
             ha="center", color=MUT, fontsize=9.5)
    return fig


def card(lines):
    fig = plt.figure(figsize=(10.2, 5.2), dpi=115)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.text(0.5, 0.9, "So why can't you know your delay?", ha="center",
            color=INK, fontsize=18, fontweight="bold")
    y = 0.72
    for txt, col, sz in lines:
        ax.text(0.5, y, txt, ha="center", color=col, fontsize=sz,
                fontweight="bold" if sz >= 15 else "normal")
        y -= 0.135
    return fig


def fig_to_img(fig):
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    frames, durs = [], []
    frames.append(fig_to_img(frame(0, present=True))); durs.append(2600)
    for fr in range(T):
        frames.append(fig_to_img(frame(fr))); durs.append(320)
    frames.append(fig_to_img(frame(T - 1))); durs.append(3000)
    c1 = fig_to_img(card([
        ("The present was fully known - and it still didn't contain the answer.", INK, 15),
        ("Your delay isn't a hidden number sitting in 'now'.", MUT, 13),
        ("It gets MADE later, by who wins a race that hasn't run yet.", HOT, 14),
        ("A one-step nudge flips it: 3  or  25.", INK, 15),
    ]))
    c2 = fig_to_img(card([
        ("And the NEXT task is a brand-new race,", INK, 15),
        ("with different robots and different pickers.", MUT, 13),
        ("Knowing this task waited 3 tells you nothing about it.", HOT, 14),
        ("That's why per-task delay never adds up - each one is its own coin.", INK, 14),
    ]))
    frames += [c1, c2]
    durs += [4200, 4200]
    frames[0].save("results/why_race.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/why_race.gif  ({len(frames)} frames)")


if __name__ == "__main__":
    main()
