"""Builds the head-to-head report for the outside task-assignment baselines (2026-10-09).

Pairs the Token Passing / Hungarian arms in results/mapd/ against the existing champ, mpc, fifo and
rush arms in results/m5_bench_retired*.csv -- same 144 seeds, same regimes, same disturbance
conditions -- and writes:

    results/mapd/mapd_comparison.csv   one row per (condition, regime, arm): mean, margin vs every
                                       reference arm, paired t, episodes won
    results/mapd/MAPD_RESULTS.md       the same thing as a readable report

    python scripts/report_mapd.py
"""
from __future__ import annotations

import csv
import io
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SOURCES = {
    "clean":   ("results/m5_bench_retired.csv",         "results/mapd/mapd_clean.csv"),
    "disturb": ("results/m5_bench_disturb_retired.csv", "results/mapd/mapd_disturb.csv"),
}
# order matters: it is the order the report prints, weakest baseline first
ARMS = ["fifo", "tp", "hung", "rush", "hungv", "champ", "mpc"]
LABEL = {
    "fifo":  "FIFO (simulator's own)",
    "tp":    "Token Passing (Ma et al. 2017)",
    "hung":  "Hungarian, travel cost (CENTRAL)",
    "rush":  "RushValue (ours, weighted-tardiness)",
    "hungv": "Hungarian, on-time value (optimal myopic)",
    "champ": "Planner, fixed constants",
    "mpc":   "Planner + self-tuner (shipped)",
}
OUTSIDE = ("fifo", "tp", "hung", "hungv")     # not ours


def load(paths):
    """{(regime, arm): {seed: onv}} merged across the given CSVs."""
    out = {}
    for p in paths:
        full = os.path.join(ROOT, p)
        if not os.path.exists(full):
            continue
        for r in csv.DictReader(io.open(full, encoding="utf-8")):
            out.setdefault((r["regime"], r["arm"]), {})[int(r["seed"])] = float(r["onv"])
    return out


def paired(a, b):
    """(mean delta, pct, t, wins, n) for a over b, on seeds both ran."""
    s = sorted(set(a) & set(b))
    if len(s) < 3:
        return None
    d = [a[x] - b[x] for x in s]
    md = st.mean(d)
    sd = st.stdev(d)
    t = md / (sd / len(s) ** 0.5) if sd else float("inf")
    return md, 100.0 * md / st.mean(b[x] for x in s), t, sum(1 for x in d if x > 0), len(s)


def main():
    rows = []
    md = ["# Outside baselines: Token Passing and Hungarian assignment",
          "",
          "Every arm runs the **same world, the same 144 seeds, and the same execution layer** "
          "(routing, picker dispatch, mission state machine, dock choice). Only the task-assignment "
          "rule differs. `fifo`, `tp`, `hung`, `hungv` and `rush` run with **free energy** -- no "
          "battery constraint -- which is an advantage over `champ`/`mpc`, both of which pay the "
          "full charging cost.",
          "",
          "| arm | what it is | ours? |",
          "|---|---|---|"]
    for a in ARMS:
        md.append("| `%s` | %s | %s |" % (a, LABEL[a], "no" if a in OUTSIDE else "**yes**"))
    md += ["", "Token Passing and the travel-cost Hungarian are **deadline-blind by construction** -- "
               "MAPD and MRTA optimise service time and travel cost, not on-time value. `hungv` is "
               "the control for that: the identical exact solver, with the cost matrix set to "
               "projected on-time value, so it is an *optimal myopic* assignment on the paper's own "
               "objective.", ""]

    for cond, paths in SOURCES.items():
        data = load(paths)
        regimes = sorted({g for (g, _) in data}, reverse=True)
        for g in regimes:
            md += ["", "## %s floor, %s demand" % (cond.capitalize(), g), "",
                   "| arm | mean on-time value | vs FIFO | vs best outside baseline | t | won |",
                   "|---|---|---|---|---|---|"]
            present = [a for a in ARMS if (g, a) in data]
            # the strongest arm that is not ours -- the honest bar to clear
            outs = [a for a in present if a in OUTSIDE]
            best_out = max(outs, key=lambda a: st.mean(data[(g, a)].values())) if outs else None
            for a in present:
                me = data[(g, a)]
                mean = st.mean(me.values())
                vf = paired(me, data[(g, "fifo")]) if (g, "fifo") in data and a != "fifo" else None
                vb = (paired(me, data[(g, best_out)])
                      if best_out and a != best_out else None)
                md.append("| `%s` | %.2f | %s | %s | %s | %s |" % (
                    a, mean,
                    "--" if not vf else "%+.1f%%" % vf[1],
                    "--" if not vb else "%+.1f%%" % vb[1],
                    "--" if not vb else "%+.2f" % vb[2],
                    "--" if not vb else "%d/%d" % (vb[3], vb[4])))
                rows.append({
                    "condition": cond, "regime": g, "arm": a, "label": LABEL[a],
                    "ours": "no" if a in OUTSIDE else "yes",
                    "mean_onv": round(mean, 2), "n": len(me),
                    "vs_fifo_pct": "" if not vf else round(vf[1], 2),
                    "vs_fifo_t": "" if not vf else round(vf[2], 2),
                    "best_outside": best_out or "",
                    "vs_best_outside_pct": "" if not vb else round(vb[1], 2),
                    "vs_best_outside_t": "" if not vb else round(vb[2], 2),
                    "vs_best_outside_wins": "" if not vb else vb[3],
                })
            if best_out:
                md += ["", "Strongest arm that is not ours in this cell: **`%s`** (%.2f)."
                       % (best_out, st.mean(data[(g, best_out)].values()))]
                if (g, "mpc") in data:
                    v = paired(data[(g, "mpc")], data[(g, best_out)])
                    if v:
                        md.append("The shipped planner beats it by **%+.1f%%** "
                                  "(%+.2f value/episode, t = %+.2f, won %d of %d)."
                                  % (v[1], v[0], v[2], v[3], v[4]))

    out_csv = os.path.join(ROOT, "results/mapd/mapd_comparison.csv")
    with io.open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    out_md = os.path.join(ROOT, "results/mapd/MAPD_RESULTS.md")
    io.open(out_md, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("wrote", out_csv)
    print("wrote", out_md)
    print("\n".join(md))


if __name__ == "__main__":
    main()
