$ErrorActionPreference = "Stop"

# 1) Stop the current non-interactive API process (and its launcher parent) to free :8091
$c = Get-NetTCPConnection -LocalPort 8091 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c) {
    $w = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $c.OwningProcess) -ErrorAction SilentlyContinue
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    if ($w) { Stop-Process -Id $w.ParentProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# 2) Register a scheduled task that runs the API in the interactive console session at logon
$action = New-ScheduledTaskAction -Execute "C:\SentinelDesktop\buildenv\Scripts\python.exe" `
    -Argument "main.py --api --port 8091" -WorkingDirectory "C:\SentinelDesktop"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "Administrator" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "SentinelDesktopAPI" -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "TASK_REGISTERED"

# 3) Start it now (Administrator is at the console, so this lands in the interactive session)
Start-ScheduledTask -TaskName "SentinelDesktopAPI"
Start-Sleep -Seconds 10

# 4) Report listener + which session it landed in (1 = interactive console = desktop access)
$c2 = Get-NetTCPConnection -LocalPort 8091 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c2) {
    $sid = (Get-Process -Id $c2.OwningProcess -ErrorAction SilentlyContinue).SessionId
    Write-Output ("LISTENING pid=" + $c2.OwningProcess + " sessionId=" + $sid)
} else {
    Write-Output "NOT LISTENING"
}
