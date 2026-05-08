<#
.SYNOPSIS
    Pixiis performance measurement.

.DESCRIPTION
    Measures cold start, library-scan duration, installer size, and
    binary size against the migration-plan targets. Writes results to
    perf-results.md next to this script.

    Non-destructive: only reads files, launches Pixiis (which the user
    closes manually), and writes one markdown file. Does not require
    administrator rights.

.EXAMPLE
    .\scripts\perf.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# -- Resolve paths ------------------------------------------------------------

$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot    = Resolve-Path (Join-Path $scriptDir '..')
$exePath     = Join-Path $repoRoot 'src-tauri\target\release\pixiis.exe'
$bundleDir   = Join-Path $repoRoot 'src-tauri\target\release\bundle\nsis'
$scanLog     = Join-Path $env:APPDATA 'pixiis\scan_debug.log'
$resultsPath = Join-Path $scriptDir 'perf-results.md'

# Migration-plan targets (single source of truth — change here, render below).
$targets = @{
    ColdStartMs    = 800
    ScanMs         = 5000
    InstallerMB    = 50
    BinaryMB       = 25
}

# Result accumulator (everything stays a string for clean rendering).
$results = [ordered]@{
    ColdStart    = 'manual: launch the app, stopwatch from click to first paint'
    ScanMs       = 'manual: run Settings -> Scan Now, then re-run this script'
    InstallerMB  = 'manual: build the NSIS installer first (./build.sh)'
    BinaryMB     = 'manual: build the release binary first (./build.sh)'
}

Write-Host '== Pixiis perf =='
Write-Host "repo:   $repoRoot"
Write-Host "exe:    $exePath"
Write-Host "bundle: $bundleDir"
Write-Host "log:    $scanLog"
Write-Host ''

# -- 1. Cold start ------------------------------------------------------------
#
# The app has no --measure-startup-and-exit flag, so this is user-mediated:
# we Measure-Command the full launch-to-exit. The user is told to close the
# window as soon as the Home grid renders. The reported number includes user
# reaction time, so treat it as an upper bound, not gospel.

if (Test-Path $exePath) {
    Write-Host '[1/4] Cold start' -ForegroundColor Cyan
    Write-Host '      Pixiis will launch. Close the window AS SOON AS you see'
    Write-Host '      the Home grid. (User-mediated — includes reaction time.)'
    Write-Host '      Press <Enter> to continue, or Ctrl+C to skip.'
    $null = Read-Host

    try {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Start-Process -Wait -FilePath $exePath
        $sw.Stop()
        $ms = [int]$sw.Elapsed.TotalMilliseconds
        $results.ColdStart = "$ms ms (user-mediated upper bound — includes reaction time)"
        Write-Host "      -> $ms ms" -ForegroundColor Green
    }
    catch {
        $results.ColdStart = "manual: launch failed ($($_.Exception.Message))"
        Write-Host "      -> manual: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
else {
    Write-Host "[1/4] Cold start: exe not found at $exePath" -ForegroundColor Yellow
    $results.ColdStart = "manual: build first (./build.sh) — exe not at $exePath"
}

# -- 2. Library scan time -----------------------------------------------------
#
# scan_debug.log has one line per provider per scan, each ending in `(NNNms)`.
# We sum the most-recent run only (lines after the most recent "scan started"
# marker, if present, else all lines).

Write-Host ''
Write-Host '[2/4] Library scan time' -ForegroundColor Cyan
if (Test-Path $scanLog) {
    try {
        $lines = Get-Content $scanLog
        # Take only the most recent "scan started" block if present.
        $startIdx = -1
        for ($i = $lines.Count - 1; $i -ge 0; $i--) {
            if ($lines[$i] -match '(?i)scan\s+started') { $startIdx = $i; break }
        }
        if ($startIdx -ge 0) { $lines = $lines[$startIdx..($lines.Count - 1)] }

        $totalMs = 0
        $perProvider = @()
        foreach ($line in $lines) {
            if ($line -match '\((\d+)\s*ms\)') {
                $totalMs += [int]$Matches[1]
                $perProvider += $line.Trim()
            }
        }

        if ($perProvider.Count -gt 0) {
            $results.ScanMs = "$totalMs ms across $($perProvider.Count) provider entries"
            Write-Host "      -> $totalMs ms across $($perProvider.Count) provider entries" -ForegroundColor Green
            foreach ($p in $perProvider) { Write-Host "         $p" }
        }
        else {
            $results.ScanMs = 'manual: no (NNNms) entries in scan_debug.log — run Settings -> Scan Now'
            Write-Host '      -> no timing entries found in log' -ForegroundColor Yellow
        }
    }
    catch {
        $results.ScanMs = "manual: failed to parse scan_debug.log ($($_.Exception.Message))"
        Write-Host "      -> parse failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
else {
    Write-Host "      scan_debug.log not at $scanLog" -ForegroundColor Yellow
    $results.ScanMs = "manual: scan_debug.log not found — run the app and trigger Settings -> Scan Now"
}

# -- 3. Bundle (installer) size ----------------------------------------------

Write-Host ''
Write-Host '[3/4] Installer size' -ForegroundColor Cyan
if (Test-Path $bundleDir) {
    $installer = Get-ChildItem -Path $bundleDir -Filter '*.exe' -ErrorAction SilentlyContinue |
                 Sort-Object LastWriteTime -Descending |
                 Select-Object -First 1
    if ($installer) {
        $mb = [math]::Round($installer.Length / 1MB, 2)
        $results.InstallerMB = "$mb MB ($($installer.Name))"
        Write-Host "      -> $mb MB ($($installer.Name))" -ForegroundColor Green
    }
    else {
        $results.InstallerMB = "manual: no .exe found under $bundleDir"
        Write-Host "      -> no .exe under $bundleDir" -ForegroundColor Yellow
    }
}
else {
    Write-Host "      bundle dir not at $bundleDir" -ForegroundColor Yellow
    $results.InstallerMB = "manual: bundle dir not found — run ./build.sh to produce the NSIS installer"
}

# -- 4. Unpacked binary size --------------------------------------------------

Write-Host ''
Write-Host '[4/4] Binary size (pixiis.exe)' -ForegroundColor Cyan
if (Test-Path $exePath) {
    $size = (Get-Item $exePath).Length
    $mb = [math]::Round($size / 1MB, 2)
    $results.BinaryMB = "$mb MB"
    Write-Host "      -> $mb MB" -ForegroundColor Green
}
else {
    Write-Host "      pixiis.exe not at $exePath" -ForegroundColor Yellow
    $results.BinaryMB = "manual: pixiis.exe not found — run ./build.sh"
}

# -- Render perf-results.md ---------------------------------------------------

function Format-Row {
    param([string]$Metric, [string]$Measured, [string]$Target)
    "| $Metric | $Measured | $Target |"
}

$now    = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
$branch = try { (git -C $repoRoot rev-parse --abbrev-ref HEAD).Trim() } catch { 'unknown' }
$sha    = try { (git -C $repoRoot rev-parse --short HEAD).Trim() }     catch { 'unknown' }

$lines = @()
$lines += '# perf-results.md'
$lines += ''
$lines += "_Generated $now on branch \`$branch\` @ \`$sha\`._"
$lines += ''
$lines += '## Summary'
$lines += ''
$lines += '| Metric | Measured | Target (migration plan) |'
$lines += '|--------|----------|-------------------------|'
$lines += (Format-Row 'Cold start'                 $results.ColdStart   "<= $($targets.ColdStartMs) ms")
$lines += (Format-Row 'Library scan (sum of providers)' $results.ScanMs $("<= $($targets.ScanMs) ms"))
$lines += (Format-Row 'NSIS installer size'        $results.InstallerMB "<= $($targets.InstallerMB) MB")
$lines += (Format-Row 'pixiis.exe size'            $results.BinaryMB    "<= $($targets.BinaryMB) MB")
$lines += ''
$lines += '## Notes'
$lines += ''
$lines += '- Cold start is **user-mediated** — the script has no IPC handshake'
$lines += '  with the app, so the number includes the time it took the operator'
$lines += '  to recognize first paint and click close. Treat it as an upper'
$lines += '  bound; the real number is lower.'
$lines += '- Library scan time is summed from `(NNNms)` entries in'
$lines += '  `%APPDATA%\pixiis\scan_debug.log`, scoped to the most recent'
$lines += '  "scan started" block when one is present. Trigger a fresh scan'
$lines += '  via Settings -> Scan Now before running this script for the'
$lines += '  cleanest reading.'
$lines += '- Installer size is the most recently modified `.exe` in the NSIS'
$lines += '  bundle output directory.'
$lines += '- "manual: ..." rows mean the script could not measure that metric'
$lines += '  automatically — the description tells you what to do.'
$lines += ''

Set-Content -Path $resultsPath -Value ($lines -join "`r`n") -Encoding UTF8

Write-Host ''
Write-Host "Wrote $resultsPath" -ForegroundColor Green
