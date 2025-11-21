# Quick start script for Docker deployment on Windows

Write-Host "=== Wowza Webhook to Slack Translator - Docker Quick Start ===" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-not (Test-Path .env)) {
    Write-Host "Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "⚠️  IMPORTANT: Edit .env file and add your Slack Webhook URL!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run: notepad .env"
    Write-Host "Then set: SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    Write-Host ""
    Read-Host "Press Enter after you've configured .env"
}

# Check if SLACK_WEBHOOK_URL is set
$envContent = Get-Content .env -Raw
if ($envContent -match 'SLACK_WEBHOOK_URL=(.+)') {
    $webhookUrl = $matches[1].Trim()
    if ([string]::IsNullOrEmpty($webhookUrl) -or $webhookUrl -eq "https://hooks.slack.com/services/YOUR/WEBHOOK/URL") {
        Write-Host "❌ Error: SLACK_WEBHOOK_URL not configured in .env" -ForegroundColor Red
        Write-Host "Please edit .env and set your Slack webhook URL"
        exit 1
    }
} else {
    Write-Host "❌ Error: SLACK_WEBHOOK_URL not found in .env" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Configuration found" -ForegroundColor Green
Write-Host ""

# Create logs directory
if (-not (Test-Path logs)) {
    New-Item -ItemType Directory -Path logs | Out-Null
}

# Build and start
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker-compose build

Write-Host ""
Write-Host "Starting container..." -ForegroundColor Cyan
docker-compose up -d

Write-Host ""
Write-Host "✓ Container started successfully!" -ForegroundColor Green
Write-Host ""

# Get local IP
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*"} | Select-Object -First 1).IPAddress
$port = if ($envContent -match 'PORT=(\d+)') { $matches[1] } else { "8080" }

Write-Host "Webhook endpoint: http://${localIP}:${port}/webhook" -ForegroundColor Cyan
Write-Host ""
Write-Host "View logs: docker-compose logs -f"
Write-Host "Stop: docker-compose down"
Write-Host ""
Write-Host "Configure Wowza to send webhooks to the endpoint above."
