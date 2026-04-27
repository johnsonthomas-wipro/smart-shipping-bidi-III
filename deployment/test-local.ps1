#!/usr/bin/env pwsh
# test-local.ps1 - Test Docker image locally before deploying

param(
    [string]$GoogleApiKey = ""
)

Write-Host "🧪 Testing SmartShip Bidi Voice locally..." -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
docker info >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: Docker is not running" -ForegroundColor Red
    Write-Host "   Start Docker Desktop and try again" -ForegroundColor Yellow
    exit 1
}

# Get API key if not provided
if ([string]::IsNullOrEmpty($GoogleApiKey)) {
    $GoogleApiKey = Read-Host "Enter Google API Key"
    if ([string]::IsNullOrEmpty($GoogleApiKey)) {
        Write-Host "❌ Error: API key required" -ForegroundColor Red
        exit 1
    }
}

# Stop any existing container
Write-Host "🛑 Stopping existing container..." -ForegroundColor Yellow
docker stop smartship-bidi-test2 >$null 2>&1
docker rm smartship-bidi-test2 >$null 2>&1

# Run container
Write-Host "🚀 Starting container on http://localhost:8080..." -ForegroundColor Green
Write-Host ""

docker run -d `
    --name smartship-bidi-test2 `
    -p 8080:8080 `
    -e GOOGLE_API_KEY=$GoogleApiKey `
    -e PORT=8080 `
    -e SHOW_CONVERSATION=yes `
    smartship-bidi-2:latest

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Container started successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "🌐 Open in browser:" -ForegroundColor Cyan
    Write-Host "   http://localhost:8080" -ForegroundColor White
    Write-Host ""
    Write-Host "📋 View logs:" -ForegroundColor Cyan
    Write-Host "   docker logs -f smartship-bidi-test2" -ForegroundColor White
    Write-Host ""
    Write-Host "🛑 Stop container:" -ForegroundColor Cyan
    Write-Host "   docker stop smartship-bidi-test" -ForegroundColor White
    Write-Host ""
    
    # Wait a moment for container to start
    Start-Sleep -Seconds 2
    
    # Check if container is running
    $status = docker ps --filter "name=smartship-bidi-test2" --format "{{.Status}}"
    if ($status) {
        Write-Host "✓ Container is running: $status" -ForegroundColor Green
        
        # Try to open in browser
        Start-Process "http://localhost:8080"
    } else {
        Write-Host "⚠️  Container may have crashed. Check logs:" -ForegroundColor Yellow
        docker logs smartship-bidi-test2
    }
} else {
    Write-Host "❌ Failed to start container" -ForegroundColor Red
    exit 1
}
