# Test script for Docker deployment on Windows

Write-Host "=== Testing Wowza Webhook to Slack Translator ===" -ForegroundColor Cyan
Write-Host ""

# Check if container is running
$containerRunning = docker ps --format "{{.Names}}" | Select-String "wowza-webhook-to-slack"
if (-not $containerRunning) {
    Write-Host "❌ Container is not running!" -ForegroundColor Red
    Write-Host "Start with: docker-compose up -d"
    exit 1
}

Write-Host "✓ Container is running" -ForegroundColor Green

# Test health endpoint
Write-Host ""
Write-Host "Testing health endpoint..." -ForegroundColor Cyan
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method Get
    if ($healthResponse.status -eq "healthy") {
        Write-Host "✓ Health check passed" -ForegroundColor Green
    } else {
        Write-Host "❌ Health check failed" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Health check failed: $_" -ForegroundColor Red
    exit 1
}

# Test webhook endpoint with sample data
Write-Host ""
Write-Host "Testing webhook endpoint with sample Wowza event..." -ForegroundColor Cyan

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$body = @{
    name = "stream.started"
    context = @{
        stream = "test_stream"
        app = "live"
        appInstance = "_definst_"
        vhost = "_defaultVHost_"
        state = "started"
    }
    source = "Wowza"
    timestamp = $timestamp
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "http://localhost:8080/webhook" -Method Post -Body $body -ContentType "application/json"
    if ($response.status -eq "success") {
        Write-Host "✓ Webhook endpoint responded successfully" -ForegroundColor Green
        Write-Host ""
        Write-Host "Response: $($response | ConvertTo-Json)"
        Write-Host ""
        Write-Host "⚠️  Check Slack to verify the message was received!" -ForegroundColor Yellow
    } else {
        Write-Host "❌ Webhook endpoint failed" -ForegroundColor Red
        Write-Host "Response: $($response | ConvertTo-Json)"
        exit 1
    }
} catch {
    Write-Host "❌ Webhook endpoint failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== All tests passed! ===" -ForegroundColor Green
Write-Host ""
Write-Host "View logs: docker-compose logs -f"
