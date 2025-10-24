<#
uninstall_windows.ps1

Removes the NSSM service and deletes installed files for WS Slack Translator.

Usage (run as Administrator):
  .\uninstall_windows.ps1 [-InstallDir "C:\Program Files\WS_Slack_Translator"]
#>

param(
    [string]$InstallDir = "C:\Program Files\WS_Slack_Translator"
)

# Remember the directory the user invoked the script from so we can return to it
$OriginalLocation = Get-Location

function Ensure-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error "This script must be run as Administrator. Right-click and Run as Administrator."
        exit 1
    }
}

Ensure-Admin

$nssmPath = Join-Path $env:ProgramFiles 'nssm\nssm.exe'
$svcName = 'WS-Slack-Translator'

if (-not (Test-Path $nssmPath)) {
    Write-Warning "NSSM not found at $nssmPath. If you installed NSSM elsewhere, remove the service manually."
} else {
    Write-Host "Stopping service $svcName (if present)"
    & $nssmPath stop $svcName 2>$null
    Start-Sleep -Seconds 2
    # If still running, try to kill the process(es) NSSM manages
    $status = (& $nssmPath status $svcName) 2>$null
    if ($status -and $status.Trim() -ne 'SERVICE_STOPPED') {
        Write-Warning "Service did not stop gracefully (status: $status). Attempting nssm remove and process cleanup."
        try { & $nssmPath remove $svcName confirm 2>$null } catch {}

        # Find Python processes that reference the install dir or http_server.py and kill them
        try {
            $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -like "*http_server.py*" -or $_.CommandLine -like "*$InstallDir*") }
            foreach ($p in $procs) {
                Write-Host "Killing process Id $($p.ProcessId) (CmdLine: $($p.CommandLine))"
                Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            }
        } catch {
            Write-Warning "Failed to enumerate/kill processes: $_"
        }
    } else {
        # Remove service entry if it exists
        try { & $nssmPath remove $svcName confirm 2>$null } catch {}
    }
}

# Change current directory to a safe location to avoid locking the install directory
try {
    Set-Location -Path $env:TEMP
} catch {
    Write-Warning "Failed to change directory to TEMP: $_"
}

# Attempt to remove the install directory with retries, because open handles may exist briefly
if (Test-Path $InstallDir) {
    Write-Host "Attempting to remove install directory $InstallDir"
    $maxAttempts = 5
    $attempt = 0
    $removed = $false
    while (-not $removed -and $attempt -lt $maxAttempts) {
        try {
            Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction Stop
            $removed = $true
            Write-Host "Removed $InstallDir"
        } catch {
                $attempt++
                Write-Warning ("Attempt {0}: Failed to remove {1}: {2}. Retrying in 2s..." -f $attempt, $InstallDir, $_)
            Start-Sleep -Seconds 2
        }
    }
    if (-not $removed) {
        Write-Error "Failed to remove $InstallDir after $maxAttempts attempts. Some files may still be in use. Close programs or reboot and try again."
    }
} else {
    Write-Host "Install directory $InstallDir not found."
}

Write-Host "Uninstall complete."

# Attempt to return to the directory the user started the script from
try {
    if ($OriginalLocation) { Set-Location -Path $OriginalLocation }
} catch {
    Write-Warning "Failed to return to original directory: $_"
}
