"""Check map-open checkpoint read and safe fallback paths."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_saved_v2_builder_test", HERE / "build-nornir-stock-saved-state-v2-test.py")
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class MapOpenSavedStateTest(unittest.TestCase):
    def test_only_map_layer_changes_and_compiles(self):
        raw, report = builder.build()
        self.assertTrue(report["raven_prefix_byte_identical"])
        self.assertTrue(report["stock_resources_byte_identical"])
        self.assertEqual(report["changed_file"], builder.MAP)
        self.assertEqual(raw, (builder.OUT / builder.MAP).read_bytes())
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = raw.decode("utf-8-sig")
        lua.execute("assert(loadstring(source))")

    def test_map_open_accepts_exact_reply_and_refuses_bad_reply(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = builder.READER.read_text(encoding="utf-8")
        lua.execute("""
          local Saved = assert(loadstring(source))()
          local contract = string.rep('a',64)
          local reply = 'NORNIR_SNAPSHOT_V1 nonce=1 restoreEpoch=1 contract='..
            contract..' states=40'
          local clock = 10
          local client = {
            settimeout=function() return true end,
            connect=function() return true end,
            send=function(_,message) return #message end,
            receive=function() return reply end,
            close=function() return true end,
          }
          local transport = {now=function() return clock end,
                             create=function() return client end}
          local rows = {{family='nornir_chest',id='a'},
                        {family='nornir_chest',id='b'}}
          local saved = Saved.New(rows,contract,transport,function() return 1 end)
          saved:Reset(1)
          local ok,status = saved:ReadOnce(1)
          assert(ok and string.find(status,'accepted:',1,true)==1)
          assert(saved:Current(1).states.a==4 and saved:Current(1).states.b==0)
          clock=13
          assert(saved:Current(1)==nil)
          reply='NORNIR_SNAPSHOT_V1 UNAVAILABLE'
          saved:Reset(2)
          ok,status=saved:ReadOnce(2)
          assert(not ok and status=='native_unavailable' and saved:Current(2)==nil)
        """)

    def test_map_create_applies_opened_chest_before_pin_draw(self):
        template = builder.TEMPLATE.read_text(encoding="utf-8")
        reader = builder.READER.read_text(encoding="utf-8")
        source = template.replace("-- @@NORNIR_ROWS@@", """{
          Name='test_chest', Family='nornir_chest', CatalogueId='chest_a',
          Realm='Midgard', IdString='1', Class='SIDE', UidHex='1',
        },""")
        source = source.replace("-- @@NORNIR_SAVED_READER@@", reader)
        source = source.replace("@@NORNIR_SAVE_CONTRACT@@", "a" * 64)
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = source
        lua.execute("""
          created=0
          clock=10
          reply='NORNIR_SNAPSHOT_V1 nonce=1 restoreEpoch=1 contract='..
            string.rep('a',64)..' states=4'
          local client={
            settimeout=function() return true end,
            connect=function() return true end,
            send=function(_,message) return #message end,
            receive=function() return reply end,
            close=function() return true end,
          }
          package.preload['socket.core']=function()
            return {gettime=function() return clock end,
                    tcp=function() return client end}
          end
          CompletionistMapV105LastNativeRestoreEpoch=1
          MapOn={Update=function() end, UpdateFilterButtonMapping=function() end}
          Map={
            FindRegionFromMarker=function() return true, {} end,
            CreateMarkerIcon=function()
              created=created+1
              return {Show=function() end}
            end,
          }
          game={Map={GetMarkerInfo=function() return {Id=1} end},
                Compass={HideMarker=function() end}}
          CompletionistMapV100_CreateMapPin=function() end
          assert(loadstring(source))()
          local map={currRealmName='Midgard',filterButtonMapping={1},filterIndex=1}
          CompletionistMapV100_CreateMapPin(map)
          assert(created==0)
          assert(map.completionistMapV105NornirIdTestIcons.test_chest==nil)
        """)


if __name__ == "__main__":
    unittest.main()
