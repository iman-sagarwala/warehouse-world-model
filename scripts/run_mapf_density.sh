#!/usr/bin/env bash
# DENSITY-MATCHED MAPF. The shipped world is 25x16 = 400 cells with 172 pod cells, so 228
# traversable cells carry 14 agents: 6.14% agent density. Matching that density rather than the
# agent COUNT is the comparison that means something -- the earlier sweep ran the warehouse map at
# 0.2-1.8% density, up to thirty times sparser than the system actually operates.
#   warehouse-10-20-10-2-1  5699 free -> 350 agents   (scen has 451 rows)
#   empty-32-32             1024 free ->  63 agents
#   random-32-32-20          819 free ->  50 agents   (scen has only 101 rows)
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
L=results/mapf_logs
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
step() {
  local n=$1; shift
  if grep -q "END   $n rc=0" "$L/queue.log" 2>/dev/null; then log "SKIP  $n"; return; fi
  log "START $n"; "$@" > "$L/$n.log" 2>&1; log "END   $n rc=$?"
}
# small maps first: cheap, and they bracket the operating density directly
step dens_random env MAPS=random-32-32-20 KS=50 NSCEN=25 CAP_MULT=10 CAP_FLOOR=1000 \
     OUT=results/mapf/dens_random.csv "$PY" scripts/exp_mapf_multi.py
step dens_empty  env MAPS=empty-32-32 KS=63 NSCEN=25 CAP_MULT=10 CAP_FLOOR=1000 \
     OUT=results/mapf/dens_empty.csv "$PY" scripts/exp_mapf_multi.py
step dens_wh     env MAPS=warehouse-10-20-10-2-1 KS=200,350 NSCEN=25 CAP_MULT=10 CAP_FLOOR=1000 \
     OUT=results/mapf/dens_warehouse.csv "$PY" scripts/exp_mapf_multi.py
log "DENSITY MATCHED DONE"
