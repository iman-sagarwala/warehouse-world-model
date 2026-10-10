#!/usr/bin/env bash
# The shedding hybrids on the full grid, best K per regime from the even-seed sweep:
#   atcs   wave K=5.0   stream K=1.0
#   atcxs  wave K=8.0   stream K=1.0
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/atc; L=results/atc_logs
export WWM_RETIRE_BAYS=1
S=$(seq -s, 1 144)
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
run() {
  local n=$1 d=$2 g=$3 a=$4
  if grep -q "END   $n rc=0" "$L/queue.log" 2>/dev/null; then log "SKIP  $n"; return; fi
  log "START $n"
  env BAYFLOOR=retired DISTURB=$d ARMS="$a" REGIMES="$g" M5SEEDS="$S" NPROC=8 \
      OUT="$R/atc_shed_final_$( [ "$d" = 1 ] && echo disturb || echo clean ).csv" \
      "$PY" scripts/exp_m5_bench.py > "$L/$n.log" 2>&1
  log "END   $n rc=$?"
}
run shed_clean_wave   0 wave   atcs_k5p0,atcxs_k8p0
run shed_clean_stream 0 stream atcs_k1p0,atcxs_k1p0
run shed_dist_wave    1 wave   atcs_k5p0,atcxs_k8p0
run shed_dist_stream  1 stream atcs_k1p0,atcxs_k1p0
log "SHED FINAL DONE"
