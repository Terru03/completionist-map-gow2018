"""Unit tests for isDirectlyCollected in collectible-location-map.lua across all supported families."""
from pathlib import Path
import unittest
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT.parent / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime

class DirectlyCollectedTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        # Load collectible-location-map.lua into lua environment
        script = (HERE / "collectible-location-map.lua").read_text(encoding="utf-8")
        # Extract the relevant tables and function
        # Find where digQuests starts and isDirectlyCollected ends
        start_idx = script.index("local digQuests = {")
        end_idx = script.index("local function syncDirectObservations")
        sub_script = script[start_idx:end_idx]

        self.lua.execute('''
          game = {
            Wallets = {
              resources = {},
              HasResource = function(wallet, res)
                return (game.Wallets.resources[res] or 0) > 0
              end,
              GetResourceValue = function(wallet, res)
                return game.Wallets.resources[res] or 0
              end
            },
            QuestManager = {
              quests = {},
              GetQuestState = function(q)
                return game.QuestManager.quests[q] or "Inactive"
              end
            }
          }
        ''' + sub_script + '''
          function testDirectlyCollected(row)
            return isDirectlyCollected(row)
          end
        ''')

    def test_artefact_uncollected(self):
        row = self.lua.table_from({
            "CatalogueId": "artefact_707ae0e24dc7bc9a56c19eb7ce17b351",
            "Family": "artefact"
        })
        self.assertFalse(self.lua.globals().testDirectlyCollected(row))

    def test_artefact_collected_via_wallet(self):
        self.lua.execute('game.Wallets.resources["AlfheimSHook"] = 1')
        row = self.lua.table_from({
            "CatalogueId": "artefact_707ae0e24dc7bc9a56c19eb7ce17b351",
            "Family": "artefact"
        })
        self.assertTrue(self.lua.globals().testDirectlyCollected(row))

    def test_artefact_shared_resource_threshold(self):
        row = self.lua.table_from({
            "CatalogueId": "artefact_xpl200funeralwad2768cb29f445634bb075f7a858cabcc3",
            "Family": "artefact"
        })
        # HornUShape requires 4
        self.lua.execute('game.Wallets.resources["HornUShape"] = 2')
        self.assertFalse(self.lua.globals().testDirectlyCollected(row))
        self.lua.execute('game.Wallets.resources["HornUShape"] = 4')
        self.assertTrue(self.lua.globals().testDirectlyCollected(row))

    def test_artefact_collected_via_quest(self):
        row = self.lua.table_from({
            "CatalogueId": "artefact_eb672a1647b1f7e64595e48f821670f5", # BroochRay
            "Family": "artefact"
        })
        self.lua.execute('game.QuestManager.quests["Quest_Artifacts_Brooches"] = "Complete"')
        self.assertTrue(self.lua.globals().testDirectlyCollected(row))

    def test_realm_tear_collected_via_quest(self):
        row = self.lua.table_from({
            "CatalogueId": "realm_tear_885f79d8699b58e655739f1b924bf442",
            "Family": "realm_tear"
        })
        self.assertFalse(self.lua.globals().testDirectlyCollected(row))
        self.lua.execute('game.QuestManager.quests["RegionSummary_ALF_PocketRift_Parent"] = "Complete"')
        self.assertTrue(self.lua.globals().testDirectlyCollected(row))

    def test_niflheim_realm_tear_via_trophy_resource(self):
        row = self.lua.table_from({
            "CatalogueId": "realm_tear_10374be1dacc7b5afc9b38ff1c50b3f5",
            "Family": "realm_tear"
        })
        self.assertFalse(self.lua.globals().testDirectlyCollected(row))
        self.lua.execute('game.Wallets.resources["NiflheimTrophyTracker"] = 1')
        self.assertTrue(self.lua.globals().testDirectlyCollected(row))

    def test_jotnar_shrine_collected_via_wallet(self):
        row = self.lua.table_from({
            "CatalogueId": "jotnar_shrine_4f54c8b2f4d927800573fde8aece376f",
            "Family": "jotnar_shrine"
        })
        self.assertFalse(self.lua.globals().testDirectlyCollected(row))
        self.lua.execute('game.Wallets.resources["Tryptich_Skadi"] = 1')
        self.assertTrue(self.lua.globals().testDirectlyCollected(row))

    def test_treasure_dig_collected_via_quest(self):
        row = self.lua.table_from({
            "CatalogueId": "treasure_dig_5f6d01b68cdf70a9815dc6fa7c3a839f",
            "Family": "treasure_dig"
        })
        self.assertFalse(self.lua.globals().testDirectlyCollected(row))
        self.lua.execute('game.QuestManager.quests["Quest_TreasureMap_BlackBreath"] = "Complete"')
        self.assertTrue(self.lua.globals().testDirectlyCollected(row))

if __name__ == "__main__":
    unittest.main()
