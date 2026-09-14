"""Trace internal Lua TValue type-tag dispatch in the checkpoint serializer.

The previous pass proved that 0x7E7F10 is the real table->byte-buffer checkpoint
serializer and that 0x7E88F0 checks lua_type()==5 (table). GameObject userdata is
therefore expected to be handled through the engine/Lua internal TValue tag rather
than an obvious lua_type()==7 call.

This scanner is read-only and version locked. It searches the serializer family
for the common Lua 5.1-style internal tag pattern (type & 0x0F) and nearby tests
for tag 7, while also recording direct calls, strings, and proven GameObject
helper intersections. It does not launch the game or open saves.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"

SEEDS = {
    "serializer": 0x7E7F10,
    "write_graph": 0x7E83D0,
    "build_root_record": 0x7E8540,
    "scan_strings_a": 0x7E8760,
    "scan_strings_b": 0x7E88F0,
    "scan_strings_c": 0x7E8B70,
    "table_ref_context": 0x7E8D90,
    "table_ref_helper": 0x7E8F80,
    "helper_7E9190": 0x7E9190,
    "helper_7E9340": 0x7E9340,
    "indirect_heavy_9C9CC0": 0x9C9CC0,
    "indirect_9F3EA0": 0x9F3EA0,
    "indirect_9F3BB0": 0x9F3BB0,
    "helper_B3E90": 0x0B3E90,
}

KNOWN = {
    "lua_type": 0x9E4900,
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
    "gameobject_token_resolver": 0x4EF0B0,
    "canpickle": 0x5AA350,
    "checkpoint_pickle_driver": 0x5AF8AD,
}

INTERESTING_TERMS = (
    "tableref", "userdata", "gameobject", "pickle", "serialize", "class",
    "reference", "object", "level", "wad", "refnode",
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


def bounded(pe, entry: int, fallback: int = 0x500):
    fn = pe.function_for(entry)
    if fn is not None:
        return fn["begin"], fn["end"], pe.bytes_for(fn), "pdata"
    off = pe.rva_to_file(entry)
    if off is None:
        return entry, entry, b"", "unmapped"
    end = min(pe.size_of_image, entry + fallback)
    return entry, end, pe.data[off:off + end - entry], "bounded-leaf"


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
            "context_hex": blob[max(0, i-24):min(len(blob), i+40)].hex(),
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
        text = strings.get(target)
        out.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target": target,
            "section": sec["name"] if sec else None,
            "text": text,
        })
    return out


def internal_tag_sites(begin: int, blob: bytes):
    """Find conservative x86 patterns around Lua TValue low-nibble tag tests.

    Common engine code already observed in this binary includes:
      mov eax,[...+8] ; and eax,0x0f ; cmp al,5
    We record all AND-immediate-0x0f sites and inspect a 48-byte forward window
    for comparisons against tag 7. We also detect direct CMP imm8/imm32 7 and
    archive context without claiming semantics unless an AND 0x0f is nearby.
    """
    out = []
    n = len(blob)
    for i in range(n):
        and_len = None
        # 83 /4 r32, imm8  => 83 E0..E7 0F
        if i + 2 < n and blob[i] == 0x83 and (blob[i+1] & 0xF8) == 0xE0 and blob[i+2] == 0x0F:
            and_len = 3
        # 25 0F000000 => and eax,0x0f
        elif i + 4 < n and blob[i] == 0x25 and blob[i+1:i+5] == b"\x0f\x00\x00\x00":
            and_len = 5
        if and_len is None:
            continue

        lo = max(0, i - 32)
        hi = min(n, i + 64)
        window = blob[i:min(n, i+48)]
        tag7 = []
        tag_values = []
        for j in range(len(window)):
            # cmp al, imm8
            if j + 1 < len(window) and window[j] == 0x3C:
                imm = window[j+1]
                tag_values.append({"site": begin+i+j, "form": "cmp_al_imm8", "imm": imm})
                if imm == 7:
                    tag7.append(tag_values[-1])
            # cmp r/m32, imm8: 83 /7 xx
            if j + 2 < len(window) and window[j] == 0x83 and ((window[j+1] >> 3) & 7) == 7:
                imm = window[j+2]
                tag_values.append({"site": begin+i+j, "form": "cmp_rm32_imm8", "imm": imm})
                if imm == 7:
                    tag7.append(tag_values[-1])
            # cmp r/m8, imm8: 80 /7 xx
            if j + 2 < len(window) and window[j] == 0x80 and ((window[j+1] >> 3) & 7) == 7:
                imm = window[j+2]
                tag_values.append({"site": begin+i+j, "form": "cmp_rm8_imm8", "imm": imm})
                if imm == 7:
                    tag7.append(tag_values[-1])
        out.append({
            "and_site": begin + i,
            "context_hex": blob[lo:hi].hex(),
            "nearby_tag_compares": tag_values,
            "tag7_compares": tag7,
        })
    return out


def direct_cmp7_sites(begin: int, blob: bytes):
    out = []
    n = len(blob)
    for i in range(n):
        hit = None
        if i + 1 < n and blob[i] == 0x3C and blob[i+1] == 7:
            hit = "cmp_al_7"
        elif i + 2 < n and blob[i] in (0x80, 0x83) and ((blob[i+1] >> 3) & 7) == 7 and blob[i+2] == 7:
            hit = "cmp_rm_7"
        if hit:
            out.append({
                "site": begin + i,
                "form": hit,
                "context_hex": blob[max(0, i-40):min(n, i+56)].hex(),
            })
    return out


def trace(pe, entry: int, strings):
    begin, end, blob, boundary = bounded(pe, entry)
    refs = rip_refs(pe, begin, blob, strings)
    tags = internal_tag_sites(begin, blob)
    cmp7 = direct_cmp7_sites(begin, blob)
    return {
        "entry": entry,
        "begin": begin,
        "end": end,
        "size": end - begin,
        "boundary": boundary,
        "hex": blob.hex(),
        "direct_edges": direct_edges(pe, begin, blob),
        "indirect_calls": indirect_calls(begin, blob),
        "rip_refs": refs,
        "interesting_refs": [r for r in refs if r.get("text") and any(t in r["text"].lower() for t in INTERESTING_TERMS)],
        "internal_tag_sites": tags,
        "direct_cmp7_sites": cmp7,
        "tag7_near_mask_count": sum(len(x["tag7_compares"]) for x in tags),
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

    functions = {}
    queue = list(SEEDS.values())
    seen = set()
    depth = {x: 0 for x in queue}
    while queue and len(functions) < 120:
        entry = queue.pop(0)
        if entry in seen:
            continue
        seen.add(entry)
        tr = trace(pe, entry, strings)
        key = f"0x{tr['begin']:X}"
        functions[key] = tr
        d = depth.get(entry, 0)
        if d >= 3:
            continue
        for edge in tr["direct_edges"]:
            if edge["kind"] != "call":
                continue
            fb = edge.get("target_function_begin")
            if fb is None or fb in seen:
                continue
            # Keep local serializer functions and anything with a proven known
            # target path. Broader third-party/runtime helpers are still seeded
            # explicitly above when already ranked by the previous scan.
            if 0x7E0000 <= fb <= 0x7F0000 or d < 1:
                queue.append(fb)
                depth.setdefault(fb, d + 1)

    tag7_candidates = []
    known_intersections = []
    ranked = []
    for key, tr in functions.items():
        for edge in tr["direct_edges"]:
            if edge.get("known"):
                known_intersections.append({"function": key, **edge})
        if tr["tag7_near_mask_count"] or tr["direct_cmp7_sites"]:
            tag7_candidates.append({
                "function": key,
                "range": [tr["begin"], tr["end"]],
                "tag7_near_mask_count": tr["tag7_near_mask_count"],
                "direct_cmp7_count": len(tr["direct_cmp7_sites"]),
                "internal_tag_sites": tr["internal_tag_sites"],
                "direct_cmp7_sites": tr["direct_cmp7_sites"],
            })
        score = tr["tag7_near_mask_count"] * 20 + len(tr["direct_cmp7_sites"]) * 5
        score += len(tr["interesting_refs"]) * 3 + len(tr["indirect_calls"])
        score += sum(10 for e in tr["direct_edges"] if e.get("known") in ("lua_gameobject_unbox", "gameobject_token_packer", "gameobject_token_resolver"))
        if score:
            ranked.append({
                "function": key,
                "score": score,
                "tag7_near_mask": tr["tag7_near_mask_count"],
                "direct_cmp7": len(tr["direct_cmp7_sites"]),
                "indirect": len(tr["indirect_calls"]),
                "strings": [r.get("text") for r in tr["interesting_refs"]],
                "known": [e.get("known") for e in tr["direct_edges"] if e.get("known")],
            })
    ranked.sort(key=lambda x: (-x["score"], x["function"]))

    result = {
        "schema": 1,
        "analysis": "lua_state_serializer_internal_tags",
        "gow_exe_sha256": digest,
        "seeds": {k: f"0x{v:X}" for k, v in SEEDS.items()},
        "function_count": len(functions),
        "functions": functions,
        "tag7_candidates": tag7_candidates,
        "known_intersections": known_intersections,
        "ranked": ranked,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - Lua-state serializer internal TValue tag trace",
        f"gow_exe_sha256={digest}",
        f"function_count={len(functions)}",
        "",
        "TAG-7 CANDIDATES",
    ]
    if not tag7_candidates:
        lines.append("  (none)")
    for row in tag7_candidates:
        lines.append(
            f"  {row['function']} range=0x{row['range'][0]:X}-0x{row['range'][1]:X} "
            f"near_mask={row['tag7_near_mask_count']} direct_cmp7={row['direct_cmp7_count']}"
        )
        for site in row["internal_tag_sites"]:
            if site["tag7_compares"]:
                lines.append(f"    AND_MASK site=0x{site['and_site']:X} context={site['context_hex']}")
                for cmp in site["tag7_compares"]:
                    lines.append(f"      TAG7 site=0x{cmp['site']:X} form={cmp['form']}")
        for site in row["direct_cmp7_sites"]:
            lines.append(f"    CMP7 site=0x{site['site']:X} form={site['form']} context={site['context_hex']}")

    lines.extend(["", "KNOWN INTERSECTIONS"])
    if not known_intersections:
        lines.append("  (none)")
    for row in known_intersections:
        lines.append(
            f"  {row['function']} site=0x{row['site']:X} -> 0x{row['dest']:X} known={row['known']}"
        )

    lines.extend(["", "RANKED"])
    for row in ranked[:30]:
        lines.append(
            f"  {row['function']} score={row['score']} tag7={row['tag7_near_mask']} "
            f"cmp7={row['direct_cmp7']} indirect={row['indirect']} strings={row['strings']} known={row['known']}"
        )

    lines.extend([
        "",
        "NOTE: tag-7 classification is structural only until the surrounding control flow is manually verified.",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("LUA_STATE_SERIALIZER_INTERNAL_TAG_TRACE_PASSED")
    print(f"functions={len(functions)} tag7_candidates={len(tag7_candidates)} known_intersections={len(known_intersections)}")


if __name__ == "__main__":
    main()
