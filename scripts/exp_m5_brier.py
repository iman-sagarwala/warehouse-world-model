"""M5 evaluation gap: Brier score, reliability diagram and precision-recall curve for the
belief map, treated as what it is -- a per-cell probabilistic detector of "this cell is blocked".

Two arms on identical seeds:
  reset   the shipped map (a direct look replaces the cell's evidence)
  legacy  the pre-2026-08-23 incremental-vote map
Scoring is over EVERY highway cell at EVERY step (~4.8M predictions/arm at 24 seeds), accumulated
into 1000-bin score histograms so nothing has to be held in memory.

Outputs: printed metrics + results/m5_belief_curves.png (reliability, PR, detection latency).
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = [int(x) for x in os.environ.get("M5SEEDS", ",".join(str(i) for i in range(1, 25))).split(",")]
NBIN = 1000


def one(job):
    arm, seed = job
    import numpy as np
    from record_race import build
    from wwm_sim.rumor_map import BetaRumorMap
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    env.disturb_rate = 0.02
    env._disturb_rng = np.random.RandomState(4000 + seed)
    env.disturb_dur = (150, 400)
    env.disturb_event_cells = (1, 3)
    env.debris_hold_steps = -1
    env.use_belief_routing = True
    rm = BetaRumorMap(env.grid_size)
    rm.obs_reset = (arm == "reset")
    env.rumor_map = rm
    env.b_hard = 0.5
    env.los_sensing = True
    hw = env.highways.astype(bool)

    pos = np.zeros(NBIN + 1)          # score histogram for truly-blocked cells
    neg = np.zeros(NBIN + 1)          # ... and for truly-clear cells
    sq = 0.0                          # sum of squared error -> Brier
    n = 0
    spawn_t, det_t = {}, {}
    prev = set()
    for t in range(500):
        env.step(ctrl.act())
        dist = set(env.disturbed)
        for c in dist - prev:
            spawn_t.setdefault(c, t)
        prev = set(dist)
        b = rm.belief()
        truth = np.zeros(b.shape, dtype=bool)
        for (y, x) in dist:
            truth[y, x] = True
        p = b[hw]
        y_ = truth[hw]
        sq += float(((p - y_) ** 2).sum())
        n += p.size
        idx = np.clip((p * NBIN).astype(int), 0, NBIN)
        np.add.at(pos, idx[y_], 1)
        np.add.at(neg, idx[~y_], 1)
        for c in dist:
            if c not in det_t and b[c[0], c[1]] > 0.5:
                det_t[c] = t
    lat = [det_t[c] - spawn_t[c] for c in det_t if c in spawn_t]
    return (arm, pos, neg, sq, n, lat, len(spawn_t))


if __name__ == "__main__":
    import numpy as np
    jobs = [(a, s) for a in ("reset", "legacy") for s in SEEDS]
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        res = pool.map(one, jobs)
    agg = {}
    for arm, pos, neg, sq, n, lat, nev in res:
        d = agg.setdefault(arm, dict(pos=np.zeros(NBIN + 1), neg=np.zeros(NBIN + 1),
                                     sq=0.0, n=0, lat=[], ev=0))
        d["pos"] += pos
        d["neg"] += neg
        d["sq"] += sq
        d["n"] += n
        d["lat"] += lat
        d["ev"] += nev

    curves = {}
    print("BELIEF MAP AS A PROBABILISTIC DETECTOR (%d seeds, every highway cell every step)\n"
          % len(SEEDS))
    for arm in ("reset", "legacy"):
        d = agg[arm]
        edges = np.arange(NBIN + 1) / NBIN
        P, N = d["pos"], d["neg"]
        base = P.sum() / (P.sum() + N.sum())                 # prevalence of blocked cells
        brier = d["sq"] / d["n"]
        bs_ref = base * (1 - base)                           # Brier of always predicting the base rate
        bss = 1.0 - brier / bs_ref
        # PR curve by sweeping the threshold downward
        tp = np.cumsum(P[::-1])[::-1]
        fp = np.cumsum(N[::-1])[::-1]
        prec = np.where(tp + fp > 0, tp / np.maximum(tp + fp, 1), 1.0)
        rec = tp / max(1.0, P.sum())
        order = np.argsort(rec)
        auprc = float(np.trapz(prec[order], rec[order]))
        curves[arm] = (rec, prec, edges, P, N)
        print("%-7s Brier %.5f  (base-rate reference %.5f -> skill %+.3f)"
              % (arm, brier, bs_ref, bss))
        print("        prevalence of blocked cells %.4f%%   AUPRC %.3f  (random = %.4f)"
              % (100 * base, auprc, base))
        print("        detection latency: mean %.1f  median %.0f  (events %d, detected %d)"
              % (np.mean(d["lat"]) if d["lat"] else -1,
                 np.median(d["lat"]) if d["lat"] else -1, d["ev"], len(d["lat"])))
        print()

    # ---------------- figure ----------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(15.5, 4.6))
    COL = {"reset": "#c0392b", "legacy": "#8a8a8a"}
    LBL = {"reset": "shipped map (one look overwrites)", "legacy": "old map (incremental votes)"}

    for arm in ("legacy", "reset"):
        rec, prec, edges, P, N = curves[arm]
        axA.plot(rec, prec, color=COL[arm], lw=2, label=LBL[arm])
    base = curves["reset"][3].sum() / (curves["reset"][3].sum() + curves["reset"][4].sum())
    axA.axhline(base, ls="--", color="#999", lw=1)
    axA.text(0.42, base + 0.05, "random guessing (only %.1f%% of cells are blocked)" % (100 * base),
             fontsize=8, color="#666")
    axA.set_xlabel("recall - fraction of blocked cells the map flags")
    axA.set_ylabel("precision")
    axA.set_title("Precision-recall (higher and further right is better)", fontsize=11)
    axA.set_xlim(0, 1.02)
    axA.set_ylim(0, 1.02)
    axA.legend(fontsize=8, loc="lower left")

    for arm in ("legacy", "reset"):
        rec, prec, edges, P, N = curves[arm]
        tot = P + N
        m = tot > 500
        conf = edges[m]
        freq = P[m] / tot[m]
        axB.plot(conf, freq, "o-", ms=3, color=COL[arm], lw=1.6, label=LBL[arm])
    axB.plot([0, 1], [0, 1], ls="--", color="#999", lw=1)
    axB.annotate("cells nobody has looked at sit at 50% by\nconvention -- they are almost never blocked,\nso the curve runs low here",
                 xy=(0.5, 0.03), xytext=(0.04, 0.60), fontsize=7.5, color="#666",
                 arrowprops=dict(arrowstyle="->", color="#999", lw=0.9))
    axB.annotate("where it acts: says ~98%, is ~98%", xy=(0.98, 0.985), xytext=(0.30, 0.72),
                 fontsize=8, color="#c0392b",
                 arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.1))
    axB.set_xlabel("what the map says (probability blocked)")
    axB.set_ylabel("what actually happened")
    axB.set_title("Reliability - beliefs are near-binary, so the ends are what matter", fontsize=11)
    axB.legend(fontsize=8, loc="upper left")

    for arm in ("legacy", "reset"):
        lat = np.array(sorted(agg[arm]["lat"]))
        if len(lat):
            axC.plot(lat, np.arange(1, len(lat) + 1) / len(lat), color=COL[arm], lw=2,
                     label="%s (median %.0f)" % (LBL[arm], np.median(lat)))
    axC.set_xlabel("steps from spill appearing to fleet believing it")
    axC.set_ylabel("fraction of spills detected")
    axC.set_title("Detection latency - identical: the fix is not about seeing sooner", fontsize=11)
    axC.set_xlim(0, 200)
    axC.legend(fontsize=8, loc="lower right")

    for ax in (axA, axB, axC):
        ax.grid(alpha=0.25)
    fig.tight_layout()
    out = os.path.join("results", "m5_belief_curves.png")
    fig.savefig(out, dpi=140)
    print("saved", out)
