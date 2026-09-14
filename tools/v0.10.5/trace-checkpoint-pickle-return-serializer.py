"""Trace the checkpoint save path after core.pickle.Pickle returns its Lua table.

Read-only, version-locked static analysis for the supported God of War PC
executable. core.pickle has been proven to leave engine-pickleable userdata
unchanged, so this scanner concentrates on the native checkpoint path that
consumes the returned P table and eventually serializes its Lua values.

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
TARGETS = {
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
    "on_pickle_internal": 0x5B2130,
}
KNOWN = {
    "token_packer": 0x60B9C0,
    "token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
}
INTERESTING = (
    "pickle", "unpickle", "userdata", "serialize", "checkpoint", "save",
    "gameobject", "subobj", "softpickle", "prevunpickle", "codesidelua",
    "reference", "objectref", "persistent", "level", "wad",
)


def load_base():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    if not path.is_file():
        raise RuntimeError(f"missing dependency {path}")
    spec = importlib.util.spec_from_file_location("gow_pickle_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load pickle bridge dependency")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def direct_edges(pe, begin: int, blob: bytes):
    rev = {v: k for k, v in KNOWN.items()}
    out = []
    for i in range(max(0, len(blob) - 4)):
        op = blob[i]
        if op not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", blob, i + 1)[0]
        dest = begin + i + 5 + disp
        if not (0 <= dest < pe.size_of_image):
            continue
        tf = pe.function_for(dest)
        out.append({
            "kind": "call" if op == 0xE8 else "jmp",
            "site": begin + i,
            "dest": dest,
            "known": rev.get(dest),
            "target_function_begin": tf["begin"] if tf else None,
            "target_function_end": tf["end"] if tf else None,
        })
    return out


def branches(pe, begin: int, blob: bytes):
    out = []
    for i in range(len(blob)):
        b = blob[i]
        site = begin + i
        if b in (0xE8, 0xE9) and i + 4 < len(blob):
            disp = struct.unpack_from("<i", blob, i + 1)[0]
            dest = site + 5 + disp
            out.append({"kind": "call" if b == 0xE8 else "jmp", "site": site, "dest": dest})
        elif b == 0xEB and i + 1 < len(blob):
            disp = struct.unpack_from("<b", blob, i + 1)[0]
            out.append({"kind": "jmp8", "site": site, "dest": site + 2 + disp})
        elif 0x70 <= b <= 0x7F and i + 1 < len(blob):
            disp = struct.unpack_from("<b", blob, i + 1)[0]
            out.append({"kind": f"jcc8_{b:02X}", "site": site, "dest": site + 2 + disp})
        elif b == 0x0F and i + 5 < len(blob) and 0x80 <= blob[i + 1] <= 0x8F:
            disp = struct.unpack_from("<i", blob, i + 2)[0]
            out.append({"kind": f"jcc32_{blob[i+1]:02X}", "site": site, "dest": site + 6 + disp})
    return out


def indirect_calls(begin: int, blob: bytes):
    out = []
    # Capture FF /2 (CALL r/m64). This is deliberately syntactic; the raw bytes
    # are archived for later manual decode rather than over-claiming a target.
    for i in range(max(0, len(blob) - 2)):
        if blob[i] != 0xFF:
            continue
        modrm = blob[i + 1]
        if ((modrm >> 3) & 7) != 2:
            continue
        out.append({
            "site": begin + i,
            "modrm": modrm,
            "bytes": blob[i:min(len(blob), i + 16)].hex(),
        })
    return out


def rip_refs(pe, begin: int, blob: bytes, strings):
    out = []
    for i in range(max(0, len(blob) - 7)):
        if not (0x40 <= blob[i] <= 0x4F):
            continue
        op = blob[i + 1]
        modrm = blob[i + 2]
        if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", blob, i + 3)[0]
        site = begin + i
        target = site + 7 + disp
        sec = pe.section_for_rva(target)
        out.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target": target,
            "section": sec["name"] if sec else None,
            "text": strings.get(target),
        })
    return out


def bounded(pe, entry: int, fallback=0x300):
    fn = pe.function_for(entry)
    if fn is not None:
        return fn["begin"], fn["end"], pe.bytes_for(fn), "pdata"
    off = pe.rva_to_file(entry)
    end = min(pe.size_of_image, entry + fallback)
    return entry, end, b"" if off is None else pe.data[off:off + end - entry], "bounded-leaf"


def trace_entry(pe, entry: int, strings):
    begin, end, blob, boundary = bounded(pe, entry)
    refs = rip_refs(pe, begin, blob, strings)
    return {
        "entry": entry,
        "begin": begin,
        "end": end,
        "size": end - begin,
        "boundary": boundary,
        "hex": blob.hex(),
        "direct_edges": direct_edges(pe, begin, blob),
        "branches": branches(pe, begin, blob),
        "indirect_calls": indirect_calls(begin, blob),
        "rip_refs": refs,
        "interesting_refs": [r for r in refs if r.get("text") and any(t in r["text"].lower() for t in INTERESTING)],
    }


def next_runtime_functions(pe, fn_begin: int, count=3):
    rows = pe.runtime_functions
    index = next((i for i, r in enumerate(rows) if r["begin"] == fn_begin), None)
    if index is None:
        return []
    return rows[index + 1:index + 1 + count]


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
    pe = base.PE(exe.read_bytes())
    strings = base.ascii_map(pe)

    targets = {name: trace_entry(pe, entry, strings) for name, entry in TARGETS.items()}

    # The checkpoint routines have previously crossed pdata boundaries. Archive
    # the following runtime functions as logical-continuation candidates without
    # assuming that they are part of the same C++ source routine.
    continuations = {}
    for name in ("pickle_table_builder", "pickle_driver"):
        tr = targets[name]
        if tr["boundary"] != "pdata":
            continue
        for row in next_runtime_functions(pe, tr["begin"], 3):
            key = f"0x{row['begin']:X}"
            continuations[key] = trace_entry(pe, row["begin"], strings)

    # Gather one-hop callees from the two save-side targets. Keep only real CALLs
    # with known function boundaries and de-duplicate by function begin.
    one_hop = {}
    for name in ("pickle_table_builder", "pickle_driver"):
        for edge in targets[name]["direct_edges"]:
            if edge["kind"] != "call":
                continue
            fb = edge.get("target_function_begin")
            if fb is None:
                continue
            key = f"0x{fb:X}"
            if key not in one_hop:
                one_hop[key] = trace_entry(pe, fb, strings)

    # Highlight likely post-Pickle consumers conservatively. We do not know the
    # exact lua_pcall helper yet, so rank one-hop functions by serializer-related
    # strings, indirect calls, and intersections with proven GameObject helpers.
    ranked = []
    for key, tr in one_hop.items():
        known_edges = [e for e in tr["direct_edges"] if e.get("known")]
        score = len(tr["interesting_refs"]) * 4 + len(tr["indirect_calls"]) + len(known_edges) * 8
        if score:
            ranked.append({
                "function": key,
                "score": score,
                "interesting_strings": [r.get("text") for r in tr["interesting_refs"]],
                "known_edges": known_edges,
                "indirect_count": len(tr["indirect_calls"]),
            })
    ranked.sort(key=lambda r: (-r["score"], r["function"]))

    known_intersections = []
    for scope_name, scope in [("target:" + k, v) for k, v in targets.items()] + [("one_hop:" + k, v) for k, v in one_hop.items()]:
        for e in scope["direct_edges"]:
            if e.get("known"):
                known_intersections.append({"scope": scope_name, **e})

    result = {
        "schema": 1,
        "analysis": "checkpoint_pickle_return_serializer_trace",
        "gow_exe_sha256": digest,
        "targets": targets,
        "continuation_candidates": continuations,
        "one_hop_callees": one_hop,
        "ranked_post_return_candidates": ranked,
        "known_intersections": known_intersections,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_txt = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - checkpoint pickle return serializer trace",
        f"gow_exe_sha256={digest}",
        "",
        "TARGETS",
    ]
    for name, tr in targets.items():
        lines.append(
            f"  {name}: entry=0x{tr['entry']:X} range=0x{tr['begin']:X}-0x{tr['end']:X} "
            f"size={tr['size']} boundary={tr['boundary']} calls={sum(e['kind']=='call' for e in tr['direct_edges'])} "
            f"indirect={len(tr['indirect_calls'])} refs={len(tr['interesting_refs'])}"
        )
        for r in tr["interesting_refs"]:
            lines.append(f"    string site=0x{r['site']:X} -> {r['text']!r}")
        for e in tr["direct_edges"]:
            suffix = f" known={e['known']}" if e.get("known") else ""
            lines.append(f"    {e['kind'].upper()} site=0x{e['site']:X} -> 0x{e['dest']:X}{suffix}")
        for ind in tr["indirect_calls"]:
            lines.append(f"    INDIRECT_CALL site=0x{ind['site']:X} bytes={ind['bytes']}")

    lines.extend(["", "LOGICAL CONTINUATION CANDIDATES"])
    if not continuations:
        lines.append("  (none)")
    for key, tr in continuations.items():
        lines.append(
            f"  {key} range=0x{tr['begin']:X}-0x{tr['end']:X} calls={sum(e['kind']=='call' for e in tr['direct_edges'])} "
            f"indirect={len(tr['indirect_calls'])}"
        )
        for r in tr["interesting_refs"]:
            lines.append(f"    string site=0x{r['site']:X} -> {r['text']!r}")

    lines.extend(["", "RANKED ONE-HOP CONSUMERS"])
    if not ranked:
        lines.append("  (none ranked; inspect JSON one_hop_callees)")
    for row in ranked:
        lines.append(
            f"  {row['function']} score={row['score']} indirect={row['indirect_count']} "
            f"strings={row['interesting_strings']}"
        )
        for e in row["known_edges"]:
            lines.append(f"    known {e['known']} site=0x{e['site']:X} -> 0x{e['dest']:X}")

    lines.extend(["", "KNOWN INTERSECTIONS"])
    if not known_intersections:
        lines.append("  (none)")
    for row in known_intersections:
        lines.append(
            f"  {row['scope']} site=0x{row['site']:X} -> 0x{row['dest']:X} known={row['known']}"
        )

    lines.extend([
        "",
        "NOTE: candidate ranking is structural only; it does not claim dataflow until manually verified.",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("CHECKPOINT_PICKLE_RETURN_SERIALIZER_TRACE_PASSED")
    print(
        f"targets={len(targets)} continuations={len(continuations)} one_hop={len(one_hop)} "
        f"ranked={len(ranked)} known_intersections={len(known_intersections)}"
    )


if __name__ == "__main__":
    main()
