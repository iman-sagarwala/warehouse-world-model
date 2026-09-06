"""Robots move constantly and deliver ~nothing. Two candidate mechanisms:
   H-A THRASH   the assigner retargets an AGV before it arrives, so it walks A->B->A. Net progress 0.
   H-B ARRIVED  the AGV reaches its target but the completion trigger never fires (stuck at dist 0).
Distinguish by tracking, per carrying AGV: its target cell, and its distance to that target."""
import sys, collections; sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
import gymnasium as gym, wwm_sim
from wwm_sim.demand import DemandModel
import congestion_policies as cp

def run(seed):
    env=gym.make('wwm_sim-largedense-8agvs-6pickers-globalobs-v1').unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=500,window_index=seed,n_windows=162,
                   value_dist='lognormal',value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; n=dm.warm_start_n()
    dm.seed_day_list(env,horizon=500); dm.seed_initial(env,n=n)
    env.picker_service_steps=8; env.station_service_steps=6; env.station_headway=True
    ctrl=cp._SqWidePkRateAdaptive(env)
    prev_tgt={}; churn=collections.Counter(); dist_hist=collections.defaultdict(list)
    carry_steps=collections.Counter(); at_target=collections.Counter()
    for t in range(500):
        env.step(ctrl.act())
        if t<350: 
            prev_tgt={a.id:(tuple(a.path[-1]) if a.path else None) for a in env.agents}
            continue
        for a in env.agents:
            tgt=tuple(a.path[-1]) if a.path else None
            if prev_tgt.get(a.id) is not None and tgt is not None and tgt!=prev_tgt[a.id]:
                churn[a.id]+=1
            prev_tgt[a.id]=tgt
            if getattr(a,'carrying_shelf',None) is not None:
                carry_steps[a.id]+=1
                if tgt: dist_hist[a.id].append(abs(a.x-tgt[1])+abs(a.y-tgt[0]))
                else: at_target[a.id]+=1
    return env,churn,dist_hist,carry_steps,at_target

for seed in (13,14):
    env,churn,dist,carry,at_t=run(seed)
    agvs=[a for a in env.agents if str(a.type).endswith('AGV')]
    print('=== seed %d  (t=350..499, 150 steps) ==='%seed)
    print('  %-4s %-8s %-9s %-11s %-9s %s'%('agv','carrying','retargets','steps-no-path','dist','distance trace (every 15 steps)'))
    for a in agvs:
        d=dist.get(a.id,[])
        tr=' '.join('%d'%v for v in d[::15][:10]) if d else '-'
        print('  %-4d %-8d %-9d %-11d %-9s %s'%(a.id,carry.get(a.id,0),churn.get(a.id,0),
              at_t.get(a.id,0),(str(d[-1]) if d else '-'),tr))
    print('  pickers: %d  | request_queue len=%d'%(len(env.agents)-len(agvs),len(env.request_queue)))
