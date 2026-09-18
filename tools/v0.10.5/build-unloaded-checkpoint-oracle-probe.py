"""Fill exact Raven catalogue rows into the read-only Lua oracle probe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


PLACEHOLDER = "-- @@RAVEN_ORACLE_ROWS@@"
NATIVE_MODULE_PLACEHOLDER = "@@OBJECT_TOKEN_READER_PATH@@"


def lua_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(template: str, catalogue: dict, native_module: str | None = None) -> str:
    rows = catalogue["ravens"]
    identities: set[tuple[str, str]] = set()
    runtime_identities: dict[tuple[str, str], str] = {}
    rendered = []
    for row in rows:
        wad = row["source"]["wad"].lower()
        object_name = row["native"]["object_name"].lower()
        identity = (wad, object_name)
        if identity in identities:
            raise ValueError(f"duplicate exact WAD/object identity: {identity!r}")
        identities.add(identity)
        runtime_names = [object_name]
        if object_name.startswith("go"):
            runtime_names.append(object_name[2:])
        for runtime_name in runtime_names:
            runtime_identity = (wad, runtime_name)
            previous = runtime_identities.get(runtime_identity)
            if previous is not None and previous != row["catalogue_id"]:
                raise ValueError(
                    "duplicate runtime WAD/object identity: "
                    f"{runtime_identity!r} maps to {previous!r} and {row['catalogue_id']!r}"
                )
            runtime_identities[runtime_identity] = row["catalogue_id"]
        x, y, z = row["source"]["native_world_position"]
        rendered.append(
            "    { CatalogueId = %s, Wad = %s, ObjectName = %s, ParentQuest = %s, X = %.15g, Y = %.15g, Z = %.15g },"
            % (
                lua_quote(row["catalogue_id"]),
                lua_quote(wad),
                lua_quote(object_name),
                lua_quote(row["progression"]["parent_quest"]),
                x, y, z,
            )
        )
    if len(rows) != 53:
        raise ValueError(f"expected 53 Raven rows, found {len(rows)}")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError("probe template placeholder missing or duplicated")
    if template.count(NATIVE_MODULE_PLACEHOLDER) != 1:
        raise ValueError("native module placeholder missing or duplicated")
    native_value = "nil" if native_module is None else lua_quote(native_module)
    return template.replace(PLACEHOLDER, "\n".join(rendered)).replace(
        NATIVE_MODULE_PLACEHOLDER, native_value
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-module", type=Path)
    args = parser.parse_args()
    output = build(
        args.template.read_text(encoding="utf-8"),
        json.loads(args.catalogue.read_text(encoding="utf-8")),
        str(args.native_module.resolve()) if args.native_module is not None else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8", newline="\n")
    print("UNLOADED_CHECKPOINT_ORACLE_PROBE_BUILT rows=53")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
