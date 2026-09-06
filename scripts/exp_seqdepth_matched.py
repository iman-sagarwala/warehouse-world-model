"""SEQ_DEPTH regime question, WORKLOAD-MATCHED. High priority.

THE BUG THIS FIXES: stream received `seed_initial` warm-start orders ON TOP OF the same arrival stream
that wave generates, so stream carried **+29.7% more orders** (84.7 vs 65.3) and +29% more available
value. Every cross-regime statement was therefore confounded -- including "the rollout helps on stream
but hurts on wave", since a busier system is exactly where lookahead should pay more. (This confound
was found and fixed once before for the VoPI measurement and had returned, now worse because
`warm_start_n()` varies with time of day.)

FIX: BOTH regimes get the warm start. Wave = warm start + all arrivals released at t=0; stream = warm
start + the same arrivals revealed over time. Only VISIBILITY differs, which is the intended contrast.

n = 324 seeds x 3 fleets = 972 paired, which covers the 958 needed to resolve the observed
SEQ_DEPTH effect at t>=2 (power computed from measured variance, pre-committed, tested once).
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","324")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/seqdepth_matched.csv")
FLEETS=[(4,4),(8,6),(9,9)]; REGIMES=["daylist","stream"]; VALS=[0,1,2,3,5]

def one(job):
    val,regime,agv,pk,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    C=type("_D",(cp._SqWidePkRateAdaptive,),{"SEQ_DEPTH":val})
    env=gym.make(f"wwm_sim-largedense-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm
    n_warm=dm.warm_start_n()
    if regime=="daylist":
        dm.seed_day_list(env,horizon=STEPS)     # all arrivals, released at t=0
        dm.seed_initial(env,n=n_warm)           # + the SAME warm start stream gets
    else:
        dm.seed_initial(env,n=n_warm)           # warm start, then arrivals revealed over time
    env.picker_service_steps=8; env.station_service_steps=6
    ctrl=C(env); onv,t,done=0.0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (float(val),regime,agv,pk,seed,round(onv,1),dm.arrivals)

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(float(r["value"]),r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),int(r["arrivals"]))); have.add(k)
    jobs=[(v,rg,ag,pk,s) for s in range(SEEDS) for v in VALS for rg in REGIMES for (ag,pk) in FLEETS
          if (float(v),rg,ag,pk,s) not in have]
    print(f"seqdepth_matched: {len(jobs)} runs · workload-matched · n={SEEDS}x3 fleets",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["value","regime","agvs","pickers","seed","on_time_value","arrivals"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%500==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("seqdepth_matched: DONE",flush=True)

if __name__=="__main__":
    main()
