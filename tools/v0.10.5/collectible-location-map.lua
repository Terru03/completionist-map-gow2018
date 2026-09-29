-- BEGIN COMPLETIONIST V0.10.5 COLLECTIBLE LOCATIONS
-- Hides collected pins using tri-state service with save-epoch isolation.
do
  local State = _G.CompletionistMapV105LocationState
  local runtime = _G.CompletionistMapV105LocationRuntime
  local activeMap, activeSelectionContext, cleanupPending
  local constsOK, constslib = pcall(require, "ui.consts")
  local AS_ForwardCycle_NoReset = (constsOK and type(constslib) == "table" and constslib.AS_ForwardCycle_NoReset) or 10
  local AS_Forward = (constsOK and type(constslib) == "table" and constslib.AS_Forward) or 0
  local categories = {
-- @@LOCATION_CATEGORIES@@
  }
  local rows = {
-- @@LOCATION_ROWS@@
  }
  local byName, byFamily, byCatalogue, nativeIds = {}, {}, {}, {}
  for _, category in ipairs(categories) do
    byFamily[category.Family] = category
    completionistFilterLabels[category.Filter] = category.Label
  end
  for _, row in ipairs(rows) do
    byName[row.Name] = row
    if row.CatalogueId then byCatalogue[row.CatalogueId] = row end
    if row.Native then nativeIds[row.IdString] = true end
  end

  local digQuests = {
    ["treasure_dig_5f6d01b68cdf70a9815dc6fa7c3a839f"] = "Quest_TreasureMap_BlackBreath",
    ["treasure_dig_c49a3435a3361bfb0f23ee7a0cecc202"] = "Quest_TreasureMap_TurtleHouse",
    ["treasure_dig_33fd783f7b353537d922042c2a967396"] = "Quest_TreasureMap_VF",
    ["treasure_dig_ebcc555c3dc8b13561d8afa2bd4c0ba0"] = "Quest_TreasureMap_Stronghold",
    ["treasure_dig_1004498996e12e1bd865e937caf21f2d"] = "Quest_TreasureMap_ValkyrieArena",
    ["treasure_dig_70214d5859cc48c2bfddd06fb252a8ba"] = "Quest_TreasureMap_Oarsmen",
    ["treasure_dig_8d79870871fe184c47d369eabbd68f92"] = "Quest_TreasureMap_ForestDungeon",
    ["treasure_dig_a46f12e366ccfd55f7a945383f1231d0"] = "Quest_TreasureMap_IslandArch",
    ["treasure_dig_9680b8bc8eff19d4c84b439b0e5a841b"] = "Quest_TreasureMap_Shipwreck",
    ["treasure_dig_8c965bccff326f509c02f9321af9a223"] = "Quest_TreasureMap_IslandClimb",
    ["treasure_dig_4a770cc6263ef7c83b7ea0e4130c6c59"] = "Quest_TreasureMap01",
    ["treasure_dig_4ec60e59f32086918769282570d5b976"] = "Quest_TreasureMap_ThorStatue",
  }

  local mapQuests = {
    ["treasure_map_4011675d69434ff50662d79d43b08305"] = "Quest_TreasureMap_IslandClimb_Parent",
    ["treasure_map_f48eb59997ca3572363316461a106067"] = "Quest_TreasureMap_ValkyrieArena_Parent",
    ["treasure_map_3cab9691f053fec1dc02301cf9c04021"] = "Quest_TreasureMap_TurtleHouse_Parent",
    ["treasure_map_82e41ccaf3093e62880d64a18227112c"] = "Quest_TreasureMap_Oarsmen_Parent",
    ["treasure_map_67ec3f2c214e4fd07a7eaf0b58cf213c"] = "Quest_TreasureMap01_Parent",
    ["treasure_map_ce589a091d984c3581097a8700aad61d"] = "Quest_TreasureMap_ThorStatue_Parent",
    ["treasure_map_b08d1fd606f2ac8a09bf8edc6d5a55b7"] = "Quest_TreasureMap_BlackBreath_Parent",
    ["treasure_map_adf20b36ad0f86b68901b8e49aeeb498"] = "Quest_TreasureMap_ForestDungeon_Parent",
    ["treasure_map_8b1707f94ad818100dd4a5afc67fc6c6"] = "Quest_TreasureMap_Stronghold_Parent",
    ["treasure_map_4a07636dc59583c9bfe877849ab5a97f"] = "Quest_TreasureMap_IslandArch_Parent",
    ["treasure_map_aef0891f1c3ee6d1f88f86b1601052f4"] = "Quest_TreasureMap_VF_Parent",
    ["treasure_map_5d8b3d55a299888357a6893fcec99c05"] = "Quest_TreasureMap_Shipwreck_Parent",
  }

  local shrineResources = {
    ["jotnar_shrine_4f54c8b2f4d927800573fde8aece376f"] = "Tryptich_Skadi",
    ["jotnar_shrine_682f1626cae370f11b4df300ae79219d"] = "Tryptich_Surtr",
    ["jotnar_shrine_6e55a7d7704af68ce4b82e5edecf81a7"] = "Tryptich_Groa",
    ["jotnar_shrine_7dadb7c3e8c5fdc6259b311fe6ac74ba"] = "Tryptich_Solargram",
    ["jotnar_shrine_b124fa2d62938dc8fcf85d67432d8550"] = "Tryptich_Starkadr",
    ["jotnar_shrine_b35ee9b618a76bfdf24596944d7b11b0"] = "Tryptich_Thrym",
    ["jotnar_shrine_e49959e54f3f1da0632c3ac2a01d7ec7"] = "Tryptich_Thamur",
    ["jotnar_shrine_1af4f035065fe9603505c02d9b2e1462"] = "Tryptich_Tyr",
    ["jotnar_shrine_23d6030ef079b748c4574a940bf2047b"] = "Tryptich_Tyr",
    ["jotnar_shrine_5abb17c179c16ed72287fc2740a46f9a"] = "Tryptich_Ymir",
    ["jotnar_shrine_8a16de1ec11694c5752092bd06e16978"] = "Tryptich_Bergelmir",
    ["jotnar_shrine_c0d7a4d17e152054e3e3c3e2571d98b8"] = "Tryptich_Hrungnir",
    ["jotnar_shrine_19c69abd2cdf4145b71903eabdaf87f8"] = "Tryptich_Jormungandr",
  }

  local scrollResources = {
    ["lore_scroll_dc56801cbe1e7d3cbd54f9150cc78a3c"] = "ForestChisel_Lore",
    ["lore_scroll_62cc5c222fbe7d849e83705cfe13638c"] = "SerpentScroll_Lore",
    ["lore_scroll_0a8de84c5e82fd19ccc618bce5ef6f84"] = "JotunheimScroll_Lore",
    ["lore_scroll_2242aadeda389dae8c5283057c5326ca"] = "SvartleheimScroll_Lore",
    ["lore_scroll_e8415d73adfe99aa45c8e142856455da"] = "ShipwreckIsland_Lore",
  }

  local loreResources = {
    ["lore_marker_alf150bridgedarkwad76250fcb340065498ff1b75bddd20fcf"] = "ALF_100_Lore_01",
    ["lore_marker_alf150bridgedarkwad969e45f02f76844192ec5566056fbfd4"] = "ALF_100_Lore_01",
    ["lore_marker_alf440hiveextlhwad0f75539e19bc0947ba4d6f46ea0a95d2"] = "ALF_390_Lore_01",
    ["lore_marker_alf690lakelightlhwade723fb1f62e1ef4a94d19a5eeeef0673"] = "ALF_690_Lore_01",
    ["lore_marker_cal250foothillslhwadb456381ff98fb449896acb659da524fa"] = "CAL_250_Lore_02",
    ["lore_marker_cal250foothillslhwad8ab6b877e9062c4b9f0d0f375f8326c1"] = "CAL_250_Lore_03",
    ["lore_marker_cal250foothillslhwad9614e6b2dfd34f4b86e932b59f2aa621"] = "CAL_250_Lore_01",
    ["lore_marker_xpl910islandshipwreckwad6093995aaaf7ad4b9830d1be0e7e0684"] = "CAL_100_Lore_01",
    ["lore_marker_xpl940beachcavewad6093995aaaf7ad4b9830d1be0e7e0684"] = "CAL_100_Lore_01",
    ["lore_marker_xpl950beachmazewad6093995aaaf7ad4b9830d1be0e7e0684"] = "CAL_100_Lore_01",
    ["lore_marker_xpl960beachshipwad6093995aaaf7ad4b9830d1be0e7e0684"] = "CAL_100_Lore_01",
    ["lore_marker_cal500runevaultwad14f472bb0d9d2e4993d0774cbc755e02"] = "CAL_500_Lore_01",
    ["lore_marker_3d2e2f04d7df6a4b9a4e30601432871f"] = "CAL_740_Lore_01",
    ["lore_marker_d988f2795775914592a04b62df2726d9"] = "CAL_750_Lore_01",
    ["lore_marker_xpl125httklhwad36f99a6c8537174bbaab95fb9d956455"] = "HTTK_125_Lore_01",
    ["lore_marker_xpl170httkcaverwad776651e16e0bcd4995eaa2ad3e73f56a"] = "HTTK_170_Lore_01",
    ["lore_marker_xpl400huldramineswade1701a5ddf529645b442371f82145220"] = "Xpl450_DeathHere",
    ["lore_marker_xpl400huldramineswadf014bd94366e7b49ade008aff1769396"] = "Xpl450_InnMenn",
    ["lore_marker_xpl425huldramineslhwad7f236d968be3c14db2ecde8780a968a0"] = "Xpl425_LoreMarker",
    ["lore_marker_xpl300strongholdwad79d7700bc6e8cf47a77b5403426b5297"] = "Xpl300_FalseLeader",
    ["lore_marker_xpl300strongholdwade361f1b4a04c074b84896263475139ab"] = "Xpl300_LoreMarker",
    ["lore_marker_xpl650masontrailcavewadb2f0bf0705313e4aa27b33fddd3a0665"] = "Xpl650_LoreMarker",
    ["lore_marker_peak100entrancewadeda4d87459eae64ba0a1c556edca5809"] = "PP_100_Lore_01",
    ["lore_marker_peak140caverndarkwad3aae61a66981c34082d9e3dcb14c9a39"] = "PP_140_Lore_01",
    ["lore_marker_peak180enttochimneylhwadcc54f8d5e69b0945a3674ddc65276412"] = "PP_180_Lore_02",
    ["lore_marker_peak200chimneylowwad29a3fec3318213458a458abb0eb539a2"] = "PP_300_Lore_01",
    ["lore_marker_peak500chimneytopwad1d9b928f5f7eab4082f9c52e2f066780"] = "PP_500_Lore_01",
    ["lore_marker_peak720summitascenthubwadda8178f1357e8d45922a657e6f760dd8"] = "PP_720_Lore_01",
    ["lore_marker_riv085dangersentrancelhwad0359c55688ca5b48bd66cf4ae66fbed3"] = "RIV_100_Lore_01",
    ["lore_marker_riv200dangersmainwad452dc462aab2814097a8c9a7d317c558"] = "RIV_200_Lore_01",
    ["lore_marker_riv420forestboarstartwad0c671129ecb3144cbcf4a641a4160b66"] = "RIV_420_Lore_01",
    ["lore_marker_riv475freyahouseextwad5124f330461a8e42b1659c4517e18c29"] = "RIV_475_Lore_01",
    ["lore_marker_riv475freyahouseextwad9a50243a697a924481d49d5c44c980ac"] = "RIV_475_Lore_02",
    ["lore_marker_riv475freyahouseextwadd328468a73cead438031e76201fbddc9"] = "RIV_475_Lore_03",
    ["lore_marker_ab859d0b83766845bb0b0e69023e1c31"] = "RIV_925_Lore_01",
    ["lore_marker_stn200lakeextwad64309dc36de48d438409f5abb85cfc92"] = "SM_200_Lore_01",
    ["lore_marker_xpl200funeralwadf8ceaf9fdf59ef4c97b6d4398c23bb9d"] = "VF_200_Lore_03",
    ["lore_marker_xpl200funeralwad0ab993b107a42f41af27749c6749728d"] = "VF_200_Lore_02",
    ["lore_marker_xpl220funerallhwadeea6c57321539249a4d58ca8baa527cb"] = "VF_220_Lore_01",
    ["lore_marker_xpl225funerallhwadb18d193b7ba34340a8831d0e11ff1b4e"] = "XPL_200_Lore_01",
    ["lore_marker_xpl225funerallhwadfb3c8f6c096b464dafa89220022f8c54"] = "VF_225_Lore_01",
    ["lore_marker_xpl250funeralinteriorwadd1ddaedac0dbac478444718ac2f19211"] = "VF_250_Lore_01",
    ["lore_marker_nid150calderabridgewad2eabc6ebc9dafd40b34cb41a6ffcd2d4"] = "NIF_150_Lore_01",
  }

  local function isDirectlyCollected(row)
    if type(game) ~= "table" then return false end
    local cid = row.CatalogueId
    if not cid then return false end
    local fam = row.Family

    if fam == "treasure_dig" then
      local q = digQuests[cid]
      if q and type(game.QuestManager) == "table" and type(game.QuestManager.GetQuestState) == "function" then
        local ok, st = pcall(game.QuestManager.GetQuestState, q)
        if ok and st == "Complete" then return true end
        local ok2, pst = pcall(game.QuestManager.GetQuestState, q .. "_Parent")
        if ok2 and pst == "Complete" then return true end
      end
    elseif fam == "treasure_map" then
      local mq = mapQuests[cid]
      if mq and type(game.QuestManager) == "table" and type(game.QuestManager.GetQuestState) == "function" then
        local ok, st = pcall(game.QuestManager.GetQuestState, mq)
        if ok and st and st ~= "" and st ~= "Inactive" then return true end
      end
    elseif fam == "jotnar_shrine" then
      local sr = shrineResources[cid]
      if sr and type(game.Wallets) == "table" then
        if type(game.Wallets.HasResource) == "function" then
          local ok, res = pcall(game.Wallets.HasResource, "HERO", sr)
          if ok and res == true then return true end
          local ok2, res2 = pcall(game.Wallets.HasResource, "HERO_SAVEONLY", sr)
          if ok2 and res2 == true then return true end
        end
        if type(game.Wallets.GetResourceValue) == "function" then
          local ok, val = pcall(game.Wallets.GetResourceValue, "HERO", sr)
          if ok and type(val) == "number" and val > 0 then return true end
          local ok2, val2 = pcall(game.Wallets.GetResourceValue, "HERO_SAVEONLY", sr)
          if ok2 and type(val2) == "number" and val2 > 0 then return true end
        end
      end
    elseif fam == "lore_marker" then
      local lr = loreResources[cid]
      if lr and type(game.Wallets) == "table" then
        if type(game.Wallets.HasResource) == "function" then
          local ok, res = pcall(game.Wallets.HasResource, "HERO", lr)
          if ok and res == true then return true end
          local ok2, res2 = pcall(game.Wallets.HasResource, "HERO_SAVEONLY", lr)
          if ok2 and res2 == true then return true end
        end
        if type(game.Wallets.GetResourceValue) == "function" then
          local ok, val = pcall(game.Wallets.GetResourceValue, "HERO", lr)
          if ok and type(val) == "number" and val > 0 then return true end
          local ok2, val2 = pcall(game.Wallets.GetResourceValue, "HERO_SAVEONLY", lr)
          if ok2 and type(val2) == "number" and val2 > 0 then return true end
        end
      end
    elseif fam == "lore_scroll" then
      local scr = scrollResources[cid]
      if scr and type(game.Wallets) == "table" then
        if type(game.Wallets.HasResource) == "function" then
          local ok, res = pcall(game.Wallets.HasResource, "HERO", scr)
          if ok and res == true then return true end
          local ok2, res2 = pcall(game.Wallets.HasResource, "HERO_SAVEONLY", scr)
          if ok2 and res2 == true then return true end
        end
        if type(game.Wallets.GetResourceValue) == "function" then
          local ok, val = pcall(game.Wallets.GetResourceValue, "HERO", scr)
          if ok and type(val) == "number" and val > 0 then return true end
          local ok2, val2 = pcall(game.Wallets.GetResourceValue, "HERO_SAVEONLY", scr)
          if ok2 and type(val2) == "number" and val2 > 0 then return true end
        end
      end
    end
    return false
  end

  local function syncDirectObservations(rt, epoch)
    if rt == nil or rt.store == nil then return end
    epoch = epoch or rt.store:Epoch()
    local before = rt.store:Revision()
    for _, row in ipairs(rows) do
      if row.CatalogueId and rt.store:Get(row.CatalogueId) ~= "collected" and isDirectlyCollected(row) then
        rt.store:Observe(row.CatalogueId, "collected", epoch)
      end
    end
    if rt.store:Revision() ~= before then rt:Changed() end
  end

  local targetRow = nil

  local function updateHighlights(self)
    local target = self or activeMap
    if target == nil or type(UI) ~= "table" or type(UI.Anim) ~= "function" then return end
    for name, icon in pairs(target.completionistMapV105LocationIcons or {}) do
      local row = byName[name]
      if targetRow ~= nil and targetRow == row then
        pcall(UI.Anim, icon, AS_ForwardCycle_NoReset, "", 1)
      else
        pcall(UI.Anim, icon, AS_Forward, "", 0, 0)
      end
    end
  end

  local function hideTarget()
    if targetRow == nil then return true end
    local ok, result = pcall(game.Compass.HideMarker, targetRow.Name)
    if not ok or result == false then return false end
    targetRow = nil
    cleanupPending = nil
    updateHighlights(activeMap)
    return true
  end

  _G.CompletionistMapV105ReleaseLocationCompass = function()
    local ok = hideTarget()
    if activeMap and type(activeMap.UpdateMapMarkerHighlights) == "function" then
      pcall(activeMap.UpdateMapMarkerHighlights, activeMap)
    end
    return ok
  end
  _G.CompletionistMapV105HasLocationCompassTarget = function()
    return targetRow ~= nil
  end


  local function hideCollectedTarget()
    if targetRow ~= nil and (cleanupPending or (State and State:Get(targetRow.CatalogueId) == "collected") or isDirectlyCollected(targetRow)) then
      cleanupPending = true
      hideTarget()
    end
  end

  if runtime then
    runtime.cleanup = hideCollectedTarget
    runtime.directObserver = syncDirectObservations
  end

  if _G.CompletionistMapV105PersistentShowAll == nil then
    _G.CompletionistMapV105PersistentShowAll = true
  end
  if _G.CompletionistMapV105PersistentShowCategories == nil then
    _G.CompletionistMapV105PersistentShowCategories = true
  end

  _G.CompletionistMapV105ShowAll = function(val)
    if val ~= nil then _G.CompletionistMapV105PersistentShowAll = (val == true) end
    return _G.CompletionistMapV105PersistentShowAll
  end

  _G.CompletionistMapV105ShowCategories = function(val)
    if val ~= nil then _G.CompletionistMapV105PersistentShowCategories = (val == true) end
    return _G.CompletionistMapV105PersistentShowCategories
  end

  local function filter(self)
    return self.filterButtonMapping and self.filterButtonMapping[self.filterIndex] or 1
  end

  local function visible(self, row)
    if State and row.CatalogueId and State:Get(row.CatalogueId) == "collected" then return false end
    if isDirectlyCollected(row) then return false end
    if self.isOpenedForFastTravel or self.currRealmName ~= row.Realm then return false end
    local kind = filter(self)
    if kind == 1 then
      return _G.CompletionistMapV105ShowAll()
    elseif kind == -101 or kind == byFamily[row.Family].Filter then
      return _G.CompletionistMapV105ShowCategories()
    end
    return false
  end

  local function clearSelection(self, icon)
    if icon == nil or self.mapIconCollision == icon then self.mapIconCollision = nil end
    self.completionistMapV105LocationSelected = nil
    self.currMarkerID = nil
    if activeSelectionContext then
      pcall(function() self:SetReticleInfo(activeSelectionContext, "", "") end)
      pcall(function() self:UpdateFooterButtonPrompt(activeSelectionContext.menu, false, false) end)
    end
  end

  local function recycle(self)
    for _, icon in pairs(self.completionistMapV105LocationIcons or {}) do
      if type(UI) == "table" and type(UI.Anim) == "function" then
        pcall(UI.Anim, icon, AS_Forward, "", 0, 0)
      end
      pcall(Map.RecycleIcon, icon)
      if self.mapIconCollision == icon then self.mapIconCollision = nil end
    end
    self.completionistMapV105LocationIcons = {}
    self.completionistMapV105LocationSelected = nil
    self.completionistMapV105LocationVisibility = nil
  end

  local function visibilityKey(self)
    local rev = State and State:Revision() or 0
    return tostring(self.currRealmName) .. ":" .. tostring(filter(self)) ..
      ":" .. tostring(self.isOpenedForFastTravel == true) .. ":" .. tostring(rev) ..
      ":" .. tostring(_G.CompletionistMapV105ShowAll()) .. ":" .. tostring(_G.CompletionistMapV105ShowCategories())
  end

  local function sync(self)
    if self == nil then return end
    activeMap = self
    local icons = self.completionistMapV105LocationIcons or {}
    self.completionistMapV105LocationIcons = icons
    for name, icon in pairs(icons) do
      if byName[name] == nil or not visible(self, byName[name]) then
        pcall(Map.RecycleIcon, icon)
        if self.completionistMapV105LocationSelected == byName[name] then
          clearSelection(self, icon)
        elseif self.mapIconCollision == icon then
          self.mapIconCollision = nil
        end
        icons[name] = nil
      end
    end
    for _, row in ipairs(rows) do
      if visible(self, row) and icons[row.Name] == nil then
        local ok, icon = pcall(function()
          local info = game.Map.GetMarkerInfo(row.Name)
          if type(info) ~= "table" or tostring(info.Id) ~= row.IdString then return nil end
          local found, region = Map.FindRegionFromMarker(info.Id)
          if found ~= true or region == nil then return nil end
          return Map.CreateMarkerIcon(info.Id, region, "")
        end)
        if ok and icon ~= nil then
          icons[row.Name] = icon
          pcall(function()
            icon:Show()
            if type(UI) == "table" and type(UI.SetIsClickable) == "function" then
              UI.SetIsClickable(icon)
            end
          end)
        else
          print("[CompletionistLocations] create_failed name=" .. row.Name)
        end
      end
    end
    updateHighlights(self)
    self.completionistMapV105LocationVisibility = visibilityKey(self)
  end


  _G.CompletionistMapV105LocationStateChanged = function(boundary)
    if boundary then
      if targetRow then cleanupPending = true end
      if activeMap then clearSelection(activeMap) end
    end
    hideCollectedTarget()
    sync(activeMap)
  end

  local createPins = CompletionistMapV100_CreateMapPin
  CompletionistMapV100_CreateMapPin = function(self, ...)
    if syncDirectObservations and runtime then
      pcall(syncDirectObservations, runtime, State and State:Epoch() or 0)
    end
    local result = createPins(self, ...)
    if runtime then runtime:Poll() end
    sync(self)
    return result
  end

  -- Reuse the three authored Niflheim rift IDs. The location layer owns their
  -- icons in normal map mode, so native enumeration must not draw a second copy.
  local getRealmInfo = MapOn.GetRealmMarkerInfo
  MapOn.GetRealmMarkerInfo = function(self, ...)
    local result = getRealmInfo(self, ...)
    if not self.isOpenedForFastTravel then
      local remaining = {}
      for _, info in ipairs(self.realmMarkerInfo or {}) do
        if nativeIds[tostring(info.Id)] then
          if info.iconGO ~= nil then Map.RecycleIcon(info.iconGO); info.iconGO = nil end
        else
          remaining[#remaining + 1] = info
        end
      end
      self.realmMarkerInfo = remaining
      self:UpdateFilterButtonMapping()
    end
    return result
  end

  local updateMapping = MapOn.UpdateFilterButtonMapping
  MapOn.UpdateFilterButtonMapping = function(self, ...)
    local selected = filter(self)
    local result = updateMapping(self, ...)
    local present, families = {}, {}
    for _, kind in ipairs(self.filterButtonMapping) do present[kind] = true end
    for _, row in ipairs(rows) do
      if row.Realm == self.currRealmName then families[row.Family] = true end
    end
    local function add(kind)
      if not present[kind] then
        self.filterButtonMapping[#self.filterButtonMapping + 1] = kind
        present[kind] = true
      end
    end
    if next(families) ~= nil then add(-101) end
    for _, category in ipairs(categories) do
      if families[category.Family] then add(category.Filter) end
    end
    for index, kind in ipairs(self.filterButtonMapping) do
      if kind == selected then
        self.filterIndex = index
        if kind > 0 then self.markerIncludeFlags = markerFilters[kind].markerIncludeFlags end
        break
      end
    end
    self:UpdateFilterUI()
    return result
  end

  local nextFilter = MapOn.Menu_Next_Filter
  MapOn.Menu_Next_Filter = function(self, ...)
    local result = nextFilter(self, ...)
    sync(self)
    return result
  end

  -- Realm entry calls these after rebuilding the filter list. Keep a restored
  -- family filter from repopulating the game's stock markers on that path.
  for _, method in ipairs({"GetAlwaysOnMarkers", "GetMarkers"}) do
    local previous = MapOn[method]
    MapOn[method] = function(self, ...)
      if not self.isOpenedForFastTravel and filter(self) < 0 then
        self:ClearMarkers(true)
        return
      end
      return previous(self, ...)
    end
  end

  local update = MapOn.Update
  MapOn.Update = function(self, ...)
    local result = update(self, ...)
    if runtime then runtime:Poll() end
    hideCollectedTarget()
    if self.completionistMapV105LocationVisibility ~= visibilityKey(self) then sync(self) end
    return result
  end

  for _, method in ipairs({"SubmenuExit", "Exit"}) do
    local previous = MapOn[method]
    MapOn[method] = function(self, ...)
      recycle(self)
      if activeMap == self then activeMap = nil; activeSelectionContext = nil end
      return previous(self, ...)
    end
  end

  local previousClearIcons = MapOn.ClearIcons
  MapOn.ClearIcons = function(self, ...)
    recycle(self)
    if activeMap == self then activeMap = nil; activeSelectionContext = nil end
    return previousClearIcons(self, ...)
  end

  _G.CompletionistMapV105ToggleMarkers = function(map)
    local target = map or activeMap
    if target == nil or target.isOpenedForFastTravel then return false end
    local kind = filter(target)
    if kind == 1 then
      _G.CompletionistMapV105ShowAll(not _G.CompletionistMapV105ShowAll())
    else
      _G.CompletionistMapV105ShowCategories(not _G.CompletionistMapV105ShowCategories())
    end
    pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_Region_Hover_Tick") end)
    sync(target)
    if type(_G.CompletionistMapV105ResyncRavens) == "function" then
      pcall(_G.CompletionistMapV105ResyncRavens, target)
    end
    if type(_G.CompletionistMapV105ResyncNornir) == "function" then
      pcall(_G.CompletionistMapV105ResyncNornir, target)
    end
    local menu = target.menu or (activeSelectionContext and activeSelectionContext.menu)
    if menu and type(target.UpdateFooterButtonPrompt) == "function" then
      pcall(target.UpdateFooterButtonPrompt, target, menu, false, false)
    end
    return true
  end

  local previousDown = MapOn.EVT_Down_Release
  MapOn.EVT_Down_Release = function(self, ...)
    local target = self or activeMap
    if target and not target.isOpenedForFastTravel then
      return _G.CompletionistMapV105ToggleMarkers(target)
    end
    if previousDown then return previousDown(self, ...) end
  end

  local previousFooterPrompt = MapOn.UpdateFooterButtonPrompt
  MapOn.UpdateFooterButtonPrompt = function(self, currMenu, showConfirmFastTravel, showGoToJournal)
    if previousFooterPrompt then
      previousFooterPrompt(self, currMenu, showConfirmFastTravel, showGoToJournal)
    end
    if currMenu and type(currMenu.UpdateFooterButton) == "function" then
      if self.isOpenedForFastTravel then
        currMenu:UpdateFooterButton("ActiveMarkers", false)
      else
        local kind = filter(self)
        local shouldShowToggle = (kind == 1 or kind == -101 or kind < -104)
        if shouldShowToggle then
          local isShowing
          if kind == 1 then
            isShowing = _G.CompletionistMapV105ShowAll()
          else
            isShowing = _G.CompletionistMapV105ShowCategories()
          end
          local toggleText = isShowing and "[DownButton] Hide Markers" or "[DownButton] Show Markers"
          currMenu:UpdateFooterButton("ActiveMarkers", true, toggleText)
        else
          currMenu:UpdateFooterButton("ActiveMarkers", false)
        end
      end
      if type(currMenu.UpdateFooterButtonText) == "function" then
        currMenu:UpdateFooterButtonText()
      end
    end
  end

  local function selection(self)
    local row = self.completionistMapV105LocationSelected
    if row == nil then return nil end
    local icon = (self.completionistMapV105LocationIcons or {})[row.Name]
    if icon == nil or not visible(self, row) or (self.currMarkerID ~= nil and tostring(self.currMarkerID) ~= row.IdString) then
      self.completionistMapV105LocationSelected = nil
      return nil
    end
    return row
  end

  local refreshCompassPromptUI

  local collision = MapOn.MapCollisionChangeHandler
  MapOn.MapCollisionChangeHandler = function(self, currState, hits, realmName)
    activeSelectionContext = currState
    self.completionistMapV105LocationSelected = nil
    local result = collision(self, currState, hits, realmName)
    local icons = self.completionistMapV105LocationIcons or {}
    for _, hit in ipairs(hits or {}) do
      for name, icon in pairs(icons) do
        if hit == icon then
          local row = byName[name]
          if row and visible(self, row) then
            self.completionistMapV105LocationSelected = row
            self.currMarkerID = row.IdString
            self.mapIconCollision = icon
            local caption = "Collectible location"
            if State and row.CatalogueId then
              local s = State:Get(row.CatalogueId)
              if s == "remaining" then caption = "Not collected" end
            end
            pcall(function() self:SetReticleInfo(currState, byFamily[row.Family].Title, caption) end)
            if refreshCompassPromptUI then
              refreshCompassPromptUI(self, currState and currState.menu)
            end
            return result
          end
        end
      end
    end
    return result
  end

  local previousMouseClick = MapOn.MouseClickHandler
  MapOn.MouseClickHandler = function(self, currState, ...)
    local sender = (type(UI) == "table" and type(UI.GetEventSenderGameObject) == "function") and UI.GetEventSenderGameObject() or nil

    if sender ~= nil and not self.isOpenedForFastTravel then
      if type(self.goFilterButtons) == "table" then
        for key, button in ipairs(self.goFilterButtons) do
          if sender == button then
            local first = self.completionistMapV100FilterWindowFirst or 1
            local desired = first + key - 1
            if desired <= #(self.filterButtonMapping or {}) then
              self:Menu_Next_Filter(desired - self.filterIndex)
            end
            return
          end
        end
      end
    end

    if not self.isOpenedForFastTravel then
      local clickedRow = nil
      local clickedIcon = nil
      if sender ~= nil then
        for name, icon in pairs(self.completionistMapV105LocationIcons or {}) do
          if sender == icon and self.mapIconCollision == icon then
            clickedRow = byName[name]
            clickedIcon = icon
            break
          end
        end
      end

      if clickedRow ~= nil and clickedIcon ~= nil and visible(self, clickedRow) then
        self.completionistMapV105LocationSelected = clickedRow
        self.currMarkerID = clickedRow.IdString
        self.mapIconCollision = clickedIcon
        self.clickedMarkerInfo = nil
        self.clickedPlayer = false
        local caption = "Collectible location"
        if State and clickedRow.CatalogueId then
          local s = State:Get(clickedRow.CatalogueId)
          if s == "remaining" then caption = "Not collected" end
        end
        pcall(function() self:SetReticleInfo(currState, byFamily[clickedRow.Family].Title, caption) end)
        if refreshCompassPromptUI then
          refreshCompassPromptUI(self, currState and currState.menu)
        end
        pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_Region_Hover_Tick") end)
        return
      end

      if sender ~= nil then
        self.completionistMapV105LocationSelected = nil
      else
        if self.mapIconCollision == nil and not self.testEnvironment then
          return
        end
      end
    end

    if previousMouseClick then return previousMouseClick(self, currState, ...) end
  end

  local previousUpdateHighlights = MapOn.UpdateMapMarkerHighlights
  MapOn.UpdateMapMarkerHighlights = function(self, ...)
    if previousUpdateHighlights then previousUpdateHighlights(self, ...) end
    updateHighlights(self)
  end

  local previousPrompt = MapOn.GetShowOnCompassPrompt
  MapOn.GetShowOnCompassPrompt = function(self, ...)
    local row = selection(self)
    if row == nil then
      local show, label = previousPrompt(self, ...)
      if show and (targetRow ~= nil or _G.CompletionistMapV105TrackedCatalogueId ~= nil or _G.CompletionistMapV105HasNornirCompassTarget()) and
          label == "[AdvanceButton] " .. util.GetLAMSMsg(lamsConsts.AddToCompass) then
        label = "[AdvanceButton] " .. util.GetLAMSMsg(lamsConsts.ReplaceInCompass)
      end
      return show, label
    end
    if self.isOpenedForFastTravel or not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then return false, nil end
    local label = lamsConsts.AddToCompass
    if targetRow == row then
      label = lamsConsts.RemoveFromCompass
    elseif targetRow ~= nil or self.currShownMarkerID ~= nil or
        _G.CompletionistMapV105TrackedCatalogueId ~= nil or
        _G.CompletionistMapV105HasNornirCompassTarget() then
      label = lamsConsts.ReplaceInCompass
    end
    return true, "[AdvanceButton] " .. util.GetLAMSMsg(label)
  end

  refreshCompassPromptUI = function(self, menu)
    local targetMap = self or activeMap
    if targetMap == nil then return end
    local targetMenu = menu or targetMap.menu or (activeSelectionContext and activeSelectionContext.menu)
    local show, text = targetMap:GetShowOnCompassPrompt(targetMenu)
    if show and text then
      if type(util) == "table" and type(util.GetUiObjByName) == "function" then
        pcall(function()
          local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
          if goMapCursorText ~= nil then
            goMapCursorText:Show()
            local top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
            if top ~= nil then
              local handle = util.GetTextHandle(top, "CursorAction_Text")
              if handle ~= nil then
                if type(UI) == "table" and type(UI.SetTextIsClickable) == "function" then
                  UI.SetTextIsClickable(handle)
                end
                if type(UI) == "table" and type(UI.SetText) == "function" then
                  UI.SetText(handle, text)
                end
              end
              top:Show()
            end
          end
        end)
      end
      if targetMenu and type(targetMenu.UpdateFooterButton) == "function" then
        pcall(function()
          targetMenu:UpdateFooterButton("ShowOnCompass", true, text)
          if type(targetMenu.UpdateFooterButtonText) == "function" then
            targetMenu:UpdateFooterButtonText()
          end
        end)
      end
    end
    if targetMenu and type(targetMap.UpdateFooterButtonPrompt) == "function" then
      pcall(targetMap.UpdateFooterButtonPrompt, targetMap, targetMenu, false, false)
    end
  end

  local previousShow = MapOn.ShowOnCompass
  MapOn.ShowOnCompass = function(self, ...)
    local row = selection(self)
    if row == nil then
      local isNornir = (self.completionistMapV105NornirSelected ~= nil)
      local isRaven = (self.completionistMapV105SelectedRaven ~= nil)
      if not isNornir and not isRaven then
        if type(_G.CompletionistMapV105ReleaseRavenCompass) == "function" then
          pcall(_G.CompletionistMapV105ReleaseRavenCompass)
        end
        if type(_G.CompletionistMapV105ReleaseNornirCompass) == "function" then
          pcall(_G.CompletionistMapV105ReleaseNornirCompass)
        end
      end
      if not hideTarget() then return false end
      local res = previousShow and previousShow(self, ...)
      updateHighlights(self)
      return res
    end
    if self.isOpenedForFastTravel or not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then return false end
    if targetRow == row then
      if not hideTarget() then return false end
      pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass") end)
    else
      if type(_G.CompletionistMapV105ReleaseRavenCompass) == "function" then
        if _G.CompletionistMapV105ReleaseRavenCompass() == false then return false end
      end
      if type(_G.CompletionistMapV105ReleaseNornirCompass) == "function" then
        if _G.CompletionistMapV105ReleaseNornirCompass() == false then return false end
      end
      if not hideTarget() then return false end
      if self.currShownMarkerID ~= nil then
        pcall(game.Compass.HideMarker, self.currShownMarkerID)
        self.currShownMarkerID = nil
      end
      local stockMarkers = (type(enabledShowOnCompassMarkerFlags) == "table" and
          type(game.Compass) == "table" and
          type(game.Compass.FindMarkersByIconClass) == "function") and
          game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags) or nil
      if type(stockMarkers) == "table" then
        for _, id in ipairs(stockMarkers) do
          pcall(game.Compass.HideMarker, id)
        end
      end
      pcall(function() self:UpdateMapMarkerHighlights() end)
      local familyClasses = {
        ["artefact"] = "CompletionistArtefact",
        ["cipher_chest"] = "CompletionistCipherChest",
        ["coffin"] = "CompletionistCoffin",
        ["jotnar_shrine"] = "CompletionistJotnarShrine",
        ["legendary_chest"] = "CompletionistLegendaryChest",
        ["lore_marker"] = "CompletionistLoreMarker",
        ["lore_scroll"] = "CompletionistLoreScroll",
        ["nornir_bell"] = "CompletionistNornirBell",
        ["nornir_chest"] = "CompletionistNornirChest",
        ["nornir_mechanism"] = "CompletionistNornirMechanism",
        ["nornir_seal"] = "CompletionistNornirSeal",
        ["realm_tear"] = "CompletionistRealmTear",
        ["treasure_dig"] = "CompletionistTreasureDig",
        ["treasure_map"] = "CompletionistTreasureMap",
        ["wooden_chest"] = "CompletionistWoodenChest",
      }
      local compassClass = (row.Family and familyClasses[row.Family]) or "SIDE"
      local ok, result = pcall(game.Compass.ShowMarker, row.Name, compassClass)
      if not ok or result == false then
        ok, result = pcall(game.Compass.ShowMarker, row.Name, "SIDE")
      end
      if not ok or result == false then return false end
      targetRow = row
      if _G.CompletionistMapV100Target then _G.CompletionistMapV100Target.active = false end
      pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass") end)
    end
    updateHighlights(self)
    local currState = select(1, ...)
    if refreshCompassPromptUI then
      refreshCompassPromptUI(self, currState and currState.menu)
    end
    return true
  end


  -- Expose state publisher for trusted event adapters (active outside map).
  _G.CompletionistMapV105PublishLocationState = function(id, state, epoch)
    if State == nil then return false end
    if runtime then return runtime:Observe(id, state, epoch) end
    local accepted = State:Observe(id, state, epoch)
    if accepted then _G.CompletionistMapV105LocationStateChanged() end
    return accepted
  end

  local controller = _G.CompletionistMapV105Nornir
  local beginEpoch = controller.BeginEpoch
  controller.BeginEpoch = function(self, ...)
    local accepted = beginEpoch(self, ...)
    if accepted then
      local epoch = self.service.epoch
      if runtime then runtime:BeginEpoch(epoch)
      elseif State and epoch > State:Epoch() then
        State:BeginEpoch(epoch)
        _G.CompletionistMapV105LocationStateChanged(true)
      end
    end
    return accepted
  end
  local mode = State and "hide_collected" or "all_known_locations"
  print("[CompletionistLocations] installed rows=" .. tostring(#rows) ..
    " categories=" .. tostring(#categories) .. " art=stock_blue_quest mode=" .. mode)
end
-- END COMPLETIONIST V0.10.5 COLLECTIBLE LOCATIONS
