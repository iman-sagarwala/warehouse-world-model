"""Knob response curves on the corrected world, one line per fleet.
With only 3 ratio cells a heatmap is not meaningful; curves show whether the RESPONSE SHAPE differs by
fleet, which is the ratio-dependence question the 3-cell coverage cannot otherwise answer."""
import csv, os, collections, statistics as st
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
INK="#171b20"; SUB="#5b6672"; GRID="#e3e7ea"
COL={"4x4":"#2f6f8f","8x6":"#c9821f","9x9":"#7b4f9d"}
M={"family":"DejaVu Sans Mono"}
R=collections.defaultdict(lambda: collections.defaultdict(list))
for f in ["results/knobs_realworld.csv","results/knobs_confirm.csv","results/knobs_ext.csv"]:
    if not os.path.exists(f): continue
    for r in csv.DictReader(open(f)):
        R[(r["knob"],r["regime"],"%sx%s"%(r["agvs"],r["pickers"]))][float(r["value"])].append(
            float(r["on_time_value"]))
KNOBS=["URG_W","SEQ_DEPTH","RATE_ALPHA","W_SYNC"]
SHIP={"URG_W":{"daylist":0,"stream":8},"SEQ_DEPTH":{"daylist":5,"stream":5},
      "RATE_ALPHA":{"daylist":5,"stream":5},"W_SYNC":{"daylist":.3,"stream":.3}}
f,axes=plt.subplots(2,4,figsize=(17,7.6),dpi=165)
f.patch.set_facecolor("#f6f7f8")
for i,regime in enumerate(["daylist","stream"]):
    for j,knob in enumerate(KNOBS):
        ax=axes[i][j]; ax.set_facecolor("#ffffff")
        any_data=False
        for fleet in ["4x4","8x6","9x9"]:
            d=R[(knob,regime,fleet)]
            if not d: continue
            vals=sorted(d); n0=len(d[vals[0]])
            xs=[v for v in vals if len(d[v])>=max(50,n0*0.4)]
            if len(xs)<2: continue
            base=st.mean(d[xs[0]])
            ys=[100*(st.mean(d[v])-base)/base for v in xs]
            ax.plot(xs,ys,marker="o",ms=4,lw=1.6,color=COL[fleet],label=fleet)
            any_data=True
        s=SHIP[knob][regime]
        ax.axvline(s,color="#a3302c",lw=1.1,ls="--",alpha=.8)
        ax.grid(True,color=GRID,lw=.7); ax.set_axisbelow(True)
        for sp in ax.spines.values(): sp.set_color(GRID)
        ax.tick_params(labelsize=8,colors=SUB)
        ax.set_title("%s · %s"%(knob,regime),fontsize=10.5,color=INK,**M)
        if j==0: ax.set_ylabel("% vs lowest value tested",fontsize=8.5,color=SUB,**M)
        if not any_data: ax.text(.5,.5,"no data yet",transform=ax.transAxes,ha="center",color=SUB,**M)
axes[0][0].legend(fontsize=8,frameon=False,title="fleet",title_fontsize=8)
f.suptitle("Knob response on the CORRECTED world — dashed red = shipped value · one line per AGVxPicker fleet",
           fontsize=11.5,color=INK,y=.98,**M)
f.tight_layout(rect=[0,0,1,.95])
f.savefig("results/diag_knob_curves.png",bbox_inches="tight",facecolor=f.get_facecolor())
print("ok")
