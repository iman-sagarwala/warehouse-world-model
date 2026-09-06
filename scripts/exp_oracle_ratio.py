"""ORACLE CEILING x FLEET RATIO, workload-matched, in one sweep.

Combines the two open questions:
  · which AGV:picker ratio is best (the +8.4% claim, never re-measured on the corrected world)
  · how much headroom the champion leaves at EACH ratio (the assignment ceiling, previously one ratio)
Answering them together is what makes them useful: a ratio that scores high but leaves a large gap is a
DIFFERENT recommendation from one that scores high because the problem is easy there.

Per ratio: champion + best-of-M perturbed rollouts (`_ChampExplore` deviates from the sequencer's
winner with p, so every rollout is a competent policy with perturbations -- best-of-M then explores the
neighbourhood ABOVE the champion, giving a LOWER bound on the ceiling).
Reported both ways, as asked: gap at the ARGMAX ratio, and gap AVERAGED over ratios.
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","12")); M=int(os.environ.get("M","60"))
NPROC=int(os.environ.get("NPROC","8")); OUT=os.environ.get("OUT","results/oracle_ratio.csv")
FLEETS=[(8,4),(8,5),(8,6),(8,7),(8,8),(8,9)]
REGIME=os.environ.get("REGIME","daylist")

def _episode(agv,pk,seed,cls,rng_seed=None,top_k=4):
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    env=gym.make(f"wwm_sim-largedense-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; n_warm=dm.warm_start_n()
    if REGIME=="daylist":
        dm.seed_day_list(env,horizon=STEPS); dm.seed_initial(env,n=n_warm)
    else:
        dm.seed_initial(env,n=n_warm)
    env.picker_service_steps=8; env.station_service_steps=6
    ctrl = cls(env) if rng_seed is None else cls(env,rng_seed=rng_seed,top_k=top_k)
    onv,t,done=0.0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return onv

def one(job):
    agv,pk,seed,m = job
    import congestion_policies as cp
    if m<0:
        return (agv,pk,seed,-1,round(_episode(agv,pk,seed,cp._SqWidePkRateAdaptive),1))
    return (agv,pk,seed,m,round(_episode(agv,pk,seed,cp._ChampExplore,rng_seed=1000*seed+m,top_k=4),1))

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(int(r["agvs"]),int(r["pickers"]),int(r["seed"]),int(r["m"]))
                rows.append(k+(float(r["on_time_value"]),)); have.add(k)
    jobs=[(ag,pk,s,m) for (ag,pk) in FLEETS for s in range(SEEDS) for m in [-1]+list(range(M))
          if (ag,pk,s,m) not in have]
    print(f"oracle_ratio: {len(jobs)} runs · {len(FLEETS)} ratios x {SEEDS} seeds x (1+{M}) · {REGIME}",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["agvs","pickers","seed","m","on_time_value"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%500==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("oracle_ratio: DONE",flush=True)

if __name__=="__main__":
    main()
