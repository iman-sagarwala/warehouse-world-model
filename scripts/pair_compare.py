"""Paired comparison of arms in an ablate_l2 CSV. Two instruments: t-test + sign test.

Usage:  python scripts/pair_compare.py <csv> <baseline_arm> <arm1> [arm2 ...]
Prints, for each arm vs the baseline: mean delta/day, SE, t, W/L/tie, sign-test p.
"""
import csv
import sys
from math import comb

import numpy as np


def paired(a, b):
    d = a - b
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else 0.0
    w = int((d > 0).sum()); l = int((d < 0).sum()); tie = int((d == 0).sum()); m = w + l
    p = sum(comb(m, k) for k in range(min(w, l) + 1)) / 2 ** (m - 1) if m else 1.0
    p = min(1.0, p)
    return d.mean(), se, (d.mean() / se if se else 0.0), w, l, tie, p


def main():
    path, base = sys.argv[1], sys.argv[2]
    arms = sys.argv[3:]
    rows = list(csv.DictReader(open(path)))
    col = lambda k: np.array([float(r[k]) for r in rows])
    b = col(f"{base}_on_time_value")
    print(f"n={len(rows)}  baseline {base} = {b.mean():.1f}/day")
    for arm in arms:
        a = col(f"{arm}_on_time_value")
        m, se, t, w, l, tie, p = paired(a, b)
        star = "" if p < 0.05 else "  (n.s. sign)"
        print(f"  {arm:16} {a.mean():7.1f}   d {m:+6.2f}/day  SE {se:4.2f}  t {t:+5.2f}  "
              f"W/L/tie {w}/{l}/{tie}  sign p={p:.4f}{star}")


if __name__ == "__main__":
    main()
