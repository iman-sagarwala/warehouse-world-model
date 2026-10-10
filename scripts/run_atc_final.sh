#!/usr/bin/env bash
# ATC on the full grid, with K chosen PER REGIME from the even-seed sweep -- the most generous
# selection available to the baseline:
#   atc   wave K=1.0   stream K=5.0
#   atcx  wave K=2.0   stream K=8.0
# K was selected on the even seeds and the comparison is reported on all 144, so the selection
# overlaps the evaluation. That overlap favours the baseline.
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/atc; L=results/atc_logs
export WWM_RETIRE_BAYS=1
S=$(seq -s, 1 144)
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
run() {   # run <name> <disturb 0|1> <regime> <arms>
  local n=$1 d=$2 g=$3 a=$4
  if grep -q "END   $n rc=0" "$L/queue.log" 2>/dev/null; then log "SKIP  $n"; return; fi
  log "START $n"
  env BAYFLOOR=retired DISTURB=$d ARMS="$a" REGIMES="$g" M5SEEDS="$S" NPROC=8 \
      OUT="$R/atc_final_$( [ "$d" = 1 ] && echo disturb || echo clean ).csv" \
      "$PY" scripts/exp_m5_bench.py > "$L/$n.log" 2>&1
  log "END   $n rc=$?"
}
run final_clean_wave     0 wave   atc_k1p0,atcx_k2p0
run final_clean_stream   0 stream atc_k5p0,atcx_k8p0
run final_dist_wave      1 wave   atc_k1p0,atcx_k2p0
run final_dist_stream    1 stream atc_k5p0,atcx_k8p0
log "FINAL DONE"
