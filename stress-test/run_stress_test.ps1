# Stress Test Runner for SmartShip Voice Assistant
# Simulates Telnyx phone calls to /ws/phone endpoint

param(
    [int]$Calls = 10,
    [string]$ServerHost,
    [int]$Port,
    [double]$Delay = 0.5,
    [int]$Batch = 0,
    [switch]$Sequential,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

# Load config from .env if not provided
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([^#=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($key -eq "SERVER_HOST" -and -not $ServerHost) { $ServerHost = $value }
            if ($key -eq "SERVER_PORT" -and -not $Port) { $Port = [int]$value }
        }
    }
}

# Defaults if still not set
if (-not $ServerHost) { $ServerHost = "localhost" }
if (-not $Port) { $Port = 8000 }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SmartShip Telnyx Stress Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if server is running
$scheme = if ($Port -eq 443 -or $ServerHost -match "\.run\.app") { "https" } else { "http" }
$checkUrl = if ($Port -eq 443) { "${scheme}://${ServerHost}/" } else { "${scheme}://${ServerHost}:${Port}/" }
Write-Host "Checking if server is running at $checkUrl..." -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri $checkUrl -TimeoutSec 10 -UseBasicParsing
    Write-Host "Server is running!" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Server is not reachable at $checkUrl" -ForegroundColor Red
    Write-Host ""
    if ($ServerHost -eq "localhost") {
        Write-Host "Please start the server first:" -ForegroundColor Yellow
        Write-Host "  cd app" -ForegroundColor White
        Write-Host "  uv run uvicorn main:app --port ${Port}" -ForegroundColor White
    } else {
        Write-Host "Check that Cloud Run service is deployed and running." -ForegroundColor Yellow
    }
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Calls:      $Calls"
Write-Host "  Host:       $ServerHost"
Write-Host "  Port:       $Port"
Write-Host "  Endpoint:   /ws/phone (Telnyx protocol)"
Write-Host "  Delay:      ${Delay}s"
if ($Batch -gt 0) {
    $numBatches = [math]::Ceiling($Calls / $Batch)
    Write-Host "  Batch Size: $Batch ($numBatches batches)"
}
Write-Host "  Sequential: $Sequential"
Write-Host ""

# Build command arguments
$cmdArgs = @(
    "stress_test.py"
    "--calls", $Calls
    "--host", $ServerHost
    "--port", $Port
    "--delay", $Delay
)

if ($Batch -gt 0) {
    $cmdArgs += @("--batch", $Batch)
}

if ($Sequential) {
    $cmdArgs += "--sequential"
}

if ($Verbose) {
    $cmdArgs += "--verbose"
}

# Run the stress test
Write-Host "Starting stress test..." -ForegroundColor Green
Write-Host ""

# Get the directory where this script is located
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $scriptDir
try {
    & uv run python @cmdArgs
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $exitCode
