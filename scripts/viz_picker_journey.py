"""The picker journey: baseline -> commit paths -> value-rate a=3 -> a=5 -> 1:1 ratio -> free-picker
ceiling, all on the champion base, 120 day-list seeds (8x8 demand verified identical to 8x4).
Reads pj4_*.csv (8x4 arms) + pj8_*.csv (value-rate @ 8x8). Output: results/picker_journey.png"""
import csv, os, sys
import numpy as np
from math import comb
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_BASE="#b5b4ab"; C_STEP="#2a78d6"; C_BEST="#1baf7a"; C_RATIO="#4a3aa7"; C_CEIL="#eda100"
C_INK="#40403e"; C_MUT="#8a8a82"; C_GRID="#d6d5cd"


def load(prefix):
    rows=[]
    for off in (0,30,60,90):
        with open(f"results/{prefix}_{off}.csv") as fh: rows+=list(csv.DictReader(fh))
    return {int(r["seed"]):r for r in rows}


def paired(a,b):
    d=a-b; se=d.std(ddof=1)/np.sqrt(len(d)); w=int((d>0).sum()); l=int((d<0).sum()); m=w+l
    p=sum(comb(m,k) for k in range(min(w,l)+1))/2**(m-1) if m else 1.0
    return d.mean(),se,(d.mean()/se if se else 0),w,l,p


def main():
    p4,p8=load("pj4"),load("pj8")
    seeds=sorted(set(p4)&set(p8))
    def C(d,k): return np.array([float(d[s][k]) for s in seeds])
    base=C(p4,"urg8_on_time_value")
    arms=[("baseline\n(stupid pickers)", base, C_BASE),
          ("+ commit paths\n(\"make sure\")", C(p4,"pkcommit_on_time_value"), C_STEP),
          ("+ value-rate\nα=3 (before)", C(p4,"pkrate3_on_time_value"), C_STEP),
          ("+ value-rate\nα=5 (now)", C(p4,"pkrate_on_time_value"), C_BEST),
          ("+ 1:1 ratio\n(8 pickers)", C(p8,"pkrate_on_time_value"), C_RATIO),
          ("free pickers\n(ceiling)", C(p4,"urgfreepk_on_time_value"), C_CEIL)]
    print(f"n={len(seeds)} seeds")
    for nm,a,_ in arms:
        m,se,t,w,l,pp=paired(a,base)
        print(f"  {nm.replace(chr(10),' '):32} {a.mean():7.1f}   d vs baseline {m:+6.2f}  t {t:+5.2f}  {w}/{l}  p={pp:.3f}")

    fig,ax=plt.subplots(figsize=(11.4,5.8),dpi=115); fig.patch.set_facecolor("white")
    x=np.arange(len(arms)); vals=[a.mean() for _,a,_ in arms]; cols=[c for _,_,c in arms]
    ax.bar(x,vals,0.62,color=cols,edgecolor="white",lw=1.5,zorder=3)
    for xi,(nm,a,_) in zip(x,arms):
        ax.text(xi,a.mean()+0.5,f"{a.mean():.0f}",ha="center",color=C_INK,fontsize=10.5,fontweight="bold")
        if xi>0:
            m,se,t,w,l,pp=paired(a,base)
            sig="" if pp<0.05 else " n.s."
            ax.text(xi,base.mean()-3.2,f"{m:+.1f}{sig}",ha="center",color=C_MUT,fontsize=8.5,fontweight="bold")
    ax.axhline(base.mean(),color=C_GRID,ls=":",lw=1.3,zorder=1)
    lo=base.mean()-6; ax.set_ylim(lo,max(vals)+7)
    ax.set_xticks(x); ax.set_xticklabels([nm for nm,_,_ in arms],color=C_INK,fontsize=9)
    ax.set_ylabel("on-time value ($/day, 120 seeds)",color=C_MUT,fontsize=10)
    ax.set_title("The picker journey — and how much is still left (the ceiling)",color=C_INK,fontsize=13,loc="left",fontweight="bold")
    for s in ("top","right"): ax.spines[s].set_visible(False)
    for s in ("left","bottom"): ax.spines[s].set_color(C_GRID)
    ax.tick_params(colors=C_MUT,labelsize=8.5)
    fig.text(0.06,0.02,"deltas vs baseline below each bar. Path-commit ~0; value-rate is the real lever "
             "(α=5 > α=3); 1:1 ratio + free pickers = the headcount ceiling scoring can't reach.",
             color=C_MUT,fontsize=8.5)
    fig.subplots_adjust(bottom=0.18,top=0.9,left=0.08,right=0.97)
    fig.savefig("results/picker_journey.png",facecolor="white"); print("PNG: results/picker_journey.png")


if __name__=="__main__":
    main()
