#!/usr/bin/env python3
"""Generate bounded native catalogue and accepted offline fixture headers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def c_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def normal_wad(value: str) -> str:
    return Path(value).stem.lower() + ".wad"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--catalogue-output", type=Path, required=True)
    parser.add_argument("--fixture-output", type=Path, required=True)
    args = parser.parse_args()

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))["ravens"]
    replay = json.loads(args.replay.read_text(encoding="utf-8"))
    states = {row["catalogue_id"]: row for row in replay["raven_states"]}
    if len(catalogue) != 53 or len(states) != 53:
        raise SystemExit("expected 53 catalogue and replay rows")
    pairs = {
        (int(row["registry_hash_hex"], 16), int(row["object_hash_hex"], 16))
        for row in catalogue
    }
    ids = {row["catalogue_id"] for row in catalogue}
    if len(pairs) != 53 or len(ids) != 53 or set(states) != ids:
        raise SystemExit("Raven identities are not one-to-one")
    if any(row["candidate_ravenKilled"] is None for row in states.values()):
        raise SystemExit("accepted replay contains unknown Raven state")

    catalogue_lines = [
        "#pragma once",
        "",
        "#include <array>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        "namespace completionist {",
        "struct RavenIdentity {",
        "  std::string_view catalogue_id;",
        "  std::string_view wad;",
        "  std::uint64_t registry_hash;",
        "  std::uint64_t object_hash;",
        "  bool fixture_killed;",
        "};",
        "inline constexpr std::array<RavenIdentity, 53> kRavenCatalogue{{",
    ]
    for row in catalogue:
        state = bool(states[row["catalogue_id"]]["candidate_ravenKilled"])
        catalogue_lines.append(
            "  RavenIdentity{%s, %s, UINT64_C(0x%016X), UINT64_C(0x%016X), %s},"
            % (
                c_string(row["catalogue_id"]),
                c_string(normal_wad(row["wad"])),
                int(row["registry_hash_hex"], 16),
                int(row["object_hash_hex"], 16),
                "true" if state else "false",
            )
        )
    catalogue_lines += ["}};", "}  // namespace completionist", ""]

    fixture_records = [row for row in replay["records"] if row.get("payload_file")]
    fixture_lines = [
        "#pragma once",
        "",
        "#include <array>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        "namespace completionist {",
        "struct FixtureRecord {",
        "  std::string_view relative_path;",
        "  std::string_view name;",
        "  std::uint32_t expected_lua_length;",
        "};",
        f"inline constexpr std::array<FixtureRecord, {len(fixture_records)}> kFixtureRecords{{{{",
    ]
    for row in fixture_records:
        fixture_lines.append(
            "  FixtureRecord{%s, %s, UINT32_C(%d)},"
            % (
                c_string(row["payload_file"]),
                c_string(row.get("name") or ""),
                int(row["cached_channel_a_lua_length"]),
            )
        )
    fixture_lines += ["}};", "}  // namespace completionist", ""]

    args.catalogue_output.write_text("\n".join(catalogue_lines), encoding="utf-8")
    args.fixture_output.write_text("\n".join(fixture_lines), encoding="utf-8")
    print(f"RAVEN_BRIDGE_DATA_GENERATED catalogue={len(catalogue)} fixtures={len(fixture_records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
