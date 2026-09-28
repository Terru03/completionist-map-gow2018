# Custom art per collectible type

User asks switch from completion work to custom artwork. One icon per type.
Use supplied PNGs in `C:/Users/david/Documents/GitHub/gow_all_artworks_named`.
User approved three matching additions: wooden chest, coffin, lore scroll.

## Scope and checks

- Keep latest installed completion Lua, native bridge, save readers and filters.
- Give 15 current non-Raven collectible types separate map resources, materials,
  texture IDs and texture content. Keep existing Raven art intact.
- Use supplied buried_treasure.png for treasure_dig. Other supplied stock-type
  PNGs stay available; do not replace unrelated stock or player icons.
- Keep all marker IDs, positions, realms, links and compass behavior.
- Reassign added pool reserve; add no UI physics objects.
- Freeze installed hashes before changes; own rollback restores exact prior bytes.
- Treat material +0x20 isolation as hypothesis until actual renderer checked.

## Work

1. Review latest four artwork files, old collision evidence, supplied PNGs, installed hashes.
2. Save three new matching images; build 148px DDS/texpack/resident data with pinned tools.
3. Build distinct resources for all 15 types, prove no shared texture/material identities,
   prove old WAD exact inverse and only intended map resource/pool changes.
4. Review transaction code; test full install/verify/rollback and failure paths offline.
5. Produce checked package and install while game closed. Live Raven/Nornir comparison
   must pass before claiming rendering collision fixed. If runtime fails, restore exact baseline.

## Current evidence

Seven existing artwork tests pass. They check one-type probe and rollback, not live renderer.
Installed baseline records upgrade-v2 plus newer loaded-reader edits. Do not replace it
with old Legendary-only package. Completion expansion work parked in its own plan workspace.
