Completionist Map v0.10.2
MATERIAL / TEXPACK DISCOVERY

Purpose
-------
v0.10.1 proved that loose PNG setters are not available on the synthetic map
marker GameObjects. v0.10.2 moves to the game's authored material / texpack
pipeline.

The native Kratos/Omega player marker is not part of this replacement work and
must remain native.

Current step: container inventory
---------------------------------
From the repository root:

  git pull --ff-only origin feat/v0.10.2-material-icons

  powershell -ExecutionPolicy Bypass `
      -File ".\tools\v0.10.2\inventory-ui-containers.ps1"

The inventory script is read-only with respect to the game. It records likely
UI/map WAD and texpack filenames, saves the report under archive/field-logs,
commits it, and pushes the current branch automatically.

Expected report:

  archive\field-logs\completionist-v102-container-inventory.txt

Next step after the report
--------------------------
Select the most likely map/UI texpack(s), extract them using the God of War
2018 PC release of GOWTool, and locate the DockPoint map texture hash.

GOWTool PC notes
----------------
The God of War 2018 PC release v0.1.3-alpha supports DDS/GNF texture export and
import/packing into .texpack files.

A temporary replacement of the native DockPoint texture is acceptable only as
a diagnostic proof that our custom Raven image can reach the map renderer.
It is NOT acceptable as the final implementation because stock docks must
retain their native artwork.

Final material isolation must use a synthetic-only material/material-swap route
before the custom family art is enabled globally.
