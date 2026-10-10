#!/usr/bin/env bash
# Token Passing + Hungarian baselines on the corrected floor, paired with the headline benchmark.
# Same seeds, same regimes, same disturbance conditions as results/m5_bench_retired*.csv, so every
# arm is comparable to champ/mpc/fifo/rush seed-for-seed.
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/mapd
L=results/mapd_logs
mkdir -p "$R" "$L"
export WWM_RETIRE_BAYS=1
S144=$(seq -s, 1 144)
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
step() {
  local name=$1; shift
  if grep -q "END   $name rc=0" "$L/queue.log" 2>/dev/null; then log "SKIP  $name"; return; fi
  log "START $name"; "$@" > "$L/$name.log" 2>&1; log "END   $name rc=$?"
}
step clean   env BAYFLOOR=retired ARMS=tp,hung,hungv REGIMES=wave,stream M5SEEDS="$S144" \
      NPROC=8 OUT="$R/mapd_clean.csv"   "$PY" scripts/exp_m5_bench.py
step disturb env BAYFLOOR=retired DISTURB=1 ARMS=tp,hung,hungv REGIMES=wave,stream M5SEEDS="$S144" \
      NPROC=8 OUT="$R/mapd_disturb.csv" "$PY" scripts/exp_m5_bench.py
log "QUEUE DONE"
