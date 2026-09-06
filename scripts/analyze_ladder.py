import csv, collections, statistics as st, math
R=collections.defaultdict(dict); D=collections.defaultdict(dict)
for r in csv.DictReader(open('results/realworld_ladder.csv')):
    R[int(r['seed'])][r['arm']]=float(r['on_time_value']); D[int(r['seed'])][r['arm']]=int(r['deliveries'])
ARMS=["fifo","priority","feasible","value","rush","champion"]
LAB={"fifo":"FIFO (oldest first)","priority":"+ nearest-first","feasible":"+ drop impossible",
     "value":"+ rank by value","rush":"+ deadline urgency","champion":"CHAMPION (rollout)"}
base="fifo"
print("%-24s %6s %10s %9s %10s %9s"%("controller","n","on-time val","vs FIFO","deliveries","vs prev"))
prev=None
for a in ARMS:
    vals=[R[s][a] for s in R if a in R[s]]
    dels=[D[s][a] for s in D if a in D[s]]
    if not vals: continue
    m=st.mean(vals); dm=st.mean(dels)
    b=st.mean([R[s][base] for s in R if base in R[s]])
    step=""
    if prev is not None:
        pr=[(R[s][a],R[s][prev]) for s in R if a in R[s] and prev in R[s]]
        d=[x-y for x,y in pr]; sd=st.stdev(d) if len(d)>1 else 0
        t=st.mean(d)/(sd/math.sqrt(len(d))) if sd else float('nan')
        step="%+.1f t=%+.1f"%(st.mean(d),t)
    print("%-24s %6d %10.1f %+8.1f%% %10.1f %9s"%(LAB[a],len(vals),m,100*(m-b)/b,dm,step))
    prev=a
print()
pr=[(R[s]["champion"],R[s]["rush"]) for s in R if "champion" in R[s] and "rush" in R[s]]
d=[x-y for x,y in pr]; sd=st.stdev(d); t=st.mean(d)/(sd/math.sqrt(len(d)))
print("CHAMPION vs RUSH (the core claim): %+.2f  (%+.2f%%)  t=%+.2f  n=%d  W/L %d/%d"%(
    st.mean(d),100*st.mean(d)/st.mean([y for x,y in pr]),t,len(d),
    sum(1 for x in d if x>0),sum(1 for x in d if x<0)))
for lab,par in (("evens",0),("odds",1)):
    dd=[R[s]["champion"]-R[s]["rush"] for s in R if s%2==par and "champion" in R[s] and "rush" in R[s]]
    print("   split-half %-6s %+.2f (n=%d)"%(lab,st.mean(dd),len(dd)))
