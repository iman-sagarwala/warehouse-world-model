import csv, collections, statistics as st, math
R=collections.defaultdict(dict)
for r in csv.DictReader(open('results/knobs_confirm.csv')):
    R[(r['part'],r['knob'],r['regime'],r['agvs'],r['pickers'],int(r['seed']))][float(r['value'])]=float(r['on_time_value'])
def block(part,knob,regime,ref,title,bar):
    keys=[k for k in R if k[0]==part and k[1]==knob and k[2]==regime]
    if not keys: return
    vals=sorted({v for k in keys for v in R[k]})
    print("="*74); print(title); print("="*74)
    print("  %-8s %6s %11s %10s %9s %s"%("value","n","mean otv","vs %g"%ref,"t","split-half"))
    for v in vals:
        pr=[(R[k][v],R[k][ref]) for k in keys if v in R[k] and ref in R[k]]
        if len(pr)<10: continue
        d=[a-b for a,b in pr]; m=st.mean(d); sd=st.stdev(d) if len(d)>1 else 0
        t=m/(sd/math.sqrt(len(d))) if sd else float('nan')
        mo=st.mean([a for a,b in pr])
        mark=" <-- PASSES t>=%g"%bar if (sd and abs(t)>=bar and m>0) else ""
        print("  %-8g %6d %11.1f %+10.2f %9s%s"%(v,len(d),mo,m,('%+.2f'%t) if sd else 'IDENT',mark))
    sh=[]
    for par in (0,1):
        kk=[k for k in keys if k[5]%2==par]
        sh.append(max(vals,key=lambda v: st.mean([R[k][v] for k in kk if v in R[k]] or [0])))
    print("  argmax split-half: evens %g / odds %g  -> %s"%(sh[0],sh[1],
          "AGREE" if sh[0]==sh[1] else "DISAGREE"))
block("confirm","W_SYNC","stream",0.3,"PART A · W_SYNC on stream  (confirmatory, 486 seeds, bar t>=2)",2)
block("confirm","SEQ_DEPTH","stream",5.0,"PART A · SEQ_DEPTH on stream  (confirmatory, 486 seeds, bar t>=2)",2)
block("cluster","SEQ_DEPTH","daylist",5.0,"PART B · SEQ_DEPTH day-list  (clustered comb, 162 seeds)",3)
block("cluster","RATE_ALPHA","stream",5.0,"PART B · RATE_ALPHA stream  (clustered comb, 162 seeds)",3)
