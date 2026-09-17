param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = 'codex/all-collectibles-production-research'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDirRel = 'archive/field-logs/local-handoffs'
$logDir = Join-Path $repo $logDirRel
$logRel = "$logDirRel/raven-caption-stock-mapmenu-$stamp.txt"
$log = Join-Path $repo $logRel
$activeManifest = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction\active.json'
$relativeMapMenu = 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$expectedPristineSha = '16e13b342f3bbe98ac9b87eb34bf0115e6b04340d6e41270f38a557f2ed51493'

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repo

function Log([string]$Text) {
    $Text | Add-Content -LiteralPath $log -Encoding utf8
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Emit-Context {
    param(
        [string[]]$Lines,
        [int]$Index,
        [int]$Radius,
        [string]$Reason
    )
    $start = [Math]::Max(0, $Index - $Radius)
    $end = [Math]::Min($Lines.Count - 1, $Index + $Radius)
    Log ''
    Log ("--- CONTEXT reason={0} hit_line={1} range={2}-{3} ---" -f $Reason, ($Index + 1), ($start + 1), ($end + 1))
    for ($i = $start; $i -le $end; $i++) {
        Log ("{0,5}: {1}" -f ($i + 1), $Lines[$i])
    }
}

function Commit-Log([string]$Message) {
    & git add -- $logRel | Out-Null
    if ($LASTEXITCODE -ne 0) { return }
    & git commit -m $Message *> $null
    if ($LASTEXITCODE -eq 0) {
        & git push origin $branch *> $null
    }
}

"=== RAVEN CAPTION STOCK MAPMENU TRACE ===" | Set-Content -LiteralPath $log -Encoding utf8
Log "timestamp=$stamp"
Log "branch=$branch"
Log 'mode=read-only'
Log 'game_files_written=false'
Log 'save_or_progression_written=false'

try {
    $currentBranch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $branch) {
        throw "Expected branch '$branch', got '$currentBranch'."
    }
    $dirty = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Git status.' }
    if ($dirty) { throw 'Tracked checkout is dirty; refusing read-only evidence run.' }

    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) {
        throw "Missing active Raven transaction manifest: $activeManifest"
    }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ([string]$manifest.status -ne 'installed') {
        throw "Expected active Raven transaction status installed, got '$($manifest.status)'."
    }
    if (@($manifest.entries).Count -ne 5) {
        throw "Expected five active Raven transaction entries, got $(@($manifest.entries).Count)."
    }

    $transactionRoot = [string]$manifest.transaction_root
    $backupMapMenu = Join-Path (Join-Path $transactionRoot 'backup\game-root') $relativeMapMenu
    $liveMapMenu = Join-Path $GameRoot $relativeMapMenu
    if (-not (Test-Path -LiteralPath $backupMapMenu -PathType Leaf)) {
        throw "Missing pristine transaction backup mapmenu.lua: $backupMapMenu"
    }
    if (-not (Test-Path -LiteralPath $liveMapMenu -PathType Leaf)) {
        throw "Missing installed mapmenu.lua: $liveMapMenu"
    }

    $backupSha = Get-Sha256 $backupMapMenu
    $liveSha = Get-Sha256 $liveMapMenu
    if ($backupSha -ne $expectedPristineSha) {
        throw "Pristine mapmenu SHA differs. Expected $expectedPristineSha, got $backupSha."
    }

    Log "transaction_id=$($manifest.transaction_id)"
    Log "transaction_status=$($manifest.status)"
    Log "transaction_root=$transactionRoot"
    Log "pristine_mapmenu=$backupMapMenu"
    Log "pristine_mapmenu_sha256=$backupSha"
    Log "installed_mapmenu=$liveMapMenu"
    Log "installed_mapmenu_sha256=$liveSha"
    Log 'pristine_sha_verified=true'

    $lines = [IO.File]::ReadAllLines($backupMapMenu)
    Log "pristine_line_count=$($lines.Count)"

    $anchors = @(
        'function MapOn:MapCollisionChangeHandler',
        'MapCollisionChangeHandler',
        'function MapOn:GetShowOnCompassPrompt',
        'GetShowOnCompassPrompt',
        'function MapOn:ShowOnCompass',
        'ShowOnCompass',
        'CreateMarkerIcon',
        'GetMarkerInfo',
        'currMarkerID',
        'currShownMarkerID',
        'mapIconCollision'
    )

    $emitted = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($anchor in $anchors) {
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i].IndexOf($anchor, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $key = "$i|$anchor"
                if ($emitted.Add($key)) {
                    Emit-Context -Lines $lines -Index $i -Radius 18 -Reason $anchor
                }
            }
        }
    }

    Log ''
    Log '=== TEXT / LABEL / LOCALIZATION CALL INVENTORY ==='
    $callRegex = '(?i)(SetText|SetString|SetLabel|SetMessage|SetTitle|GetLAMSMsg|LAMS|CreateMarkerIcon|GetMarkerInfo|markerName|displayName|currMarker|mapIconCollision)'
    $callCount = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $callRegex) {
            Log ("{0,5}: {1}" -f ($i + 1), $lines[$i])
            $callCount++
        }
    }
    Log "inventory_match_count=$callCount"

    Log ''
    Log '=== UI TEXT ASSIGNMENT CONTEXTS ==='
    $setterRegex = '(?i)(SetText|SetString|SetLabel|SetMessage|SetTitle|GetLAMSMsg)'
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $setterRegex) {
            Emit-Context -Lines $lines -Index $i -Radius 8 -Reason 'text/localization setter'
        }
    }

    $liveLines = [IO.File]::ReadAllLines($liveMapMenu)
    Log ''
    Log '=== INSTALLED COMPLETIONIST TAIL SIGNALS ==='
    $tailStart = [Math]::Max(0, $liveLines.Count - 650)
    for ($i = $tailStart; $i -lt $liveLines.Count; $i++) {
        if ($liveLines[$i] -match '(?i)(CompletionistMap|CreateMarkerIcon|markerLabel|MapCollisionChangeHandler|GetShowOnCompassPrompt|currMarkerID|mapIconCollision)') {
            Log ("{0,5}: {1}" -f ($i + 1), $liveLines[$i])
        }
    }

    Log ''
    Log '=== RESULT ==='
    Log 'RESULT=PASS'
    Log 'ANALYSIS_ONLY=true'
    Log 'NEXT=derive exact stock selected-marker caption data path before modifying runtime'
    Commit-Log -Message "logs: trace stock Raven caption path $stamp"
}
catch {
    Log ''
    Log '=== RESULT ==='
    Log 'RESULT=FAILED'
    Log "ERROR=$($_.Exception.Message)"
    Log 'ANALYSIS_ONLY=true'
    Commit-Log -Message "logs: capture failed stock Raven caption trace $stamp"
}

Write-Host 'DONE'
