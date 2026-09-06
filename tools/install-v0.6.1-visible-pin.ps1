param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\ui\scripts\inworldmenu\mapmenu.lua'
$source = Join-Path $GameRoot ('mods\lua_source\' + $relative)
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v061-backup'

if (-not (Test-Path $source)) {
    throw "Missing loader source file: $source"
}

$text = [IO.File]::ReadAllText($source)

$required = @(
    'local alwaysOnMarkerFlags = {',
    'function MapOn:SubmenuEnter(currState, realmName)',
    'function MapOn:SubmenuExit(currState)',
    'function MapOn:MouseClickHandler(currState)',
    'UI.WorldUIRender(map_camera.Name)'
)

foreach ($needle in $required) {
    if (-not $text.Contains($needle)) {
        throw "mapmenu.lua does not match the expected structure. Missing: $needle"
    }
}

if ($text.Contains('[CompletionistMap v0.6.1]')) {
    throw 'The lua_source copy already contains v0.6.1 instrumentation.'
}

$helper = @'
-- Completionist Map v0.6.1 visible-pin prototype.
-- Uses a known safe discovered native marker only as an icon template.
-- No map-marker state, quest state, or collectible state is changed.
local completionistMapV061Target = {
  Type = "Raven",
  Realm = "Midgard",
  Wad = "WAD_Xpl200_Funeral",
  RegionQuest = "RegionSummary_VF_Raven_Parent",
  WorldX = -64.850898742676,
  WorldY = 12.987384796143,
  WorldZ = 787.30694580078,
  MapX = 3.21177116,
  MapZ = 0.86959973,
  BackingMarkerIdString = "2924516555722838670"
}

local function CompletionistMapV061_ProbeMembers(domainName, domain, names)
  for _, name in ipairs(names) do
    local ok, value = pcall(function()
      return domain[name]
    end)
    if ok and value ~= nil then
      print("[CompletionistMap v0.6.1] API" ..
        " domain=" .. tostring(domainName) ..
        " name=" .. tostring(name) ..
        " type=" .. tostring(type(value)))
    end
  end
end

local function CompletionistMapV061_RunAPIProbe(self)
  if self.completionistMapV061APIDumped then
    return
  end
  self.completionistMapV061APIDumped = true

  CompletionistMapV061_ProbeMembers("Map", Map, {
    "CreateMarkerIcon",
    "RecycleIcon",
    "FindInfoFromIcon",
    "SetPlayerMapMarkerToPlayerMapTransform",
    "CreateMarker",
    "AddMarker",
    "RegisterMarker",
    "CreateMapMarker",
    "AddMapMarker",
    "RegisterMapMarker",
    "CreateMarkerAtPosition",
    "AddMarkerAtPosition",
    "SetMarkerCoordinates",
    "SetMarkerPosition",
    "ChangeMarkerCoordinates",
    "UpdateMarkerCoordinates",
    "MoveMarker",
    "WorldToMap",
    "WorldToMapPosition",
    "TransformWorldToMap",
    "SetMapMarkerPosition"
  })

  CompletionistMapV061_ProbeMembers("Compass", game.Compass, {
    "ShowMarker",
    "HideMarker",
    "FindMarkersByIconClass",
    "HideAllMarkersOfType",
    "ShowMarkerAtPosition",
    "ShowMarkerAtWorldPosition",
    "ShowWorldMarker",
    "ShowLocationMarker",
    "CreateMarker",
    "AddMarker",
    "RegisterMarker",
    "AddCompassMarker",
    "SetMarkerPosition",
    "SetCustomMarker",
    "SetObjectiveMarker",
    "ShowObjectiveMarker",
    "ShowObjectiveMarkerAtPosition",
    "SetCompassTarget",
    "SetTarget",
    "SetWorldTarget"
  })
end

local function CompletionistMapV061_FindBackingMarker(self)
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    if tostring(markerInfo.Id) == completionistMapV061Target.BackingMarkerIdString then
      return markerInfo
    end
  end
  return nil
end

local function CompletionistMapV061_DestroyPin(self)
  if self.completionistMapV061IconGO ~= nil then
    local ok, err = pcall(function()
      Map.RecycleIcon(self.completionistMapV061IconGO)
    end)
    print("[CompletionistMap v0.6.1] PIN_DESTROY" ..
      " ok=" .. tostring(ok) ..
      " error=" .. tostring(err))
    self.completionistMapV061IconGO = nil
  end
  self.completionistMapV061Selected = false
end

local function CompletionistMapV061_CreatePin(self)
  if self.currRealmName ~= completionistMapV061Target.Realm then
    return
  end
  if self.completionistMapV061IconGO ~= nil then
    return
  end

  CompletionistMapV061_RunAPIProbe(self)

  local backing = CompletionistMapV061_FindBackingMarker(self)
  if backing == nil then
    print("[CompletionistMap v0.6.1] PIN_CREATE ok=false reason=backing_marker_not_found")
    return
  end

  local isDock = false
  local dockOK, dockResult = pcall(function()
    return Map.MarkerHasAnyFlag(backing.Id, {consts.COMPASS_MARKER_TYPE_DOCK_POINT})
  end)
  if dockOK then
    isDock = dockResult
  end

  print("[CompletionistMap v0.6.1] BACKING" ..
    " id=" .. tostring(backing.Id) ..
    " state=" .. tostring(backing.State) ..
    " region=" .. tostring(backing.regionId) ..
    " wad=" .. tostring(backing.WadName) ..
    " isDock=" .. tostring(isDock))

  if backing.State ~= tweaks.eTokenState.kDiscovered or not isDock then
    print("[CompletionistMap v0.6.1] PIN_CREATE ok=false reason=backing_marker_not_safe")
    return
  end

  local createOK, iconOrErr = pcall(function()
    return Map.CreateMarkerIcon(backing.Id, backing.regionId, "")
  end)

  if not createOK or iconOrErr == nil then
    print("[CompletionistMap v0.6.1] PIN_CREATE ok=false reason=create_failed error=" ..
      tostring(iconOrErr))
    return
  end

  local iconGO = iconOrErr
  self.completionistMapV061IconGO = iconGO

  local mapY = -0.2
  local yOK, playerIconPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if yOK and playerIconPos ~= nil and playerIconPos.y ~= nil then
    mapY = playerIconPos.y
  end

  local setOK, setErr = pcall(function()
    iconGO:SetWorldPosition(engine.Vector.New(
      completionistMapV061Target.MapX,
      mapY,
      completionistMapV061Target.MapZ
    ))
    iconGO:Show()
    UI.SetIsClickable(iconGO)
  end)

  if not setOK then
    print("[CompletionistMap v0.6.1] PIN_CREATE ok=false reason=position_failed error=" ..
      tostring(setErr))
    CompletionistMapV061_DestroyPin(self)
    return
  end

  local actualOK, actual = pcall(function()
    return iconGO:GetWorldPosition()
  end)

  print("[CompletionistMap v0.6.1] PIN_CREATE" ..
    " ok=true" ..
    " type=" .. completionistMapV061Target.Type ..
    " worldX=" .. tostring(completionistMapV061Target.WorldX) ..
    " worldY=" .. tostring(completionistMapV061Target.WorldY) ..
    " worldZ=" .. tostring(completionistMapV061Target.WorldZ) ..
    " mapX=" .. tostring(completionistMapV061Target.MapX) ..
    " mapY=" .. tostring(mapY) ..
    " mapZ=" .. tostring(completionistMapV061Target.MapZ) ..
    " actual=" .. (actualOK and
      ("x=" .. tostring(actual.x) .. ",y=" .. tostring(actual.y) .. ",z=" .. tostring(actual.z))
      or "<error>"))

  local cameraOK, cameraErr = pcall(function()
    Camera.PointAtGO(iconGO, true)
  end)

  print("[CompletionistMap v0.6.1] PIN_CAMERA" ..
    " ok=" .. tostring(cameraOK) ..
    " error=" .. tostring(cameraErr))
end

'@

$text = $text.Replace(
    'local alwaysOnMarkerFlags = {',
    $helper + "`r`nlocal alwaysOnMarkerFlags = {"
)

$worldRenderAnchor = '  UI.WorldUIRender(map_camera.Name)'
$worldRenderReplacement = @'
  CompletionistMapV061_CreatePin(self)
  UI.WorldUIRender(map_camera.Name)
'@
$text = $text.Replace($worldRenderAnchor, $worldRenderReplacement.TrimEnd())

$submenuExitRegex = [regex]::new('function MapOn:SubmenuExit\(currState\)\r?\n')
if (-not $submenuExitRegex.IsMatch($text)) {
    throw 'Could not locate SubmenuExit.'
}
$text = $submenuExitRegex.Replace(
    $text,
    "function MapOn:SubmenuExit(currState)`r`n  CompletionistMapV061_DestroyPin(self)`r`n",
    1
)

$exitRegex = [regex]::new('function MapOn:Exit\(\)\r?\n')
if (-not $exitRegex.IsMatch($text)) {
    throw 'Could not locate MapOn:Exit.'
}
$text = $exitRegex.Replace(
    $text,
    "function MapOn:Exit()`r`n  CompletionistMapV061_DestroyPin(self)`r`n",
    1
)

$mouseRegex = [regex]::new('function MapOn:MouseClickHandler\(currState\)\r?\n')
if (-not $mouseRegex.IsMatch($text)) {
    throw 'Could not locate MouseClickHandler.'
}
$mouseInjection = @'
function MapOn:MouseClickHandler(currState)
  if self.completionistMapV061IconGO ~= nil and
      UI.GetEventSenderGameObject() == self.completionistMapV061IconGO then
    self.completionistMapV061Selected = true
    self.currMarkerID = nil
    self.currQuestID = nil
    self.clickedMarkerInfo = nil
    self.clickedPlayer = false
    Camera.PointAtGO(self.completionistMapV061IconGO)
    self:SetReticleInfo(currState, "Odin's Raven", "Remaining collectible - Completionist Map prototype")
    print("[CompletionistMap v0.6.1] PIN_CLICK")
    return
  end
'@
$text = $mouseRegex.Replace(
    $text,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $mouseInjection },
    1
)

$destDir = Split-Path $dest -Parent
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

if (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)
    if ($existing.Contains('[CompletionistMap v0.6.1]')) {
        Write-Host 'Completionist Map v0.6.1 is already installed.'
        exit 0
    }

    Copy-Item $dest $backup -Force
    Write-Host "Backed up existing mapmenu override to: $backup"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($dest, $text, $utf8NoBom)

Write-Host ''
Write-Host 'Completionist Map v0.6.1 VISIBLE PIN prototype installed.'
Write-Host "Override: $dest"
Write-Host ''
Write-Host 'Open the Midgard map. It should centre on a duplicated native dock-style icon'
Write-Host 'placed at the predicted map position of the remaining Veithurgard Raven.'
Write-Host 'This build does not alter collectible, quest, or map-marker progression.'
