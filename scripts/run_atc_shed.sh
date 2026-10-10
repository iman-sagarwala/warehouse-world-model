#!/usr/bin/env bash
# ATC's index with rush's hard demotion of projected-late tasks. Sweep K on the even seeds, then
# run the best value per regime on the full grid -- same protocol as the plain ATC arms, so the
# three-way comparison (atc / atcs / rush) isolates the tiering from the index.
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/atc; L=results/atc_logs
export WWM_RETIRE_BAYS=1
EVEN=$(seq -s, 2 2 144)
KARMS=$(for k in 0p5 1p0 2p0 3p0 5p0 8p0; do printf "atcs_k%s,atcxs_k%s," "$k" "$k"; done | sed 's/,$//')
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
if ! grep -q "END   shedsweep rc=0" "$L/queue.log" 2>/dev/null; then
  log "START shedsweep"
  env BAYFLOOR=retired ARMS="$KARMS" REGIMES=wave,stream M5SEEDS="$EVEN" NPROC=8 \
      OUT="$R/atc_shed_sweep.csv" "$PY" scripts/exp_m5_bench.py > "$L/shedsweep.log" 2>&1
  log "END   shedsweep rc=$?"
fi
log "SHED SWEEP DONE"
