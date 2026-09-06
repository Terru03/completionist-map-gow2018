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
-- Temporarily borrows one already-rendered discovered DockPoint icon.
-- The original icon position is restored when leaving the map.
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

local function CompletionistMapV061_RestorePin(self)
  if self.completionistMapV061IconGO ~= nil and
      self.completionistMapV061OriginalPosition ~= nil then
    local ok, err = pcall(function()
      self.completionistMapV061IconGO:SetWorldPosition(
        self.completionistMapV061OriginalPosition
      )
    end)
    print("[CompletionistMap v0.6.1] PIN_RESTORE" ..
      " ok=" .. tostring(ok) ..
      " error=" .. tostring(err))
  end

  self.completionistMapV061IconGO = nil
  self.completionistMapV061OriginalPosition = nil
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
    " isDock=" .. tostring(isDock) ..
    " hasIcon=" .. tostring(backing.iconGO ~= nil))

  if backing.State ~= tweaks.eTokenState.kDiscovered or
      not isDock or backing.iconGO == nil then
    print("[CompletionistMap v0.6.1] PIN_CREATE ok=false reason=backing_marker_not_safe")
    return
  end

  local originalOK, original = pcall(function()
    return backing.iconGO:GetWorldPosition()
  end)

  if not originalOK or original == nil then
    print("[CompletionistMap v0.6.1] PIN_CREATE ok=false reason=original_position_unavailable")
    return
  end

  self.completionistMapV061IconGO = backing.iconGO
  self.completionistMapV061OriginalPosition =
    engine.Vector.New(original.x, original.y, original.z)

  local mapY = original.y
  local yOK, playerIconPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if yOK and playerIconPos ~= nil and playerIconPos.y ~= nil then
    mapY = playerIconPos.y
  end

  local setOK, setErr = pcall(function()
    self.completionistMapV061IconGO:SetWorldPosition(engine.Vector.New(
      completionistMapV061Target.MapX,
      mapY,
      completionistMapV061Target.MapZ
    ))
    self.completionistMapV061IconGO:Show()
    UI.SetIsClickable(self.completionistMapV061IconGO)
  end)

  if not setOK then
    print("[CompletionistMap v0.6.1] PIN_CREATE ok=false reason=position_failed error=" ..
      tostring(setErr))
    CompletionistMapV061_RestorePin(self)
    return
  end

  local actualOK, actual = pcall(function()
    return self.completionistMapV061IconGO:GetWorldPosition()
  end)

  print("[CompletionistMap v0.6.1] PIN_CREATE" ..
    " ok=true" ..
    " mode=borrowed_discovered_dock_icon" ..
    " type=" .. completionistMapV061Target.Type ..
    " worldX=" .. tostring(completionistMapV061Target.WorldX) ..
    " worldY=" .. tostring(completionistMapV061Target.WorldY) ..
    " worldZ=" .. tostring(completionistMapV061Target.WorldZ) ..
    " mapX=" .. tostring(completionistMapV061Target.MapX) ..
    " mapY=" .. tostring(mapY) ..
    " mapZ=" .. tostring(completionistMapV061Target.MapZ) ..
    " originalX=" .. tostring(original.x) ..
    " originalY=" .. tostring(original.y) ..
    " originalZ=" .. tostring(original.z) ..
    " actual=" .. (actualOK and
      ("x=" .. tostring(actual.x) .. ",y=" .. tostring(actual.y) .. ",z=" .. tostring(actual.z))
      or "<error>"))

  local cameraOK, cameraErr = pcall(function()
    Camera.PointAtGO(self.completionistMapV061IconGO, true)
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
    "function MapOn:SubmenuExit(currState)`r`n  CompletionistMapV061_RestorePin(self)`r`n",
    1
)

$exitRegex = [regex]::new('function MapOn:Exit\(\)\r?\n')
if (-not $exitRegex.IsMatch($text)) {
    throw 'Could not locate MapOn:Exit.'
}
$text = $exitRegex.Replace(
    $text,
    "function MapOn:Exit()`r`n  CompletionistMapV061_RestorePin(self)`r`n",
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
Write-Host 'Open the Midgard map. The prototype temporarily moves one already-rendered'
Write-Host 'discovered dock icon to the calculated map position of the remaining Raven.'
Write-Host 'The dock icon is restored when you leave the map.'
Write-Host 'No save/progression state is changed.'
