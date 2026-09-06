"""Direct interrogation of a PEAK-DEMAND dead seed, the way seed 13 was cracked.

Three hypotheses died guessing (dock capacity, aisle width, loaded-robot graph). So stop guessing and
ask the frozen robots what they are doing: position, next cell, who holds it, what they requested, what
the referee did to them, and whether they even have a task.
"""
import sys
import os
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.warehouse import Warehouse, Action, CollisionLayers, AgentType
from wwm_sim.demand import DemandModel
import congestion_policies as cp

SEED = int(os.environ.get("SEED", "100"))
SNAP = {}
_orig = Warehouse.resolve_move_conflict


def probe(self, agent_list):
    t = self._cur_steps
    pre = {a.id: a.req_action for a in agent_list}
    r = _orig(self, agent_list)
    if t in (460, 461, 462):
        rows = []
        for a in agent_list:
            if a.type != AgentType.AGV:
                continue
            nxt = tuple(a.path[0]) if a.path else None
            occ = "-"
            if nxt:
                ox = self.grid[CollisionLayers.AGVS, nxt[1], nxt[0]]
                op = self.grid[CollisionLayers.PICKERS, nxt[1], nxt[0]]
                occ = ("agv%d" % ox) if ox else (("picker%d" % op) if op else "FREE")
            rows.append((a.id, (a.x, a.y), nxt, occ,
                         str(pre[a.id]).split(".")[-1], str(a.req_action).split(".")[-1],
                         a.carrying_shelf is not None, len(a.path or []), a.busy,
                         (self._service_until.get(a.id, 0) if getattr(self, "_service_until", None) else 0)))
        SNAP[t] = rows
    return r


Warehouse.resolve_move_conflict = probe

env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
env.reset(seed=SEED)
env.request_queue = []
dm = DemandModel(env, seed=SEED, exogenous=True, horizon=500, window_index=SEED, n_windows=162,
                 value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
env.demand_model = dm
n = dm.warm_start_n()
dm.seed_day_list(env, horizon=500)
dm.seed_initial(env, n=n)
env.picker_service_steps = 8
env.station_service_steps = 6
env.station_headway = True
env.station_exit_priority = True
ctrl = cp._SqWidePkRateAdaptive(env)
delivered = 0
for t in range(500):
    _, rew, _, _, _ = env.step(ctrl.act())
    delivered += int(sum(rew))

print("seed %d  goals=%s  delivered=%d  queue_left=%d" % (SEED, env.goals, delivered, len(env.request_queue)))
for t in sorted(SNAP):
    print("--- t=%d ---" % t)
    print("  %-4s %-9s %-9s %-9s %-9s %-9s %-6s %-5s %-6s %s"
          % ("agv", "pos", "next", "next-occ", "want", "after-ref", "carry", "plen", "busy", "svc"))
    for r in SNAP[t]:
        print("  %-4d %-9s %-9s %-9s %-9s %-9s %-6s %-5d %-6s %d"
              % (r[0], str(r[1]), str(r[2]), r[3], r[4], r[5], str(r[6]), r[7], str(r[8]), r[9]))

# where are the pickers, and is anyone waiting on one?
pk = [(a.id, (a.x, a.y), a.busy, len(a.path or [])) for a in env.agents if a.type == AgentType.PICKER]
print("\npickers (id, pos, busy, plen):", pk)
