"""Trace the native engine.CanPickle Lua binding and userdata persistence path.

Read-only, version-locked static analysis for the supported God of War PC
executable. core.pickle has now been proven to leave approved userdata unchanged:

    if engine.CanPickle(v) then return v end

Therefore the persistent GameObject representation must be implemented below the
Lua module. This tracer locates the exact native CanPickle binding via code/data
references to the "CanPickle" string, traces candidate implementations and their
call graph, and highlights intersections with already-proven GameObject helpers.

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
IMAGE_BASE = 0x140000000
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
    "pickle", "unpickle", "userdata", "gameobject", "serialize", "deserialize",
    "persistent", "objectref", "refnode", "guid", "softpickle", "canpickle",
)


def load_base():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    if not path.is_file():
        raise RuntimeError(f"missing dependency {path}")
    spec = importlib.util.spec_from_file_location("gow_pickle_bridge_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load bridge tracer dependency")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def qword_pointer_occurrences(pe, target_rva: int):
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
            out.append({
                "rva": rva,
                "file_offset": off,
                "section": sec["name"] if sec else None,
            })
        pos = off + 1
    return out


def code_rip_refs(pe, target_rva: int):
    """Find common x64 RIP-relative MOV/LEA references to one exact RVA."""
    out = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start = sec["raw"]
        stop = min(len(pe.data), start + sec["rawsize"])
        d = pe.data
        # Scan REX + opcode + modrm + disp32. This deliberately accepts all
        # registers but requires RIP-relative modrm r/m=101, mod=00.
        for off in range(start, max(start, stop - 7)):
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
            dest = site + 7 + disp
            if dest != target_rva:
                continue
            fn = pe.function_for(site)
            out.append({
                "site": site,
                "opcode": "mov" if op == 0x8B else "lea",
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def bounded_region(pe, entry: int, fallback_size: int = 0x300):
    fn = pe.function_for(entry)
    if fn:
        begin, end = fn["begin"], fn["end"]
        blob = pe.bytes_for(fn)
        boundary = "pdata"
    else:
        begin = entry
        end = min(pe.size_of_image, entry + fallback_size)
        off = pe.rva_to_file(begin)
        blob = b"" if off is None else pe.data[off:off + (end - begin)]
        boundary = "bounded-leaf"
    return begin, end, blob, boundary


def direct_callers(pe, target: int):
    out = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start = sec["raw"]
        stop = min(len(pe.data), start + sec["rawsize"])
        for off in range(start, max(start, stop - 5)):
            op = pe.data[off]
            if op not in (0xE8, 0xE9):
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", pe.data, off + 1)[0]
            dest = site + 5 + disp
            if dest != target:
                continue
            fn = pe.function_for(site)
            out.append({
                "kind": "call" if op == 0xE8 else "jmp",
                "site": site,
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def outgoing(pe, begin: int, blob: bytes):
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
            "known_target": rev.get(dest),
            "target_function_begin": tf["begin"] if tf else None,
            "target_function_end": tf["end"] if tf else None,
        })
    return out


def rip_refs_in_region(pe, begin: int, blob: bytes, strings):
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
        text = strings.get(target)
        out.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target_rva": target,
            "target_section": sec["name"] if sec else None,
            "text": text,
        })
    return out


def exec_ptrs_near(pe, file_off: int, strings):
    rows = []
    for delta in range(-0x40, 0x49, 8):
        qoff = file_off + delta
        if qoff < 0 or qoff + 8 > len(pe.data):
            continue
        value = struct.unpack_from("<Q", pe.data, qoff)[0]
        if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
            rva = value - IMAGE_BASE
            sec = pe.section_for_rva(rva)
            rows.append({
                "delta": delta,
                "entry_rva": pe.file_to_rva(qoff),
                "target_rva": rva,
                "target_section": sec["name"] if sec else None,
                "target_executable": bool(sec and sec["exec"]),
                "target_text": strings.get(rva),
            })
    return rows


def trace_candidate(pe, entry: int, strings):
    begin, end, blob, boundary = bounded_region(pe, entry)
    refs = rip_refs_in_region(pe, begin, blob, strings)
    interesting_strings = [
        r for r in refs
        if r.get("text") and any(term in r["text"].lower() for term in INTERESTING)
    ]
    return {
        "entry": entry,
        "begin": begin,
        "end": end,
        "size": end - begin,
        "boundary": boundary,
        "direct_callers": direct_callers(pe, entry),
        "outgoing": outgoing(pe, begin, blob),
        "rip_refs": refs,
        "interesting_string_refs": interesting_strings,
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
    string_hits = sorted(rva for rva, text in strings.items() if text == "CanPickle")
    if not string_hits:
        raise RuntimeError("exact CanPickle string not found")

    code_refs = []
    pointer_rows = []
    candidates = set()

    for srva in string_hits:
        for row in code_rip_refs(pe, srva):
            row = dict(row)
            row["string_rva"] = srva
            code_refs.append(row)
            if row.get("function_begin") is not None:
                candidates.add(row["function_begin"])

        for occ in qword_pointer_occurrences(pe, srva):
            near = exec_ptrs_near(pe, occ["file_offset"], strings)
            pointer_rows.append({
                "string_rva": srva,
                "pointer_rva": occ["rva"],
                "pointer_section": occ["section"],
                "near_image_pointers": near,
            })
            for p in near:
                if p["target_executable"] and p["delta"] != 0:
                    candidates.add(p["target_rva"])

    # Also include functions containing direct references to the pointer-table
    # neighbourhood, because some binding systems reference a descriptor rather
    # than the string itself.
    for prow in pointer_rows:
        prva = prow["pointer_rva"]
        for delta in range(-0x20, 0x21, 8):
            target = prva + delta
            for ref in code_rip_refs(pe, target):
                if ref.get("function_begin") is not None:
                    candidates.add(ref["function_begin"])

    traces = {f"0x{entry:X}": trace_candidate(pe, entry, strings) for entry in sorted(candidates)}

    known_intersections = []
    for key, tr in traces.items():
        for edge in tr["outgoing"]:
            if edge.get("known_target"):
                known_intersections.append({
                    "candidate": key,
                    "site": edge["site"],
                    "target": edge["dest"],
                    "known_target": edge["known_target"],
                })

    conclusion = "CANPICKLE_BINDING_CANDIDATES_FOUND" if traces else "CANPICKLE_BINDING_NOT_RESOLVED"
    result = {
        "schema": 1,
        "analysis": "engine_canpickle_binding_trace",
        "gow_exe_sha256": digest,
        "canpickle_string_rvas": string_hits,
        "code_refs": code_refs,
        "pointer_table_refs": pointer_rows,
        "candidate_count": len(traces),
        "candidates": traces,
        "known_gameobject_intersections": known_intersections,
        "conclusion": conclusion,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_txt = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - engine.CanPickle native binding trace",
        f"gow_exe_sha256={digest}",
        "canpickle_string_rvas=" + ",".join(f"0x{x:X}" for x in string_hits),
        f"direct_code_refs={len(code_refs)}",
        f"pointer_table_occurrences={len(pointer_rows)}",
        f"candidate_count={len(traces)}",
        f"known_gameobject_intersections={len(known_intersections)}",
        f"conclusion={conclusion}",
        "",
        "DIRECT CODE REFS",
    ]
    for r in code_refs:
        lines.append(
            f"  site=0x{r['site']:X} opcode={r['opcode']} fn=" +
            (f"0x{r['function_begin']:X}-0x{r['function_end']:X}" if r.get('function_begin') is not None else "none")
        )
    if not code_refs:
        lines.append("  (none)")

    lines.extend(["", "POINTER TABLE OCCURRENCES"])
    for p in pointer_rows:
        lines.append(f"  pointer=0x{p['pointer_rva']:X} section={p['pointer_section']}")
        for q in p["near_image_pointers"]:
            lines.append(
                f"    delta={q['delta']:+#x} target=0x{q['target_rva']:X} "
                f"section={q['target_section']} exec={q['target_executable']} text={q.get('target_text')!r}"
            )
    if not pointer_rows:
        lines.append("  (none)")

    lines.extend(["", "CANDIDATES"])
    for key, tr in traces.items():
        lines.append(
            f"  {key} range=0x{tr['begin']:X}-0x{tr['end']:X} size={tr['size']} boundary={tr['boundary']} "
            f"callers={len(tr['direct_callers'])} outgoing={len(tr['outgoing'])} strings={len(tr['interesting_string_refs'])}"
        )
        for s in tr["interesting_string_refs"]:
            lines.append(f"    string site=0x{s['site']:X} target=0x{s['target_rva']:X} text={s['text']!r}")
        for e in tr["outgoing"]:
            known = e.get("known_target")
            suffix = f" known={known}" if known else ""
            lines.append(f"    {e['kind'].upper()} site=0x{e['site']:X} -> 0x{e['dest']:X}{suffix}")

    lines.extend(["", "KNOWN GAMEOBJECT INTERSECTIONS"])
    if not known_intersections:
        lines.append("  (none)")
    for x in known_intersections:
        lines.append(
            f"  candidate={x['candidate']} site=0x{x['site']:X} -> 0x{x['target']:X} ({x['known_target']})"
        )

    lines.extend([
        "",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("ENGINE_CANPICKLE_BINDING_TRACE_PASSED")
    print(f"conclusion={conclusion}")
    print(f"candidate_count={len(traces)} known_gameobject_intersections={len(known_intersections)}")


if __name__ == "__main__":
    main()
