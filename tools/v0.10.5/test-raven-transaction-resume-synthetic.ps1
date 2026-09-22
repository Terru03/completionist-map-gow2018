$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$engine = Join-Path $repo 'tools\v0.10.4\nornir-runtime-candidate3.ps1'
if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
    throw "Missing transaction engine: $engine"
}
. $engine -LibraryOnly

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Write-TestFile([string]$Path, [string]$Text) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'completionist-raven-rollback-resume-' + [Guid]::NewGuid().ToString('N'))
$game = Join-Path $tempRoot 'fake-game'
$candidate = Join-Path $tempRoot 'candidate'
$state = Join-Path $tempRoot 'state'
$active = Join-Path $state 'active.json'
$proof = Join-Path $tempRoot 'proof.json'
New-Item -ItemType Directory -Force -Path $game,$candidate,$state | Out-Null
Write-TestFile $proof '{"synthetic":true}'

$files = [ordered]@{
    mapmaster = 'exec/dc/pc_le/mapmaster.dcb'
    mapcoords = 'exec/dc/pc_le/mapcoords.dcb'
    ui = 'exec/dc/pc_le/wad_r_ui.dcb'
    mapmenu = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    events = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
}

$candidateShas = [ordered]@{}
$baselineShas = [ordered]@{}

try {
    $index = 0
    foreach ($name in $files.Keys) {
        $relative = [string]$files[$name]
        $candidatePath = Join-Path $candidate $relative
        $gamePath = Join-Path $game $relative
        Write-TestFile $candidatePath "candidate-$index-$name"
        Write-TestFile $gamePath "baseline-$index-$name"
        $candidateShas[$name] = Get-Sha256 $candidatePath
        $baselineShas[$name] = Get-Sha256 $gamePath
        $index++
    }

    $common = @{
        Game = $game
        Candidate = $candidate
        State = $state
        Active = $active
        FileMap = $files
        CandidateShas = $candidateShas
        CandidateLabel = 'raven-synthetic-rollback-resume'
        RepoBranch = 'codex/raven-release-adversarial-audit'
        RepoHead = 'synthetic'
        ProofPath = $proof
    }
    $manifest = Invoke-TransactionalInstall @common
    Assert-True ([string]$manifest.status -eq 'installed') 'Synthetic install did not finish.'

    $script:rollbackWrites = 0
    $guard = {
        $script:rollbackWrites++
        if ($script:rollbackWrites -eq 2) {
            throw 'SYNTHETIC_ROLLBACK_INTERRUPTION'
        }
    }

    $restoreArgs = @{
        Manifest = $manifest
        Game = $game
        Candidate = $candidate
        State = $state
        Active = $active
        ProofPath = $proof
        FileMap = $files
        CandidateShas = $candidateShas
        CandidateLabel = 'raven-synthetic-rollback-resume'
        RepoBranch = 'codex/raven-release-adversarial-audit'
        CheckInstalled = $true
        Force = $false
        WriteGuard = $guard
    }

    $interrupted = $false
    try {
        Restore-State @restoreArgs
    }
    catch {
        $interrupted = $_.Exception.Message -like '*SYNTHETIC_ROLLBACK_INTERRUPTION*'
    }
    Assert-True $interrupted 'Synthetic rollback interruption was not observed.'

    $validateArgs = @{
        Active = $active
        Game = $game
        Candidate = $candidate
        State = $state
        ProofPath = $proof
        FileMap = $files
        CandidateShas = $candidateShas
        CandidateLabel = 'raven-synthetic-rollback-resume'
        RepoBranch = 'codex/raven-release-adversarial-audit'
    }
    $resume = Get-ValidatedActiveTransaction @validateArgs

    Assert-True (
        [string]$resume.status -in @('rolling-back','rolling-back-after-install-failure')
    ) "Unexpected interrupted rollback status: $($resume.status)"
    Assert-True (
        @($resume.entries | Where-Object { [string]$_.write_state -eq 'restored' }).Count -ge 1
    ) 'Interrupted rollback did not persist restored progress.'

    $resumeArgs = @{
        Manifest = $resume
        Game = $game
        Candidate = $candidate
        State = $state
        Active = $active
        ProofPath = $proof
        FileMap = $files
        CandidateShas = $candidateShas
        CandidateLabel = 'raven-synthetic-rollback-resume'
        RepoBranch = 'codex/raven-release-adversarial-audit'
        CheckInstalled = $false
        Force = $false
    }
    Restore-State @resumeArgs

    foreach ($name in $files.Keys) {
        $gamePath = Join-Path $game ([string]$files[$name])
        Assert-True (Test-Path -LiteralPath $gamePath -PathType Leaf) "Restored file missing: $name"
        Assert-True ((Get-Sha256 $gamePath) -eq [string]$baselineShas[$name]) "Restored SHA differs: $name"
    }

    $final = Get-ValidatedActiveTransaction @validateArgs
    Assert-True (
        @($final.entries | Where-Object { [string]$_.write_state -notin @('pending','restored') }).Count -eq 0
    ) 'Final resumed rollback contains unrestored written entries.'

    Write-Host 'RAVEN_SYNTHETIC_ROLLBACK_RESUME_PASSED files=5 interruption=true resumed=true exact=true'
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
