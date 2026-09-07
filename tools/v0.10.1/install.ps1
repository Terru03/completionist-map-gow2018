param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$IconRoot = Join-Path $GameRoot 'mods\completionist-map\icons'
$IconConceptDir = Join-Path $IconRoot 'concepts'
$IconGeneratedDir = Join-Path $IconRoot 'generated'
$IconManifestPath = Join-Path $IconRoot 'manifest.json'

$CompletionistIconFiles = [ordered]@{
    'raven' = 'raven_concept_master.png'
    'nornir_chest' = 'nornir_chest_concept_master.png'
    'nornir_seal' = 'nornir_seal_concept_master.png'
    'nornir_bell' = 'nornir_bell_concept_master.png'
    'nornir_mechanism' = 'nornir_mechanism_concept_master.png'
    'lore_marker' = 'lore_marker_concept_master.png'
    'artefact' = 'artefact_concept_master.png'
    'legendary_chest' = 'legendary_chest_concept_master.png'
    'remaining_collectible' = 'remaining_collectible_concept_master.png'
    'player_marker' = 'player_marker_concept_master.png'
}

# v0.10.1 is network-independent. Prefer assets bundled beside install.ps1.
# When running directly from the cloned repository, fall back to repo/assets.
$IconSourceDir = Join-Path $PSScriptRoot 'assets\icons\concepts'
if (-not (Test-Path $IconSourceDir)) {
    $repoRootCandidate = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $repoAssetCandidate = Join-Path $repoRootCandidate 'assets\icons\concepts'
    if (Test-Path $repoAssetCandidate) {
        $IconSourceDir = $repoAssetCandidate
    }
}

if (-not (Test-Path $IconSourceDir)) {
    throw "Completionist icon masters were not found. Expected bundled or repository assets at: $IconSourceDir"
}

function Assert-CompletionistPng([string]$Path) {
    if (-not (Test-Path $Path)) {
        throw "Missing icon master: $Path"
    }

    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 8 -or
        $bytes[0] -ne 0x89 -or
        $bytes[1] -ne 0x50 -or
        $bytes[2] -ne 0x4E -or
        $bytes[3] -ne 0x47 -or
        $bytes[4] -ne 0x0D -or
        $bytes[5] -ne 0x0A -or
        $bytes[6] -ne 0x1A -or
        $bytes[7] -ne 0x0A) {
        throw "Icon master is not a valid PNG: $Path"
    }
}
function Export-CompletionistSquarePng(
    [string]$Source,
    [string]$Destination,
    [int]$Size
) {
    $src = [Drawing.Image]::FromFile($Source)
    try {
        $bmp = New-Object Drawing.Bitmap(
            $Size,
            $Size,
            [Drawing.Imaging.PixelFormat]::Format32bppArgb
        )
        try {
            $g = [Drawing.Graphics]::FromImage($bmp)
            try {
                $g.Clear([Drawing.Color]::Transparent)
                $g.CompositingMode = [Drawing.Drawing2D.CompositingMode]::SourceCopy
                $g.CompositingQuality = [Drawing.Drawing2D.CompositingQuality]::HighQuality
                $g.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::HighQuality
                $g.PixelOffsetMode = [Drawing.Drawing2D.PixelOffsetMode]::HighQuality

                $margin = [Math]::Max(1, [Math]::Round($Size * 0.04))
                $usable = $Size - 2 * $margin
                $scale = [Math]::Min(
                    $usable / [double]$src.Width,
                    $usable / [double]$src.Height
                )
                $w = [Math]::Max(1, [Math]::Round($src.Width * $scale))
                $h = [Math]::Max(1, [Math]::Round($src.Height * $scale))
                $x = [Math]::Floor(($Size - $w) / 2)
                $y = [Math]::Floor(($Size - $h) / 2)

                $g.DrawImage($src, $x, $y, $w, $h)
            }
            finally {
                $g.Dispose()
            }

            $parent = Split-Path $Destination -Parent
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
            $bmp.Save($Destination, [Drawing.Imaging.ImageFormat]::Png)
        }
        finally {
            $bmp.Dispose()
        }
    }
    finally {
        $src.Dispose()
    }
}

Write-Host ''
Write-Host 'Preparing Completionist Map v0.10.1 custom icon assets...'
New-Item -ItemType Directory -Force -Path $IconConceptDir | Out-Null
New-Item -ItemType Directory -Force -Path $IconGeneratedDir | Out-Null

Add-Type -AssemblyName System.Drawing
$iconManifest = @()
$iconSizes = @(24, 32, 48, 64)

foreach ($family in $CompletionistIconFiles.Keys) {
    $fileName = $CompletionistIconFiles[$family]
    $sourceConceptPath = Join-Path $IconSourceDir $fileName
    $conceptPath = Join-Path $IconConceptDir $fileName

    Assert-CompletionistPng -Path $sourceConceptPath
    Copy-Item $sourceConceptPath $conceptPath -Force
    Assert-CompletionistPng -Path $conceptPath

    $sourceImage = [Drawing.Image]::FromFile($conceptPath)
    try {
        $sourceWidth = $sourceImage.Width
        $sourceHeight = $sourceImage.Height
    }
    finally {
        $sourceImage.Dispose()
    }

    $sha256 = (Get-FileHash $conceptPath -Algorithm SHA256).Hash
    foreach ($size in $iconSizes) {
        $sizeDir = Join-Path $IconGeneratedDir ([string]$size)
        $outPath = Join-Path $sizeDir ($family + '.png')
        Export-CompletionistSquarePng `
            -Source $conceptPath `
            -Destination $outPath `
            -Size $size
    }

    $iconManifest += [pscustomobject]@{
        family = $family
        concept = $fileName
        sourceWidth = $sourceWidth
        sourceHeight = $sourceHeight
        sha256 = $sha256
        map32 = (Join-Path (Join-Path $IconGeneratedDir '32') ($family + '.png'))
        compass24 = (Join-Path (Join-Path $IconGeneratedDir '24') ($family + '.png'))
        filter32 = (Join-Path (Join-Path $IconGeneratedDir '32') ($family + '.png'))
    }

    Write-Host ("  {0,-24} {1}x{2}  SHA256 {3}" -f `
        $family, $sourceWidth, $sourceHeight, $sha256.Substring(0, 12))
}

$iconManifest | ConvertTo-Json -Depth 4 | Set-Content -Path $IconManifestPath -Encoding UTF8
$CompletionistIconLuaRoot = ($IconGeneratedDir -replace '\\', '/')
Write-Host "Icon manifest: $IconManifestPath"
Write-Host 'Generated 24/32/48/64 px transparent production candidates for every concept master.'

$mapRelative = 'gameart\ui\scripts\inworldmenu\mapmenu.lua'
$hudRelative = 'gameart\ui\scripts\hud\mainhud.lua'
$ravenRelative = 'gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$nornirRelative = 'gameart\scripts\levels\gameplaymodules\progression\interact_chest_runic.lua'
$standardChestRelative = 'gameart\scripts\levels\gameplaymodules\progression\interact_chest_standard.lua'

$mapSource = Join-Path $GameRoot ('mods\lua_source\' + $mapRelative)
$hudSource = Join-Path $GameRoot ('mods\lua_source\' + $hudRelative)

$mapDest = Join-Path $GameRoot ('mods\lua\' + $mapRelative)
$hudDest = Join-Path $GameRoot ('mods\lua\' + $hudRelative)
$ravenDest = Join-Path $GameRoot ('mods\lua\' + $ravenRelative)
$nornirDest = Join-Path $GameRoot ('mods\lua\' + $nornirRelative)
$standardChestDest = Join-Path $GameRoot ('mods\lua\' + $standardChestRelative)

$mapBackup = $mapDest + '.pre-v100-backup'
$hudBackup = $hudDest + '.pre-v100-backup'
$ravenBackup = $ravenDest + '.pre-v100-backup'
$nornirBackup = $nornirDest + '.pre-v100-backup'
$standardChestBackup = $standardChestDest + '.pre-v100-backup'

if (-not (Test-Path $mapSource)) { throw "Missing loader source file: $mapSource" }
if (-not (Test-Path $hudSource)) { throw "Missing loader source file: $hudSource" }

$mapText = [IO.File]::ReadAllText($mapSource)
$hudText = [IO.File]::ReadAllText($hudSource)

$mapRequired = @(
    'local alwaysOnMarkerFlags = {',
    'function MapOn:GetShowOnCompassPrompt(currMenu)',
    'function MapOn:ShowOnCompass(currState)',
    'function MapOn:MapCollisionChangeHandler(currState, collisionGameObjectTable, realmName)',
    'function MapOn:Update()',
    'function MapOn:SubmenuExit(currState)',
    'function MapOn:Exit()',
    'UI.WorldUIRender(map_camera.Name)',
    'Map.SetPlayerMapMarkerToPlayerMapTransform(self.playerIconGO, "facingJoint", "arrowJoint")'
)
foreach ($needle in $mapRequired) {
    if (-not $mapText.Contains($needle)) {
        throw "mapmenu.lua does not match expected structure. Missing: $needle"
    }
}

$completionistZoomRegex =
    [regex]::new('(?m)^  MaxIn = 6,\r?\n  MaxOut = 10,')

$completionistZoomMatches =
    $completionistZoomRegex.Matches($mapText)

if ($completionistZoomMatches.Count -ne 1) {
    throw "Expected exactly one stock MapMenuCam MaxIn/MaxOut block, found $($completionistZoomMatches.Count)."
}

$mapText = $completionistZoomRegex.Replace(
    $mapText,
    "  MaxIn = 2.5,`r`n  MaxOut = 10,",
    1
)

Write-Host 'Extended map zoom enabled: MaxIn 6 -> 2.5 (~2.4x closer).'

$cursorScaleRegex =
    [regex]::new('(?m)^  CursorScale_Min = 0\.5,\r?\n  CursorScale_Max = 0\.85,')

$cursorScaleMatches = $cursorScaleRegex.Matches($mapText)
if ($cursorScaleMatches.Count -ne 1) {
    throw "Expected exactly one stock cursor-scale block, found $($cursorScaleMatches.Count)."
}

$mapText = $cursorScaleRegex.Replace(
    $mapText,
    "  CursorScale_Min = 0.05,`r`n  CursorScale_Max = 0.85,",
    1
)

Write-Host 'Zoom-aware cursor reach tightened: CursorScale_Min 0.50 -> 0.05.'

$cursorSnapRegex =
    [regex]::new('(?m)^  CursorSnap_Enabled = 1,\r?\n  CursorSnap_Strength = 2\.4,')

$cursorSnapMatches = $cursorSnapRegex.Matches($mapText)
if ($cursorSnapMatches.Count -ne 1) {
    throw "Expected exactly one stock cursor-snap block, found $($cursorSnapMatches.Count)."
}

$mapText = $cursorSnapRegex.Replace(
    $mapText,
    "  CursorSnap_Enabled = 0,`r`n  CursorSnap_Strength = 0.0,",
    1
)

Write-Host 'Map cursor magnetic snapping disabled: CursorSnap_Enabled 1 -> 0.'

$hudRequired = @(
    'local mainHUD = MainHUD.New("mainHUD", {})',
    'self.compassObj = util.GetUiObjByName("Compass")',
    'self.compassBase = util.GetUiObjByName("Compass_Base")',
    'self.compassRadius = util.GetUiObjByName("Compass_Radius")',
    'function MainHUD:SetRagePrompts()'
)
foreach ($needle in $hudRequired) {
    if (-not $hudText.Contains($needle)) {
        throw "mainhud.lua does not match expected structure. Missing: $needle"
    }
}


function Test-CompletionistRavenSource([string]$Text) {
    $required = @(
        'local ravenKilled = false',
        'function OnStart(level, obj)',
        'function OnHitByWeapon(level, obj, attacker, weapon)',
        'function OnRestoreCheckpoint(level, obj, tab)',
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

$ravenText = $null
$ravenSource = Join-Path $GameRoot ('mods\lua_source\' + $ravenRelative)

if (Test-Path $ravenSource) {
    $candidate = [IO.File]::ReadAllText($ravenSource)
    if (Test-CompletionistRavenSource $candidate) {
        $ravenText = $candidate
        Write-Host "Using local Raven source: $ravenSource"
    }
}

if ($null -eq $ravenText) {
    $pinnedCommit = '1958cf514d56e1278f02570c876ad127462b3551'
    $sourceUrl = "https://raw.githubusercontent.com/MorseTheCode/GoWLUA/$pinnedCommit/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua"
    $downloadedSource = Join-Path $env:TEMP 'completionist-map-v100-precisionchallenge.lua'

    Write-Host 'Local precisionchallenge.lua source was not found.'
    Write-Host 'Downloading the pinned reference source used by the earlier Raven diagnostic...'
    Invoke-WebRequest -Uri $sourceUrl -UseBasicParsing -OutFile $downloadedSource

    $candidate = [IO.File]::ReadAllText($downloadedSource)
    if (-not (Test-CompletionistRavenSource $candidate)) {
        throw 'Downloaded precisionchallenge.lua did not match the expected Raven script. Nothing was installed.'
    }

    $ravenText = $candidate
    $ravenSource = $downloadedSource
    Write-Host "Validated pinned Raven source: $pinnedCommit"
}

$ravenHelper = @'
-- Completionist Map v0.10.1 Raven lifecycle bridge.
-- Read-only with respect to progression: it only observes the script's own
-- ravenKilled state and publishes it to the custom map/HUD prototype.
local function CompletionistMapV100_IsTargetRaven()
  if thisObj == nil then
    return false, nil
  end

  local posOK, pos = pcall(function()
    return thisObj:GetWorldPosition()
  end)

  if not posOK or pos == nil then
    return false, nil
  end

  local dx = pos.x - (-64.850898742676)
  local dy = pos.y - 12.987384796143
  local dz = pos.z - 787.30694580078
  local distanceSq = dx * dx + dy * dy + dz * dz

  return distanceSq <= 0.25, pos
end

local function CompletionistMapV100_PublishTargetState(killed, source)
  local isTarget, pos = CompletionistMapV100_IsTargetRaven()
  if not isTarget then
    return
  end

  local collected = killed == true
  _G.CompletionistMapV100TargetRavenKilled = collected

  if _G.CompletionistMapV100Target ~= nil and
      _G.CompletionistMapV100Target.type == "Raven" then
    _G.CompletionistMapV100Target.collected = collected
    if collected then
      _G.CompletionistMapV100Target.active = false
    end
  end

  print("[CompletionistMap v0.10.1] RAVEN_STATE" ..
    " target=true" ..
    " source=" .. tostring(source) ..
    " killed=" .. tostring(collected) ..
    " regionQuest=" .. tostring(regionSummaryQuest) ..
    " x=" .. tostring(pos and pos.x or "<nil>") ..
    " y=" .. tostring(pos and pos.y or "<nil>") ..
    " z=" .. tostring(pos and pos.z or "<nil>"))
end
'@

$ravenText = $ravenText.Replace(
    'function OnScriptLoaded(level, obj)',
    $ravenHelper + "`r`nfunction OnScriptLoaded(level, obj)"
)

$ravenText = $ravenText.Replace(
    "function OnStart(level, obj)`n",
    "function OnStart(level, obj)`n  CompletionistMapV100_PublishTargetState(ravenKilled, `"OnStart`")`n"
)
$ravenText = $ravenText.Replace(
    "function OnStart(level, obj)`r`n",
    "function OnStart(level, obj)`r`n  CompletionistMapV100_PublishTargetState(ravenKilled, `"OnStart`")`r`n"
)

$ravenText = $ravenText.Replace(
    "function OnHitByWeapon(level, obj, attacker, weapon)`n",
    "function OnHitByWeapon(level, obj, attacker, weapon)`n  CompletionistMapV100_PublishTargetState(true, `"OnHitByWeapon`")`n"
)
$ravenText = $ravenText.Replace(
    "function OnHitByWeapon(level, obj, attacker, weapon)`r`n",
    "function OnHitByWeapon(level, obj, attacker, weapon)`r`n  CompletionistMapV100_PublishTargetState(true, `"OnHitByWeapon`")`r`n"
)

$ravenText = $ravenText.Replace(
    "  ravenKilled = tab.ravenKilled`nend`n",
    "  ravenKilled = tab.ravenKilled`n  CompletionistMapV100_PublishTargetState(ravenKilled, `"OnRestoreCheckpoint`")`nend`n"
)
$ravenText = $ravenText.Replace(
    "  ravenKilled = tab.ravenKilled`r`nend`r`n",
    "  ravenKilled = tab.ravenKilled`r`n  CompletionistMapV100_PublishTargetState(ravenKilled, `"OnRestoreCheckpoint`")`r`nend`r`n"
)

if (-not $ravenText.Contains('[CompletionistMap v0.10.1] RAVEN_STATE')) {
    throw 'Failed to inject the Raven lifecycle bridge.'
}

function Test-CompletionistNornirSource([string]$Text) {
    $required = @(
        'local keysUsed = 0',
        'local challengeComplete = false',
        'local runeTable = {}',
        'keyType = go:GetLuaTableAttribute("KeyType")',
        'thisObj:FindLuaTableAttribute("sealBreakable0" .. tostring(i))',
        'function OnPreStart(level, obj)',
        'function OnStart(level, go)',
        'function OnKeyBroken(runeIndex)',
        'function OnBellStartRinging(runeVisual, runeID)',
        'function OnRotateCallback()'
    )

    foreach ($needle in $required) {
        if (-not $Text.Contains($needle)) {
            return $false
        }
    }
    return $true
}

$nornirText = $null
$nornirSource = Join-Path $GameRoot ('mods\lua_source\' + $nornirRelative)

if (Test-Path $nornirSource) {
    $candidate = [IO.File]::ReadAllText($nornirSource)
    if (Test-CompletionistNornirSource $candidate) {
        $nornirText = $candidate
        Write-Host "Using local Nornir source: $nornirSource"
    }
}

if ($null -eq $nornirText) {
    $pinnedCommit = '1958cf514d56e1278f02570c876ad127462b3551'
    $sourceUrl = "https://raw.githubusercontent.com/MorseTheCode/GoWLUA/$pinnedCommit/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua"
    $downloadedSource = Join-Path $env:TEMP 'completionist-map-v100-interact_chest_runic.lua'

    Write-Host 'Local interact_chest_runic.lua source was not found.'
    Write-Host 'Downloading the pinned reference source for the Nornir diagnostic...'
    Invoke-WebRequest -Uri $sourceUrl -UseBasicParsing -OutFile $downloadedSource

    $candidate = [IO.File]::ReadAllText($downloadedSource)
    if (-not (Test-CompletionistNornirSource $candidate)) {
        throw 'Downloaded interact_chest_runic.lua did not match the expected Nornir script. Nothing was installed.'
    }

    $nornirText = $candidate
    $nornirSource = $downloadedSource
    Write-Host "Validated pinned Nornir source: $pinnedCommit"
}

$nornirHelper = @'
-- Completionist Map v0.10.1 Nornir state publisher.
-- Observes stock Nornir state and forwards a plain-data snapshot to the UI
-- WAD. It does not mutate puzzle state, quest state, or save data.

_G.CompletionistMapV100NornirRegistry =
  _G.CompletionistMapV100NornirRegistry or {}

local function CompletionistMapV100_SafeName(go)
  if go == nil then
    return "<nil>"
  end
  local ok, value = pcall(function()
    return go:GetName()
  end)
  return ok and tostring(value) or "<name-unavailable>"
end

local function CompletionistMapV100_SafePosition(go)
  if go == nil then
    return nil
  end
  local ok, pos = pcall(function()
    return go:GetWorldPosition()
  end)
  return ok and pos or nil
end

local function CompletionistMapV100_DumpNornir(source, activeIndex)
  if thisObj == nil then
    return
  end

  local chestPos = CompletionistMapV100_SafePosition(thisObj)
  local chestName = CompletionistMapV100_SafeName(thisObj)
  local registryKey =
    tostring(chestName) .. "|" ..
    tostring(chestPos and chestPos.x or "?") .. "|" ..
    tostring(chestPos and chestPos.z or "?")

  local previous =
    _G.CompletionistMapV100NornirRegistry[registryKey]

  local entry = {
    registryKey = registryKey,
    name = chestName,
    keyType = keyType,
    state = state,
    opened = state == states.OPENED,
    puzzleRevealed =
      state == states.LOCKED or
      challengeComplete == true or
      (previous ~= nil and previous.puzzleRevealed == true),
    challengeComplete = challengeComplete == true,
    keysUsed = keysUsed,
    x = chestPos and chestPos.x or nil,
    y = chestPos and chestPos.y or nil,
    z = chestPos and chestPos.z or nil,
    source = "ui_call_event",
    keys = {}
  }

  local unknownBreakable = {}
  local knownBrokenCount = 0

  for i = 1, 3 do
    local keyGO = runeTable[i] and runeTable[i].runeKey or nil
    local keyPos = CompletionistMapV100_SafePosition(keyGO)
    local keyName = CompletionistMapV100_SafeName(keyGO)

    local refOK, sealRef = pcall(function()
      return thisObj:FindLuaTableAttribute(
        "sealBreakable0" .. tostring(i)
      )
    end)

    local runeEnabledOK, runeEnabled = pcall(function()
      if runeTable[i] == nil or
          runeTable[i].runeVisual == nil or
          runeTable[i].runeVisual.LuaObjectScript == nil or
          runeTable[i].runeVisual.LuaObjectScript.IsEnabled == nil then
        return nil
      end
      return runeTable[i].runeVisual.LuaObjectScript.IsEnabled()
    end)

    local runeEnabledValue = nil
    if runeEnabledOK then
      runeEnabledValue = runeEnabled
    end

    local broken =
      previous ~= nil and
      previous.keys ~= nil and
      previous.keys[i] ~= nil and
      previous.keys[i].broken == true

    -- For Breakable chests only, a disabled rune visual is durable evidence
    -- that this exact seal has already been broken. Bell and MemoryChest
    -- visuals are intentionally temporary and must not use this rule.
    if keyType == "Breakable" and
        runeEnabledOK and runeEnabled == false then
      broken = true
    end

    if keyType == "Breakable" and
        source == "OnKeyBroken-after-disable" and
        tonumber(activeIndex) == i then
      broken = true
    end

    if broken then
      knownBrokenCount = knownBrokenCount + 1
    elseif keyType == "Breakable" and
        (not runeEnabledOK or runeEnabled == nil) then
      unknownBreakable[#unknownBreakable + 1] = i
    end

    entry.keys[i] = {
      index = i,
      ref = refOK and sealRef or nil,
      name = keyName,
      runeEnabled = runeEnabledValue,
      runeEnabledKnown = runeEnabledOK and runeEnabled ~= nil,
      broken = broken == true,
      x = keyPos and keyPos.x or nil,
      y = keyPos and keyPos.y or nil,
      z = keyPos and keyPos.z or nil
    }
  end

  -- Conservative persisted-state inference. If the stock aggregate says N
  -- Breakable seals are already gone and the exact number still unaccounted
  -- for equals the number of unknown rune visuals, those unknown indices must
  -- be the persisted broken seals. If the numbers do not match, show the
  -- uncertain seal rather than hide a potentially remaining one.
  if keyType == "Breakable" then
    local expectedBroken = tonumber(keysUsed) or 0
    local missing = expectedBroken - knownBrokenCount
    if missing > 0 and missing == #unknownBreakable then
      for _, index in ipairs(unknownBreakable) do
        entry.keys[index].broken = true
      end
      print("[CompletionistMap v0.10.1] NORNIR_PERSISTED_INFER" ..
        " registryKey=" .. tostring(registryKey) ..
        " keysUsed=" .. tostring(keysUsed) ..
        " inferred=" .. tostring(#unknownBreakable))
    end
  end

  print("[CompletionistMap v0.10.1] NORNIR_CHEST" ..
    " source=" .. tostring(source) ..
    " activeIndex=" .. tostring(activeIndex) ..
    " name=" .. tostring(chestName) ..
    " keyType=" .. tostring(keyType) ..
    " state=" .. tostring(state) ..
    " opened=" .. tostring(entry.opened) ..
    " puzzleRevealed=" .. tostring(entry.puzzleRevealed) ..
    " challengeComplete=" .. tostring(challengeComplete) ..
    " keysUsed=" .. tostring(keysUsed) ..
    " x=" .. tostring(chestPos and chestPos.x or "<nil>") ..
    " y=" .. tostring(chestPos and chestPos.y or "<nil>") ..
    " z=" .. tostring(chestPos and chestPos.z or "<nil>"))

  for i = 1, 3 do
    local key = entry.keys[i]
    print("[CompletionistMap v0.10.1] NORNIR_KEY" ..
      " chest=" .. tostring(chestName) ..
      " keyType=" .. tostring(keyType) ..
      " activeIndex=" .. tostring(activeIndex) ..
      " index=" .. tostring(i) ..
      " runeEnabledKnown=" .. tostring(key.runeEnabledKnown) ..
      " runeEnabled=" .. tostring(key.runeEnabled) ..
      " broken=" .. tostring(key.broken) ..
      " ref=" .. tostring(key.ref or "<unavailable>") ..
      " name=" .. tostring(key.name) ..
      " x=" .. tostring(key.x or "<nil>") ..
      " y=" .. tostring(key.y or "<nil>") ..
      " z=" .. tostring(key.z or "<nil>"))
  end

  _G.CompletionistMapV100NornirRegistry[registryKey] = entry

  local sendOK, sendErr = pcall(function()
    engine.SendHook(
      "UI_CALL_EVENT",
      engine.GetUIWad(),
      "EVT_COMPLETIONIST_NORNIR_STATE",
      entry
    )
  end)

  print("[CompletionistMap v0.10.1] NORNIR_UI_BRIDGE_SEND" ..
    " ok=" .. tostring(sendOK) ..
    " error=" .. tostring(sendErr) ..
    " registryKey=" .. tostring(registryKey))
end
'@

$nornirText = $nornirText.Replace(
    'function OnScriptLoaded(level, go)',
    $nornirHelper + "`r`nfunction OnScriptLoaded(level, go)"
)

$nornirText = $nornirText.Replace(
    "function OnStart(level, go)`n",
    "function OnStart(level, go)`n  CompletionistMapV100_DumpNornir(`"OnStart`")`n"
)
$nornirText = $nornirText.Replace(
    "function OnStart(level, go)`r`n",
    "function OnStart(level, go)`r`n  CompletionistMapV100_DumpNornir(`"OnStart`")`r`n"
)

$nornirText = $nornirText.Replace(
    "function PerformKratosInteraction_Locked()`n  Lock()`n",
    "function PerformKratosInteraction_Locked()`n  Lock()`n  CompletionistMapV100_DumpNornir(`"OnLockedAttempt`")`n"
)
$nornirText = $nornirText.Replace(
    "function PerformKratosInteraction_Locked()`r`n  Lock()`r`n",
    "function PerformKratosInteraction_Locked()`r`n  Lock()`r`n  CompletionistMapV100_DumpNornir(`"OnLockedAttempt`")`r`n"
)

$nornirText = $nornirText.Replace(
    "function OnKeyBroken(runeIndex)`n",
    "function OnKeyBroken(runeIndex)`n  CompletionistMapV100_DumpNornir(`"OnKeyBroken-before`", runeIndex)`n"
)
$nornirText = $nornirText.Replace(
    "function OnKeyBroken(runeIndex)`r`n",
    "function OnKeyBroken(runeIndex)`r`n  CompletionistMapV100_DumpNornir(`"OnKeyBroken-before`", runeIndex)`r`n"
)

$nornirText = $nornirText.Replace(
    "  runeTable[i].runeVisual.LuaObjectScript.Disable()`n",
    "  runeTable[i].runeVisual.LuaObjectScript.Disable()`n  CompletionistMapV100_DumpNornir(`"OnKeyBroken-after-disable`", runeIndex)`n"
)
$nornirText = $nornirText.Replace(
    "  runeTable[i].runeVisual.LuaObjectScript.Disable()`r`n",
    "  runeTable[i].runeVisual.LuaObjectScript.Disable()`r`n  CompletionistMapV100_DumpNornir(`"OnKeyBroken-after-disable`", runeIndex)`r`n"
)

$nornirText = $nornirText.Replace(
    "  CheckKeys()`n",
    "  CheckKeys()`n  CompletionistMapV100_DumpNornir(`"OnKeyBroken-after-check`", runeIndex)`n"
)
$nornirText = $nornirText.Replace(
    "  CheckKeys()`r`n",
    "  CheckKeys()`r`n  CompletionistMapV100_DumpNornir(`"OnKeyBroken-after-check`", runeIndex)`r`n"
)

$nornirText = $nornirText.Replace(
    "function OnBellStartRinging(runeVisual, runeID)`n",
    "function OnBellStartRinging(runeVisual, runeID)`n  CompletionistMapV100_DumpNornir(`"OnBellStartRinging-before`", runeID)`n"
)
$nornirText = $nornirText.Replace(
    "function OnBellStartRinging(runeVisual, runeID)`r`n",
    "function OnBellStartRinging(runeVisual, runeID)`r`n  CompletionistMapV100_DumpNornir(`"OnBellStartRinging-before`", runeID)`r`n"
)

$nornirText = $nornirText.Replace(
    "function OnRotateCallback()`n",
    "function OnRotateCallback()`n  CompletionistMapV100_DumpNornir(`"OnRotateCallback-before`")`n"
)
$nornirText = $nornirText.Replace(
    "function OnRotateCallback()`r`n",
    "function OnRotateCallback()`r`n  CompletionistMapV100_DumpNornir(`"OnRotateCallback-before`")`r`n"
)

$nornirText = $nornirText.Replace(
    "  state = states.OPENED`n",
    "  state = states.OPENED`n  CompletionistMapV100_DumpNornir(`"OnInteractFinish-after-open`")`n"
)
$nornirText = $nornirText.Replace(
    "  state = states.OPENED`r`n",
    "  state = states.OPENED`r`n  CompletionistMapV100_DumpNornir(`"OnInteractFinish-after-open`")`r`n"
)

if (-not $nornirText.Contains('[CompletionistMap v0.10.1] NORNIR_KEY')) {
    throw 'Failed to inject the Nornir position diagnostic.'
}

function Test-CompletionistStandardChestSource([string]$Text) {
    $required = @(
        'function OnStart(level, obj)',
        'function OnOpened()',
        'state = states.OPENED',
        'chestType == "Runic_Axe" or chestType == "Runic_Blades"',
        'parentObj = thisObj.Parent.Parent',
        'function OnRestoreCheckpoint(level, obj, savedInfo)'
    )

    foreach ($needle in $required) {
        if (-not $Text.Contains($needle)) {
            return $false
        }
    }
    return $true
}

$standardChestText = $null
$standardChestSource =
    Join-Path $GameRoot ('mods\lua_source\' + $standardChestRelative)

if (Test-Path $standardChestSource) {
    $candidate = [IO.File]::ReadAllText($standardChestSource)
    if (Test-CompletionistStandardChestSource $candidate) {
        $standardChestText = $candidate
        Write-Host "Using local standard chest source: $standardChestSource"
    }
}

if ($null -eq $standardChestText) {
    $pinnedCommit = '1958cf514d56e1278f02570c876ad127462b3551'
    $sourceUrl = "https://raw.githubusercontent.com/MorseTheCode/GoWLUA/$pinnedCommit/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua"
    $downloadedSource =
        Join-Path $env:TEMP 'completionist-map-v100-interact_chest_standard.lua'

    Write-Host 'Local interact_chest_standard.lua source was not found.'
    Write-Host 'Downloading the pinned standard chest reference source...'
    Invoke-WebRequest -Uri $sourceUrl -UseBasicParsing -OutFile $downloadedSource

    $candidate = [IO.File]::ReadAllText($downloadedSource)
    if (-not (Test-CompletionistStandardChestSource $candidate)) {
        throw 'Downloaded interact_chest_standard.lua did not match expected structure. Nothing was installed.'
    }

    $standardChestText = $candidate
    $standardChestSource = $downloadedSource
    Write-Host "Validated pinned standard chest source: $pinnedCommit"
}

$standardChestHelper = @'
-- Completionist Map v0.10.1 authoritative Nornir chest-open publisher.
-- The runic parent owns puzzle state, but interact_chest_standard.lua owns the
-- actual loot chest's OPENED state. This is observational only.
local function CompletionistMapV100_PublishRunicChestOpened(source)
  if chestType ~= "Runic_Axe" and chestType ~= "Runic_Blades" then
    return
  end

  if parentObj == nil then
    return
  end

  local posOK, pos = pcall(function()
    return parentObj:GetWorldPosition()
  end)
  local nameOK, name = pcall(function()
    return parentObj:GetName()
  end)

  if not posOK or pos == nil then
    return
  end

  local registryKey =
    tostring(nameOK and name or "chest_locked_parent") .. "|" ..
    tostring(pos.x) .. "|" ..
    tostring(pos.z)

  local payload = {
    registryKey = registryKey,
    name = nameOK and name or "chest_locked_parent",
    opened = true,
    x = pos.x,
    y = pos.y,
    z = pos.z,
    source = source
  }

  local sendOK, sendErr = pcall(function()
    engine.SendHook(
      "UI_CALL_EVENT",
      engine.GetUIWad(),
      "EVT_COMPLETIONIST_NORNIR_OPENED",
      payload
    )
  end)

  print("[CompletionistMap v0.10.1] NORNIR_OPENED_SEND" ..
    " source=" .. tostring(source) ..
    " ok=" .. tostring(sendOK) ..
    " error=" .. tostring(sendErr) ..
    " registryKey=" .. tostring(registryKey))
end
'@

$standardChestText = $standardChestText.Replace(
    'function OnScriptLoaded(level, obj)',
    $standardChestHelper + "`r`nfunction OnScriptLoaded(level, obj)"
)

$standardChestText = $standardChestText.Replace(
    "function OnOpened()`n",
    "function OnOpened()`n  CompletionistMapV100_PublishRunicChestOpened(`"OnOpened`")`n"
)
$standardChestText = $standardChestText.Replace(
    "function OnOpened()`r`n",
    "function OnOpened()`r`n  CompletionistMapV100_PublishRunicChestOpened(`"OnOpened`")`r`n"
)

# OnStart is also useful when loading an already-opened Runic chest.
$standardChestText = $standardChestText.Replace(
    "function OnStart(level, obj)`n",
    "function OnStart(level, obj)`n  if state == states.OPENED then CompletionistMapV100_PublishRunicChestOpened(`"OnStart-opened`") end`n"
)
$standardChestText = $standardChestText.Replace(
    "function OnStart(level, obj)`r`n",
    "function OnStart(level, obj)`r`n  if state == states.OPENED then CompletionistMapV100_PublishRunicChestOpened(`"OnStart-opened`") end`r`n"
)

if (-not $standardChestText.Contains('[CompletionistMap v0.10.1] NORNIR_OPENED_SEND')) {
    throw 'Failed to inject standard Runic chest opened-state publisher.'
}

$mapHelper = @'
-- Completionist Map v0.10.1
--
-- Map side:
--   Create a genuinely separate duplicate of a SAFE DISCOVERED DockPoint icon,
--   move the duplicate ROOT to the Raven map coordinate, and intercept only
--   collision with that exact duplicate. This gives us boat artwork without
--   hijacking the original dock.
--
-- HUD side:
--   While the map is open and Add to Compass is pressed, create a SECOND safe
--   DockPoint duplicate, detach it from the map hierarchy, and hand it to the
--   MainHUD script. MainHUD reparents that visual beneath Compass and moves it
--   across the strip using the already-proven Raven bearing math.
--
-- No marker state, quest state, collectible state, or save data is changed.
_G.CompletionistMapV100NornirRegistry = _G.CompletionistMapV100NornirRegistry or {}

print("[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED")

if _G.CompletionistMapV100PlayerMarkerVisible == nil then
  _G.CompletionistMapV100PlayerMarkerVisible = true
end

_G.CompletionistMapV100Target = _G.CompletionistMapV100Target or {
  active = false,
  collected = false,
  type = "Raven",
  realm = "Midgard",
  regionQuest = "RegionSummary_VF_Raven_Parent",
  x = -64.850898742676,
  y = 12.987384796143,
  z = 787.30694580078,
  mapX = 3.2117712497711,
  mapZ = 0.8695997595787
}

local CompletionistMapV100_GetNornirRegistry
local CompletionistMapV100_ApplyZoomAdaptiveIconScale

local COMPLETIONIST_RAVEN_WORLD_X = -64.850898742676
local COMPLETIONIST_RAVEN_WORLD_Y = 12.987384796143
local COMPLETIONIST_RAVEN_WORLD_Z = 787.30694580078
local COMPLETIONIST_RAVEN_MAP_X = 3.2117712497711
local COMPLETIONIST_RAVEN_MAP_Z = 0.8695997595787

local COMPLETIONIST_ICON_ROOT = "__COMPLETIONIST_ICON_ROOT__"
local completionistMapV100IconApiLogged = {}

local function CompletionistMapV100_IconPath(family, size)
  return COMPLETIONIST_ICON_ROOT .. "/" .. tostring(size) .. "/" ..
    tostring(family) .. ".png"
end

local function CompletionistMapV100_GetCallable(container, name)
  if container == nil then return nil end
  local ok, value = pcall(function() return container[name] end)
  if ok and type(value) == "function" then
    return value
  end
  return nil
end

local function CompletionistMapV100_LogIconCapabilities(go, family)
  if go == nil then return end
  if completionistMapV100IconApiLogged[family] then return end
  completionistMapV100IconApiLogged[family] = true

  local goMethods = {
    "SetTexture",
    "SetTextureName",
    "SetImage",
    "SetImagePath",
    "SetSprite",
    "SetMaterialSwap"
  }
  local uiMethods = {
    "SetTexture",
    "SetTextureName",
    "SetImage",
    "SetImagePath",
    "SetSprite"
  }

  local goCaps = {}
  for _, name in ipairs(goMethods) do
    goCaps[#goCaps + 1] = name .. "=" .. tostring(
      CompletionistMapV100_GetCallable(go, name) ~= nil
    )
  end

  local uiCaps = {}
  for _, name in ipairs(uiMethods) do
    uiCaps[#uiCaps + 1] = name .. "=" .. tostring(
      CompletionistMapV100_GetCallable(UI, name) ~= nil
    )
  end

  print("[CompletionistMap v0.10.1] ICON_CAPS" ..
    " family=" .. tostring(family) ..
    " go={" .. table.concat(goCaps, ",") .. "}" ..
    " ui={" .. table.concat(uiCaps, ",") .. "}" ..
    " path=" .. CompletionistMapV100_IconPath(family, 32))
end

local function CompletionistMapV100_TryDirectIconBind(go, family)
  if go == nil then return false end
  CompletionistMapV100_LogIconCapabilities(go, family)

  local path = CompletionistMapV100_IconPath(family, 32)
  local attempts = {
    {owner = go, ownerName = "GO", name = "SetTexture"},
    {owner = go, ownerName = "GO", name = "SetTextureName"},
    {owner = go, ownerName = "GO", name = "SetImage"},
    {owner = go, ownerName = "GO", name = "SetImagePath"},
    {owner = UI, ownerName = "UI", name = "SetTexture", passGO = true},
    {owner = UI, ownerName = "UI", name = "SetTextureName", passGO = true},
    {owner = UI, ownerName = "UI", name = "SetImage", passGO = true},
    {owner = UI, ownerName = "UI", name = "SetImagePath", passGO = true}
  }

  for _, attempt in ipairs(attempts) do
    local fn = CompletionistMapV100_GetCallable(attempt.owner, attempt.name)
    if fn ~= nil then
      local ok, err = pcall(function()
        if attempt.passGO then
          fn(go, path)
        else
          fn(go, path)
        end
      end)

      print("[CompletionistMap v0.10.1] ICON_BIND_ATTEMPT" ..
        " family=" .. tostring(family) ..
        " api=" .. tostring(attempt.ownerName) .. "." .. tostring(attempt.name) ..
        " ok=" .. tostring(ok) ..
        " error=" .. tostring(err) ..
        " path=" .. tostring(path))

      if ok then
        return true
      end
    end
  end

  print("[CompletionistMap v0.10.1] ICON_BIND_RESULT" ..
    " family=" .. tostring(family) ..
    " direct=false" ..
    " fallback=DockPointProxy")
  return false
end

local function CompletionistMapV100_NornirIconFamily(keyType)
  if keyType == "Breakable" then return "nornir_seal" end
  if keyType == "Bell" then return "nornir_bell" end
  if keyType == "MemoryChest" then return "nornir_mechanism" end
  return "remaining_collectible"
end

local function CompletionistMapV100_IsRavenCollected()
  if _G.CompletionistMapV100TargetRavenKilled == true then
    return true
  end

  local stateOK, state = pcall(function()
    return game.QuestManager.GetQuestState(
      "RegionSummary_VF_Raven_Parent"
    )
  end)

  if stateOK and tostring(state) == "Complete" then
    _G.CompletionistMapV100TargetRavenKilled = true
    return true
  end

  return false
end

local function CompletionistMapV100_IsTargetCollected()
  local target = _G.CompletionistMapV100Target
  if target == nil then return false end

  if target.type == "NornirPuzzle" or target.type == "NornirChest" then
    if not _G.CompletionistMapV100TargetCollectedNornirLogged then
      _G.CompletionistMapV100TargetCollectedNornirLogged = true
      print("[CompletionistMap v0.10.1] NORNIR_TARGET_STATE_CHECK" ..
        " type=" .. tostring(target.type) ..
        " registryKey=" .. tostring(target.registryKey) ..
        " helperScope=local_forward_declared")
    end

    local registry = CompletionistMapV100_GetNornirRegistry()
    local entry = registry and registry[target.registryKey] or nil
    if entry ~= nil then
      if target.type == "NornirChest" then
        target.collected = entry.opened == true
      else
        local key = entry.keys and entry.keys[target.keyIndex] or nil
        if entry.challengeComplete == true or entry.opened == true then
          target.collected = true
        elseif entry.keyType == "Breakable" then
          target.collected = key ~= nil and key.broken == true
        else
          target.collected = false
        end
      end
    end
    if target.collected then target.active = false end
    return target.collected == true
  end

  if _G.CompletionistMapV100TargetRavenKilled == true then
    target.collected = true
  end
  if not target.collected and target.regionQuest ~= nil then
    local stateOK, state = pcall(function()
      return game.QuestManager.GetQuestState(target.regionQuest)
    end)
    if stateOK and tostring(state) == "Complete" then
      target.collected = true
      _G.CompletionistMapV100TargetRavenKilled = true
    end
  end
  if target.collected then target.active = false end
  return target.collected
end

local function CompletionistMapV100_LogMapCalibration(self)
  if self.currRealmName ~= "Midgard" or self.playerIconGO == nil then
    return
  end

  local player = game.Player.FindPlayer()
  if player == nil then
    return
  end

  local worldOK, worldPos = pcall(function()
    return player:GetWorldPosition()
  end)

  local mapOK, mapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)

  if not worldOK or worldPos == nil or
      not mapOK or mapPos == nil then
    return
  end

  local last = _G.CompletionistMapV100LastCalibration
  local shouldLog = last == nil

  if last ~= nil then
    local dx = worldPos.x - last.x
    local dz = worldPos.z - last.z
    shouldLog = dx * dx + dz * dz >= 400
  end

  if not shouldLog then
    return
  end

  _G.CompletionistMapV100LastCalibration = {
    x = worldPos.x,
    z = worldPos.z
  }

  print("[CompletionistMap v0.10.1] MAP_CALIBRATION" ..
    " realm=" .. tostring(self.currRealmName) ..
    " worldX=" .. tostring(worldPos.x) ..
    " worldY=" .. tostring(worldPos.y) ..
    " worldZ=" .. tostring(worldPos.z) ..
    " mapX=" .. tostring(mapPos.x) ..
    " mapY=" .. tostring(mapPos.y) ..
    " mapZ=" .. tostring(mapPos.z))
end

local completionistMapV100PreferredDockIds = {
  "2924516555722838670",
  "3015224018432851104",
  "-8580963607903916635",
  "-8580963607903813648",
  "-8580963607903819882",
  "-8580963607903820923",
  "-8580963607903817804",
  "-8580963607903818837",
  "-8580963607903824038",
  "3665597207158594306",
  "-7682859529157234129",
  "2012662071676473320",
  "-1367314585613671475",
  "-5774578489664548484",
  "1998313177983296660",
  "674850249950444597"
}

local function CompletionistMapV100_BuildBackingDockPool(self)
  if type(self.completionistMapV100BackingDockPool) == "table" and
      #self.completionistMapV100BackingDockPool > 0 then
    return self.completionistMapV100BackingDockPool
  end

  local byId = {}
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    local safeOK, safe = pcall(function()
      return markerInfo.State == tweaks.eTokenState.kDiscovered and
        Map.MarkerHasAnyFlag(
          markerInfo.Id,
          {consts.COMPASS_MARKER_TYPE_DOCK_POINT}
        )
    end)

    if safeOK and safe then
      markerInfo.regionId = markerInfo.regionId or
        select(2, Map.FindRegionFromMarker(markerInfo.Id))
      byId[tostring(markerInfo.Id)] = markerInfo
    end
  end

  local pool = {}
  local used = {}

  for _, idString in ipairs(completionistMapV100PreferredDockIds) do
    local markerInfo = byId[idString]
    if markerInfo ~= nil and not used[idString] then
      pool[#pool + 1] = markerInfo
      used[idString] = true
    end
  end

  local remaining = {}
  for idString, markerInfo in pairs(byId) do
    if not used[idString] then
      remaining[#remaining + 1] = markerInfo
    end
  end

  table.sort(remaining, function(a, b)
    return tostring(a.Id) < tostring(b.Id)
  end)

  for _, markerInfo in ipairs(remaining) do
    pool[#pool + 1] = markerInfo
  end

  self.completionistMapV100BackingDockPool = pool

  local ids = {}
  for i = 1, math.min(#pool, 12) do
    ids[#ids + 1] = tostring(pool[i].Id)
  end

  print("[CompletionistMap v0.10.1] BACKING_POOL" ..
    " count=" .. tostring(#pool) ..
    " first=" .. table.concat(ids, ","))

  return pool
end

local function CompletionistMapV100_FindBackingDock(self, slot)
  local pool = CompletionistMapV100_BuildBackingDockPool(self)
  if type(pool) ~= "table" or #pool == 0 then
    return nil
  end

  slot = math.max(1, tonumber(slot) or 1)
  local index = ((slot - 1) % #pool) + 1
  local markerInfo = pool[index]

  self.completionistMapV100BackingSlotLog =
    self.completionistMapV100BackingSlotLog or {}

  if not self.completionistMapV100BackingSlotLog[slot] then
    self.completionistMapV100BackingSlotLog[slot] = true
    print("[CompletionistMap v0.10.1] BACKING_ASSIGN" ..
      " slot=" .. tostring(slot) ..
      " id=" .. tostring(markerInfo.Id) ..
      " region=" .. tostring(markerInfo.regionId))
  end

  return markerInfo
end


local function CompletionistMapV100_WorldToMidgardMap(x, z)
  return
    0.004 * z + 0.0625431,
    -0.004 * x + 0.6101961
end

CompletionistMapV100_GetNornirRegistry = function()
  local uiRegistry = _G.CompletionistMapV100NornirRegistry
  if type(uiRegistry) == "table" and next(uiRegistry) ~= nil then
    if not _G.CompletionistMapV100RegistryLogged then
      _G.CompletionistMapV100RegistryLogged = true
      print("[CompletionistMap v0.10.1] NORNIR_REGISTRY" ..
        " source=ui_call_event")
    end
    return uiRegistry, "ui_call_event"
  end

  -- One verified parent location remains as a bootstrap so the known chest
  -- can appear before its gameplay script publishes live state. Puzzle child
  -- pins are deliberately NOT created from this fallback because persisted
  -- per-seal state would be unknown.
  local registryKey =
    "known_breakable|-43.904609680176|748.57946777344"
  local fallback = {}
  fallback[registryKey] = {
    registryKey = registryKey,
    name = "chest_locked_parent",
    keyType = "Breakable",
    opened = false,
    challengeComplete = false,
    keysUsed = nil,
    x = -43.904609680176,
    y = 14.5,
    z = 748.57946777344,
    source = "verified_parent_fallback",
    keys = {}
  }

  if not _G.CompletionistMapV100FallbackLogged then
    _G.CompletionistMapV100FallbackLogged = true
    print("[CompletionistMap v0.10.1] NORNIR_FALLBACK" ..
      " parentOnly=true chest=chest_locked_parent" ..
      " ignoresStockSummary=true")
  end

  return fallback, "verified_parent_fallback"
end

local function CompletionistMapV100_IsNornirKeyRemaining(pin)
  if pin == nil then
    return false
  end

  local registry = CompletionistMapV100_GetNornirRegistry()
  local entry = registry and registry[pin.registryKey] or nil
  if entry == nil or entry.opened == true or entry.challengeComplete == true then
    return false
  end

  local key = entry.keys and entry.keys[pin.keyIndex] or nil
  if key == nil then
    return false
  end

  if entry.keyType == "Breakable" then
    return key.broken ~= true
  end

  -- Bell and MemoryChest actors remain relevant until the whole timed/rotator
  -- challenge completes. Their transient runeVisual disabled state is not a
  -- collected state.
  return true
end

local function CompletionistMapV100_DestroyNornirPins(self)
  if self.completionistMapV100NornirPins ~= nil then
    for _, pin in ipairs(self.completionistMapV100NornirPins) do
      if pin.iconGO ~= nil then
        pcall(function()
          Map.RecycleIcon(pin.iconGO)
        end)
      end
    end
  end

  self.completionistMapV100NornirPins = {}
  self.completionistMapV100NornirSelected = nil
  self.completionistMapV100NornirLastHitFrame = nil
end

local function CompletionistMapV100_NornirReticle(self, currState, pin)
  self.currQuestID = nil
  self.currMarkerID = nil
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false
  self.completionistMapV100Selected = false
  self.completionistMapV100NornirChestSelected = nil

  local title = "Nornir Puzzle " .. tostring(pin.keyIndex)
  local description = "Nornir puzzle element - Completionist Map"
  if pin.keyType == "Breakable" then
    title = "Nornir Seal " .. tostring(pin.keyIndex)
    description = "Unbroken rune seal - Completionist Map"
  elseif pin.keyType == "Bell" then
    title = "Nornir Bell " .. tostring(pin.keyIndex)
    description = "Timed Nornir bell - Completionist Map"
  elseif pin.keyType == "MemoryChest" then
    title = "Nornir Rune Mechanism " .. tostring(pin.keyIndex)
    description = "Rune rotator - Completionist Map"
  end

  local target = _G.CompletionistMapV100Target
  if target ~= nil and
      target.type == "NornirPuzzle" and
      target.registryKey == pin.registryKey and
      target.keyIndex == pin.keyIndex and
      target.active then
    description = description .. " - tracked"
  end

  self:SetReticleInfo(currState, title, description)
  self:UpdateFooterButtonPrompt(currState.menu, false, false)
end

local function CompletionistMapV100_DestroyNornirChestPins(self)
  if type(self.completionistMapV100NornirChestPins) == "table" then
    for _, pin in ipairs(self.completionistMapV100NornirChestPins) do
      if pin.iconGO ~= nil then
        pcall(function() Map.RecycleIcon(pin.iconGO) end)
      end
    end
  end
  self.completionistMapV100NornirChestPins = {}
  self.completionistMapV100NornirChestSelected = nil
end

local function CompletionistMapV100_IsNornirChestRemaining(pin)
  if pin == nil then return false end
  local registry = CompletionistMapV100_GetNornirRegistry()
  local entry = registry and registry[pin.registryKey] or nil
  return entry ~= nil and entry.opened ~= true
end

local function CompletionistMapV100_NornirChestReticle(self, currState, pin)
  self.currQuestID = nil
  self.currMarkerID = nil
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false
  self.completionistMapV100Selected = false
  self.completionistMapV100NornirSelected = nil

  local registry = CompletionistMapV100_GetNornirRegistry()
  local entry = registry and registry[pin.registryKey] or nil
  local title = "Nornir Chest"
  local description = "Incomplete Nornir Chest - Completionist Map"
  if entry ~= nil then
    if entry.challengeComplete == true and entry.opened ~= true then
      description = "Unlocked Nornir Chest - open it to complete"
    elseif entry.keyType == "Breakable" then
      description = "Nornir Chest - break the remaining rune seals"
    elseif entry.keyType == "Bell" then
      description = "Nornir Chest - ring the three timed bells"
    elseif entry.keyType == "MemoryChest" then
      description = "Nornir Chest - solve the rune mechanisms"
    end
  end

  self:SetReticleInfo(currState, title, description)
  self:UpdateFooterButtonPrompt(currState.menu, false, false)
end

local function CompletionistMapV100_CreateNornirChestPins(self, currState)
  CompletionistMapV100_DestroyNornirChestPins(self)
  if self.currRealmName ~= "Midgard" then return end

  local registry, registrySource = CompletionistMapV100_GetNornirRegistry()

  local mapY = 0
  local playerYOK, playerMapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerYOK and playerMapPos ~= nil then mapY = playerMapPos.y end

  local chestOrdinal = 0
  for registryKey, entry in pairs(registry or {}) do
    if entry ~= nil and entry.opened ~= true and
        entry.x ~= nil and entry.z ~= nil then
      chestOrdinal = chestOrdinal + 1
      local backing =
        CompletionistMapV100_FindBackingDock(self, 2 + chestOrdinal - 1)
      if backing == nil then
        print("[CompletionistMap v0.10.1] NORNIR_CHEST_PIN" ..
          " ok=false reason=safe_dock_not_found" ..
          " registryKey=" .. tostring(registryKey))
      else
        local mapX, mapZ =
          CompletionistMapV100_WorldToMidgardMap(entry.x, entry.z)
        local createOK, iconOrErr = pcall(function()
          return Map.CreateMarkerIcon(backing.Id, backing.regionId, "")
        end)
      if createOK and iconOrErr ~= nil then
        local pin = {
          registryKey = registryKey,
          keyType = entry.keyType,
          worldX = entry.x, worldY = entry.y, worldZ = entry.z,
          mapX = mapX, mapY = mapY, mapZ = mapZ,
          iconGO = iconOrErr, frames = 0
        }
        local ok = pcall(function()
          pin.iconGO:SetWorldPosition(engine.Vector.New(mapX, mapY, mapZ))
          pin.iconGO:Show()
          UI.SetIsClickable(pin.iconGO)
          CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
          CompletionistMapV100_TryDirectIconBind(pin.iconGO, "nornir_chest")
        end)
        if ok then
          table.insert(self.completionistMapV100NornirChestPins, pin)
          print("[CompletionistMap v0.10.1] NORNIR_CHEST_PIN" ..
            " ok=true source=" .. tostring(registrySource) ..
            " registryKey=" .. tostring(registryKey) ..
            " backingId=" .. tostring(backing.Id) ..
            " mapX=" .. tostring(mapX) ..
            " mapZ=" .. tostring(mapZ))
        else
          pcall(function() Map.RecycleIcon(pin.iconGO) end)
        end
      end
      end
    end
  end
end

local function CompletionistMapV100_FindNornirChestCollision(self, collisionGameObjectTable)
  if type(collisionGameObjectTable) ~= "table" or
      type(self.completionistMapV100NornirChestPins) ~= "table" then
    return nil
  end
  for _, collGO in ipairs(collisionGameObjectTable) do
    for _, pin in ipairs(self.completionistMapV100NornirChestPins) do
      if pin.iconGO == collGO and
          CompletionistMapV100_IsNornirChestRemaining(pin) then
        return pin
      end
    end
  end
  return nil
end

local function CompletionistMapV100_RefreshNornirChestPins(self)
  if type(self.completionistMapV100NornirChestPins) ~= "table" then return end
  for i = #self.completionistMapV100NornirChestPins, 1, -1 do
    local pin = self.completionistMapV100NornirChestPins[i]
    pin.frames = (pin.frames or 0) + 1
    if pin.frames <= 60 and pin.iconGO ~= nil then
      pcall(function()
        pin.iconGO:SetWorldPosition(
          engine.Vector.New(pin.mapX, pin.mapY or 0, pin.mapZ)
        )
        UI.SetIsClickable(pin.iconGO)
      end)
    end
    if not CompletionistMapV100_IsNornirChestRemaining(pin) then
      if pin.iconGO ~= nil then
        pcall(function() Map.RecycleIcon(pin.iconGO) end)
      end
      if self.completionistMapV100NornirChestSelected == pin then
        self.completionistMapV100NornirChestSelected = nil
      end
      table.remove(self.completionistMapV100NornirChestPins, i)
      print("[CompletionistMap v0.10.1] NORNIR_CHEST_PIN_REMOVE" ..
        " registryKey=" .. tostring(pin.registryKey))
    end
  end
end

local function CompletionistMapV100_CreateNornirPins(self, currState)
  CompletionistMapV100_DestroyNornirPins(self)

  if self.currRealmName ~= "Midgard" then
    return
  end

  local registry, registrySource =
    CompletionistMapV100_GetNornirRegistry()

  if registrySource ~= "ui_call_event" then
    print("[CompletionistMap v0.10.1] NORNIR_MAP" ..
      " count=0 reason=live_state_required")
    return
  end

  local mapY = 0
  local playerYOK, playerMapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerYOK and playerMapPos ~= nil then
    mapY = playerMapPos.y
  end

  local created = 0
  for registryKey, entry in pairs(registry) do
    if entry ~= nil and
        entry.opened ~= true and
        entry.challengeComplete ~= true and
        type(entry.keys) == "table" then
      for i = 1, 3 do
        local key = entry.keys[i]
        local shouldCreate = key ~= nil and
          key.x ~= nil and key.z ~= nil

        if shouldCreate and entry.keyType == "Breakable" then
          shouldCreate = key.broken ~= true
        end

        if shouldCreate then
          local backing =
            CompletionistMapV100_FindBackingDock(self, 10 + created)
          if backing == nil then
            print("[CompletionistMap v0.10.1] NORNIR_PIN_CREATE" ..
              " ok=false index=" .. tostring(i) ..
              " reason=safe_dock_not_found")
          else
            local mapX, mapZ =
              CompletionistMapV100_WorldToMidgardMap(key.x, key.z)
            local createOK, iconOrErr = pcall(function()
              return Map.CreateMarkerIcon(backing.Id, backing.regionId, "")
            end)

            if createOK and iconOrErr ~= nil then
            local pin = {
              registryKey = registryKey,
              keyIndex = i,
              keyType = entry.keyType,
              worldX = key.x,
              worldY = key.y,
              worldZ = key.z,
              mapX = mapX,
              mapY = mapY,
              mapZ = mapZ,
              iconGO = iconOrErr,
              frames = 0,
              broken = key.broken == true
            }
            local setOK, setErr = pcall(function()
              pin.iconGO:SetWorldPosition(
                engine.Vector.New(mapX, mapY, mapZ)
              )
              pin.iconGO:Show()
              UI.SetIsClickable(pin.iconGO)
              CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
              CompletionistMapV100_TryDirectIconBind(
                pin.iconGO,
                CompletionistMapV100_NornirIconFamily(entry.keyType)
              )
            end)
            if setOK then
              table.insert(self.completionistMapV100NornirPins, pin)
              created = created + 1
              print("[CompletionistMap v0.10.1] NORNIR_PIN_CREATE" ..
                " ok=true registryKey=" .. tostring(registryKey) ..
                " keyType=" .. tostring(entry.keyType) ..
                " index=" .. tostring(i) ..
                " backingId=" .. tostring(backing.Id) ..
                " mapX=" .. tostring(mapX) ..
                " mapZ=" .. tostring(mapZ))
            else
              pcall(function() Map.RecycleIcon(pin.iconGO) end)
              print("[CompletionistMap v0.10.1] NORNIR_PIN_CREATE" ..
                " ok=false index=" .. tostring(i) ..
                " error=" .. tostring(setErr))
            end
            end
          end
        end
      end
    end
  end

  print("[CompletionistMap v0.10.1] NORNIR_MAP" ..
    " count=" .. tostring(created) ..
    " source=" .. tostring(registrySource))
end

local function CompletionistMapV100_FindNornirCollision(
  self,
  collisionGameObjectTable
)
  if type(collisionGameObjectTable) ~= "table" or
      type(self.completionistMapV100NornirPins) ~= "table" then
    return nil
  end

  for _, collGO in ipairs(collisionGameObjectTable) do
    for _, pin in ipairs(self.completionistMapV100NornirPins) do
      if pin.iconGO == collGO and
          CompletionistMapV100_IsNornirKeyRemaining(pin) then
        return pin
      end
    end
  end

  return nil
end

local function CompletionistMapV100_RefreshNornirPins(self)
  if type(self.completionistMapV100NornirPins) ~= "table" then
    return
  end

  for i = #self.completionistMapV100NornirPins, 1, -1 do
    local pin = self.completionistMapV100NornirPins[i]

    pin.frames = (pin.frames or 0) + 1
    if pin.frames <= 60 and pin.iconGO ~= nil then
      pcall(function()
        pin.iconGO:SetWorldPosition(
          engine.Vector.New(
            pin.mapX,
            pin.mapY or 0,
            pin.mapZ
          )
        )
        pin.iconGO:Show()
        UI.SetIsClickable(pin.iconGO)
      end)
    end

    if not CompletionistMapV100_IsNornirKeyRemaining(pin) then
      if pin.iconGO ~= nil then
        pcall(function()
          Map.RecycleIcon(pin.iconGO)
        end)
      end

      if self.completionistMapV100NornirSelected == pin then
        self.completionistMapV100NornirSelected = nil
      end

      table.remove(self.completionistMapV100NornirPins, i)

      print("[CompletionistMap v0.10.1] NORNIR_PIN_REMOVE" ..
        " registryKey=" .. tostring(pin.registryKey) ..
        " index=" .. tostring(pin.keyIndex))
    elseif pin.frames == 30 and pin.iconGO ~= nil then
      local posOK, actual = pcall(function()
        return pin.iconGO:GetWorldPosition()
      end)

      print("[CompletionistMap v0.10.1] NORNIR_PIN_VERIFY" ..
        " index=" .. tostring(pin.keyIndex) ..
        " expectedX=" .. tostring(pin.mapX) ..
        " expectedZ=" .. tostring(pin.mapZ) ..
        " actual=" .. (
          posOK and actual ~= nil and
          ("x=" .. tostring(actual.x) ..
           ",y=" .. tostring(actual.y) ..
           ",z=" .. tostring(actual.z))
          or "<unavailable>"
        ))
    end
  end
end

local function CompletionistMapV100_Description()
  local target = _G.CompletionistMapV100Target
  if target ~= nil and target.type == "Raven" and target.active then
    return "Remaining collectible - tracked on custom compass"
  end
  return "Remaining collectible - Completionist Map"
end

local function CompletionistMapV100_ClearStockCompass(self, reason)
  if self.currShownMarkerID == nil then
    return
  end

  local oldId = self.currShownMarkerID
  local hideOK, hideErr = pcall(function()
    game.Compass.HideMarker(oldId)
  end)

  self.currShownMarkerID = nil

  print("[CompletionistMap v0.10.1] STOCK_COMPASS_CLEAR" ..
    " reason=" .. tostring(reason) ..
    " id=" .. tostring(oldId) ..
    " ok=" .. tostring(hideOK) ..
    " error=" .. tostring(hideErr))
end

local function CompletionistMapV100_ShowReticle(self, currState)
  self.currQuestID = nil
  self.currMarkerID = nil
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false

  self:SetReticleInfo(
    currState,
    "Odin's Raven",
    CompletionistMapV100_Description()
  )

  self:UpdateFooterButtonPrompt(
    currState.menu,
    false,
    false
  )
end

local function CompletionistMapV100_DestroyMapPin(self)
  if self.completionistMapV100MapIconGO ~= nil then
    pcall(function()
      Map.RecycleIcon(self.completionistMapV100MapIconGO)
    end)
  end

  self.completionistMapV100MapIconGO = nil
  self.completionistMapV100BackingMarker = nil
  self.completionistMapV100Selected = false
  self.completionistMapV100Frame = 0
  self.completionistMapV100CurrState = nil
  self.completionistMapV100LastHitFrame = nil
  self.completionistMapV100LastSnapFrame = nil
  self.completionistMapV100CollisionState = false
end

local function CompletionistMapV100_CreateMapPin(self, currState)
  if self.currRealmName ~= "Midgard" then
    return
  end

  CompletionistMapV100_DestroyMapPin(self)

  if CompletionistMapV100_IsRavenCollected() then
    print("[CompletionistMap v0.10.1] MAP_PIN_SKIP reason=raven_collected")
    return
  end

  local backing = CompletionistMapV100_FindBackingDock(self, 1)
  if backing == nil then
    print("[CompletionistMap v0.10.1] MAP_PIN_CREATE" ..
      " ok=false reason=safe_dock_not_found")
    return
  end

  local createOK, iconOrErr = pcall(function()
    return Map.CreateMarkerIcon(
      backing.Id,
      backing.regionId,
      ""
    )
  end)

  if not createOK or iconOrErr == nil then
    print("[CompletionistMap v0.10.1] MAP_PIN_CREATE" ..
      " ok=false reason=duplicate_create_failed" ..
      " error=" .. tostring(iconOrErr))
    return
  end

  local iconGO = iconOrErr
  self.completionistMapV100MapIconGO = iconGO
  self.completionistMapV100BackingMarker = backing
  self.completionistMapV100CurrState = currState
  self.completionistMapV100Frame = 0
  self.completionistMapV100Selected = false
  self.completionistMapV100LastHitFrame = 0
  self.completionistMapV100LastSnapFrame = -9999
  self.completionistMapV100CollisionState = false

  local originalOK, original = pcall(function()
    return iconGO:GetWorldPosition()
  end)

  local mapY = originalOK and original ~= nil and original.y or 0

  local playerYOK, playerPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerYOK and playerPos ~= nil then
    mapY = playerPos.y
  end

  local setOK, setErr = pcall(function()
    iconGO:SetWorldPosition(
      engine.Vector.New(
        COMPLETIONIST_RAVEN_MAP_X,
        mapY,
        COMPLETIONIST_RAVEN_MAP_Z
      )
    )
    iconGO:Show()
    UI.SetIsClickable(iconGO)
    CompletionistMapV100_ApplyZoomAdaptiveIconScale(iconGO)
    CompletionistMapV100_TryDirectIconBind(iconGO, "raven")
  end)

  local afterOK, after = pcall(function()
    return iconGO:GetWorldPosition()
  end)

  print("[CompletionistMap v0.10.1] MAP_PIN_CREATE" ..
    " ok=" .. tostring(setOK) ..
    " error=" .. tostring(setErr) ..
    " backingId=" .. tostring(backing.Id) ..
    " region=" .. tostring(backing.regionId) ..
    " visual=DockPointRoot" ..
    " actual=" .. (afterOK and after ~= nil and
      ("x=" .. tostring(after.x) ..
       ",y=" .. tostring(after.y) ..
       ",z=" .. tostring(after.z))
      or "<error>"))

end

local function CompletionistMapV100_GetZoomAdaptiveIconScale()
  -- Keep temporary DockPoint-backed custom markers at native marker scale.
  -- Magnetic attraction is handled separately at the map-camera level.
  return 1.0, 1.0
end

CompletionistMapV100_ApplyZoomAdaptiveIconScale = function(go)
  if go == nil then return end
  local iconScale = CompletionistMapV100_GetZoomAdaptiveIconScale()
  pcall(function()
    UI.SetGOScale(
      go,
      engine.Vector.New(iconScale, iconScale, iconScale)
    )
  end)
end

local function CompletionistMapV100_UpdateSnapTuning(self)
  local iconScale, cursorScale =
    CompletionistMapV100_GetZoomAdaptiveIconScale()

  local bucket = math.floor(iconScale * 10 + 0.5)
  if self.completionistMapV100SnapScaleBucket ~= bucket then
    self.completionistMapV100SnapScaleBucket = bucket
    print("[CompletionistMap v0.10.1] SNAP_TUNING" ..
      " mode=native_scale_no_camera_snap" ..
      " customIconScale=" .. tostring(iconScale))
  end

  CompletionistMapV100_ApplyZoomAdaptiveIconScale(
    self.completionistMapV100MapIconGO
  )

  for _, pin in ipairs(self.completionistMapV100NornirChestPins or {}) do
    CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
  end

  for _, pin in ipairs(self.completionistMapV100NornirPins or {}) do
    CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
  end
end

local function CompletionistMapV100_SetCustomCursorSelected(selected)
  local goCursorRefnode = util.GetUiObjByName("MapCursor")
  if goCursorRefnode ~= nil then
    animationUtil.SetCursorSelected(goCursorRefnode, selected == true)
  end

  if selected then
    Audio.PlaySound("SND_UX_Pause_Menu_Screen_Map_Region_Hover_Tick")
  end
end

local function CompletionistMapV100_ReinforceRavenPin(self)
  local go = self.completionistMapV100MapIconGO
  if go == nil or CompletionistMapV100_IsRavenCollected() then
    return
  end

  local mapY = 0
  local playerOK, playerMapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerOK and playerMapPos ~= nil then
    mapY = playerMapPos.y
  end

  pcall(function()
    go:SetWorldPosition(
      engine.Vector.New(
        COMPLETIONIST_RAVEN_MAP_X,
        mapY,
        COMPLETIONIST_RAVEN_MAP_Z
      )
    )
    go:Show()
    UI.SetIsClickable(go)
  end)

  self.completionistMapV100RavenPinFrames =
    (self.completionistMapV100RavenPinFrames or 0) + 1

  local activeTarget = _G.CompletionistMapV100Target
  if activeTarget ~= nil and
      activeTarget.active == true and
      activeTarget.type ~= "Raven" and
      self.completionistMapV100RavenIndependentTargetType ~= activeTarget.type then
    self.completionistMapV100RavenIndependentTargetType = activeTarget.type
    print("[CompletionistMap v0.10.1] RAVEN_PIN_INDEPENDENT" ..
      " activeTargetType=" .. tostring(activeTarget.type) ..
      " mapX=" .. tostring(COMPLETIONIST_RAVEN_MAP_X) ..
      " mapZ=" .. tostring(COMPLETIONIST_RAVEN_MAP_Z))
  end

  if self.completionistMapV100RavenPinFrames == 30 then
    local ok, actual = pcall(function() return go:GetWorldPosition() end)
    print("[CompletionistMap v0.10.1] RAVEN_PIN_VERIFY" ..
      " expectedX=" .. tostring(COMPLETIONIST_RAVEN_MAP_X) ..
      " expectedZ=" .. tostring(COMPLETIONIST_RAVEN_MAP_Z) ..
      " activeTargetType=" .. tostring(
        _G.CompletionistMapV100Target and
        _G.CompletionistMapV100Target.type or "<nil>"
      ) ..
      " actual=" .. (
        ok and actual ~= nil and
        ("x=" .. tostring(actual.x) ..
         ",y=" .. tostring(actual.y) ..
         ",z=" .. tostring(actual.z))
        or "<unavailable>"
      ))
  end
end

local COMPLETIONIST_FILTER = -101
local RAVEN_FILTER = -102
local NORNIR_CHEST_FILTER = -103
local NORNIR_PUZZLE_FILTER = -104

local completionistFilterLabels = {
  [COMPLETIONIST_FILTER] = "COMPLETIONIST",
  [RAVEN_FILTER] = "RAVENS",
  [NORNIR_CHEST_FILTER] = "NORNIR CHESTS",
  [NORNIR_PUZZLE_FILTER] = "NORNIR PUZZLE"
}

local function CompletionistMapV100_GetFilterKind(self)
  if self.filterButtonMapping == nil then return 1 end
  return self.filterButtonMapping[self.filterIndex] or 1
end

local function CompletionistMapV100_SetGOVisible(go, visible)
  if go == nil then return end
  pcall(function()
    if visible then go:Show() else go:Hide() end
  end)
end

local function CompletionistMapV100_RefreshCustomPins(self)
  CompletionistMapV100_UpdateSnapTuning(self)

  local filter = CompletionistMapV100_GetFilterKind(self)
  local showRaven = filter == 1 or
    filter == COMPLETIONIST_FILTER or filter == RAVEN_FILTER
  local showChest = filter == 1 or
    filter == COMPLETIONIST_FILTER or filter == NORNIR_CHEST_FILTER
  local showPuzzle = filter == NORNIR_PUZZLE_FILTER
  local registry = CompletionistMapV100_GetNornirRegistry()

  CompletionistMapV100_ReinforceRavenPin(self)

  CompletionistMapV100_SetGOVisible(
    self.completionistMapV100MapIconGO,
    showRaven and not CompletionistMapV100_IsRavenCollected()
  )

  for _, pin in ipairs(self.completionistMapV100NornirChestPins or {}) do
    CompletionistMapV100_SetGOVisible(pin.iconGO, showChest)
  end

  if not self.completionistMapV100AliasCheckLogged then
    self.completionistMapV100AliasCheckLogged = true
    local raven = self.completionistMapV100MapIconGO

    for _, chestPin in ipairs(self.completionistMapV100NornirChestPins or {}) do
      print("[CompletionistMap v0.10.1] ALIAS_CHECK" ..
        " pair=raven_chest" ..
        " sameGO=" .. tostring(
          raven ~= nil and raven == chestPin.iconGO
        ))
    end

    local pins = self.completionistMapV100NornirPins or {}
    for i = 1, #pins do
      if raven ~= nil then
        print("[CompletionistMap v0.10.1] ALIAS_CHECK" ..
          " pair=raven_puzzle" ..
          " index=" .. tostring(pins[i].keyIndex) ..
          " sameGO=" .. tostring(raven == pins[i].iconGO))
      end

      for j = i + 1, #pins do
        print("[CompletionistMap v0.10.1] ALIAS_CHECK" ..
          " pair=puzzle_puzzle" ..
          " a=" .. tostring(pins[i].keyIndex) ..
          " b=" .. tostring(pins[j].keyIndex) ..
          " sameGO=" .. tostring(pins[i].iconGO == pins[j].iconGO))
      end
    end
  end

  for _, pin in ipairs(self.completionistMapV100NornirPins or {}) do
    local entry = registry and registry[pin.registryKey] or nil
    local revealInShowAll =
      filter == 1 and
      entry ~= nil and
      entry.puzzleRevealed == true and
      entry.challengeComplete ~= true and
      entry.opened ~= true

    CompletionistMapV100_SetGOVisible(
      pin.iconGO,
      showPuzzle or revealInShowAll
    )
  end

  if not showRaven then self.completionistMapV100Selected = false end
  if not showChest then self.completionistMapV100NornirChestSelected = nil end

  if self.completionistMapV100NornirSelected ~= nil then
    local selectedPin = self.completionistMapV100NornirSelected
    local selectedEntry =
      registry and registry[selectedPin.registryKey] or nil

    local selectedPuzzleVisible =
      showPuzzle or
      (
        filter == 1 and
        selectedEntry ~= nil and
        selectedEntry.puzzleRevealed == true and
        selectedEntry.challengeComplete ~= true and
        selectedEntry.opened ~= true
      )

    if not selectedPuzzleVisible then
      self.completionistMapV100NornirSelected = nil
    end
  end

  if self.completionistMapV100LastVisibilityFilter ~= filter then
    self.completionistMapV100LastVisibilityFilter = filter
    print("[CompletionistMap v0.10.1] FILTER_CUSTOM_VISIBILITY" ..
      " filter=" .. tostring(filter) ..
      " raven=" .. tostring(showRaven) ..
      " chest=" .. tostring(showChest) ..
      " puzzleFilter=" .. tostring(showPuzzle) ..
      " puzzleAfterAttempt=" .. tostring(filter == 1))
  end
end

local function CompletionistMapV100_CollisionContainsPin(
  self,
  collisionGameObjectTable
)
  if type(collisionGameObjectTable) ~= "table" or
      self.completionistMapV100MapIconGO == nil then
    return false
  end

  for _, collGO in ipairs(collisionGameObjectTable) do
    if collGO == self.completionistMapV100MapIconGO then
      return true
    end
  end

  return false
end
'@

$mapHelper = $mapHelper.Replace('__COMPLETIONIST_ICON_ROOT__', $CompletionistIconLuaRoot)

$mapText = $mapText.Replace(
    'local alwaysOnMarkerFlags = {',
    $mapHelper + "`r`nlocal alwaysOnMarkerFlags = {"
)

$mapCalibrationAnchor =
    '    Map.SetPlayerMapMarkerToPlayerMapTransform(self.playerIconGO, "facingJoint", "arrowJoint")'

if (-not $mapText.Contains($mapCalibrationAnchor)) {
    throw 'Could not locate stock player map transform call.'
}

$mapText = $mapText.Replace(
    $mapCalibrationAnchor,
    $mapCalibrationAnchor +
      "`r`n    CompletionistMapV100_LogMapCalibration(self)"
)

$mapText = $mapText.Replace(
    '  UI.WorldUIRender(map_camera.Name)',
    "  CompletionistMapV100_CreateMapPin(self, currState)`r`n  CompletionistMapV100_CreateNornirChestPins(self, currState)`r`n  CompletionistMapV100_CreateNornirPins(self, currState)`r`n  CompletionistMapV100_RefreshCustomPins(self)`r`n  UI.WorldUIRender(map_camera.Name)"
)

$mapUpdateRegex = [regex]::new('function MapOn:Update\(\)\r?\n')
if (-not $mapUpdateRegex.IsMatch($mapText)) {
    throw 'Could not locate MapOn:Update.'
}

$mapUpdateInjection = @'
function MapOn:Update()
  self.completionistMapV100Frame =
    (self.completionistMapV100Frame or 0) + 1

  CompletionistMapV100_RefreshNornirPins(self)
  CompletionistMapV100_RefreshNornirChestPins(self)
  CompletionistMapV100_IsTargetCollected()
  CompletionistMapV100_RefreshCustomPins(self)

  if CompletionistMapV100_IsRavenCollected() then
    if self.completionistMapV100MapIconGO ~= nil then
      CompletionistMapV100_DestroyMapPin(self)
      print("[CompletionistMap v0.10.1] MAP_PIN_REMOVE reason=raven_collected")
    end
  end
'@

$mapText = $mapUpdateRegex.Replace(
    $mapText,
    [System.Text.RegularExpressions.MatchEvaluator]{
      param($m) $mapUpdateInjection
    },
    1
)

if (-not $mapText.Contains('[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED')) {
    throw 'Map-side Completionist helper was not injected.'
}

if (-not $mapText.Contains('CompletionistMapV100_RefreshCustomPins(self)')) {
    throw 'MapOn:Update Completionist refresh hook was not injected.'
}

if (-not $mapText.Contains('if Camera.GetCursorScaleValue then')) {
    throw 'Stock MapOn:Update body is missing after Completionist injection.'
}

if (-not $mapText.Contains('local CompletionistMapV100_GetNornirRegistry')) {
    throw 'Nornir registry helper forward declaration is missing.'
}

if (-not $mapText.Contains('CompletionistMapV100_GetNornirRegistry = function()')) {
    throw 'Nornir registry helper assignment is missing.'
}

if ($mapText.Contains('Camera.PointAt(') -and
    $mapText.Contains('preservesZoom=true')) {
    # Stock mapmenu legitimately contains Camera.PointAt elsewhere. Custom
    # collision blocks are validated below by their explicit native snap logs.
}

if (-not $mapText.Contains('RAVEN_PIN_VERIFY')) {
    throw 'Raven pin position reinforcement is missing.'
}

if (-not $mapText.Contains('ICON_CAPS')) {
    throw 'v0.10.1 map icon capability probe is missing.'
}


if (-not $mapText.Contains('STOCK_COMPASS_CLEAR')) {
    throw 'Stock/custom compass isolation helper is missing.'
}

if (-not $mapText.Contains('local CompletionistMapV100_ApplyZoomAdaptiveIconScale')) {
    throw 'Adaptive-scale helper forward declaration is missing.'
}

if (-not $mapText.Contains('CompletionistMapV100_ApplyZoomAdaptiveIconScale = function(go)')) {
    throw 'Adaptive-scale helper assignment is missing.'
}

if (-not $mapText.Contains('CursorScale_Min = 0.05')) {
    throw 'Close-zoom cursor scale patch is missing.'
}

if (-not $mapText.Contains('CursorSnap_Enabled = 0')) {
    throw 'Cursor snap disable patch is missing.'
}

if (-not $mapText.Contains('CursorSnap_Strength = 0.0')) {
    throw 'Zero cursor snap strength patch is missing.'
}

$submenuExitRegex = [regex]::new('function MapOn:SubmenuExit\(currState\)\r?\n')
$mapText = $submenuExitRegex.Replace(
    $mapText,
    "function MapOn:SubmenuExit(currState)`r`n  CompletionistMapV100_DestroyNornirChestPins(self)`r`n  CompletionistMapV100_DestroyNornirPins(self)`r`n  CompletionistMapV100_DestroyMapPin(self)`r`n",
    1
)

$mapExitRegex = [regex]::new('function MapOn:Exit\(\)\r?\n')
$mapText = $mapExitRegex.Replace(
    $mapText,
    "function MapOn:Exit()`r`n  CompletionistMapV100_DestroyNornirChestPins(self)`r`n  CompletionistMapV100_DestroyNornirPins(self)`r`n  CompletionistMapV100_DestroyMapPin(self)`r`n",
    1
)

$playerMarkerLine =
    '  local showPlayerMarker = playerRealm == self.currRealmName and self.playerIconGO ~= nil'

if (-not $mapText.Contains($playerMarkerLine)) {
    throw 'Could not locate stock ShouldShowPlayerMarker line.'
}

$mapText = $mapText.Replace(
    $playerMarkerLine,
    @'
  local showPlayerMarker =
    playerRealm == self.currRealmName and
    self.playerIconGO ~= nil and
    _G.CompletionistMapV100PlayerMarkerVisible ~= false
'@
)

$goJournalLine =
    '  currMenu:UpdateFooterButton("GoToJournal", showGoToJournal and not self.isOpenedForFastTravel)'

if (-not $mapText.Contains($goJournalLine)) {
    throw 'Could not locate GoToJournal footer update line.'
}

$mapText = $mapText.Replace(
    $goJournalLine,
    @'
  local showPlayerToggle =
    not showGoToJournal and
    not self.isOpenedForFastTravel and
    mapUtil.GetPlayerRealm() == self.currRealmName

  if showPlayerToggle then
    local playerToggleText =
      _G.CompletionistMapV100PlayerMarkerVisible == false and
      "[SquareButton] Show Kratos" or
      "[SquareButton] Hide Kratos"

    currMenu:UpdateFooterButton(
      "GoToJournal",
      true,
      playerToggleText
    )
  else
    currMenu:UpdateFooterButton(
      "GoToJournal",
      showGoToJournal and not self.isOpenedForFastTravel
    )
  end
'@
)

$submenuEnterActivate =
    '  currState.menu:Activate()'

if (-not $mapText.Contains($submenuEnterActivate)) {
    throw 'Could not locate SubmenuEnter menu activation.'
}

$mapText = $mapText.Replace(
    $submenuEnterActivate,
    "  currState.menu:Activate()`r`n  self.completionistMapV100Menu = currState.menu"
)

$hiddenPlayerFocusRegex =
    [regex]::new(
      '  elseif showPlayerMarker then\r?\n' +
      '    local instant = true\r?\n' +
      '    Camera\.PointAtGO\(self\.playerIconGO, instant\)\r?\n' +
      '  elseif Camera\.PointAt ~= nil then'
    )

$hiddenPlayerFocusMatches = $hiddenPlayerFocusRegex.Matches($mapText)
if ($hiddenPlayerFocusMatches.Count -ne 1) {
    throw "Expected one stock player-focus fallback block, found $($hiddenPlayerFocusMatches.Count)."
}

$hiddenPlayerFocusReplacement = @'
  elseif showPlayerMarker then
    local instant = true
    Camera.PointAtGO(self.playerIconGO, instant)
  elseif _G.CompletionistMapV100PlayerMarkerVisible == false and
      mapUtil.GetPlayerRealm() == self.currRealmName and
      self.playerIconGO ~= nil then
    local instant = true
    Camera.PointAtGO(self.playerIconGO, instant)
    print("[CompletionistMap v0.10.1] PLAYER_HIDDEN_CENTER" ..
      " centered=true realm=" .. tostring(self.currRealmName))
  elseif Camera.PointAt ~= nil then
'@

$mapText = $hiddenPlayerFocusRegex.Replace(
    $mapText,
    $hiddenPlayerFocusReplacement,
    1
)

if (-not $mapText.Contains('PLAYER_HIDDEN_CENTER')) {
    throw 'Hidden-Kratos opening-centre patch was not applied.'
}

$squareRegex =
    [regex]::new('function MapOn:Menu_Square_ReleaseHandler\(\)\r?\n')

$squareInjection = @'
function MapOn:Menu_Square_ReleaseHandler()
  local currRootQuestID = questUtil.GetRootQuestID(self.currQuestID)

  if not questUtil.IsValidID(currRootQuestID) then
    _G.CompletionistMapV100PlayerMarkerVisible =
      not (_G.CompletionistMapV100PlayerMarkerVisible ~= false)

    local visible =
      _G.CompletionistMapV100PlayerMarkerVisible ~= false

    if self.playerIconGO ~= nil then
      if visible and self:ShouldShowPlayerMarker() then
        self.playerIconGO:Show()
      else
        self.playerIconGO:Hide()
      end
    end

    if self.completionistMapV100Menu ~= nil then
      local text =
        visible and
        "[SquareButton] Hide Kratos" or
        "[SquareButton] Show Kratos"

      self.completionistMapV100Menu:UpdateFooterButton(
        "GoToJournal",
        true,
        text
      )
      self.completionistMapV100Menu:UpdateFooterButtonText()
    end

    print("[CompletionistMap v0.10.1] PLAYER_MARKER_TOGGLE" ..
      " visible=" .. tostring(visible))
    Audio.PlaySound("SND_UX_Pause_Menu_Map_Region_Hover_Tick")
    return
  end
'@

$mapText = $squareRegex.Replace(
    $mapText,
    [System.Text.RegularExpressions.MatchEvaluator]{
      param($m) $squareInjection
    },
    1
)

$collisionRegex =
    [regex]::new('function MapOn:MapCollisionChangeHandler\(currState, collisionGameObjectTable, realmName\)\r?\n')

$collisionInjection = @'
function MapOn:MapCollisionChangeHandler(currState, collisionGameObjectTable, realmName)
  -- Child puzzle actors take priority over their parent chest when their
  -- clickable roots overlap at high zoom.
  local completionistMapV100NornirPin =
    CompletionistMapV100_FindNornirCollision(
      self,
      collisionGameObjectTable
    )

  if completionistMapV100NornirPin ~= nil then
    self.completionistMapV100NornirSelected =
      completionistMapV100NornirPin
    self.completionistMapV100NornirLastHitFrame =
      self.completionistMapV100Frame or 0
    self.completionistMapV100NornirChestSelected = nil
    self.completionistMapV100Selected = false

    CompletionistMapV100_SetCustomCursorSelected(true)

    CompletionistMapV100_NornirReticle(
      self,
      currState,
      completionistMapV100NornirPin
    )

    print("[CompletionistMap v0.10.1] NORNIR_SELECTION" ..
      " active=true" ..
      " registryKey=" ..
        tostring(completionistMapV100NornirPin.registryKey) ..
      " index=" ..
        tostring(completionistMapV100NornirPin.keyIndex) ..
      " priority=child" ..
      " snapMode=native_cursor" ..
      " preservesZoom=true")
    return
  end

  if self.completionistMapV100NornirSelected ~= nil then
    local frame = self.completionistMapV100Frame or 0
    local lastHit =
      self.completionistMapV100NornirLastHitFrame or frame

    if frame - lastHit <= 12 then
      return
    end

    self.completionistMapV100NornirSelected = nil
    print("[CompletionistMap v0.10.1] NORNIR_SELECTION cleared=true" ..
      " latchFrames=12")
  end

  local completionistMapV100ChestPin =
    CompletionistMapV100_FindNornirChestCollision(
      self, collisionGameObjectTable
    )

  if completionistMapV100ChestPin ~= nil then
    self.completionistMapV100NornirChestSelected = completionistMapV100ChestPin
    self.completionistMapV100NornirSelected = nil
    self.completionistMapV100Selected = false
    CompletionistMapV100_SetCustomCursorSelected(true)
    CompletionistMapV100_NornirChestReticle(
      self, currState, completionistMapV100ChestPin
    )
    print("[CompletionistMap v0.10.1] NORNIR_CHEST_SELECTION" ..
      " active=true registryKey=" ..
        tostring(completionistMapV100ChestPin.registryKey) ..
      " priority=parent" ..
      " snapMode=native_cursor" ..
      " preservesZoom=true")
    return
  end

  self.completionistMapV100NornirChestSelected = nil

  local completionistMapV100IsCustom =
    CompletionistMapV100_CollisionContainsPin(
      self,
      collisionGameObjectTable
    )

  if completionistMapV100IsCustom then
    local frame = self.completionistMapV100Frame or 0
    self.completionistMapV100LastHitFrame = frame

    if not self.completionistMapV100CollisionState then
      print("[CompletionistMap v0.10.1] MAP_COLLISION hit=true")
    end
    self.completionistMapV100CollisionState = true

    if not self.completionistMapV100Selected then
      self.completionistMapV100Selected = true
      print("[CompletionistMap v0.10.1] MAP_SELECTION active=true")
    end

    CompletionistMapV100_SetCustomCursorSelected(true)
    CompletionistMapV100_ShowReticle(self, currState)

    if not self.completionistMapV100NativeSnapLogged then
      self.completionistMapV100NativeSnapLogged = true
      print("[CompletionistMap v0.10.1] MAP_SNAP" ..
        " mode=native_cursor" ..
        " preservesZoom=true" ..
        " frame=" .. tostring(frame))
    end
    return
  end

  if self.completionistMapV100CollisionState then
    print("[CompletionistMap v0.10.1] MAP_COLLISION hit=false_debounced")
  end
  self.completionistMapV100CollisionState = false

  if self.completionistMapV100Selected then
    local frame = self.completionistMapV100Frame or 0
    local lastHit = self.completionistMapV100LastHitFrame or 0
    local age = frame - lastHit

    if age <= 6 then
      return
    end

    self.completionistMapV100Selected = false
    print("[CompletionistMap v0.10.1] MAP_SELECTION cleared=true" ..
      " ageFrames=" .. tostring(age))
  end
'@

$mapText = $collisionRegex.Replace(
    $mapText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $collisionInjection },
    1
)

if (-not $mapText.Contains('snapMode=native_cursor')) {
    throw 'Custom marker native cursor-snap path was not injected.'
}

if (-not $mapText.Contains('preservesZoom=true')) {
    throw 'Custom marker zoom-preservation path was not injected.'
}

if ($collisionInjection.Contains('Camera.PointAt(')) {
    throw 'Custom collision injection still contains Camera.PointAt.'
}

$promptRegex =
    [regex]::new('function MapOn:GetShowOnCompassPrompt\(currMenu\)\r?\n')

$promptInjection = @'
function MapOn:GetShowOnCompassPrompt(currMenu)
  if self.completionistMapV100NornirChestSelected ~= nil then
    local pin = self.completionistMapV100NornirChestSelected
    if not CompletionistMapV100_IsNornirChestRemaining(pin) then
      return false, nil
    end
    if self.isOpenedForFastTravel or
        not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then
      return false, nil
    end
    local target = _G.CompletionistMapV100Target
    local sameTarget = target ~= nil and
      target.type == "NornirChest" and
      target.registryKey == pin.registryKey
    local lamsId = sameTarget and target.active and
      lamsConsts.RemoveFromCompass or lamsConsts.AddToCompass
    return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  if self.completionistMapV100NornirSelected ~= nil then
    local pin = self.completionistMapV100NornirSelected

    if not CompletionistMapV100_IsNornirKeyRemaining(pin) then
      return false, nil
    end

    if self.isOpenedForFastTravel or
        not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then
      return false, nil
    end

    local target = _G.CompletionistMapV100Target
    local sameTarget =
      target ~= nil and
      target.type == "NornirPuzzle" and
      target.registryKey == pin.registryKey and
      target.keyIndex == pin.keyIndex

    local lamsId =
      sameTarget and target.active and
      lamsConsts.RemoveFromCompass or
      lamsConsts.AddToCompass

    if self.completionistMapV100NornirPromptLogged ~= pin.keyIndex then
      self.completionistMapV100NornirPromptLogged = pin.keyIndex
      print("[CompletionistMap v0.10.1] NORNIR_PROMPT" ..
        " visible=true" ..
        " index=" .. tostring(pin.keyIndex) ..
        " active=" .. tostring(sameTarget and target.active == true))
    end

    return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  if self.completionistMapV100Selected then
    if CompletionistMapV100_IsRavenCollected() then
      return false, nil
    end

    if self.isOpenedForFastTravel or
        not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then
      return false, nil
    end

    local target = _G.CompletionistMapV100Target
    local sameTarget = target ~= nil and target.type == "Raven"
    local lamsId =
      sameTarget and target.active and
      lamsConsts.RemoveFromCompass or
      lamsConsts.AddToCompass

    return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end
'@

$mapText = $promptRegex.Replace(
    $mapText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $promptInjection },
    1
)

$showRegex =
    [regex]::new('function MapOn:ShowOnCompass\(currState\)\r?\n')

$showInjection = @'
function MapOn:ShowOnCompass(currState)
  if self.completionistMapV100NornirChestSelected ~= nil then
    CompletionistMapV100_ClearStockCompass(self, "custom_nornir_chest")
    local pin = self.completionistMapV100NornirChestSelected
    if not CompletionistMapV100_IsNornirChestRemaining(pin) then
      self.completionistMapV100NornirChestSelected = nil
      return
    end
    local target = _G.CompletionistMapV100Target
    local sameTarget = target ~= nil and
      target.type == "NornirChest" and
      target.registryKey == pin.registryKey
    if sameTarget and target.active then
      target.active = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
    else
      target.type = "NornirChest"
      target.realm = "Midgard"
      target.registryKey = pin.registryKey
      target.keyIndex = nil
      target.regionQuest = nil
      target.x = pin.worldX
      target.y = pin.worldY
      target.z = pin.worldZ
      target.mapX = pin.mapX
      target.mapZ = pin.mapZ
      target.collected = false
      target.active = true
      _G.CompletionistMapV100TargetCollectedNornirLogged = false
      _G.CompletionistMapV100NornirTargetGeneration =
        (_G.CompletionistMapV100NornirTargetGeneration or 0) + 1
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    end
    CompletionistMapV100_NornirChestReticle(self, currState, pin)
    print("[CompletionistMap v0.10.1] NORNIR_CHEST_COMPASS" ..
      " active=" .. tostring(target.active) ..
      " registryKey=" .. tostring(pin.registryKey) ..
      " x=" .. tostring(pin.worldX) ..
      " y=" .. tostring(pin.worldY) ..
      " z=" .. tostring(pin.worldZ))
    return
  end

  if self.completionistMapV100NornirSelected ~= nil then
    CompletionistMapV100_ClearStockCompass(self, "custom_nornir_puzzle")
    local pin = self.completionistMapV100NornirSelected

    if not CompletionistMapV100_IsNornirKeyRemaining(pin) then
      self.completionistMapV100NornirSelected = nil
      return
    end

    local target = _G.CompletionistMapV100Target
    local sameTarget =
      target ~= nil and
      target.type == "NornirPuzzle" and
      target.registryKey == pin.registryKey and
      target.keyIndex == pin.keyIndex

    if sameTarget and target.active then
      target.active = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
    else
      target.type = "NornirPuzzle"
      target.realm = "Midgard"
      target.registryKey = pin.registryKey
      target.keyIndex = pin.keyIndex
      target.keyType = pin.keyType
      target.regionQuest = nil
      target.x = pin.worldX
      target.y = pin.worldY
      target.z = pin.worldZ
      target.mapX = pin.mapX
      target.mapZ = pin.mapZ
      target.collected = false
      target.active = true
      _G.CompletionistMapV100NornirTargetGeneration =
        (_G.CompletionistMapV100NornirTargetGeneration or 0) + 1
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    end

    CompletionistMapV100_NornirReticle(self, currState, pin)

    print("[CompletionistMap v0.10.1] NORNIR_COMPASS" ..
      " active=" .. tostring(target.active) ..
      " registryKey=" .. tostring(pin.registryKey) ..
      " index=" .. tostring(pin.keyIndex) ..
      " x=" .. tostring(pin.worldX) ..
      " y=" .. tostring(pin.worldY) ..
      " z=" .. tostring(pin.worldZ))
    return
  end

  if self.completionistMapV100Selected then
    CompletionistMapV100_ClearStockCompass(self, "custom_raven")
    local target = _G.CompletionistMapV100Target

    if CompletionistMapV100_IsRavenCollected() then
      if target ~= nil and target.type == "Raven" then
        target.active = false
        target.collected = true
      end
      self.completionistMapV100Selected = false
      print("[CompletionistMap v0.10.1] CUSTOM_COMPASS refused=raven_collected")
      return
    end

    local sameTarget = target ~= nil and target.type == "Raven"

    if sameTarget and target.active then
      target.active = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
    else
      target.type = "Raven"
      target.realm = "Midgard"
      target.regionQuest = "RegionSummary_VF_Raven_Parent"
      target.registryKey = nil
      target.keyIndex = nil
      target.x = COMPLETIONIST_RAVEN_WORLD_X
      target.y = COMPLETIONIST_RAVEN_WORLD_Y
      target.z = COMPLETIONIST_RAVEN_WORLD_Z
      target.mapX = COMPLETIONIST_RAVEN_MAP_X
      target.mapZ = COMPLETIONIST_RAVEN_MAP_Z
      target.collected = false
      target.active = true
      _G.CompletionistMapV100TargetCollectedNornirLogged = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    end

    CompletionistMapV100_ShowReticle(self, currState)

    print("[CompletionistMap v0.10.1] CUSTOM_COMPASS" ..
      " active=" .. tostring(target.active) ..
      " mode=hud_native_visual_proof" ..
      " x=" .. tostring(target.x) ..
      " y=" .. tostring(target.y) ..
      " z=" .. tostring(target.z))
    return
  end
  local completionistTarget = _G.CompletionistMapV100Target
  if completionistTarget ~= nil and
      completionistTarget.active == true and
      self.currMarkerID ~= nil then
    completionistTarget.active = false
    print("[CompletionistMap v0.10.1] CUSTOM_COMPASS_CLEAR" ..
      " reason=stock_marker_selected" ..
      " type=" .. tostring(completionistTarget.type))
  end

'@

$mapText = $showRegex.Replace(
    $mapText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $showInjection },
    1
)

$filterFunctionsRegex = [regex]::new(
    'function MapOn:Menu_Next_Filter\(direction\).*?function MapOn:ShowOnCompass\(currState\)',
    [System.Text.RegularExpressions.RegexOptions]::Singleline
)

if (-not $filterFunctionsRegex.IsMatch($mapText)) {
    throw 'Could not locate stock map filter function block.'
}

$filterFunctionsReplacement = @'
function MapOn:Menu_Next_Filter(direction)
  if self.isOpenedForFastTravel then return end
  self.filterIndex =
    (self.filterIndex + direction - 1) % #self.filterButtonMapping + 1

  local logical = self.filterButtonMapping[self.filterIndex]
  if logical ~= nil and logical > 0 then
    self.markerIncludeFlags = markerFilters[logical].markerIncludeFlags
    self:GetAlwaysOnMarkers()
    self:GetMarkers()
  else
    self:ClearMarkers(true)
  end

  self:UpdateIcons()
  CompletionistMapV100_RefreshCustomPins(self)
  self:UpdateFilterUI()
  self.jumpToMarkerIndex = 0
  self:UpdateMapMarkerHighlights()
  Audio.PlaySound("SND_UX_Pause_Menu_Map_Filters_Tick")
  print("[CompletionistMap v0.10.1] FILTER_CHANGE" ..
    " logical=" .. tostring(logical) ..
    " index=" .. tostring(self.filterIndex))
end

function MapOn:UpdateFilterButtonMapping()
  self.filterButtonMapping = {1}
  self.filterIndex = 1
  self.markerIncludeFlags = markerFilters[1].markerIncludeFlags

  for filterIndex = 2, #markerFilters do
    local markerIncludeFlags = markerFilters[filterIndex].markerIncludeFlags
    for i = 1, #self.realmMarkerInfo do
      local markerInfo = self.realmMarkerInfo[i]
      if Map.MarkerHasAnyFlag(markerInfo.Id, markerIncludeFlags) and
          mapUtil.MapMarkerInfoHasStates(markerInfo, markerStates) then
        self.filterButtonMapping[#self.filterButtonMapping + 1] = filterIndex
        break
      end
    end
  end

  if self.currRealmName == "Midgard" then
    self.filterButtonMapping[#self.filterButtonMapping + 1] = COMPLETIONIST_FILTER
    self.filterButtonMapping[#self.filterButtonMapping + 1] = RAVEN_FILTER
    self.filterButtonMapping[#self.filterButtonMapping + 1] = NORNIR_CHEST_FILTER
    self.filterButtonMapping[#self.filterButtonMapping + 1] = NORNIR_PUZZLE_FILTER

    print("[CompletionistMap v0.10.1] FILTER_MAPPING" ..
      " total=" .. tostring(#self.filterButtonMapping) ..
      " completionist=true")
  end

  self:UpdateFilterUI()
end

function MapOn:UpdateFilterUI()
  local logical = self.filterButtonMapping[self.filterIndex] or 1
  local label = completionistFilterLabels[logical]
  if label ~= nil then
    UI.SetText(self.thFilterLabel, label)
  else
    UI.SetText(self.thFilterLabel, util.GetLAMSMsg(markerFilters[logical].name))
  end

  local total = #self.filterButtonMapping
  local visible = math.min(#self.goFilterButtons, total)
  local first = 1
  if total > visible then
    first = self.filterIndex - math.floor(visible / 2)
    if first < 1 then first = 1 end
    local maxFirst = total - visible + 1
    if first > maxFirst then first = maxFirst end
  end
  self.completionistMapV100FilterWindowFirst = first

  local posOffset = (#self.goFilterButtons - visible) * 0.2
  for slot = 1, #self.goFilterButtons do
    local button = self.goFilterButtons[slot]
    if slot <= visible then
      local logicalIndex = first + slot - 1
      local pos = engine.Vector.New(
        self.goFilterButtonPositions[slot].x + posOffset,
        self.goFilterButtonPositions[slot].y,
        self.goFilterButtonPositions[slot].z
      )
      button:SetWorldPosition(pos)
      button:Show()
      local selected = logicalIndex == self.filterIndex
      UI.Anim(
        button,
        consts.AS_Forward,
        "",
        consts.DEFAULT_BUTTON_ANIM_RATE,
        selected and 0 or 0.5,
        selected and 0.5 or 1
      )
    else
      UI.Anim(button, consts.AS_Reset, "", 0, 0)
      button:Hide()
    end
  end
end
function MapOn:ShowOnCompass(currState)
'@

$mapText = $filterFunctionsRegex.Replace(
    $mapText,
    [System.Text.RegularExpressions.MatchEvaluator]{
      param($m) $filterFunctionsReplacement
    },
    1
)

$mouseFilterRegex = [regex]::new(
    'for key, button in ipairs\(self\.goFilterButtons\) do\r?\n    if UI\.GetEventSenderGameObject\(\) == button then\r?\n      self:Menu_Next_Filter\(key - self\.filterIndex\)\r?\n    end\r?\n  end'
)

$mouseFilterReplacement = @'
for key, button in ipairs(self.goFilterButtons) do
    if UI.GetEventSenderGameObject() == button then
      local first = self.completionistMapV100FilterWindowFirst or 1
      local desired = first + key - 1
      if desired <= #self.filterButtonMapping then
        self:Menu_Next_Filter(desired - self.filterIndex)
      end
      return
    end
  end
'@

$mapText = $mouseFilterRegex.Replace(
    $mapText,
    [System.Text.RegularExpressions.MatchEvaluator]{
      param($m) $mouseFilterReplacement
    },
    1
)

$hudHelper = @'
-- Completionist Map v0.10.1
-- HUD-native visual proof using an already-authored HUD object.
--
-- v0.7.6 proved there is no Lua-visible Clone/Create/Instantiate API for HUD
-- GameObjects. The safe route is therefore to borrow a pre-authored HUD object
-- that already belongs to the gameplay HUD render context.
--
-- R3_L3 is deliberately used only as a temporary proof visual. It is small,
-- HUD-native, and normally hidden outside specific mechanic prompts.
-- If it moves correctly along the compass, the renderer problem is solved.
--
-- No native Compass.ShowMarker call is used.

local completionistMapV100HudIconCapsLogged = false

local function CompletionistMapV100_ProbeHudIconApi(go)
  if completionistMapV100HudIconCapsLogged or go == nil then return end
  completionistMapV100HudIconCapsLogged = true

  local function callable(container, name)
    if container == nil then return false end
    local ok, value = pcall(function() return container[name] end)
    return ok and type(value) == "function"
  end

  local names = {
    "SetTexture",
    "SetTextureName",
    "SetImage",
    "SetImagePath",
    "SetSprite",
    "SetMaterialSwap"
  }
  local parts = {}
  for _, name in ipairs(names) do
    parts[#parts + 1] = name .. "=" .. tostring(callable(go, name))
  end

  print("[CompletionistMap v0.10.1] HUD_ICON_CAPS" ..
    " go={" .. table.concat(parts, ",") .. "}" ..
    " assetRoot=__COMPLETIONIST_ICON_ROOT__")
end

local function CompletionistMapV100_GetProofVisual(self)
  if self.completionistMapV100ProofGO ~= nil then
    return self.completionistMapV100ProofGO
  end

  local candidates = {
    "R3_L3",
    "BuffLogTimer",
    "MechanicsMeter"
  }

  for _, name in ipairs(candidates) do
    local ok, go = pcall(function()
      return util.GetUiObjByName(name)
    end)

    if ok and go ~= nil then
      local nameOK, actualName = pcall(function()
        return go:GetName()
      end)

      local posOK, pos = pcall(function()
        return go:GetWorldPosition()
      end)

      self.completionistMapV100ProofGO = go
      self.completionistMapV100ProofName =
        nameOK and actualName or name

      if posOK and pos ~= nil then
        self.completionistMapV100ProofOrigin =
          engine.Vector.New(pos.x, pos.y, pos.z)
      end

      print("[CompletionistMap v0.10.1] HUD_VISUAL_SELECTED" ..
        " requested=" .. tostring(name) ..
        " actual=" .. tostring(self.completionistMapV100ProofName) ..
        " origin=" .. (
          posOK and pos ~= nil and
          ("x=" .. tostring(pos.x) ..
           ",y=" .. tostring(pos.y) ..
           ",z=" .. tostring(pos.z))
          or "<unavailable>"
        ))

      return go
    end
  end

  if not self.completionistMapV100MissingVisualLogged then
    self.completionistMapV100MissingVisualLogged = true
    print("[CompletionistMap v0.10.1] HUD_VISUAL_SELECTED ok=false")
  end

  return nil
end

local function CompletionistMapV100_RestoreProofVisual(self)
  local go = self.completionistMapV100ProofGO
  if go == nil then
    return
  end

  if self.completionistMapV100ProofWasActive and
      self.completionistMapV100ProofOrigin ~= nil then
    local restoreOK, restoreErr = pcall(function()
      go:SetWorldPosition(
        self.completionistMapV100ProofOrigin
      )
      go:Hide()
    end)

    print("[CompletionistMap v0.10.1] HUD_VISUAL_RESTORE" ..
      " ok=" .. tostring(restoreOK) ..
      " error=" .. tostring(restoreErr))
  end

  self.completionistMapV100ProofWasActive = false
end

local function CompletionistMapV100_StoreNornirUIState(args)
  if args == nil or args.registryKey == nil then return end
  _G.CompletionistMapV100NornirRegistry =
    _G.CompletionistMapV100NornirRegistry or {}
  _G.CompletionistMapV100NornirRegistry[args.registryKey] = args

  local target = _G.CompletionistMapV100Target
  if target ~= nil and target.registryKey == args.registryKey then
    if target.type == "NornirChest" and args.opened == true then
      target.collected = true
      target.active = false
    elseif target.type == "NornirPuzzle" then
      local key = args.keys and args.keys[target.keyIndex] or nil
      if args.challengeComplete == true or args.opened == true or
          (args.keyType == "Breakable" and key ~= nil and key.broken == true) then
        target.collected = true
        target.active = false
      end
    end
  end

  print("[CompletionistMap v0.10.1] NORNIR_UI_BRIDGE_RECV" ..
    " registryKey=" .. tostring(args.registryKey) ..
    " keyType=" .. tostring(args.keyType) ..
    " opened=" .. tostring(args.opened) ..
    " challengeComplete=" .. tostring(args.challengeComplete) ..
    " keysUsed=" .. tostring(args.keysUsed))
end

function MainHUD:EVT_COMPLETIONIST_NORNIR_STATE(args)
  CompletionistMapV100_StoreNornirUIState(args)
end

local function CompletionistMapV100_StoreNornirOpened(args)
  if args == nil or args.registryKey == nil then return end

  _G.CompletionistMapV100NornirRegistry =
    _G.CompletionistMapV100NornirRegistry or {}

  local entry = _G.CompletionistMapV100NornirRegistry[args.registryKey]
  if entry == nil then
    entry = {
      registryKey = args.registryKey,
      name = args.name,
      opened = true,
      x = args.x,
      y = args.y,
      z = args.z,
      keys = {}
    }
    _G.CompletionistMapV100NornirRegistry[args.registryKey] = entry
  else
    entry.opened = true
  end

  local target = _G.CompletionistMapV100Target
  if target ~= nil and
      target.registryKey == args.registryKey and
      (target.type == "NornirChest" or target.type == "NornirPuzzle") then
    target.collected = true
    target.active = false
  end

  print("[CompletionistMap v0.10.1] NORNIR_OPENED_RECV" ..
    " registryKey=" .. tostring(args.registryKey) ..
    " source=" .. tostring(args.source))
end

function MainHUD:EVT_COMPLETIONIST_NORNIR_OPENED(args)
  CompletionistMapV100_StoreNornirOpened(args)
end

local function CompletionistMapV100_UpdateHUDMarker(self)
  local target = _G.CompletionistMapV100Target

  if target ~= nil then
    if target.type == "Raven" and
        _G.CompletionistMapV100TargetRavenKilled == true then
      target.collected = true
    end

    if target.type == "Raven" and
        not target.collected and
        target.regionQuest ~= nil then
      local stateOK, state = pcall(function()
        return game.QuestManager.GetQuestState(target.regionQuest)
      end)

      if stateOK and tostring(state) == "Complete" then
        target.collected = true
        _G.CompletionistMapV100TargetRavenKilled = true
      end
    end

    if (target.type == "NornirPuzzle" or
        target.type == "NornirChest") and
        self.completionistMapV100NornirGeneration ~=
          _G.CompletionistMapV100NornirTargetGeneration then
      self.completionistMapV100NornirGeneration =
        _G.CompletionistMapV100NornirTargetGeneration
      print("[CompletionistMap v0.10.1] HUD_NORNIR_TRACK" ..
        " active=true" ..
        " mode=direct_xyz" ..
        " registryLookup=false" ..
        " index=" .. tostring(target.keyIndex) ..
        " x=" .. tostring(target.x) ..
        " y=" .. tostring(target.y) ..
        " z=" .. tostring(target.z))
    end

    if target.collected then
      if target.active then
        print("[CompletionistMap v0.10.1] HUD_AUTO_CLEAR reason=target_collected")
      end
      target.active = false
      CompletionistMapV100_RestoreProofVisual(self)
      return
    end
  end

  if target == nil or not target.active then
    CompletionistMapV100_RestoreProofVisual(self)
    return
  end

  local go = CompletionistMapV100_GetProofVisual(self)
  if go ~= nil then
    CompletionistMapV100_ProbeHudIconApi(go)
  end
  if go == nil then
    return
  end

  local player = game.Player.FindPlayer()
  if player == nil then
    return
  end

  local posOK, playerPos = pcall(function()
    return player:GetWorldPosition()
  end)

  local forwardOK, forward = pcall(function()
    return player:GetWorldForward()
  end)

  local compassOK, compassPos = pcall(function()
    return self.compassObj:GetWorldPosition()
  end)

  if not posOK or playerPos == nil or
      not forwardOK or forward == nil or
      not compassOK or compassPos == nil then
    return
  end

  local tx = target.x - playerPos.x
  local tz = target.z - playerPos.z
  local targetLen = math.sqrt(tx * tx + tz * tz)

  local forwardLen =
    math.sqrt(
      forward.x * forward.x +
      forward.z * forward.z
    )

  if targetLen < 0.001 or forwardLen < 0.001 then
    return
  end

  tx = tx / targetLen
  tz = tz / targetLen

  local fx = forward.x / forwardLen
  local fz = forward.z / forwardLen

  local cross = fx * tz - fz * tx
  local dot = fx * tx + fz * tz
  local angle = math.atan2(cross, dot)
  local angleDeg = math.deg(angle)

  -- Match the earlier proven compass orientation.
  local normalized = angleDeg / 90
  if normalized > 1 then
    normalized = 1
  elseif normalized < -1 then
    normalized = -1
  end

  local xOffset = -normalized * 1.15

  -- Keep it slightly in front of the compass base.
  local targetPos = engine.Vector.New(
    compassPos.x + xOffset,
    compassPos.y,
    compassPos.z - 0.05
  )

  local moveOK, moveErr = pcall(function()
    go:SetWorldPosition(targetPos)
    go:SetScale(0.55)
    go:Show()
    UI.AlphaFade(go, 1, 0)
  end)

  if not moveOK then
    if not self.completionistMapV100MoveErrorLogged then
      self.completionistMapV100MoveErrorLogged = true
      print("[CompletionistMap v0.10.1] HUD_VISUAL_MOVE" ..
        " ok=false error=" .. tostring(moveErr))
    end
    return
  end

  self.completionistMapV100ProofWasActive = true
  self.completionistMapV100HUDFrame =
    (self.completionistMapV100HUDFrame or 0) + 1

  if self.completionistMapV100HUDFrame == 1 or
      self.completionistMapV100HUDFrame % 600 == 0 then
    local verifyOK, actual = pcall(function()
      return go:GetWorldPosition()
    end)

    print("[CompletionistMap v0.10.1] HUD_VISUAL_FRAME" ..
      " name=" .. tostring(self.completionistMapV100ProofName) ..
      " moveOK=true" ..
      " distance=" .. tostring(targetLen) ..
      " angleDeg=" .. tostring(angleDeg) ..
      " normalized=" .. tostring(normalized) ..
      " xOffset=" .. tostring(xOffset) ..
      " actual=" .. (
        verifyOK and actual ~= nil and
        ("x=" .. tostring(actual.x) ..
         ",y=" .. tostring(actual.y) ..
         ",z=" .. tostring(actual.z))
        or "<unavailable>"
      ))
  end
end
'@

$hudHelper = $hudHelper.Replace('__COMPLETIONIST_ICON_ROOT__', $CompletionistIconLuaRoot)

$hudText = $hudText.Replace(
    'local mainHUD = MainHUD.New("mainHUD", {})',
    'local mainHUD = MainHUD.New("mainHUD", {})' + "`r`n" + $hudHelper
)

$hudSetupAnchor =
    '  self.compassRadius = util.GetUiObjByName("Compass_Radius")'
$hudSetupReplacement = @'
  self.compassRadius = util.GetUiObjByName("Compass_Radius")
  self.completionistMapV100HUDFrame = 0
  self.completionistMapV100ProofGO = nil
  self.completionistMapV100ProofName = nil
  self.completionistMapV100ProofOrigin = nil
  self.completionistMapV100ProofWasActive = false
  self.completionistMapV100MissingVisualLogged = false
  self.completionistMapV100MoveErrorLogged = false
'@
$hudText = $hudText.Replace(
    $hudSetupAnchor,
    $hudSetupReplacement.TrimEnd()
)

$setupTailRegex =
    [regex]::new('end\r?\nfunction MainHUD:SetRagePrompts\(\)')

$setupTailReplacement = @'
  local completionistMapV100OriginalUpdate = self.Update
  self.Update = function()
    if completionistMapV100OriginalUpdate ~= nil then
      completionistMapV100OriginalUpdate()
    end
    CompletionistMapV100_UpdateHUDMarker(self)
  end

  print("[CompletionistMap v0.10.1] HUD_HOOK installed=true")
end
function MainHUD:SetRagePrompts()
'@

$hudText = $setupTailRegex.Replace(
    $hudText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $setupTailReplacement },
    1
)

# Validate HUD instrumentation only after the helper and Update hook have been
# injected into $hudText. The previous seed checked the untouched source script.
if (-not $hudText.Contains('HUD_ICON_CAPS')) {
    throw 'v0.10.1 HUD icon capability probe is missing after HUD injection.'
}

if (-not $hudText.Contains('[CompletionistMap v0.10.1] HUD_HOOK installed=true')) {
    throw 'v0.10.1 HUD update hook is missing after HUD injection.'
}

$mapDestDir = Split-Path $mapDest -Parent
$hudDestDir = Split-Path $hudDest -Parent
$ravenDestDir = Split-Path $ravenDest -Parent
$nornirDestDir = Split-Path $nornirDest -Parent
$standardChestDestDir = Split-Path $standardChestDest -Parent
New-Item -ItemType Directory -Force -Path $mapDestDir | Out-Null
New-Item -ItemType Directory -Force -Path $hudDestDir | Out-Null
New-Item -ItemType Directory -Force -Path $ravenDestDir | Out-Null
New-Item -ItemType Directory -Force -Path $nornirDestDir | Out-Null
New-Item -ItemType Directory -Force -Path $standardChestDestDir | Out-Null

if (Test-Path $mapDest) {
    Copy-Item $mapDest $mapBackup -Force
    Write-Host "Backed up existing mapmenu override to: $mapBackup"
}
if (Test-Path $hudDest) {
    Copy-Item $hudDest $hudBackup -Force
    Write-Host "Backed up existing mainhud override to: $hudBackup"
}
if (Test-Path $ravenDest) {
    Copy-Item $ravenDest $ravenBackup -Force
    Write-Host "Backed up existing precisionchallenge override to: $ravenBackup"
}
if (Test-Path $nornirDest) {
    Copy-Item $nornirDest $nornirBackup -Force
    Write-Host "Backed up existing Nornir chest override to: $nornirBackup"
}
if (Test-Path $standardChestDest) {
    Copy-Item $standardChestDest $standardChestBackup -Force
    Write-Host "Backed up existing standard chest override to: $standardChestBackup"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($mapDest, $mapText, $utf8NoBom)
[IO.File]::WriteAllText($hudDest, $hudText, $utf8NoBom)
[IO.File]::WriteAllText($ravenDest, $ravenText, $utf8NoBom)
[IO.File]::WriteAllText($nornirDest, $nornirText, $utf8NoBom)
[IO.File]::WriteAllText($standardChestDest, $standardChestText, $utf8NoBom)

Write-Host ''
Write-Host 'Completionist Map v0.10.1 ICON PIPELINE + RENDERING DISCOVERY installed.'

Write-Host "Map override: $mapDest"
Write-Host "HUD override: $hudDest"
Write-Host "Raven lifecycle override: $ravenDest"
Write-Host "Nornir diagnostic override: $nornirDest"
Write-Host "Runic chest opened-state override: $standardChestDest"
Write-Host ''
Write-Host 'Expected changes:'
Write-Host '- map Raven test pin should be a separate BOAT/DockPoint icon, not the red Omega quest icon'
Write-Host '- original real dock remains untouched'
Write-Host '- collision selection uses frame debounce rather than oscillating true/false'
Write-Host '- Add/Remove to Compass now toggles only the safe custom Raven XYZ state'
Write-Host '- HUD still uses the proven R3_L3 temporary marker visual'
Write-Host '- the exact Raven gameplay script now publishes its persisted ravenKilled state'
Write-Host '- killing the target immediately clears the HUD target and prevents the map pin returning'
Write-Host '- every loaded Nornir chest logs its KeyType and the XYZ of sealBreakable01..03'
Write-Host '- Nornir logs now include exact runeIndex + runeEnabled state for individual seal lifecycle'
Write-Host '- Midgard map opens emit player world-to-map calibration pairs'
Write-Host '- loaded incomplete Breakable Nornir chests now get separate selectable map pins'
Write-Host '- selected Nornir seals reuse the proven arbitrary-XYZ custom HUD compass target'
Write-Host ''
Write-Host '- FIX: mapmenu.lua now loads correctly; v0.8.5 premature MapOn:Update closure removed'`r`nWrite-Host '- SHOW ALL includes top-level Completionist markers: remaining Raven + incomplete Nornir chest'`r`nWrite-Host '- NORNIR PUZZLE shows only unresolved puzzle actors; Breakable hides persisted broken seals'`r`nWrite-Host '- custom filters are appended to the EXISTING bottom-left filter cycle'`r`nWrite-Host '- stock regional Undiscovered summary is ignored for our synthetic Nornir chest parent pin'`r`nWrite-Host '- FIX: Nornir chest/seal Add to Compass no longer calls a nil global registry helper'`r`nWrite-Host '- GetNornirRegistry is now a forward-declared local captured by IsTargetCollected'`r`nWrite-Host '- filters, only-unbroken Breakable seals, Nornir parent pins, Raven path and extended zoom are retained'`r`nWrite-Host '- INSTALLER FIX: native-hover validation now runs after collision injection'`r`nWrite-Host '- milestone: Raven pin root is reinforced at its real map coordinate every map frame'`r`nWrite-Host '- custom marker hover no longer calls Camera.PointAt, so zoom is preserved'`r`nWrite-Host '- custom markers use the stock SetCursorSelected animation'`r`nWrite-Host '- trying a locked Nornir chest reveals remaining siblings in SHOW ALL'`r`nWrite-Host '- actual Runic chest OnOpened now removes the parent marker and clears its compass target'`r`nWrite-Host '- FIX: seal selection is no longer cleared every frame while puzzle actors are visible in SHOW ALL'`r`nWrite-Host '- Nornir puzzle children have priority over the parent chest and a 120-frame action latch'`r`nWrite-Host '- deeper zoom: MaxIn 6 -> 2.5 (~2.4x closer than stock)'`r`nWrite-Host '- Square/keyboard equivalent toggles Kratos marker whenever Go to Journal is unavailable'`r`nWrite-Host '- FIX: Raven, Nornir parent and each puzzle actor now use DISTINCT discovered DockPoint backing IDs'`r`nWrite-Host '- this prevents same-ID native marker aliasing from collapsing custom markers onto one location'`r`nWrite-Host '- max-zoom snap reach reduced with CursorScale_Min 0.32 and adaptive custom marker scaling'`r`nWrite-Host '- deep MaxIn 2.5 zoom and Kratos show/hide toggle are retained'`r`nWrite-Host '- HOTFIX: rebuilt from compile-good v0.9.2, not the broken v0.9.3 map patch'`r`nWrite-Host '- adaptive-scale helper is forward-declared so marker creation cannot resolve it as nil'`r`nWrite-Host '- distinct backings, filters, seal compass and Kratos toggle are retained'`r`nWrite-Host '- close-zoom snapping is much weaker: CursorScale_Min 0.12, CursorSnap_Strength 0.55'`r`nWrite-Host '- FIX: Raven map position is independent of the one active compass target object'`r`nWrite-Host '- tracking Nornir can no longer move/hide the Raven at the Nornir coordinates'`r`nWrite-Host '- synthetic marker roots are fixed at 0.28 scale to reduce their clickable/snap footprint'`r`nWrite-Host '- Nornir child debounce reduced from 120 to 12 frames'`r`nWrite-Host '- snap tuning tightened: CursorScale_Min 0.05, CursorSnap_Strength 0.18'`r`nWrite-Host '- FIX: restored v0.9.4 native-clickable custom collision instead of the failed manual-hover experiment'`r`nWrite-Host '- tMapCamera magnetic snapping is fully disabled: CursorSnap_Enabled=0'`r`nWrite-Host '- custom marker visuals are back at native scale 1.0'`r`nWrite-Host '- custom tracking clears any stale stock DockPoint compass destination first'`r`nWrite-Host '- hidden Kratos opening-centre fix is retained'`r`nWrite-Host '- INSTALLER HOTFIX: hidden-player validation now runs only after the camera-focus patch is applied'`r`nWrite-Host '- v0.10.1 uses bundled/local user-authored concept PNG masters with no GitHub/network dependency'`r`nWrite-Host '- generates 24/32/48/64 px transparent production candidates under mods\completionist-map\icons'`r`nWrite-Host '- Raven/Nornir synthetic GOs probe direct SetTexture/SetImage APIs and attempt binding only when such an API exists'`r`nWrite-Host '- if no direct loose-PNG API exists, stable DockPoint visuals remain while logs identify the next texture/material integration route'`r`nWrite-Host '- HUD carrier is capability-probed only; it is not mutated by unknown texture APIs in this build'`r`nWrite-Host 'Raven lifecycle + Nornir diagnostics are read-only with respect to puzzle/progression state.'
