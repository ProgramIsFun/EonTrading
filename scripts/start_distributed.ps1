# Start/stop all 7 distributed components outside Docker (Windows).
# Usage:
#   .\scripts\start_distributed.ps1 start          # start all processes
#   .\scripts\start_distributed.ps1 stop           # kill all processes
#   .\scripts\start_distributed.ps1 status         # show running processes
#   .\scripts\start_distributed.ps1 restart        # stop + start

param([string]$Command = "start")

$ScriptDir = Split-Path -LiteralPath $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$PidDir = "$ProjectRoot\run\.pids"
$LogDir = "$ProjectRoot\logs"

$Components = @(
    @{Name="watcher"; Module="src.live.runners.run_watcher"}
    @{Name="analyzer"; Module="src.live.runners.run_analyzer"}
    @{Name="trader"; Module="src.live.runners.run_trader"}
    @{Name="executor"; Module="src.live.runners.run_executor"}
    @{Name="monitor"; Module="src.live.runners.run_monitor"}
    @{Name="order_tracker"; Module="src.live.runners.run_order_tracker"}
)

# Load .env if present
$EnvFile = "$ProjectRoot\.env"
if (Test-Path -LiteralPath $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $k = $Matches[1].Trim()
            $v = $Matches[2].Trim()
            # Strip surrounding quotes
            if ($v.StartsWith('"') -and $v.EndsWith('"')) { $v = $v.Substring(1, $v.Length - 2) }
            if ($v -like '*$*') { $v = $ExecutionContext.InvokeCommand.ExpandString($v) }
            Set-Item -Path "Env:$k" -Value $v
        }
    }
}

$null = New-Item -ItemType Directory -Path $PidDir -Force
$null = New-Item -ItemType Directory -Path $LogDir -Force

function Get-PidFile($name) { "$PidDir\$name.pid" }
function Get-LogFile($name) { "$LogDir\$name.log" }

function Start-Component($name, $module) {
    $pidFile = Get-PidFile $name
    $logFile = Get-LogFile $name
    if (Test-Path $pidFile) {
        $oldPid = Get-Content $pidFile
        if ((Get-Process -Id $oldPid -ErrorAction SilentlyContinue).Count -gt 0) {
            Write-Host "  [$name] already running (pid $oldPid)"
            return
        }
    }
    # Write a PowerShell wrapper script for the restart loop
    $wrapper = @"
`$ProjectRoot = '$ProjectRoot'
Set-Location '`$ProjectRoot'
`$env:PYTHONPATH = '`$ProjectRoot'
while (`$true) {
    '$((Get-Date -Format o)) Starting $name...' | Out-File -FilePath '$logFile' -Encoding utf8 -Append
    python -m '$module' 2>&1 | Out-File -FilePath '$logFile' -Encoding utf8 -Append
    `$rc = `$LASTEXITCODE
    '$((Get-Date -Format o)) $name exited with code `$rc, restarting in 3s...' | Out-File -FilePath '$logFile' -Encoding utf8 -Append
    Start-Sleep -Seconds 3
}
"@
    $wrapperFile = "$PidDir\wrap_$name.ps1"
    $wrapper | Out-File -FilePath $wrapperFile -Encoding utf8

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-WindowStyle Hidden -File `"$wrapperFile`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $p.Id | Out-File -FilePath $pidFile -Encoding ascii
    Write-Host "  [$name] started (pid $($p.Id))"
}

function Start-Api {
    $pidFile = Get-PidFile "api"
    $logFile = Get-LogFile "api"
    if (Test-Path $pidFile) {
        $oldPid = Get-Content $pidFile
        if ((Get-Process -Id $oldPid -ErrorAction SilentlyContinue).Count -gt 0) {
            Write-Host "  [api] already running (pid $oldPid)"
            return
        }
    }
    $wrapper = @"
`$ProjectRoot = '$ProjectRoot'
Set-Location '`$ProjectRoot'
`$env:PYTHONPATH = '`$ProjectRoot'
while (`$true) {
    '$((Get-Date -Format o)) Starting API server...' | Out-File -FilePath '$logFile' -Encoding utf8 -Append
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000 2>&1 | Out-File -FilePath '$logFile' -Encoding utf8 -Append
    `$rc = `$LASTEXITCODE
    '$((Get-Date -Format o)) API exited with code `$rc, restarting in 3s...' | Out-File -FilePath '$logFile' -Encoding utf8 -Append
    Start-Sleep -Seconds 3
}
"@
    $wrapperFile = "$PidDir\wrap_api.ps1"
    $wrapper | Out-File -FilePath $wrapperFile -Encoding utf8

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-WindowStyle Hidden -File `"$wrapperFile`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $p.Id | Out-File -FilePath $pidFile -Encoding ascii
    Write-Host "  [api] started (pid $($p.Id))"
}

function Stop-All {
    $any = $false
    foreach ($c in $Components) {
        $pidFile = Get-PidFile $c.Name
        if (Test-Path $pidFile) {
            $pid = Get-Content $pidFile
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Host "  [$($c.Name)] stopped (pid $pid)"
            } catch {
                Write-Host "  [$($c.Name)] not running (pid $pid)"
            }
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
            # Remove wrapper script
            $w = "$PidDir\wrap_$($c.Name).ps1"
            Remove-Item -LiteralPath $w -Force -ErrorAction SilentlyContinue
            $any = $true
        }
    }
    # Stop API
    $pidFile = Get-PidFile "api"
    if (Test-Path $pidFile) {
        $pid = Get-Content $pidFile
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "  [api] stopped (pid $pid)"
        } catch {
            Write-Host "  [api] not running (pid $pid)"
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "$PidDir\wrap_api.ps1" -Force -ErrorAction SilentlyContinue
        $any = $true
    }
    # Kill any orphaned processes
    Get-Process | Where-Object { $_.ProcessName -eq "python" } | ForEach-Object {
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
            if ($cmd -match "src\.live\.runners\.run_") {
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    if (-not $any) { Write-Host "  Nothing running." }
}

function Status-All {
    $running = 0
    $total = $Components.Count + 1
    foreach ($c in $Components) {
        $pidFile = Get-PidFile $c.Name
        if (Test-Path $pidFile) {
            $pid = Get-Content $pidFile
            if ((Get-Process -Id $pid -ErrorAction SilentlyContinue).Count -gt 0) {
                Write-Host "  [$($c.Name)] running (pid $pid)"
                $running++
            } else {
                Write-Host "  [$($c.Name)] stopped"
                Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
            }
        } else {
            Write-Host "  [$($c.Name)] stopped"
        }
    }
    $pidFile = Get-PidFile "api"
    if (Test-Path $pidFile) {
        $pid = Get-Content $pidFile
        if ((Get-Process -Id $pid -ErrorAction SilentlyContinue).Count -gt 0) {
            Write-Host "  [api] running (pid $pid)"
            $running++
        } else {
            Write-Host "  [api] stopped"
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "  [api] stopped"
    }
    if ($running -eq 0) {
        Write-Host "  No components running."
    } elseif ($running -eq $total) {
        Write-Host "  All $running components running."
    } else {
        Write-Host "  $running / $total components running."
    }
}

switch ($Command.ToLower()) {
    "start" {
        Write-Host "Starting distributed components..."
        foreach ($c in $Components) {
            Start-Component $c.Name $c.Module
        }
        Start-Api
        Write-Host "Done. Use '$0 status' to check, '$0 stop' to stop."
    }
    "stop" {
        Write-Host "Stopping all components..."
        Stop-All
    }
    "status" {
        Status-All
    }
    "restart" {
        Write-Host "Restarting all components..."
        Stop-All
        Start-Sleep -Seconds 1
        Write-Host ""
        & $MyInvocation.MyCommand.Path "start"
    }
    default {
        Write-Host "Usage: $0 {start|stop|status|restart}"
        exit 1
    }
}
