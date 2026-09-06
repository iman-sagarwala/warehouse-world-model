"""STATION EXIT PRIORITY -- paired evaluation on the real objective (on-time value), dense map.

The rule: an AGV standing ON a station whose next path cell is held by another AGV replans around the
blocker; failing that it steps SIDEWAYS along the station row (horizontal only -- a perpendicular step
puts it off the station line and makes the continuation diagonal, which is not executable).

Also reports the deadlock signature directly: a carrying AGV that never changes cell over the last 100
steps. That is what seed 13 showed -- 7 of 8 AGVs holding pods, motionless, for 100 steps.
"""
import csv, os, sys, statistics as st
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

STEPS=500; SEEDS=int(os.environ.get("SEEDS","48")); NPROC=int(os.environ.get("NPROC","8"))

def one(job):
    arm, seed = job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.warehouse import AgentType
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    env=gym.make('wwm_sim-largedense-8agvs-6pickers-globalobs-v1').unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist='lognormal',value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; n=dm.warm_start_n()
    dm.seed_day_list(env,horizon=STEPS); dm.seed_initial(env,n=n)
    env.picker_service_steps=8; env.station_service_steps=6; env.station_headway=True
    if arm=="exit": env.station_exit_priority=True
    ctrl=cp._SqWidePkRateAdaptive(env)
    onv=0.0; t=0; done=False; hist={}
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,'fulfilled_this_step',[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        if t>400:
            for a in env.agents:
                if a.type==AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id,[]).append((a.x,a.y))
        done=all(term) or all(trunc)
    frozen=sum(1 for v in hist.values() if len(v)>=95 and len(set(v))==1)
    return (arm,seed,round(onv,1),frozen)

if __name__=="__main__":
    jobs=[(a,s) for a in ("base","exit") for s in range(1,SEEDS+1)]
    with mp.Pool(NPROC) as p: rows=p.map(one,jobs)
    with open('results/exit_priority.csv','w',newline='') as f:
        w=csv.writer(f); w.writerow(['arm','seed','on_time_value','frozen_agvs']); w.writerows(rows)
    D={a:{} for a in ("base","exit")}; F={a:0 for a in ("base","exit")}; DEAD={a:0 for a in ("base","exit")}
    for a,s,v,fr in rows:
        D[a][s]=v; F[a]+=fr; DEAD[a]+= (1 if fr>0 else 0)
    print('%-28s %10s %10s %14s %12s'%('arm','on-time val','mean','frozen AGVs','dead episodes'))
    for a,lbl in (("base","baseline (headway)"),("exit","+ STATION EXIT PRIORITY")):
        v=[D[a][s] for s in range(1,SEEDS+1)]
        print('%-28s %10.1f %10.2f %14d %9d/%d'%(lbl,sum(v),sum(v)/len(v),F[a],DEAD[a],SEEDS))
    d=[D["exit"][s]-D["base"][s] for s in range(1,SEEDS+1)]
    m=sum(d)/len(d); sd=st.pstdev(d)*(len(d)/(len(d)-1))**.5
    tt=m/(sd/len(d)**.5) if sd else float('inf')
    base=sum(D["base"].values())
    print('\npaired diff: mean %+.2f/episode  t=%+.2f  n=%d  -> %+.2f%% on-time value'
          %(m,tt,len(d),100*sum(d)/base if base else 0))
    print('wins %d  losses %d  ties %d'%(sum(1 for x in d if x>0),sum(1 for x in d if x<0),sum(1 for x in d if x==0)))
