[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ExpectedBranch = 'codex/all-ravens-release-candidate'
$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $RepoRoot

function Assert-RavenBranch {
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) { throw 'Wrong branch.' }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0 -or $staged.Count -gt 0) { throw 'Staged files present. Leave them alone.' }
}
Assert-RavenBranch
$Python = (Get-Command python -ErrorAction Stop).Source
$Probe = Join-Path $PSScriptRoot 'capture-staged-wad-bitstream-raven-state-readonly.py'
$gow = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') })
if ($gow.Count -ne 1) { throw 'Start God of War, load advanced save, pause game, then run command again.' }

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$relative = "archive/field-logs/runtime-captures/staged-wad-bitstream-raven-$stamp-$suffix"
$out = Join-Path $RepoRoot $relative
Write-Host 'Keep loaded game paused. Reader takes two equal snapshots of known staged pool.'
Write-Host 'Raw Channel A bytes and decoded candidates go in archive. Production authority stays unproven.'
$ErrorActionPreference = 'Continue'
$lines = @(& $Python $Probe --output-dir $out 2>&1 | ForEach-Object { "$_"; Write-Host "$_" })
$code = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $out -PathType Container)) { New-Item -ItemType Directory -Path $out | Out-Null }
$lines | Set-Content -LiteralPath (Join-Path $out 'console-log.txt') -Encoding UTF8
if ($code -ne 0) { "exit_code=$code" | Set-Content -LiteralPath (Join-Path $out 'error.txt') -Encoding UTF8 }
if ($code -eq 0 -and -not (Test-Path -LiteralPath (Join-Path $out 'report.json') -PathType Leaf)) {
    throw 'Capture returned no report. No success claimed.'
}
Assert-RavenBranch
& git add -f -- $relative
if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
$message = if ($code -eq 0) { "research(v0.10.5): capture packed WAD Raven candidates $stamp" } else { "research(v0.10.5): archive failed packed WAD capture $stamp" }
& git commit -m $message -- $relative
if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
if ((& git branch --show-current).Trim() -ne $ExpectedBranch) { throw 'Branch changed before push.' }
& git push origin "HEAD:refs/heads/$ExpectedBranch"
if ($LASTEXITCODE -ne 0) { throw 'git push failed; capture kept local. No force push.' }
$head = (& git rev-parse HEAD).Trim()
if ($code -ne 0) { throw "Capture failed; error evidence pushed in $head" }
Write-Host "STAGED_BITSTREAM_CAPTURE_PUSHED $head" -ForegroundColor Green
