#!/usr/bin/env python3
"""Build an offline mapmenu.lua candidate that restores stock single-active compass semantics.

The proven Raven bridge already replaces a stock compass marker when the Raven is
selected. This wrapper fixes the reverse direction and also fixes the Raven map
prompt after a stock-origin replacement. The replacement logic remains manager-owned;
this layer only retires CompletionistRaven before delegating a stock action and, after
that external replacement, derives Raven prompt text from live manager state instead
of the inner bridge's stale asynchronous prompt intent.

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
-- Enforce the stock one-target invariant in the reverse direction too:
-- when a normal game marker is chosen while CompletionistRaven is tracked,
-- hide the Raven first, then let the already-installed stock/custom bridge
-- perform the requested stock action. A small Update watchdog retries the
-- asynchronous HideMarker request until the custom class is gone.
--
-- The inner Raven bridge keeps a private asynchronous promptIntent. A stock
-- marker can hide CompletionistRaven without clearing that private value, so
-- the Raven card can incorrectly keep saying Remove from Compass. After an
-- external stock replacement, this wrapper temporarily derives the Raven
-- prompt from live manager state until the next Raven-origin action.
do
  local prefix = "[CompletionistMap v0.10.4-single-active] "
  local ravenCandidate = "Completionist_V103_Veithurgard_Raven_01"
  local ravenClass = "CompletionistRaven"
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousPrompt = MapOn.GetShowOnCompassPrompt

  local stockReplacePending = false
  local retryFrames = 0
  local retryBucket = -1
  local forceLiveRavenPrompt = false

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function ravenSelected(self)
    return self ~= nil and self.completionistMapV100Selected == true
  end

  local function candidateIdString()
    local infoOK, info = pcall(function()
      return game.Map.GetMarkerInfo(ravenCandidate)
    end)
    if not infoOK or info == nil then
      return nil
    end
    return tostring(info.Id)
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

  function MapOn:GetShowOnCompassPrompt(currMenu)
    local show, text = previousPrompt(self, currMenu)
    if not ravenSelected(self) or not show or not forceLiveRavenPrompt then
      return show, text
    end

    local shown, ravenQueryOK, ravenQueryErr = ravenShown()
    if not ravenQueryOK then
      log("PROMPT_LIVE_QUERY",
        "ravenQueryOK=false error=" .. tostring(ravenQueryErr) ..
        " fallback=previous")
      return show, text
    end

    if shown then
      return true, actionText(lamsConsts.RemoveFromCompass)
    end

    local others, stockQueryOK, stockQueryErr = stockTargets()
    if not stockQueryOK then
      log("PROMPT_LIVE_QUERY",
        "stockQueryOK=false error=" .. tostring(stockQueryErr) ..
        " fallback=previous")
      return show, text
    end

    if #others > 0 then
      return true, actionText(lamsConsts.ReplaceInCompass)
    end
    return true, actionText(lamsConsts.AddToCompass)
  end

  function MapOn:ShowOnCompass(currState)
    -- A Raven-origin action returns prompt ownership to the proven inner bridge.
    -- Its own promptIntent is correct for add/remove/replace actions it initiates.
    if ravenSelected(self) then
      forceLiveRavenPrompt = false
      stockReplacePending = false
      retryFrames = 0
      retryBucket = -1
      return previousShow(self, currState)
    end

    local shown, queryOK, queryErr = ravenShown()
    local trackedHint = _G.CompletionistMapV103NativeRavenTracked == true

    if shown or trackedHint then
      stockReplacePending = true
      forceLiveRavenPrompt = true
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

    -- Preserve the game's own action. This may queue ShowMarker/HideMarker for
    -- the selected stock target in the same frame; the watchdog below only
    -- concerns itself with ensuring CompletionistRaven actually leaves.
    return previousShow(self, currState)
  end

  function MapOn:Update(...)
    local result = previousUpdate(self, ...)

    if stockReplacePending then
      local shown, queryOK, queryErr = ravenShown()
      if queryOK then
        if not shown then
          stockReplacePending = false
          retryFrames = 0
          retryBucket = -1
          _G.CompletionistMapV103NativeRavenTracked = false
          forceLiveRavenPrompt = true
          log("STOCK_REPLACE_SETTLED",
            "ravenActive=false promptSource=live_manager")
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if retryFrames == 1 or bucket ~= retryBucket then
            retryBucket = bucket
            hideRaven("stock_replace_async_retry")
          end
        end
      else
        retryFrames = retryFrames + 1
        if retryFrames == 1 or retryFrames % 60 == 0 then
          log("STOCK_REPLACE_VERIFY",
            "queryOK=false error=" .. tostring(queryErr) ..
            " frame=" .. tostring(retryFrames))
          hideRaven("stock_replace_query_retry")
        end
      end
    end

    return result
  end

  _G.CompletionistMapV104SingleActiveCompass = true
  _G.CompletionistMapV104SingleActivePromptLiveSync = true
  log("API",
    "installed=true ravenClass=" .. ravenClass ..
    " invariant=single_active_compass_target prompt_live_sync=true")
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
        raise ValueError(
            f"mapmenu.lua is not the proven custom-class baseline: {source_sha}"
        )

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
        "return previousShow(self, currState)",
        "game.Compass.HideMarker(ravenCandidate)",
        "FindMarkersByIconClass({ravenClass})",
        "local previousPrompt = MapOn.GetShowOnCompassPrompt",
        "function MapOn:GetShowOnCompassPrompt(currMenu)",
        "lamsConsts.ReplaceInCompass",
        "forceLiveRavenPrompt = true",
    )
    missing_patch = [needle for needle in required_patch_tokens if needle not in LUA]
    if missing_patch:
        raise AssertionError(f"required v2 control token missing: {missing_patch}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)

    report = {
        "schema": 2,
        "result": "OFFLINE_RAVEN_SINGLE_ACTIVE_COMPASS_CONTROL_BUILT",
        "source_sha256": source_sha,
        "candidate_sha256": sha256(candidate),
        "source_bytes": len(source),
        "candidate_bytes": len(candidate),
        "changes": {
            "append_only": True,
            "source_prefix_byte_identical": True,
            "raven_origin_actions_delegated_unchanged": True,
            "stock_origin_action_hides_raven_before_delegate": True,
            "async_hide_watchdog": True,
            "stock_replacement_prompt_forces_live_manager_state": True,
            "prompt_override_only_active_after_external_stock_replacement": True,
            "manager_query_class": "CompletionistRaven",
            "tracked_marker": "Completionist_V103_Veithurgard_Raven_01",
        },
        "expected_runtime_invariant": {
            "stock_to_raven": "Raven only",
            "raven_to_stock": "stock only",
            "raven_remove": "none",
            "maximum_active_user_target": 1,
            "prompt_after_raven_replaced_by_stock": "Replace in Compass",
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
    print("  single-active reverse replacement: true")
    print("  stale Raven prompt live-sync fix: true")
    print("  game files written: false")
    print(f"  candidate: {args.output}")
    print(f"  report:    {args.report}")


if __name__ == "__main__":
    main()
