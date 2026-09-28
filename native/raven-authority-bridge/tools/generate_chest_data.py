"""Build exact Legendary identities and separate archived replay expectations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STATES = {
    None: "Unknown", "010000803f": "Enabled", "0100000040": "Disabled",
    "0100004040": "Locked", "0100008040": "Opened",
}


def render(data: dict) -> str:
    if (data.get("schema"), data.get("family"), data.get("state_field"),
            data.get("missing_state"), data.get("opened_value")) != (
            1, "legendary_chest", "state", "unknown", 4):
        raise ValueError("Unknown chest authority contract")
    rows = data["rows"]
    if len(rows) != 33:
        raise ValueError("Need exact current 33 candidate identities")
    ids, keys = set(), set()
    lines = ['#pragma once', '#include <array>', '#include "chest_authority.h"',
             'namespace completionist {',
             'inline constexpr std::array<ChestIdentity, 33> kLegendaryCatalogue{{']
    states = []
    for row in rows:
        cid, wad = row["catalogue_id"], row["wad"]
        registry, obj = int(row["registry_hash"], 16), int(row["object_hash"], 16)
        if cid in ids or (registry, obj) in keys:
            raise ValueError("Duplicate chest identity")
        if not cid.startswith("legendary_chest_") or not wad.endswith(".wad"):
            raise ValueError("Unexpected chest identity")
        payload = b'\x01' + registry.to_bytes(8, "little") + obj.to_bytes(8, "little")
        if payload.hex() != row["serialized_key"]:
            raise ValueError("Serialized chest identity differs")
        raw = row["fixture_raw"]
        if raw not in STATES or row["fixture_observed"] is not (raw is not None):
            raise ValueError("Archived scalar evidence differs")
        ids.add(cid)
        keys.add((registry, obj))
        lines.append('  ChestIdentity{%s, %s, UINT64_C(0x%016X), UINT64_C(0x%016X)},'
                     % (json.dumps(cid), json.dumps(wad), registry, obj))
        states.append('ChestState::' + STATES[raw])
    lines += ['}};', 'inline constexpr std::array<ChestState, 33> kLegendaryFixtureStates{{',
              '  ' + ',\n  '.join(states), '}};', '}  // namespace completionist', '']
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalogue', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    content = render(json.loads(args.catalogue.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding='utf-8')
    print('LEGENDARY_DATA_GENERATED identities=33 missing_state=unknown')


if __name__ == '__main__':
    main()
