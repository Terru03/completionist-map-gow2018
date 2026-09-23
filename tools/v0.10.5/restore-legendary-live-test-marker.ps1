param([string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$engine = Join-Path $repoRoot 'tools/v0.10.4/nornir-runtime-candidate3.ps1'
$candidate = Join-Path $repoRoot 'build/v0.10.5-legendary-live-test/candidate/game-root'
$proofPath = Join-Path $repoRoot 'build/v0.10.5-legendary-live-test/candidate/build-report.json'
$state = Join-Path $repoRoot 'build/v0.10.5-legendary-live-test/transaction'
$active = Join-Path $state 'active.json'
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}
if (-not (Test-Path -LiteralPath $active -PathType Leaf)) { throw "No Legendary transaction: $active" }
$engineText = [IO.File]::ReadAllText($engine).Replace("`r`n", "`n").Replace("`r", "`n")
$engineHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($engineText))).ToLowerInvariant()
if ($engineHash -ne '83f11f8e3a5b6e56ad5d06ba22baa779f91c986ace42ab3017de2b2231d7057a') {
    throw 'Proven transaction engine changed.'
}
$proof = Get-Content -Raw -LiteralPath $proofPath | ConvertFrom-Json
$fileMap = [ordered]@{}
$shas = [ordered]@{}
foreach ($relative in @($proof.modified_install_files)) {
    $fileMap[$relative] = $relative
    $shas[$relative] = [string]$proof.candidate_files.$relative.sha256
}
. $engine -LibraryOnly
$repo = $repoRoot
$manifest = Get-ValidatedActiveTransaction -Active $active -Game $GameRoot -Candidate $candidate -State $state `
    -ProofPath $proofPath -FileMap $fileMap -CandidateShas $shas -CandidateLabel 'legendary-live-test-raven-base' `
    -RepoBranch 'codex/collectible-legendary-chests'
if ($manifest.status -ne 'installed') { throw "Legendary transaction needs review: $($manifest.status)" }
$guard = {
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
        throw 'God of War started during restore.'
    }
}
Restore-State -Manifest $manifest -Game $GameRoot -Candidate $candidate -State $state -Active $active `
    -ProofPath $proofPath -FileMap $fileMap -CandidateShas $shas -CandidateLabel 'legendary-live-test-raven-base' `
    -RepoBranch 'codex/collectible-legendary-chests' -CheckInstalled $true -Force $false -WriteGuard $guard
& (Join-Path $repoRoot 'tools/v0.10.5/rollback-raven-authority-bridge.ps1') -GameRoot $GameRoot
if (-not $?) { throw 'Map restored; Raven bridge rollback needs review.' }
Write-Host "LEGENDARY_LIVE_TEST_RESTORED transaction=$($manifest.transaction_id)"
