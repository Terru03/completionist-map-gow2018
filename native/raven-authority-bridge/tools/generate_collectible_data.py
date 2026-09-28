"""Emit the exact ordered UI contract and verified checkpoint identities."""
import argparse
import json
import hashlib
from pathlib import Path


def render(data):
    rows = data["bindings"]
    if len(rows) != 410 or len({r["catalogue_id"] for r in rows}) != 410:
        raise ValueError("Expected 410 unique location identities")
    if rows != sorted(rows, key=lambda r: r["catalogue_id"]):
        raise ValueError("Location identities are not in contract order")
    if any(r["status"] not in {"proved", "unproved"} for r in rows):
        raise ValueError("Invalid proof status")
    contract_rows = [{k: r.get(k) for k in
        ("catalogue_id", "source_wad", "instance_keys", "predicate", "native_identity")} for r in rows]
    contract = hashlib.sha256(json.dumps(contract_rows, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    if contract != data["contract"]:
        raise ValueError("Ordered contract differs")
    active = [(i, r) for i, r in enumerate(rows) if r["status"] == "proved"]
    lines = ['#pragma once', '#include <array>', '#include "chest_authority.h"',
             'namespace completionist {',
             f'inline constexpr std::size_t kCollectibleCount = {len(rows)};',
             f'inline constexpr char kCollectibleContract[] = {json.dumps(data["contract"])};']
    identities = set()
    supported = {
        "legendary_chest": 4,
        "coffin": 4,
        "wooden_chest": 4,
        "cipher_chest": 4,
        "artefact": 3,
    }
    for _, row in active:
        terminal = supported.get(row["family"])
        if terminal is None or row["predicate"] != {"field": "state", "type": "number", "equals": terminal}:
            raise ValueError("Unsupported persisted predicate")
        native = row["native_identity"]
        registry, obj = int(native["registry_hash"], 16), int(native["object_hash"], 16)
        if native["serialized_key"] != (b'\x01' + registry.to_bytes(8, 'little') + obj.to_bytes(8, 'little')).hex():
            raise ValueError("Serialized identity differs")
        identity = (row["source_wad"].lower(), registry, obj)
        if identity in identities:
            raise ValueError("Duplicate native identity")
        identities.add(identity)
    chest_families = {"legendary_chest", "coffin", "wooden_chest", "cipher_chest"}
    selected_chests = [(i, r) for i, r in active if r["family"] in chest_families]
    selected_artefacts = [(i, r) for i, r in active if r["family"] == "artefact"]
    for selected, label in ((selected_chests, "Chest"), (selected_artefacts, "Artefact")):
        if not selected:
            raise ValueError("Missing required saved items for " + label)
        lines.append(f'inline constexpr std::array<NumericStateIdentity, {len(selected)}> kCollectible{label}s{{{{')
        for _, row in selected:
            native = row["native_identity"]
            lines.append('  NumericStateIdentity{%s, %s, UINT64_C(0x%016X), UINT64_C(0x%016X)},' %
                         (json.dumps(row["catalogue_id"]), json.dumps(row["source_wad"]),
                          int(native["registry_hash"], 16), int(native["object_hash"], 16)))
        lines += ['}};', f'inline constexpr std::array<std::size_t, {len(selected)}> kCollectible{label}Indices{{{{',
                  ', '.join(str(i) for i, _ in selected), '}};']
        if label == "Artefact":
            fixture_states = [row["evidence"].get("fixture_state") for _, row in selected]
            if any(type(state) is not int or state not in (1, 2, 3) for state in fixture_states):
                raise ValueError("Artefact fixture state missing or invalid")
            lines += [f'inline constexpr std::array<std::uint8_t, {len(selected)}> kCollectibleArtefactFixtureStates{{{{',
                      ', '.join(str(state) for state in fixture_states), '}};']
    lines.append('}')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(json.loads(args.bindings.read_text())), encoding='utf-8')
