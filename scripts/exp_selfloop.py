"""Value + safety of the SELF-LOOP FIX, paired against the champion rows already in results/yield.csv
(same fleets, regimes and seeds, run with the livelock fix but WITHOUT the self-loop fix)."""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500
SEEDS=int(os.environ.get("SEEDS","120")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/selfloop.csv")
FLEETS=[(4,4),(6,6),(8,6),(8,8),(9,9)]; REGIMES=["daylist","stream"]

def one(job):
    regime, agv, pk, seed = job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    from congestion_policies import _SqWidePkRateAdaptive as C
    env=gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    env.demand_model=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS)
    if regime=="daylist": env.demand_model.seed_day_list(env,horizon=STEPS)
    else: env.demand_model.seed_initial(env,n=12)
    ctrl=C(env); onv,t,done,coll=0.0,0,False,0
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        seen=set()
        for a in env.agents:
            k=(a.type,a.x,a.y)
            if k in seen: coll+=1
            seen.add(k)
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (regime,agv,pk,seed,round(onv,1),coll)

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"]),
                             float(r["on_time_value"]),int(r["collisions"])))
                have.add((r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"])))
    jobs=[(rg,ag,pk,s) for rg in REGIMES for (ag,pk) in FLEETS for s in range(SEEDS)
          if (rg,ag,pk,s) not in have]
    print(f"selfloop: {len(jobs)} runs",flush=True)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%200==0:
                    with open(OUT,"w",newline="",encoding="utf-8") as fh:
                        w=csv.writer(fh); w.writerow(["regime","agvs","pickers","seed","on_time_value","collisions"]); w.writerows(rows)
                    print(f"  {k}/{len(jobs)}",flush=True)
    with open(OUT,"w",newline="",encoding="utf-8") as fh:
        w=csv.writer(fh); w.writerow(["regime","agvs","pickers","seed","on_time_value","collisions"]); w.writerows(rows)
    print("selfloop: DONE",flush=True)

if __name__=="__main__":
    main()
