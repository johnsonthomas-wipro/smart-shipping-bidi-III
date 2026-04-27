<#
.SYNOPSIS
    Play μ-law audio files from stress test logs.

.PARAMETER File
    Path to a specific .ulaw file to play.

.PARAMETER Folder
    Path to a call folder to play all files in sequence.

.PARAMETER Latest
    Play all files from the latest call folder.

.EXAMPLE
    .\play_audio.ps1 -Latest
    .\play_audio.ps1 -Folder "log\audio\20260124_163430_301e8c5c"
    .\play_audio.ps1 -File "log\audio\20260124_163430_301e8c5c\turn01_agent_received.ulaw"
#>
param(
    [string]$File,
    [string]$Folder,
    [switch]$Latest,
    [switch]$Convert  # Convert to WAV instead of playing
)

# Find ffplay/ffmpeg
$ffmpegPaths = @(
    "C:\Users\Johns\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages",
    "C:\ffmpeg\bin",
    "C:\Program Files\ffmpeg\bin"
)

$ffplay = $null
$ffmpeg = $null
foreach ($path in $ffmpegPaths) {
    $testPlay = Join-Path $path "ffplay.exe"
    $testMpeg = Join-Path $path "ffmpeg.exe"
    if (Test-Path $testPlay) { $ffplay = $testPlay }
    if (Test-Path $testMpeg) { $ffmpeg = $testMpeg }
    if ($ffplay -and $ffmpeg) { break }
}

# Try PATH
if (-not $ffplay) { $ffplay = (Get-Command ffplay -ErrorAction SilentlyContinue).Path }
if (-not $ffmpeg) { $ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Path }

if (-not $ffplay -and -not $Convert) {
    Write-Host "ERROR: ffplay not found. Install with: winget install ffmpeg" -ForegroundColor Red
    Write-Host "Or use -Convert to save as WAV files instead." -ForegroundColor Yellow
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$audioDir = Join-Path $scriptDir "log\audio"

# Get folder to process
$targetFolder = $null
if ($Latest) {
    $targetFolder = Get-ChildItem -Path $audioDir -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $targetFolder) {
        Write-Host "ERROR: No audio folders found in $audioDir" -ForegroundColor Red
        exit 1
    }
    $targetFolder = $targetFolder.FullName
} elseif ($Folder) {
    if (-not [System.IO.Path]::IsPathRooted($Folder)) {
        $targetFolder = Join-Path $scriptDir $Folder
    } else {
        $targetFolder = $Folder
    }
} elseif ($File) {
    if (-not [System.IO.Path]::IsPathRooted($File)) {
        $File = Join-Path $scriptDir $File
    }
}

function Play-UlawFile($filePath) {
    $name = Split-Path -Leaf $filePath
    if ($name -match "agent") {
        Write-Host "[AGENT]   " -NoNewline -ForegroundColor Cyan
    } else {
        Write-Host "[CUSTOMER]" -NoNewline -ForegroundColor Green
    }
    Write-Host " $name" -ForegroundColor White
    & $ffplay -f mulaw -ar 8000 $filePath -autoexit -nodisp 2>$null
}

function Convert-UlawToWav($filePath) {
    $wavPath = $filePath -replace '\.ulaw$', '.wav'
    $name = Split-Path -Leaf $filePath
    Write-Host "Converting $name -> $(Split-Path -Leaf $wavPath)" -ForegroundColor Yellow
    & $ffmpeg -y -f mulaw -ar 8000 -i $filePath $wavPath 2>$null
    return $wavPath
}

# Process single file
if ($File) {
    if (-not (Test-Path $File)) {
        Write-Host "ERROR: File not found: $File" -ForegroundColor Red
        exit 1
    }
    if ($Convert) {
        $wav = Convert-UlawToWav $File
        Write-Host "Created: $wav" -ForegroundColor Green
    } else {
        Play-UlawFile $File
    }
    exit 0
}

# Process folder
if ($targetFolder) {
    if (-not (Test-Path $targetFolder)) {
        Write-Host "ERROR: Folder not found: $targetFolder" -ForegroundColor Red
        exit 1
    }
    
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor DarkGray
    Write-Host "Playing audio from: $(Split-Path -Leaf $targetFolder)" -ForegroundColor White
    Write-Host "=" * 60 -ForegroundColor DarkGray
    Write-Host ""
    
    $files = Get-ChildItem -Path $targetFolder -Filter "*.ulaw" | Sort-Object Name
    
    if ($Convert) {
        foreach ($f in $files) {
            Convert-UlawToWav $f.FullName | Out-Null
        }
        Write-Host ""
        Write-Host "WAV files created in: $targetFolder" -ForegroundColor Green
    } else {
        foreach ($f in $files) {
            Play-UlawFile $f.FullName
        }
    }
    exit 0
}

# No args - show usage
Write-Host ""
Write-Host "Usage:" -ForegroundColor Yellow
Write-Host "  .\play_audio.ps1 -Latest              # Play latest call"
Write-Host "  .\play_audio.ps1 -Folder <path>       # Play specific call folder"
Write-Host "  .\play_audio.ps1 -File <path>         # Play specific file"
Write-Host "  .\play_audio.ps1 -Latest -Convert     # Convert to WAV instead"
Write-Host ""
Write-Host "Available call folders:" -ForegroundColor Yellow
Get-ChildItem -Path $audioDir -Directory | Sort-Object Name -Descending | ForEach-Object {
    $count = (Get-ChildItem -Path $_.FullName -Filter "*.ulaw").Count
    Write-Host "  $($_.Name) ($count files)"
}
