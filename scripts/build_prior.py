"""Build the context prior from the campaign's replay log.

For each tested config: how often each knob (P, theta, cap, alpha, depth, urgw, hyst) was moved
off its shipped value across all adoptions. A new warehouse gets a similarity-weighted blend of
its neighbours' knob frequencies (features: size index, dual flag, agvs, pickers), which the
m3mpc tuner uses as pseudo-counts to warm-start its UCB move ordering.

Output: results/context_prior.json
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = ["tiny", "small", "medium", "large", "extralarge"]
DEF = dict(P=1.5, th=0.40, cap=2, alpha=7.0, depth=5, urgw=0.0, hyst=20)
KNOBS = list(DEF)


def parse_cfg(cfg):
    import re
    m = re.match(r"^([a-z]+?)(dual)?-(\d+)-(\d+)$", cfg)
    if not m or m.group(1) not in SIZES:
        return None
    return dict(size=SIZES.index(m.group(1)), dual=1 if m.group(2) else 0,
                agvs=int(m.group(3)), pickers=int(m.group(4)))


def main():
    per = {}
    for row in csv.reader(open(os.path.join(ROOT, "results", "mpc_replay.csv"), encoding="utf-8")):
        if len(row) != 12 or row[0] == "config" or row[11] != "1":
            continue          # v2 adopted rows only
        cfg = row[0]
        vals = dict(P=float(row[3]), th=float(row[4]), cap=float(row[5]), alpha=float(row[6]),
                    depth=float(row[7]), urgw=float(row[8]), hyst=float(row[9]))
        d = per.setdefault(cfg, {"n": 0, **{k: 0 for k in KNOBS}})
        d["n"] += 1
        for k in KNOBS:
            if abs(vals[k] - DEF[k]) > 1e-9:
                d[k] += 1
    out = {}
    for cfg, d in per.items():
        f = parse_cfg(cfg)
        if not f or d["n"] < 20 or cfg in os.environ.get("EXCLUDE", "").split(","):
            continue
        out[cfg] = {"features": f, "n": d["n"],
                    "freq": {k: round(d[k] / d["n"], 4) for k in KNOBS}}
    path = os.path.join(ROOT, "results", "context_prior.json")
    json.dump(out, open(path, "w"), indent=1)
    print("prior over %d configs -> %s" % (len(out), path))
    for cfg, v in sorted(out.items()):
        top = sorted(v["freq"].items(), key=lambda kv: -kv[1])[:3]
        print("  %-22s n=%-5d top knobs: %s" % (cfg, v["n"],
              ", ".join("%s %.0f%%" % (k, 100 * f) for k, f in top if f > 0) or "none"))


if __name__ == "__main__":
    main()
