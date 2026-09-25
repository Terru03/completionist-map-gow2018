"""Add an explicit UI ownership handoff to a candidate copy of the Raven layer."""
ANCHOR=b'  _G.CompletionistMapV105PublishRavenState = function('
BOUNDARY_ANCHOR=b'  _G.CompletionistMapV105NotifyAuthorityBoundary = beginAuthorityBoundary'
BOUNDARY=b'''  -- Notify Nornir through the existing boundary; keep one load-hook chain.
  local ravenBoundary = beginAuthorityBoundary
  beginAuthorityBoundary = function(...)
    local source, captureReady = ...
    local controller = rawget(_G, "CompletionistMapV105Nornir")
    if controller then
      controller:BeginEpoch((controller.service.epoch or 0) + 1)
      if controller.liveReader then controller.liveReader:SetReady(captureReady ~= false) end
    end
    return ravenBoundary(...)
  end

'''
HANDOFF=b'''  -- Nornir candidate: release Raven UI ownership without changing authority.
  _G.CompletionistMapV105ReleaseRavenCompass = function()
    local ok = hideCustom(nil, "nornir_target_replace")
    if not ok then return false end
    customCompassOwnsTarget = false
    promptIntent = nil
    promptSettleFrames = 0
    promptSettleBucket = -1
    _G.CompletionistMapV105TrackedCatalogueId = nil
    if lastMapOnSelf then
      clearSelection(lastMapOnSelf, "nornir_target_replace")
      lastMapOnSelf.currShownMarkerID = nil
    end
    suppressLegacyRavenHud()
    return true
  end

'''


def inject(source):
    if source.count(ANCHOR)!=1 or source.count(BOUNDARY_ANCHOR)!=1 or b'CompletionistMapV105ReleaseRavenCompass' in source:
        raise ValueError('Raven handoff anchor differs or already present')
    result=source.replace(ANCHOR,HANDOFF+ANCHOR,1)
    result=result.replace(BOUNDARY_ANCHOR,BOUNDARY+BOUNDARY_ANCHOR,1)
    if result.replace(HANDOFF,b'',1).replace(BOUNDARY,b'',1)!=source:
        raise ValueError('Raven source changed outside handoff')
    return result
