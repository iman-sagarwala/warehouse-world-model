"""Quick: where the stream loses value (8x4), from measured numbers. champion -> deployed (sequencer+
value-rate) -> free-picker ceiling. The gap to the ceiling = the picker-CAPACITY flaw (structural)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

champ, deployed, ceil = 316.6, 332.4, 370.6      # stream 8x4, measured (results/stream_*, orc_stream_84)
labels = ["champion\n(old baseline)", "deployed\n(sequencer +\nvalue-rate pk)", "free-picker\nceiling"]
vals = [champ, deployed, ceil]
cols = ["#b5b4ab", "#1baf7a", "#eda100"]

fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=115); fig.patch.set_facecolor("white")
x = range(3)
ax.bar(x, vals, 0.6, color=cols, edgecolor="white", lw=1.5, zorder=3)
for i, v in zip(x, vals):
    ax.text(i, v + 1, f"{v:.0f}", ha="center", fontweight="bold", color="#40403e", fontsize=12)
ax.set_ylim(300, 385)

def bracket(x0, x1, y, txt, c):
    ax.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="<->", color=c, lw=1.8))
    ax.text((x0 + x1) / 2, y + 1.5, txt, ha="center", color=c, fontsize=9.5, fontweight="bold")

bracket(0, 1, 340, "decisions +16\n(≈ MAXED)", "#1baf7a")
bracket(1, 2, 352, "picker CAPACITY +38  (10.3% below perfect)\nTHE FLAW — needs pickers, not smarter rules", "#c0392b")
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9.5, color="#40403e")
ax.set_ylabel("on-time value ($/day, stream 8×4)", color="#8a8a82")
ax.set_title("Stream: the biggest flaw is picker CAPACITY during bursts — not the decision layer",
             fontsize=12, loc="left", fontweight="bold", color="#40403e")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.text(0.06, 0.01, "Decisions (sequencer+value-rate) already capture ~all their headroom on the stream; "
         "value-rate/urgency/anticipation all wash. The +38 to the ceiling is bursts overwhelming 4 pickers.",
         fontsize=8, color="#8a8a82")
fig.subplots_adjust(bottom=0.17, top=0.9)
fig.savefig("results/stream_flaws.png", facecolor="white")
print("PNG: results/stream_flaws.png")
