"""TWO-PART FOLLOW-UP on the corrected world. No disturbances, no battery.

PART A — CONFIRMATORY, 486 seeds (= 3 simulated days), bar |t| >= 2.
  Two PRE-SPECIFIED hypotheses, chosen before seeing this data, one test each, no maximum taken --
  so no multiple-comparison correction applies and t>=2 is the right bar (the sweep's t>=3 was
  Bonferroni over 30+ arms where the max was selected).
    W_SYNC    0 vs 0.3  on stream   (split-half agreed on 0;   +0.97%, t=+1.90)
    SEQ_DEPTH 2 vs 5    on stream   (split-half agreed on 2;   +1.65%, t=+1.04)

PART B — CLUSTERED, 162 seeds, finer comb around the two winners whose split-half DISAGREED. Those
  cleared 2% but neither half of the data picked them, which is the signature of selecting noise; a
  tighter comb says whether there is a real local structure or just a spike.
    SEQ_DEPTH  daylist  {1,2,3,5}        (argmax 1 at +3.72%, halves said 8 and 3)
    RATE_ALPHA stream   {3.5,4,4.5,5}    (argmax 4 at +2.02%, halves said 7 and 4)
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/knobs_confirm.csv")
FLEETS=[(4,4),(8,6),(9,9)]
# BOUNDARY EXTENSION (2026-08-06). Both clustered winners landed on the FLOOR of their comb with
# split-half agreement and a MONOTONE trend -- the method rule says extend at a boundary.
# SEQ_DEPTH=0 DISABLES THE ROLLOUT ENTIRELY, so this asks whether the project's core contribution
# actively hurts on day-list in the corrected world.
JOBS_SPEC=[("ext","SEQ_DEPTH","daylist",[0,1],486),
           ("ext","RATE_ALPHA","stream",[2.0,2.5,3.0,3.5],486),
           # URG_W folded in at the SAME 486 seeds. It is the knob M1's only behavioural rule rests on,
           # and it is unresolved rather than flat: 3.4% spread on stream / 1.5% on day-list with NO
           # consistent split-half winner (evens 4, odds 16). That is the pattern that turned out to be
           # a WRONG COMB for SEQ_DEPTH and RATE_ALPHA, not noise -- so re-comb it low and tight,
           # since 0 was the pooled argmax in both regimes and sits at the floor.
           ("ext","URG_W","stream",[0.0,2.0,4.0,8.0],486),
           ("ext","URG_W","daylist",[0.0,2.0,4.0,8.0],486)]

def one(job):
    part,knob,regime,val,agv,pk,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    attrs={knob:val}
    if knob=="URG_W": attrs["URG_W_STREAM"]=val
    C=type("_K",(cp._SqWidePkRateAdaptive,),attrs)
    env=gym.make(f"wwm_sim-largedense-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm
    if regime=="daylist": dm.seed_day_list(env,horizon=STEPS)
    else: dm.seed_initial(env,n=dm.warm_start_n())
    env.one_way=True; env.picker_service_steps=8; env.station_service_steps=6
    ctrl=C(env); onv,t,done=0.0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (part,knob,regime,float(val),agv,pk,seed,round(onv,1))

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(r["part"],r["knob"],r["regime"],float(r["value"]),int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),)); have.add(k)
    jobs=[]
    for part,knob,regime,vals,nseed in JOBS_SPEC:
        for s in range(nseed):
            for (ag,pk) in FLEETS:
                for v in vals:
                    k=(part,knob,regime,float(v),ag,pk,s)
                    if k not in have: jobs.append((part,knob,regime,v,ag,pk,s))
    print(f"knobs_confirm: {len(jobs)} runs",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["part","knob","regime","value","agvs","pickers","seed","on_time_value"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%500==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("knobs_confirm: DONE",flush=True)

if __name__=="__main__":
    main()
