import csv, collections, statistics as st, math
R=collections.defaultdict(dict)
for r in csv.DictReader(open('results/knobs_realworld.csv')):
    R[(r['knob'],r['regime'],r['agvs'],r['pickers'],int(r['seed']))][float(r['value'])]=float(r['on_time_value'])
OLD={"URG_W":"0 daylist / 8 stream","W_SYNC":"0.3","RATE_ALPHA":"5","SEQ_DEPTH":"5"}
for knob in ["URG_W","SEQ_DEPTH","RATE_ALPHA","W_SYNC"]:
    for regime in ["daylist","stream"]:
        keys=[k for k in R if k[0]==knob and k[1]==regime]
        if not keys: continue
        vals=sorted({v for k in keys for v in R[k]})
        inc = 5.0 if knob in ("RATE_ALPHA","SEQ_DEPTH") else (0.3 if knob=="W_SYNC" else (0.0 if regime=="daylist" else 8.0))
        if inc not in vals: inc=vals[0]
        print("="*76)
        print("%s  ·  %s   (M1 shipped: %s)"%(knob,regime.upper(),OLD[knob]))
        print("  %-8s %6s %11s %9s %11s %9s"%("value","n","mean otv","vs ship","t","differs"))
        best=None
        for v in vals:
            pr=[(R[k][v],R[k][inc]) for k in keys if v in R[k] and inc in R[k]]
            if len(pr)<10: continue
            d=[a-b for a,b in pr]; nz=[x for x in d if abs(x)>1e-9]
            m=st.mean(d); sd=st.stdev(d) if len(d)>1 else 0
            t=m/(sd/math.sqrt(len(d))) if sd else float('nan')
            mo=st.mean([a for a,b in pr])
            if best is None or mo>best[1]: best=(v,mo)
            print("  %-8g %6d %11.1f %+9.2f %9s %8.0f%%"%(v,len(d),mo,m,
                  ('%+.2f'%t) if sd else 'IDENT',100*len(nz)/len(d)))
        # split-half evens/odds
        sh=[]
        for par in (0,1):
            kk=[k for k in keys if k[4]%2==par]
            b=max(vals,key=lambda v: st.mean([R[k][v] for k in kk if v in R[k]] or [0]))
            sh.append(b)
        print("  -> argmax %g   split-half evens %g / odds %g   %s"%(
            best[0],sh[0],sh[1],"AGREE" if sh[0]==sh[1] else "DISAGREE (noise)"))
