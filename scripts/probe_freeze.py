"""Per-seed, per-step ground truth: are robots MOVING during a 'freeze', and are tasks COMPLETING?
A freeze that still has movement is a LIVELOCK (robots circulate, nothing finishes), which is a
different failure from deadlock and needs a different fix."""
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
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
    rows=[]; delivered=0
    for t in range(500):
        pre={a.id:(a.x,a.y) for a in env.agents}
        _,rew,_,_,_=env.step(ctrl.act())
        delivered+=int(sum(rew))
        moved=sum(1 for a in env.agents if (a.x,a.y)!=pre[a.id])
        rows.append((t,moved,delivered))
    return rows

for seed in (13,14):
    rows=run(seed)
    # longest run of steps with ZERO position changes
    best=cur=0; bs=0; s=0
    for t,m,_ in rows:
        if m==0:
            if cur==0: s=t
            cur+=1
            if cur>best: best,bs=cur,s
        else: cur=0
    # longest run with movement but NO new delivery
    bl=cl=0; bls=0; ls=0; pd=0
    for t,m,d in rows:
        if d==pd and m>0:
            if cl==0: ls=t
            cl+=1
            if cl>bl: bl,bls=cl,ls
        else: cl=0
        pd=d
    tot=sum(m for _,m,_ in rows)
    print('seed %-3d delivered=%-4d total-moves=%-6d | longest ZERO-MOVE run=%-4d (from t=%-3d)'
          ' | longest MOVING-but-NO-DELIVERY run=%-4d (from t=%d)'
          %(seed,rows[-1][2],tot,best,bs,bl,bls))
    # movement profile over the last 150 steps
    tail=[m for t,m,_ in rows if t>=350]
    print('    moves/step over t=350..499: min=%d max=%d mean=%.2f  zero-move steps=%d/150'
          %(min(tail),max(tail),sum(tail)/len(tail),sum(1 for m in tail if m==0)))
