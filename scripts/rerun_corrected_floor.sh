#!/usr/bin/env bash
# Corrected-floor rerun queue (2026-09-20).
#
# Re-measures every number the paper cites on the corrected world: charger-bay pods retired from the
# grid AND the demand schedule (WWM_RETIRE_BAYS=1), and the three foresight/drift results that were
# never on the corrected world at all ported onto it. Runs after the headline benchmark finishes, so
# the two never compete for cores.
#
# Outputs go to results/retired/ wherever a script takes OUT. The scripts that write to fixed paths
# have their legacy output copied to results/legacy_floor/ first. Logs: results/rerun_logs/.
#
#   bash scripts/rerun_corrected_floor.sh
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/retired
L=results/rerun_logs
mkdir -p "$R" results/legacy_floor "$L"
export WWM_RETIRE_BAYS=1
S144=$(seq -s, 1 144)

log() { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
step() {
  local name=$1; shift
  # restartable: a step that already finished cleanly is not run again
  if grep -q "END   $name rc=0" "$L/queue.log" 2>/dev/null; then
    log "SKIP  $name (already done)"; return
  fi
  log "START $name"
  "$@" > "$L/$name.log" 2>&1
  log "END   $name rc=$?"
}
bench() {   # bench <name> <extra env...>  -- one benchmark configuration, resumable
  local name=$1; shift
  step "$name" env "$@" BAYFLOOR=retired REGIMES=stream NPROC=8 OUT="$R/$name.csv" \
       "$PY" scripts/exp_m5_bench.py
}

log "queue waiting for the headline benchmark"
until grep -q ALL_DONE results/m5_bench_retired.log 2>/dev/null; do sleep 300; done
log "headline benchmark finished; queue starting"

# fixed-path outputs: keep the legacy version before it is overwritten
for f in m5_belief_curves.png marl_policy.pt; do
  [ -f "results/$f" ] && cp -n "results/$f" "results/legacy_floor/$f"
done

# --- A. the scorecard and the numbers the text quotes --------------------------------------------
step safety   env OUT=$R/m5_safety.csv        "$PY" scripts/exp_m5_safety.py
step brier                                      "$PY" scripts/exp_m5_brier.py
step oracle   env OUT=$R/oracle_combined.csv   "$PY" scripts/exp_oracle_combined.py
step ceiling  env OUT=$R/tuner_ceiling.csv     "$PY" scripts/exp_tuner_ceiling.py

# --- B. the abstract's negative result: perfect demand foresight, on the shipped system too -------
bench foresight_w999 FORESIGHT=999 ARMS=champ,mpc M5SEEDS=$S144

# --- C. the other negative results and Figure 9 ---------------------------------------------------
step headroom                                   "$PY" scripts/exp_m3c_headroom.py
step chargefs                                   "$PY" scripts/exp_charge_foresight.py
step pace     env OUT=$R/m4_pace_data.csv      "$PY" scripts/exp_m4_pace.py
step cadence                                    "$PY" scripts/exp_mpc_cadence.py

# --- D. the learner, retrained on the corrected world, then evaluated -----------------------------
step marltrain                                  "$PY" scripts/marl_dispatch.py train
step marlvs   env OUT=$R/marl_vs_shipped.csv   "$PY" scripts/exp_marl_vs_shipped.py

# --- E. the foresight window sweep (Figure 8, left panel) -----------------------------------------
for W in 10 25 50 100; do
  bench foresight_w$W FORESIGHT=$W ARMS=champ,mpc M5SEEDS=$S144
done

# --- F. drifting hotspots, calibrated from the Instacart sample -----------------------------------
for W in 0 25 999; do
  bench drift_w$W WWM_DEMAND_DRIFT=1 FORESIGHT=$W ARMS=champ,mpc M5SEEDS=$S144
done

# --- G. the 46-world tuner campaign, driven until it has nothing left to do -----------------------
log "START campaign"
fails=0
for i in $(seq 1 600); do
  out=$(CAMPAIGN_CSV=$R/mpc_campaign.csv CAMPAIGN_STATUS=$R/mpc_status.md \
        "$PY" scripts/mpc_campaign_step.py 2>>"$L/campaign.err")
  rc=$?
  echo "$out" >> "$L/campaign.log"
  # a failing config would otherwise be retried until the loop cap: stop on three in a row
  if [ $rc -ne 0 ]; then
    fails=$((fails + 1))
    [ $fails -ge 3 ] && { log "campaign: 3 consecutive failures, stopping"; break; }
    continue
  fi
  fails=0
  echo "$out" | grep -q "^run " || break
done
log "END   campaign after $i steps"

log "QUEUE DONE"
