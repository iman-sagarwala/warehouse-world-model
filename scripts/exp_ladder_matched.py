"""CHAMPION LADDER — WORKLOAD-MATCHED. Supersedes the +11.83% headline.

WHY RE-RUN: the original ladder used wave WITHOUT the warm start while stream had it, so wave carried
~30% less work. That is the same confound that produced -- and then destroyed -- the "rollout is harmful
on day-list" result, so the headline inherits it and must be re-measured before it can be quoted.

Both regimes now get the SAME warm start; only VISIBILITY differs.
486 seeds x 2 regimes. Arms: fifo · rush · champion (the three the comparison actually needs).
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","486")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/ladder_matched.csv")
ENVID="wwm_sim-largedense-8agvs-6pickers-globalobs-v1"
ARMS=["fifo","rush","champion"]; REGIMES=["daylist","stream"]

def _cls(a):
    import sim_priority as sp, congestion_policies as cp
    return {"fifo":sp.FIFOController,"rush":sp.RushValueController,
            "champion":cp._SqWidePkRateAdaptive}[a]

def one(job):
    arm,regime,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    env=gym.make(ENVID).unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; n_warm=dm.warm_start_n()
    if regime=="daylist":
        dm.seed_day_list(env,horizon=STEPS); dm.seed_initial(env,n=n_warm)
    else:
        dm.seed_initial(env,n=n_warm)
    env.picker_service_steps=8; env.station_service_steps=6
    ctrl=_cls(arm)(env); onv,n,t,done=0.0,0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            n+=1
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (arm,regime,seed,round(onv,1),n,dm.arrivals)

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(r["arm"],r["regime"],int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),int(r["deliveries"]),int(r["arrivals"]))); have.add(k)
    jobs=[(a,rg,s) for s in range(SEEDS) for rg in REGIMES for a in ARMS if (a,rg,s) not in have]
    print(f"ladder_matched: {len(jobs)} runs",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["arm","regime","seed","on_time_value","deliveries","arrivals"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=2),1):
                rows.append(res)
                if k%300==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("ladder_matched: DONE",flush=True)

if __name__=="__main__":
    main()
