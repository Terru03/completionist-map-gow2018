param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\ui\scripts\inworldmenu\mapmenu.lua'
$source = Join-Path $GameRoot ('mods\lua_source\' + $relative)
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v06-backup'

if (-not (Test-Path $source)) {
    throw "Missing loader source file: $source"
}

$text = [IO.File]::ReadAllText($source)

$required = @(
    'function MapOn:GetRealmMarkerInfo()',
    'function MapOn:UpdateIcons()',
    'Map.SetPlayerMapMarkerToPlayerMapTransform(self.playerIconGO, "facingJoint", "arrowJoint")',
    'local alwaysOnMarkerFlags = {'
)

foreach ($needle in $required) {
    if (-not $text.Contains($needle)) {
        throw "mapmenu.lua does not match the expected structure. Missing: $needle"
    }
}

if ($text.Contains('[CompletionistMap v0.6]')) {
    throw 'The lua_source copy already contains v0.6 instrumentation. Refusing to patch it.'
}

$helper = @'
-- Completionist Map v0.6 experimental map/compass injection probe.
-- Read-only: discovers runtime Map/Compass/UI APIs and map-space transforms.
local completionistMapV06TargetRaven = {
  Type = "Raven",
  Realm = "Midgard",
  Wad = "WAD_Xpl200_Funeral",
  RegionQuest = "RegionSummary_VF_Raven_Parent",
  X = -64.850898742676,
  Y = 12.987384796143,
  Z = 787.30694580078
}

local function CompletionistMapV06_IsTargetWad(wad)
  if wad == nil then
    return false
  end
  local s = tostring(wad)
  return string.find(s, "WAD_Xpl200_Funeral", 1, true) ~= nil or
    string.find(s, "WAD_Xpl220_FuneralLH", 1, true) ~= nil
end

local function CompletionistMapV06_VectorString(value)
  if value == nil then
    return "<nil>"
  end
  local values = {}
  local any = false
  for _, axis in ipairs({"x", "y", "z"}) do
    local ok, v = pcall(function()
      return value[axis]
    end)
    if ok and v ~= nil then
      any = true
      values[#values + 1] = axis .. "=" .. tostring(v)
    end
  end
  if any then
    return table.concat(values, ",")
  end
  return tostring(value)
end

local function CompletionistMapV06_DumpMembers(domain, value)
  local ok, err = pcall(function()
    for key, fieldValue in pairs(value) do
      print("[CompletionistMap v0.6] API domain=" .. tostring(domain) ..
        " key=" .. tostring(key) ..
        " type=" .. tostring(type(fieldValue)))
    end
  end)
  if not ok then
    print("[CompletionistMap v0.6] API_ENUM_ERROR domain=" .. tostring(domain) ..
      " error=" .. tostring(err))
  end

  local mtOK, mt = pcall(function()
    return getmetatable(value)
  end)
  if mtOK and mt ~= nil then
    local mtDumpOK, mtDumpErr = pcall(function()
      for key, fieldValue in pairs(mt) do
        print("[CompletionistMap v0.6] META domain=" .. tostring(domain) ..
          " key=" .. tostring(key) ..
          " type=" .. tostring(type(fieldValue)))
      end
      if type(mt.__index) == "table" then
        for key, fieldValue in pairs(mt.__index) do
          print("[CompletionistMap v0.6] META_INDEX domain=" .. tostring(domain) ..
            " key=" .. tostring(key) ..
            " type=" .. tostring(type(fieldValue)))
        end
      end
    end)
    if not mtDumpOK then
      print("[CompletionistMap v0.6] META_ENUM_ERROR domain=" .. tostring(domain) ..
        " error=" .. tostring(mtDumpErr))
    end
  end
end

local function CompletionistMapV06_DumpMarkerInfo(markerInfo, regionId)
  if markerInfo == nil or not CompletionistMapV06_IsTargetWad(markerInfo.WadName) then
    return
  end

  print("[CompletionistMap v0.6] TARGET_WAD_MARKER" ..
    " region=" .. tostring(regionId) ..
    " id=" .. tostring(markerInfo.Id) ..
    " state=" .. tostring(markerInfo.State) ..
    " wad=" .. tostring(markerInfo.WadName) ..
    " lamsName=" .. tostring(markerInfo.LamsNameId) ..
    " lamsDesc=" .. tostring(markerInfo.LamsDescriptionId))

  local ok, err = pcall(function()
    for key, fieldValue in pairs(markerInfo) do
      local fieldType = type(fieldValue)
      print("[CompletionistMap v0.6] MARKER_FIELD" ..
        " id=" .. tostring(markerInfo.Id) ..
        " key=" .. tostring(key) ..
        " type=" .. tostring(fieldType) ..
        " value=" .. CompletionistMapV06_VectorString(fieldValue))
    end
  end)
  if not ok then
    print("[CompletionistMap v0.6] MARKER_FIELD_ERROR id=" ..
      tostring(markerInfo.Id) .. " error=" .. tostring(err))
  end
end

local function CompletionistMapV06_ProbeAPIs(self)
  if self.currRealmName ~= "Midgard" or self.completionistMapV06APIDumped then
    return
  end
  self.completionistMapV06APIDumped = true

  print("[CompletionistMap v0.6] BEGIN")
  print("[CompletionistMap v0.6] TARGET" ..
    " type=" .. completionistMapV06TargetRaven.Type ..
    " realm=" .. completionistMapV06TargetRaven.Realm ..
    " wad=" .. completionistMapV06TargetRaven.Wad ..
    " regionQuest=" .. completionistMapV06TargetRaven.RegionQuest ..
    " x=" .. tostring(completionistMapV06TargetRaven.X) ..
    " y=" .. tostring(completionistMapV06TargetRaven.Y) ..
    " z=" .. tostring(completionistMapV06TargetRaven.Z))

  CompletionistMapV06_DumpMembers("Map", game.Map)
  CompletionistMapV06_DumpMembers("Compass", game.Compass)
  CompletionistMapV06_DumpMembers("UI", game.UI)
  CompletionistMapV06_DumpMembers("Camera", game.Camera)
end

local function CompletionistMapV06_ProbeIcon(markerInfo)
  if markerInfo == nil or markerInfo.iconGO == nil or
      not CompletionistMapV06_IsTargetWad(markerInfo.WadName) then
    return
  end

  local okWorld, worldPos = pcall(function()
    return markerInfo.iconGO:GetWorldPosition()
  end)
  local okLocal, localPos = pcall(function()
    return markerInfo.iconGO:GetLocalPosition()
  end)

  print("[CompletionistMap v0.6] ICON" ..
    " id=" .. tostring(markerInfo.Id) ..
    " wad=" .. tostring(markerInfo.WadName) ..
    " world=" .. (okWorld and CompletionistMapV06_VectorString(worldPos) or "<error>") ..
    " local=" .. (okLocal and CompletionistMapV06_VectorString(localPos) or "<error>"))

  CompletionistMapV06_DumpMembers("MarkerIconGO", markerInfo.iconGO)
end

local function CompletionistMapV06_ProbePlayerTransform(self)
  if self.currRealmName ~= "Midgard" or self.completionistMapV06PlayerDumped or
      self.playerIconGO == nil then
    return
  end
  self.completionistMapV06PlayerDumped = true

  local player = game.Player.FindPlayer()
  local worldOK, playerWorld = pcall(function()
    return player:GetWorldPosition()
  end)
  local mapWorldOK, mapWorld = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  local mapLocalOK, mapLocal = pcall(function()
    return self.playerIconGO:GetLocalPosition()
  end)

  print("[CompletionistMap v0.6] PLAYER_TRANSFORM" ..
    " level=" .. tostring(player and player.CurrentLevelWadName or "") ..
    " playerWorld=" .. (worldOK and CompletionistMapV06_VectorString(playerWorld) or "<error>") ..
    " playerIconWorld=" .. (mapWorldOK and CompletionistMapV06_VectorString(mapWorld) or "<error>") ..
    " playerIconLocal=" .. (mapLocalOK and CompletionistMapV06_VectorString(mapLocal) or "<error>"))

  CompletionistMapV06_DumpMembers("PlayerIconGO", self.playerIconGO)
  print("[CompletionistMap v0.6] END")
end

'@

$text = $text.Replace(
    'local alwaysOnMarkerFlags = {',
    $helper + "`r`nlocal alwaysOnMarkerFlags = {"
)

$getRealmPattern = 'function MapOn:GetRealmMarkerInfo\(\)\r?\n  self:ClearIcons\(\)\r?\n  self\.realmMarkerInfo = \{\}\r?\n  if self\.currRealmName == nil then\r?\n    return\r?\n  end\r?\n'
$getRealmRegex = [regex]::new($getRealmPattern)
$getRealmMatch = $getRealmRegex.Match($text)
if (-not $getRealmMatch.Success) {
    throw 'Could not locate GetRealmMarkerInfo prologue.'
}
$getRealmReplacement = $getRealmMatch.Value + "  CompletionistMapV06_ProbeAPIs(self)`r`n"
$text = $getRealmRegex.Replace($text, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $getRealmReplacement }, 1)

$markerAnchor = '      local markerInfo = regionMarkerInfoTable[i]'
$markerInsert = @'
      local markerInfo = regionMarkerInfoTable[i]
      if self.currRealmName == "Midgard" then
        CompletionistMapV06_DumpMarkerInfo(markerInfo, regionInfo.Id)
      end
'@
$markerIndex = $text.IndexOf($markerAnchor)
if ($markerIndex -lt 0) {
    throw 'Could not locate markerInfo assignment.'
}
$text = $text.Remove($markerIndex, $markerAnchor.Length).Insert($markerIndex, $markerInsert.TrimEnd())

$clickableAnchor = '      UI.SetIsClickable(markerInfo.iconGO)'
$clickableInsert = @'
      UI.SetIsClickable(markerInfo.iconGO)
      CompletionistMapV06_ProbeIcon(markerInfo)
'@
$clickableIndex = $text.IndexOf($clickableAnchor)
if ($clickableIndex -lt 0) {
    throw 'Could not locate UI.SetIsClickable(markerInfo.iconGO).'
}
$text = $text.Remove($clickableIndex, $clickableAnchor.Length).Insert($clickableIndex, $clickableInsert.TrimEnd())

$playerAnchor = '    Map.SetPlayerMapMarkerToPlayerMapTransform(self.playerIconGO, "facingJoint", "arrowJoint")'
$playerInsert = @'
    Map.SetPlayerMapMarkerToPlayerMapTransform(self.playerIconGO, "facingJoint", "arrowJoint")
    CompletionistMapV06_ProbePlayerTransform(self)
'@
$playerIndex = $text.IndexOf($playerAnchor)
if ($playerIndex -lt 0) {
    throw 'Could not locate player-map transform call.'
}
$text = $text.Remove($playerIndex, $playerAnchor.Length).Insert($playerIndex, $playerInsert.TrimEnd())

$destDir = Split-Path $dest -Parent
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

if (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)
    if ($existing.Contains('[CompletionistMap v0.6]')) {
        Write-Host 'Completionist Map v0.6 is already installed.'
        exit 0
    }
    Copy-Item $dest $backup -Force
    Write-Host "Backed up existing mapmenu override to: $backup"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($dest, $text, $utf8NoBom)

Write-Host ''
Write-Host 'Completionist Map v0.6 API/transform prototype installed.'
Write-Host "Override: $dest"
Write-Host 'Open the Midgard map once, leave it open for several seconds, then quit normally.'
