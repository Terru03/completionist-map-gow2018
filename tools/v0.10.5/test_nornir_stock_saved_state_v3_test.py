"""Check broken rune read after load and map pin sync."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_saved_v3_builder_test", HERE / "build-nornir-stock-saved-state-v3-test.py")
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class LoadedSealTest(unittest.TestCase):
    def test_candidate_changes_only_map_and_runic_and_compiles(self):
        outputs, report = builder.build()
        self.assertTrue(report["raven_prefix_byte_identical"])
        self.assertTrue(report["stock_resources_byte_identical"])
        self.assertEqual(report["loaded_parent_paths"], 22)
        for name in (builder.MAP, builder.RUNIC):
            self.assertEqual(outputs[name], (builder.OUT / name).read_bytes())
            lua = LuaRuntime(unpack_returned_tuples=True)
            lua.globals().source = outputs[name].decode("utf-8-sig")
            lua.execute("assert(loadstring(source))")

    def test_runic_reader_needs_three_known_flags_and_matching_count(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = builder.RUNIC_READER.read_text(encoding="utf-8")
        lua.execute("""
          keyType='Breakable'; keysUsed=1
          local flags={false,true,true}
          runeTable={}
          for i=1,3 do
            runeTable[i]={runeVisual={LuaObjectScript={
              IsEnabled=function() return flags[i] end}}}
          end
          thisObj={
            FindLuaTableAttribute=function(_,name)
              return 'RunicLock0'..string.sub(name,-1)
            end,
            FindSingleGOByName=function(_,name)
              return runeTable[tonumber(string.sub(name,-1))].runeVisual
            end,
          }
          assert(loadstring(source))()
          local got=CompletionistNornirObserveSeals()
          assert(#got==3 and got[1].broken==true and got[2].broken==false)
          keysUsed=0
          assert(CompletionistNornirObserveSeals()==nil)
          keysUsed=1; flags[2]=false
          assert(CompletionistNornirObserveSeals()==nil)
        """)

    def test_loaded_broken_seal_stays_hidden_after_boundary_and_attempt(self):
        template = builder.TEMPLATE.read_text(encoding="utf-8")
        reader = builder.READER.read_text(encoding="utf-8")
        source = template.replace("-- @@NORNIR_ROWS@@", """
          {Name='chest',Family='nornir_chest',CatalogueId='parent',
           Realm='Midgard',IdString='1',Class='SIDE',UidHex='1',EventKey='key'},
          {Name='seal1',Family='nornir_seal',CatalogueId='one',ParentId='parent',
           Reference='r1',Realm='Midgard',IdString='2',Class='Valkyrie',UidHex='2'},
          {Name='seal2',Family='nornir_seal',CatalogueId='two',ParentId='parent',
           Reference='r2',Realm='Midgard',IdString='3',Class='Valkyrie',UidHex='3'},
          {Name='seal3',Family='nornir_seal',CatalogueId='three',ParentId='parent',
           Reference='r3',Realm='Midgard',IdString='4',Class='Valkyrie',UidHex='4'},
        """)
        source = source.replace("-- @@NORNIR_LOADED_PATHS@@", """
          parent={Level='xpl',Path={'goplace','goroot'},
                  ScriptPath={'golock','goplace','goroot'}},
        """)
        source = source.replace("-- @@NORNIR_SAVED_READER@@", reader)
        source = source.replace("@@NORNIR_SAVE_CONTRACT@@", "a" * 64)
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = source
        lua.execute("""
          icons={}; hook=nil; broken={true,false,false}
          package.preload['core.thunk']=function()
            return {Install=function(_,fn) hook=fn end}
          end
          local root={GetName=function() return 'goroot' end}
          local place={GetName=function() return 'goplace' end,Parent=root}
          local lock={GetName=function() return 'golock' end,Parent=place,
            LuaObjectScript={CompletionistNornirObserveSeals=function()
              return {
                {reference='r1',broken=broken[1]},
                {reference='r2',broken=broken[2]},
                {reference='r3',broken=broken[3]},
              }
            end}}
          place.FindSingleGOByName=function(_,name)
            if name=='lock' then return lock end
          end
          local level={FindSingleGameObject=function(_,name)
            if name=='place' then return place end
          end}
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
          game={
            FindLevel=function(name) if name=='xpl' then return level end end,
            Map={GetMarkerInfo=function(name) return {Id=ids[name]} end},
            Compass={HideMarker=function() end},
          }
          CompletionistMapV100_CreateMapPin=function() end
          assert(loadstring(source))()
          local controller=CompletionistMapV105Nornir
          controller.liveReader:SetReady(false)
          assert(controller:BeginEpoch(2))
          local map={currRealmName='Midgard',filterButtonMapping={1},filterIndex=1}
          CompletionistMapV100_CreateMapPin(map)
          hook('NORNIR_V1\\tattempt\\tkey\\t')
          assert(icons[1] and not icons[2] and icons[3] and icons[4])
          broken[2]=true
          hook('NORNIR_V1\\tseal\\tkey\\tr2')
          assert(not icons[2] and not icons[3] and icons[4])
          broken[1]=false; broken[2]=false
          assert(controller:BeginEpoch(3))
          hook('NORNIR_V1\\tattempt\\tkey\\t')
          assert(icons[2] and icons[3] and icons[4])
        """)


if __name__ == "__main__":
    unittest.main()
