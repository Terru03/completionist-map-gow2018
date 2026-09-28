-- Bounded, nonblocking current-save snapshot transport. No game state writes.
local Reader = {}
Reader.__index = Reader
local codes = {['0']='unknown', ['1']='remaining', ['2']='collected'}
local function integer(value)
  local n = tonumber(value)
  if not n or n < 0 or n > 9007199254740991 or n ~= math.floor(n) then return nil end
  return n
end
function Reader.New(ids, contract, expectedRestoreEpoch, transport)
  assert(type(ids) == 'table' and #ids > 0, 'empty contract')
  local seen, ordered = {}, {}
  for i,id in ipairs(ids) do
    assert(type(id) == 'string' and id ~= '', 'invalid contract id')
    assert(not seen[id], 'duplicate contract id')
    seen[id]=true; ordered[i]=id
  end
  ids=ordered
  local self = setmetatable({ids=ids, contract=contract, expectedRestoreEpoch=expectedRestoreEpoch,
    elapsed=0, nonce=0, generation=0, nextRead=0}, Reader)
  if not transport then
    local ok, socket = pcall(require, 'socket.core')
    if ok and type(socket) == 'table' and type(socket.tcp) == 'function' then
      -- GoW uses 32-bit Lua numbers. Absolute Unix timestamps lose short
      -- intervals, so use the UI timer's elapsed deltas for every deadline.
      transport = {now=function() return self.elapsed end, create=socket.tcp}
    end
  end
  self.transport=transport
  return self
end
function Reader:Advance(dt)
  if type(dt) ~= 'number' or dt < 0 or dt ~= dt or dt == math.huge then return false end
  self.elapsed=self.elapsed+dt
  return true
end
function Reader:Close()
  if self.client then pcall(function() self.client:close() end) end
  self.client=nil; self.buffer=''
end
function Reader:Reset(epoch)
  self:Close()
  self.epoch=epoch; self.generation=0; self.nextRead=0
  self.requestRestore=nil
end
function Reader:Parse(line)
  if type(line) ~= 'string' or #line > 4096 then return nil end
  local nonce, restore, contract, generation, states = line:match(
    '^COLLECTIBLE_SNAPSHOT_V1 nonce=(%d+) restoreEpoch=(%d+) contract=(%x+) generation=(%d+) states=([012]+)$')
  if not nonce or nonce ~= tostring(self.nonce) or contract ~= self.contract or
      #states ~= #self.ids then return nil end
  restore, generation = integer(restore), integer(generation)
  local expected = self.expectedRestoreEpoch()
  if restore == nil or generation == nil or type(expected) ~= 'number' or
      restore ~= expected or restore ~= self.requestRestore or
      generation <= self.generation then return nil end
  local result = {epoch=self.epoch, restoreEpoch=restore, generation=generation, states={}}
  for i, id in ipairs(self.ids) do result.states[id] = codes[states:sub(i,i)] end
  return result
end
function Reader:Poll(epoch)
  if epoch ~= self.epoch then self:Reset(epoch) end
  if not self.transport then return nil end
  local expected = self.expectedRestoreEpoch()
  if type(expected) ~= 'number' or integer(expected) == nil then self:Close(); return nil end
  local now = self.transport.now()
  if self.client then
    if expected ~= self.requestRestore or now >= self.deadline then
      self:Close(); self.nextRead=now+2; return nil
    end
    for _=1,512 do
      local ok, value, err = pcall(function() return self.client:receive(1) end)
      if ok and value == '\n' then
        local parsed = self:Parse(self.buffer)
        self:Close(); self.nextRead=now+2
        if parsed then self.generation=parsed.generation end
        return parsed
      elseif ok and value and #value == 1 then
        self.buffer=self.buffer..value
        if #self.buffer > 4096 then self:Close(); self.nextRead=now+2; break end
      elseif not ok or err ~= 'timeout' then self:Close(); self.nextRead=now+2; break
      else break end
    end
    return nil
  end
  if now < self.nextRead then return nil end
  self.nextRead=now+2
  local ok, client = pcall(self.transport.create)
  if not ok or not client then return nil end
  self.nonce=self.nonce+1
  local request='CAPTURE COLLECTIBLE_SNAPSHOT_V1 nonce='..tostring(self.nonce)..'\n'
  local connected=pcall(function()
    assert(client:settimeout(0.005)); assert(client:connect('127.0.0.1',43753))
    assert(client:send(request)==#request); assert(client:settimeout(0))
  end)
  if not connected then pcall(function() client:close() end); return nil end
  self.client=client; self.buffer=''; self.deadline=now+3; self.requestRestore=expected
  return nil
end
return Reader
