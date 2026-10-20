# Registers three Windows scheduled tasks for the current user:
#   imgw-live   every 10 minutes   -> uv run imgw live    (telemetry needs 10-min polling for full daily sums)
#   imgw-synop  hourly at :25      -> uv run imgw synop   (SYNOP messages arrive ~10-20 min after the hour)
#   imgw-sync   daily at 09:00     -> uv run imgw sync    (IMGW publishes monthly files mid-month)
# Remove with:  schtasks /Delete /TN imgw-live /F ; schtasks /Delete /TN imgw-synop /F ; schtasks /Delete /TN imgw-sync /F
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$uv = (Get-Command uv).Source
$logDir = Join-Path $project 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null

function Register-ImgwTask($name, $cmd, $schedule) {
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' `
        -Argument "/c `"`"$uv`" run --project `"$project`" imgw $cmd >> `"$logDir\$name.log`" 2>&1`"" `
        -WorkingDirectory $project
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 6)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $schedule -Settings $settings -Force | Out-Null
    Write-Host "registered $name"
}

$every10 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 10)
Register-ImgwTask 'imgw-live' 'live' $every10
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(25) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ImgwTask 'imgw-synop' 'synop' $hourly
Register-ImgwTask 'imgw-sync' 'sync' (New-ScheduledTaskTrigger -Daily -At '09:00')
