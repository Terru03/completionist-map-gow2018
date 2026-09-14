"""Trace core.pickle's native Lua registration table and Pickle/Unpickle implementations.

Read-only, version-locked static analysis of the supported GoW.exe. The native
checkpoint bridge has proven that the engine resolves package.loaded['core.pickle']
and invokes its Pickle function. This tracer looks for Lua-style registration
records that pair the strings Pickle / Unpickle / CanPickle with executable
function pointers, then traces those candidate functions.

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
IMAGE_SCN_MEM_EXECUTE = 0x20000000
WANTED = ("core.pickle", "Pickle", "Unpickle", "CanPickle", "OnPickleInternal", "OnUnpickleInternal")
KNOWN = {
    "token_packer": 0x60B9C0,
    "token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "pickle_driver": 0x5AF8AD,
}


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


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def va_to_rva(pe, value: int):
    if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
        return value - IMAGE_BASE
    return None


def pointer_occurrences(pe, target_rva: int):
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
            out.append({"rva": rva, "file_offset": off, "section": sec["name"] if sec else None})
        pos = off + 1
    return out


def rip_refs_to_range(pe, begin: int, end: int):
    out = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start = sec["raw"]
        stop = min(len(pe.data), start + sec["rawsize"])
        d = pe.data
        for off in range(start, stop - 7):
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
            if begin <= target < end:
                fn = pe.function_for(site)
                out.append({
                    "site": site,
                    "opcode": "mov" if op == 0x8B else "lea",
                    "target_rva": target,
                    "function_begin": fn["begin"] if fn else None,
                    "function_end": fn["end"] if fn else None,
                })
    return out


def direct_callers(pe, target: int):
    out = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start = sec["raw"]
        stop = min(len(pe.data), start + sec["rawsize"])
        for off in range(start, stop - 4):
            op = pe.data[off]
            if op not in (0xE8, 0xE9):
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", pe.data, off + 1)[0]
            if site + 5 + disp != target:
                continue
            fn = pe.function_for(site)
            out.append({
                "kind": "call" if op == 0xE8 else "jmp",
                "site": site,
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def bounded_bytes(pe, entry: int, size: int = 0x200):
    fn = pe.function_for(entry)
    if fn is not None:
        begin, end = fn["begin"], fn["end"]
        blob = pe.bytes_for(fn)
        synthetic = False
    else:
        begin, end = entry, min(pe.size_of_image, entry + size)
        off = pe.rva_to_file(begin)
        blob = b"" if off is None else pe.data[off:off + (end - begin)]
        synthetic = True
    return begin, end, blob, synthetic


def outgoing_rel32(pe, begin: int, blob: bytes):
    out = []
    known_rev = {v: k for k, v in KNOWN.items()}
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
            "known_target": known_rev.get(dest),
            "target_function_begin": tf["begin"] if tf else None,
        })
    return out


def describe_qword(pe, value: int, strings_by_rva):
    rva = va_to_rva(pe, value)
    if rva is None:
        return {"value": value, "kind": "scalar"}
    sec = pe.section_for_rva(rva)
    text = strings_by_rva.get(rva)
    return {
        "value": value,
        "kind": "image_ptr",
        "rva": rva,
        "section": sec["name"] if sec else None,
        "text": text,
        "executable": bool(sec and sec["exec"]),
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
    digest = file_sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {digest}")

    base = load_base()
    pe = base.PE(exe.read_bytes())
    all_strings = base.ascii_map(pe)
    wanted_rvas = {}
    for name in WANTED:
        hits = [rva for rva, text in all_strings.items() if text == name]
        wanted_rvas[name] = hits

    occurrences = {}
    registrations = []
    candidate_entries = set()

    for name, rvas in wanted_rvas.items():
        rows = []
        for srva in rvas:
            for p in pointer_occurrences(pe, srva):
                off = p["file_offset"]
                qwords = []
                for delta in range(-0x30, 0x39, 8):
                    qoff = off + delta
                    if qoff < 0 or qoff + 8 > len(pe.data):
                        continue
                    value = struct.unpack_from("<Q", pe.data, qoff)[0]
                    desc = describe_qword(pe, value, all_strings)
                    desc["delta"] = delta
                    desc["entry_rva"] = pe.file_to_rva(qoff)
                    qwords.append(desc)
                    if delta != 0 and desc.get("executable"):
                        candidate_entries.add(desc["rva"])
                        registrations.append({
                            "name": name,
                            "string_rva": srva,
                            "name_pointer_rva": p["rva"],
                            "function_pointer_delta": delta,
                            "function_rva": desc["rva"],
                            "function_section": desc.get("section"),
                        })
                refs = rip_refs_to_range(pe, max(0, p["rva"] - 0x40), p["rva"] + 0x48)
                rows.append({
                    "string_rva": srva,
                    "pointer_rva": p["rva"],
                    "section": p["section"],
                    "qwords": qwords,
                    "near_table_code_refs": refs,
                })
        occurrences[name] = rows

    # De-duplicate registration hypotheses.
    uniq = {}
    for r in registrations:
        key = (r["name"], r["name_pointer_rva"], r["function_rva"])
        uniq[key] = r
    registrations = sorted(uniq.values(), key=lambda r: (r["name"], r["name_pointer_rva"], r["function_rva"]))

    traces = {}
    for entry in sorted(candidate_entries):
        begin, end, blob, synthetic = bounded_bytes(pe, entry)
        traces[f"0x{entry:X}"] = {
            "entry": entry,
            "function_begin": begin,
            "function_end": end,
            "synthetic_leaf_window": synthetic,
            "direct_callers": direct_callers(pe, entry),
            "outgoing_rel32": outgoing_rel32(pe, begin, blob),
            "function_hex": blob[:0x400].hex(),
        }

    result = {
        "schema": 1,
        "analysis": "core_pickle_registration_trace",
        "exe_sha256": digest,
        "wanted_string_rvas": wanted_rvas,
        "pointer_occurrences": occurrences,
        "registration_candidates": registrations,
        "candidate_function_traces": traces,
    }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - core.pickle registration trace",
        f"exe_sha256={digest}",
        "",
        "STRINGS",
    ]
    for name in WANTED:
        vals = wanted_rvas[name]
        lines.append(f"  {name}: " + (", ".join(f"0x{x:X}" for x in vals) if vals else "NOT_FOUND"))

    lines.extend(["", "REGISTRATION CANDIDATES"])
    for r in registrations:
        lines.append(
            f"  {r['name']} namePtr=0x{r['name_pointer_rva']:X} delta={r['function_pointer_delta']:+#x} "
            f"func=0x{r['function_rva']:X} section={r['function_section']}"
        )

    lines.extend(["", "POINTER TABLES"])
    for name, rows in occurrences.items():
        lines.append(f"  {name}: pointer_occurrences={len(rows)}")
        for row in rows:
            lines.append(f"    PTR 0x{row['pointer_rva']:X} section={row['section']} refs={len(row['near_table_code_refs'])}")
            for q in row["qwords"]:
                if q["kind"] == "image_ptr":
                    extra = f" text={q['text']}" if q.get("text") else ""
                    lines.append(
                        f"      {q['delta']:+#x}: RVA=0x{q['rva']:X} section={q['section']} exec={q['executable']}{extra}"
                    )
            for ref in row["near_table_code_refs"]:
                fb = "none" if ref["function_begin"] is None else f"0x{ref['function_begin']:X}"
                lines.append(f"      CODE {ref['opcode'].upper()} site=0x{ref['site']:X} -> 0x{ref['target_rva']:X} fn={fb}")

    lines.extend(["", "CANDIDATE FUNCTIONS"])
    for key, row in traces.items():
        lines.append(
            f"  {key} fn=0x{row['function_begin']:X}-0x{row['function_end']:X} "
            f"synthetic={row['synthetic_leaf_window']} callers={len(row['direct_callers'])} outgoing={len(row['outgoing_rel32'])}"
        )
        for e in row["outgoing_rel32"]:
            known = "" if e["known_target"] is None else f" known={e['known_target']}"
            tf = "none" if e["target_function_begin"] is None else f"0x{e['target_function_begin']:X}"
            lines.append(f"    {e['kind'].upper()} site=0x{e['site']:X} -> 0x{e['dest']:X} targetFn={tf}{known}")
        lines.append(f"    HEX {row['function_hex']}")

    lines.extend([
        "",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("CORE_PICKLE_REGISTRATION_TRACE_PASSED")


if __name__ == "__main__":
    main()
