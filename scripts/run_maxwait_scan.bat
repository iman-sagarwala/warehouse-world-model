@echo off
rem One-time scheduled max-wait scan (full champion stack, 144 seeds).
rem Scheduled via Windows Task Scheduler; writes results\maxwait_champion.txt
rem and a timestamped log so the outcome survives the run.
cd /d C:\Users\isaga\Documents\warehouse_world_model
.venv\Scripts\python.exe scripts\scan_maxwait_champion.py > results\maxwait_champion.log 2>&1
