# Smart Shipping Bidi - Test Runner
# Runs all integration tests

Write-Host "`n" -NoNewline
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Smart Shipping Bidi - Test Suite" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "`n"

# Check if server is running
Write-Host "Checking if server is running..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000" -Method Head -TimeoutSec 2 -ErrorAction Stop
    Write-Host "✅ Server is running`n" -ForegroundColor Green
} catch {
    Write-Host "❌ Server is NOT running!`n" -ForegroundColor Red
    Write-Host "Please start the server first:" -ForegroundColor Yellow
    Write-Host "  cd app" -ForegroundColor White
    Write-Host "  uv run uvicorn main:app --reload`n" -ForegroundColor White
    exit 1
}

# Test 1: WebSocket Connection
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Test 1: WebSocket Connection" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
python test_websocket_connection.py
$test1Result = $LASTEXITCODE

Write-Host "`n"

# Test 2: Audio Streaming
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Test 2: Audio Streaming" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
python test_audio_streaming.py
$test2Result = $LASTEXITCODE

Write-Host "`n"

# Summary
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

if ($test1Result -eq 0) {
    Write-Host "Test 1 (WebSocket): " -NoNewline
    Write-Host "PASSED ✅" -ForegroundColor Green
} else {
    Write-Host "Test 1 (WebSocket): " -NoNewline
    Write-Host "FAILED ❌" -ForegroundColor Red
}

if ($test2Result -eq 0) {
    Write-Host "Test 2 (Audio):     " -NoNewline
    Write-Host "PASSED ✅" -ForegroundColor Green
} else {
    Write-Host "Test 2 (Audio):     " -NoNewline
    Write-Host "FAILED ❌" -ForegroundColor Red
}

Write-Host "================================`n" -ForegroundColor Cyan

if ($test1Result -eq 0 -and $test2Result -eq 0) {
    Write-Host "🎉 All tests passed!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "⚠️  Some tests failed" -ForegroundColor Yellow
    exit 1
}
