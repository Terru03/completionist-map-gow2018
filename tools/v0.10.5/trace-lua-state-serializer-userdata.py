"""Trace the native Lua-state byte serializer and locate userdata/GameObject handling.

Read-only, version-locked static analysis for the supported God of War PC
executable. The checkpoint save driver has been proven to call 0x7E7F10 after
core.pickle.Pickle returns a table; 0x7E7F10 references `tableref_root` and
writes directly into the caller-provided output span.

This tracer maps the local serializer family, captures a two-hop call graph,
highlights Lua type dispatch (including type 7 / userdata), and records any
intersection with the proven GameObject token/resolve/unbox routines.

No game launch and no save I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
SERIALIZER = 0x7E7F10
LOCAL_BEGIN = 0x7E8300
LOCAL_END = 0x7E9000
SEED_HELPERS = {
    "write_graph": 0x7E83D0,
    "build_root_record": 0x7E8540,
    "scan_strings_a": 0x7E8760,
    "scan_strings_b": 0x7E88F0,
    "scan_strings_c": 0x7E8B70,
    "table_ref_context": 0x7E8D90,
}
KNOWN = {
    "lua_type": 0x9E4900,
    "gameobject_token_packer": 0x60B9C0,
    "gameobject_token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
}
INTERESTING = (
    "userdata", "gameobject", "guid", "objectid", "object_id", "objectref",
    "reference", "persistent", "pickle", "unpickle", "serialize", "table",
    "tableref", "root", "wad", "level", "refnode", "subobj",
)


def load_base():
    path = Path(__file__).with_name("trace-checkpoint-pickle-return-serializer.py")
    if not path.is_file():
        raise RuntimeError(f"missing dependency {path}")
    spec = importlib.util.spec_from_file_location("checkpoint_serializer_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load serializer dependency")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def lua_type_contexts(trace):
    out = []
    blob = bytes.fromhex(trace["hex"])
    begin = trace["begin"]
    for e in trace["direct_edges"]:
        if e.get("dest") != KNOWN["lua_type"]:
            continue
        off = e["site"] - begin
        lo = max(0, off - 24)
        hi = min(len(blob), off + 48)
        chunk = blob[lo:hi]
        # Capture nearby simple CMP r32, imm8 encodings. This is evidence only;
        # manual disassembly decides which compare consumes lua_type's result.
        cmps = []
        for i in range(max(0, len(chunk) - 3)):
            if chunk[i] == 0x83 and (chunk[i + 1] & 0x38) == 0x38:
                cmps.append({"offset_from_call": (lo + i) - off, "imm8": chunk[i + 2]})
        out.append({
            "site": e["site"],
            "context_hex": chunk.hex(),
            "nearby_cmp_imm8": cmps,
            "userdata_type7_nearby": any(c["imm8"] == 7 for c in cmps),
        })
    return out


def trace_function(base, pe, entry, strings):
    tr = base.trace_entry(pe, entry, strings)
    tr["lua_type_contexts"] = lua_type_contexts(tr)
    return tr


def add_function(out, base, pe, entry, strings):
    fn = pe.function_for(entry)
    key_entry = fn["begin"] if fn else entry
    key = f"0x{key_entry:X}"
    if key not in out:
        out[key] = trace_function(base, pe, key_entry, strings)
    return key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    exe = Path(args.game_root) / "GoW.exe"
    if not exe.is_file():
        raise RuntimeError(f"missing {exe}")
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {digest}")

    base = load_base()
    pe = base.load_base().PE(exe.read_bytes())
    strings = base.load_base().ascii_map(pe)

    functions = {}
    serializer_key = add_function(functions, base, pe, SERIALIZER, strings)
    for entry in SEED_HELPERS.values():
        add_function(functions, base, pe, entry, strings)

    # Include every pdata function in the serializer's tight local range. This
    # avoids missing a helper reached through a jump table/fallthrough path.
    for row in pe.runtime_functions:
        if LOCAL_BEGIN <= row["begin"] < LOCAL_END:
            add_function(functions, base, pe, row["begin"], strings)

    # Two-hop expansion from serializer/local helpers. Keep only executable
    # functions with valid pdata boundaries to avoid interpreting data as code.
    frontier = list(functions.keys())
    for _depth in range(2):
        new_entries = []
        for key in frontier:
            tr = functions[key]
            for edge in tr["direct_edges"]:
                if edge["kind"] != "call":
                    continue
                fb = edge.get("target_function_begin")
                if fb is None:
                    continue
                k = f"0x{fb:X}"
                if k not in functions:
                    new_entries.append(fb)
        frontier = []
        for entry in sorted(set(new_entries)):
            k = add_function(functions, base, pe, entry, strings)
            frontier.append(k)

    reverse_known = {v: k for k, v in KNOWN.items()}
    intersections = []
    userdata_candidates = []
    ranked = []
    for key, tr in functions.items():
        known_edges = []
        for edge in tr["direct_edges"]:
            name = reverse_known.get(edge["dest"])
            if name:
                known_edges.append({**edge, "known_name": name})
                intersections.append({"function": key, **edge, "known_name": name})
        uctx = [c for c in tr["lua_type_contexts"] if c["userdata_type7_nearby"]]
        if uctx:
            userdata_candidates.append({"function": key, "contexts": uctx})
        interesting = [r for r in tr["rip_refs"] if r.get("text") and any(t in r["text"].lower() for t in INTERESTING)]
        score = len(interesting) * 4 + len(known_edges) * 10 + len(uctx) * 12 + len(tr["indirect_calls"])
        if score:
            ranked.append({
                "function": key,
                "score": score,
                "range": [tr["begin"], tr["end"]],
                "interesting_strings": [r["text"] for r in interesting],
                "known_edges": known_edges,
                "userdata_type7_contexts": uctx,
                "indirect_calls": tr["indirect_calls"],
            })
    ranked.sort(key=lambda r: (-r["score"], r["function"]))

    result = {
        "schema": 1,
        "analysis": "lua_state_serializer_userdata_trace",
        "gow_exe_sha256": digest,
        "serializer": serializer_key,
        "seed_helpers": {k: f"0x{v:X}" for k, v in SEED_HELPERS.items()},
        "local_range": [LOCAL_BEGIN, LOCAL_END],
        "function_count": len(functions),
        "functions": functions,
        "known_intersections": intersections,
        "userdata_type7_candidates": userdata_candidates,
        "ranked_candidates": ranked,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_txt = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - Lua-state serializer userdata trace",
        f"gow_exe_sha256={digest}",
        f"serializer={serializer_key}",
        f"function_count={len(functions)}",
        "",
        "USERDATA TYPE-7 CANDIDATES",
    ]
    if not userdata_candidates:
        lines.append("  (none from direct lua_type+cmp7 pattern; inspect ranked/call graph)")
    for row in userdata_candidates:
        lines.append(f"  {row['function']}")
        for ctx in row["contexts"]:
            lines.append(f"    lua_type site=0x{ctx['site']:X} cmp={ctx['nearby_cmp_imm8']} context={ctx['context_hex']}")

    lines.extend(["", "KNOWN GAMEOBJECT/LUA INTERSECTIONS"])
    if not intersections:
        lines.append("  (none)")
    for row in intersections:
        lines.append(f"  {row['function']} site=0x{row['site']:X} -> 0x{row['dest']:X} {row['known_name']}")

    lines.extend(["", "RANKED CANDIDATES"])
    if not ranked:
        lines.append("  (none)")
    for row in ranked[:30]:
        lines.append(
            f"  {row['function']} score={row['score']} strings={row['interesting_strings']} "
            f"userdata7={len(row['userdata_type7_contexts'])} indirect={len(row['indirect_calls'])}"
        )
        for e in row["known_edges"]:
            lines.append(f"    known site=0x{e['site']:X} -> 0x{e['dest']:X} {e['known_name']}")

    lines.extend([
        "",
        "NOTE: type-7 detection is structural; manual disassembly is required before claiming userdata semantics.",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("LUA_STATE_SERIALIZER_USERDATA_TRACE_PASSED")
    print(
        f"functions={len(functions)} userdata_type7={len(userdata_candidates)} "
        f"known_intersections={len(intersections)} ranked={len(ranked)}"
    )


if __name__ == "__main__":
    main()
