#!/usr/bin/env pwsh
# verify-setup.ps1 - Verify all prerequisites before deployment

Write-Host "Verifying deployment prerequisites..." -ForegroundColor Cyan
Write-Host ""

$errors = 0

# Check Google Cloud CLI
Write-Host "1. Checking gcloud CLI..." -ForegroundColor Yellow
if (Get-Command gcloud -ErrorAction SilentlyContinue) {
    $version = (gcloud version --format="value(version)")
    Write-Host "   ✓ gcloud CLI installed: $version" -ForegroundColor Green
} else {
    Write-Host "   ✗ gcloud CLI not found" -ForegroundColor Red
    Write-Host "     Install: https://cloud.google.com/sdk/docs/install" -ForegroundColor Yellow
    $errors++
}
Write-Host ""

# Check authentication
Write-Host "2. Checking authentication..." -ForegroundColor Yellow
$account = gcloud config get-value account 2>$null
if ($account) {
    Write-Host "   ✓ Authenticated as: $account" -ForegroundColor Green
} else {
    Write-Host "   ✗ Not authenticated" -ForegroundColor Red
    Write-Host "     Run: gcloud auth login" -ForegroundColor Yellow
    $errors++
}
Write-Host ""

# Check project
Write-Host "3. Checking active project..." -ForegroundColor Yellow
$project = gcloud config get-value project 2>$null
if ($project) {
    Write-Host "   ✓ Active project: $project" -ForegroundColor Green
} else {
    Write-Host "   ⚠ No active project" -ForegroundColor Yellow
    Write-Host "     Run: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Yellow
    Write-Host "     Or: Specify -ProjectId in deploy.ps1" -ForegroundColor Yellow
}
Write-Host ""

# Check Docker (optional)
Write-Host "4. Checking Docker (optional for local testing)..." -ForegroundColor Yellow
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker info >$null 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerVersion = docker version --format "{{.Server.Version}}" 2>$null
        Write-Host "   ✓ Docker installed and running: $dockerVersion" -ForegroundColor Green
    } else {
        Write-Host "   ⚠ Docker installed but not running" -ForegroundColor Yellow
        Write-Host "     Start Docker Desktop for local testing" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ⚠ Docker not found (optional)" -ForegroundColor Yellow
    Write-Host "     Install for local testing: https://docker.com" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "================================================" -ForegroundColor Cyan
if ($errors -eq 0) {
    Write-Host "✅ Ready for deployment!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "   1. Get Gemini API key: https://aistudio.google.com/app/apikey" -ForegroundColor White
    Write-Host "   2. Run: .\deploy.ps1 -GoogleApiKey YOUR_KEY" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "❌ Please fix $errors error(s) above" -ForegroundColor Red
    Write-Host ""
    exit 1
}
