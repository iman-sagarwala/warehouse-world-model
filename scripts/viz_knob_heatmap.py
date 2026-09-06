"""Knob heatmaps: fleet x knob value, cell = % vs the shipped value. Within-regime only (the
cross-regime workload confound does not affect these, since every arm in a regime saw the same load)."""
import csv, os, collections, statistics as st
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
INK="#171b20"; SUB="#5b6672"; M={"family":"DejaVu Sans Mono"}
SRC=[("results/seqdepth_matched.csv","SEQ_DEPTH"),("results/knobs_realworld.csv",None),
     ("results/knobs_ext.csv",None),("results/knobs_confirm.csv",None)]
SHIP={"URG_W":{"daylist":0.0,"stream":8.0},"SEQ_DEPTH":{"daylist":5.0,"stream":5.0},
      "RATE_ALPHA":{"daylist":5.0,"stream":5.0},"W_SYNC":{"daylist":0.3,"stream":0.3}}
D=collections.defaultdict(list)
for f,forced in SRC:
    if not os.path.exists(f): continue
    for r in csv.DictReader(open(f)):
        knob=forced or r.get("knob")
        if not knob: continue
        D[(knob,r["regime"],"%sx%s"%(r["agvs"],r["pickers"]),float(r["value"]))].append(float(r["on_time_value"]))
panels=[(k,rg) for k in ["SEQ_DEPTH","URG_W","RATE_ALPHA","W_SYNC"] for rg in ["daylist","stream"]]
fleets=["4x4","8x6","9x9"]
f,axes=plt.subplots(2,4,figsize=(18,6.6),dpi=165); f.patch.set_facecolor("#f6f7f8")
for idx,(knob,regime) in enumerate(panels):
    ax=axes[idx%2][idx//2]
    vals=sorted({v for (k,rg,fl,v) in D if k==knob and rg==regime})
    vals=[v for v in vals if sum(len(D[(knob,regime,fl,v)]) for fl in fleets)>=200]
    if not vals: ax.axis("off"); ax.set_title("%s · %s\nno data"%(knob,regime),fontsize=9,color=SUB,**M); continue
    ship=SHIP[knob][regime]; ship=ship if ship in vals else vals[0]
    Mx=np.full((len(fleets),len(vals)),np.nan)
    for i,fl in enumerate(fleets):
        base=st.mean(D[(knob,regime,fl,ship)]) if D[(knob,regime,fl,ship)] else None
        for j,v in enumerate(vals):
            cur=D[(knob,regime,fl,v)]
            if cur and base: Mx[i,j]=100*(st.mean(cur)-base)/base
    lim=max(1.0,np.nanmax(np.abs(Mx)))
    im=ax.imshow(Mx,cmap="RdYlGn",vmin=-lim,vmax=lim,aspect="auto")
    for i in range(len(fleets)):
        for j in range(len(vals)):
            if np.isfinite(Mx[i,j]):
                ax.text(j,i,"%+.1f"%Mx[i,j],ha="center",va="center",fontsize=8.5,
                        color="#111" if abs(Mx[i,j])<lim*.6 else "#fff",**M)
    ax.set_xticks(range(len(vals))); ax.set_xticklabels([("%g"%v) for v in vals],fontsize=8.5)
    ax.set_yticks(range(len(fleets))); ax.set_yticklabels(fleets,fontsize=8.5)
    ax.set_title("%s · %s   (vs shipped %g)"%(knob,regime,ship),fontsize=10,color=INK,**M)
    for j,v in enumerate(vals):
        if v==ship: ax.add_patch(plt.Rectangle((j-.5,-.5),1,len(fleets),fill=False,ec="#171b20",lw=2))
f.suptitle("Knob response · % vs the shipped value · rows = AGVxPicker fleet · black box = shipped",
           fontsize=12,color=INK,y=1.02,**M)
f.tight_layout()
f.savefig("results/diag_knob_heatmap.png",bbox_inches="tight",facecolor=f.get_facecolor())
print("ok")
