"""Are the frozen AGVs sitting at busy=False with the controller emitting macro_action 0?
That combination means: nobody is driving them, and nobody will."""
import sys, collections; sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
import gymnasium as gym, wwm_sim
from wwm_sim.warehouse import Warehouse, AgentType
from wwm_sim.demand import DemandModel
import congestion_policies as cp

REC={}
orig=Warehouse.attribute_macro_actions
def probe(self, macro_actions):
    t=self._cur_steps
    if t in (400,450,499):
        REC[t]=[(a.id,a.busy,int(macro_actions[i]) if i<len(macro_actions) else None,
                 a.carrying_shelf is not None,len(a.path or []),(a.x,a.y))
                for i,a in enumerate(self.agents) if a.type==AgentType.AGV]
    return orig(self,macro_actions)
Warehouse.attribute_macro_actions=probe

for seed in (13,14):
    REC.clear()
    env=gym.make('wwm_sim-largedense-8agvs-6pickers-globalobs-v1').unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=500,window_index=seed,n_windows=162,
                   value_dist='lognormal',value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; n=dm.warm_start_n()
    dm.seed_day_list(env,horizon=500); dm.seed_initial(env,n=n)
    env.picker_service_steps=8; env.station_service_steps=6; env.station_headway=True
    ctrl=cp._SqWidePkRateAdaptive(env)
    for t in range(500): env.step(ctrl.act())
    print('=== seed %d ==='%seed)
    for t in sorted(REC):
        idle=[r for r in REC[t] if not r[1] and r[2]==0]
        print('  t=%-4d  AGVs busy=False AND macro_action=0 : %d/8   %s'%(
            t,len(idle),[('agv%d carry=%s plen=%d'%(r[0],r[3],r[4])) for r in idle]))
