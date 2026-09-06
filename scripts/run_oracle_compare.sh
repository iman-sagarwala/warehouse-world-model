#!/bin/sh
# Assignment ceiling under LEGACY vs CORRECTED task/deadline layout, same seeds, same M.
cd "C:/Users/isaga/Documents/warehouse_world_model"
export PYTHONIOENCODING=utf-8 SEEDS=12 M=80 CHAMP=1 DAYLIST=1
export ENVID=wwm_sim-large-8agvs-6pickers-globalobs-v1
WINDOW=0 ./.venv/Scripts/python.exe -u scripts/oracle_assign.py > results/_oracle_legacy.log 2>&1
WINDOW=1 UTIL=0.80 ./.venv/Scripts/python.exe -u scripts/oracle_assign.py > results/_oracle_fixed.log 2>&1
echo ORACLE_COMPARE_DONE
