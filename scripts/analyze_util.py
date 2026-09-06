import csv, collections, statistics as st, math
R=collections.defaultdict(dict); ARR=collections.defaultdict(list)
for r in csv.DictReader(open('results/utilisation.csv')):
    R[(r['agvs'],r['pickers'],int(r['seed']))][(float(r['util']),float(r['urg_w']))]=float(r['on_time_value'])
    ARR[float(r['util'])].append(int(r['arrivals']))
UW=[0.0,4.0,8.0,12.0]
for u in sorted(ARR):
    print("utilisation %.2f  ->  %.1f arrivals/window (mean)"%(u,st.mean(ARR[u])))
for util in sorted({k[0] for v in R.values() for k in v}):
    print(); print("="*70); print("URG_W sweep @ utilisation %.2f  (paired vs URG_W=8)"%util); print("="*70)
    print("   %-8s %6s %11s %10s %11s"%('URG_W','n','vs 8','t','mean otv'))
    for w in UW:
        pr=[(v[(util,w)],v[(util,8.0)]) for v in R.values() if (util,w) in v and (util,8.0) in v]
        if len(pr)<5: continue
        d=[a-b for a,b in pr]; m=st.mean(d); sd=st.stdev(d) if len(d)>1 else 0
        t=m/(sd/math.sqrt(len(d))) if sd else float('nan')
        print("   %-8g %6d %+11.2f %10s %11.1f"%(w,len(d),m,('%+.2f'%t) if sd else 'IDENTICAL',
                                                 st.mean([a for a,b in pr])))
    best=max(UW,key=lambda w: st.mean([v[(util,w)] for v in R.values() if (util,w) in v] or [0]))
    print("   -> argmax URG_W = %g"%best)
    for lab,par in (('evens',0),('odds',1)):
        b=max(UW,key=lambda w: st.mean([v[(util,w)] for k,v in R.items() if k[2]%2==par and (util,w) in v] or [0]))
        print("      split-half %-6s argmax = %g"%(lab,b))
