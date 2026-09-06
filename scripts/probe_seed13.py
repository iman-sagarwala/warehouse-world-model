"""Seed 13: 7 carrying AGVs, valid paths, ZERO net progress for 150 steps. Ask each one directly:
what does it want to do, what does the referee do to it, and what is sitting in its next cell?"""
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
import gymnasium as gym, wwm_sim
from wwm_sim.warehouse import Warehouse, Action, CollisionLayers, AgentType
from wwm_sim.demand import DemandModel
import congestion_policies as cp

SNAP={}
orig=Warehouse.resolve_move_conflict
def probe(self, agent_list):
    t=self._cur_steps
    pre={a.id:a.req_action for a in agent_list}
    r=orig(self,agent_list)
    if t in (400,401,402):
        rows=[]
        for a in agent_list:
            if a.type!=AgentType.AGV: continue
            nxt=tuple(a.path[0]) if a.path else None
            occ=None
            if nxt:
                ox=self.grid[CollisionLayers.AGVS,nxt[1],nxt[0]]
                op=self.grid[CollisionLayers.PICKERS,nxt[1],nxt[0]]
                occ=('agv%d'%ox if ox else ('picker%d'%op if op else 'FREE'))
            rows.append((a.id,(a.x,a.y),a.dir.name if hasattr(a.dir,'name') else a.dir,nxt,occ,
                         str(pre[a.id]).split('.')[-1],str(a.req_action).split('.')[-1],
                         a.carrying_shelf is not None,len(a.path or []),
                         self._service_until.get(a.id,0) if getattr(self,'_service_until',None) else 0))
        SNAP[t]=rows
    return r
Warehouse.resolve_move_conflict=probe

env=gym.make('wwm_sim-largedense-8agvs-6pickers-globalobs-v1').unwrapped
env.reset(seed=13); env.request_queue=[]
dm=DemandModel(env,seed=13,exogenous=True,horizon=500,window_index=13,n_windows=162,
               value_dist='lognormal',value_sigma=1.0,value_hi=200.0)
env.demand_model=dm; n=dm.warm_start_n()
dm.seed_day_list(env,horizon=500); dm.seed_initial(env,n=n)
env.picker_service_steps=8; env.station_service_steps=6; env.station_headway=True
ctrl=cp._SqWidePkRateAdaptive(env)
for t in range(500): env.step(ctrl.act())

for t in sorted(SNAP):
    print('--- t=%d ---'%t)
    print('  %-4s %-9s %-6s %-9s %-9s %-9s %-9s %-5s %-5s %s'%(
        'agv','pos','dir','next','next-occ','want','after-ref','carry','plen','svc_until'))
    for r in SNAP[t]:
        print('  %-4d %-9s %-6s %-9s %-9s %-9s %-9s %-5s %-5d %d'%(
            r[0],str(r[1]),str(r[2])[:6],str(r[3]),str(r[4]),r[5],r[6],str(r[7]),r[8],r[9]))
print('current step at end:',env._cur_steps)
