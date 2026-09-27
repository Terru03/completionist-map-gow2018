"""Reject stale/invalid transport data before any state mutation."""
from pathlib import Path
import sys
import struct
import unittest
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime, LuaError
from lupa.lua52 import LuaRuntime as Lua52Runtime


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        module = self.lua.execute((HERE / "collectible-state-reader.lua").read_text())
        self.lua.execute('restore=12; function expected() return restore end')
        self.reader = module.New(self.lua.table('a', 'b'), 'a' * 64, self.lua.globals().expected)
        self.reader.Reset(self.reader, 1)
        self.reader.nonce = 7
        self.reader.requestRestore = 12
        self.line = 'COLLECTIBLE_SNAPSHOT_V1 nonce=7 restoreEpoch=12 contract=' + 'a' * 64 + ' generation=3 states=21'

    def test_duplicate_contract_ids_rejected_before_parse(self):
        module = self.lua.execute((HERE / "collectible-state-reader.lua").read_text())
        with self.assertRaisesRegex(LuaError, "duplicate"):
            module.New(self.lua.table('a','a'), 'a'*64, self.lua.globals().expected)

    def test_valid_normalized_states(self):
        got = self.reader.Parse(self.reader, self.line)
        self.assertEqual(got.states['a'], 'collected')
        self.assertEqual(got.states['b'], 'remaining')
        self.assertEqual(got.epoch, 1)

    def test_invalid_envelopes_rejected(self):
        for bad in [self.line.replace('nonce=7', 'nonce=8'),
                    self.line.replace('restoreEpoch=12', 'restoreEpoch=11'),
                    self.line.replace('contract=a', 'contract=b'),
                    self.line.replace('states=21', 'states=4'),
                    self.line.replace('states=21', 'states=211'),
                    self.line + ' states=21', self.line[:-1],
                    self.line.replace('generation=3', 'generation=9007199254740992'),
                    'a' * 4097]:
            with self.subTest(bad=bad[:80]):
                self.assertIsNone(self.reader.Parse(self.reader, bad))

    def test_old_generation_and_changed_restore_rejected(self):
        self.reader.generation = 3
        self.assertIsNone(self.reader.Parse(self.reader, self.line))
        self.reader.generation = 0
        self.lua.globals().restore = 13
        self.assertIsNone(self.reader.Parse(self.reader, self.line))

    def test_partial_receive_timeout_and_reset_close_socket(self):
        self.lua.execute('''
          now, closed, creates, sent, response = 0, 0, 0, nil, ''
          socket = {settimeout=function() return true end, connect=function() return true end,
            send=function(self, value) sent=value; return #value end,
            close=function() closed=closed+1 end,
            receive=function()
              if #response==0 then return nil,'timeout' end
              local value=response:sub(1,1); response=response:sub(2); return value
            end}
          transport={now=function() return now end, create=function() creates=creates+1; return socket end}
        ''')
        g = self.lua.globals()
        self.reader.transport = g.transport
        self.reader.nonce = 6
        self.reader.Poll(self.reader, 1)
        self.assertEqual(g.creates, 1)
        g.response = self.line[:25]
        self.assertIsNone(self.reader.Poll(self.reader, 1))
        g.response = self.line[25:] + '\n'
        got = self.reader.Poll(self.reader, 1)
        self.assertEqual(got.states['a'], 'collected')
        self.assertEqual(g.closed, 1)
        self.assertEqual(self.reader.generation, 3)
        g.now = 2
        self.reader.Poll(self.reader, 1)
        self.reader.Reset(self.reader, 2)
        self.assertEqual(g.closed, 2)
        self.assertEqual(self.reader.generation, 0)
        self.reader.Poll(self.reader, 2)
        g.now = 6
        self.assertIsNone(self.reader.Poll(self.reader, 2))
        self.assertEqual(g.closed, 3)

    def test_full_410_state_response_uses_elapsed_time_with_float32_wall_clock(self):
        f32 = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]
        wall = f32(1790488800)
        self.assertEqual(f32(wall + 2), wall, 'reproduce GoW clock precision loss')
        for runtime in (LuaRuntime, Lua52Runtime):
            with self.subTest(runtime=runtime):
                lua = runtime(unpack_returned_tuples=True)
                lua.execute('''
                  response,creates,clockReads='',0,0
                  package.preload['socket.core']=function()
                    return {gettime=function() clockReads=clockReads+1; error('wall clock used') end,
                      tcp=function()
                        creates=creates+1
                        return {settimeout=function() return 1 end,connect=function() return 1 end,
                          close=function() end,send=function(self,value) sent=value; return #value end,
                          receive=function()
                            if #response==0 then return nil,'timeout' end
                            local value=response:sub(1,1);response=response:sub(2);return value
                          end}
                      end}
                  end
                  function expected() return 12 end
                ''')
                module=lua.execute((HERE/'collectible-state-reader.lua').read_text())
                ids=lua.table_from(['id'+str(i) for i in range(410)])
                reader=module.New(ids,'a'*64,lua.globals().expected)
                reader.Poll(reader,1)
                lua.globals().response=('COLLECTIBLE_SNAPSHOT_V1 nonce=1 restoreEpoch=12 contract='+
                    'a'*64+' generation=3 states=2'+'0'*409+'\n')
                reader.Advance(reader,0.1)
                self.assertIsNone(reader.Poll(reader,1), 'first tick reads at most 512 bytes')
                reader.Advance(reader,0.1)
                got=reader.Poll(reader,1)
                self.assertEqual(got.states['id0'],'collected')
                self.assertEqual(got.states['id409'],'unknown')
                reader.Advance(reader,1)
                reader.Poll(reader,1)
                self.assertEqual(lua.globals().creates,1)
                reader.Advance(reader,1.1)
                reader.Poll(reader,1)
                self.assertEqual(lua.globals().creates,2)
                self.assertEqual(lua.globals().clockReads,0)


if __name__ == '__main__':
    unittest.main()
