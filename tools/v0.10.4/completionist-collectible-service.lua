-- Offline framework module. Do not install without own runtime proof.
local Service = {}
Service.__index = Service

local function need(value, name)
  if value == nil then error("missing " .. name) end
  return value
end

function Service.New(drivers)
  local self = setmetatable({}, Service)
  self.drivers = drivers or {}
  self.definitions = {}
  self.adapters = {}
  self.instances = {}
  self.children = {}
  self.activeTarget = nil
  return self
end

function Service:RegisterCollectible(definition, adapter)
  need(definition, "definition")
  local key = need(definition.key, "definition.key")
  if self.definitions[key] ~= nil then error("duplicate collectible: " .. key) end
  need(adapter, "adapter")
  need(adapter.IsComplete, "adapter.IsComplete")
  self.definitions[key] = definition
  self.adapters[key] = adapter
  self.instances[key] = {}
  local parent = definition.parentCollectibleKey
  if parent ~= nil then
    self.children[parent] = self.children[parent] or {}
    table.insert(self.children[parent], key)
  end
  return key
end

function Service:_State(key, instance)
  local all = need(self.instances[key], "registered collectible")
  local id = instance or "default"
  if all[id] == nil then
    all[id] = {remaining = true, completed = false, suppressed = false}
  end
  return all[id], id
end

function Service:GetState(key, instance)
  return self:_State(key, instance)
end

function Service:PublishState(key, instance, observed)
  local state, id = self:_State(key, instance)
  state.observed = observed
  state.completed = self.adapters[key]:IsComplete(observed) == true
  state.remaining = not state.completed
  if state.completed then self:Complete(key, id) end
  return state
end

function Service:_Call(driverName, methodName, ...)
  local driver = self.drivers[driverName]
  if driver == nil then return false, "driver unresolved" end
  local method = driver[methodName]
  if method == nil then return false, "driver method unresolved" end
  return method(driver, ...)
end

function Service:ShowMapMarker(key, instance)
  local state, id = self:_State(key, instance)
  if state.completed or state.suppressed then return false, "not remaining" end
  return self:_Call("map", "Show", key, id, self.definitions[key])
end

function Service:HideMapMarker(key, instance)
  local _, id = self:_State(key, instance)
  return self:_Call("map", "Hide", key, id, self.definitions[key])
end

function Service:SetActiveTarget(key, instance)
  local state, id = self:_State(key, instance)
  if state.completed or state.suppressed then return false, "not remaining" end
  if self.activeTarget ~= nil then
    local old = self.activeTarget
    self:_Call("compass", "Remove", old.key, old.instance, self.definitions[old.key])
  end
  local ok, err = self:_Call("compass", "Add", key, id, self.definitions[key])
  if ok then self.activeTarget = {key = key, instance = id} end
  return ok, err
end

function Service:AddCompassTarget(key, instance)
  if self.activeTarget ~= nil then return false, "target already active" end
  return self:SetActiveTarget(key, instance)
end

function Service:ReplaceCompassTarget(key, instance)
  return self:SetActiveTarget(key, instance)
end

function Service:RemoveCompassTarget(key, instance)
  local _, id = self:_State(key, instance)
  local ok, err = self:_Call("compass", "Remove", key, id, self.definitions[key])
  if self.activeTarget ~= nil and self.activeTarget.key == key and self.activeTarget.instance == id then
    self.activeTarget = nil
  end
  return ok, err
end

function Service:CreateInWorldMarker(key, instance)
  local state, id = self:_State(key, instance)
  if state.completed or state.suppressed then return false, "not remaining" end
  return self:_Call("inWorld", "Create", key, id, self.definitions[key])
end

function Service:RemoveInWorldMarker(key, instance)
  local _, id = self:_State(key, instance)
  return self:_Call("inWorld", "Remove", key, id, self.definitions[key])
end

function Service:_SuppressChildren(parentKey, instance)
  for _, childKey in ipairs(self.children[parentKey] or {}) do
    local child = self:_State(childKey, instance)
    child.suppressed = true
    self:HideMapMarker(childKey, instance)
    self:RemoveCompassTarget(childKey, instance)
    self:RemoveInWorldMarker(childKey, instance)
  end
end

function Service:Complete(key, instance)
  local state, id = self:_State(key, instance)
  state.completed = true
  state.remaining = false
  self:HideMapMarker(key, id)
  self:RemoveCompassTarget(key, id)
  self:RemoveInWorldMarker(key, id)
  self:_SuppressChildren(key, id)
  return state
end

return Service

