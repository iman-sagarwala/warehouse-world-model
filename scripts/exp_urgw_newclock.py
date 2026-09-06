"""DOES THE PROJECT'S ONLY REGIME RULE SURVIVE THE TIMESCALE FIX?

URG_W = 8 on stream is the single behavioural rule M1 produced. It was tuned under the OLD demand
clock, where `period=250` swung demand +-80% inside what is really a 10-minute window -- a mis-scaled
diurnal cycle. Under the fixed clock, diurnal variation lives ACROSS episodes (window_index=seed, 144
ten-minute windows tiling 24 h) and within-episode variation is carried by the Hawkes burst process.

If 8 still wins, the timescale fix is a free realism upgrade.
If it does not, the headline regime rule was an artifact of a mis-scaled parameter -- which is far
better found now than in review.

SCALE (user, 2026-08-06): 4 m cells -> step = 4 m / 1.5 m/s x 1.8 overhead = 4.8 s -> episode = 500 x
4.8 s = 2,400 s = 40 min -> 36 windows/day -> **108 seeds = EXACTLY 3 days**, 3 replicates per
time-of-day slot. Cell size changes NO simulation behaviour (the grid is unchanged) -- it only sets what
a step means in wall-clock, hence windows/day, hence the seed arithmetic.
NB split-half must be EVENS vs ODDS, never 0-53 vs 54-107, which would be halves of the DAY.
"""
import csv, os, sys
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
STEPS=500; SEEDS=int(os.environ.get("SEEDS","108")); NPROC=int(os.environ.get("NPROC","8"))
OUT=os.environ.get("OUT","results/urgw_newclock.csv")
FLEETS=[(4,4),(6,6),(8,6),(8,8),(9,9)]
URGWS=[0.0,4.0,8.0,12.0]
CLOCKS=["new","old"]          # old = legacy period=250, for a paired before/after

def one(job):
    clock, uw, agv, pk, seed = job
    import gymnasium as gym, wwm_sim  # noqa
    from wwm_sim.demand import DemandModel
    import congestion_policies as cp
    C = type("_U%g"%uw, (cp._SqWidePkRateAdaptive,), {"URG_W_STREAM": uw, "URG_W": uw})
    env=gym.make(f"wwm_sim-large-{agv}agvs-{pk}pickers-globalobs-v1").unwrapped
    env.reset(seed=seed); env.request_queue=[]
    kw=dict(seed=seed, exogenous=True, horizon=STEPS)
    if clock=="new": kw.update(window_index=seed, n_windows=36)
    dm=DemandModel(env, **kw); env.demand_model=dm
    dm.seed_initial(env, n=dm.warm_start_n())
    ctrl=C(env); onv,t,done=0.0,0,False
    while not done and t<STEPS:
        _,_,term,trunc,_i=env.step(ctrl.act()); t+=1
        for o in getattr(env,"fulfilled_this_step",[]):
            if o.deadline is not None and t<=o.deadline: onv+=o.value
        done=all(term) or all(trunc)
    return (clock,uw,agv,pk,seed,round(onv,1))

def main():
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    rows,have=[],set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for r in csv.DictReader(fh):
                k=(r["clock"],float(r["urg_w"]),int(r["agvs"]),int(r["pickers"]),int(r["seed"]))
                rows.append(k+(float(r["on_time_value"]),)); have.add(k)
    jobs=[(c,u,ag,pk,s) for s in range(SEEDS) for c in CLOCKS for (ag,pk) in FLEETS for u in URGWS
          if (c,u,ag,pk,s) not in have]     # seed-major: partials are readable
    print(f"urgw_newclock: {len(jobs)} runs, clocks={CLOCKS}, URG_W={URGWS}",flush=True)
    def _w():
        with open(OUT,"w",newline="",encoding="utf-8") as fh:
            w=csv.writer(fh); w.writerow(["clock","urg_w","agvs","pickers","seed","on_time_value"]); w.writerows(rows)
    if jobs:
        with mp.Pool(NPROC) as pool:
            for k,res in enumerate(pool.imap_unordered(one,jobs,chunksize=4),1):
                rows.append(res)
                if k%400==0: _w(); print(f"  {k}/{len(jobs)}",flush=True)
    _w(); print("urgw_newclock: DONE",flush=True)

if __name__=="__main__":
    main()
