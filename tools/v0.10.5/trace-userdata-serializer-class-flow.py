"""Trace the proven Lua-userdata persistence class flow at GoW.exe RVA 0x7E9190.

Checkpoint/pickle research has proven that this serializer handles Lua userdata,
recovers a code-side Lua class, walks parent classes, and invokes the first
non-null persistence callback stored at class +0xB8.  This version-locked,
read-only scanner stays on that proven path and archives enough local machine
code structure to identify the exact class lookup and +0xB8 callback flow.

It does not launch the game and does not open or write save files.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TARGET = 0x7E9190
KNOWN = {
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
    "gameobject_token_resolver": 0x4EF0B0,
    "userdata_serializer": TARGET,
    "canpickle": 0x5AA350,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
}
REGS = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi",
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


def context(blob: bytes, i: int, before=48, after=80) -> str:
    return blob[max(0, i-before):min(len(blob), i+after)].hex()


def direct_edges(pe, begin: int, blob: bytes):
    rev = {v: k for k, v in KNOWN.items()}
    out = []
    n = len(blob)
    for i in range(max(0, n - 4)):
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


def branch_edges(begin: int, blob: bytes):
    """Collect relative conditional branches; backedges are especially useful for parent walks."""
    out = []
    n = len(blob)
    for i in range(n):
        op = blob[i]
        if 0x70 <= op <= 0x7F and i + 1 < n:
            disp = struct.unpack_from("<b", blob, i + 1)[0]
            dest = begin + i + 2 + disp
            out.append({"site": begin+i, "dest": dest, "size": 2, "backedge": dest < begin+i})
        elif op == 0x0F and i + 5 < n and 0x80 <= blob[i+1] <= 0x8F:
            disp = struct.unpack_from("<i", blob, i + 2)[0]
            dest = begin + i + 6 + disp
            out.append({"site": begin+i, "dest": dest, "size": 6, "backedge": dest < begin+i})
    return out


def decode_mem_operand(blob: bytes, i: int, opcode_offset: int, modrm_offset: int):
    """Decode enough ModRM/SIB state to report base register and displacement.

    This is intentionally conservative: no claim is made about semantic object type.
    """
    n = len(blob)
    if modrm_offset >= n:
        return None
    rex = None
    if opcode_offset > i and 0x40 <= blob[i] <= 0x4F:
        rex = blob[i]
    modrm = blob[modrm_offset]
    mod = (modrm >> 6) & 3
    rm = modrm & 7
    if mod == 3:
        return {"mod": mod, "register_direct": True, "modrm": modrm, "rex": rex}
    rex_b = (rex & 1) if rex is not None else 0
    p = modrm_offset + 1
    base_index = rm | (rex_b << 3)
    sib = None
    if rm == 4:
        if p >= n:
            return None
        sib = blob[p]
        p += 1
        base = sib & 7
        base_index = base | (rex_b << 3)
    disp = 0
    disp_size = 0
    rip_relative = False
    if mod == 0:
        no_base = (rm == 5) if sib is None else ((sib & 7) == 5)
        if no_base:
            if p + 4 > n:
                return None
            disp = struct.unpack_from("<i", blob, p)[0]
            disp_size = 4
            if sib is None:
                rip_relative = True
            base_name = None
        else:
            base_name = REGS[base_index]
    elif mod == 1:
        if p >= n:
            return None
        disp = struct.unpack_from("<b", blob, p)[0]
        disp_size = 1
        base_name = REGS[base_index]
    else:
        if p + 4 > n:
            return None
        disp = struct.unpack_from("<i", blob, p)[0]
        disp_size = 4
        base_name = REGS[base_index]
    return {
        "mod": mod,
        "register_direct": False,
        "modrm": modrm,
        "rex": rex,
        "sib": sib,
        "base": base_name,
        "disp": disp,
        "disp_size": disp_size,
        "rip_relative": rip_relative,
    }


def memory_accesses(begin: int, blob: bytes):
    """Find common MOV/LEA/CMP memory forms and all exact +0xB8 accesses."""
    out = []
    n = len(blob)
    i = 0
    while i < n - 2:
        start = i
        rex = None
        if 0x40 <= blob[i] <= 0x4F:
            rex = blob[i]
            i += 1
        if i >= n:
            break
        op = blob[i]
        if op in (0x8B, 0x89, 0x8D, 0x39, 0x3B, 0x85, 0x83, 0x81, 0xC7):
            mem = decode_mem_operand(blob, start, i, i+1)
            if mem and not mem.get("register_direct"):
                disp = mem.get("disp")
                # Preserve compact structural offsets, plus every exact +0xB8 access.
                if disp == 0xB8 or (isinstance(disp, int) and -0x100 <= disp <= 0x200):
                    out.append({
                        "site": begin + start,
                        "opcode": op,
                        "base": mem.get("base"),
                        "disp": disp,
                        "rip_relative": mem.get("rip_relative"),
                        "exact_b8": disp == 0xB8,
                        "context_hex": context(blob, start),
                    })
        i = start + 1
    return out


def indirect_calls(begin: int, blob: bytes):
    out = []
    n = len(blob)
    for i in range(n - 1):
        start = i
        p = i
        rex = None
        if 0x40 <= blob[p] <= 0x4F:
            rex = blob[p]
            p += 1
            if p >= n - 1:
                continue
        if blob[p] != 0xFF:
            continue
        modrm = blob[p+1]
        if ((modrm >> 3) & 7) != 2:  # CALL r/m64
            continue
        mem = decode_mem_operand(blob, start, p, p+1)
        row = {
            "site": begin + start,
            "rex": rex,
            "modrm": modrm,
            "context_hex": context(blob, start),
        }
        if mem:
            row.update({
                "register_direct": mem.get("register_direct"),
                "base": mem.get("base"),
                "disp": mem.get("disp"),
                "exact_b8": mem.get("disp") == 0xB8,
            })
        out.append(row)
    return out


def tag7_candidates(begin: int, blob: bytes):
    out = []
    n = len(blob)
    for i in range(n - 3):
        # cmp r/m32, imm8: 83 /7 ib
        p = i
        if 0x40 <= blob[p] <= 0x4F:
            p += 1
        if p + 2 < n and blob[p] == 0x83:
            modrm = blob[p+1]
            if ((modrm >> 3) & 7) == 7 and blob[p+2] == 7:
                out.append({"site": begin+i, "form": "cmp_rm_imm8_7", "context_hex": context(blob, i, 24, 40)})
        # cmp eax, 7
        if i + 4 < n and blob[i] == 0x3D and blob[i+1:i+5] == b"\x07\x00\x00\x00":
            out.append({"site": begin+i, "form": "cmp_eax_7", "context_hex": context(blob, i, 24, 40)})
    return out


def callers(pe, target: int):
    out = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        raw = sec["raw"]
        end = min(len(pe.data), raw + sec["rawsize"])
        data = pe.data
        for off in range(raw, max(raw, end - 4)):
            if data[off] != 0xE8:
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", data, off+1)[0]
            if site + 5 + disp != target:
                continue
            fn = pe.function_for(site)
            out.append({"site": site, "function_begin": fn["begin"] if fn else None, "function_end": fn["end"] if fn else None})
    return out


def trace_fn(pe, entry: int):
    fn = pe.function_for(entry)
    if fn is None:
        return None
    blob = pe.bytes_for(fn)
    mem = memory_accesses(fn["begin"], blob)
    ind = indirect_calls(fn["begin"], blob)
    branches = branch_edges(fn["begin"], blob)
    b8 = [x for x in mem if x["exact_b8"]]
    callback_candidates = []
    for access in b8:
        near = [c for c in ind if access["site"] <= c["site"] <= access["site"] + 0x50]
        callback_candidates.append({"b8_access": access, "nearby_indirect_calls": near})
    return {
        "entry": entry,
        "begin": fn["begin"],
        "end": fn["end"],
        "size": fn["end"] - fn["begin"],
        "hex": blob.hex(),
        "direct_edges": direct_edges(pe, fn["begin"], blob),
        "indirect_calls": ind,
        "memory_accesses": mem,
        "b8_accesses": b8,
        "branches": branches,
        "backedges": [b for b in branches if b["backedge"]],
        "tag7_candidates": tag7_candidates(fn["begin"], blob),
        "callback_candidates": callback_candidates,
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
    target = trace_fn(pe, TARGET)
    if target is None:
        raise RuntimeError("userdata serializer has no runtime-function record")
    if not (target["begin"] <= TARGET < target["end"]):
        raise RuntimeError("serializer RVA escaped resolved function")

    one_hop = {}
    for edge in target["direct_edges"]:
        if edge["kind"] != "call":
            continue
        fb = edge.get("target_function_begin")
        if fb is None:
            continue
        key = f"0x{fb:X}"
        if key not in one_hop:
            one_hop[key] = trace_fn(pe, fb)

    ranked_helpers = []
    for key, tr in one_hop.items():
        if not tr:
            continue
        score = (40 * len(tr["b8_accesses"]) + 8 * len(tr["indirect_calls"]) +
                 5 * len(tr["backedges"]) + 3 * len(tr["tag7_candidates"]))
        ranked_helpers.append({
            "function": key,
            "score": score,
            "b8": len(tr["b8_accesses"]),
            "indirect": len(tr["indirect_calls"]),
            "backedges": len(tr["backedges"]),
            "tag7": len(tr["tag7_candidates"]),
        })
    ranked_helpers.sort(key=lambda x: (-x["score"], x["function"]))

    displacement_histogram = Counter(
        x["disp"] for x in target["memory_accesses"]
        if isinstance(x.get("disp"), int) and not x.get("rip_relative")
    )
    result = {
        "schema": 1,
        "analysis": "userdata_serializer_class_flow",
        "gow_exe_sha256": digest,
        "serializer_rva": TARGET,
        "serializer": target,
        "direct_callers": callers(pe, TARGET),
        "one_hop_callees": one_hop,
        "ranked_helpers": ranked_helpers,
        "serializer_displacement_histogram": [
            {"disp": k, "count": v} for k, v in displacement_histogram.most_common()
        ],
        "conclusion": (
            "EXACT_B8_CALLBACK_SITE_VISIBLE" if any(c["nearby_indirect_calls"] for c in target["callback_candidates"])
            else "B8_ACCESS_VISIBLE_NEEDS_DATAFLOW" if target["b8_accesses"]
            else "NO_B8_ACCESS_DECODED_IN_SERIALIZER"
        ),
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_txt = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - userdata serializer class-flow trace",
        f"gow_exe_sha256={digest}",
        f"serializer=0x{target['begin']:X}-0x{target['end']:X}",
        f"conclusion={result['conclusion']}",
        "",
        "TAG-7 CANDIDATES",
    ]
    if not target["tag7_candidates"]:
        lines.append("  (none decoded)")
    for x in target["tag7_candidates"]:
        lines.append(f"  0x{x['site']:X} {x['form']} context={x['context_hex']}")

    lines += ["", "+0xB8 ACCESSES"]
    if not target["b8_accesses"]:
        lines.append("  (none decoded)")
    for x in target["b8_accesses"]:
        lines.append(f"  0x{x['site']:X} op=0x{x['opcode']:02X} base={x.get('base')} context={x['context_hex']}")

    lines += ["", "INDIRECT CALLS"]
    if not target["indirect_calls"]:
        lines.append("  (none decoded)")
    for x in target["indirect_calls"]:
        disp = x.get("disp")
        d = f" disp={disp:+#x}" if isinstance(disp, int) else ""
        lines.append(f"  0x{x['site']:X} base={x.get('base')}{d} exact_b8={x.get('exact_b8')} context={x['context_hex']}")

    lines += ["", "DIRECT CALLS"]
    for x in target["direct_edges"]:
        if x["kind"] == "call":
            known = f" {x['known']}" if x.get("known") else ""
            lines.append(f"  0x{x['site']:X} -> 0x{x['dest']:X}{known}")

    lines += ["", "BACKEDGES / LOOP CANDIDATES"]
    if not target["backedges"]:
        lines.append("  (none decoded)")
    for x in target["backedges"]:
        lines.append(f"  0x{x['site']:X} -> 0x{x['dest']:X}")

    lines += ["", "CALLBACK CORRELATION"]
    for x in target["callback_candidates"]:
        a = x["b8_access"]
        lines.append(f"  B8 0x{a['site']:X} base={a.get('base')}")
        for c in x["nearby_indirect_calls"]:
            lines.append(f"    nearby CALL 0x{c['site']:X} base={c.get('base')} disp={c.get('disp')}")

    lines += ["", "RANKED ONE-HOP HELPERS"]
    for x in ranked_helpers:
        lines.append(f"  {x['function']} score={x['score']} b8={x['b8']} indirect={x['indirect']} backedges={x['backedges']} tag7={x['tag7']}")

    lines += ["", "DIRECT CALLERS"]
    for x in result["direct_callers"]:
        fb = x.get("function_begin")
        lines.append(f"  site=0x{x['site']:X} function=" + (f"0x{fb:X}" if fb is not None else "unknown"))

    lines += ["", "MEMORY DISPLACEMENT HISTOGRAM"]
    for x in result["serializer_displacement_histogram"][:40]:
        lines.append(f"  {x['disp']:+#x}: {x['count']}")

    lines += [
        "",
        "NOTE: structural decoder results remain candidates until register dataflow is verified.",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ]
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("USERDATA_SERIALIZER_CLASS_FLOW_TRACE_PASSED")
    print(f"conclusion={result['conclusion']} b8={len(target['b8_accesses'])} indirect={len(target['indirect_calls'])} backedges={len(target['backedges'])} helpers={len(one_hop)}")


if __name__ == "__main__":
    main()
