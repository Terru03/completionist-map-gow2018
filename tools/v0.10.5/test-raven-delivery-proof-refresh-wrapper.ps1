$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$wrapperSource = Join-Path $PSScriptRoot 'refresh-raven-delivery-proof-and-push.ps1'
if (-not (Test-Path -LiteralPath $wrapperSource -PathType Leaf)) {
    throw "Missing proof refresh wrapper: $wrapperSource"
}

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Invoke-Git([string]$WorkingDirectory, [string[]]$Arguments) {
    $output = @(& git -C $WorkingDirectory @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($output -join [Environment]::NewLine)"
    }
    return $output
}

function Get-Hash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function New-TestRepo([string]$Root) {
    $remote = Join-Path $Root 'remote.git'
    $work = Join-Path $Root 'work'
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    & git init --bare $remote | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize local bare remote.' }
    & git init -b codex/all-ravens-release-candidate $work | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize local test repo.' }
    Invoke-Git $work @('config','user.name','Raven Wrapper Test') | Out-Null
    Invoke-Git $work @('config','user.email','raven-wrapper-test@example.invalid') | Out-Null

    $tools = Join-Path $work 'tools\v0.10.5'
    $archive = Join-Path $work 'archive\all-ravens'
    $candidate = Join-Path $work 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
    $map = Join-Path $candidate 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
    $events = Join-Path $candidate 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
    $proof = Join-Path $archive 'all-ravens-release-candidate-offline.json'

    New-Item -ItemType Directory -Force -Path $tools,$archive,(Split-Path $map -Parent),(Split-Path $events -Parent) | Out-Null
    Copy-Item -LiteralPath $wrapperSource -Destination (Join-Path $tools 'refresh-raven-delivery-proof-and-push.ps1')

    $fakePrepare = @'
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[2]
candidate = repo / "build/v0.10.5-all-ravens-release-candidate/offline/candidate/game-root"
proof_path = repo / "archive/all-ravens/all-ravens-release-candidate-offline.json"
map_path = candidate / "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"
event_path = candidate / "mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua"

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

mode = os.environ.get("RAVEN_WRAPPER_TEST_MODE", "success")
if "--refresh-proof" in sys.argv:
    map_path.write_bytes(b"map-new")
    event_path.write_bytes(b"event-new")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof["files"]["mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"] = {
        "sha256": digest(map_path), "bytes": map_path.stat().st_size
    }
    proof["files"]["mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua"] = {
        "sha256": digest(event_path), "bytes": event_path.stat().st_size
    }
    proof["router"] = {"test": "new"}
    proof["state"] = {"test": "new"}
    proof_path.write_text(json.dumps(proof, sort_keys=True), encoding="utf-8")
    raise SystemExit(0)

if "--check" in sys.argv:
    if mode == "check_fail":
        print("INJECTED_CHECK_FAILURE")
        raise SystemExit(23)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    expected = (
        ("mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua", map_path),
        ("mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua", event_path),
    )
    for key, path in expected:
        entry = proof["files"][key]
        if entry["sha256"] != digest(path) or entry["bytes"] != path.stat().st_size:
            raise SystemExit(24)
    print("FAKE_RAVEN_PREPARE_CHECK_PASSED")
    raise SystemExit(0)

raise SystemExit(25)
'@
    Set-Content -LiteralPath (Join-Path $tools 'prepare-all-ravens-delivery-candidate.py') -Value $fakePrepare -Encoding UTF8

    [IO.File]::WriteAllBytes($map, [Text.Encoding]::UTF8.GetBytes('map-before'))
    [IO.File]::WriteAllBytes($events, [Text.Encoding]::UTF8.GetBytes('event-before'))
    $proofObject = [ordered]@{
        files = [ordered]@{
            'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua' = [ordered]@{
                sha256 = Get-Hash $map
                bytes = (Get-Item -LiteralPath $map).Length
            }
            'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua' = [ordered]@{
                sha256 = Get-Hash $events
                bytes = (Get-Item -LiteralPath $events).Length
            }
        }
        router = [ordered]@{ test = 'old' }
        state = [ordered]@{ test = 'old' }
    }
    $proofObject | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $proof -Encoding UTF8

    Invoke-Git $work @('add','tools/v0.10.5','archive/all-ravens/all-ravens-release-candidate-offline.json') | Out-Null
    Invoke-Git $work @('commit','-m','fixture: initial Raven proof state') | Out-Null
    Invoke-Git $work @('remote','add','origin',$remote) | Out-Null
    Invoke-Git $work @('push','-u','origin','codex/all-ravens-release-candidate') | Out-Null

    return [pscustomobject]@{
        Work = $work
        Remote = $remote
        Wrapper = Join-Path $tools 'refresh-raven-delivery-proof-and-push.ps1'
        Map = $map
        Events = $events
        Proof = $proof
        InitialHead = (& git -C $work rev-parse HEAD).Trim()
        MapBefore = [IO.File]::ReadAllBytes($map)
        EventsBefore = [IO.File]::ReadAllBytes($events)
        ProofBefore = [IO.File]::ReadAllBytes($proof)
    }
}

function Invoke-Wrapper([object]$Fixture, [string]$Mode) {
    $previousMode = $env:RAVEN_WRAPPER_TEST_MODE
    try {
        $env:RAVEN_WRAPPER_TEST_MODE = $Mode
        Push-Location $Fixture.Work
        try {
            & pwsh -NoProfile -ExecutionPolicy Bypass -File $Fixture.Wrapper
            return $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
    finally {
        $env:RAVEN_WRAPPER_TEST_MODE = $previousMode
    }
}

function Assert-BaselineBytes([object]$Fixture) {
    Assert-True (
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($Fixture.Map)) -eq
        [Convert]::ToBase64String($Fixture.MapBefore)
    ) 'mapmenu.lua did not return to baseline.'
    Assert-True (
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($Fixture.Events)) -eq
        [Convert]::ToBase64String($Fixture.EventsBefore)
    ) 'precisionchallenge.lua did not return to baseline.'
    Assert-True (
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($Fixture.Proof)) -eq
        [Convert]::ToBase64String($Fixture.ProofBefore)
    ) 'proof JSON did not return to baseline.'
}

function Assert-TrackedClean([object]$Fixture) {
    $status = @(& git -C $Fixture.Work status --porcelain --untracked-files=no)
    Assert-True ($status.Count -eq 0) ("Tracked repo not clean: " + ($status -join '; '))
    $cached = @(& git -C $Fixture.Work diff --cached --name-only)
    Assert-True ($cached.Count -eq 0) ("Index not clean: " + ($cached -join '; '))
}

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')
$root = Join-Path $tempBase ('completionist-raven-proof-wrapper-' + [Guid]::NewGuid().ToString('N'))

try {
    # Scenario 1: generated files/proof changed, then verification fails.
    $checkFail = New-TestRepo (Join-Path $root 'check-fail')
    $exitCode = Invoke-Wrapper $checkFail 'check_fail'
    Assert-True ($exitCode -ne 0) 'Injected verification failure unexpectedly passed.'
    Assert-BaselineBytes $checkFail
    Assert-TrackedClean $checkFail
    $failureHead = (& git -C $checkFail.Work rev-parse HEAD).Trim()
    Assert-True ($failureHead -ne $checkFail.InitialHead) 'Failure evidence was not committed.'
    $remoteFailureHead = (& git --git-dir=$($checkFail.Remote) rev-parse refs/heads/codex/all-ravens-release-candidate).Trim()
    Assert-True ($remoteFailureHead -eq $failureHead) 'Failure evidence was not pushed.'

    # Scenario 2: both success and failure commits are blocked by a hook.
    $commitFail = New-TestRepo (Join-Path $root 'commit-fail')
    $hook = Join-Path $commitFail.Work '.git\hooks\pre-commit'
    @('#!/bin/sh','exit 1') | Set-Content -LiteralPath $hook -Encoding ascii
    $exitCode = Invoke-Wrapper $commitFail 'success'
    Assert-True ($exitCode -ne 0) 'Blocked commit unexpectedly passed.'
    Assert-BaselineBytes $commitFail
    Assert-TrackedClean $commitFail
    $commitFailHead = (& git -C $commitFail.Work rev-parse HEAD).Trim()
    Assert-True ($commitFailHead -eq $commitFail.InitialHead) 'Blocked commit moved HEAD.'

    # Scenario 3: commit succeeds but push is refused. Preserve the valid commit.
    $pushFail = New-TestRepo (Join-Path $root 'push-fail')
    $prePush = Join-Path $pushFail.Work '.git\hooks\pre-push'
    @('#!/bin/sh','exit 1') | Set-Content -LiteralPath $prePush -Encoding ascii
    $exitCode = Invoke-Wrapper $pushFail 'success'
    Assert-True ($exitCode -ne 0) 'Blocked push unexpectedly passed.'
    $localHead = (& git -C $pushFail.Work rev-parse HEAD).Trim()
    $remoteHead = (& git --git-dir=$($pushFail.Remote) rev-parse refs/heads/codex/all-ravens-release-candidate).Trim()
    Assert-True ($localHead -ne $pushFail.InitialHead) 'Valid refresh commit was not preserved.'
    Assert-True ($remoteHead -eq $pushFail.InitialHead) 'Pre-push refusal unexpectedly moved remote.'
    Assert-True (([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($pushFail.Map))) -eq 'map-new') 'Preserved commit lost refreshed map candidate.'
    Assert-True (([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($pushFail.Events))) -eq 'event-new') 'Preserved commit lost refreshed event candidate.'
    Assert-TrackedClean $pushFail

    Write-Host 'RAVEN_PROOF_REFRESH_WRAPPER_TESTS_PASSED rollback_after_check_failure=true blocked_commit_cleanup=true push_failure_commit_preserved=true'
}
finally {
    $resolved = [IO.Path]::GetFullPath($root)
    if ($resolved.StartsWith(
        $tempBase + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
