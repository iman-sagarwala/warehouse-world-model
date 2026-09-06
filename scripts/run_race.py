"""Run a FRESH fixed-vs-MPC race on demand and open the side-by-side viewer.

Usage:
  python scripts/run_race.py                      # random seed, large-12-8
  python scripts/run_race.py --config extralarge-16-9 --seed 91

Runs both arms on the identical 500-step world (~4-6 min), merges the race into
results/races.json (existing races are kept), rebuilds results/wwm_sandbox.html, and
opens it in the default browser on the Race tab.
"""
import argparse
import io
import json
import os
import random
import sys
import webbrowser
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_html():
    tpl = io.open(os.path.join(ROOT, "results", "wwm_sandbox_template.html"),
                  encoding="utf-8").read()
    data = io.open(os.path.join(ROOT, "results", "sim_data.json"), encoding="utf-8").read()
    races_path = os.path.join(ROOT, "results", "races.json")
    races = io.open(races_path, encoding="utf-8").read() if os.path.exists(races_path) else "{}"
    out = os.path.join(ROOT, "results", "wwm_sandbox.html")
    io.open(out, "w", encoding="utf-8").write(
        tpl.replace("__DATA__", data).replace("__RACES__", races))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="large-12-8")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.randint(73, 144)   # peak half
    from record_race import one
    print("racing %s, day %d (fixed vs mpc, ~4-6 min)..." % (args.config, seed))
    with mp.Pool(2) as pool:
        res = pool.map(one, [(args.config, seed, "fixed"), (args.config, seed, "mpc")])
    races_path = os.path.join(ROOT, "results", "races.json")
    races = json.load(open(races_path)) if os.path.exists(races_path) else {}
    key = "%s@%d" % (args.config, seed)
    for config, sd, arm, arm_data, meta in res:
        if key not in races:
            races[key] = dict(config=config, seed=sd, **meta, arms={})
        races[key]["arms"][arm] = arm_data
    json.dump(races, open(races_path, "w"), separators=(",", ":"), default=int)
    f, m = races[key]["arms"]["fixed"], races[key]["arms"]["mpc"]
    print("done: fixed=%d  mpc=%d  (%+d)  hard-dead f/m=%d/%d  tuner moves=%d"
          % (f["val"][-1], m["val"][-1], m["val"][-1] - f["val"][-1],
             f["dead"][-1], m["dead"][-1], len(m["adopted"])))
    page = build_html()
    print("viewer:", page)
    if not args.no_open:
        webbrowser.open("file:///" + page.replace("\\", "/") + "#race")
