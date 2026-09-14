"""Trace the logical control flow behind engine.CanPickle beyond pdata splits.

Read-only, version-locked static analysis of the supported GoW.exe. The exact
engine.CanPickle Lua binding is proven at RVA 0x5AA350, but its pdata function
ends immediately after a RIP-relative LEA and the handler also jumps into a
shared tail at 0x5AA459. This tracer inspects a bounded contiguous window across
those function boundaries, resolves direct branches and RIP-relative data
references, and describes referenced data/pointers/strings.

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
START = 0x5AA350
END = 0x5AA560
INTERESTING_TARGETS = {0x5AA350: "CanPickle", 0x5AA3B3: "CanPickle_fallthrough", 0x5AA459: "CanPickle_false/shared_tail"}


def load_base():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pickle_bridge_base", path)
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


def read_rva(pe, rva: int, size: int) -> bytes:
    off = pe.rva_to_file(rva)
    if off is None:
        return b""
    return pe.data[off:off + size]


def describe_target(pe, rva: int, strings: dict[int, str]):
    sec = pe.section_for_rva(rva)
    row = {
        "rva": rva,
        "section": sec["name"] if sec else None,
        "executable": bool(sec and sec["exec"]),
        "string": strings.get(rva),
        "bytes32": read_rva(pe, rva, 32).hex(),
        "qwords": [],
    }
    raw = read_rva(pe, rva, 64)
    for i in range(0, min(len(raw), 64) - 7, 8):
        value = struct.unpack_from("<Q", raw, i)[0]
        q = {"delta": i, "value": value}
        if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
            trva = value - IMAGE_BASE
            tsec = pe.section_for_rva(trva)
            q.update({
                "image_rva": trva,
                "image_section": tsec["name"] if tsec else None,
                "image_string": strings.get(trva),
                "image_exec": bool(tsec and tsec["exec"]),
            })
        row["qwords"].append(q)
    return row


def scan_region(pe, strings):
    blob = read_rva(pe, START, END - START)
    if len(blob) != END - START:
        raise RuntimeError("unable to map CanPickle control-flow region")

    branches = []
    rip_refs = []

    # rel32 CALL/JMP
    for i in range(0, len(blob) - 4):
        op = blob[i]
        if op not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", blob, i + 1)[0]
        site = START + i
        dest = site + 5 + disp
        if 0 <= dest < pe.size_of_image:
            fn = pe.function_for(dest)
            branches.append({
                "kind": "call" if op == 0xE8 else "jmp",
                "site": site,
                "dest": dest,
                "label": INTERESTING_TARGETS.get(dest),
                "target_function_begin": fn["begin"] if fn else None,
                "target_function_end": fn["end"] if fn else None,
            })

    # short JMP and Jcc for local logical structure
    for i in range(0, len(blob) - 1):
        op = blob[i]
        site = START + i
        if op == 0xEB:
            disp = struct.unpack_from("<b", blob, i + 1)[0]
            branches.append({"kind": "jmp8", "site": site, "dest": site + 2 + disp, "label": INTERESTING_TARGETS.get(site + 2 + disp)})
        elif 0x70 <= op <= 0x7F:
            disp = struct.unpack_from("<b", blob, i + 1)[0]
            branches.append({"kind": f"jcc8_{op:02X}", "site": site, "dest": site + 2 + disp, "label": INTERESTING_TARGETS.get(site + 2 + disp)})

    # Common RIP-relative LEA/MOV: optional REX, opcode, modrm(r/m=101), disp32.
    for i in range(0, len(blob) - 6):
        rex_len = 1 if 0x40 <= blob[i] <= 0x4F else 0
        j = i + rex_len
        if j + 5 >= len(blob):
            continue
        op = blob[j]
        modrm = blob[j + 1]
        if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", blob, j + 2)[0]
        insn_len = rex_len + 6
        site = START + i
        target = site + insn_len + disp
        if not (0 <= target < pe.size_of_image):
            continue
        rip_refs.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target": target,
            "target_description": describe_target(pe, target, strings),
        })

    boundaries = []
    for fn in pe.runtime_functions:
        if fn["begin"] < END and fn["end"] > START:
            boundaries.append({"begin": fn["begin"], "end": fn["end"], "size": fn["end"] - fn["begin"]})

    entry_descriptions = {}
    for rva, label in INTERESTING_TARGETS.items():
        entry_descriptions[label] = describe_target(pe, rva, strings)

    return {
        "region_start": START,
        "region_end": END,
        "region_hex": blob.hex(),
        "pdata_boundaries": boundaries,
        "branches": sorted(branches, key=lambda x: (x["site"], x["kind"])),
        "rip_refs": sorted(rip_refs, key=lambda x: x["site"]),
        "entry_descriptions": entry_descriptions,
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
    trace = scan_region(pe, strings)

    result = {
        "schema": 1,
        "analysis": "engine_canpickle_logical_control_flow",
        "gow_exe_sha256": digest,
        "trace": trace,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_txt = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - engine.CanPickle logical control-flow trace",
        f"gow_exe_sha256={digest}",
        f"region=0x{START:X}-0x{END:X}",
        "",
        "PDATA BOUNDARIES",
    ]
    for fn in trace["pdata_boundaries"]:
        lines.append(f"  0x{fn['begin']:X}-0x{fn['end']:X} size={fn['size']}")

    lines.extend(["", "BRANCHES"])
    for b in trace["branches"]:
        suffix = f" label={b['label']}" if b.get("label") else ""
        lines.append(f"  {b['kind']} site=0x{b['site']:X} -> 0x{b['dest']:X}{suffix}")

    lines.extend(["", "RIP REFERENCES"])
    for r in trace["rip_refs"]:
        d = r["target_description"]
        lines.append(
            f"  {r['opcode']} site=0x{r['site']:X} -> 0x{r['target']:X} "
            f"section={d['section']} exec={d['executable']} string={d.get('string')!r}"
        )
        for q in d["qwords"]:
            if "image_rva" in q:
                lines.append(
                    f"    qword+0x{q['delta']:X} -> 0x{q['image_rva']:X} section={q.get('image_section')} "
                    f"exec={q.get('image_exec')} string={q.get('image_string')!r}"
                )

    lines.extend(["", "ENTRY DESCRIPTIONS"])
    for label, d in trace["entry_descriptions"].items():
        lines.append(f"  {label}: rva=0x{d['rva']:X} section={d['section']} string={d.get('string')!r} bytes32={d['bytes32']}")

    lines.extend([
        "",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("ENGINE_CANPICKLE_CONTROL_FLOW_TRACE_PASSED")
    print(f"branches={len(trace['branches'])} rip_refs={len(trace['rip_refs'])} pdata={len(trace['pdata_boundaries'])}")


if __name__ == "__main__":
    main()
