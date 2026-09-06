"""M2.0 GATE on the DENSE (realistic) map, using the CORRECTED knob table.

The disturbance premise failed on the old floor, but that floor was 69% OPEN AISLE -- one-cell debris
always had a parallel lane. The dense map is 55% storage with 1-cell lanes, which is the condition that
could make a blocked cell actually cost something. This is a GATE: if cost is still ~0%, stop and write
the negative rather than building the belief-driven decision logic on top of an effect that is not there.

ARMS (all on the dense map, corrected world, corrected knobs):
  clean        no disturbances -- the ceiling
  clairvoyant  router reads GROUND TRUTH (status quo)
  belief_los   router reads a line-of-sight belief map; execution still hits ground truth
  exposure     router IGNORES debris entirely (b_hard>1) -- the unconfounded exposure/sharing baseline
"""
import csv, json, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","162")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/m2_dense.csv")
FLEETS=[(8,6),(9,9)]; REGIMES=["daylist","stream"]
ARMS=["clean","clairvoyant","belief_los","exposure"]
RATES=[float(x) for x in os.environ.get("RATES","0.002,0.037").split(",")]
KNOBS=json.load(open("results/knob_table_corrected.json")) if os.path.exists("results/knob_table_corrected.json") else {}

def one(job):
    arm,rate,regime,agv,pk,seed=job
    import numpy as np, gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    from wwm_sim.rumor_map import BetaRumorMap
    import congestion_policies as cp
    attrs={}
    for k,v in KNOBS.items():
        knob,rg=k.split("|")
        if rg==regime:
            attrs[knob]=v
            if knob=="URG_W": attrs["URG_W_STREAM" if rg=="stream" else "URG_W_DAYLIST"]=v
    C=type("_Champ",(cp._SqWidePkRateAdaptive,),attrs)
    env=gym.make(f"wwm_sim-largedense-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    dm=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS,window_index=seed,n_windows=162,
                   value_dist="lognormal",value_sigma=1.0,value_hi=200.0)
    env.demand_model=dm
    if regime=="daylist": dm.seed_day_list(env,horizon=STEPS)
    else: dm.seed_initial(env,n=dm.warm_start_n())
    env.picker_service_steps=8; env.station_service_steps=6
    if arm!="clean":
        env.disturb_rate=rate; env.disturb_amnesty_rate=0.037
        env._disturb_rng=np.random.RandomState(10_000+seed)
        env.rumor_map=BetaRumorMap(env.grid_size); env.los_sensing=True
        env.use_belief_routing = arm in ("belief_los","exposure")
        if arm=="exposure": env.b_hard=1.1
    ctrl=C(env); onv,t,done=0.0,0,False
    crossers={}
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for c in (getattr(env,"disturbed",None) or set()):
            s=crossers.setdefault(c,set())
            for a in env.agents:
                for (px,py) in (a.path or []):
                    if (py,px)==c: s.add(a.id); break
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    nc=len(crossers); sh=(sum(len(v) for v in crossers.values())/nc) if nc else 0.0
    return (arm,rate,regime,agv,pk,seed,round(onv,1),nc,round(sh,3))

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(r["arm"],float(r["rate"]),r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),int(r["n_dist_cells"]),float(r["mean_crossers"]))); have.add(k)
    jobs=[]
    for s in range(SEEDS):
        for rg in REGIMES:
            for (ag,pk) in FLEETS:
                for rate in RATES:
                    for a in ARMS:
                        if a=="clean" and rate!=RATES[0]: continue
                        k=(a,rate,rg,ag,pk,s)
                        if k not in have: jobs.append(k)
    print(f"m2_dense: {len(jobs)} runs · knobs={KNOBS}",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["arm","rate","regime","agvs","pickers","seed","on_time_value","n_dist_cells","mean_crossers"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=2),1):
                rows.append(res)
                if k%300==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("m2_dense: DONE",flush=True)

if __name__=="__main__":
    main()
