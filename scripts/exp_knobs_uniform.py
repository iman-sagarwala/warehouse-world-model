"""DEFINITIVE KNOB SWEEP — one uniform n for EVERY knob and value.

WHY UNIFORM: within a knob's comb, unequal n biases the argmax toward whichever value got more data.
Across knobs it is defensible but invites the obvious reviewer question, so we remove the question
instead of defending it. Every (knob, value, regime, fleet) cell gets the SAME 486 seeds.

n = 486 seeds x 3 fleets = 1,458 paired per arm. Power (from the measured variance):
  detects the observed SEQ_DEPTH day-list effect (+4.6%) at t>=2 with n=958  -> covered
  detects the observed RATE_ALPHA stream effect (+3.3%) at t>=2 with n=823   -> covered
  a 2% effect anywhere would need ~5,100 paired -> NOT covered; report the MDE alongside.

PRE-COMMITMENT (states the p-hacking guard in the artifact itself): the hypotheses were selected by
SPLIT-HALF AGREEMENT BEFORE any decision to add seeds, n was computed from observed variance and not
from proximity to a threshold, and the result is tested ONCE at this n whatever it shows. No optional
stopping.

Resumes from the earlier CSVs, so completed cells are not re-run.
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","486")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/knobs_uniform.csv")
FLEETS=[(4,4),(8,6),(9,9)]; REGIMES=["daylist","stream"]
COMBS={"URG_W":[0.0,4.0,8.0,12.0],"SEQ_DEPTH":[0,1,2,3,5],
       "RATE_ALPHA":[2.0,3.0,4.0,5.0,6.0],"W_SYNC":[0.0,0.15,0.3,0.5]}

def one(job):
    knob,val,regime,agv,pk,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    attrs={knob:val}
    if knob=="URG_W": attrs["URG_W_STREAM" if regime=="stream" else "URG_W_DAYLIST"]=val
    C=type("_K",(cp._SqWidePkRateAdaptive,),attrs)
    env=gym.make(f"wwm_sim-largedense-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm
    if regime=="daylist": dm.seed_day_list(env,horizon=STEPS)
    else: dm.seed_initial(env,n=dm.warm_start_n())
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
    for src in [OUT,"results/knobs_ext.csv","results/knobs_confirm.csv","results/knobs_realworld.csv"]:
        if not os.path.exists(src): continue
        for r in csv.DictReader(open(src)):
            k=(r["knob"],float(r["value"]),r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
            if k in have: continue
            if k[0] in COMBS and k[1] in [float(x) for x in COMBS[k[0]]] and k[5]<SEEDS:
                rows.append(k+(float(r["on_time_value"]),)); have.add(k)
    jobs=[(kn,v,rg,ag,pk,s) for s in range(SEEDS) for kn in COMBS for v in COMBS[kn]
          for rg in REGIMES for (ag,pk) in FLEETS
          if (kn,float(v),rg,ag,pk,s) not in have]
    print(f"knobs_uniform: {len(jobs)} new runs (reused {len(rows)}) · n={SEEDS} seeds x 3 fleets",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["knob","value","regime","agvs","pickers","seed","on_time_value"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%1000==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("knobs_uniform: DONE",flush=True)

if __name__=="__main__":
    main()
