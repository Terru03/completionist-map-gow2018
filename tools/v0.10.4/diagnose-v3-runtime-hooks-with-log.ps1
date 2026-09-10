param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Repo = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Repo)) {
    throw 'Run this from inside the completionist-map-gow2018 repository.'
}
Set-Location $Repo

$Branch = 'codex/v104-raven-uid-compass-lifecycle-v3'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v3-hook-diagnostic-$Stamp"
$LogDir = Join-Path $Repo $LogRel
$ConsoleLog = Join-Path $LogDir 'console-log.txt'
$Summary = Join-Path $LogDir 'result.txt'
$MapExtract = Join-Path $LogDir 'mapmenu-hook-context.txt'
$GameplayExtract = Join-Path $LogDir 'precisionchallenge-hook-context.txt'
$LoaderExtract = Join-Path $LogDir 'loader-hook-context.txt'
$Hashes = Join-Path $LogDir 'installed-file-hashes.txt'

$MapMenu = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$Gameplay = Join-Path $GameRoot 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$LoaderLog = Join-Path $GameRoot 'mods\loader_log.txt'

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Succeeded = $false
$FailureText = ''

function Write-Log([string]$Text = '') {
    $Text | Tee-Object -FilePath $ConsoleLog -Append | Out-Host
}

function Get-ContextExtract {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string[]]$Patterns,
        [Parameter(Mandatory=$true)][string]$Destination,
        [int]$Radius = 12
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing diagnostic source: $Path"
    }

    $lines = [IO.File]::ReadAllLines($Path)
    $wanted = New-Object 'System.Collections.Generic.HashSet[int]'
    for ($i = 0; $i -lt $lines.Length; $i++) {
        foreach ($pattern in $Patterns) {
            if ($lines[$i] -match $pattern) {
                $start = [Math]::Max(0, $i - $Radius)
                $end = [Math]::Min($lines.Length - 1, $i + $Radius)
                for ($j = $start; $j -le $end; $j++) { [void]$wanted.Add($j) }
                break
            }
        }
    }

    $ordered = @($wanted | Sort-Object)
    $out = New-Object System.Collections.Generic.List[string]
    $previous = -2
    foreach ($index in $ordered) {
        if ($previous -ge 0 -and $index -gt ($previous + 1)) {
            $out.Add('---')
        }
        $out.Add(('{0,6}: {1}' -f ($index + 1), $lines[$index]))
        $previous = $index
    }
    if ($out.Count -eq 0) { $out.Add('NO_MATCHES') }
    [IO.File]::WriteAllLines($Destination, $out, (New-Object System.Text.UTF8Encoding($false)))
}

try {
    Write-Log 'COMPLETIONIST V3 RUNTIME HOOK DIAGNOSTIC'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"

    $current = (& git branch --show-current).Trim()
    if ($current -ne $Branch) { throw "Expected branch '$Branch', got '$current'." }

    if (Get-Process -Name 'GoW','GodOfWar' -ErrorAction SilentlyContinue) {
        throw 'Close God of War before running the read-only diagnostic.'
    }

    & git diff --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes exist.' }
    & git diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Staged changes exist.' }

    Write-Log "HEAD=$((& git rev-parse HEAD).Trim())"

    foreach ($path in @($MapMenu,$Gameplay,$LoaderLog)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $item = Get-Item -LiteralPath $path
            $sha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
            "$($path.Substring($GameRoot.Length).TrimStart('\')) bytes=$($item.Length) sha256=$sha" | Add-Content -LiteralPath $Hashes -Encoding UTF8
        } else {
            "$($path.Substring($GameRoot.Length).TrimStart('\')) MISSING" | Add-Content -LiteralPath $Hashes -Encoding UTF8
        }
    }

    Get-ContextExtract -Path $MapMenu -Destination $MapExtract -Radius 16 -Patterns @(
        'v0\.10\.4-single-active-v3',
        'uid-lifecycle-v3',
        'CompletionistMapV104UidAwareRavenCompassRouting',
        'CompletionistMapV104SelectedRavenIdentity',
        'CompletionistMapV100_CreateMapPin',
        'completionistSharedLoaderTwinGO',
        'function\s+MapOn:GetShowOnCompassPrompt',
        'function\s+MapOn:ShowOnCompass',
        'function\s+MapOn:Update',
        'RAVEN_SHOW',
        'HIDE_STOCK',
        'mapIconCollision'
    )

    Get-ContextExtract -Path $Gameplay -Destination $GameplayExtract -Radius 18 -Patterns @(
        'CompletionistMapV100TargetRavenKilled',
        'CompletionistMapV100_IsTargetRaven',
        'CompletionistMapV104ObserveRavenCompletion',
        'uid-lifecycle-v3',
        'ravenKilled',
        'function\s+OnHitByWeapon',
        'function\s+OnRestoreCheckpoint',
        'function\s+OnStart'
    )

    if (Test-Path -LiteralPath $LoaderLog -PathType Leaf) {
        $all = Get-Content -LiteralPath $LoaderLog
        $relevant = @($all | Where-Object {
            $_ -match 'CompletionistMap v0\.10\.4-single-active-v3|CompletionistMap v0\.10\.4-uid-lifecycle-v3|CompletionistMap shared-loader-twin|RAVEN_STATE|CompletionistMapV104|OnHitByWeapon'
        })
        $tail = @($relevant | Select-Object -Last 300)
        $tail | Set-Content -LiteralPath $LoaderExtract -Encoding UTF8
    } else {
        'loader_log.txt missing' | Set-Content -LiteralPath $LoaderExtract -Encoding UTF8
    }

    Write-Log "map_context=$MapExtract"
    Write-Log "gameplay_context=$GameplayExtract"
    Write-Log "loader_context=$LoaderExtract"
    Write-Log 'game_files_written=false'
    Write-Log 'RESULT: PASS'
    $Succeeded = $true
}
catch {
    $FailureText = ($_ | Out-String).Trim()
    Write-Log 'RESULT: FAIL'
    Write-Log $FailureText
}
finally {
    @(
        "result=$(if ($Succeeded) { 'PASS' } else { 'FAIL' })",
        "time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "game_root=$GameRoot",
        'game_files_written=false',
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    try {
        Set-Location $Repo
        & git add -- $LogRel
        if ($LASTEXITCODE -ne 0) { throw 'Could not stage diagnostic log.' }
        & git diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            $message = if ($Succeeded) { 'Archive v3 runtime hook diagnostic' } else { 'Archive v3 runtime hook diagnostic failure' }
            & git commit -m $message | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not commit diagnostic log.' }
            & git push origin HEAD | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not push diagnostic log.' }
        }
    }
    catch {
        Write-Warning "Diagnostic publication failed: $($_.Exception.Message)"
        Write-Warning "Local diagnostic remains at: $LogDir"
    }
}

if (-not $Succeeded) {
    throw "V3 runtime hook diagnostic failed. Full log was archived under $LogRel when publication succeeded."
}

Write-Host "Done. Read-only diagnostic pushed under $LogRel."
