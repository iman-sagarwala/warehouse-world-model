"""M2 STEP 0+1 GATE. Two questions, before any belief-driven decision logic is built:

  Q1  Does a disturbance cost anything once the router is NOT clairvoyant?
      Baseline `find_path` reads `env.disturbed` (GROUND TRUTH), so routes dodge blockages the
      instant they spawn — nobody ever encounters one. `use_belief_routing` plans on what the fleet
      has actually OBSERVED (line-of-sight limited, decaying); execution still hits ground truth.

  Q2  Is a disturbance SHARED or PRIVATE? Count the distinct robots whose committed route crosses
      each disturbed cell before it clears. If that is ~1, the map has nobody to tell and the whole
      "one robot's pain -> fleet knowledge" claim is dead REGARDLESS of the cost in Q1.

ARMS
  clean          no disturbances at all (the ceiling)
  clairvoyant    disturbances on, router reads ground truth  (status quo)
  belief_los     disturbances on, router reads belief w/ line-of-sight occlusion
  belief_radius  disturbances on, router reads belief w/ plain Manhattan radius (sensing ablation)

Env: SEEDS, NPROC, RATE (disturb_rate multiplier), OUT.
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","60")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/m2_gate.csv")
FLEETS=[(8,6),(8,8)]; REGIMES=["daylist","stream"]
ARMS=["clean","exposure","exp_pick","exp_traffic","exp_both"]
RATES=[float(x) for x in os.environ.get("RATES","0.002,0.01,0.05").split(",")]

def one(job):
    arm, rate, regime, agv, pk, seed = job
    import numpy as np
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    from wwm_sim.rumor_map import BetaRumorMap
    from congestion_policies import _SqWidePkRateAdaptive as C
    env=gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    env.demand_model=DemandModel(env,seed=seed,exogenous=True,horizon=STEPS)
    if regime=="daylist": env.demand_model.seed_day_list(env,horizon=STEPS)
    else: env.demand_model.seed_initial(env,n=12)
    if arm!="clean":
        env.disturb_rate=rate; env.disturb_amnesty_rate=0.037
        env._disturb_rng=np.random.RandomState(10_000+seed)
        env.rumor_map=BetaRumorMap(env.grid_size)
        env.los_sensing=True
        env.use_belief_routing=arm.startswith("exp")
        if arm in ("exp_pick","exp_both"):
            env.amnesty_at_pick=True          # calibrated 3.7% also at the POD-side handling event
        if arm in ("exp_traffic","exp_both"):
            env.traffic_weighted_blockage=True  # debris where work happens, not uniform on highways
        if arm.startswith("exp"):
            # EXPOSURE ARM: b_hard above 1.0 means NOTHING is ever believed blocked, so routing
            # ignores disturbances entirely while execution still hits ground truth. This is the
            # unconfounded sharing measurement: how many distinct robots WOULD cross each disturbed
            # cell absent any avoidance. The earlier mean_crossers was confounded -- arms that avoid
            # better cross less, so it measured knowledge, not exposure.
            env.b_hard=1.1
    ctrl=C(env); onv,t,done=0.0,0,False
    # Q2: distinct robots whose CURRENT path crosses each disturbed cell, while it is disturbed
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
    ncells=len(crossers)
    shared=(sum(len(v) for v in crossers.values())/ncells) if ncells else 0.0
    return (arm,rate,regime,agv,pk,seed,round(onv,1),ncells,round(shared,3))

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(r["arm"],float(r["rate"]),r["regime"],int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),int(r["n_dist_cells"]),float(r["mean_crossers"])))
                have.add(k)
    jobs=[]
    for s in range(SEEDS):
        for rg in REGIMES:
            for (ag,pk) in FLEETS:
                for rate in RATES:
                    for a in ARMS:
                        if a=="clean" and rate!=RATES[0]: continue   # clean is rate-independent
                        k=(a,rate,rg,ag,pk,s)
                        if k not in have: jobs.append(k)
    print(f"m2_gate: {len(jobs)} runs, arms={ARMS}, rates={RATES}",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["arm","rate","regime","agvs","pickers","seed","on_time_value","n_dist_cells","mean_crossers"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=2),1):
                rows.append(res)
                if k%200==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("m2_gate: DONE",flush=True)

if __name__=="__main__":
    main()
