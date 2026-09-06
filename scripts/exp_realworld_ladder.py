"""Controller ladder on the FULLY REALISTIC world, ONE-WAY LANES ON.

SEEDS=162 because at the corrected clock (1.069 s/tick) an episode is 8.9 min, so 162 windows tile
EXACTLY 24 h. 60 would have been both below the 120-seed rule and not a whole day.

World: dense geometry (55% storage, 4x6 Kiva clusters, 1-cell lanes), 3 stations (throughput-balanced),
one-way lanes, lognormal order values, picker service 8 steps, station service 6 steps/item.
Everything M1 was tuned on has changed, so the ladder has to be re-established from the bottom.

  fifo      FIFOController          take the oldest request
  priority  PriorityController      + nearest-first
  feasible  FeasiblePriorityController + drop the impossible
  value     ValuePriorityController + rank by task value
  rush      RushValueController     + deadline urgency (the pre-rollout heuristic)
  champion  _SqWidePkRateAdaptive   sequencer rollout + value-rate pickers
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","162")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/realworld_ladder.csv")
ENVID=os.environ.get("ENVID","wwm_sim-largedense-8agvs-6pickers-globalobs-v1")
ONEWAY=os.environ.get("ONEWAY","1")=="1"
ARMS=[a for a in os.environ.get("ARMS","fifo,priority,feasible,value,rush,champion").split(",") if a]

def _cls(a):
    import sim_priority as sp, congestion_policies as cp
    return {"fifo":sp.FIFOController,"priority":sp.PriorityController,
            "feasible":sp.FeasiblePriorityController,"value":sp.ValuePriorityController,
            "rush":sp.RushValueController,"champion":cp._SqWidePkRateAdaptive}[a]

def one(job):
    arm,seed=job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    env=gym.make(ENVID).unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm; dm.seed_day_list(env,horizon=STEPS)
    if ONEWAY: env.one_way=True
    env.picker_service_steps=8; env.station_service_steps=6
    ctrl=_cls(arm)(env); onv,n,t,done=0.0,0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            n+=1
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (arm,seed,round(onv,1),n)

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                rows.append((r["arm"],int(r["seed"]),float(r["on_time_value"]),int(r["deliveries"])))
                have.add((r["arm"],int(r["seed"])))
    jobs=[(a,s) for s in range(SEEDS) for a in ARMS if (a,s) not in have]
    print(f"realworld_ladder: {len(jobs)} runs · one_way={ONEWAY} · {ENVID}",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["arm","seed","on_time_value","deliveries"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=2),1):
                rows.append(res)
                if k%60==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("realworld_ladder: DONE",flush=True)

if __name__=="__main__":
    main()
