"""A/B the no-seal-in rule on the 24 diagnostic seeds. A 'stuck AGV' = a carrying AGV whose distance
to its own target never changes over the last 100 steps -- the signature of the seed-13 deadlock.
Reported separately from value so a fix that trades throughput for liveness is visible as such."""
import sys, csv; sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
import gymnasium as gym, wwm_sim
from wwm_sim.warehouse import AgentType
from wwm_sim.demand import DemandModel
import congestion_policies as cp

def run(seed, noseal):
    env=gym.make('wwm_sim-largedense-8agvs-6pickers-globalobs-v1').unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=500,window_index=seed,n_windows=162,
                   value_dist='lognormal',value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; n=dm.warm_start_n()
    dm.seed_day_list(env,horizon=500); dm.seed_initial(env,n=n)
    env.picker_service_steps=8; env.station_service_steps=6; env.station_headway=True
    if noseal=='noseal': env.station_no_seal=True
    elif noseal=='exit': env.station_exit_priority=True
    elif noseal=='both': env.station_no_seal=True; env.station_exit_priority=True
    ctrl=cp._SqWidePkRateAdaptive(env)
    val=0.0; hist={}
    for t in range(500):
        pre={a.id:(a.x,a.y) for a in env.agents}
        _,rew,_,_,_=env.step(ctrl.act())
        for sh in getattr(env,'_delivered_this_step',[]) or []: pass
        val+=float(sum(rew))
        if t>=400:
            for a in env.agents:
                if a.type==AgentType.AGV and a.carrying_shelf is not None:
                    hist.setdefault(a.id,[]).append((a.x,a.y))
    stuck=sum(1 for k,v in hist.items() if len(v)>=95 and len(set(v))==1)
    return val, stuck

rows=[]
for noseal in ('base','exit','both'):
    tv=ts=0
    for seed in range(1,25):
        v,s=run(seed,noseal); tv+=v; ts+=s
        rows.append((noseal,seed,v,s))
    print('%-24s  total=%8.1f  mean=%7.2f  frozen-carrying-AGVs(t>=400)=%d'
          %({'base':'baseline (headway)','noseal':'no-seal','exit':'EXIT PRIORITY',
             'both':'no-seal + exit'}[noseal],tv,tv/24,ts))
with open('results/noseal.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(['noseal','seed','value','stuck_agvs']); w.writerows(rows)
