param(
    [ValidateSet('Install','Remove')]
    [string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-hud-research'
$ExpectedSourcePerm = '85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5'
$ExpectedUiDcb = '40eb9f6fc934b0fb34b568a3fa74bac24b19e6259b2dc5749f26a8cd90865d36'
$ExpectedUiWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$ExpectedCoords = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
$ExpectedGraph = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'
$ExpectedNewName = 'COMPASS_INWORLD_COMPLETIONIST_RAVEN'
$ExpectedNewUid = '21DC5A7D4AD17628'
$ExpectedRavenHud = '45E5C7943749F81C'
$ExpectedDockHud = '82F0296748C7393D'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-carrier-stock-art-control'
$Candidate = Join-Path $StateDir 'candidate\wad_r_perm.dcb'
$Report = Join-Path $StateDir 'offline-report.json'
$RuntimeDir = Join-Path $StateDir 'runtime'
$ManifestPath = Join-Path $RuntimeDir 'active.json'
$BackupPath = Join-Path $RuntimeDir 'wad_r_perm.custom-art.before'
$Builder = Join-Path $PSScriptRoot 'build-raven-inworld-carrier-stock-art-control.py'

$Perm = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_perm.dcb'
$UiDcb = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
$UiWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$Coords = Join-Path $GameRoot 'exec\dc\pc_le\mapcoords.dcb'
$Graph = Join-Path $GameRoot 'exec\dc\pc_le\compassgraph.dcb'
$MapMenu = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'

$UnderlyingCarrierManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-carrier\runtime\active.json'
$SingleActiveManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-single-active-compass-control\active.json'
$CustomClassManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-native-custom-class-control\active.json'
$GopoolManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-compass-hud-gopool-registration\active-install.json'

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash).ToLowerInvariant()
}

function Assert-GameClosed {
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
    })
    if ($running.Count -gt 0) { throw 'God of War is running. Close it before changing wad_r_perm.dcb.' }
}

function Assert-Branch {
    $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
        throw "Expected Git branch '$ExpectedBranch', found '$branch'."
    }
}

function Write-JsonFile([object]$Object, [string]$Path) {
    $json = $Object | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Assert-ProvenCompanions {
    $checks = @(
        @($UiDcb, $ExpectedUiDcb, 'wad_r_ui.dcb'),
        @($UiWad, $ExpectedUiWad, 'r_ui.wad'),
        @($Coords, $ExpectedCoords, 'mapcoords.dcb'),
        @($Graph, $ExpectedGraph, 'compassgraph.dcb')
    )
    foreach ($row in $checks) {
        $actual = Get-Sha256 $row[0]
        if ($actual -ne $row[1]) {
            throw "$($row[2]) is not the proven Raven baseline. Expected $($row[1]), got $actual"
        }
    }

    foreach ($p in @($UnderlyingCarrierManifest, $SingleActiveManifest, $CustomClassManifest, $GopoolManifest)) {
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required active manifest missing: $p" }
    }
    $under = Get-Content -LiteralPath $UnderlyingCarrierManifest -Raw | ConvertFrom-Json
    if ([string]$under.kind -ne 'completionist-v104-raven-inworld-carrier-runtime' -or $under.schema -ne 1 -or
        ([string]$under.wad_r_perm_after_sha256).ToLowerInvariant() -ne $ExpectedSourcePerm) {
        throw 'Underlying dedicated Raven in-world carrier manifest is not the expected active custom-art candidate.'
    }
    $single = Get-Content -LiteralPath $SingleActiveManifest -Raw | ConvertFrom-Json
    if ([string]$single.kind -ne 'completionist-v104-raven-single-active-compass-control' -or $single.schema -ne 3) {
        throw 'Raven single-target control is not the proven schema-3 version.'
    }
    if ((Get-Sha256 $MapMenu) -ne ([string]$single.map_after_sha256).ToLowerInvariant()) {
        throw 'Live mapmenu.lua does not match the proven schema-3 single-target control.'
    }
}

Assert-GameClosed
Assert-Branch
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Write-Host 'Raven in-world stock-art control is already removed.'
        exit 0
    }
    if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
        throw "Active stock-art control has no exact custom-art backup: $BackupPath"
    }
    $m = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ([string]$m.kind -ne 'completionist-v104-raven-inworld-stock-art-control' -or $m.schema -ne 1) {
        throw 'Unexpected Raven in-world stock-art manifest.'
    }
    $after = ([string]$m.wad_r_perm_after_sha256).ToLowerInvariant()
    $live = Get-Sha256 $Perm
    if ($live -ne $after -and $live -ne $ExpectedSourcePerm) {
        throw "Live wad_r_perm.dcb is neither the stock-art control nor underlying custom-art candidate: $live"
    }
    if ((Get-Sha256 $BackupPath) -ne $ExpectedSourcePerm) {
        throw 'Stock-art control backup is not the exact custom-art carrier candidate.'
    }
    if ($live -eq $after) {
        Copy-Item -LiteralPath $BackupPath -Destination $Perm -Force
    }
    if ((Get-Sha256 $Perm) -ne $ExpectedSourcePerm) {
        throw 'Stock-art control rollback verification failed.'
    }
    $removed = Join-Path $RuntimeDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $ManifestPath -Destination $removed -Force
    Write-Host 'RAVEN_INWORLD_STOCK_ART_CONTROL_REMOVED'
    Write-Host "  restored custom-art carrier SHA256: $ExpectedSourcePerm"
    Write-Host '  other game files touched: false'
    exit 0
}

if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
    throw "Raven in-world stock-art control is already installed: $ManifestPath"
}
Assert-ProvenCompanions
if ((Get-Sha256 $Perm) -ne $ExpectedSourcePerm) {
    throw "Live wad_r_perm.dcb is not the installed custom-art carrier candidate. Expected $ExpectedSourcePerm, got $(Get-Sha256 $Perm)"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
if (-not (Test-Path -LiteralPath $Builder -PathType Leaf)) { throw "Missing builder: $Builder" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Candidate) | Out-Null

& $python.Source $Builder --input $Perm --output $Candidate --report $Report
if ($LASTEXITCODE -ne 0) { throw 'Offline Raven in-world stock-art control build failed.' }
$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_INWORLD_STOCK_ART_CONTROL_BUILT' -or
    ([string]$proof.source_sha256).ToLowerInvariant() -ne $ExpectedSourcePerm -or
    [string]$proof.new_export -ne $ExpectedNewName -or
    ([string]$proof.new_export_uid).ToUpperInvariant() -ne $ExpectedNewUid -or
    ([string]$proof.carrier_before_icon_hash).ToUpperInvariant() -ne $ExpectedRavenHud -or
    ([string]$proof.carrier_after_icon_hash).ToUpperInvariant() -ne $ExpectedDockHud -or
    $proof.completionist_raven_inworld_binding_unchanged -ne $true -or
    $proof.carrier_after_byte_identical_to_stock_dock -ne $true -or
    $proof.changes_confined_to_new_carrier_icon_qword -ne $true -or
    $proof.export_table_byte_identical -ne $true -or
    $proof.relocation_table_semantics_identical -ne $true -or
    $proof.game_files_written -ne $false) {
    throw 'Offline Raven in-world stock-art A/B contract failed.'
}
$candidateSha = ([string]$proof.candidate_sha256).ToLowerInvariant()
if ((Get-Sha256 $Candidate) -ne $candidateSha) { throw 'Candidate hash mismatch against report.' }
if ((Get-Sha256 $Perm) -ne $ExpectedSourcePerm) { throw 'Live wad_r_perm.dcb changed during offline build.' }

Copy-Item -LiteralPath $Perm -Destination $BackupPath -Force
if ((Get-Sha256 $BackupPath) -ne $ExpectedSourcePerm) { throw 'Exact custom-art candidate backup verification failed.' }

$m = [ordered]@{
    kind = 'completionist-v104-raven-inworld-stock-art-control'
    schema = 1
    purpose = 'Causal A/B: keep the new independent type-0x129 export and Raven binding, but make only that clone use stock Dock art.'
    installed_utc = [DateTime]::UtcNow.ToString('o')
    wad_r_perm_before_sha256 = $ExpectedSourcePerm
    wad_r_perm_after_sha256 = $candidateSha
    new_export = $ExpectedNewName
    new_export_uid = $ExpectedNewUid
    completionist_raven_inworld_binding = $ExpectedNewUid
    carrier_icon_before = $ExpectedRavenHud
    carrier_icon_after = $ExpectedDockHud
    only_delta = 'new carrier IconName qword'
    underlying_carrier_manifest = $UnderlyingCarrierManifest
    backup = $BackupPath
    candidate = $Candidate
    report = $Report
    saves_progression_marker_state_touched = $false
}
Write-JsonFile $m $ManifestPath

try {
    Copy-Item -LiteralPath $Candidate -Destination $Perm -Force
    if ((Get-Sha256 $Perm) -ne $candidateSha) { throw 'Installed stock-art control hash mismatch.' }
    Assert-ProvenCompanions
} catch {
    Copy-Item -LiteralPath $BackupPath -Destination $Perm -Force
    if ((Get-Sha256 $Perm) -ne $ExpectedSourcePerm) {
        throw 'Stock-art install failed and exact custom-art rollback also failed.'
    }
    Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host ''
Write-Host 'RAVEN_INWORLD_STOCK_ART_CONTROL_INSTALLED'
Write-Host "  wad_r_perm.dcb: $ExpectedSourcePerm -> $candidateSha"
Write-Host "  Raven InWorld binding remains: $ExpectedNewUid"
Write-Host "  new carrier IconName only: $ExpectedRavenHud -> $ExpectedDockHud"
Write-Host '  new export/root/UID preserved: true'
Write-Host '  export/relocation semantics preserved: true'
Write-Host '  other game files touched: false'
Write-Host '  saves/progression/marker state touched: false'
Write-Host ''
Write-Host 'Runtime interpretation:'
Write-Host '  BOAT appears above Raven => new type-0x129 export resolves; custom Raven art path is the remaining problem.'
Write-Host '  NO in-world marker => new type-0x129 export itself is not resolving/registered.'
Write-Host ''
Write-Host ("Rollback to current custom-art carrier: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
