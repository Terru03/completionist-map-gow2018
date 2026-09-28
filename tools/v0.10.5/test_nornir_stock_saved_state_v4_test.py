"""Check restored rune flags survive the late Raven map boundary."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_saved_v4_builder_test", HERE / "build-nornir-stock-saved-state-v4-test.py")
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class RestoredSealsTest(unittest.TestCase):
    def test_build_is_lua51_and_keeps_raven_prefix(self):
        outputs, report = builder.build()
        self.assertTrue(report["raven_prefix_byte_identical"])
        self.assertTrue(report["stock_resources_byte_identical"])
        for name in (builder.MAP, builder.RUNIC):
            self.assertEqual(outputs[name], (builder.OUT / name).read_bytes())
            lua = LuaRuntime(unpack_returned_tuples=True)
            lua.globals().source = outputs[name].decode("utf-8-sig")
            lua.execute("assert(loadstring(source))")

    def test_snapshot_survives_boundary_and_tracks_new_save(self):
        source = builder.TEMPLATE.read_text(encoding="utf-8")
        source = source.replace("-- @@NORNIR_ROWS@@", """
          {Name='chest',Family='nornir_chest',CatalogueId='parent',
           Realm='Midgard',IdString='1',Class='SIDE',UidHex='1',EventKey='xpl|r1|r2|r3'},
          {Name='seal1',Family='nornir_seal',CatalogueId='one',ParentId='parent',
           Reference='r1',Realm='Midgard',IdString='2',Class='Valkyrie',UidHex='2'},
          {Name='seal2',Family='nornir_seal',CatalogueId='two',ParentId='parent',
           Reference='r2',Realm='Midgard',IdString='3',Class='Valkyrie',UidHex='3'},
          {Name='seal3',Family='nornir_seal',CatalogueId='three',ParentId='parent',
           Reference='r3',Realm='Midgard',IdString='4',Class='Valkyrie',UidHex='4'},
        """)
        source = source.replace("-- @@NORNIR_LOADED_PATHS@@", "")
        source = source.replace("-- @@NORNIR_SAVED_READER@@",
                                builder.v3.READER.read_text(encoding="utf-8"))
        source = source.replace("@@NORNIR_SAVE_CONTRACT@@", "a" * 64)
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = source
        lua.globals().events = builder.EVENTS.read_text(encoding="utf-8")
        lua.execute("""
          icons={}; hook=nil; flags={true,false,false}
          package.preload['core.thunk']=function()
            return {Install=function(_,fn) hook=fn end}
          end
          MapOn={Update=function() end,UpdateFilterButtonMapping=function() end}
          Map={
            FindRegionFromMarker=function() return true,{} end,
            CreateMarkerIcon=function(id)
              local icon={id=id,Show=function() end}
              icons[id]=icon
              return icon
            end,
            RecycleIcon=function(icon) icons[icon.id]=nil end,
          }
          local ids={chest=1,seal1=2,seal2=3,seal3=4}
          game={FindLevel=function() return nil end,
            Map={GetMarkerInfo=function(name) return {Id=ids[name]} end},
            Compass={HideMarker=function() end}}
          CompletionistMapV100_CreateMapPin=function() end
          assert(loadstring(source))()
          CompletionistMapV105Nornir.liveReader:SetReady(false)
          thisLevel={Name='xpl'}
          thisObj={}
          CompletionistNornirObserveSeals=function()
            return {
              {reference='r1',broken=flags[1]},
              {reference='r2',broken=flags[2]},
              {reference='r3',broken=flags[3]},
            }
          end
          engine={GetUIWad=function() return {} end,
            SendHook=function(_,_,payload) hook(payload) end}
          OnStart=function() end
          OnKeyBroken=function() end
          assert(loadstring(events))()
          OnStart()
          assert(CompletionistMapV105Nornir:BeginEpoch(2))
          local map={currRealmName='Midgard',filterButtonMapping={1},filterIndex=1}
          CompletionistMapV100_CreateMapPin(map)
          hook('NORNIR_V1\\tattempt\\txpl|r1|r2|r3\\t')
          assert(icons[1] and not icons[2] and icons[3] and icons[4])
          flags[2]=true
          OnKeyBroken(2)
          assert(not icons[2] and not icons[3] and icons[4])
          flags={false,false,false}
          OnStart()
          assert(CompletionistMapV105Nornir:BeginEpoch(3))
          hook('NORNIR_V1\\tattempt\\txpl|r1|r2|r3\\t')
          assert(icons[2] and icons[3] and icons[4])
          hook('NORNIR_V1\\tsnapshot\\txpl|r1|r2|r3\\tbad')
          assert(icons[2] and icons[3] and icons[4])
        """)


if __name__ == "__main__":
    unittest.main()
