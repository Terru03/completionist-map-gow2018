-- Pure state adapters. Hook discovery stays outside this file.
local Adapters = {}

local function adapter(name, predicate)
  return {
    name = name,
    IsComplete = function(_, observed)
      if type(observed) ~= "table" then return false end
      return predicate(observed) == true
    end
  }
end

function Adapters.KillableCollectible()
  return adapter("killable_collectible", function(state)
    return state.completed == true
  end)
end

function Adapters.OpenedChest()
  return adapter("opened_chest", function(state)
    return state.opened == true or state.state == "OPENED"
  end)
end

function Adapters.PickupCollectible()
  return adapter("pickup_collectible", function(state)
    return state.pickedUp == true
  end)
end

function Adapters.InteractReadCollectible()
  return adapter("interact_read_collectible", function(state)
    return state.read == true
  end)
end

function Adapters.ParentPuzzleCollectible()
  return adapter("parent_puzzle_collectible", function(state)
    return state.rewardOpened == true or state.opened == true
  end)
end

function Adapters.ChildPuzzleElement()
  return adapter("child_puzzle_element", function(state)
    return state.childComplete == true
  end)
end

return Adapters
