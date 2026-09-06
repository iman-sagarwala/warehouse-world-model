"""Beta rumor map — a Bayesian OBSERVATION map of disturbances (NOT a prediction).

Disturbances are random and unpredictable (see docs/NOTES 2026-07-16): they don't depend on the
robots, have no inferable ranking, and can't be forecast the way congestion can (congestion is a
rollout of KNOWN robot futures; a disturbance is exogenous noise). The only thing you can do is
OBSERVE where they have been and keep a running, decaying belief — "this area has been disturbed
lately." Unlike the congestion map (a forward rollout you STEER by), this is a backward-looking
belief you ACCUMULATE from sightings. We build it here; acting on it (Part B support + task
selection) is deliberately LEFT FOR LATER.

Per cell: a Beta(alpha, beta) belief that the cell is disturbed.
  - SIGHTING  (a disturbance seen within sensing range of a robot) -> alpha += 1
  - CLEAN     (a robot stands on / traverses a non-disturbed cell) -> beta  += 1
  - DECAY     each step both counters relax toward the uniform prior (old evidence fades)
  belief P(disturbed) = alpha / (alpha + beta).
It is calibrated (a real probability), partial-observability aware (only sightings near robots),
and non-stationary-friendly (decay), which is exactly what an unpredictable, moving hazard needs.
"""
from __future__ import annotations

import numpy as np


class BetaRumorMap:
    def __init__(self, grid_size, decay=0.99, sight_radius=None, learn_style=False):
        # SIGHT RADIUS IS A TUNABLE WORLD KNOB (user 2026-08-23): hardware, not policy -- set it
        # per deployment via WWM_SIGHT_RADIUS (default 5 = camera-equipped; 1 = sensor-poor
        # near-contact; 3 = modest camera, ~free vs 5). Explicit constructor arg still wins.
        # Measured price (48 seeds, multi-cell): r1 48.5% of oracle / r2 70% / r3 86% / r5 89.5%.
        if sight_radius is None:
            import os as _os
            sight_radius = int(_os.environ.get("WWM_SIGHT_RADIUS", "5"))
        H, W = grid_size
        self.alpha = np.ones((H, W), dtype=np.float32)   # disturbance evidence
        self.beta = np.ones((H, W), dtype=np.float32)    # clean evidence
        self.decay = decay
        self.sight_radius = sight_radius
        # STYLE LEARNING (user 2026-08-23): learn the spawn PROCESS, not just the current state.
        # spawn_prior counts first confirmations per cell (where spills happen); _event_n/_event_cells
        # give a running mean of confirmed-event size (how many cells one spill covers). Used to
        # (a) spread suspicion to neighbors of a fresh sighting when events are learned multi-cell,
        # (b) forget slower in learned hot zones. Resting belief never rises above the uniform
        # prior, so this cannot create permanent no-go zones (the M2 boundary lesson).
        self.learn_style = learn_style
        self.style_bump = True        # v1 effect (a): neighbor suspicion -- ablatable
        self.style_slowmem = True     # v1 effect (b): slow forgetting in hot zones -- ablatable
        # v2 (user 2026-08-23): SIGHT-GATED spread avoidance. The estimated spread of a confirmed
        # spill is a PLACEHOLDER, not evidence: avoid those cells only while UNOBSERVED; the
        # moment any robot's line of sight covers one, the placeholder dies and truth takes over
        # (v1's failure was suspicion lingering ~2-3 clean looks after the cell was visibly fine).
        self.style_suspect = False
        self.obs_gain = 1.0           # evidence per observation; large = one look is decisive
        self.obs_reset = True         # SHIPPED 2026-08-23 (t=+4.05, hits 236->80, 83% of
                                      # clairvoyant VoPI): a look REPLACES the cell's evidence
                                      # (noiseless sensors -> last-observation-wins + decay).
                                      # False = legacy incremental-vote updates.
        self.suspect = {}             # cell -> tick added; resolved by observation or expiry
        self._tick = 0
        self.spawn_prior = np.zeros((H, W), dtype=np.float32)
        self._event_n, self._event_cells = 0, 0
        self._known = set()

    # ---- line-of-sight sensing -------------------------------------------------------------
    # A plain radius lets a robot see THROUGH shelving, which in a rack warehouse is the dominant
    # unrealism: in an aisle layout you see down your own aisle and essentially nothing laterally.
    # Radius-only sensing also SATURATES the map within a few hundred steps, collapsing back toward
    # the clairvoyance we are trying to remove — so occlusion is what preserves an information gap
    # long enough for the map to be worth having.
    # Racks (non-highway cells) block sight. The ray's endpoint is still visible (you can see the
    # rack face in front of you); only cells STRICTLY BETWEEN robot and target can occlude.
    @staticmethod
    def _between(dy, dx):
        """Cells strictly between (0,0) and (dy,dx) on the Bresenham ray."""
        steps = max(abs(dy), abs(dx))
        out = []
        for i in range(1, steps):
            y, x = int(round(dy * i / steps)), int(round(dx * i / steps))
            if (y, x) not in ((0, 0), (dy, dx)):
                out.append((y, x))
        return out

    def _los_table(self):
        if getattr(self, "_los", None) is None:
            r = self.sight_radius
            self._los = [((dy, dx), self._between(dy, dx))
                         for dy in range(-r, r + 1) for dx in range(-r, r + 1)
                         if (dy or dx) and dy * dy + dx * dx <= r * r]
        return self._los

    def update(self, env, line_of_sight=True):
        """Fold one step of observations into the belief (call each env step).

        `line_of_sight=False` reproduces the original Manhattan-radius sensing (kept so the two
        sensing models can be ablated against each other)."""
        self._tick += 1
        # SIGHT = CERTAINTY (user 2026-08-23): cells observed THIS step read exact truth in
        # belief(); everything else is PREDICTION from decaying memory. Two regimes, one map.
        self._live = {}
        if self.suspect:              # placeholders expire with a typical spill lifetime
            for c in [c for c, t0 in self.suspect.items() if self._tick - t0 > 150]:
                del self.suspect[c]
        # DECAY toward the uniform prior (alpha=beta=1) so stale evidence fades.
        # With style learning, learned hot zones forget SLOWER (decay pulled toward 1) -- longer
        # memory of real sightings without ever raising resting belief above the prior.
        if self.learn_style and self.style_slowmem and self.spawn_prior.max() > 0:
            hz = self.spawn_prior / self.spawn_prior.max()
            d = self.decay + (0.999 - self.decay) * hz
            self.alpha = 1.0 + (self.alpha - 1.0) * d
            self.beta = 1.0 + (self.beta - 1.0) * d
        else:
            self.alpha = 1.0 + (self.alpha - 1.0) * self.decay
            self.beta = 1.0 + (self.beta - 1.0) * self.decay
        disturbed = getattr(env, "disturbed", None) or set()
        agents = env.agents
        H, W = self.alpha.shape

        if not line_of_sight:
            r = self.sight_radius
            for (y, x) in disturbed:
                if any(abs(a.y - y) + abs(a.x - x) <= r for a in agents):
                    self.alpha[y, x] += 1.0
            for a in agents:
                if (a.y, a.x) not in disturbed:
                    self.beta[a.y, a.x] += 1.0
            return

        hw = env.highways                       # 1 = open highway, 0 = rack -> blocks sight
        for a in agents:
            ay, ax = a.y, a.x
            # the cell you stand on is always observed
            self._observe(ay, ax, (ay, ax) in disturbed, env)
            for (dy, dx), between in self._los_table():
                y, x = ay + dy, ax + dx
                if not (0 <= y < H and 0 <= x < W):
                    continue
                blocked = False
                for (by, bx) in between:
                    yy, xx = ay + by, ax + bx
                    if 0 <= yy < H and 0 <= xx < W and not hw[yy, xx]:
                        blocked = True
                        break
                if blocked:
                    continue
                self._observe(y, x, (y, x) in disturbed, env)

    def _observe(self, y, x, dirty, env):
        """One confirmed observation of cell (y,x); feeds the style learner on first sightings."""
        self.suspect.pop((y, x), None)     # sight overrides estimate, instantly, either way
        self._live[(y, x)] = dirty         # in-sight this step: belief() reads exact truth
        g = self.obs_gain
        if self.obs_reset:
            if dirty:
                self.alpha[y, x], self.beta[y, x] = 26.0, 1.0
            else:
                self.alpha[y, x], self.beta[y, x] = 1.0, 26.0
                if self.learn_style:
                    self._known.discard((y, x))
                return
        elif not dirty:
            self.beta[y, x] += g
            if self.learn_style:
                self._known.discard((y, x))
            return
        else:
            self.alpha[y, x] += g
        if not self.learn_style or (y, x) in self._known:
            return
        # FIRST confirmation of this spill cell: update the learned spawn process
        self.spawn_prior[y, x] += 1.0
        touching = any(n in self._known for n in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)))
        self._known.add((y, x))
        self._event_cells += 1
        if not touching:
            self._event_n += 1            # a genuinely new event (not growth of a known one)
        # neighbor generalization: if learned events are multi-cell, a fresh sighting makes the
        # cells NEXT to it suspicious before anyone sees them (evidence-shaped; decays like any)
        est = self._event_cells / max(1, self._event_n)
        w = min(1.5, max(0.0, est - 1.0)) if self.style_bump else 0.0
        if w > 0.05:
            H, W = self.alpha.shape
            hw = env.highways
            for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                if 0 <= ny < H and 0 <= nx < W and hw[ny, nx] and (ny, nx) not in self._known:
                    self.alpha[ny, nx] += w
        if self.style_suspect and est > 1.2:
            H, W = self.alpha.shape
            hw = env.highways
            for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                if 0 <= ny < H and 0 <= nx < W and hw[ny, nx] and (ny, nx) not in self._known:
                    self.suspect[(ny, nx)] = self._tick

    def believed_blocked(self, b_hard=0.5):
        """Cells the FLEET currently believes are blocked — what a non-clairvoyant router plans on.
        Includes sight-gated spread placeholders: estimated-but-unobserved neighbors of confirmed
        spills (they vanish the instant anyone actually sees the cell)."""
        b = self.belief()
        ys, xs = np.where(b > b_hard)
        out = {(int(y), int(x)) for y, x in zip(ys, xs)}
        if self.style_suspect and self.suspect:
            out |= set(self.suspect.keys())
        return out

    def belief(self):
        """Per-cell P(disturbed). Cells in someone's sight THIS step read exact truth (1/0 --
        a noiseless look leaves nothing to estimate); everything else is a PREDICTION:
        alpha/(alpha+beta) decaying from the last observation toward ignorance."""
        b = self.alpha / (self.alpha + self.beta)
        for (y, x), dirty in getattr(self, "_live", {}).items():
            b[y, x] = 1.0 if dirty else 0.0
        return b

    def info_gain_map(self, env):
        """Expected value of LOOKING from each cell: for every floor cell, how much unobserved,
        hazard-prone area a robot standing there would sweep. V(cell) = learned hazard x current
        uncertainty (evidence-starved cells count, freshly observed ones don't); G = disc sum of V
        within sight radius. Drives opportunistic scout detours -- information gathering priced in
        path steps, never a dedicated scout robot."""
        H, W = self.alpha.shape
        if self.spawn_prior.max() <= 0:
            return np.zeros((H, W), dtype=np.float32)
        haz = self.spawn_prior / self.spawn_prior.max()
        unc = 1.0 / np.maximum(self.alpha + self.beta - 1.0, 1.0)   # 1 at the prior, ~0 when fresh
        V = haz * unc
        if not hasattr(self, "_disc"):
            r = self.sight_radius
            self._disc = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
                          if dy * dy + dx * dx <= r * r]
        G = np.zeros((H, W), dtype=np.float32)
        for dy, dx in self._disc:
            ys, ye = max(0, -dy), min(H, H - dy)
            xs, xe = max(0, -dx), min(W, W - dx)
            G[ys:ye, xs:xe] += V[ys + dy:ye + dy, xs + dx:xe + dx]
        return G

    def hazard_smooth(self):
        """Disc-smoothed learned spawn prior: expected spills within sight radius of each cell.
        Pure WHERE-prediction (no uncertainty term) -- for siting a responder, not for scouting."""
        H, W = self.alpha.shape
        if not hasattr(self, "_disc"):
            r = self.sight_radius
            self._disc = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
                          if dy * dy + dx * dx <= r * r]
        G = np.zeros((H, W), dtype=np.float32)
        for dy, dx in self._disc:
            ys, ye = max(0, -dy), min(H, H - dy)
            xs, xe = max(0, -dx), min(W, W - dx)
            G[ys:ye, xs:xe] += self.spawn_prior[ys + dy:ye + dy, xs + dx:xe + dx]
        return G

    def hotspots(self, k=10):
        """Top-k highest-belief cells as (y, x, p) — the observed disturbance areas."""
        b = self.belief()
        idx = np.argsort(b, axis=None)[::-1][:k]
        H, W = b.shape
        return [(int(i // W), int(i % W), float(b.flat[i])) for i in idx]
