"""Trace the exact native engine.SerializeHook handler for persistent userdata research.

Read-only, version-locked static analysis of the supported God of War PC executable.
The engine registration block pairs SerializeHook with RVA 0x4A5D50, and earlier
independent scans already observed a direct call at 0x4A5DAF to the proven
GameObject token packer 0x60B9C0. This tracer records the exact handler body,
control-flow edges, direct/indirect calls, RIP-relative data/string references,
and one-hop callees around that intersection.

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
HANDLER = 0x4A5D50
REG_NAME_SITE = 0x5A8AC1
REG_HANDLER_SITE = 0x5A8AE6
TOKEN_PACKER = 0x60B9C0
KNOWN = {
    "token_packer": 0x60B9C0,
    "token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "pickle_driver": 0x5AF8AD,
    "pickle_table_builder": 0x5AF01C,
    "unpickle_driver": 0x5B1030,
    "canpickle": 0x5AA350,
}
INTERESTING = (
    "serialize", "deserialize", "pickle", "unpickle", "gameobject", "userdata",
    "guid", "persistent", "objectref", "refnode", "wad", "level", "codeside",
)


def load_base():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    if not path.is_file():
        raise RuntimeError(f"missing dependency {path}")
    spec = importlib.util.spec_from_file_location("gow_pickle_bridge_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load dependency")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def bounded(pe, entry: int, fallback: int = 0x300):
    fn = pe.function_for(entry)
    if fn:
        return fn["begin"], fn["end"], pe.bytes_for(fn), "pdata"
    begin = entry
    end = min(pe.size_of_image, entry + fallback)
    off = pe.rva_to_file(begin)
    blob = b"" if off is None else pe.data[off:off + end - begin]
    return begin, end, blob, "bounded"


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


def indirect_sites(begin: int, blob: bytes):
    out = []
    i = 0
    while i + 1 < len(blob):
        rex = None
        pos = i
        if 0x40 <= blob[pos] <= 0x4F:
            rex = blob[pos]
            pos += 1
        if pos + 1 < len(blob) and blob[pos] == 0xFF:
            modrm = blob[pos + 1]
            reg = (modrm >> 3) & 7
            if reg in (2, 4):
                out.append({
                    "site": begin + i,
                    "kind": "call_indirect" if reg == 2 else "jmp_indirect",
                    "rex": rex,
                    "modrm": modrm,
                    "bytes": blob[i:min(len(blob), i + 12)].hex(),
                })
        i += 1
    return out


def rip_refs(pe, begin: int, blob: bytes, strings):
    out = []
    for i in range(max(0, len(blob) - 7)):
        # Common RIP-relative MOV/LEA with optional REX.
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
        text = strings.get(target)
        out.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target": target,
            "section": sec["name"] if sec else None,
            "exec": bool(sec and sec["exec"]),
            "text": text,
        })
    return out


def callers(pe, target: int):
    out = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start = sec["raw"]
        stop = min(len(pe.data), start + sec["rawsize"])
        for off in range(start, max(start, stop - 5)):
            if pe.data[off] not in (0xE8, 0xE9):
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", pe.data, off + 1)[0]
            if site + 5 + disp != target:
                continue
            fn = pe.function_for(site)
            out.append({
                "kind": "call" if pe.data[off] == 0xE8 else "jmp",
                "site": site,
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def trace_fn(pe, entry: int, strings):
    begin, end, blob, boundary = bounded(pe, entry)
    refs = rip_refs(pe, begin, blob, strings)
    return {
        "entry": entry,
        "begin": begin,
        "end": end,
        "size": end - begin,
        "boundary": boundary,
        "hex": blob.hex(),
        "callers": callers(pe, entry),
        "direct_edges": direct_edges(pe, begin, blob),
        "indirect_sites": indirect_sites(begin, blob),
        "rip_refs": refs,
        "interesting_refs": [r for r in refs if r.get("text") and any(x in r["text"].lower() for x in INTERESTING)],
    }


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
    handler = trace_fn(pe, HANDLER, strings)

    token_calls = [e for e in handler["direct_edges"] if e["dest"] == TOKEN_PACKER]
    one_hop = {}
    for e in handler["direct_edges"]:
        if e["kind"] != "call" or e["dest"] == TOKEN_PACKER:
            continue
        dest = e["target_function_begin"] if e.get("target_function_begin") is not None else e["dest"]
        key = f"0x{dest:X}"
        if key not in one_hop:
            one_hop[key] = trace_fn(pe, dest, strings)

    registration = {
        "name": "SerializeHook",
        "name_ref_site": REG_NAME_SITE,
        "handler_ref_site": REG_HANDLER_SITE,
        "handler_rva": HANDLER,
    }

    result = {
        "schema": 1,
        "analysis": "engine_serializehook_handler_trace",
        "gow_exe_sha256": digest,
        "registration": registration,
        "handler": handler,
        "token_packer_calls": token_calls,
        "one_hop_callees": one_hop,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    outj = Path(args.output_json)
    outt = Path(args.output_text)
    outj.parent.mkdir(parents=True, exist_ok=True)
    outj.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - exact engine.SerializeHook handler trace",
        f"gow_exe_sha256={digest}",
        f"registration=SerializeHook@0x{REG_NAME_SITE:X} -> handler_ref@0x{REG_HANDLER_SITE:X} -> 0x{HANDLER:X}",
        f"handler_range=0x{handler['begin']:X}-0x{handler['end']:X} size={handler['size']} boundary={handler['boundary']}",
        f"direct_edges={len(handler['direct_edges'])}",
        f"indirect_sites={len(handler['indirect_sites'])}",
        f"rip_refs={len(handler['rip_refs'])}",
        f"token_packer_calls={len(token_calls)}",
        "",
        "DIRECT EDGES",
    ]
    for e in handler["direct_edges"]:
        suffix = f" known={e['known']}" if e.get("known") else ""
        lines.append(f"  {e['kind'].upper()} site=0x{e['site']:X} -> 0x{e['dest']:X}{suffix}")
    if not handler["direct_edges"]:
        lines.append("  (none)")

    lines.extend(["", "INDIRECT SITES"])
    for row in handler["indirect_sites"]:
        lines.append(f"  {row['kind']} site=0x{row['site']:X} bytes={row['bytes']}")
    if not handler["indirect_sites"]:
        lines.append("  (none)")

    lines.extend(["", "RIP REFERENCES"])
    for r in handler["rip_refs"]:
        lines.append(f"  {r['opcode']} site=0x{r['site']:X} -> 0x{r['target']:X} section={r['section']} text={r['text']!r}")
    if not handler["rip_refs"]:
        lines.append("  (none)")

    lines.extend(["", "TOKEN PACKER INTERSECTION"])
    for e in token_calls:
        lines.append(f"  site=0x{e['site']:X} -> 0x{e['dest']:X} known=token_packer")
    if not token_calls:
        lines.append("  (none)")

    lines.extend(["", "ONE-HOP CALLEES"])
    for key, tr in one_hop.items():
        lines.append(f"  {key} range=0x{tr['begin']:X}-0x{tr['end']:X} size={tr['size']} direct_edges={len(tr['direct_edges'])} indirect={len(tr['indirect_sites'])}")
        for r in tr["interesting_refs"]:
            lines.append(f"    string site=0x{r['site']:X} -> {r['text']!r}")
        for e in tr["direct_edges"]:
            if e.get("known"):
                lines.append(f"    known edge site=0x{e['site']:X} -> {e['known']} (0x{e['dest']:X})")

    lines.extend([
        "",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    outt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("ENGINE_SERIALIZEHOOK_HANDLER_TRACE_PASSED")
    print(f"handler=0x{HANDLER:X} token_packer_calls={len(token_calls)} indirect={len(handler['indirect_sites'])}")


if __name__ == "__main__":
    main()
