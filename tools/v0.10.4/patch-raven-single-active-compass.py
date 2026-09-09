#!/usr/bin/env python3
"""Build an offline mapmenu.lua candidate that restores stock single-active compass semantics.

The currently proven Raven bridge correctly replaces a stock compass marker when the
Raven is selected, but the reverse direction is incomplete: selecting a stock marker
can leave CompletionistRaven active as a second target. This patch wraps the already
installed custom-class bridge and explicitly retires the Raven before delegating a
non-Raven tracking action to the game's existing MapOn.ShowOnCompass implementation.

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
do
  local prefix = "[CompletionistMap v0.10.4-single-active] "
  local ravenCandidate = "Completionist_V103_Veithurgard_Raven_01"
  local ravenClass = "CompletionistRaven"
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update

  local stockReplacePending = false
  local retryFrames = 0
  local retryBucket = -1

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function ravenSelected(self)
    return self ~= nil and self.completionistMapV100Selected == true
  end

  local function ravenShown()
    local infoOK, info = pcall(function()
      return game.Map.GetMarkerInfo(ravenCandidate)
    end)
    if not infoOK or info == nil then
      return false, false, "candidate_lookup_failed"
    end

    local candidateId = tostring(info.Id)
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

  function MapOn:ShowOnCompass(currState)
    -- The existing Raven bridge already owns Raven -> stock replacement and
    -- Raven add/remove semantics. Do not interfere with Raven-origin actions.
    if ravenSelected(self) then
      stockReplacePending = false
      retryFrames = 0
      retryBucket = -1
      return previousShow(self, currState)
    end

    local shown, queryOK, queryErr = ravenShown()
    local trackedHint = _G.CompletionistMapV103NativeRavenTracked == true

    if shown or trackedHint then
      stockReplacePending = true
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
          log("STOCK_REPLACE_SETTLED", "ravenActive=false")
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
          -- The global tracked hint was set by the proven Raven bridge, so a
          -- failed class query must not silently permit a permanent duplicate.
          hideRaven("stock_replace_query_retry")
        end
      end
    end

    return result
  end

  _G.CompletionistMapV104SingleActiveCompass = true
  log("API",
    "installed=true ravenClass=" .. ravenClass ..
    " invariant=single_active_compass_target")
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
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise ValueError(f"expected custom Raven bridge tokens missing: {missing}")

    separator = "" if text.endswith("\n") else "\n"
    candidate_text = text + separator + LUA
    candidate = candidate_text.encode("utf-8")

    # Contract checks: this patch is append-only and does not rewrite the
    # already-proven mapmenu baseline.
    if not candidate.startswith(source):
        raise AssertionError("candidate no longer preserves source bytes as prefix")
    if candidate_text.count(BEGIN) != 1 or candidate_text.count(END) != 1:
        raise AssertionError("single-active block markers are not unique")
    if "return previousShow(self, currState)" not in LUA:
        raise AssertionError("stock MapOn.ShowOnCompass delegation missing")
    if "game.Compass.HideMarker(ravenCandidate)" not in LUA:
        raise AssertionError("explicit Raven retirement missing")
    if "FindMarkersByIconClass({ravenClass})" not in LUA:
        raise AssertionError("custom-class manager verification missing")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)

    report = {
        "schema": 1,
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
            "manager_query_class": "CompletionistRaven",
            "tracked_marker": "Completionist_V103_Veithurgard_Raven_01",
        },
        "expected_runtime_invariant": {
            "stock_to_raven": "Raven only",
            "raven_to_stock": "stock only",
            "raven_remove": "none",
            "maximum_active_user_target": 1,
        },
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Re-read source to prove the builder itself stayed read-only.
    if args.input.read_bytes() != source:
        raise AssertionError("source mapmenu.lua changed during offline build")

    print(report["result"])
    print(f"  source SHA256:    {source_sha}")
    print(f"  candidate SHA256: {report['candidate_sha256']}")
    print("  append-only: true")
    print("  game files written: false")
    print(f"  candidate: {args.output}")
    print(f"  report:    {args.report}")


if __name__ == "__main__":
    main()
