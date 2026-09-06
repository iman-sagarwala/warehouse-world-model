"""Sight-radius sweep for the belief arm (until-amnesty cell, timer amnesty, 48 seeds).

Bounds from the recorded block (same seeds): blind 826.58, clairvoyant 850.73.
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

RADII = [2, 3, 5, 8, 12]
BLIND, CLAIR = 826.58, 850.73

if __name__ == "__main__":
    os.environ["M2HOLD"] = "-1"
    import exp_m2_belief as E
    print("SIGHT-RADIUS SWEEP (until-amnesty transient, %d seeds; blind %.2f, clairvoyant %.2f)\n"
          % (len(E.SEEDS), BLIND, CLAIR))
    for r in RADII:
        os.environ["M2RADIUS"] = str(r)
        import importlib
        importlib.reload(E)
        jobs = [("belief", s) for s in E.SEEDS]
        with mp.Pool(8) as pool:
            rows = pool.map(E.one, jobs)
        vals = [v for _, _, v, _ in rows]
        hits = sum(h for _, _, _, h in rows)
        m = sum(vals) / len(vals)
        cap = 100.0 * (m - BLIND) / (CLAIR - BLIND)
        print("radius %-3d belief mean %8.2f  capture %5.1f%%  debris hits %d"
              % (r, m, cap, hits))
