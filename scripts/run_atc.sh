#!/usr/bin/env bash
# ATC dispatching: sweep the look-ahead parameter K, then run the best value on the full grid.
# K is selected on the EVEN seeds and the comparison is reported on all 144, so the selection
# overlaps the evaluation. That overlap favours the BASELINE, which is the conservative direction
# for a claim of the form "the planner still beats it".
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/atc; L=results/atc_logs
mkdir -p "$R" "$L"
export WWM_RETIRE_BAYS=1
EVEN=$(seq -s, 2 2 144)
S144=$(seq -s, 1 144)
KARMS=$(for k in 0p5 1p0 2p0 3p0 5p0 8p0; do printf "atc_k%s,atcx_k%s," "$k" "$k"; done | sed 's/,$//')
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
step() {
  local n=$1; shift
  if grep -q "END   $n rc=0" "$L/queue.log" 2>/dev/null; then log "SKIP  $n"; return; fi
  log "START $n"; "$@" > "$L/$n.log" 2>&1; log "END   $n rc=$?"
}
step sweep env BAYFLOOR=retired ARMS="$KARMS" REGIMES=wave,stream M5SEEDS="$EVEN" NPROC=8 \
     OUT="$R/atc_sweep.csv" "$PY" scripts/exp_m5_bench.py
log "SWEEP DONE"
