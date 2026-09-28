"""Read-only probes appended to exact stock scripts; source remains intact."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
STOCK = ROOT.parent / "completionist-map-gow2018/dist/gowlua-src"
PREFIX = "gameart/scripts/levels/gameplaymodules/"
SCRIPTS = {
    "chest": ("progression/interact_chest_standard.lua", "state", 4,
              ("OnOpened", "OnStart", "OnRestoreCheckpoint")),
    "artefact": ("progression/interact_loot_artifact.lua", "state", 3,
                 ("LuaHook_GiveLoot", "OnStart", "OnRestoreCheckpoint")),
    "lore": ("soninteracts/langcheckruneread.lua", "mapSummaryComplete", True,
             ("UpdateJournal", "OnStart", "OnRestoreCheckpoint")),
    "pickup": ("soninteracts/sonlanguagepickup.lua", "collected", True,
               ("InteractComplete", "OnStart", "OnRestoreCheckpoint")),
    "dig": ("progression/interact_loot_dirtdig.lua", "state", 3,
            ("UpdateQuest", "OnStart", "OnRestoreCheckpoint")),
    "rift": ("progression/interact_loot_pocketrift.lua", "hasOpened", True,
             ("OnInteractFinish", "OnStart", "OnRestoreCheckpoint")),
    "shrine": ("interactive/triptychs/interact_triptych.lua", "triptychCompleted", True,
               ("UpdateJournal", "OnStart", "OnRestoreCheckpoint")),
}
ADAPTERS = {"legendary_chest": "chest", "wooden_chest": "chest", "coffin": "chest",
            "cipher_chest": "chest", "artefact": "artefact", "lore_marker": "lore",
            "treasure_map": "pickup", "lore_scroll": "pickup", "treasure_dig": "dig",
            "realm_tear": "rift", "jotnar_shrine": "shrine"}


def render_probe(adapter):
    _, field, terminal, callbacks = SCRIPTS[adapter]
    if type(terminal) is bool:
        predicate = f'if type({field}) ~= "boolean" then return nil end\n    local collected = {field}'
    else:
        predicate = f'if type({field}) ~= "number" or {field} < 1 or {field} > {terminal} or {field} ~= math.floor({field}) then return nil end\n    local collected = {field} == {terminal}'
    if adapter == "shrine":
        # Stock sets triptychCompleted when interaction STARTS. Its journal
        # resource is awarded only on completed reading and checked by QuestFixUp.
        predicate += '\n    if collected then\n      if type(journalUpdateID) ~= "string" or journalUpdateID == "" then return nil end\n      collected = game.Wallets.HasResource("HERO", journalUpdateID) == true\n    end'
    if adapter == "dig":
        # ACQUIRED is assigned on start; the exact dig quest completes on reward.
        predicate += '\n    if collected then\n      if type(questName) ~= "string" or questName == "" then return nil end\n      collected = game.QuestManager.GetQuestState(questName) == "Complete"\n    end'
    return '''
-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function CompletionistCollectibleObserve()
    %s
    return %s, collected and "collected" or "remaining"
  end
  local function notify()
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
%s
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION
''' % (predicate, json.dumps(adapter), "\n".join(
        f'  if type({name}) == "function" then {name} = wrap({name}) end'
        for name in callbacks))


def loaded_bindings(rows):
    result = []
    seen = set()
    for row in rows:
        adapter = ADAPTERS[row["family"]]
        for source in row.get("sources", [row.get("source")]):
            if not source:
                continue
            chain = source["transform_chain"]
            native = row.get("native", {})
            placement_id = row.get("placement", {}).get("record_id") or native.get("placement_final_record_id")
            placement_name = row.get("placement", {}).get("name")
            index = next((i for i, node in enumerate(chain)
                          if node["record_id"] == placement_id and
                          (not placement_name or node["name"] == placement_name)),
                         next((i for i, node in enumerate(chain) if node["record_id"] == placement_id), 0))
            # Deduplicate consecutive identical names
            placement_names = []
            for n in chain[index:]:
                if not placement_names or placement_names[-1] != n["name"]:
                    placement_names.append(n["name"])
            owner_names = []
            for n in chain:
                if not owner_names or owner_names[-1] != n["name"]:
                    owner_names.append(n["name"])
            # Each lookup must stay inside one exact physical placement.
            item = {"id": row["catalogue_id"], "adapter": adapter,
                    "level": Path(source["wad"]).stem.lower(),
                    "placement": placement_names,
                    "owner": owner_names,
                    "extra": "gochestscript" if adapter == "chest" and
                               chain[0]["name"] != "gochestscript" else None}
            key = (item["id"], item["adapter"], item["level"],
                   tuple(item["placement"]), tuple(item["owner"]), item["extra"])
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result

