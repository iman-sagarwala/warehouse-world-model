"""viz_noise -- the simplest possible picture of the whole idea, for someone who's tired of words.

ACT 1: 60 task-dots drop in one by one, each at a wildly random height (its delay). Chaos.
       Then one smooth line is drawn = their running average -> it lands right on the hidden
       'real pace' curve. Message: one task = a dice roll (useless); average them = the truth appears.
ACT 2: two little crowds of arrows. Left: random directions -> they cancel -> go nowhere.
       Right: all lean the same way -> they add up -> go far. Message: random wiggles cancel;
       a steady lean compounds. (Why per-task delay is useless but the pace pad is powerful.)

Output: results/why_average.gif
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

INK, MUT, GRID = "#38382f", "#9a9a90", "#e2e1d8"
DOT, HOT, PACE = "#a9c2e0", "#eb6834", "#1baf7a"
BLUE = "#2a78d6"
rng = np.random.default_rng(7)

N = 60
tx = np.linspace(0.03, 0.97, N)
true_pace = 12 + 14 * np.exp(-(((tx - 0.5) / 0.17) ** 2))          # gentle midday hump
noise = rng.normal(0, 13, N)
delay = np.clip(true_pace + noise, -6, None)


def base_ax(fig):
    ax = fig.add_axes([0.08, 0.13, 0.88, 0.72])
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-12, 46)
    ax.set_xticks([])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUT, labelsize=9)
    ax.set_ylabel("how late a task was (steps)", color=MUT, fontsize=11)
    ax.axhline(0, color=GRID, lw=1)
    return ax


def draw_act1(k, phase, line_prog=0.0):
    """k dots shown; phase in {'dots','line','hold'}."""
    fig = plt.figure(figsize=(9.6, 5.6), dpi=115)
    fig.patch.set_facecolor("white")
    ax = base_ax(fig)
    if k > 0:
        ax.scatter(tx[:k], delay[:k], s=95, color=DOT, edgecolors="white",
                   linewidths=1.4, zorder=3)
    if phase == "dots" and 0 < k <= N:
        i = k - 1
        ax.scatter([tx[i]], [delay[i]], s=240, color=HOT, edgecolors="white",
                   linewidths=2, zorder=5)
        ax.annotate(f"this one task:  {delay[i]:+.0f}",
                    xy=(tx[i], delay[i]), xytext=(0.5, 41), ha="center",
                    color=INK, fontsize=17, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=HOT, lw=2))
        ax.set_title("Every task is late by a random amount - like a dice roll.",
                     color=INK, fontsize=15, loc="left", pad=14)
        fig.text(0.08, 0.03, "one task on its own tells you almost nothing",
                 color=MUT, fontsize=11)
    else:
        # rolling average line, revealed left->right by line_prog
        win = 9
        avg = np.convolve(delay, np.ones(win) / win, mode="same")
        m = max(1, int(line_prog * N))
        if phase in ("line", "hold"):
            ax.plot(tx[:N], true_pace, ls="--", color=MUT, lw=2, zorder=2)
            ax.plot(tx[:m], avg[:m], color=PACE, lw=5, zorder=4, solid_capstyle="round")
        if phase == "hold":
            ax.annotate("the average!", xy=(tx[N // 2], avg[N // 2]),
                        xytext=(0.62, 40), color=PACE, fontsize=17, fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color=PACE, lw=2.2))
            ax.text(0.03, -9.5, "dashed grey = the real pace, hidden in the mess",
                    color=MUT, fontsize=10)
            ax.set_title("Average them all -> the real pace appears.",
                         color=INK, fontsize=15, loc="left", pad=14)
            fig.text(0.08, 0.03, "the messy dots were hiding a smooth truth the whole time",
                     color=MUT, fontsize=11)
        else:
            ax.set_title("Now watch what the average does...",
                         color=INK, fontsize=15, loc="left", pad=14)
    return fig


def draw_act2(reveal):
    """reveal 0..1 across: left random arrows, then right same-way arrows, then labels."""
    fig = plt.figure(figsize=(9.6, 5.6), dpi=115)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.04, 0.08, 0.92, 0.8])
    ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
    ax.text(2.5, 5.6, "random wiggles", ha="center", color=INK, fontsize=15, fontweight="bold")
    ax.text(7.5, 5.6, "a steady lean", ha="center", color=INK, fontsize=15, fontweight="bold")
    ax.plot([5, 5], [0.3, 5.2], color=GRID, lw=2)
    na = 12
    # evenly spaced directions + small jitter -> they very nearly cancel (tiny resultant)
    ang = np.linspace(0, 2 * np.pi, na, endpoint=False) + rng.uniform(-0.18, 0.18, na)
    nL = min(na, int(reveal * na * 2))
    cx, cy = 2.5, 3.0
    ex = ey = 0.0
    for i in range(nL):
        dx, dy = 0.62 * np.cos(ang[i]), 0.62 * np.sin(ang[i])
        ax.annotate("", xy=(cx + dx, cy + dy), xytext=(cx, cy),
                    arrowprops=dict(arrowstyle="->", color=DOT, lw=2))
        ex += dx; ey += dy
    if nL >= na:
        ax.annotate("", xy=(cx + ex, cy + ey), xytext=(cx, cy),
                    arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=3.5))
        ax.text(2.5, 0.5, "they cancel -> go nowhere", ha="center",
                color=BLUE, fontsize=13, fontweight="bold")
    nR = min(na, max(0, int((reveal - 0.5) * na * 2)))
    bx, by = 6.0, 1.2
    for i in range(nR):
        ax.annotate("", xy=(bx + 0.62, by + i * 0.32), xytext=(bx, by + i * 0.32),
                    arrowprops=dict(arrowstyle="->", color="#f0a883", lw=2))
    if nR >= na:
        ax.annotate("", xy=(bx + 3.0, by + (na - 1) * 0.32 / 2), xytext=(bx, by + (na - 1) * 0.32 / 2),
                    arrowprops=dict(arrowstyle="-|>", color=PACE, lw=3.5))
        ax.text(7.6, 0.5, "they add up -> go FAR", ha="center",
                color=PACE, fontsize=13, fontweight="bold")
    fig.text(0.5, 0.955, "one task's delay = random (useless).   the day's pace = a steady lean (gold).",
             ha="center", color=MUT, fontsize=11.5)
    return fig


def fig_to_img(fig):
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(img.copy())


def main():
    os.makedirs("results", exist_ok=True)
    frames, durs = [], []
    # Act 1: dots drop in
    for k in range(1, N + 1, 2):
        frames.append(fig_to_img(draw_act1(k, "dots"))); durs.append(150)
    frames += [fig_to_img(draw_act1(N, "dots"))] * 2; durs += [500, 500]
    # Act 1: line draws
    for p in np.linspace(0.06, 1.0, 12):
        frames.append(fig_to_img(draw_act1(N, "line", p))); durs.append(120)
    frames += [fig_to_img(draw_act1(N, "hold", 1.0))] * 12; durs += [750] * 12
    # Act 2: arrows
    for r in np.linspace(0.05, 1.0, 20):
        frames.append(fig_to_img(draw_act2(r))); durs.append(160)
    frames += [fig_to_img(draw_act2(1.0))] * 12; durs += [750] * 12
    frames[0].save("results/why_average.gif", save_all=True, append_images=frames[1:],
                   duration=durs, loop=0)
    print(f"GIF: results/why_average.gif  ({len(frames)} frames)")


if __name__ == "__main__":
    main()
