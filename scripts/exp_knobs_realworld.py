"""M1 KNOB SWEEPS RE-RUN ON THE CORRECTED WORLD.

Everything M1 was tuned on has changed: storage 31%->55%, stations 10->3, one-way lanes, lognormal
values, picker service 8 steps, station service 6/item, utilisation-anchored arrivals. Throughput fell
66% (171 -> 58 deliveries), so the old table cannot be assumed to transfer.

NO DISTURBANCES, NO BATTERY (both default off) -- per instruction, so this isolates the decision layer
on a realistic but clean floor.

Knobs and combs are the M1 ones, so the results are directly comparable in SHAPE:
  URG_W {0,4,8,12,16} · W_SYNC {0,0.15,0.3,0.5} · RATE_ALPHA {3,4,5,6,7} · SEQ_DEPTH {1,2,3,5,8}
Seeds are windows (window_index=seed, 36/day). Split-half must be EVENS vs ODDS.
Env: SEEDS, NPROC, KNOB (default all), OUT.
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","162")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/knobs_realworld.csv")
FLEETS=[(4,4),(8,6),(9,9)]
REGIMES=["daylist","stream"]
COMBS={"URG_W":[0.0,4.0,8.0,12.0,16.0],"W_SYNC":[0.0,0.15,0.3,0.5],
       "RATE_ALPHA":[3.0,4.0,5.0,6.0,7.0],"SEQ_DEPTH":[1,2,3,5,8]}
KNOBS=[k for k in os.environ.get("KNOB","URG_W,SEQ_DEPTH,RATE_ALPHA,W_SYNC").split(",") if k in COMBS]

def one(job):
    knob,val,regime,agv,pk,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    attrs={knob:val}
    if knob=="URG_W": attrs["URG_W_STREAM"]=val          # champion reads the regime-specific one
    C=type("_K",(cp._SqWidePkRateAdaptive,),attrs)
    env=gym.make(f"wwm_sim-largedense-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm
    if regime=="daylist": dm.seed_day_list(env,horizon=STEPS)
    else: dm.seed_initial(env,n=dm.warm_start_n())
    env.one_way=True; env.picker_service_steps=8; env.station_service_steps=6
    ctrl=C(env); onv,n,t,done=0.0,0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            n+=1
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (knob,val,regime,agv,pk,seed,round(onv,1),n)

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(r["knob"],float(r["value"]),r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),int(r["deliveries"]))); have.add(k)
    jobs=[(kn,v,rg,ag,pk,s) for s in range(SEEDS) for kn in KNOBS for v in COMBS[kn]
          for rg in REGIMES for (ag,pk) in FLEETS
          if (kn,float(v),rg,ag,pk,s) not in have]
    print(f"knobs_realworld: {len(jobs)} runs · knobs={KNOBS} · no disturbances, no battery",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["knob","value","regime","agvs","pickers","seed","on_time_value","deliveries"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%400==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("knobs_realworld: DONE",flush=True)

if __name__=="__main__":
    main()
