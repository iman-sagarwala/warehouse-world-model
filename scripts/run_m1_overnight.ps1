# M1 close-out chain: wait for part A (deferred knobs) to finish, then run part B (scale study).
# Part A and the oracle are already running when this starts; this only chains B behind A so the
# whole close-out completes unattended.
Set-Location "C:/Users/isaga/Documents/warehouse_world_model"
$env:PYTHONIOENCODING = "utf-8"

# --- wait for part A ---
while (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*exp_m1_close*' }) {
    Start-Sleep -Seconds 60
}
"[chain] part A finished $(Get-Date -Format 'MM-dd HH:mm')" | Out-File -Append results/_chain.log

# --- part B: scale / generalisation ---
$env:SEEDS = "120"; $env:NPROC = "8"; $env:PART = "b"; $env:OUT = "results/m1_close_b.csv"
& ".\.venv\Scripts\python.exe" -u scripts/exp_m1_close.py *>> results/_m1b.log
"[chain] part B finished $(Get-Date -Format 'MM-dd HH:mm')" | Out-File -Append results/_chain.log

# --- if the oracle died early, restart it (resume is not supported, so only if no rows exist) ---
if (-not (Test-Path results/_oracle_v2.log) -or
    -not (Select-String -Path results/_oracle_v2.log -Pattern "MEAN GAP" -Quiet)) {
    if (-not (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*oracle_assign*' })) {
        "[chain] oracle not finished and not running -> restarting" | Out-File -Append results/_chain.log
        $env:SEEDS = "12"; $env:M = "80"; $env:CHAMP = "1"; $env:DAYLIST = "1"
        $env:ENVID = "wwm_sim-large-8agvs-6pickers-globalobs-v1"
        & ".\.venv\Scripts\python.exe" -u scripts/oracle_assign.py *>> results/_oracle_v2.log
    }
}
"[chain] ALL DONE $(Get-Date -Format 'MM-dd HH:mm')" | Out-File -Append results/_chain.log
