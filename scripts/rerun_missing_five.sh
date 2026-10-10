#!/usr/bin/env bash
# The five measurements the paper still quotes from the pre-correction world (2026-10-09).
#
# Each one is cited in the draft but was never re-measured after the bay fix, so each is either a
# number from a world the paper says it excludes, or (for the rollout ablation) a number no script
# regenerates at all. All five run with WWM_RETIRE_BAYS=1, so build() retires the charger-bay pods
# from BOTH the grid and the demand schedule -- the corrected floor the headline now sits on.
#
# Ordered cheapest-first so the short ones land early if the budget runs out.
#   bash scripts/rerun_missing_five.sh
set -u
cd "$(dirname "$0")/.."
PY=./.venv/Scripts/python.exe
R=results/missing
L=results/missing_logs
mkdir -p "$R" "$L"
export WWM_RETIRE_BAYS=1
S144=$(seq -s, 1 144)
S48=$(seq -s, 1 48)

log()  { echo "[$(date '+%m-%d %H:%M')] $*" >> "$L/queue.log"; }
step() {
  local name=$1; shift
  if grep -q "END   $name rc=0" "$L/queue.log" 2>/dev/null; then log "SKIP  $name"; return; fi
  log "START $name"
  "$@" > "$L/$name.log" 2>&1
  log "END   $name rc=$?"
}

# 1. phantom hard blocks + decision latency (3.5 and the 1.3 ms claim in 3.1)
step gaps     env PGSEEDS="$S48" NPROC=8 "$PY" scripts/exp_proposal_gaps.py

# 2. the reliability diagram (3.5: "98.0% stated, 97.9% observed")
step calib    env NPROC=8 "$PY" scripts/exp_m2_calibration.py

# 3. sensing ceiling + clairvoyant VoPI (3.5: "99.8% of ceiling, 38% -> 83%")
step m2belief env SEEDLIST="$S48" NPROC=8 "$PY" scripts/exp_m2_belief.py

# 4. the disturbance-sensing oracle at full power. The 48-seed run reversed a published null at
#    t=+2.23, which is too thin to carry an abstract claim; 144 seeds settles it, and the same run
#    re-tests the demand channel and their interaction.
step oracle144 env ORSEEDS="$S144" NPROC=8 OUT="$R/oracle_combined_144.csv" \
      "$PY" scripts/exp_oracle_combined.py

# 5. the stage-6 ablation: the champion funnel with the rollout sequencer switched off. champ only,
#    because SEQ_DEPTH is tuner parameter 4 and the mpc arm would tune it straight back.
step ablate   env BAYFLOOR=retired SEQDEPTH=0 ARMS=champ REGIMES=wave,stream M5SEEDS="$S144" \
      NPROC=8 OUT="$R/ablate_rollout.csv" "$PY" scripts/exp_m5_bench.py

log "QUEUE DONE"
