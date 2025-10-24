<#
install_windows.ps1

Installs the WS Slack Translator on Windows:
- Ensures Python is installed (downloads and installs silently if missing)
- Installs pip requirements
- Downloads NSSM and installs it to Program Files\nssm
- Copies this project to Program Files\WS_Slack_Translator
- Registers an NSSM service named "WS-Slack-Translator" that runs `python http_server.py`

Usage (run as Administrator):
  .\install_windows.ps1 [-InstallDir "C:\Program Files\WS_Slack_Translator"] [-WebhookUrl "https://hooks.slack.com/services/..."]

Notes:
 - This script needs to be run with Administrator privileges to install the service.
 - Default Python installer URL targets recent Python 3.11 x64. Adjust if needed.
#>

param(
    [string]$InstallDir = "C:\Program Files\WS_Slack_Translator",
    [string]$WebhookUrl = "",
    [string]$PythonInstallerUrl = "https://www.python.org/ftp/python/3.11.16/python-3.11.16-amd64.exe",
    [string]$NssmZipUrl = "https://nssm.cc/release/nssm-2.24.zip"
)

function Ensure-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error "This script must be run as Administrator. Right-click and Run as Administrator."
        exit 1
    }
}

function Download-File($url, $outPath) {
    Write-Host "Downloading $url to $outPath"
    try {
        Invoke-WebRequest -Uri $url -OutFile $outPath -UseBasicParsing -ErrorAction Stop
        return $true
    } catch {
        Write-Error ("Failed to download {0}: {1}" -f $url, $_)
        return $false
    }
}

Ensure-Admin

Write-Host "Installer started. Using InstallDir=$InstallDir"

# Create install directory
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Copy project files into InstallDir
Write-Host "Copying project files to $InstallDir"
Copy-Item -Path (Join-Path $scriptDir '*') -Destination $InstallDir -Recurse -Force

# Find python
function Get-PythonExe {
    $python = (Get-Command python -ErrorAction SilentlyContinue)
    if ($python) { return $python.Source }
    $py = (Get-Command python3 -ErrorAction SilentlyContinue)
    if ($py) { return $py.Source }
    return $null
}

$pythonExe = Get-PythonExe
if (-not $pythonExe) {
    Write-Host "Python not found. Downloading installer..."
    $tmp = Join-Path $env:TEMP "python_installer.exe"
    if (-not (Download-File -url $PythonInstallerUrl -outPath $tmp)) { Write-Error "Cannot download Python installer"; exit 1 }
    Write-Host "Running Python installer silently..."
    $args = "/quiet InstallAllUsers=1 PrependPath=1"
    $proc = Start-Process -FilePath $tmp -ArgumentList $args -Wait -PassThru
    if ($proc.ExitCode -ne 0) { Write-Error "Python installer failed with exit code $($proc.ExitCode)"; exit 1 }
    # Refresh path
    $pythonExe = Get-PythonExe
    if (-not $pythonExe) { Write-Error "Python installation not found after installer"; exit 1 }
}

Write-Host "Using Python at $pythonExe"

# Install requirements
$reqFile = Join-Path $InstallDir 'requirements.txt'
if (Test-Path $reqFile) {
    Write-Host "Installing Python dependencies from $reqFile"
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install -r $reqFile
} else {
    Write-Warning "requirements.txt not found in $InstallDir; skipping pip install"
}

# Download and install NSSM
$nssmTarget = Join-Path $env:ProgramFiles "nssm"
if (-not (Test-Path $nssmTarget)) { New-Item -ItemType Directory -Path $nssmTarget | Out-Null }

$nssmZip = Join-Path $env:TEMP "nssm.zip"
if (-not (Download-File -url $NssmZipUrl -outPath $nssmZip)) { Write-Error "Failed to download NSSM"; exit 1 }

Write-Host "Extracting NSSM"
# Extract into a unique temp folder to avoid "file already exists" errors from previous runs
$nssmExtractDir = Join-Path $env:TEMP ("nssm_extracted_{0}" -f (Get-Date -Format "yyyyMMddHHmmss"))
if (-not (Test-Path $nssmExtractDir)) { New-Item -ItemType Directory -Path $nssmExtractDir | Out-Null }
try {
    # Use Expand-Archive which supports -Force on PowerShell 5+ and avoids .NET duplicate file errors
    Expand-Archive -Path $nssmZip -DestinationPath $nssmExtractDir -Force
} catch {
    Write-Warning "Expand-Archive failed: $_. Falling back to .NET extraction (will overwrite existing files)."
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($nssmZip, $nssmExtractDir)
    } catch {
        Write-Error ("Failed to extract NSSM archive to {0}: {1}" -f $nssmExtractDir, $_)
        exit 1
    }
}

# Find nssm.exe in extracted folder (it includes subfolders like win64)
$nssmExeCandidate = Get-ChildItem -Path $nssmExtractDir -Filter nssm.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $nssmExeCandidate) { Write-Error "nssm.exe not found in extracted archive"; exit 1 }

Copy-Item -Path $nssmExeCandidate.FullName -Destination (Join-Path $nssmTarget 'nssm.exe') -Force

$nssmExe = Join-Path $nssmTarget 'nssm.exe'
Write-Host "NSSM installed to $nssmExe"

# Create config.json if webhook provided
function Prompt-ForWebhook {
    param([string]$Message = "Enter Slack Incoming Webhook URL:", [string]$Title = "Slack Webhook")
    # Try to show a Windows GUI input box via Microsoft.VisualBasic if available
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop
        $input = [Microsoft.VisualBasic.Interaction]::InputBox($Message, $Title, "")
        if ($input -and $input.Trim().Length -gt 0) { return $input.Trim() }
    } catch {
        # GUI not available or failed; fall back to console prompt
    }

    # Console fallback
    try {
        $consoleInput = Read-Host -Prompt "Enter Slack Incoming Webhook URL (or leave blank to skip)"
        if ($consoleInput -and $consoleInput.Trim().Length -gt 0) { return $consoleInput.Trim() }
    } catch {
        return ""
    }

    return ""
}

if (-not $WebhookUrl) {
    Write-Host "No webhook provided on the command line. Prompting for Slack webhook..."
    $prompted = Prompt-ForWebhook
    if ($prompted) { $WebhookUrl = $prompted }
}

if ($WebhookUrl) {
    $cfg = @{ slack_webhook_url = $WebhookUrl } | ConvertTo-Json -Depth 3
    $cfgPath = Join-Path $InstallDir 'config.json'
    $cfg | Out-File -FilePath $cfgPath -Encoding utf8
    Write-Host "Wrote config.json with Slack webhook to $cfgPath"
} else {
    Write-Host "No webhook configured. You can run config_gui.py on the host or create config.json manually later."
}

# Register service with NSSM
$svcName = 'WS-Slack-Translator'
$svcInstalled = & $nssmExe status $svcName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Service $svcName already installed; will remove and reinstall"
    & $nssmExe remove $svcName confirm
}

$appDir = $InstallDir
$pythonCmd = $pythonExe
$appParameter = Join-Path $appDir 'http_server.py'

Write-Host "Installing NSSM service: $svcName"
# Install the service with application only; set parameters explicitly to avoid quoting issues
& $nssmExe install $svcName $pythonCmd
 # Quote the AppParameters so NSSM treats the full path with spaces as a single argument
 # Use a relative parameter (script filename) and rely on AppDirectory so NSSM invokes
 # python with the working directory set to the install folder. This avoids any
 # quoting/space issues when the install path contains spaces.
 $relativeParam = 'http_server.py'
 & $nssmExe set $svcName AppParameters $relativeParam
& $nssmExe set $svcName AppDirectory $appDir
& $nssmExe set $svcName Start SERVICE_AUTO_START

# Ensure a logs directory exists for service stdout/stderr capture
$logsDir = Join-Path $appDir 'logs'
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

# Configure NSSM to capture stdout/stderr to files so we can diagnose failures
$stdoutPath = Join-Path $logsDir 'stdout.log'
$stderrPath = Join-Path $logsDir 'stderr.log'
& $nssmExe set $svcName AppStdout $stdoutPath
& $nssmExe set $svcName AppStderr $stderrPath
& $nssmExe set $svcName AppRotateFiles 1
& $nssmExe set $svcName AppRestartDelay 5000

# Ensure the service can find python: add the python executable directory to the service environment PATH
try {
    $pythonDir = Split-Path -Parent $pythonExe
    # NSSM AppEnvironmentExtra expects newline-separated VAR=VALUE entries; only one provided here
    $envEntry = "PATH=$pythonDir;$env:PATH"
    & $nssmExe set $svcName AppEnvironmentExtra $envEntry
    Write-Host "Set AppEnvironmentExtra for $svcName to include Python path: $pythonDir"
} catch {
    Write-Warning "Failed to set AppEnvironmentExtra: $_"
}

Write-Host "Starting service $svcName"
& $nssmExe start $svcName

Write-Host "Installation complete. Service should be running. Check Windows Services or run `nssm status $svcName`."
