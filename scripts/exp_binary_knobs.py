"""BINARY knob tests — asking DIRECTION, not argmax.

Split-half on the argmax asks "do both halves pick the same value out of 4-6 near-identical options?"
When candidates differ by fractions of a percent that fails even when a real effect exists: it is a test
built to find a PEAK, and these knobs have a SLOPE. The data already showed the direction consistently
while the argmax test discarded it -- for URG_W both halves REJECT 8, they just disagree on the
replacement.

So collapse each comb to a binary and test the pair directly. Two ways to be wrong instead of six.
  URG_W       low = 1   vs  high = 8    (shipped 8 on stream)
  RATE_ALPHA  low = 3   vs  high = 6    (shipped 5)
Workload-MATCHED (both regimes get the warm start). n = 324 seeds x 3 fleets = 972 paired.
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","324")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/binary_knobs.csv")
FLEETS=[(4,4),(8,6),(9,9)]; REGIMES=["daylist","stream"]
PAIRS={"URG_W":[1.0,8.0],"RATE_ALPHA":[3.0,6.0]}

def one(job):
    knob,val,regime,agv,pk,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    attrs={knob:val}
    if knob=="URG_W": attrs["URG_W_STREAM" if regime=="stream" else "URG_W_DAYLIST"]=val
    C=type("_B",(cp._SqWidePkRateAdaptive,),attrs)
    env=gym.make(f"wwm_sim-largedense-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; n_warm=dm.warm_start_n()
    if regime=="daylist":
        dm.seed_day_list(env,horizon=STEPS); dm.seed_initial(env,n=n_warm)
    else:
        dm.seed_initial(env,n=n_warm)
    env.picker_service_steps=8; env.station_service_steps=6
    ctrl=C(env); onv,t,done=0.0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (knob,float(val),regime,agv,pk,seed,round(onv,1))

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(r["knob"],float(r["value"]),r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),)); have.add(k)
    jobs=[(kn,v,rg,ag,pk,s) for s in range(SEEDS) for kn in PAIRS for v in PAIRS[kn]
          for rg in REGIMES for (ag,pk) in FLEETS if (kn,float(v),rg,ag,pk,s) not in have]
    print(f"binary_knobs: {len(jobs)} runs",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["knob","value","regime","agvs","pickers","seed","on_time_value"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%500==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("binary_knobs: DONE",flush=True)

if __name__=="__main__":
    main()
