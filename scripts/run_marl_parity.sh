#!/usr/bin/env bash
# Retrain the learner on a PARITY split and evaluate it across all four benchmark conditions.
# Seed difficulty is monotone in the index, so the original sequential 1-96/97-144 split tested the
# learner on days 2.5x harder than the ones it trained on. Parity puts easy and hard days on both
# sides, which is what 2.5 of the paper says the protocol requires.
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
L=results/mapd_logs
export WWM_RETIRE_BAYS=1 MARLSPLIT=parity MARL_MODEL=results/marl_policy_parity.pt
ODD=$(seq -s, 1 2 143)
log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/marl_parity.log"; }
log "START train (even seeds)"
"$PY" scripts/marl_dispatch.py train > "$L/marl_parity_train.log" 2>&1
log "END   train rc=$?"
for cond in clean disturb; do
  if [ "$cond" = disturb ]; then D=1; else D=0; fi
  log "START eval_$cond"
  env BAYFLOOR=retired DISTURB=$D ARMS=marl REGIMES=wave,stream M5SEEDS="$ODD" NPROC=8 \
      MARL_MODEL=results/marl_policy_parity.pt OUT="results/mapd/marl_parity_$cond.csv" \
      "$PY" scripts/exp_m5_bench.py > "$L/marl_parity_eval_$cond.log" 2>&1
  log "END   eval_$cond rc=$?"
done
log "DONE"
