#!/usr/bin/env python3
"""Build an offline mapmenu.lua candidate with stock single-target Raven semantics.

The Completionist Raven uses a custom CompassIconClass. The older inner Raven bridge
queries only the stock enabled compass classes, so it can successfully show the custom
Raven but cannot reliably detect that same Raven for Remove from Compass. This wrapper
owns Raven-origin add/replace/remove actions using the live CompletionistRaven manager
query, while continuing to delegate ordinary stock-marker actions to the game's existing
MapOn.ShowOnCompass implementation.

It also derives Raven prompt text from live manager state (plus a short asynchronous
intent guard) so Add / Replace / Remove text stays synchronized after either Raven-origin
or stock-origin replacement.

No game file is written by this builder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "55e6ab3771417211cab670aaa4871e5f4083dac8f00f324d5584e803bb9a11a9"
BEGIN = "-- BEGIN COMPLETIONIST V0.10.4 SINGLE ACTIVE COMPASS CONTROL"
END = "-- END COMPLETIONIST V0.10.4 SINGLE ACTIVE COMPASS CONTROL"

LUA = r'''-- BEGIN COMPLETIONIST V0.10.4 SINGLE ACTIVE COMPASS CONTROL
-- Final Raven-only manager bridge for v0.10.4 testing.
--
-- Why this wrapper owns Raven-origin actions:
-- the older Raven bridge's shownState() queries enabledShowOnCompassMarkerFlags,
-- which contains stock classes but not CompletionistRaven. Once the Raven uses its
-- custom class, delegating Remove from Compass to that older bridge can re-show the
-- Raven instead of hiding it. This layer uses FindMarkersByIconClass({CompletionistRaven})
-- for the Raven and the stock class list for ordinary targets.
do
  local prefix = "[CompletionistMap v0.10.4-single-active-v3] "
  local ravenCandidate = "Completionist_V103_Veithurgard_Raven_01"
  local ravenClass = "CompletionistRaven"
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousPrompt = MapOn.GetShowOnCompassPrompt

  local stockReplacePending = false
  local ravenIntent = nil -- "tracked" / "untracked" while native manager settles
  local retryFrames = 0
  local retryBucket = -1

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function ravenSelected(self)
    return self ~= nil and self.completionistMapV100Selected == true
  end

  local function candidateInfo()
    local ok, info = pcall(function()
      return game.Map.GetMarkerInfo(ravenCandidate)
    end)
    if not ok then
      return nil, tostring(info)
    end
    if info == nil then
      return nil, "candidate_missing"
    end
    return info, nil
  end

  local function candidateIdString()
    local info = candidateInfo()
    return info ~= nil and tostring(info.Id) or nil
  end

  local function ravenShown()
    local candidateId = candidateIdString()
    if candidateId == nil then
      return false, false, "candidate_lookup_failed"
    end

    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not ok then
      return false, false, tostring(ids)
    end

    for _, id in ipairs(ids or {}) do
      if tostring(id) == candidateId then
        return true, true, nil
      end
    end
    return false, true, nil
  end

  local function stockTargets()
    local ravenId = candidateIdString()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not ok then
      return {}, false, tostring(ids)
    end

    local out = {}
    for _, id in ipairs(ids or {}) do
      if ravenId == nil or tostring(id) ~= ravenId then
        out[#out + 1] = id
      end
    end
    return out, true, nil
  end

  local function actionText(lamsId)
    return "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  local function hideRaven(reason)
    local ok, err = pcall(function()
      game.Compass.HideMarker(ravenCandidate)
    end)
    log("HIDE_RAVEN",
      "reason=" .. tostring(reason) ..
      " ok=" .. tostring(ok) ..
      " error=" .. tostring(err))
    return ok
  end

  local function hideStockTargets(reason)
    local ids, ok, err = stockTargets()
    if not ok then
      log("HIDE_STOCK", "reason=" .. tostring(reason) .. " queryOK=false error=" .. tostring(err))
      return false, 0
    end

    for _, id in ipairs(ids) do
      local hideOK, hideErr = pcall(function()
        game.Compass.HideMarker(id)
      end)
      log("HIDE_STOCK",
        "reason=" .. tostring(reason) ..
        " id=" .. tostring(id) ..
        " ok=" .. tostring(hideOK) ..
        " error=" .. tostring(hideErr))
    end
    return true, #ids
  end

  local function suppressLegacyRavenHud()
    local target = _G.CompletionistMapV100Target
    if target ~= nil and target.type == "Raven" and target.active == true then
      target.active = false
      log("LEGACY_R3L3_DISABLED", "reason=native_custom_raven_tracking")
    end
  end

  local function refreshRavenPrompt(self)
    if self == nil or self.menu == nil or not ravenSelected(self) then return end
    local show, text = self:GetShowOnCompassPrompt(self.menu)

    local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
    if goMapCursorText ~= nil then
      goMapCursorText:Show()
      local goCursorInfoTop = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
      if goCursorInfoTop ~= nil then
        local thPrompt = util.GetTextHandle(goCursorInfoTop, "CursorAction_Text")
        if thPrompt ~= nil then
          UI.SetTextIsClickable(thPrompt)
          UI.SetText(thPrompt, show and text or "")
        end
        if show then goCursorInfoTop:Show() else goCursorInfoTop:Hide() end
      end
    end

    self.menu:UpdateFooterButton("ShowOnCompass", show, text)
    self.menu:UpdateFooterButtonText()
    log("PROMPT_REFRESH",
      "visible=" .. tostring(show) ..
      " intent=" .. tostring(ravenIntent) ..
      " text=" .. tostring(text))
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    local show, previousText = previousPrompt(self, currMenu)
    if not ravenSelected(self) or not show then
      return show, previousText
    end

    -- During an asynchronous user action, reflect the requested state immediately.
    if ravenIntent == "tracked" then
      return true, actionText(lamsConsts.RemoveFromCompass)
    elseif ravenIntent == "untracked" then
      local others, stockOK = stockTargets()
      if stockOK and #others > 0 then
        return true, actionText(lamsConsts.ReplaceInCompass)
      end
      return true, actionText(lamsConsts.AddToCompass)
    end

    local shown, ravenOK, ravenErr = ravenShown()
    if not ravenOK then
      log("PROMPT_LIVE_QUERY", "ravenQueryOK=false error=" .. tostring(ravenErr) .. " fallback=previous")
      return show, previousText
    end
    if shown then
      return true, actionText(lamsConsts.RemoveFromCompass)
    end

    local others, stockOK, stockErr = stockTargets()
    if not stockOK then
      log("PROMPT_LIVE_QUERY", "stockQueryOK=false error=" .. tostring(stockErr) .. " fallback=previous")
      return show, previousText
    end
    if #others > 0 then
      return true, actionText(lamsConsts.ReplaceInCompass)
    end
    return true, actionText(lamsConsts.AddToCompass)
  end

  function MapOn:ShowOnCompass(currState)
    if not ravenSelected(self) then
      local shown, queryOK, queryErr = ravenShown()
      local trackedHint = _G.CompletionistMapV103NativeRavenTracked == true

      if shown or trackedHint then
        stockReplacePending = true
        ravenIntent = "untracked"
        retryFrames = 0
        retryBucket = -1
        log("STOCK_REPLACE_BEGIN",
          "ravenShown=" .. tostring(shown) ..
          " trackedHint=" .. tostring(trackedHint) ..
          " queryOK=" .. tostring(queryOK) ..
          " queryError=" .. tostring(queryErr))
        hideRaven("stock_marker_selected")
      else
        stockReplacePending = false
      end

      -- Stock-origin actions stay game-owned.
      return previousShow(self, currState)
    end

    stockReplacePending = false
    retryFrames = 0
    retryBucket = -1

    local info, infoErr = candidateInfo()
    if info == nil then
      ravenIntent = nil
      log("RAVEN_ACTION", "refused=candidate_missing error=" .. tostring(infoErr))
      return
    end

    local shown, queryOK, queryErr = ravenShown()
    if not queryOK then
      ravenIntent = nil
      log("RAVEN_ACTION", "refused=custom_class_query_failed error=" .. tostring(queryErr))
      return
    end

    if shown then
      if hideRaven("user_remove") then
        ravenIntent = "untracked"
        self.currShownMarkerID = nil
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
        refreshRavenPrompt(self)
        log("RAVEN_REMOVE", "request_queued=true")
      end
      return
    end

    local stockOK, stockCount = hideStockTargets("raven_replace")
    if not stockOK then
      ravenIntent = nil
      log("RAVEN_ACTION", "refused=stock_target_query_failed")
      return
    end

    suppressLegacyRavenHud()
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(ravenCandidate, ravenClass)
    end)
    log("RAVEN_SHOW",
      "ok=" .. tostring(showOK) ..
      " error=" .. tostring(showErr) ..
      " replacedStockCount=" .. tostring(stockCount))

    if not showOK then
      ravenIntent = nil
      return
    end

    ravenIntent = "tracked"
    self.currShownMarkerID = info.Id
    _G.CompletionistMapV103NativeRavenTracked = true
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    refreshRavenPrompt(self)
  end

  function MapOn:Update(...)
    local result = previousUpdate(self, ...)

    local shown, ravenOK, ravenErr = ravenShown()
    if ravenOK then
      _G.CompletionistMapV103NativeRavenTracked = shown
      if shown then suppressLegacyRavenHud() end

      if stockReplacePending then
        if not shown then
          stockReplacePending = false
          ravenIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("STOCK_REPLACE_SETTLED", "ravenActive=false")
          refreshRavenPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if retryFrames == 1 or bucket ~= retryBucket then
            retryBucket = bucket
            hideRaven("stock_replace_async_retry")
          end
        end
      elseif ravenIntent == "untracked" then
        if not shown then
          ravenIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("RAVEN_REMOVE_SETTLED", "ravenActive=false")
          refreshRavenPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if retryFrames == 1 or bucket ~= retryBucket then
            retryBucket = bucket
            hideRaven("raven_remove_async_retry")
          end
        end
      elseif ravenIntent == "tracked" then
        local others, stockOK = stockTargets()
        if shown and stockOK and #others == 0 then
          ravenIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("RAVEN_SHOW_SETTLED", "ravenActive=true stockTargets=0")
          refreshRavenPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if stockOK and #others > 0 and (retryFrames == 1 or bucket ~= retryBucket) then
            retryBucket = bucket
            hideStockTargets("raven_replace_async_retry")
          end
        end
      end
    elseif stockReplacePending or ravenIntent ~= nil then
      retryFrames = retryFrames + 1
      if retryFrames == 1 or retryFrames % 60 == 0 then
        log("VERIFY", "ravenQueryOK=false error=" .. tostring(ravenErr) .. " frame=" .. tostring(retryFrames))
      end
    end

    return result
  end

  _G.CompletionistMapV104SingleActiveCompass = true
  _G.CompletionistMapV104SingleActivePromptLiveSync = true
  _G.CompletionistMapV104RavenActionsUseCustomClassManager = true
  log("API",
    "installed=true ravenClass=" .. ravenClass ..
    " invariant=single_active_compass_target raven_actions=custom_class_manager prompt=live_manager")
end
-- END COMPLETIONIST V0.10.4 SINGLE ACTIVE COMPASS CONTROL
'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args()

    source = args.input.read_bytes()
    source_sha = sha256(source)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"mapmenu.lua is not the proven custom-class baseline: {source_sha}")

    text = source.decode("utf-8")
    if BEGIN in text or END in text:
        raise ValueError("single-active compass control is already present")
    required = (
        "Completionist_V103_Veithurgard_Raven_01",
        "CompletionistRaven",
        "game.Compass.ShowMarker",
        "game.Compass.HideMarker",
        "GetShowOnCompassPrompt",
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise ValueError(f"expected custom Raven bridge tokens missing: {missing}")

    separator = "" if text.endswith("\n") else "\n"
    candidate_text = text + separator + LUA
    candidate = candidate_text.encode("utf-8")

    if not candidate.startswith(source):
        raise AssertionError("candidate no longer preserves source bytes as prefix")
    if candidate_text.count(BEGIN) != 1 or candidate_text.count(END) != 1:
        raise AssertionError("single-active block markers are not unique")

    required_patch_tokens = (
        "FindMarkersByIconClass({ravenClass})",
        "game.Compass.ShowMarker(ravenCandidate, ravenClass)",
        "game.Compass.HideMarker(ravenCandidate)",
        "function MapOn:GetShowOnCompassPrompt(currMenu)",
        "if shown then",
        "hideStockTargets(\"raven_replace\")",
        "RAVEN_REMOVE_SETTLED",
        "RAVEN_SHOW_SETTLED",
        "return previousShow(self, currState)",
    )
    missing_patch = [needle for needle in required_patch_tokens if needle not in LUA]
    if missing_patch:
        raise AssertionError(f"required v3 control token missing: {missing_patch}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)

    report = {
        "schema": 3,
        "result": "OFFLINE_RAVEN_SINGLE_ACTIVE_COMPASS_CONTROL_BUILT",
        "source_sha256": source_sha,
        "candidate_sha256": sha256(candidate),
        "source_bytes": len(source),
        "candidate_bytes": len(candidate),
        "changes": {
            "append_only": True,
            "source_prefix_byte_identical": True,
            "raven_origin_actions_use_custom_class_manager": True,
            "raven_remove_is_direct_HideMarker": True,
            "raven_add_is_direct_ShowMarker_custom_class": True,
            "stock_origin_action_hides_raven_before_delegate": True,
            "async_hide_watchdog": True,
            "prompt_always_live_for_raven": True,
            "manager_query_class": "CompletionistRaven",
            "tracked_marker": "Completionist_V103_Veithurgard_Raven_01",
        },
        "expected_runtime_invariant": {
            "stock_to_raven": "Raven only",
            "raven_to_stock": "stock only",
            "raven_remove": "none",
            "maximum_active_user_target": 1,
            "prompt_when_raven_active": "Remove from Compass",
            "prompt_when_stock_active": "Replace in Compass",
            "prompt_when_none_active": "Add to Compass",
        },
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.input.read_bytes() != source:
        raise AssertionError("source mapmenu.lua changed during offline build")

    print(report["result"])
    print(f"  source SHA256:    {source_sha}")
    print(f"  candidate SHA256: {report['candidate_sha256']}")
    print("  append-only: true")
    print("  Raven add/remove uses CompletionistRaven manager query: true")
    print("  stock <-> Raven single-target replacement: true")
    print("  Raven prompt derives from live manager state: true")
    print("  game files written: false")
    print(f"  candidate: {args.output}")
    print(f"  report:    {args.report}")


if __name__ == "__main__":
    main()
