"""Two heatmaps over the AGV x picker grid.

FIG 1  results/grid_best_knobs.png   -- per-cell ARGMAX of every swept knob, all in one picture.
       Colour = best on-time value reachable in that cell (max over the swept values, per knob, then
       the champion arm as the floor). Text = the winning value of each knob for that ratio.
       EXPLORATORY ONLY: these are MARGINAL per-knob argmaxes (each sweep varies one knob with the
       others at default), and per-cell argmax is noise-driven when margins are small vs per-cell SE.

FIG 2  results/grid_champion.png     -- the CHAMPION's own surface at the frozen settings, with the
       argmax ratio outlined. This is what we actually ship, so the difference between the two figures
       is the price of using one global table instead of tuning per ratio.
"""
import csv, glob, os, sys
from collections import defaultdict
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

AGVS=[4,5,6,7,8,9]; PKS=[4,5,6,7,8,9]; REGIMES=["daylist","stream"]
MIN_SEEDS=120
FROZEN={"URG_W":{"daylist":0.0,"stream":8.0},"W_SYNC":{"daylist":0.3,"stream":0.3},
        "RATE_ALPHA":{"daylist":5.0,"stream":5.0},"SEQ_DEPTH":{"daylist":5.0,"stream":5.0}}
SHORT={"URG_W":"U","W_SYNC":"W","RATE_ALPHA":"R","SEQ_DEPTH":"S"}

d=defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
for f in glob.glob("results/knobsweep/*agv*pk_*.csv"):
    for r in csv.DictReader(open(f)):
        d[r["knob"]][r["regime"]][(int(r["agvs"]),int(r["pickers"]))][float(r["value"])].append(float(r["on_time_value"]))

KNOBS=[k for k in ["URG_W","W_SYNC","RATE_ALPHA","SEQ_DEPTH"] if k in d]

def champ_cell(rg,cell):
    """Champion on-time value: pooled over every sweep arm sitting at the frozen value."""
    vals=[]
    for k in KNOBS:
        fv=FROZEN[k][rg]
        got=d[k][rg].get(cell,{}).get(fv,[])
        if len(got)>=MIN_SEEDS: vals.extend(got)
    return float(np.mean(vals)) if vals else np.nan

def best_cell(rg,cell):
    """Best MARGINAL value in this cell (max over knobs of that knob's best arm)."""
    best=champ_cell(rg,cell); argm={}
    for k in KNOBS:
        arms={v:np.mean(x) for v,x in d[k][rg].get(cell,{}).items() if len(x)>=MIN_SEEDS}
        if not arms: continue
        bv=max(arms,key=arms.get); argm[k]=bv
        best=max(best,arms[bv]) if best==best else arms[bv]
    return best,argm

for figno,(title,fname) in enumerate([
        ("Best knob value per AGV x picker ratio  (marginal argmax — EXPLORATORY)","results/grid_best_knobs.png"),
        ("CHAMPION at the frozen table — on-time value per ratio","results/grid_champion.png")]):
    fig,axes=plt.subplots(1,2,figsize=(15,6.4))
    for ax,rg in zip(axes,REGIMES):
        M=np.full((len(AGVS),len(PKS)),np.nan); TXT={}
        for i,a in enumerate(AGVS):
            for j,p in enumerate(PKS):
                if figno==0:
                    b,argm=best_cell(rg,(a,p)); M[i,j]=b
                    TXT[(i,j)]="\n".join("%s%g"%(SHORT[k],argm[k]) for k in KNOBS if k in argm)
                else:
                    M[i,j]=champ_cell(rg,(a,p))
                    TXT[(i,j)]="%.0f"%M[i,j] if M[i,j]==M[i,j] else ""
        im=ax.imshow(M,cmap="viridis",aspect="auto")
        for (i,j),t in TXT.items():
            if t: ax.text(j,i,t,ha="center",va="center",color="w",fontsize=7.5 if figno==0 else 11,
                          fontweight="bold" if figno==1 else "normal")
        if figno==1 and np.isfinite(M).any():
            bi,bj=np.unravel_index(np.nanargmax(M),M.shape)
            ax.add_patch(Rectangle((bj-.5,bi-.5),1,1,fill=False,edgecolor="red",lw=3))
            ax.set_xlabel("pickers     (red = best ratio: %d AGV x %d pk)"%(AGVS[bi],PKS[bj]))
        else:
            ax.set_xlabel("pickers")
        ax.set_xticks(range(len(PKS))); ax.set_xticklabels(PKS)
        ax.set_yticks(range(len(AGVS))); ax.set_yticklabels(AGVS)
        ax.set_ylabel("AGVs"); ax.set_title(rg.upper())
        fig.colorbar(im,ax=ax,label="on-time value")
    sub=("U=URG_W  W=W_SYNC  R=RATE_ALPHA  S=SEQ_DEPTH   |   colour = best reachable on-time value"
         if figno==0 else
         "frozen: URG_W 0/8 · W_SYNC 0.3 · RATE_ALPHA 5 · SEQ_DEPTH 5   |   >=120 seeds per cell")
    fig.suptitle(title+"\n"+sub,fontsize=11)
    fig.tight_layout(rect=[0,0,1,0.90]); fig.savefig(fname,dpi=140); plt.close(fig)
    print("PNG:",fname)
