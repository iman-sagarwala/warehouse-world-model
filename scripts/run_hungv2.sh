#!/usr/bin/env bash
# The unhandicapped Hungarian-on-value arm. Chains behind run_mapd_baselines.sh so the two never
# compete for cores, then regenerates the report with every arm present.
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/mapd
L=results/mapd_logs
export WWM_RETIRE_BAYS=1
S144=$(seq -s, 1 144)
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
until grep -q "QUEUE DONE" "$L/queue.log" 2>/dev/null; do sleep 20; done
log "START hungv2_clean"
env BAYFLOOR=retired ARMS=hungv2 REGIMES=wave,stream M5SEEDS="$S144" NPROC=8 \
    OUT="$R/mapd_clean.csv" "$PY" scripts/exp_m5_bench.py > "$L/hungv2_clean.log" 2>&1
log "END   hungv2_clean rc=$?"
log "START hungv2_disturb"
env BAYFLOOR=retired DISTURB=1 ARMS=hungv2 REGIMES=wave,stream M5SEEDS="$S144" NPROC=8 \
    OUT="$R/mapd_disturb.csv" "$PY" scripts/exp_m5_bench.py > "$L/hungv2_disturb.log" 2>&1
log "END   hungv2_disturb rc=$?"
"$PY" scripts/report_mapd.py > "$L/report.log" 2>&1
log "REPORT DONE"
