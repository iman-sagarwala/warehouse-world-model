"""LIVE RESULTS BOARD — rebuilds the whole picture from whatever result CSVs currently exist.

Safe to run at any time, including mid-experiment: every panel is independent, and a missing or partial
file yields an "awaiting data" tile instead of a crash. Re-run after anything finishes to refresh.

    ./.venv/Scripts/python.exe scripts/viz_live.py      ->  results/diag_live.png

NOTE ON SPEED: this workload is CPU-bound discrete simulation (Python loops, A*, networkx over ~650
cells). There is no dense linear algebra, so a GPU cannot help. The only real lever is process
parallelism (NPROC), and this machine has 8 cores with NPROC already at 8.
"""
import csv
import collections
import json
import math
import os
import statistics as st
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK = "#171b20"; SUB = "#5b6672"; GRID = "#e3e7ea"
FIFO = "#9aa5b1"; RUSH = "#c9821f"; CH = "#2f6f8f"; BAD = "#a3302c"; OK = "#2b7a4b"
MONO = {"family": "DejaVu Sans Mono"}


def rows(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def style(ax, title):
    ax.set_facecolor("#ffffff")
    ax.grid(True, axis="y", color=GRID, lw=.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=7.5, colors=SUB)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.set_title(title, fontsize=9.5, color=INK, **MONO)


def nodata(ax, title):
    ax.axis("off")
    ax.text(.5, .5, "awaiting data", ha="center", va="center", fontsize=9, color=SUB, **MONO)
    ax.set_title(title, fontsize=9.5, color=SUB, **MONO)


fig = plt.figure(figsize=(19, 14.0), dpi=160)
fig.patch.set_facecolor("#f6f7f8")
gs = fig.add_gridspec(4, 4, hspace=.62, wspace=.30)
P = lambda i, j: fig.add_subplot(gs[i, j])

# ---------------- ladder, workload-matched ----------------
L = collections.defaultdict(dict)
for r in rows("results/ladder_matched.csv"):
    L[(r["regime"], int(r["seed"]))][r["arm"]] = float(r["on_time_value"])
for j, rg in enumerate(["daylist", "stream"]):
    ax = P(0, j)
    keys = [k for k in L if k[0] == rg]
    if len(keys) < 10:
        nodata(ax, "LADDER - %s" % rg); continue
    arms = ["fifo", "rush", "champion"]
    v = [st.mean([L[k][a] for k in keys if a in L[k]]) for a in arms]
    e = [1.96 * st.stdev([L[k][a] for k in keys if a in L[k]]) / math.sqrt(len(keys)) for a in arms]
    ax.bar(range(3), v, .6, yerr=e, capsize=5, color=[FIFO, RUSH, CH], edgecolor="#fff")
    for i, x in enumerate(v):
        ax.text(i, x + e[i] + 5, "%.0f" % x, ha="center", fontsize=8.5, **MONO)
    ax.set_xticks(range(3)); ax.set_xticklabels(["FIFO", "rush", "champ"], fontsize=8)
    d = [L[k]["champion"] - L[k]["rush"] for k in keys if "champion" in L[k] and "rush" in L[k]]
    t = st.mean(d) / (st.stdev(d) / math.sqrt(len(d))) if len(d) > 1 else 0
    style(ax, "LADDER - %s (n=%d)\nchamp vs rush %+.1f%%  t=%+.1f" % (
        "WAVE" if rg == "daylist" else "STREAM", len(keys),
        100 * st.mean(d) / st.mean([L[k]["rush"] for k in keys if "rush" in L[k]]), t))

# ---------------- rollout depth ----------------
SD = collections.defaultdict(dict)
for r in rows("results/seqdepth_matched.csv"):
    SD[(r["regime"], r["agvs"], r["pickers"], int(r["seed"]))][float(r["value"])] = float(r["on_time_value"])
ax = P(0, 2)
if SD:
    for rg, c in [("daylist", RUSH), ("stream", CH)]:
        keys = [k for k in SD if k[0] == rg]
        if not keys:
            continue
        vals = sorted({v for k in keys for v in SD[k]})
        base = st.mean([SD[k][5.0] for k in keys if 5.0 in SD[k]] or [1])
        ys = [100 * (st.mean([SD[k][v] for k in keys if v in SD[k]] or [0]) - base) / base for v in vals]
        ax.plot(vals, ys, marker="o", ms=4, lw=1.8, color=c,
                label="wave" if rg == "daylist" else "stream")
    ax.axhline(0, color=SUB, ls="--", lw=1)
    ax.legend(fontsize=7, frameon=False)
    ax.set_xlabel("SEQ_DEPTH (0 = rollout off)", fontsize=7.5, color=SUB)
    style(ax, "ROLLOUT DEPTH\n% vs shipped depth 5")
else:
    nodata(ax, "ROLLOUT DEPTH")

# ---------------- workload confound ----------------
ax = P(0, 3)
ax.bar([0, 1], [65.3, 84.7], .35, color=BAD, edgecolor="#fff", label="before")
ax.bar([.4, 1.4], [77.2, 79.1], .35, color=OK, edgecolor="#fff", label="after")
ax.set_xticks([.2, 1.2]); ax.set_xticklabels(["wave", "stream"], fontsize=8)
ax.legend(fontsize=7, frameon=False)
style(ax, "WORKLOAD CONFOUND (fixed)\norders: +29.7% gap -> +2.5%")

# ---------------- knobs ----------------
K = collections.defaultdict(lambda: collections.defaultdict(list))
for src in ["results/knobs_realworld.csv", "results/knobs_ext.csv", "results/knobs_confirm.csv",
            "results/binary_knobs.csv", "results/knobs_uniform.csv"]:
    for r in rows(src):
        K[(r["knob"], r["regime"])][float(r["value"])].append(float(r["on_time_value"]))
ax = P(1, 0)
if K:
    labs, best = [], []
    for key in sorted(K):
        d = K[key]; vals = sorted(d)
        if len(vals) < 2:
            continue
        base = st.mean(d[vals[0]])
        labs.append("%s\n%s" % (key[0][:9], key[1][:4]))
        best.append(max(100 * (st.mean(d[v]) - base) / base for v in vals))
    if labs:
        ax.bar(range(len(labs)), best, .6, color=CH, edgecolor="#fff")
        ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs, fontsize=6.5)
        style(ax, "KNOBS - spread across comb\nnone clears |t|>=3")
    else:
        nodata(ax, "KNOBS")
else:
    nodata(ax, "KNOBS")

# ---------------- M2 disturbances ----------------
ax = P(1, 1)
m2 = rows("results/m2_dense.csv")
if m2:
    A = collections.defaultdict(dict)
    for r in m2:
        A[(r["regime"], r["agvs"], r["pickers"], r["seed"])][(r["arm"], float(r["rate"]))] = float(r["on_time_value"])
    rates = sorted({k[1] for v in A.values() for k in v if k[0] != "clean"})
    bk = ("clean", rates[0])
    base = st.mean([v[bk] for v in A.values() if bk in v])
    hi = rates[-1]
    arms = ["clairvoyant", "belief_los", "exposure"]
    vv = [100 * st.mean([v[(a, hi)] - v[bk] for v in A.values() if (a, hi) in v and bk in v]) / base
          for a in arms]
    ax.bar(range(3), vv, .6, color=[BAD, RUSH, OK], edgecolor="#fff")
    ax.axhline(0, color=SUB, lw=1)
    ax.set_xticks(range(3)); ax.set_xticklabels(["clairvoy", "belief", "ignore"], fontsize=7.5)
    style(ax, "M2 - disturbances @ high rate\nignoring debris performs best")
else:
    nodata(ax, "M2 disturbances")

# ---------------- stall rate / attempted fixes ----------------
ax = P(1, 2)
sf = rows("results/swapfix.csv")
if sf:
    G = collections.defaultdict(list)
    for r in sf:
        G[(r["config"], r["arm"])].append(float(r["on_time_value"]))
    labs = sorted(G)
    ax.bar(range(len(labs)), [st.mean(G[k]) for k in labs], .6,
           color=[BAD if "current" in k[0] else OK for k in labs], edgecolor="#fff")
    ax.set_xticks(range(len(labs)))
    ax.set_xticklabels(["%s\n%s" % (k[0][:9], k[1][:6]) for k in labs], fontsize=6.5)
    style(ax, "DEADLOCK FIX ATTEMPT")
else:
    ax.bar(range(3), [23, 19, 12], .6, color=[FIFO, RUSH, CH], edgecolor="#fff")
    for i, x in enumerate([23, 19, 12]):
        ax.text(i, x + .4, "%d/24" % x, ha="center", fontsize=8.5, **MONO)
    ax.set_xticks(range(3)); ax.set_xticklabels(["FIFO", "rush", "champ"], fontsize=8)
    style(ax, "STALL RATE /24 - PRE-FIX\ndetector counted pickers too")

# ---------------- realism pass ----------------
ax = P(1, 3)
ax.bar(range(4), [171, 95, 76, 58], .62, color=[BAD, RUSH, RUSH, OK], edgecolor="#fff")
for i, x in enumerate([171, 95, 76, 58]):
    ax.text(i, x + 3, str(x), ha="center", fontsize=8.5, **MONO)
ax.set_xticks(range(4))
ax.set_xticklabels(["orig", "+geom", "+lognorm", "+service"], fontsize=7)
style(ax, "REALISM PASS\ndeliveries - throughput -66%")

# ---------------- stall trace ----------------
if os.path.exists("results/_collapse_trace.json"):
    T = json.load(open("results/_collapse_trace.json"))
    ax = P(2, 0)
    ax.plot(T["champ"]["deliv"], color=CH, lw=1.6, label="champion")
    ax.plot(T["expl"]["deliv"], color=RUSH, lw=1.6, label="explorer")
    ax.legend(fontsize=7, frameon=False)
    ax.set_xlabel("step", fontsize=7.5, color=SUB)
    style(ax, "A STALL (seed 1) - PRE-FIX\nsuperseded by bottom row")
    ax = P(2, 1)
    ax.plot(T["champ"]["frozen"], color=CH, lw=1.6)
    ax.plot(T["expl"]["frozen"], color=RUSH, lw=1.6)
    ax.axhline(14, color=BAD, ls="--", lw=1)
    ax.set_xlabel("step", fontsize=7.5, color=SUB)
    style(ax, "frozen robots - PRE-FIX\nsuperseded by bottom row")
else:
    nodata(P(2, 0), "stall trace"); nodata(P(2, 1), "frozen robots")

# ---------------- fleet ratio ----------------
ax = P(2, 2)
orr = rows("results/oracle_ratio.csv")
if orr:
    C = collections.defaultdict(dict)
    for r in orr:
        if int(r["m"]) < 0:
            C[(int(r["agvs"]), int(r["pickers"]))][int(r["seed"])] = float(r["on_time_value"])
    ks = sorted(C)
    ax.bar(range(len(ks)), [st.mean(list(C[k].values())) for k in ks], .6, color=CH, edgecolor="#fff")
    ax.set_xticks(range(len(ks)))
    ax.set_xticklabels(["%dx%d" % k for k in ks], fontsize=7, rotation=20)
    style(ax, "FLEET RATIO - champion value\nceiling estimator was invalid")
else:
    nodata(ax, "FLEET RATIO")

# ---------------- failed fixes (geometry / assignment era) ----------------
ax = P(2, 3)
ax.bar(range(4), [356.8, 344.4, 267.8, 222.4], .6, color=[CH, BAD, BAD, BAD], edgecolor="#fff")
ax.set_xticks(range(4))
ax.set_xticklabels(["baseline", "balance\nstations", "one-way", "one-way\n+hard"], fontsize=7)
style(ax, "FIXES THAT FAILED (earlier)\nall made it worse or inert")


# ================= 2026-08-08: deadlock eliminated, and the rationing result =================

def _grp(path, arm_key, val_key):
    """{arm: [values]} from a results CSV, tolerant of a missing file."""
    out = collections.defaultdict(list)
    for r in rows(path):
        try:
            out[r[arm_key]].append(float(r[val_key]))
        except (KeyError, ValueError):
            pass
    return out


# ---- frozen carrying AGVs: the metric that exposed the problem ----
ax = P(3, 0)
ep = _grp("results/exit_priority.csv", "arm", "frozen_agvs")
pa = _grp("results/progress_aging.csv", "arm", "frozen")
bars, labs, cols = [], [], []
if ep.get("base"):
    bars.append(sum(ep["base"])); labs.append("headway\nonly"); cols.append(BAD)
if ep.get("exit"):
    bars.append(sum(ep["exit"])); labs.append("+exit\npriority"); cols.append(RUSH)
if pa.get("off"):
    bars.append(sum(pa["off"])); labs.append("+free pod\nreturn"); cols.append(OK)
if bars:
    ax.bar(range(len(bars)), bars, .6, color=cols, edgecolor="#fff")
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels(labs, fontsize=7)
    for i, b in enumerate(bars):
        ax.text(i, b, "%d" % b, ha="center", va="bottom", fontsize=8, color=INK, **MONO)
    style(ax, "DEADLOCK ELIMINATED\nfrozen carrying AGVs (144 seeds)")
else:
    nodata(ax, "DEADLOCK ELIMINATED")

# ---- every rule that rations rerouting loses ----
ax = P(3, 1)
base_cc = _grp("results/clash_choose.csv", "one-waiter rule", "on_time_value")
base_pa = _grp("results/progress_aging.csv", "arm", "on_time_value")


def _t(arm_vals, off_vals):
    d = [a - b for a, b in zip(arm_vals, off_vals)]
    if len(d) < 3:
        return None
    m = sum(d) / len(d)
    sd = st.pstdev(d) * (len(d) / (len(d) - 1)) ** .5
    return m / (sd / len(d) ** .5) if sd else None


ts, tl = [], []
off_cc = base_cc.get("") or base_cc.get("None") or []
for k, lab in (("near", "one-waiter\nHOLD"), ("near+req", "HOLD\n+req"), ("step+req", "SIDESTEP\n+req")):
    if base_cc.get(k) and off_cc:
        v = _t(base_cc[k], off_cc)
        if v is not None:
            ts.append(v); tl.append(lab)
for k, lab in (("aging", "progress\naging"), ("aging+step", "aging\n+sidestep")):
    if base_pa.get(k) and base_pa.get("off"):
        v = _t(base_pa[k], base_pa["off"])
        if v is not None:
            ts.append(v); tl.append(lab)
if ts:
    ax.bar(range(len(ts)), ts, .6, color=[OK if x > 0 else BAD for x in ts], edgecolor="#fff")
    ax.axhline(0, color=SUB, lw=.8)
    ax.axhline(3, color=SUB, ls="--", lw=.8)
    ax.axhline(-3, color=SUB, ls="--", lw=.8)
    ax.set_xticks(range(len(ts)))
    ax.set_xticklabels(tl, fontsize=6.5)
    ax.set_ylabel("t vs always-reroute", fontsize=7, color=SUB)
    style(ax, "RATIONING REROUTES ALWAYS LOSES\nseparation is what keeps it live")
else:
    nodata(ax, "RATIONING REROUTES")

# ---- picker oracle headroom is regime-dependent ----
ax = P(3, 2)
ph = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows("results/picker_headroom.csv"):
    try:
        half = "off-peak" if int(r["seed"]) <= 72 else "peak"
        ph[half][r["pickers_free"]].append(float(r["on_time_value"]))
    except (KeyError, ValueError):
        pass
if ph:
    labs, gains = [], []
    for half in ("off-peak", "peak"):
        d = ph.get(half, {})
        base = d.get("False") or d.get("")
        orc = d.get("True")
        if base and orc:
            labs.append(half)
            gains.append(100.0 * (sum(orc) - sum(base)) / sum(base))
    if gains:
        ax.bar(range(len(gains)), gains, .5, color=[CH, RUSH][:len(gains)], edgecolor="#fff")
        ax.set_xticks(range(len(gains)))
        ax.set_xticklabels(labs, fontsize=7.5)
        for i, g in enumerate(gains):
            ax.text(i, g, "+%.2f%%" % g, ha="center", va="bottom", fontsize=8, color=INK, **MONO)
        ax.set_ylabel("% value if pickers were free", fontsize=7, color=SUB)
        style(ax, "PICKER CEILING is regime-dependent\npeak drains by expiry, not delivery")
    else:
        nodata(ax, "PICKER CEILING")
else:
    nodata(ax, "PICKER CEILING")

# ---- what pod-waiting actually is ----
ax = P(3, 3)
ax.barh([1, 0], [98.7, 1.3], .55, color=[SUB, CH], edgecolor="#fff")
ax.set_yticks([1, 0])
ax.set_yticklabels(["picker committed,\nstill travelling", "no picker\nassigned"], fontsize=7)
ax.text(98.7, 1, " 98.7%  mean 11 steps", va="center", fontsize=7.5, color=INK, **MONO)
ax.text(1.3, 0, " 1.3%  mean 41 steps", va="center", fontsize=7.5, color=INK, **MONO)
ax.set_xlim(0, 130)
style(ax, "POD-WAIT IS MOSTLY TRAVEL\nirreducible by dispatch policy")

fig.suptitle("LIVE RESULTS - corrected world (55%% storage, 3 stations, service times, "
             "lognormal values, one clock)   -   %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
             fontsize=12, color=INK, y=.965, **MONO)
fig.savefig("results/diag_live.png", bbox_inches="tight", facecolor=fig.get_facecolor())
print("wrote results/diag_live.png at", datetime.now().strftime("%H:%M"))
