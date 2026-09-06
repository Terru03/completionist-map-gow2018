param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v051-backup'

function Test-PrecisionChallengeSource([string]$Text) {
    $required = @(
        'local ravenKilled = false',
        'function OnStart(level, obj)',
        'function OnHitByWeapon(level, obj, attacker, weapon)',
        'Quest_Labor_KillRavens',
        'regionSummaryQuest = thisObj:FindLuaTableAttribute("regionSummaryQuest")'
    )

    foreach ($needle in $required) {
        if (-not $Text.Contains($needle)) {
            return $false
        }
    }

    return $true
}

$localCandidates = @(
    (Join-Path $GameRoot ('mods\lua_source\' + $relative)),
    (Join-Path $GameRoot ('mods\lua\' + $relative))
)

$source = $null
$text = $null

foreach ($candidate in $localCandidates) {
    if (Test-Path $candidate) {
        $candidateText = [IO.File]::ReadAllText($candidate)

        if ($candidateText.Contains('[CompletionistMap v0.5.1]')) {
            Write-Host 'Completionist Map v0.5.1 raven diagnostic is already installed.'
            exit 0
        }

        if (Test-PrecisionChallengeSource $candidateText) {
            $source = $candidate
            $text = $candidateText
            break
        }
    }
}

if ($null -eq $text) {
    $pinnedCommit = '1958cf514d56e1278f02570c876ad127462b3551'
    $sourceUrl = "https://raw.githubusercontent.com/MorseTheCode/GoWLUA/$pinnedCommit/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua"
    $downloadedSource = Join-Path $env:TEMP 'completionist-map-v051-precisionchallenge.lua'

    Write-Host 'Local precisionchallenge.lua was not found.'
    Write-Host 'Downloading pinned reference source from MorseTheCode/GoWLUA...'

    Invoke-WebRequest -Uri $sourceUrl -UseBasicParsing -OutFile $downloadedSource
    $text = [IO.File]::ReadAllText($downloadedSource)

    if (-not (Test-PrecisionChallengeSource $text)) {
        throw 'Downloaded precisionchallenge.lua does not match the expected raven-script structure. Nothing was installed.'
    }

    $source = $downloadedSource
    Write-Host "Validated pinned reference source: $pinnedCommit"
} else {
    Write-Host "Using local source: $source"
}

$injection = @'
function OnStart(level, obj)
  local completionistMapV051OK, completionistMapV051Err = pcall(function()
    local completionistMapV051Pos = thisObj:GetWorldPosition()
    local completionistMapV051ID = "<unavailable>"
    local completionistMapV051IDOK, completionistMapV051IDValue = pcall(function()
      return thisObj:GetID()
    end)
    if completionistMapV051IDOK then
      completionistMapV051ID = tostring(completionistMapV051IDValue)
    end
    print("[CompletionistMap v0.5.1] RAVEN" ..
      " level=" .. tostring(level and level.Name or "") ..
      " object=" .. tostring(thisObj:GetName()) ..
      " id=" .. completionistMapV051ID ..
      " regionQuest=" .. tostring(regionSummaryQuest) ..
      " killed=" .. tostring(ravenKilled) ..
      " x=" .. tostring(completionistMapV051Pos.x) ..
      " y=" .. tostring(completionistMapV051Pos.y) ..
      " z=" .. tostring(completionistMapV051Pos.z))
  end)
  if not completionistMapV051OK then
    print("[CompletionistMap v0.5.1] RAVEN_ERROR error=" .. tostring(completionistMapV051Err))
  end
'@

$pattern = 'function OnStart\(level, obj\)\r?\n'
$regex = [regex]::new($pattern)
$match = $regex.Match($text)

if (-not $match.Success) {
    throw 'Could not find the expected OnStart(level, obj) function. Nothing was installed.'
}

$patched = $regex.Replace(
    $text,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $injection },
    1
)

$destDir = Split-Path $dest -Parent
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

if (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)

    if ($existing.Contains('[CompletionistMap v0.5.1]')) {
        Write-Host 'Completionist Map v0.5.1 raven diagnostic is already installed.'
        exit 0
    }

    Copy-Item $dest $backup -Force
    Write-Host "Backed up existing override to: $backup"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($dest, $patched, $utf8NoBom)

Write-Host ''
Write-Host 'Completionist Map v0.5.1 raven diagnostic installed successfully.'
Write-Host "Override: $dest"
Write-Host 'Launch God of War, load the Midgard save, wait about 15 seconds, then quit normally.'
