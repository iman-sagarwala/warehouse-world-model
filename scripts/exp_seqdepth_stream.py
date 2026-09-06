"""GAP IN M1: on STREAM, SEQ_DEPTH 3 and 5 were never run on the same cells, so the frozen value 5
rests only on beating depth 0. SEQ_DEPTH is a FUTURE knob, and the space-vs-future principle predicts
future knobs are REGIME-DEPENDENT (as URG_W is). Run 3 vs 5 vs 7 paired, stream, matched cells."""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","120")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/seqdepth_stream.csv")
FLEETS=[(4,4),(6,6),(8,6),(8,8),(9,9)]; DEPTHS=[2,3,4,5,7]

def one(job):
    depth, agv, pk, seed = job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    C = type("_D%d"%depth, (cp._SqWidePkRateAdaptive,), {"SEQ_DEPTH": depth})
    env=gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    env.demand_model=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS)
    env.demand_model.seed_initial(env,n=12)
    ctrl=C(env); onv,t,done=0.0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (depth,agv,pk,seed,round(onv,1))

def main():
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((int(r["depth"]),int(r["agvs"]),int(r["pickers"]),int(r["seed"]),float(r["on_time_value"])))
                have.add((int(r["depth"]),int(r["agvs"]),int(r["pickers"]),int(r["seed"])))
    # seed-major so partial results are readable (lesson from exp_yield)
    jobs=[(d,ag,pk,s) for s in range(SEEDS) for (ag,pk) in FLEETS for d in DEPTHS
          if (d,ag,pk,s) not in have]
    print(f"seqdepth_stream: {len(jobs)} runs, depths={DEPTHS}",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["depth","agvs","pickers","seed","on_time_value"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%200==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("seqdepth_stream: DONE",flush=True)

if __name__=="__main__":
    main()
