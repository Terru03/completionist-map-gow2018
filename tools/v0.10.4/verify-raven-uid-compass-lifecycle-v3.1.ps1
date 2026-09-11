param(
    [string]$RavenRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'raven-uid-compass-lifecycle-v3.1-runtime.ps1') -LibraryOnly
Assert-SourceBlobPins
Invoke-OfflineBuildAndTests -Game $RavenRoot
$proof = Assert-UidRoutingProof
$shas = Get-CandidateShasFromProof -Proof $proof
Assert-UidRoutingCandidate -Proof $proof -CandidateShas $shas
& (Join-Path $PSScriptRoot 'test-raven-uid-compass-lifecycle-v3.1-transaction.ps1')
Write-Host 'RAVEN_UID_COMPASS_LIFECYCLE_V31_OFFLINE_HANDOFF_VERIFIED'
Write-Host '  runtime tested: false'
Write-Host '  game files written: false'
