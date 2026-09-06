"""REALISTIC LOAD. The arrival rate was a bare constant implying ~47% fleet utilisation; real DCs run
far busier. `utilisation` now derives it: rate = utilisation * n_agvs / task_steps.

Tests URG_W {0,4,8,12} at legacy load (0.47) vs realistic load (0.80), stream, under the FIXED clock
(window_index=seed, 36 windows/day -> 108 seeds = exactly 3 days). Two questions at once:
  does the project's only regime rule survive the clock fix AND a realistic offered load?
Split-half is EVENS vs ODDS (seeds tile the day)."""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","108")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/utilisation.csv")
FLEETS=[(4,4),(6,6),(8,6),(8,8),(9,9)]; UTILS=[0.47,0.80]; URGWS=[0.0,4.0,8.0,12.0]

def one(job):
    util,uw,agv,pk,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    C=type("_U%g"%uw,(cp._SqWidePkRateAdaptive,),{"URG_W_STREAM":uw,"URG_W":uw})
    env=gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,
                   window_index=seed,n_windows=36,utilisation=util)
    env.demand_model=dm; dm.seed_initial(env,n=dm.warm_start_n())
    ctrl=C(env); onv,t,done=0.0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (util,uw,agv,pk,seed,round(onv,1),dm.arrivals)

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(float(r["util"]),float(r["urg_w"]),int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),int(r["arrivals"]))); have.add(k)
    jobs=[(u,w,ag,pk,s) for s in range(SEEDS) for u in UTILS for (ag,pk) in FLEETS for w in URGWS
          if (u,w,ag,pk,s) not in have]
    print(f"utilisation: {len(jobs)} runs, utils={UTILS}, URG_W={URGWS}",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            c=csv.writer(fh); c.writerow(["util","urg_w","agvs","pickers","seed","on_time_value","arrivals"]); c.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%400==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("utilisation: DONE",flush=True)

if __name__=="__main__":
    main()
