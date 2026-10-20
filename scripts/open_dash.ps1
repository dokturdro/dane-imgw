# One-file launcher for the dashboard, opened from the browser bookmark  imgw://dash
#   powershell -File scripts\open_dash.ps1 -Register   once: make imgw:// links run this script
#   powershell -File scripts\open_dash.ps1             start `imgw dash` hidden (if needed), open the browser,
#                                                      then refresh the data: synop -> live -> sync
#   powershell -File scripts\open_dash.ps1 -Stop       stop the background dashboard
# Unregister with:  Remove-Item -Recurse HKCU:\Software\Classes\imgw
param([switch]$Register, [switch]$Stop, [int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$url = "http://localhost:$Port"
$logDir = Join-Path $project 'data\logs'

if ($Register) {
    $key = 'HKCU:\Software\Classes\imgw'
    New-Item -Force $key | Out-Null
    Set-ItemProperty $key '(default)' 'URL:IMGW dashboard'
    Set-ItemProperty $key 'URL Protocol' ''
    New-Item -Force "$key\shell\open\command" | Out-Null
    # the link's own text (%1) is deliberately not passed to the script
    Set-ItemProperty "$key\shell\open\command" '(default)' `
        "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Write-Host "registered imgw:// -> $PSCommandPath"
    Write-Host "Now bookmark this URL in your browser:  imgw://dash"
    Write-Host "(the browser asks once before opening it; tick 'always allow' to skip that next time)"
    exit
}

function Get-Listener {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
}

if ($Stop) {
    $l = Get-Listener
    if ($l) { Stop-Process -Id $l.OwningProcess -Force; Write-Host "stopped dashboard on port $Port" }
    else { Write-Host "no dashboard running on port $Port" }
    exit
}

New-Item -ItemType Directory -Force $logDir | Out-Null
$uv = (Get-Command uv).Source

if (-not (Get-Listener)) {
    Start-Process -FilePath $uv -WindowStyle Hidden -WorkingDirectory $project `
        -ArgumentList 'run', '--project', "`"$project`"", 'imgw', 'dash', '--no-open', '--port', $Port `
        -RedirectStandardOutput (Join-Path $logDir 'dash.log') -RedirectStandardError (Join-Path $logDir 'dash.err.log')
    # wait up to 60 s for Streamlit to start listening
    $deadline = (Get-Date).AddSeconds(60)
    while (-not (Get-Listener) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
}

Start-Process $url

# Refresh after the page is up. The dashboard reads with short read-only connections, so it keeps
# working meanwhile and picks up the new data on its next rerun. A mutex skips the refresh when
# another launch is already running one.
$mutex = New-Object System.Threading.Mutex($false, 'Local\imgw-launch-refresh')
if (-not $mutex.WaitOne(0)) { exit }
try {
    $log = Join-Path $logDir 'launch_refresh.log'
    foreach ($cmd in 'synop', 'live', 'sync') {
        Add-Content $log "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') imgw $cmd"
        # cmd.exe does the redirect so uv's stderr (its logging) lands in the log as plain text
        & cmd.exe /c "`"$uv`" run --project `"$project`" imgw $cmd >> `"$log`" 2>&1"
    }
} finally {
    $mutex.ReleaseMutex()
}
