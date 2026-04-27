#!/usr/bin/env pwsh
# build.ps1 - Build Docker image locally for testing

Write-Host "Building SmartShip Bidi Voice Docker image..." -ForegroundColor Cyan
Write-Host ""

# Copy files from parent directory
Write-Host "Copying application files..." -ForegroundColor Yellow
Copy-Item -Path "..\pyproject.toml" -Destination "pyproject.toml" -Force
Copy-Item -Path "..\README.md" -Destination "README.md" -Force
Copy-Item -Path "..\app" -Destination "app" -Recurse -Force
Write-Host "   Files copied" -ForegroundColor Green
Write-Host ""

# Build Docker image
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build -t smart-bidi-3:latest .

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "To run locally:" -ForegroundColor Cyan
    Write-Host "   docker run -p 8080:8080 -e GOOGLE_API_KEY=your_key smart-bidi-3:latest" -ForegroundColor White
    Write-Host ""
    Write-Host "To test:" -ForegroundColor Cyan
    Write-Host "   .\test-local.ps1" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "Build failed" -ForegroundColor Red
    exit 1
}
