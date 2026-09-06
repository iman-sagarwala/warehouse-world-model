"""Attribute every stalled AGV-step to a CAUSE, before trying to fix any of it.

32% of working AGV-time is spent not moving. But the stall metric counts ANY non-move, and several
non-moves are legitimate work: a rotation is a real action, and picker/station service time is the
robot doing its job. Rerouting arms all measured negative, which is what you would expect if most of
the 32% is not blockage at all.

So decompose it. Only the genuinely-blocked share is addressable, and its size sets the ceiling on
any stall fix.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import gymnasium as gym
import wwm_sim  # noqa
from wwm_sim.warehouse import Warehouse, Action, CollisionLayers, AgentType
from wwm_sim.demand import DemandModel
import congestion_policies as cp

CAUSE = collections.Counter()
MOVED = collections.Counter()
_pre_ref = {}
_orig_ref = Warehouse.resolve_move_conflict


def ref(self, agent_list):
    _pre_ref.clear()
    for a in agent_list:
        _pre_ref[a.id] = a.req_action
    return _orig_ref(self, agent_list)


Warehouse.resolve_move_conflict = ref


def classify(env, a):
    """Why did this working AGV not change cell this step?"""
    svc = getattr(env, "_service_until", None)
    if svc and svc.get(a.id, 0) > env._cur_steps:
        return "service (picker/station dwell)"
    ra = a.req_action
    if ra in (Action.LEFT, Action.RIGHT):
        return "rotating (real action)"
    if ra == Action.TOGGLE_LOAD:
        return "load/unload (real action)"
    if not a.path:
        return "no path: waiting at pod for picker" if a.carrying_shelf is None else "no path: carrying, idle"
    nx, ny = a.path[0]
    occ = env.grid[CollisionLayers.AGVS, ny, nx]
    pre = _pre_ref.get(a.id)
    if pre == Action.FORWARD and ra == Action.NOOP:
        return "referee silenced (next cell FREE)" if not occ else "referee silenced (next cell taken)"
    if ra == Action.NOOP and occ:
        return "held: next cell occupied"
    if ra == Action.NOOP:
        return "held by rule (headway / exit priority)"
    return "other"


for seed in range(73, 97):
    env = gym.make("wwm_sim-largedense-8agvs-6pickers-globalobs-v1").unwrapped
    env.reset(seed=seed)
    env.request_queue = []
    dm = DemandModel(env, seed=seed, exogenous=True, horizon=500, window_index=seed, n_windows=162,
                     value_dist="lognormal", value_sigma=1.0, value_hi=200.0)
    env.demand_model = dm
    n = dm.warm_start_n()
    dm.seed_day_list(env, horizon=500)
    dm.seed_initial(env, n=n)
    env.picker_service_steps = 8
    env.station_service_steps = 6
    env.station_headway = True
    env.station_exit_priority = True
    env.free_pod_return = True
    ctrl = cp._SqWidePkRateAdaptive(env)
    for t in range(500):
        pre = {a.id: (a.x, a.y) for a in env.agents if a.type == AgentType.AGV}
        working = {a.id for a in env.agents
                   if a.type == AgentType.AGV and (a.busy or a.carrying_shelf is not None)}
        env.step(ctrl.act())
        for a in env.agents:
            if a.type != AgentType.AGV or a.id not in working:
                continue
            if (a.x, a.y) != pre.get(a.id):
                MOVED["moved"] += 1
            else:
                CAUSE[classify(env, a)] += 1

tot = sum(CAUSE.values())
print("AGV-steps with work, seeds 73-96 (24 peak episodes)")
print("  moved      %7d" % MOVED["moved"])
print("  did NOT move %7d   (%.1f%% of working AGV-time)"
      % (tot, 100.0 * tot / (tot + MOVED["moved"])))
print()
print("  %-42s %9s %8s" % ("cause of non-move", "steps", "share"))
for k, v in CAUSE.most_common():
    print("  %-42s %9d %7.1f%%" % (k, v, 100.0 * v / tot))
real = sum(v for k, v in CAUSE.items() if "real action" in k or k.startswith("service"))
print()
print("  legitimate work (service + rotate + load): %d  (%.1f%% of non-moves)"
      % (real, 100.0 * real / tot))
print("  genuinely lost to blocking:                %d  (%.1f%% of non-moves)"
      % (tot - real, 100.0 * (tot - real) / tot))
