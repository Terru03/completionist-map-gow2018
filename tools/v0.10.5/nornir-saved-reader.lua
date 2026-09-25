-- Fresh native checkpoint reads. Socket polling never waits for capture work.
local Saved={}
Saved.__index=Saved
function Saved.New(rows,contract,transport,expectedRestoreEpoch)
 local self=setmetatable({parents={},contract=contract,nonce=0,nextRead=0,
  expectedRestoreEpoch=expectedRestoreEpoch},Saved)
 for _,row in ipairs(rows) do if row.family=='nornir_chest' then self.parents[#self.parents+1]=row end end
 table.sort(self.parents,function(a,b) return a.id<b.id end)
 if not transport then
  local ok,socket=pcall(require,'socket.core')
  if ok and type(socket)=='table' and type(socket.gettime)=='function' and type(socket.tcp)=='function' then
   transport={now=socket.gettime,create=socket.tcp}
  end
 end
 self.transport=transport
 return self
end
function Saved:Reset(epoch)
 if self.client then pcall(function() self.client:close() end) end
 self.epoch=epoch; self.client=nil; self.snapshot=nil; self.buffer=''; self.nextRead=0
end
function Saved:Current(epoch)
 if not self.snapshot or self.snapshot.epoch~=epoch or not self.snapshotTime or not self.transport then return nil end
 local age=self.transport.now()-self.snapshotTime
 if age<0 or age>2.5 then return nil end
 if self.expectedRestoreEpoch and tonumber(self.snapshot.restoreEpoch)~=self.expectedRestoreEpoch() then return nil end
 return self.snapshot
end
function Saved:Parse(line)
 local nonce,restore,contract,states=string.match(line,
  '^NORNIR_SNAPSHOT_V1 nonce=(%d+) restoreEpoch=(%d+) contract=(%x+) states=([0-4]+)$')
 if nonce~=tostring(self.nonce) or contract~=self.contract or #states~=#self.parents then return nil end
 if self.expectedRestoreEpoch then
  local expected=self.expectedRestoreEpoch()
  if type(expected)~='number' or expected<0 or expected~=math.floor(expected) or
   tonumber(restore)~=expected then return nil end
 end
 local result={epoch=self.epoch,states={},restoreEpoch=restore}
 for i,row in ipairs(self.parents) do result.states[row.id]=tonumber(string.sub(states,i,i)) end
 return result
end
function Saved:Poll(epoch)
 if epoch~=self.epoch then self:Reset(epoch) end
 if not self.transport or not epoch then return false end
 local now=self.transport.now()
 local expired=self.snapshot~=nil and self:Current(epoch)==nil
 if expired then self.snapshot=nil end
 if self.client then
  local finished=false
  for _=1,256 do
   local ok,value,err=pcall(function() return self.client:receive(1) end)
   if ok and value=='\n' then
    self.snapshot=self:Parse(self.buffer); self.snapshotTime=now; finished=true; break
   elseif ok and value and #value==1 then
    self.buffer=self.buffer..value
    if #self.buffer>256 then self.snapshot=nil; finished=true; break end
   elseif not ok or err~='timeout' then self.snapshot=nil; finished=true; break
   else break end
  end
  if now>=self.deadline then self.snapshot=nil; finished=true end
  if finished then
   pcall(function() self.client:close() end); self.client=nil; self.nextRead=now+2
   return true
  end
  return expired
 end
 if now<self.nextRead then return expired end
 self.nextRead=now+2
 local ok,client=pcall(self.transport.create)
 if not ok or not client then local had=self.snapshot~=nil; self.snapshot=nil; return had or expired end
 self.nonce=self.nonce+1
 local request='CAPTURE NORNIR_SNAPSHOT_V1 nonce='..tostring(self.nonce)..'\n'
 local connected=pcall(function()
  assert(client:settimeout(0.005)); assert(client:connect('127.0.0.1',43753))
  assert(client:send(request)==#request); assert(client:settimeout(0))
 end)
 if not connected then
  pcall(function() client:close() end)
  local had=self.snapshot~=nil; self.snapshot=nil; return had or expired
 end
 self.client=client; self.buffer=''; self.deadline=now+3
 return expired
end
return Saved
