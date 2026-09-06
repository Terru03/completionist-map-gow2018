param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$source = Join-Path $GameRoot ('mods\lua_source\' + $relative)
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v05-backup'

if (-not (Test-Path $source)) {
    throw "Missing loader source file: $source"
}

$text = [IO.File]::ReadAllText($source)

if ($text.Contains('[CompletionistMap v0.5]')) {
    Write-Host 'v0.5 diagnostic is already present in lua_source; refusing to patch the source copy.'
    exit 1
}

$injection = @'
function OnStart(level, obj)
  local completionistMapV05OK, completionistMapV05Err = pcall(function()
    local completionistMapV05Pos = thisObj:GetWorldPosition()
    local completionistMapV05ID = "<unavailable>"
    local completionistMapV05IDOK, completionistMapV05IDValue = pcall(function()
      return thisObj:GetID()
    end)
    if completionistMapV05IDOK then
      completionistMapV05ID = tostring(completionistMapV05IDValue)
    end
    print("[CompletionistMap v0.5] RAVEN" ..
      " level=" .. tostring(level and level.Name or "") ..
      " object=" .. tostring(thisObj:GetName()) ..
      " id=" .. completionistMapV05ID ..
      " regionQuest=" .. tostring(regionSummaryQuest) ..
      " killed=" .. tostring(ravenKilled) ..
      " x=" .. tostring(completionistMapV05Pos.x) ..
      " y=" .. tostring(completionistMapV05Pos.y) ..
      " z=" .. tostring(completionistMapV05Pos.z))
  end)
  if not completionistMapV05OK then
    print("[CompletionistMap v0.5] RAVEN_ERROR error=" .. tostring(completionistMapV05Err))
  end
'@

$pattern = 'function OnStart\(level, obj\)\r?\n'
$regex = [regex]::new($pattern)
$match = $regex.Match($text)
if (-not $match.Success) {
    throw 'Could not find the expected OnStart(level, obj) function in precisionchallenge.lua.'
}

$patched = $regex.Replace($text, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $injection }, 1)

$destDir = Split-Path $dest -Parent
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

if (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)
    if ($existing.Contains('[CompletionistMap v0.5]')) {
        Write-Host 'Completionist Map v0.5 raven diagnostic is already installed.'
        exit 0
    }
    Copy-Item $dest $backup -Force
    Write-Host "Backed up existing override to: $backup"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($dest, $patched, $utf8NoBom)

Write-Host 'Completionist Map v0.5 raven diagnostic installed.'
Write-Host "Override: $dest"
Write-Host 'Launch the game, load a Midgard save, wait around 15 seconds, then quit normally.'
