"""Trace the exact GameObject code-side Lua class registration around 0x822C40.

The checkpoint serializer has proven that Lua userdata persistence calls the first
non-null callback at code-side Lua class +0xB8. The previous class scan found a
strong GameObject registration anchor at 0x822C40, with the exact "GameObject"
string referenced at 0x822F28 and proven GameObject unboxing calls nearby.

This read-only, version-locked pass stays deliberately narrow. It archives the
registration window, direct/indirect calls, RIP-relative pointers, executable
function-pointer candidates, +0xB8 stores, and one-hop callees around the exact
GameObject reference. It does not launch the game or open/write saves.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TARGET_FN = 0x822C40
GAMEOBJECT_REF_SITE = 0x822F28
WINDOW_BEFORE = 0xC0
WINDOW_AFTER = 0x108
KNOWN = {
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
    "gameobject_token_resolver": 0x4EF0B0,
    "userdata_serializer": 0x7E9190,
    "canpickle": 0x5AA350,
}
INTERESTING = (
    "gameobject", "codesideluaclass", "pickle", "serialize", "userdata",
    "class", "level", "wad", "refnode", "reference", "object",
)


def load_base():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pickle_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load dependency {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def qword(pe, rva: int):
    off = pe.rva_to_file(rva)
    if off is None or off + 8 > len(pe.data):
        return None
    return struct.unpack_from("<Q", pe.data, off)[0]


def ptr_rva(pe, value):
    if value is not None and IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
        return value - IMAGE_BASE
    return None


def raw_slice(pe, start: int, end: int) -> bytes:
    off = pe.rva_to_file(start)
    if off is None:
        return b""
    return pe.data[off:off + max(0, end - start)]


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
        fn = pe.function_for(dest)
        out.append({
            "kind": "call" if op == 0xE8 else "jmp",
            "site": begin + i,
            "dest": dest,
            "known": rev.get(dest),
            "target_function_begin": fn["begin"] if fn else None,
            "target_function_end": fn["end"] if fn else None,
        })
    return out


def indirect_calls(begin: int, blob: bytes):
    out = []
    for i in range(max(0, len(blob) - 2)):
        if blob[i] != 0xFF:
            continue
        modrm = blob[i + 1]
        if ((modrm >> 3) & 7) != 2:
            continue
        out.append({
            "site": begin + i,
            "modrm": modrm,
            "context_hex": blob[max(0, i-32):min(len(blob), i+48)].hex(),
        })
    return out


def rip_refs(pe, begin: int, blob: bytes, strings):
    out = []
    n = len(blob)
    for i in range(max(0, n - 7)):
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
        val = qword(pe, target)
        deref = ptr_rva(pe, val)
        deref_sec = pe.section_for_rva(deref) if deref is not None else None
        out.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target": target,
            "target_section": sec["name"] if sec else None,
            "text": strings.get(target),
            "qword_value": val,
            "deref_rva": deref,
            "deref_section": deref_sec["name"] if deref_sec else None,
            "deref_text": strings.get(deref) if deref is not None else None,
            "deref_executable": bool(deref_sec and deref_sec["exec"]),
        })
    return out


def b8_stores(begin: int, blob: bytes):
    out = []
    n = len(blob)
    for i in range(max(0, n - 8)):
        p = i
        rex = None
        if 0x40 <= blob[p] <= 0x4F:
            rex = blob[p]
            p += 1
        if p + 6 >= n or blob[p] not in (0x89, 0xC7):
            continue
        op = blob[p]
        modrm = blob[p+1]
        if ((modrm >> 6) & 3) != 2:
            continue
        q = p + 2
        if (modrm & 7) == 4:
            q += 1
        if q + 4 > n:
            continue
        disp = struct.unpack_from("<i", blob, q)[0]
        if disp != 0xB8:
            continue
        if op == 0xC7 and ((modrm >> 3) & 7) != 0:
            continue
        out.append({
            "site": begin + i,
            "opcode": "mov_rm_r" if op == 0x89 else "mov_rm_imm",
            "rex": rex,
            "modrm": modrm,
            "context_hex": blob[max(0, i-56):min(n, i+88)].hex(),
        })
    return out


def executable_immediates(pe, begin: int, blob: bytes):
    out = []
    for i in range(max(0, len(blob) - 8)):
        val = struct.unpack_from("<Q", blob, i)[0]
        rv = ptr_rva(pe, val)
        if rv is None:
            continue
        sec = pe.section_for_rva(rv)
        if sec and sec["exec"]:
            out.append({"site": begin+i, "value": val, "rva": rv, "section": sec["name"]})
    return out


def trace_fn(pe, entry: int, strings):
    fn = pe.function_for(entry)
    if fn is None:
        return None
    blob = pe.bytes_for(fn)
    refs = rip_refs(pe, fn["begin"], blob, strings)
    return {
        "entry": entry,
        "begin": fn["begin"],
        "end": fn["end"],
        "size": fn["end"] - fn["begin"],
        "hex": blob.hex(),
        "direct_edges": direct_edges(pe, fn["begin"], blob),
        "indirect_calls": indirect_calls(fn["begin"], blob),
        "rip_refs": refs,
        "interesting_refs": [r for r in refs if (r.get("text") and any(t in r["text"].lower() for t in INTERESTING)) or (r.get("deref_text") and any(t in r["deref_text"].lower() for t in INTERESTING))],
        "b8_stores": b8_stores(fn["begin"], blob),
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

    target = trace_fn(pe, TARGET_FN, strings)
    if target is None:
        raise RuntimeError("target registration function has no .pdata record")
    if not (target["begin"] <= GAMEOBJECT_REF_SITE < target["end"]):
        raise RuntimeError("GameObject reference site is outside target function")

    ws = max(target["begin"], GAMEOBJECT_REF_SITE - WINDOW_BEFORE)
    we = min(target["end"], GAMEOBJECT_REF_SITE + WINDOW_AFTER)
    wb = raw_slice(pe, ws, we)
    window = {
        "begin": ws,
        "end": we,
        "hex": wb.hex(),
        "direct_edges": direct_edges(pe, ws, wb),
        "indirect_calls": indirect_calls(ws, wb),
        "rip_refs": rip_refs(pe, ws, wb, strings),
        "b8_stores": b8_stores(ws, wb),
        "executable_immediates": executable_immediates(pe, ws, wb),
    }

    one_hop = {}
    for edge in window["direct_edges"]:
        if edge["kind"] != "call":
            continue
        fb = edge.get("target_function_begin")
        if fb is None:
            continue
        key = f"0x{fb:X}"
        if key not in one_hop:
            one_hop[key] = trace_fn(pe, fb, strings)

    ranked = []
    for key, tr in one_hop.items():
        if not tr:
            continue
        exec_refs = [r for r in tr["rip_refs"] if r.get("deref_executable")]
        known = [e for e in tr["direct_edges"] if e.get("known")]
        score = 20*len(tr["b8_stores"]) + 5*len(exec_refs) + 4*len(tr["interesting_refs"]) + 8*len(known) + len(tr["indirect_calls"])
        ranked.append({
            "function": key,
            "score": score,
            "b8_store_count": len(tr["b8_stores"]),
            "exec_ref_count": len(exec_refs),
            "interesting_strings": [r.get("text") or r.get("deref_text") for r in tr["interesting_refs"]],
            "known_edges": known,
            "indirect_count": len(tr["indirect_calls"]),
        })
    ranked.sort(key=lambda r: (-r["score"], r["function"]))

    result = {
        "schema": 1,
        "analysis": "gameobject_class_registration_detail",
        "gow_exe_sha256": digest,
        "target_function": target,
        "gameobject_ref_site": GAMEOBJECT_REF_SITE,
        "registration_window": window,
        "one_hop_callees": one_hop,
        "ranked_callees": ranked,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_txt = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - GameObject class registration detail",
        f"gow_exe_sha256={digest}",
        f"target=0x{target['begin']:X}-0x{target['end']:X}",
        f"gameobject_ref_site=0x{GAMEOBJECT_REF_SITE:X}",
        f"window=0x{ws:X}-0x{we:X}",
        "",
        "WINDOW RIP REFERENCES",
    ]
    for r in window["rip_refs"]:
        extra = ""
        if r.get("text"):
            extra += f" text={r['text']!r}"
        if r.get("deref_rva") is not None:
            extra += f" deref=0x{r['deref_rva']:X} exec={r['deref_executable']}"
            if r.get("deref_text"):
                extra += f" deref_text={r['deref_text']!r}"
        lines.append(f"  0x{r['site']:X} {r['opcode']} -> 0x{r['target']:X}{extra}")

    lines += ["", "WINDOW CALLS"]
    for e in window["direct_edges"]:
        suffix = f" known={e['known']}" if e.get("known") else ""
        lines.append(f"  {e['kind'].upper()} 0x{e['site']:X} -> 0x{e['dest']:X}{suffix}")
    for c in window["indirect_calls"]:
        lines.append(f"  INDIRECT 0x{c['site']:X} context={c['context_hex']}")

    lines += ["", "WINDOW +0xB8 STORES"]
    if not window["b8_stores"]:
        lines.append("  (none in exact window)")
    for s in window["b8_stores"]:
        lines.append(f"  0x{s['site']:X} {s['opcode']} context={s['context_hex']}")

    lines += ["", "RANKED WINDOW CALLEES"]
    for r in ranked:
        lines.append(
            f"  {r['function']} score={r['score']} b8={r['b8_store_count']} exec_refs={r['exec_ref_count']} "
            f"indirect={r['indirect_count']} strings={r['interesting_strings']}"
        )
        for e in r["known_edges"]:
            lines.append(f"    known 0x{e['site']:X} -> 0x{e['dest']:X} {e['known']}")

    lines += [
        "",
        "NOTE: +0xB8 write/function-pointer results are structural candidates until register dataflow is manually verified.",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ]
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("GAMEOBJECT_CLASS_REGISTRATION_DETAIL_TRACE_PASSED")
    print(f"window_calls={len(window['direct_edges'])} one_hop={len(one_hop)} b8_window={len(window['b8_stores'])} ranked={len(ranked)}")


if __name__ == "__main__":
    main()
