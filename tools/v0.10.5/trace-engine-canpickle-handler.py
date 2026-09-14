"""Trace the exact native engine.CanPickle handler at RVA 0x5AA350.

Read-only, version-locked static analysis. The registration sequence has proven:
  CanPickle string ref 0x5A91CF
  handler address load 0x5A91F4 -> 0x5AA350
  next binding string HasGameOption at 0x5A9250

This script traces the exact handler, its direct calls, RIP-relative references,
indirect call sites, and one-hop callees. No game launch and no save I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
HANDLER = 0x5AA350
KNOWN = {
    "token_packer": 0x60B9C0,
    "token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "pickle_driver": 0x5AF8AD,
    "pickle_table_builder": 0x5AF01C,
    "unpickle_driver": 0x5B1030,
}
INTERESTING = (
    "pickle", "serialize", "userdata", "gameobject", "object", "ref", "guid",
    "level", "wad", "persistent", "soft", "lua", "type", "class"
)


def load_base():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fn_region(pe, entry: int, fallback: int = 0x300):
    fn = pe.function_for(entry)
    if fn:
        return fn["begin"], fn["end"], pe.bytes_for(fn), "pdata"
    begin, end = entry, min(pe.size_of_image, entry + fallback)
    off = pe.rva_to_file(begin)
    blob = b"" if off is None else pe.data[off:off + end - begin]
    return begin, end, blob, "bounded-leaf"


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
    # Common FF /2 CALL r/m64 and FF /4 JMP r/m64 encodings. We report sites
    # conservatively without pretending to fully decode arbitrary x64 operands.
    for i in range(max(0, len(blob) - 2)):
        if blob[i] != 0xFF:
            continue
        reg = (blob[i + 1] >> 3) & 7
        if reg in (2, 4):
            out.append({
                "kind": "call_indirect" if reg == 2 else "jmp_indirect",
                "site": begin + i,
                "bytes": blob[i:i + 8].hex(),
            })
    return out


def rip_refs(pe, begin: int, blob: bytes, strings):
    rows = []
    for i in range(max(0, len(blob) - 7)):
        # REX + MOV/LEA r64,[rip+disp32]
        if 0x40 <= blob[i] <= 0x4F and blob[i + 1] in (0x8B, 0x8D) and (blob[i + 2] & 0xC7) == 0x05:
            disp = struct.unpack_from("<i", blob, i + 3)[0]
            site = begin + i
            target = site + 7 + disp
            sec = pe.section_for_rva(target)
            rows.append({
                "site": site,
                "opcode": "mov" if blob[i + 1] == 0x8B else "lea",
                "target": target,
                "section": sec["name"] if sec else None,
                "text": strings.get(target),
            })
        # CMP byte/dword/qword [rip+disp32], imm/register families are useful
        # for discovering globals but are not fully decoded here.
    return rows


def caller_sites(pe, target: int):
    rows = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start, stop = sec["raw"], min(len(pe.data), sec["raw"] + sec["rawsize"])
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
            rows.append({
                "site": site,
                "kind": "call" if pe.data[off] == 0xE8 else "jmp",
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return rows


def trace(pe, entry: int, strings):
    begin, end, blob, boundary = fn_region(pe, entry)
    refs = rip_refs(pe, begin, blob, strings)
    return {
        "entry": entry,
        "begin": begin,
        "end": end,
        "size": end - begin,
        "boundary": boundary,
        "callers": caller_sites(pe, entry),
        "direct_edges": direct_edges(pe, begin, blob),
        "indirect_sites": indirect_sites(begin, blob),
        "rip_refs": refs,
        "interesting_refs": [r for r in refs if r.get("text") and any(t in r["text"].lower() for t in INTERESTING)],
        "hex": blob.hex(),
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

    primary = trace(pe, HANDLER, strings)
    callee_entries = sorted({
        e["target_function_begin"] if e.get("target_function_begin") is not None else e["dest"]
        for e in primary["direct_edges"] if e["kind"] == "call"
    })
    one_hop = {}
    for entry in callee_entries:
        if entry is None or not (0 <= entry < pe.size_of_image):
            continue
        try:
            one_hop[f"0x{entry:X}"] = trace(pe, entry, strings)
        except Exception as exc:
            one_hop[f"0x{entry:X}"] = {"entry": entry, "error": str(exc)}

    known_hits = []
    for owner, tr in [("handler", primary)] + list(one_hop.items()):
        if not isinstance(tr, dict):
            continue
        for edge in tr.get("direct_edges", []):
            if edge.get("known"):
                known_hits.append({"owner": owner, **edge})

    result = {
        "schema": 1,
        "analysis": "exact_engine_canpickle_handler",
        "gow_exe_sha256": digest,
        "registration_proof": {
            "name_ref_site": 0x5A91CF,
            "handler_ref_site": 0x5A91F4,
            "handler_rva": HANDLER,
            "next_name_ref_site": 0x5A9250,
            "next_name": "HasGameOption",
        },
        "handler": primary,
        "one_hop_callees": one_hop,
        "known_intersections": known_hits,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - exact engine.CanPickle handler trace",
        f"gow_exe_sha256={digest}",
        "registration=CanPickle@0x5A91CF -> handler_ref@0x5A91F4 -> 0x5AA350 -> next=HasGameOption@0x5A9250",
        f"handler_range=0x{primary['begin']:X}-0x{primary['end']:X} size={primary['size']} boundary={primary['boundary']}",
        f"direct_calls={sum(1 for e in primary['direct_edges'] if e['kind']=='call')}",
        f"indirect_sites={len(primary['indirect_sites'])}",
        f"rip_refs={len(primary['rip_refs'])}",
        f"one_hop_callees={len(one_hop)}",
        f"known_intersections={len(known_hits)}",
        "",
        "HANDLER DIRECT EDGES",
    ]
    for e in primary["direct_edges"]:
        suffix = f" known={e['known']}" if e.get("known") else ""
        lines.append(f"  {e['kind'].upper()} site=0x{e['site']:X} -> 0x{e['dest']:X}{suffix}")
    if not primary["direct_edges"]:
        lines.append("  (none)")

    lines.extend(["", "HANDLER INDIRECT SITES"])
    for row in primary["indirect_sites"]:
        lines.append(f"  {row['kind']} site=0x{row['site']:X} bytes={row['bytes']}")
    if not primary["indirect_sites"]:
        lines.append("  (none)")

    lines.extend(["", "HANDLER RIP REFS"])
    for r in primary["rip_refs"]:
        lines.append(f"  site=0x{r['site']:X} {r['opcode']} -> 0x{r['target']:X} section={r['section']} text={r.get('text')!r}")
    if not primary["rip_refs"]:
        lines.append("  (none)")

    lines.extend(["", "ONE-HOP CALLEES"])
    for key, tr in one_hop.items():
        if "error" in tr:
            lines.append(f"  {key} ERROR {tr['error']}")
            continue
        lines.append(f"  {key} range=0x{tr['begin']:X}-0x{tr['end']:X} size={tr['size']} calls={sum(1 for e in tr['direct_edges'] if e['kind']=='call')} indirect={len(tr['indirect_sites'])}")
        for r in tr["interesting_refs"]:
            lines.append(f"    string site=0x{r['site']:X} -> {r.get('text')!r}")
        for e in tr["direct_edges"]:
            if e.get("known"):
                lines.append(f"    KNOWN {e['kind'].upper()} site=0x{e['site']:X} -> 0x{e['dest']:X} {e['known']}")

    lines.extend(["", "KNOWN INTERSECTIONS"])
    for h in known_hits:
        lines.append(f"  owner={h['owner']} site=0x{h['site']:X} -> 0x{h['dest']:X} {h['known']}")
    if not known_hits:
        lines.append("  (none)")

    lines.extend(["", "source_hash_unchanged=true", "game_launched=false", "save_opened=false", "progression_written=false"])
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("ENGINE_CANPICKLE_HANDLER_TRACE_PASSED")
    print(f"handler=0x{HANDLER:X} calls={sum(1 for e in primary['direct_edges'] if e['kind']=='call')} indirect={len(primary['indirect_sites'])} one_hop={len(one_hop)}")


if __name__ == "__main__":
    main()
