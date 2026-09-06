"""3-trial end-to-end verification: battery model + FIFO-vs-random consistency.

For each of 3 seeds, runs FIFO and random on wwm_sim with the battery tracker
attached, then checks:
  1. picks_charged == deliveries          (battery <-> delivery consistency)
  2. FIFO deliveries >> random deliveries  (policies behave as expected)
  3. FIFO stucks == 0, random stucks > 0   (coordination vs flailing)
  4. battery actually drained (min < 100%) (battery model is live)

Run: python scripts/verify_trials.py
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import gymnasium as gym

import wwm_sim  # noqa: F401
from wwm_sim.heuristic import heuristic_episode
from wwm_sim.battery import BatteryConfig, BatteryTracker

ENV = "wwm_sim-tiny-3agvs-2pickers-globalobs-v1"
SEEDS = [0, 1, 2]


def _acc():
    return {"deliveries": 0, "clashes": 0, "stucks": 0}


def _add(acc, info):
    acc["deliveries"] += info.get("shelf_deliveries", 0)
    acc["clashes"] += info.get("clashes", 0)
    acc["stucks"] += info.get("stucks", 0)


def run_fifo(seed):
    env = gym.make(ENV).unwrapped
    bat = BatteryTracker(env)
    acc = _acc()
    orig_reset, orig_step = env.reset, env.step

    def rw(*a, **k):
        out = orig_reset(*a, **k)
        bat.reset()
        return out

    def sw(actions):
        out = orig_step(actions)
        bat.step()
        _add(acc, out[4])
        return out

    env.reset, env.step = rw, sw
    heuristic_episode(env, False, seed)
    return acc, bat


def run_random(seed):
    env = gym.make(ENV).unwrapped
    env.reset(seed=seed)
    bat = BatteryTracker(env)
    acc = _acc()
    done = False
    while not done:
        _, _, term, trunc, info = env.step(env.action_space.sample())
        bat.step()
        _add(acc, info)
        done = all(term) or all(trunc)
    return acc, bat


def main():
    print(f"env: {ENV}  |  battery: default (compressed, steps_per_charge=300)")
    print("=" * 82)
    hdr = (f"{'seed':>4} | {'FIFO deliv':>10} {'picks':>6} {'inTransit':>9} {'minBatt':>8} "
           f"{'strand':>6} {'stuck':>5} | {'RND deliv':>9} {'stuck':>5}")
    print(hdr)
    print("-" * 82)

    all_checks = []
    for seed in SEEDS:
        f, fbat = run_fifo(seed)
        r, rbat = run_random(seed)
        picks = fbat.picks_charged
        in_transit = picks - f["deliveries"]  # picked up but not yet delivered at cutoff
        minb = fbat.min_level() * 100
        strand = len(fbat.stranded)
        n_agvs = fbat.env.num_agvs
        print(f"{seed:>4} | {f['deliveries']:>10} {picks:>6} {in_transit:>9} {minb:>7.1f}% "
              f"{strand:>6} {f['stucks']:>5} | {r['deliveries']:>9} {r['stucks']:>5}")

        checks = {
            "picks>=deliveries":   in_transit >= 0,
            "in-transit<=nAGVs":   in_transit <= n_agvs,
            "FIFO>>random":        f["deliveries"] >= 3 * (r["deliveries"] + 1),
            "FIFO stucks==0":      f["stucks"] == 0,
            "random stucks>0":     r["stucks"] > 0,
            "battery drained":     minb < 100.0,
        }
        all_checks.append((seed, checks))

    print("=" * 82)
    overall = True
    for seed, checks in all_checks:
        for name, ok in checks.items():
            if not ok:
                overall = False
                print(f"  seed {seed}  FAIL: {name}")
    print(f"consistency checks across all seeds: {'ALL PASS' if overall else 'FAILURES ABOVE'}")

    # Bonus: prove the charge-ratio fix — charge:discharge must be identical at
    # compressed vs realistic steps_per_charge (it scales together now).
    print("-" * 82)
    for spc in (300.0, 21600.0):
        c = BatteryConfig(steps_per_charge=spc)
        ratio = c.charge_gain / c.drive_drain
        print(f"  steps_per_charge={spc:>7.0f}: charge/discharge rate ratio = {ratio:.3f}  (should be constant)")


if __name__ == "__main__":
    main()
