"""MARL baseline: a LEARNED dispatcher trained by policy gradient, vs our rule-based one.

WHY THIS LEVEL. The RWARE-standard MARL setup has agents emit primitive moves; published results
show that setup struggling to reach even greedy-heuristic throughput at this scale, and it would
not isolate the DECISION layer (it would mostly be learning to walk). So the learned agent gets
exactly what our controller gets and no less: the same feasibility funnel, the same candidate
tasks, the same 24 assembler features per candidate, the same routes, pickers and battery layer.
Only the CHOICE is learned -- a shared-parameter policy (standard MARL parameter sharing) that
scores candidates and picks one, trained on the team's on-time value.

  policy    MLP(24 -> 64 -> 64 -> 1) scoring each candidate; softmax over candidates
  credit    each decision is credited with the on-time value the chosen task actually earned
            (0 if it missed its deadline) -- dense, low-variance credit for dispatch
  update    REINFORCE with a running-mean baseline + entropy bonus, Adam
  eval      argmax (greedy) on held-out seeds, vs champion / rush / fifo

Usage:  python scripts/marl_dispatch.py train      (writes results/marl_policy.pt)
        python scripts/marl_dispatch.py eval
"""
import os
import pickle
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

FEATS = ["pred_finish", "my_arrival", "dock", "picker_eta", "my_wait", "n_busy_agv", "n_free_pk",
         "q_size", "value", "dl_slack", "delay_ema", "dur_recent", "dur_trend", "deliv_rate",
         "busy_frac", "free_pk_frac", "q_per_agv", "local_density", "path_stretch", "sin_t",
         "cos_t", "day_frac", "dl_soon40", "dl_soon80"]
# fixed scales so workers need no shared state (magnitudes from a champion run)
SCALE = dict(pred_finish=60.0, my_arrival=30.0, dock=30.0, picker_eta=30.0, my_wait=20.0,
             n_busy_agv=8.0, n_free_pk=6.0, q_size=20.0, value=40.0, dl_slack=200.0,
             delay_ema=40.0, dur_recent=60.0, dur_trend=10.0, deliv_rate=0.2, busy_frac=1.0,
             free_pk_frac=1.0, q_per_agv=3.0, local_density=1.0, path_stretch=3.0, sin_t=1.0,
             cos_t=1.0, day_frac=1.0, dl_soon40=10.0, dl_soon80=15.0)
MODEL = "results/marl_policy.pt"
TRAIN_SEEDS = list(range(1, 97))
TEST_SEEDS = list(range(97, 145))


def vec(feat):
    import numpy as np
    return np.array([float(feat.get(k, 0.0)) / SCALE[k] for k in FEATS], dtype=np.float32)


def make_net():
    import torch.nn as nn
    return nn.Sequential(nn.Linear(len(FEATS), 64), nn.Tanh(),
                         nn.Linear(64, 64), nn.Tanh(), nn.Linear(64, 1))


def rollout(job):
    """One episode with the learned policy plugged into _pick_winner. Returns transitions."""
    seed, state, greedy, arm = job
    import numpy as np
    import torch
    from record_race import build
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    net = make_net()
    if state is not None:
        net.load_state_dict(state)
    net.eval()
    rng = np.random.RandomState(seed * 7919 + 13)
    decisions = []                       # (candidate matrix, chosen idx, shelf id, step)

    if arm == "marl":
        def pick(self, scored):
            X = np.stack([vec(s[4]) for s in scored])
            with torch.no_grad():
                logits = net(torch.from_numpy(X)).squeeze(-1).numpy()
            logits = logits - logits.max()
            p = np.exp(logits)
            p = p / p.sum()
            k = int(np.argmax(p)) if greedy else int(rng.choice(len(p), p=p))
            decisions.append((X, k, scored[k][1].id, self.timestep))
            return scored[k]
        type(ctrl)._pick_winner = pick

    onv = 0.0
    earned = {}
    for t in range(500):
        env.step(ctrl.act())
        for o in getattr(env, "fulfilled_this_step", []):
            got = o.value if (o.deadline is not None and t + 1 <= o.deadline) else 0.0
            onv += got
            earned[o.shelf.id] = earned.get(o.shelf.id, 0.0) + got
    if arm != "marl":
        return (seed, round(onv, 1), [])
    out = [(X, k, earned.get(sid, 0.0)) for (X, k, sid, _st) in decisions]
    type(ctrl)._pick_winner = None       # not strictly needed; worker dies anyway
    return (seed, round(onv, 1), out)


def train():
    import numpy as np
    import torch
    import torch.optim as optim
    iters = int(os.environ.get("ITERS", "40"))
    batch = int(os.environ.get("BATCH", "24"))
    net = make_net()
    if os.path.exists(MODEL):
        net.load_state_dict(torch.load(MODEL))
        print("resumed from", MODEL, flush=True)
    opt = optim.Adam(net.parameters(), lr=float(os.environ.get("LR", "0.003")))
    baseline = None
    rng = np.random.RandomState(0)
    pool = mp.Pool(int(os.environ.get("NPROC", "8")))
    try:
        for it in range(iters):
            state = {k: v.clone() for k, v in net.state_dict().items()}
            seeds = [int(rng.choice(TRAIN_SEEDS)) for _ in range(batch)]
            res = pool.map(rollout, [(s, state, False, "marl") for s in seeds])
            vals = [r[1] for r in res]
            trans = [tr for r in res for tr in r[2]]
            if not trans:
                print("no transitions -- policy hook not firing", flush=True)
                return
            rewards = np.array([t[2] for t in trans], dtype=np.float32)
            baseline = rewards.mean() if baseline is None else 0.9 * baseline + 0.1 * rewards.mean()
            adv = (rewards - baseline) / (rewards.std() + 1e-6)
            loss_terms = []
            for (X, k, _r), a in zip(trans, adv):
                logits = net(torch.from_numpy(X)).squeeze(-1)
                logp = torch.log_softmax(logits, dim=0)
                ent = -(logp.exp() * logp).sum()
                loss_terms.append(-logp[k] * float(a) - 0.01 * ent)
            loss = torch.stack(loss_terms).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            torch.save(net.state_dict(), MODEL)
            print("iter %2d/%d  episodes %d  mean value %7.1f  decisions %4d  loss %+.4f"
                  % (it + 1, iters, batch, float(np.mean(vals)), len(trans), float(loss)),
                  flush=True)
    finally:
        pool.close()
        pool.join()


def evaluate():
    import statistics as st
    import torch
    net = make_net()
    net.load_state_dict(torch.load(MODEL))
    state = net.state_dict()
    with mp.Pool(int(os.environ.get("NPROC", "8"))) as pool:
        marl = pool.map(rollout, [(s, state, True, "marl") for s in TEST_SEEDS])
        champ = pool.map(rollout, [(s, None, True, "champ") for s in TEST_SEEDS])
    M = {s: v for s, v, _ in marl}
    C = {s: v for s, v, _ in champ}
    d = [M[s] - C[s] for s in TEST_SEEDS]
    n = len(d)
    m = sum(d) / n
    sd = st.pstdev(d) * (n / (n - 1)) ** 0.5
    print("\nMARL LEARNED DISPATCHER vs CHAMPION (held-out seeds 97-144)\n")
    print("champion mean %8.2f" % (sum(C.values()) / n))
    print("marl     mean %8.2f   vs champion %+7.2f (%+.1f%%)  t=%+.2f  wins %d/%d"
          % (sum(M.values()) / n, m, 100 * m / (sum(C.values()) / n),
             m / (sd / n ** 0.5) if sd else 0.0, sum(1 for x in d if x > 0), n))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    if cmd == "train":
        train()
    else:
        evaluate()
