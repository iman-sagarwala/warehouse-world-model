#!/usr/bin/env bash
# Multi-agent MAPF benchmark, standard MovingAI instances, 25 scenarios per (map, k).
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
L=results/mapf_logs; mkdir -p "$L" results/mapf
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
step() {
  local n=$1; shift
  if grep -q "END   $n rc=0" "$L/queue.log" 2>/dev/null; then log "SKIP  $n"; return; fi
  log "START $n"; "$@" > "$L/$n.log" 2>&1; log "END   $n rc=$?"
}
step warehouse env MAPS=warehouse-10-20-10-2-1 KS=10,20,40,60,80,100 NSCEN=25 \
     OUT=results/mapf/mapf_multi_warehouse.csv "$PY" scripts/exp_mapf_multi.py
step empty     env MAPS=empty-32-32 KS=10,20,40,60,80,100 NSCEN=25 \
     OUT=results/mapf/mapf_multi_empty.csv "$PY" scripts/exp_mapf_multi.py
step random    env MAPS=random-32-32-20 KS=10,20,40,60,80,100 NSCEN=25 \
     OUT=results/mapf/mapf_multi_random.csv "$PY" scripts/exp_mapf_multi.py
log "MAPF MULTI DONE"
