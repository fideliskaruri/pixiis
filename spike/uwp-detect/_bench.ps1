$ErrorActionPreference = 'Continue'
Set-Location 'D:\code\python\pixiis\.worktrees\pane3-uwp\spike\uwp-detect'

Write-Host '=== uwp-detect.exe (3 warm runs, total wall time) ==='
$null = & target\release\uwp-detect.exe 2>&1 | Out-Null
$rust = Measure-Command {
    for ($i = 0; $i -lt 3; $i++) {
        $null = & target\release\uwp-detect.exe 2>&1
    }
}
Write-Host ('  3 runs: {0:N3}s, avg {1:N3}s' -f $rust.TotalSeconds, ($rust.TotalSeconds / 3))

Write-Host ''
Write-Host '=== powershell baseline (3 warm runs incl. process startup) ==='
$null = powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\_baseline.ps1 *>$null
$ps = Measure-Command {
    for ($i = 0; $i -lt 3; $i++) {
        $null = powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\_baseline.ps1 *>$null
    }
}
Write-Host ('  3 runs: {0:N3}s, avg {1:N3}s' -f $ps.TotalSeconds, ($ps.TotalSeconds / 3))

Write-Host ''
Write-Host '=== single-run capture for diff ==='
& target\release\uwp-detect.exe > out_rust.json 2> out_rust_stderr.txt
Get-Content out_rust_stderr.txt
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\_baseline.ps1 > out_ps.json
Write-Host ('  out_rust.json: {0} bytes' -f (Get-Item out_rust.json).Length)
Write-Host ('  out_ps.json:   {0} bytes' -f (Get-Item out_ps.json).Length)
