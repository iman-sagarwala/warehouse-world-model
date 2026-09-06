"""Two questions for the morning:
 Q1 IS VALUE PER EPISODE PROPORTIONAL, old clock vs new? If the new demand model changes the achievable
    scale, results are not comparable and everything needs restating on the new basis.
 Q2 DOES URG_W = 8 SURVIVE? It is the only behavioural rule M1 produced and it was tuned under the
    mis-scaled sinusoid.
Split-half is EVENS vs ODDS (seeds tile the day; 0-53 vs 54-107 would be two halves of the DAY)."""
import csv, collections, statistics as st, math
R=collections.defaultdict(dict)
for r in csv.DictReader(open('results/urgw_newclock.csv')):
    R[(r['agvs'],r['pickers'],int(r['seed']))][(r['clock'],float(r['urg_w']))]=float(r['on_time_value'])
UW=[0.0,4.0,8.0,12.0]

print("="*74); print("Q1  VALUE PER EPISODE — old clock vs new clock (at the shipped URG_W=8)"); print("="*74)
old=[v[('old',8.0)] for v in R.values() if ('old',8.0) in v]
new=[v[('new',8.0)] for v in R.values() if ('new',8.0) in v]
if old and new:
    mo,mn=st.mean(old),st.mean(new)
    print("   old clock  mean %7.1f   n=%d"%(mo,len(old)))
    print("   new clock  mean %7.1f   n=%d"%(mn,len(new)))
    print("   RATIO new/old = %.3f   (1.00 = perfectly proportional)"%(mn/mo if mo else 0))
    paired=[(v[('new',8.0)],v[('old',8.0)]) for v in R.values() if ('new',8.0) in v and ('old',8.0) in v]
    d=[a-b for a,b in paired]; sd=st.stdev(d) if len(d)>1 else 0
    t=st.mean(d)/(sd/math.sqrt(len(d))) if sd else 0
    print("   paired diff %+.2f  t=%+.2f  n=%d"%(st.mean(d),t,len(d)))

for clock in ('old','new'):
    print(); print("="*74); print("Q2  URG_W sweep — %s clock  (stream, paired vs URG_W=8)"%clock.upper()); print("="*74)
    print("   %-8s %6s %11s %9s %10s"%('URG_W','n','vs 8','t','mean otv'))
    for u in UW:
        pr=[(v[(clock,u)],v[(clock,8.0)]) for v in R.values() if (clock,u) in v and (clock,8.0) in v]
        if len(pr)<5: continue
        dd=[a-b for a,b in pr]; m=st.mean(dd); sd=st.stdev(dd) if len(dd)>1 else 0
        t=m/(sd/math.sqrt(len(dd))) if sd else float('nan')
        print("   %-8g %6d %+11.2f %9s %10.1f"%(u,len(dd),m,('%+.2f'%t) if sd else 'IDENTICAL',
                                                st.mean([a for a,b in pr])))
    best=max(UW,key=lambda u: st.mean([v[(clock,u)] for v in R.values() if (clock,u) in v] or [0]))
    print("   -> argmax URG_W = %g"%best)
    print("   SPLIT-HALF (evens vs odds, NOT 0-53/54-107):")
    for lab,par in (('evens',0),('odds',1)):
        b=max(UW,key=lambda u: st.mean([v[(clock,u)] for k,v in R.items() if k[2]%2==par and (clock,u) in v] or [0]))
        print("      %-6s argmax URG_W = %g"%(lab,b))
