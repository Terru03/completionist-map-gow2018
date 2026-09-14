"""Resolve the GameObject code-side Lua class persistence callback.

The checkpoint serializer at 0x7E9190 has now been proven to handle internal
Lua tag 7 (userdata), recover the code-side Lua class, walk its parent chain,
and invoke the first non-null callback stored at class +0xB8. This read-only,
version-locked scanner tries to resolve that +0xB8 callback specifically for
GameObject by correlating:

* exact ``GameObject`` strings,
* the already-proven GameObject Lua method descriptor range,
* static data records containing those references,
* code functions that reference both the class name and method table,
* common x64 stores to a +0xB8 class field.

It does not launch the game or open/write saves.
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
METHOD_START = 0x11B8000
METHOD_END = 0x11C1000
KNOWN = {
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
    "gameobject_token_resolver": 0x4EF0B0,
    "userdata_serializer": 0x7E9190,
}


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


def qword_at(pe, rva: int):
    off = pe.rva_to_file(rva)
    if off is None or off + 8 > len(pe.data):
        return None
    return struct.unpack_from("<Q", pe.data, off)[0]


def ptr_rva(pe, value: int):
    if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
        return value - IMAGE_BASE
    return None


def qword_occurrences(pe, target_rva: int):
    needle = struct.pack("<Q", IMAGE_BASE + target_rva)
    out = []
    pos = 0
    while True:
        off = pe.data.find(needle, pos)
        if off < 0:
            break
        rva = pe.file_to_rva(off)
        if rva is not None:
            sec = pe.section_for_rva(rva)
            out.append({"rva": rva, "section": sec["name"] if sec else None})
        pos = off + 1
    return out


def rip_refs(pe, strings, exact_targets: set[int]):
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start = s["raw"]
        end = min(len(pe.data), start + s["rawsize"])
        d = pe.data
        for off in range(start, end - 7):
            if not (0x40 <= d[off] <= 0x4F):
                continue
            op = d[off + 1]
            modrm = d[off + 2]
            if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", d, off + 3)[0]
            target = site + 7 + disp
            kind = None
            if target in exact_targets:
                kind = "exact"
            elif METHOD_START <= target < METHOD_END:
                kind = "gameobject_method_range"
            if kind is None:
                continue
            fn = pe.function_for(site)
            out.append({
                "site": site,
                "target": target,
                "kind": kind,
                "opcode": "mov" if op == 0x8B else "lea",
                "text": strings.get(target),
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def direct_edges(pe, begin: int, blob: bytes):
    rev = {v: k for k, v in KNOWN.items()}
    out = []
    for i in range(max(0, len(blob) - 4)):
        if blob[i] not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", blob, i + 1)[0]
        dest = begin + i + 5 + disp
        if not (0 <= dest < pe.size_of_image):
            continue
        tf = pe.function_for(dest)
        out.append({
            "kind": "call" if blob[i] == 0xE8 else "jmp",
            "site": begin + i,
            "dest": dest,
            "known": rev.get(dest),
            "target_function_begin": tf["begin"] if tf else None,
            "target_function_end": tf["end"] if tf else None,
        })
    return out


def b8_stores(begin: int, blob: bytes):
    """Conservatively decode common MOV r/m64,r64 or MOV r/m64,imm32 stores.

    We only claim the displacement, not which architectural register is the
    class object. Raw context is archived for manual verification.
    """
    out = []
    n = len(blob)
    for i in range(n - 7):
        p = i
        rex = None
        if 0x40 <= blob[p] <= 0x4F:
            rex = blob[p]
            p += 1
        if p >= n:
            continue
        op = blob[p]
        if op not in (0x89, 0xC7):
            continue
        if p + 1 >= n:
            continue
        modrm = blob[p + 1]
        mod = (modrm >> 6) & 3
        rm = modrm & 7
        reg = (modrm >> 3) & 7
        if mod != 2:
            continue
        q = p + 2
        if rm == 4:
            if q >= n:
                continue
            q += 1  # SIB
        if q + 4 > n:
            continue
        disp = struct.unpack_from("<i", blob, q)[0]
        if disp != 0xB8:
            continue
        if op == 0xC7 and reg != 0:
            continue
        out.append({
            "site": begin + i,
            "opcode": "mov_rm64_r64" if op == 0x89 else "mov_rm64_imm32",
            "rex": rex,
            "modrm": modrm,
            "context_hex": blob[max(0, i - 48):min(n, i + 80)].hex(),
        })
    return out


def trace_function(pe, entry: int):
    fn = pe.function_for(entry)
    if fn is None:
        return None
    blob = pe.bytes_for(fn)
    return {
        "begin": fn["begin"],
        "end": fn["end"],
        "size": fn["end"] - fn["begin"],
        "hex": blob.hex(),
        "direct_edges": direct_edges(pe, fn["begin"], blob),
        "b8_stores": b8_stores(fn["begin"], blob),
    }


def static_descriptor_candidates(pe, gameobject_string_rvas: list[int]):
    """Rank static records that could be a code-side class descriptor.

    For every stored pointer to an exact GameObject string, try nearby aligned
    bases. A strong candidate has an executable qword at base+0xB8 and another
    qword within the record that points into the proven GameObject method table.
    """
    out = {}
    for srva in gameobject_string_rvas:
        for occ in qword_occurrences(pe, srva):
            occ_rva = occ["rva"]
            sec = pe.section_for_rva(occ_rva)
            if sec and sec["exec"]:
                continue
            for name_off in range(0, 0x101, 8):
                base = occ_rva - name_off
                if base < 0:
                    continue
                cb_val = qword_at(pe, base + 0xB8)
                cb_rva = ptr_rva(pe, cb_val) if cb_val is not None else None
                cb_sec = pe.section_for_rva(cb_rva) if cb_rva is not None else None
                if cb_sec is None or not cb_sec["exec"]:
                    continue
                method_ptrs = []
                go_string_ptrs = []
                for off in range(0, 0x121, 8):
                    val = qword_at(pe, base + off)
                    rv = ptr_rva(pe, val) if val is not None else None
                    if rv is None:
                        continue
                    if METHOD_START <= rv < METHOD_END:
                        method_ptrs.append({"offset": off, "target": rv})
                    if rv in gameobject_string_rvas:
                        go_string_ptrs.append({"offset": off, "target": rv})
                score = 20 + 10 * len(method_ptrs) + 3 * len(go_string_ptrs)
                key = (base, cb_rva)
                row = {
                    "base": base,
                    "section": (pe.section_for_rva(base) or {}).get("name") if pe.section_for_rva(base) else None,
                    "callback_rva": cb_rva,
                    "name_pointer_occurrence": occ_rva,
                    "name_offset": name_off,
                    "method_pointers": method_ptrs,
                    "gameobject_string_pointers": go_string_ptrs,
                    "score": score,
                }
                if key not in out or out[key]["score"] < score:
                    out[key] = row
    rows = sorted(out.values(), key=lambda r: (-r["score"], r["base"], r["callback_rva"]))
    return rows[:80]


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

    base_mod = load_base()
    pe = base_mod.PE(exe.read_bytes())
    strings = base_mod.ascii_map(pe)
    go_strings = sorted(rva for rva, text in strings.items() if text == "GameObject")
    if not go_strings:
        raise RuntimeError("exact GameObject string not found")

    exact_targets = set(go_strings)
    refs = rip_refs(pe, strings, exact_targets)
    by_fn = {}
    for ref in refs:
        fb = ref.get("function_begin")
        if fb is None:
            continue
        by_fn.setdefault(fb, []).append(ref)

    code_candidates = []
    for fb, fn_refs in by_fn.items():
        has_name = any(r["target"] in exact_targets for r in fn_refs)
        has_methods = any(r["kind"] == "gameobject_method_range" for r in fn_refs)
        tr = trace_function(pe, fb)
        if tr is None:
            continue
        score = (20 if has_name else 0) + (30 if has_methods else 0) + 12 * len(tr["b8_stores"])
        score += 20 * sum(1 for e in tr["direct_edges"] if e.get("known") in ("lua_gameobject_unbox", "gameobject_token_packer", "gameobject_token_resolver"))
        if score:
            code_candidates.append({
                "function": fb,
                "score": score,
                "has_gameobject_name": has_name,
                "has_method_range": has_methods,
                "refs": fn_refs,
                "trace": tr,
            })
    code_candidates.sort(key=lambda r: (-r["score"], r["function"]))

    static_candidates = static_descriptor_candidates(pe, go_strings)

    # Also enumerate every function in the executable with a common +0xB8 MOV
    # store, so a registration helper can still be found when it receives class
    # name/method pointers indirectly from a descriptor table.
    b8_functions = []
    for fn in pe.runtime_functions:
        blob = pe.bytes_for(fn)
        stores = b8_stores(fn["begin"], blob)
        if not stores:
            continue
        edges = direct_edges(pe, fn["begin"], blob)
        known_edges = [e for e in edges if e.get("known")]
        b8_functions.append({
            "function": fn["begin"],
            "end": fn["end"],
            "stores": stores,
            "known_edges": known_edges,
        })

    result = {
        "schema": 1,
        "analysis": "gameobject_persistence_class_callback",
        "gow_exe_sha256": digest,
        "gameobject_string_rvas": go_strings,
        "method_range": [METHOD_START, METHOD_END],
        "rip_refs": refs,
        "code_candidates": code_candidates[:80],
        "static_descriptor_candidates": static_candidates,
        "b8_store_functions": b8_functions,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - GameObject persistence class callback trace",
        f"gow_exe_sha256={digest}",
        "gameobject_strings=" + ",".join(f"0x{x:X}" for x in go_strings),
        f"method_range=0x{METHOD_START:X}-0x{METHOD_END:X}",
        "",
        "STATIC DESCRIPTOR CANDIDATES",
    ]
    if not static_candidates:
        lines.append("  (none with executable base+0xB8)")
    for row in static_candidates:
        lines.append(
            f"  base=0x{row['base']:X} callback=0x{row['callback_rva']:X} score={row['score']} "
            f"name_off=0x{row['name_offset']:X} methods=" +
            ",".join(f"+0x{x['offset']:X}->0x{x['target']:X}" for x in row['method_pointers'])
        )

    lines += ["", "CODE REGISTRATION CANDIDATES"]
    if not code_candidates:
        lines.append("  (none)")
    for row in code_candidates[:30]:
        tr = row["trace"]
        lines.append(
            f"  0x{row['function']:X} score={row['score']} name={row['has_gameobject_name']} "
            f"methods={row['has_method_range']} b8stores={len(tr['b8_stores'])}"
        )
        for ref in row["refs"]:
            label = repr(ref.get("text")) if ref.get("text") else f"0x{ref['target']:X}"
            lines.append(f"    REF site=0x{ref['site']:X} kind={ref['kind']} -> {label}")
        for st in tr["b8_stores"]:
            lines.append(f"    B8_STORE site=0x{st['site']:X} op={st['opcode']} context={st['context_hex']}")
        for e in tr["direct_edges"]:
            if e.get("known"):
                lines.append(f"    KNOWN site=0x{e['site']:X} -> 0x{e['dest']:X} {e['known']}")

    lines += ["", "ALL +0xB8 STORE FUNCTIONS"]
    lines.append(f"  count={len(b8_functions)}")
    for row in b8_functions[:80]:
        lines.append(f"  0x{row['function']:X}-0x{row['end']:X} stores={len(row['stores'])}")
        for st in row["stores"]:
            lines.append(f"    site=0x{st['site']:X} op={st['opcode']} context={st['context_hex']}")
        for e in row["known_edges"]:
            lines.append(f"    known site=0x{e['site']:X} -> 0x{e['dest']:X} {e['known']}")

    lines += [
        "",
        "NOTE: static candidates are structural until class registration is manually verified.",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ]
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("GAMEOBJECT_PERSISTENCE_CLASS_TRACE_PASSED")
    print(
        f"gameobject_strings={len(go_strings)} refs={len(refs)} code_candidates={len(code_candidates)} "
        f"static_candidates={len(static_candidates)} b8_store_functions={len(b8_functions)}"
    )


if __name__ == "__main__":
    main()
