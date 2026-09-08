"""Read-only WAD loader bookkeeping probe for Completionist Map v0.10.4.

Combines stock WAD accounting with a static x64 call/xref probe of the pinned
GoW.exe. It does not assert that ranked native functions are understood; those
are candidates for the next manual reverse-engineering pass.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
BASE = 0x140000000
EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_DCB = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
EXPECTED_MAPMASTER = "1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a"
EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
RIG_KEYS = {0x10001, 0x20001, 0x30001, 0x40001}
KNOWN_NATIVE = {
    0x951E40: "CreateMarkerIcon wrapper",
    0x903F40: "marker Icon hash/resource path",
    0x750920: "general resource lookup",
    0x423100: "resource resolve by name/hash",
    0x672A00: "GOPool Name/Cnt loop",
    0x60DD80: "pool add/capacity clone",
    0x60D8B0: "pool lookup by resource pointer",
    0x60EDA0: "pool checkout",
    0x673FE0: "GOPool incremental warmup",
    0x5B813D: "GOPool memory/work estimate",
}
CLONE_SOURCE_NAMES = [
    "TX_mapmarker_docklocation_emissive_FCC664130951154C",
    "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
    "MAT_0C599DC8DC7E2170",
    "MDL_mapicondock",
    "goProtoMapIconDock",
    "gomapicondock",
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def check(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def public_record(r: dict) -> dict:
    out = {
        "name": r["name"],
        "payload_index": r["payload_index"],
        "file_offset": None if r["original_offset"] is None else f"0x{r['original_offset']:X}",
        "kind": r["kind"],
        "flags": f"0x{r['flags']:X}",
        "bytes": len(r["data"]),
        "resource_id": r["id"].hex(),
    }
    if len(r["data"]) >= 4:
        out["first_dword"] = f"0x{struct.unpack_from('<I', r['data'])[0]:X}"
    return out


def payload_type_word(r: dict):
    if len(r["data"]) < 4:
        return None
    return struct.unpack_from("<I", r["data"])[0]


def payload_internal_name(r: dict):
    if r["flags"] != 0x3D or len(r["data"]) != 164:
        return None
    raw = bytes(r["data"])
    end = raw.find(b"\0", 0x1C, 0x54)
    if end < 0:
        raise ValueError(f"unterminated final-instance payload name: {r['name']}")
    return raw[0x1C:end].decode("ascii")


def type_word_counts(records: list[dict]) -> collections.Counter:
    return collections.Counter(payload_type_word(r) for r in records if r["data"] and len(r["data"]) >= 4)


def type_word_flags(records: list[dict]) -> dict[int, collections.Counter]:
    out: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in records:
        word = payload_type_word(r)
        if word is not None:
            out[word][r["flags"]] += 1
    return out


def accounting_evidence(logical, records: list[dict]) -> dict:
    payloads = logical.payload_records(records)
    check(len(payloads) >= 2, "WAD lacks accounting payloads")
    heap, root = payloads[0], payloads[1]
    table = logical.read_type_table(root["data"])
    counts = type_word_counts(records)
    flags = type_word_flags(records)
    root_total = struct.unpack_from("<I", root["data"], 0x1C)[0]
    heap_total = struct.unpack_from("<I", heap["data"], 4)[0]
    rows = []
    for row in table:
        key = row["key"]
        rows.append({
            "key": f"0x{key:X}",
            "base": row["base"],
            "count": row["count"],
            "global_payload_first_dword_count": counts[key],
            "count_matches_global_first_dword": counts[key] == row["count"],
            "header_flags_for_matching_payloads": {f"0x{k:X}": v for k, v in sorted(flags[key].items())},
        })
    rig_rows = [x for x in rows if int(x["key"], 16) in RIG_KEYS]
    return {
        "heap_record": public_record(heap),
        "root_record": public_record(root),
        "heap_total": heap_total,
        "root_total": root_total,
        "payload_count": len(payloads),
        "table_row_count": len(table),
        "table_count_sum": sum(r["count"] for r in table),
        "table_rows": rows,
        "all_table_counts_match_global_first_dword": all(x["count_matches_global_first_dword"] for x in rows),
        "rig_type_rows": rig_rows,
        "all_rig_counts_match": all(x["count_matches_global_first_dword"] for x in rig_rows),
        "totals_self_consistent": heap_total == root_total == sum(r["count"] for r in table),
    }


def clone_source_evidence(logical, records: list[dict]) -> dict:
    table = {r["key"]: r for r in logical.read_type_table(logical.payload_records(records)[1]["data"])}
    sources = []
    type_deltas = collections.Counter()
    for name in CLONE_SOURCE_NAMES:
        matches = [r for r in records if r["data"] and r["name"] == name]
        for r in matches:
            word = payload_type_word(r)
            participates = word in table
            if participates:
                type_deltas[word] += 1
            item = public_record(r)
            item["type_table_key_match"] = participates
            if participates:
                item["type_table_row"] = {"key": f"0x{word:X}", "base": table[word]["base"], "count": table[word]["count"]}
            sources.append(item)
    finals = [r for r in records if r["data"] and r["flags"] == 0x3D and len(r["data"]) == 164]
    mismatches = []
    for r in finals:
        internal = payload_internal_name(r)
        if internal != r["name"]:
            mismatches.append({"header_name": r["name"], "payload_name": internal, "payload_index": r["payload_index"]})
    return {
        "sources": sources,
        "required_type_count_delta_if_each_source_payload_is_cloned_once": {f"0x{k:X}": v for k, v in sorted(type_deltas.items())},
        "stock_final_header_payload_name_mismatches": mismatches,
    }


def candidate_audit(logical, path: Path, stock_accounting: dict) -> dict:
    raw = path.read_bytes()
    records = logical.parse_wad(raw)
    acc = accounting_evidence(logical, records)
    table_stock = {x["key"]: x for x in stock_accounting["table_rows"]}
    table_candidate = {x["key"]: x for x in acc["table_rows"]}
    diffs = []
    for key in sorted(set(table_stock) | set(table_candidate), key=lambda x: int(x, 16)):
        a, b = table_stock.get(key), table_candidate.get(key)
        if a is None or b is None or a["base"] != b["base"] or a["count"] != b["count"]:
            diffs.append({"key": key, "stock": a, "candidate": b})
    raven = [r for r in records if r["data"] and r["name"].lower() == "gomapiconcompletionistraven"]
    raven_rows = []
    for r in raven:
        item = public_record(r)
        item["payload_name"] = payload_internal_name(r)
        item["header_payload_name_match"] = item["payload_name"] == r["name"]
        raven_rows.append(item)
    return {
        "path": str(path),
        "sha256": sha(raw),
        "bytes": len(raw),
        "accounting": acc,
        "type_table_diffs_from_stock": diffs,
        "raven_finals": raven_rows,
        "runtime_valid": False,
    }


class PeImage:
    def __init__(self, raw: bytes):
        self.raw = raw
        pe = struct.unpack_from("<I", raw, 0x3C)[0]
        check(raw[pe:pe + 4] == b"PE\0\0", "invalid PE")
        nsects = struct.unpack_from("<H", raw, pe + 6)[0]
        opt_size = struct.unpack_from("<H", raw, pe + 20)[0]
        opt = pe + 24
        check(struct.unpack_from("<H", raw, opt)[0] == 0x20B, "not PE32+")
        self.image_base = struct.unpack_from("<Q", raw, opt + 24)[0]
        self.sections = {}
        sh = opt + opt_size
        for i in range(nsects):
            at = sh + i * 40
            name = raw[at:at + 8].split(b"\0", 1)[0].decode("ascii")
            vsize, rva, raw_size, raw_ptr = struct.unpack_from("<IIII", raw, at + 8)
            chars = struct.unpack_from("<I", raw, at + 36)[0]
            self.sections[name] = {"name": name, "rva": rva, "vsize": vsize,
                                   "raw_size": raw_size, "raw_ptr": raw_ptr, "chars": chars}

    def read(self, rva: int, size: int) -> bytes:
        for s in self.sections.values():
            length = max(s["vsize"], s["raw_size"])
            if s["rva"] <= rva and rva + size <= s["rva"] + length:
                off = s["raw_ptr"] + rva - s["rva"]
                check(off + size <= len(self.raw), "PE RVA reaches beyond raw file")
                return self.raw[off:off + size]
        raise ValueError(f"RVA outside sections: {rva:#x}+{size:#x}")

    def runtime_functions(self) -> list[tuple[int, int]]:
        pdata = self.sections.get(".pdata")
        text = self.sections.get(".text")
        check(pdata is not None and text is not None, "PE lacks .pdata/.text")
        raw = self.raw[pdata["raw_ptr"]:pdata["raw_ptr"] + pdata["raw_size"]]
        out = set()
        text_end = text["rva"] + max(text["vsize"], text["raw_size"])
        for off in range(0, len(raw) - 11, 12):
            begin, end, unwind = struct.unpack_from("<III", raw, off)
            if begin == end == unwind == 0:
                continue
            if text["rva"] <= begin < end <= text_end:
                out.add((begin, end))
        check(out, "no x64 runtime functions parsed")
        return sorted(out)


def function_for_rva(starts: list[int], ranges: dict[int, int], rva: int):
    i = bisect.bisect_right(starts, rva) - 1
    if i < 0:
        return None
    start = starts[i]
    return start if rva < ranges[start] else None


def score_type_table_candidate(disps: set[int], imms: set[int], calls: set[int]) -> tuple[int, list[str]]:
    score, why = 0, []
    core = {0x1C, 0x20, 0x28}
    overlap = core & disps
    if len(overlap) == 3:
        score += 12; why.append("uses root offsets 0x1C,0x20,0x28")
    elif len(overlap) == 2:
        score += 6; why.append("uses two root accounting offsets")
    elif len(overlap) == 1:
        score += 2; why.append("uses one root accounting offset")
    if 0xC in imms:
        score += 4; why.append("uses 12-byte row stride/immediate")
    hits = sorted(RIG_KEYS & imms)
    if hits:
        score += min(8, 2 * len(hits)); why.append("references rig type key(s)")
    if 0x60 in imms:
        score += 1; why.append("uses 0x60 WAD header size")
    if 0xF in imms or 0xFFFFFFFFFFFFFFF0 in imms:
        score += 1; why.append("has 16-byte alignment immediate")
    if 0x423100 in calls:
        score += 3; why.append("calls resource resolver")
    return score, why


def score_name_map_candidate(disps: set[int], imms: set[int], calls: set[int], write_disps: set[int]) -> tuple[int, list[str]]:
    score, why = 0, []
    if 0x78 in disps:
        score += 5; why.append("references WAD name-map offset +0x78")
    if 0x78 in write_disps:
        score += 7; why.append("writes through +0x78")
    if 0x401 in imms:
        score += 5; why.append("contains folded-name hash multiplier 0x401")
    if 6 in imms:
        score += 1; why.append("contains shift/immediate 6")
    if 0x423100 in calls:
        score += 3; why.append("calls resource resolver")
    if 0x750920 in calls:
        score += 2; why.append("calls general resource lookup")
    return score, why


def native_probe(exe: bytes, type_keys: set[int]) -> dict:
    import capstone
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM

    pe = PeImage(exe)
    check(pe.image_base == BASE, "unexpected image base")
    funcs = pe.runtime_functions()
    starts = [a for a, _ in funcs]
    ranges = {a: b for a, b in funcs}
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    features = {}
    callers = collections.defaultdict(set)

    interesting_imms = set(type_keys) | RIG_KEYS | {0x401, 6, 0xC, 0x1C, 0x20, 0x28, 0x60, 0x78, 0xF}
    for start, end in funcs:
        try:
            code = pe.read(start, end - start)
        except ValueError:
            continue
        disps, imms, calls, write_disps = set(), set(), set(), set()
        for insn in md.disasm(code, BASE + start):
            for op in insn.operands:
                if op.type == X86_OP_IMM:
                    value = op.imm
                    if value >= BASE:
                        target = value - BASE
                        if target in ranges:
                            calls.add(target)
                            callers[target].add(start)
                    if value in interesting_imms:
                        imms.add(value)
                elif op.type == X86_OP_MEM:
                    disp = op.mem.disp
                    if disp in interesting_imms:
                        disps.add(disp)
                        if insn.operands and insn.operands[0].type == X86_OP_MEM and insn.operands[0].mem.disp == disp:
                            write_disps.add(disp)
        type_score, type_why = score_type_table_candidate(disps, imms, calls)
        name_score, name_why = score_name_map_candidate(disps, imms, calls, write_disps)
        if type_score or name_score or calls:
            features[start] = {
                "start_rva": f"0x{start:X}",
                "end_rva": f"0x{end:X}",
                "bytes": end - start,
                "type_score": type_score,
                "type_reasons": type_why,
                "name_map_score": name_score,
                "name_map_reasons": name_why,
                "calls": [f"0x{x:X}" for x in sorted(calls)],
            }

    type_candidates = sorted((v for v in features.values() if v["type_score"]), key=lambda x: (-x["type_score"], int(x["start_rva"], 16)))[:80]
    name_candidates = sorted((v for v in features.values() if v["name_map_score"]), key=lambda x: (-x["name_map_score"], int(x["start_rva"], 16)))[:80]
    neighborhoods = []
    for target, label in KNOWN_NATIVE.items():
        neighborhoods.append({
            "target_rva": f"0x{target:X}",
            "label": label,
            "direct_callers": [f"0x{x:X}" for x in sorted(callers.get(target, set()))],
        })
    return {
        "runtime_function_count": len(funcs),
        "type_table_consumer_candidates": type_candidates,
        "name_map_construction_candidates": name_candidates,
        "known_native_call_neighborhoods": neighborhoods,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--python-module-dir", type=Path)
    ap.add_argument("--candidate-wad", type=Path, action="append", default=[])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    logical = load_module("completionist_logical_clone", HERE / "build-raven-ui-logical-clone.py")
    if args.python_module_dir:
        sys.path.insert(0, str(args.python_module_dir.resolve()))

    game = args.game_root.resolve()
    out = args.output.resolve()
    allowed = (HERE.parent.parent / "archive" / "field-logs").resolve()
    check(out.is_relative_to(allowed) and out.suffix.lower() == ".json", "output must be repo archive/field-logs JSON")
    check(not out.is_relative_to(game), "output must be outside game tree")

    paths = {
        "r_ui.wad": game / "exec/wad/pc_le/r_ui.wad",
        "wad_r_ui.dcb": game / "exec/dc/pc_le/wad_r_ui.dcb",
        "mapmaster.dcb": game / "exec/dc/pc_le/mapmaster.dcb",
        "GoW.exe": game / "GoW.exe",
    }
    pins = {"r_ui.wad": EXPECTED_WAD, "wad_r_ui.dcb": EXPECTED_DCB,
            "mapmaster.dcb": EXPECTED_MAPMASTER, "GoW.exe": EXPECTED_EXE}
    blobs = {name: path.read_bytes() for name, path in paths.items()}
    for name, raw in blobs.items():
        check(sha(raw) == pins[name], f"source pin differs: {name}")

    stock_records = logical.parse_wad(blobs["r_ui.wad"])
    check(logical.serialize_wad(stock_records) == blobs["r_ui.wad"], "stock WAD byte round-trip failed")
    stock_acc = accounting_evidence(logical, stock_records)
    table_keys = {int(x["key"], 16) for x in stock_acc["table_rows"]}

    result = {
        "result": "READ_ONLY_WAD_LOADER_BOOKKEEPING_PROBE",
        "game_files_written": False,
        "runtime_test_ready": False,
        "source_hashes": {name: sha(raw) for name, raw in blobs.items()},
        "stock_wad_accounting": stock_acc,
        "clone_source_accounting": clone_source_evidence(logical, stock_records),
        "native_probe": native_probe(blobs["GoW.exe"], table_keys),
        "existing_candidate_audits": [candidate_audit(logical, p.resolve(), stock_acc) for p in args.candidate_wad if p.exists()],
        "gates": {
            "type_table_semantics_fully_proved": False,
            "all_required_counts_and_budgets_identified": False,
            "name_map_registration_fully_traced": False,
            "scope_dependency_bookkeeping_fully_accounted": False,
            "header_payload_name_consistency_rule_static": True,
            "new_runtime_candidate_allowed": False,
        },
    }
    check(all(sha(paths[name].read_bytes()) == pins[name] for name in paths), "source changed during scan")
    result["source_hashes_unchanged_after_scan"] = True
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    table_counts_match = stock_acc.get(
        "all_table_counts_match_rig_type_words",
        stock_acc.get("all_table_counts_match_global_first_dword"),
    )
    print(json.dumps({
        "table_rows": stock_acc["table_row_count"],
        "all_table_counts_match": table_counts_match,
        "all_rig_counts_match": stock_acc["all_rig_counts_match"],
        "type_candidates": len(result["native_probe"]["type_table_consumer_candidates"]),
        "name_map_candidates": len(result["native_probe"]["name_map_construction_candidates"]),
        "runtime_test_ready": False,
        "output": str(out),
    }, indent=2))
    print("No God of War files, saves, boot options, or progression state were modified.")


if __name__ == "__main__":
    main()
