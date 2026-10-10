#!/usr/bin/env bash
# MAPF methods on the SHIPPED map, environment held fixed, density swept around the operating point.
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
L=results/mapf_logs
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
log "START ownmap"
env KS=4,8,14,20,28,40 NINST=25 OUT=results/mapf/mapf_ownmap.csv \
    "$PY" scripts/exp_mapf_ownmap.py > "$L/ownmap.log" 2>&1
log "END   ownmap rc=$?"
