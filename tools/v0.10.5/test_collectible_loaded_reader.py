"""Exact loaded ownership; ambiguity and save changes stay visible."""
from pathlib import Path
import sys
import unittest
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime

class LoadedReaderTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.State = self.lua.execute((HERE / "collectible-state.lua").read_text())
        g.Runtime = self.lua.execute((HERE / "collectible-state-runtime.lua").read_text())
        g.Loaded = self.lua.execute((HERE / "collectible-loaded-reader.lua").read_text())
        self.lua.execute('''
          store=State.New({"a"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end}); runtime:AuthorityReady(12)
          function node(name,parent)
            local value={Parent=parent, GetName=function() return name end}
            function value:FindGOsByName(query) return self.matches or {} end
            function value:FindSingleGOByName(query) return (self.matches or {})[1] end
            return value
          end
          placement=node("place",nil); owner=node("chestscript",placement)
          owner.LuaObjectScript={CompletionistCollectibleObserve=function() return "chest","collected" end}
          placement.matches={owner}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="a",level="level",placement={"goplace"},owner={"gochestscript","goplace"},adapter="chest"}}
          loaded=Loaded.New(rows,runtime)
        ''')
        self.g = g
    def poll(self):
        self.g.loaded.Poll(self.g.loaded)
        return self.g.store.Get(self.g.store,"a")
    def test_exact_owner_collects(self):
        self.assertEqual(self.poll(), "collected")
    def test_duplicate_placement_stays_unknown(self):
        self.lua.execute('level.matches={placement,placement}')
        self.assertEqual(self.poll(), "unknown")
    def test_duplicate_owner_stays_unknown(self):
        self.lua.execute('placement.matches={owner,owner}')
        self.assertEqual(self.poll(), "unknown")
    def test_owner_outside_placement_stays_unknown(self):
        self.lua.execute('owner.Parent=node("place",nil)')
        self.assertEqual(self.poll(), "unknown")
    def test_ambiguous_catalogue_sources_stay_unknown(self):
        self.lua.execute('rows[2]=rows[1]')
        self.assertEqual(self.poll(), "unknown")
    def test_epoch_change_during_read_cannot_apply(self):
        self.lua.execute('''owner.LuaObjectScript.CompletionistCollectibleObserve=function()
          runtime:BeginEpoch(2); runtime:AuthorityReady(13); return "chest","collected" end''')
        self.assertEqual(self.poll(), "unknown")
    def test_deep_chest_prefab_hierarchy_with_is_open(self):
        self.lua.execute('''
          root=node("goplace",nil)
          placement=node("gochest_common_tier3_peak740_2",root)
          common_parent=node("gochest_common_parent",placement)
          script_root=node("gochestscript_root",common_parent)
          script_node=node("gochestscript",script_root)
          script_node.LuaObjectScript={IsOpen=function() return true end, GetState=function() return 4 end}
          placement.matches={common_parent}
          common_parent.matches={script_node}
          level.matches={placement}
          rows[1]={id="a",level="level",
                   placement={"gochest_common_tier3_peak740_2","goplace"},
                   owner={"gochest_common_parent","gochest_common_tier3_peak740_2","goplace"},
                   extra="gochestscript",adapter="chest"}
        ''')
        self.assertEqual(self.poll(), "collected")
    def test_unopened_chest_with_is_open_returns_remaining(self):
        self.lua.execute('''
          root=node("goplace",nil)
          placement=node("gochest_common_tier3_peak740_2",root)
          common_parent=node("gochest_common_parent",placement)
          script_root=node("gochestscript_root",common_parent)
          script_node=node("gochestscript",script_root)
          script_node.LuaObjectScript={IsOpen=function() return false end, GetState=function() return 1 end}
          placement.matches={common_parent}
          common_parent.matches={script_node}
          level.matches={placement}
          rows[1]={id="a",level="level",
                   placement={"gochest_common_tier3_peak740_2","goplace"},
                   owner={"gochest_common_parent","gochest_common_tier3_peak740_2","goplace"},
                   extra="gochestscript",adapter="chest"}
        ''')
        self.assertEqual(self.poll(), "remaining")

    def test_level_name_with_wad_prefix(self):
        self.lua.execute('''
          game={FindLevel=function(name)
            if name == "WAD_level" then return level end
            return nil
          end}
        ''')
        self.assertEqual(self.poll(), "collected")
    def test_non_ref_node_child_stepping(self):
        self.lua.execute('''
          child_node=node("child",owner)
          child_node.Parent=owner
          owner.Child=child_node
          owner.IsRefNode=false
          owner.LuaObjectScript=nil
          child_node.LuaObjectScript={IsOpen=function() return true end}
        ''')
        self.assertEqual(self.poll(), "collected")

    def test_poll_collects_without_authority_ready(self):
        self.lua.execute('''
          store=State.New({"b"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          -- Note: runtime:AuthorityReady is NOT called!
          placement=node("place",nil); owner=node("chestscript",placement)
          owner.LuaObjectScript={IsOpen=function() return true end, GetState=function() return 4 end}
          placement.matches={owner}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="b",level="level",placement={"goplace"},owner={"gochestscript","goplace"},adapter="chest"}}
          loaded=Loaded.New(rows,runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("b")'), "collected")

    def test_runtime_poll_dispatches_loaded_poll_without_authority_ready(self):
        self.lua.execute('''
          store=State.New({"c"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end, Poll=function() return nil end, Advance=function() end})
          -- Note: runtime:AuthorityReady is NOT called!
          placement=node("place",nil); owner=node("chestscript",placement)
          owner.LuaObjectScript={IsOpen=function() return true end, GetState=function() return 4 end}
          placement.matches={owner}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="c",level="level",placement={"goplace"},owner={"gochestscript","goplace"},adapter="chest"}}
          loaded=Loaded.New(rows,runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('runtime:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("c")'), "collected")

    def test_collapsed_intermediate_hierarchy_matches_placement(self):
        self.lua.execute('''
          store=State.New({"d"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          -- Hierarchy has placement with Parent = nil (flattened scene node)
          -- but row.placement expects 4 intermediate parent nodes
          placement=node("gochest_common_tier3_xpl980_1", nil)
          script_node=node("gochestscript", placement)
          script_node.LuaObjectScript={IsOpen=function() return true end, GetState=function() return 4 end}
          placement.matches={script_node}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="d",level="level",
                 placement={"gochest_common_tier3_xpl980_1", "go____loot", "goxpl980_ents_nooffset", "goxpl980_ents"},
                 owner={"gochest_common_parent", "gochest_common_tier3_xpl980_1", "go____loot", "goxpl980_ents_nooffset", "goxpl980_ents"},
                 adapter="chest"}}
          loaded=Loaded.New(rows,runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("d")'), "collected")

    def test_rift_observe_collected_via_has_opened(self):
        self.lua.execute('''
          store=State.New({"rift_col"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          root=node("goroot", nil)
          placement=node("gomisc_legendary_tier4_nid400_1", root)
          owner=node("golootpocketgeo", placement)
          script_node=node("gopocketrift_interact_loot", placement)
          script_node.LuaObjectScript={hasOpened=true}
          placement.matches={owner, script_node}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="rift_col", level="nid400_center",
                 placement={"gomisc_legendary_tier4_nid400_1", "goroot"},
                 owner={"golootpocketgeo", "gomisc_legendary_tier4_nid400_1", "goroot"},
                 adapter="rift"}}
          loaded=Loaded.New(rows, runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("rift_col")'), "collected")

    def test_rift_observe_remaining_when_unopened(self):
        self.lua.execute('''
          store=State.New({"rift_rem"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          root=node("goroot", nil)
          placement=node("gomisc_legendary_tier4_nid400_1", root)
          owner=node("golootpocketgeo", placement)
          script_node=node("gopocketrift_interact_loot", placement)
          script_node.LuaObjectScript={hasOpened=false}
          placement.matches={owner, script_node}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="rift_rem", level="nid400_center",
                 placement={"gomisc_legendary_tier4_nid400_1", "goroot"},
                 owner={"golootpocketgeo", "gomisc_legendary_tier4_nid400_1", "goroot"},
                 adapter="rift"}}
          loaded=Loaded.New(rows, runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("rift_rem")'), "remaining")

    def test_rift_observe_probe_function(self):
        self.lua.execute('''
          store=State.New({"rift_probe"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          root=node("goroot", nil)
          placement=node("golootpocketrift920", root)
          owner=node("golootpocketgeo", placement)
          script_node=node("gopocketrift_interact_loot", placement)
          script_node.LuaObjectScript={
            CompletionistCollectibleObserve=function() return "rift", "collected" end
          }
          placement.matches={owner, script_node}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="rift_probe", level="xpl920",
                 placement={"golootpocketrift920", "goroot"},
                 owner={"golootpocketgeo", "golootpocketrift920", "goroot"},
                 adapter="rift"}}
          loaded=Loaded.New(rows, runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("rift_probe")'), "collected")

    def test_rift_script_on_placement_directly(self):
        self.lua.execute('''
          store=State.New({"rift_direct"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          root=node("goroot", nil)
          placement=node("gomisc_legendary_tier4_nid400_1", root)
          owner=node("golootpocketgeo", placement)
          placement.LuaObjectScript={hasOpened=true}
          placement.matches={owner}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="rift_direct", level="nid400_center",
                 placement={"gomisc_legendary_tier4_nid400_1", "goroot"},
                 owner={"golootpocketgeo", "gomisc_legendary_tier4_nid400_1", "goroot"},
                 adapter="rift"}}
          loaded=Loaded.New(rows, runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("rift_direct")'), "collected")

    def test_artefact_observe_collected_via_get_state(self):
        self.lua.execute('''
          store=State.New({"art_col"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          root=node("goroot", nil)
          placement=node("goartifactalfheim06", root)
          owner=node("goartifactscript", placement)
          owner.LuaObjectScript={GetState=function() return 3 end}
          placement.matches={owner}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="art_col", level="alf325",
                 placement={"goartifactalfheim06", "goroot"},
                 owner={"goartifactscript", "goartifactalfheim06", "goroot"},
                 adapter="artefact"}}
          loaded=Loaded.New(rows, runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("art_col")'), "collected")

    def test_artefact_observe_collected_via_is_acquired(self):
        self.lua.execute('''
          store=State.New({"art_acq"}); store:BeginEpoch(1)
          runtime=Runtime.New(store,{Reset=function() end})
          root=node("goroot", nil)
          placement=node("goartifactalfheim06", root)
          owner=node("goartifactscript", placement)
          owner.LuaObjectScript={IsAcquired=function() return true end}
          placement.matches={owner}
          level={matches={placement}}
          function level:FindGameObjects(query) return self.matches end
          function level:FindSingleGameObject(query) return self.matches[1] end
          game={FindLevel=function() return level end}
          rows={{id="art_acq", level="alf325",
                 placement={"goartifactalfheim06", "goroot"},
                 owner={"goartifactscript", "goartifactalfheim06", "goroot"},
                 adapter="artefact"}}
          loaded=Loaded.New(rows, runtime)
          runtime.loaded = loaded
        ''')
        self.lua.execute('loaded:Poll()')
        self.assertEqual(self.lua.execute('return store:Get("art_acq")'), "collected")

if __name__ == "__main__": unittest.main()


