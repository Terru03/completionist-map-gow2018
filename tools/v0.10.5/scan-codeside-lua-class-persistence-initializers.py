"""Find CodeSideLuaClass persistence-callback initializer candidates in GoW.exe.

The userdata serializer at RVA 0x7E9190 has now proven this class layout:
  +0x48 parent CodeSideLuaClass pointer
  +0xA4 asserted byte while walking the hierarchy
  +0xB8 first non-null persistence callback, invoked by the serializer

This read-only, version-locked pass scans executable code for writes to +0xB8,
groups them by function, and ranks candidates using the other proven offsets.
For register stores it also traces a short backwards window for RIP-relative LEA
or MOV instructions that may reveal the exact callback RVA assigned to +0xB8.
String references are only supporting evidence; a GameObject string xref alone
is NOT treated as registration evidence.

The tool does not launch the game and does not open or write save files.
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
PROVEN_OFFSETS = {0x48: "parent", 0xA4: "asserted_byte", 0xB8: "persistence_callback"}
INTERESTING_TERMS = (
    "gameobject", "codesideluaclass", "pickle", "unpickle", "serialize",
    "userdata", "class", "resolvegameobject", "onpickleinternal",
    "onunpickleinternal",
)
REG_NAMES = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi",
             "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]


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


def reg_name(index: int) -> str:
    return REG_NAMES[index & 0xF]


def context(blob: bytes, i: int, before=48, after=96) -> str:
    return blob[max(0, i-before):min(len(blob), i+after)].hex()


def read_disp32(blob: bytes, p: int):
    if p + 4 > len(blob):
        return None
    return struct.unpack_from("<i", blob, p)[0]


def parse_mem(blob: bytes, start: int, opcode_pos: int, modrm_pos: int):
    if modrm_pos >= len(blob):
        return None
    rex = blob[start] if opcode_pos > start and 0x40 <= blob[start] <= 0x4F else 0
    modrm = blob[modrm_pos]
    mod = (modrm >> 6) & 3
    rm = modrm & 7
    if mod == 3:
        return None
    p = modrm_pos + 1
    sib = None
    base = rm | ((rex & 1) << 3)
    if rm == 4:
        if p >= len(blob):
            return None
        sib = blob[p]
        p += 1
        base = (sib & 7) | ((rex & 1) << 3)
    rip_relative = False
    base_name = reg_name(base)
    if mod == 0:
        no_base = (rm == 5) if sib is None else ((sib & 7) == 5)
        if no_base:
            disp = read_disp32(blob, p)
            if disp is None:
                return None
            size = 4
            base_name = None
            rip_relative = sib is None
        else:
            disp = 0
            size = 0
    elif mod == 1:
        if p >= len(blob):
            return None
        disp = struct.unpack_from("<b", blob, p)[0]
        size = 1
    else:
        disp = read_disp32(blob, p)
        if disp is None:
            return None
        size = 4
    return {
        "rex": rex,
        "modrm": modrm,
        "mod": mod,
        "base": base_name,
        "disp": disp,
        "disp_size": size,
        "rip_relative": rip_relative,
        "operand_end": p + size,
    }


def decode_store(blob: bytes, i: int):
    """Decode MOV r/m,reg and MOV r/m,imm enough for exact +0xB8 stores."""
    p = i
    rex = 0
    if p < len(blob) and 0x40 <= blob[p] <= 0x4F:
        rex = blob[p]
        p += 1
    if p + 1 >= len(blob):
        return None
    op = blob[p]
    if op not in (0x89, 0xC7):
        return None
    mem = parse_mem(blob, i, p, p + 1)
    if not mem or mem["disp"] != 0xB8:
        return None
    modrm = mem["modrm"]
    if op == 0x89:
        src = ((modrm >> 3) & 7) | (((rex >> 2) & 1) << 3)
        return {
            "opcode": "mov_mem_reg",
            "base": mem["base"],
            "source_reg": reg_name(src),
            "source_reg_index": src,
            "end": mem["operand_end"],
        }
    if ((modrm >> 3) & 7) != 0:
        return None
    q = mem["operand_end"]
    if q + 4 > len(blob):
        return None
    imm = struct.unpack_from("<I", blob, q)[0]
    return {
        "opcode": "mov_mem_imm32",
        "base": mem["base"],
        "immediate": imm,
        "end": q + 4,
    }


def decode_access_at(blob: bytes, i: int):
    p = i
    if p < len(blob) and 0x40 <= blob[p] <= 0x4F:
        p += 1
    if p + 1 >= len(blob):
        return None
    op = blob[p]
    if op not in (0x8B, 0x89, 0x8D, 0x39, 0x3B, 0x80, 0x81, 0x83, 0xC6, 0xC7):
        return None
    mem = parse_mem(blob, i, p, p + 1)
    if not mem or mem["rip_relative"]:
        return None
    if mem["disp"] not in PROVEN_OFFSETS:
        return None
    return {
        "site_offset": i,
        "opcode": op,
        "base": mem["base"],
        "disp": mem["disp"],
        "field": PROVEN_OFFSETS[mem["disp"]],
    }


def preceding_source_candidates(pe, fn_begin: int, blob: bytes, store_i: int, source_reg_index: int):
    """Look backwards for a recent assignment to the register stored at +0xB8."""
    out = []
    lo = max(0, store_i - 0x80)
    for j in range(lo, store_i):
        p = j
        rex = 0
        if 0x40 <= blob[p] <= 0x4F:
            rex = blob[p]
            p += 1
            if p >= store_i:
                continue
        # LEA reg,[RIP+disp32] / MOV reg,[RIP+disp32]
        if p + 6 <= store_i and blob[p] in (0x8D, 0x8B):
            modrm = blob[p+1]
            if (modrm & 0xC7) == 0x05:
                dst = ((modrm >> 3) & 7) | (((rex >> 2) & 1) << 3)
                if dst == source_reg_index:
                    disp = struct.unpack_from("<i", blob, p+2)[0]
                    instr_len = (p - j) + 6
                    target = fn_begin + j + instr_len + disp
                    sec = pe.section_for_rva(target)
                    row = {
                        "site": fn_begin + j,
                        "kind": "lea_rip" if blob[p] == 0x8D else "mov_rip",
                        "target": target,
                        "target_section": sec["name"] if sec else None,
                        "target_executable": bool(sec and sec["exec"]),
                    }
                    if blob[p] == 0x8B:
                        off = pe.rva_to_file(target)
                        if off is not None and off + 8 <= len(pe.data):
                            value = struct.unpack_from("<Q", pe.data, off)[0]
                            if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
                                rv = value - IMAGE_BASE
                                s2 = pe.section_for_rva(rv)
                                row["deref_target"] = rv
                                row["deref_executable"] = bool(s2 and s2["exec"])
                    out.append(row)
        # MOV r64, imm64: REX.W + B8+r qword
        if rex & 8 and p < store_i and 0xB8 <= blob[p] <= 0xBF and p + 9 <= store_i:
            dst = (blob[p] - 0xB8) | ((rex & 1) << 3)
            if dst == source_reg_index:
                value = struct.unpack_from("<Q", blob, p+1)[0]
                row = {"site": fn_begin+j, "kind": "mov_imm64", "value": value}
                if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
                    rv = value - IMAGE_BASE
                    sec = pe.section_for_rva(rv)
                    row.update({"target": rv, "target_section": sec["name"] if sec else None,
                                "target_executable": bool(sec and sec["exec"])})
                out.append(row)
    out.sort(key=lambda x: x["site"], reverse=True)
    return out[:12]


def direct_edges(pe, begin: int, blob: bytes):
    out = []
    for i in range(max(0, len(blob) - 4)):
        if blob[i] not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", blob, i+1)[0]
        dest = begin + i + 5 + disp
        if not (0 <= dest < pe.size_of_image):
            continue
        fn = pe.function_for(dest)
        out.append({"kind": "call" if blob[i] == 0xE8 else "jmp", "site": begin+i,
                    "dest": dest, "target_function_begin": fn["begin"] if fn else None})
    return out


def rip_refs(pe, begin: int, blob: bytes, strings):
    out = []
    n = len(blob)
    for i in range(max(0, n - 7)):
        p = i
        if not (0x40 <= blob[p] <= 0x4F):
            continue
        op = blob[p+1]
        modrm = blob[p+2]
        if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", blob, p+3)[0]
        target = begin + i + 7 + disp
        text = strings.get(target)
        row = {"site": begin+i, "opcode": op, "target": target, "text": text}
        if text is not None:
            row["interesting"] = any(term in text.lower() for term in INTERESTING_TERMS)
            row["exact_gameobject"] = text == "GameObject"
        else:
            row["interesting"] = False
            row["exact_gameobject"] = False
        out.append(row)
    return out


def scan_function(pe, strings, fn):
    blob = pe.bytes_for(fn)
    accesses = []
    stores = []
    for i in range(len(blob)):
        a = decode_access_at(blob, i)
        if a:
            a["site"] = fn["begin"] + i
            accesses.append(a)
        s = decode_store(blob, i)
        if s:
            row = dict(s)
            row["site"] = fn["begin"] + i
            row["context_hex"] = context(blob, i)
            if s.get("source_reg_index") is not None:
                row["source_candidates"] = preceding_source_candidates(
                    pe, fn["begin"], blob, i, s["source_reg_index"])
            else:
                row["source_candidates"] = []
            stores.append(row)
    if not stores:
        return None
    refs = rip_refs(pe, fn["begin"], blob, strings)
    offsets = sorted({a["disp"] for a in accesses})
    exact_gameobject_refs = [r for r in refs if r["exact_gameobject"]]
    interesting_refs = [r for r in refs if r["interesting"]]
    exec_sources = []
    for s in stores:
        for src in s["source_candidates"]:
            if src.get("target_executable") or src.get("deref_executable"):
                exec_sources.append({"store_site": s["site"], **src})
    score = 50 * len(stores)
    if 0x48 in offsets:
        score += 25
    if 0xA4 in offsets:
        score += 25
    if 0x48 in offsets and 0xA4 in offsets:
        score += 30
    score += 18 * len(exec_sources)
    score += 15 * len(exact_gameobject_refs)
    score += min(20, 3 * len(interesting_refs))
    return {
        "begin": fn["begin"], "end": fn["end"], "size": fn["end"]-fn["begin"],
        "score": score, "proven_offset_accesses": accesses, "offsets": offsets,
        "b8_stores": stores, "executable_source_candidates": exec_sources,
        "exact_gameobject_refs": exact_gameobject_refs, "interesting_refs": interesting_refs,
        "direct_edges": direct_edges(pe, fn["begin"], blob),
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

    seen = set()
    candidates = []
    raw_store_sites = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        raw = sec["raw"]
        end = min(len(pe.data), raw + sec["rawsize"])
        for off in range(raw, end):
            rva = pe.file_to_rva(off)
            if rva is None:
                continue
            # cheap prefilter: optional REX followed by 89/C7; exact decoding follows
            b0 = pe.data[off]
            q = off + 1 if 0x40 <= b0 <= 0x4F else off
            if q >= end or pe.data[q] not in (0x89, 0xC7):
                continue
            fn = pe.function_for(rva)
            if fn is None:
                continue
            blob = pe.bytes_for(fn)
            rel = rva - fn["begin"]
            s = decode_store(blob, rel)
            if not s:
                continue
            raw_store_sites.append(rva)
            if fn["begin"] in seen:
                continue
            seen.add(fn["begin"])
            tr = scan_function(pe, strings, fn)
            if tr:
                candidates.append(tr)

    candidates.sort(key=lambda x: (-x["score"], x["begin"]))
    result = {
        "schema": 1,
        "analysis": "codeside_lua_class_persistence_initializers",
        "gow_exe_sha256": digest,
        "proven_layout": {"parent": "class+0x48", "asserted_byte": "class+0xA4",
                          "persistence_callback": "class+0xB8"},
        "raw_b8_store_site_count": len(set(raw_store_sites)),
        "candidate_function_count": len(candidates),
        "candidates": candidates,
        "conclusion": "B8_INITIALIZER_CANDIDATES_FOUND" if candidates else "NO_B8_INITIALIZER_CANDIDATES_FOUND",
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_txt = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - CodeSideLuaClass persistence initializer scan",
        f"gow_exe_sha256={digest}",
        "PROVEN class layout: parent=+0x48 asserted-byte=+0xA4 persistence-callback=+0xB8",
        f"raw_b8_store_sites={len(set(raw_store_sites))}",
        f"candidate_functions={len(candidates)}",
        f"conclusion={result['conclusion']}",
        "",
        "RANKED CANDIDATES",
    ]
    for idx, c in enumerate(candidates[:80], 1):
        lines.append(f"#{idx} fn=0x{c['begin']:X}-0x{c['end']:X} score={c['score']} offsets={[hex(x) for x in c['offsets']]} b8_stores={len(c['b8_stores'])} gameobject_refs={len(c['exact_gameobject_refs'])} exec_sources={len(c['executable_source_candidates'])}")
        for s in c["b8_stores"]:
            extra = f" src={s.get('source_reg')}" if s.get("source_reg") else f" imm={s.get('immediate')}"
            lines.append(f"  STORE 0x{s['site']:X} base={s.get('base')} {s['opcode']}{extra}")
            for src in s["source_candidates"][:5]:
                t = src.get("target")
                d = src.get("deref_target")
                parts = [f"    SOURCE 0x{src['site']:X} {src['kind']}"]
                if t is not None:
                    parts.append(f"target=0x{t:X} exec={src.get('target_executable')}")
                if d is not None:
                    parts.append(f"deref=0x{d:X} exec={src.get('deref_executable')}")
                lines.append(" ".join(parts))
        for r in c["exact_gameobject_refs"][:5]:
            lines.append(f"  GAMEOBJECT_REF 0x{r['site']:X} -> 0x{r['target']:X}")
        for r in c["interesting_refs"][:8]:
            if not r["exact_gameobject"]:
                lines.append(f"  STRING 0x{r['site']:X} -> {r.get('text')!r}")
    lines += [
        "",
        "NOTE: ranked rows are initializer CANDIDATES. A +0xB8 store is not by itself proof that the base object is a CodeSideLuaClass.",
        "NOTE: GameObject string references are supporting evidence only and are not treated as registration proof.",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ]
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("CODESIDE_LUA_CLASS_PERSISTENCE_INITIALIZER_SCAN_PASSED")
    print(f"b8_store_sites={len(set(raw_store_sites))} candidate_functions={len(candidates)}")
    if candidates:
        print(f"top_candidate=0x{candidates[0]['begin']:X} score={candidates[0]['score']}")


if __name__ == "__main__":
    main()
