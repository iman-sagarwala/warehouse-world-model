"""Graph the dense-map ladder from results/dense_ladder.csv -> results/dense_ladder.png"""
import csv
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = list(csv.DictReader(open("results/dense_ladder.csv")))
ARMS = ["fifo", "rush", "champion"]
LABEL = {"fifo": "FIFO", "rush": "rush\n(value greedy)", "champion": "CHAMPION v5\n(rollout + dispatch stack)"}
COLOR = {"fifo": "#9aa5b1", "rush": "#c9821f", "champion": "#2f6f8f"}

V = {a: [] for a in ARMS}
MX = {a: 0 for a in ARMS}
FR = {a: 0 for a in ARMS}
for r in rows:
    V[r["arm"]].append(float(r["on_time_value"]))
    MX[r["arm"]] = max(MX[r["arm"]], int(r["max_wait"]))
    FR[r["arm"]] += int(r["frozen"])

fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.6), dpi=160,
                              gridspec_kw={"width_ratios": [1.4, 1]})
fig.patch.set_facecolor("#f6f7f8")

means = [st.mean(V[a]) for a in ARMS]
sems = [st.stdev(V[a]) / len(V[a]) ** 0.5 for a in ARMS]
bars = ax.bar(range(3), means, 0.62, yerr=sems, capsize=4,
              color=[COLOR[a] for a in ARMS], edgecolor="white")
for i, a in enumerate(ARMS):
    ax.text(i, means[i] + sems[i] + 8, "%.1f" % means[i], ha="center", fontsize=11,
            weight="bold", color="#171b20")
    pct = "" if a == "fifo" else "+%.1f%% vs FIFO" % (100 * (means[i] - means[0]) / means[0])
    if pct:
        ax.text(i, means[i] / 2, pct, ha="center", fontsize=9, color="white", weight="bold")
ax.set_xticks(range(3))
ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=9.5)
ax.set_ylabel("on-time value (mean of 144 paired seeds)", fontsize=9)
ax.set_title("DENSE MAP LADDER — champion vs rush t=+10.15\nsame v5 env stack for every arm",
             fontsize=10.5, family="monospace")
ax.grid(True, axis="y", color="#e3e7ea", lw=0.6)
ax.set_axisbelow(True)
for s_ in ax.spines.values():
    s_.set_color("#e3e7ea")

x = range(3)
b1 = ax2.bar([i - 0.2 for i in x], [MX[a] for a in ARMS], 0.36, color="#a3302c",
             edgecolor="white", label="worst single wait (steps)")
b2 = ax2.bar([i + 0.2 for i in x], [FR[a] for a in ARMS], 0.36, color="#5b6672",
             edgecolor="white", label="frozen AGVs (sum/144 eps)")
for i, a in enumerate(ARMS):
    ax2.text(i - 0.2, MX[a] + 6, str(MX[a]), ha="center", fontsize=9, color="#a3302c", weight="bold")
    ax2.text(i + 0.2, FR[a] + 6, str(FR[a]), ha="center", fontsize=9, color="#5b6672", weight="bold")
ax2.set_xticks(range(3))
ax2.set_xticklabels([LABEL[a] for a in ARMS], fontsize=9.5)
ax2.set_title("LIVENESS — the decision layer is part of it\nFIFO/rush freeze even on the v5 env stack",
              fontsize=10.5, family="monospace")
ax2.legend(fontsize=8, frameon=False)
ax2.grid(True, axis="y", color="#e3e7ea", lw=0.6)
ax2.set_axisbelow(True)
for s_ in ax2.spines.values():
    s_.set_color("#e3e7ea")

fig.tight_layout()
fig.savefig("results/dense_ladder.png", bbox_inches="tight", facecolor=fig.get_facecolor())
print("wrote results/dense_ladder.png")
