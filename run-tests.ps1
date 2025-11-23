# PowerShell script to run tests for WS Slack Translator

Write-Host "=== WS Slack Translator Test Runner ===" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& ".\venv\Scripts\Activate.ps1"

# Install/upgrade test dependencies
Write-Host ""
Write-Host "Installing test dependencies..." -ForegroundColor Cyan
pip install -q --upgrade pip
pip install -q -r requirements-test.txt

# Run tests
Write-Host ""
Write-Host "Running test suite..." -ForegroundColor Cyan
Write-Host ""

python -m pytest test_http_server.py -v --tb=short --color=yes

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "✓ All tests passed!" -ForegroundColor Green
} else {
    Write-Host "✗ Some tests failed" -ForegroundColor Red
}

Write-Host ""
Write-Host "To run tests with coverage report:" -ForegroundColor Yellow
Write-Host "  pytest test_http_server.py --cov=http_server --cov-report=html"
Write-Host ""
Write-Host "To run specific test class:" -ForegroundColor Yellow
Write-Host "  pytest test_http_server.py::TestConfiguration -v"
Write-Host ""

exit $exitCode
