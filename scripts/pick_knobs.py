"""Resolve the corrected-world knob table from every sweep, then emit it as JSON for downstream runs.

RULE (per the recorded M1 method): adopt the argmax ONLY where split-half AGREES (evens vs odds -- seeds
tile a day, so first-half/second-half would compare morning to evening). Split-half is the promised
validation and is a reproducibility check, not a significance test: for a value you must set anyway, the
argmax is the maximum-likelihood choice and split-half is the guard against the winner's curse.
Where the halves disagree, keep the shipped value -- changing on no evidence is adopting noise.
"""
import csv, json, os, collections, statistics as st
FILES=["results/knobs_realworld.csv","results/knobs_confirm.csv","results/knobs_ext.csv"]
SHIPPED={("URG_W","daylist"):0.0,("URG_W","stream"):8.0,("W_SYNC","daylist"):0.3,
         ("W_SYNC","stream"):0.3,("RATE_ALPHA","daylist"):5.0,("RATE_ALPHA","stream"):5.0,
         ("SEQ_DEPTH","daylist"):5.0,("SEQ_DEPTH","stream"):5.0}
R=collections.defaultdict(lambda: collections.defaultdict(dict))
for f in FILES:
    if not os.path.exists(f): continue
    for r in csv.DictReader(open(f)):
        key=(r["knob"],r["regime"])
        R[key][(r["agvs"],r["pickers"],int(r["seed"]))][float(r["value"])]=float(r["on_time_value"])
out={}
print("%-12s %-8s %8s %8s %9s %s"%("knob","regime","shipped","chosen","delta%","split-half"))
for key,cells in sorted(R.items()):
    knob,regime=key
    vals=sorted({v for c in cells.values() for v in c})
    if len(vals)<2: continue
    mean=lambda v,sub: st.mean([c[v] for k,c in cells.items() if v in c and (sub is None or k[2]%2==sub)] or [0])
    best=max(vals,key=lambda v: mean(v,None))
    ev=max(vals,key=lambda v: mean(v,0)); od=max(vals,key=lambda v: mean(v,1))
    agree = ev==od
    ship=SHIPPED.get(key,best)
    chosen = best if agree else ship
    base=mean(ship,None) or 1.0
    out["%s|%s"%(knob,regime)]=chosen
    print("%-12s %-8s %8g %8g %+8.2f%% %s"%(knob,regime,ship,chosen,
          100*(mean(chosen,None)-base)/base,"AGREE" if agree else "disagree -> keep shipped"))
json.dump(out,open("results/knob_table_corrected.json","w"),indent=1)
print("\nwrote results/knob_table_corrected.json")
