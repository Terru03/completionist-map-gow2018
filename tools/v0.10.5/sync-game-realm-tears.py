#!/usr/bin/env python3
"""Synchronize Realm Tear completion fixes into the installed game mapmenu.lua."""
from pathlib import Path
import sys

GAME_MAP = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua")

def sync():
    if not GAME_MAP.exists():
        print(f"Error: {GAME_MAP} does not exist.")
        sys.exit(1)

    text = GAME_MAP.read_text(encoding="utf-8")
    original_text = text

    # Backup
    backup_path = GAME_MAP.with_suffix(".lua.bak_realm_tears_sync")
    if not backup_path.exists():
        backup_path.write_text(original_text, encoding="utf-8")
        print(f"Created backup at {backup_path}")

    # =========================================================================
    # 1. LOADED MODULE: observeScript rift handling
    # =========================================================================
    t1_old = """  elseif adapter == 'shrine' then
    if type(script.IsTriptychCompleted) == 'function' then
      local ok, done = pcall(script.IsTriptychCompleted)
      if ok and type(done) == 'boolean' then
        return done and 'collected' or 'remaining'
      end
    end
  end
  return nil"""

    t1_new = """  elseif adapter == 'shrine' then
    if type(script.IsTriptychCompleted) == 'function' then
      local ok, done = pcall(script.IsTriptychCompleted)
      if ok and type(done) == 'boolean' then
        return done and 'collected' or 'remaining'
      end
    end
  elseif adapter == 'rift' then
    if type(script.hasOpened) == 'boolean' then
      return script.hasOpened and 'collected' or 'remaining'
    end
    if type(script.GetState) == 'function' then
      local ok, st = pcall(script.GetState)
      if ok and type(st) == 'number' then
        return st == 4 and 'collected' or 'remaining'
      end
    end
  end
  return nil"""

    assert text.count(t1_old) == 1, f"Anchor 1 count: {text.count(t1_old)}"
    text = text.replace(t1_old, t1_new, 1)

    # =========================================================================
    # 2. LOADED MODULE: read(row) placement fallback on rift
    # =========================================================================
    t2_old = """    if owner == nil then
      if row.adapter == 'chest' and #oMatches == 0 then
        owner = placement
      else
        return nil
      end
    end"""

    t2_new = """    if owner == nil then
      if (row.adapter == 'chest' or row.adapter == 'rift') and #oMatches == 0 then
        owner = placement
      else
        return nil
      end
    end"""

    assert text.count(t2_old) == 1, f"Anchor 2 count: {text.count(t2_old)}"
    text = text.replace(t2_old, t2_new, 1)

    # =========================================================================
    # 3. LOADED MODULE: read(row) check placement directly if owner lacks script
    # =========================================================================
    t3_old = """  -- 1. Check owner directly
  local state = observeScript(owner, row.adapter)
  if state ~= nil then return state end"""

    t3_new = """  -- 1. Check owner directly
  local state = observeScript(owner, row.adapter)
  if state ~= nil then return state end
  if placement ~= nil and placement ~= owner then
    state = observeScript(placement, row.adapter)
    if state ~= nil then return state end
  end"""

    assert text.count(t3_old) == 1, f"Anchor 3 count: {text.count(t3_old)}"
    text = text.replace(t3_old, t3_new, 1)

    # =========================================================================
    # 4. LOADED MODULE: read(row) step 5 rift fast lookup
    # =========================================================================
    t4_old = """  -- 4. Fast direct lookup for chest scripts under placement or owner
  if row.adapter == 'chest' then
    for _, container in ipairs({owner, placement}) do
      if container ~= nil and type(container.FindSingleGOByName) == 'function' then
        for _, q in ipairs({'gochestscript', 'chestscript', '*chestscript*'}) do
          local ok, node = pcall(container.FindSingleGOByName, container, q)
          if ok and node ~= nil then
            local st = observeScript(node, row.adapter)
            if st ~= nil then return st end
            if node.Child then
              st = observeScript(node.Child, row.adapter)
              if st ~= nil then return st end
            end
          end
        end
      end
    end
  end

  return nil"""

    t4_new = """  -- 4. Fast direct lookup for chest scripts under placement or owner
  if row.adapter == 'chest' then
    for _, container in ipairs({owner, placement}) do
      if container ~= nil and type(container.FindSingleGOByName) == 'function' then
        for _, q in ipairs({'gochestscript', 'chestscript', '*chestscript*'}) do
          local ok, node = pcall(container.FindSingleGOByName, container, q)
          if ok and node ~= nil then
            local st = observeScript(node, row.adapter)
            if st ~= nil then return st end
            if node.Child then
              st = observeScript(node.Child, row.adapter)
              if st ~= nil then return st end
            end
          end
        end
      end
    end
  end

  -- 5. Fast direct lookup for rift scripts under placement or owner
  if row.adapter == 'rift' then
    local containers = {owner, placement}
    if owner ~= nil and owner.Parent ~= nil then
      containers[#containers + 1] = owner.Parent
    end
    if placement ~= nil and placement.Parent ~= nil then
      containers[#containers + 1] = placement.Parent
    end
    for _, container in ipairs(containers) do
      if container ~= nil and type(container.FindSingleGOByName) == 'function' then
        for _, q in ipairs({'gopocketrift_interact_loot', 'pocketrift_interact_loot', '*interact_loot*', '*pocketrift*'}) do
          local ok, node = pcall(container.FindSingleGOByName, container, q)
          if ok and node ~= nil then
            local st = observeScript(node, row.adapter)
            if st ~= nil then return st end
            if node.Child then
              st = observeScript(node.Child, row.adapter)
              if st ~= nil then return st end
            end
          end
        end
      end
      if container ~= nil and type(container.FindGOsByName) == 'function' then
        for _, q in ipairs({'gopocketrift_interact_loot', 'pocketrift_interact_loot', '*interact_loot*'}) do
          local ok, nodes = pcall(container.FindGOsByName, container, q)
          if ok and type(nodes) == 'table' then
            for _, node in ipairs(nodes) do
              local st = observeScript(node, row.adapter)
              if st ~= nil then return st end
              if node.Child then
                st = observeScript(node.Child, row.adapter)
                if st ~= nil then return st end
              end
            end
          end
        end
      end
    end
  end

  return nil"""

    assert text.count(t4_old) == 1, f"Anchor 4 count: {text.count(t4_old)}"
    text = text.replace(t4_old, t4_new, 1)

    # =========================================================================
    # 5. LOCATION MAP: riftQuests table definition
    # =========================================================================
    t5_old = """    ["lore_marker_nid150calderabridgewad2eabc6ebc9dafd40b34cb41a6ffcd2d4"] = "NIF_150_Lore_01",
  }

  local function isDirectlyCollected(row)"""

    t5_new = """    ["lore_marker_nid150calderabridgewad2eabc6ebc9dafd40b34cb41a6ffcd2d4"] = "NIF_150_Lore_01",
  }

  local riftQuests = {
    ["realm_tear_10374be1dacc7b5afc9b38ff1c50b3f5"] = "RegionSummary_NID_PocketRift_Parent",
    ["realm_tear_80a81219135f07ea1c0eb1948748fc58"] = "RegionSummary_NID_PocketRift_Parent",
    ["realm_tear_ad3009f9f80b31ab80419fd380e60c1c"] = "RegionSummary_NID_PocketRift_Parent",
    ["realm_tear_885f79d8699b58e655739f1b924bf442"] = "RegionSummary_ALF_PocketRift_Parent",
    ["realm_tear_d9d5fe53b4d7bd0c88376c7647f5537e"] = "RegionSummary_ALF_PocketRift_Parent",
    ["realm_tear_c3d17070f981647e7189e2076fbcc55c"] = "RegionSummary_HTTK_PocketRift_Parent",
    ["realm_tear_75c3365cbb3042f761a82660c314147e"] = "RegionSummary_CALT_PocketRift_Parent",
    ["realm_tear_12672293750dfc6b1381cf5159ad0615"] = "RegionSummary_ISL_PocketRift_Parent",
    ["realm_tear_cb9a35e72a6bd571c820349c901762a9"] = "RegionSummary_ISL_PocketRift_Parent",
    ["realm_tear_1c939364d61323b0c9db30a25da5b0f0"] = "RegionSummary_FOO_PocketRift_Parent",
    ["realm_tear_a3857496e778be84cdb14938feb3885d"] = "RegionSummary_FOO_PocketRift_Parent",
    ["realm_tear_64256db4dca56cbedc9c2ad1bb454bef"] = "RegionSummary_RP_PocketRift_Parent",
    ["realm_tear_f4600a74cbfaceabd4ba6d80a59a66bc"] = "RegionSummary_RP_PocketRift_Parent",
    ["realm_tear_64b7ac07cbf1db2d7956e3298e23970f"] = "RegionSummary_CALS_PocketRift_Parent",
    ["realm_tear_664c0fd312a6e88d8739f7d5af968fe3"] = "RegionSummary_CALS_PocketRift_Parent",
    ["realm_tear_6f5037ce091595b1bc2b0ab31cfaf05b"] = "RegionSummary_CALS_PocketRift_Parent",
    ["realm_tear_71588ab9681c6184279e7384fdafbbdd"] = "RegionSummary_CALS_PocketRift_Parent",
    ["realm_tear_ae12a2c33fd8e441bf159a5fd7ac3c22"] = "RegionSummary_CALS_PocketRift_Parent",
    ["realm_tear_af0e22716b928bcf52889387ffc91c4f"] = "RegionSummary_CALS_PocketRift_Parent",
    ["realm_tear_2b6da4fe76312741d21ade4905d66ff4"] = "RegionSummary_MID_PocketRift_Parent",
    ["realm_tear_b24fe2ba5298d202f41bda97b2a00845"] = "RegionSummary_MID_PocketRift_Parent",
  }

  local function isDirectlyCollected(row)"""

    assert text.count(t5_old) == 1, f"Anchor 5 count: {text.count(t5_old)}"
    text = text.replace(t5_old, t5_new, 1)

    # =========================================================================
    # 6. LOCATION MAP: realm_tear branch in isDirectlyCollected
    # =========================================================================
    t6_old = """    elseif fam == "lore_scroll" then
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
    return false"""

    t6_new = """    elseif fam == "lore_scroll" then
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
    elseif fam == "realm_tear" then
      local rq = riftQuests[cid]
      if rq and type(game.QuestManager) == "table" and type(game.QuestManager.GetQuestState) == "function" then
        local ok, st = pcall(game.QuestManager.GetQuestState, rq)
        if ok and st == "Complete" then return true end
      end
      if type(game.QuestManager) == "table" and type(game.QuestManager.GetQuestState) == "function" then
        local ok, lst = pcall(game.QuestManager.GetQuestState, "Quest_Labor_RiftPockets_Silver")
        if ok and lst == "Complete" then return true end
      end
      if (cid == "realm_tear_10374be1dacc7b5afc9b38ff1c50b3f5" or
          cid == "realm_tear_80a81219135f07ea1c0eb1948748fc58" or
          cid == "realm_tear_ad3009f9f80b31ab80419fd380e60c1c") and
         type(game.Wallets) == "table" then
        if type(game.Wallets.GetResourceValue) == "function" then
          local ok, val = pcall(game.Wallets.GetResourceValue, "HERO", "NiflheimTrophyTracker")
          if ok and type(val) == "number" and val > 0 then return true end
          local ok2, val2 = pcall(game.Wallets.GetResourceValue, "HERO_SAVEONLY", "NiflheimTrophyTracker")
          if ok2 and type(val2) == "number" and val2 > 0 then return true end
        end
        if type(game.Wallets.HasResource) == "function" then
          local ok, res = pcall(game.Wallets.HasResource, "HERO", "NiflheimTrophyTracker")
          if ok and res == true then return true end
          local ok2, res2 = pcall(game.Wallets.HasResource, "HERO_SAVEONLY", "NiflheimTrophyTracker")
          if ok2 and res2 == true then return true end
        end
      end
    end
    return false"""

    assert text.count(t6_old) == 1, f"Anchor 6 count: {text.count(t6_old)}"
    text = text.replace(t6_old, t6_new, 1)

    # Validate Lua syntax with lupa
    try:
        import lupa
        lua = lupa.LuaRuntime()
        lua.compile(text)
        print("Lua syntax check: PASSED (compiled cleanly via Lupa)")
    except Exception as e:
        print(f"Lua syntax error: {e}")
        sys.exit(1)

    GAME_MAP.write_text(text, encoding="utf-8")
    print(f"Successfully patched {GAME_MAP} ({len(text):,} bytes).")

if __name__ == "__main__":
    sync()
