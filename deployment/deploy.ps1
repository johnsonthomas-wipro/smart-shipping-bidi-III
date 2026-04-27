#!/usr/bin/env pwsh
# deploy.ps1 - Deploy SmartShip Bidi Voice to Google Cloud Run

param(
    [string]$ProjectId = "",
    [string]$Region = "us-central1",
    [string]$ServiceName = "smart-bidi-3",
    [string]$GoogleApiKey = ""
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "SmartShip Bidi Voice - Cloud Run Deployment" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if gcloud is installed
if (!(Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: gcloud CLI not found" -ForegroundColor Red
    Write-Host "   Install from: https://cloud.google.com/sdk/docs/install" -ForegroundColor Yellow
    exit 1
}

# Get project ID if not provided
if ([string]::IsNullOrEmpty($ProjectId)) {
    $ProjectId = gcloud config get-value project 2>$null
    if ([string]::IsNullOrEmpty($ProjectId)) {
        Write-Host "ERROR: No GCP project ID found" -ForegroundColor Red
        Write-Host "   Run: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Yellow
        Write-Host "   Or: .\deploy.ps1 -ProjectId YOUR_PROJECT_ID" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "Configuration:" -ForegroundColor Green
Write-Host "   Project ID:    $ProjectId"
Write-Host "   Region:        $Region"
Write-Host "   Service Name:  $ServiceName"
Write-Host ""

# Get API key if not provided
if ([string]::IsNullOrEmpty($GoogleApiKey)) {
    Write-Host "Google Gemini API Key:" -ForegroundColor Yellow
    Write-Host "   Get your key from: https://aistudio.google.com/app/apikey" -ForegroundColor Cyan
    $GoogleApiKey = Read-Host "   Enter Google API Key"
    if ([string]::IsNullOrEmpty($GoogleApiKey)) {
        Write-Host "ERROR: API key required" -ForegroundColor Red
        exit 1
    }
}

# Get Telnyx API key for phone integration
Write-Host ""
Write-Host "Telnyx API Key (for phone calls):" -ForegroundColor Yellow
Write-Host "   Get your key from: https://portal.telnyx.com/#/app/api-keys" -ForegroundColor Cyan
$TelnyxApiKey = Read-Host "   Enter Telnyx API Key (or press Enter to skip)"

Write-Host ""
Write-Host "Starting deployment..." -ForegroundColor Green
Write-Host ""

# Copy files to deployment directory
Write-Host "Preparing deployment files..." -ForegroundColor Cyan
Copy-Item -Path "..\pyproject.toml" -Destination "pyproject.toml" -Force
Copy-Item -Path "..\README.md" -Destination "README.md" -Force
Copy-Item -Path "..\app" -Destination "app" -Recurse -Force
Write-Host "   Files copied" -ForegroundColor Green
Write-Host ""

# Enable required APIs
Write-Host "Enabling Google Cloud APIs..." -ForegroundColor Cyan
gcloud services enable run.googleapis.com --project=$ProjectId
gcloud services enable cloudbuild.googleapis.com --project=$ProjectId
gcloud services enable artifactregistry.googleapis.com --project=$ProjectId
Write-Host "   APIs enabled" -ForegroundColor Green
Write-Host ""

# Build and deploy
Write-Host "Building and deploying to Cloud Run..." -ForegroundColor Cyan
Write-Host "   (This may take 3-5 minutes)" -ForegroundColor Yellow
Write-Host ""

# Build environment variables string
$EnvVars = "GOOGLE_API_KEY=$GoogleApiKey,SHOW_CONVERSATION=no"
if (-not [string]::IsNullOrEmpty($TelnyxApiKey)) {
    $EnvVars += ",TELNYX_API_KEY=$TelnyxApiKey"
}

gcloud run deploy $ServiceName `
    --source . `
    --project=$ProjectId `
    --region=$Region `
    --platform=managed `
    --allow-unauthenticated `
    --set-env-vars="$EnvVars" `
    --memory=2Gi `
    --cpu=2 `
    --timeout=3600 `
    --max-instances=10 `
    --min-instances=0 `
    --cpu-boost `
    --no-cpu-throttling `
    --port=8080

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "Deployment Successful!" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    
    # Get service URL
    $ServiceUrl = gcloud run services describe $ServiceName --region=$Region --project=$ProjectId --format="value(status.url)" 2>$null
    
    if ($ServiceUrl) {
        Write-Host "Your app is live at:" -ForegroundColor Cyan
        Write-Host "   $ServiceUrl" -ForegroundColor White
        Write-Host ""
        Write-Host "Test the voice interface in your browser!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Configure Telnyx Phone Integration:" -ForegroundColor Yellow
        Write-Host "   1. Go to Telnyx Portal: https://portal.telnyx.com/#/app/numbers" -ForegroundColor White
        Write-Host "   2. Select your phone number" -ForegroundColor White
        Write-Host "   3. Under 'Voice Configuration', set Webhook URL to:" -ForegroundColor White
        Write-Host "      $ServiceUrl/telnyx/webhook" -ForegroundColor Cyan
        Write-Host "   4. Set HTTP Method: POST" -ForegroundColor White
        Write-Host "   5. Save and call your number!" -ForegroundColor White
        Write-Host ""
        Write-Host "To view logs:" -ForegroundColor Yellow
        Write-Host "   gcloud run logs tail $ServiceName --region=$Region --project=$ProjectId" -ForegroundColor White
        Write-Host ""
    }
} else {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Red
    Write-Host "Deployment Failed" -ForegroundColor Red
    Write-Host "================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check errors above and try again" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}
