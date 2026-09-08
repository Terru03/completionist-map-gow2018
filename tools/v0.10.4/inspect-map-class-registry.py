"""Trace map resource and pool data. Read files; write repo JSON only.

Need Capstone 5; use --python-module-dir for an existing local copy.
No process access, install, WAD build, or save access.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("registry_inventory", HERE / "inspect-r-ui-registered-map-classes.py")
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)
native, logical = inventory.native, inventory.logical
EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
LUA_COMMIT = "1958cf514d56e1278f02570c876ad127462b3551"
BASE = 0x140000000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def cstring(raw, start, end):
    check(0 <= start < end <= len(raw), "string range outside payload")
    zero = raw.find(b"\0", start, end)
    check(zero >= 0, "unterminated payload name")
    return raw[start:zero].decode("ascii")


def final_name(record):
    check(record["flags"] == 0x3D and len(record["data"]) == 164, "not a final-instance layout")
    return cstring(bytes(record["data"]), 0x1C, 0x54)


def type_accounting(records):
    payloads = logical.payload_records(records)
    table = logical.read_type_table(payloads[1]["data"])
    observed = collections.Counter(struct.unpack_from("<I", r["data"])[0]
                                   for r in records if r["flags"] == 0x3D and len(r["data"]) >= 4)
    checks = []
    for key in sorted(set(observed) | {0x10001, 0x20001, 0x30001, 0x40001}):
        count = observed[key]
        row = next((x for x in table if x["key"] == key), None)
        check(row is not None, f"missing rig type table row {key:#x}")
        checks.append({"type_key": f"0x{key:X}", "observed_payloads": count,
                       "declared_count": row["count"], "matches": row["count"] == count})
    examples = []
    for r in records:
        if r["data"] and r["name"] in ("gomapicondock", "gomapiconprimaryquest", logical.RAVEN_WAD_NAME):
            wrong = next((x for x in table if x["base"] <= r["payload_index"] < x["base"] + x["count"]), None)
            examples.append({"name": r["name"], "payload_index": r["payload_index"],
                             "payload_type_key": f"0x{struct.unpack_from('<I', r['data'])[0]:X}",
                             "type_key_if_payload_index_misused": None if wrong is None else f"0x{wrong['key']:X}"})
    return {"rig_type_counts": checks, "all_rig_type_counts_match": all(x["matches"] for x in checks),
            "index_domain_counterexamples": examples,
            "note": "WAD type-table bases are runtime type ranges, not file payload indices. Checks cover rig types only, not full heap correctness."}


def describe(r):
    return {"name": r["name"], "payload_index": r["payload_index"],
            "file_offset": f"0x{r['original_offset']:X}", "bytes": len(r["data"]),
            "kind": r["kind"], "flags": f"0x{r['flags']:X}", "resource_id": r["id"].hex()}


def wad_evidence(records, rows, master):
    headers = collections.defaultdict(list)
    definitions = collections.defaultdict(list)
    children = collections.defaultdict(list)
    finals = []
    for r in records:
        children[r["parent"]].append(r)
        if r["name"]:
            headers[native.name_hash(r["name"])].append(r)
        if r["data"] and r["kind"] == 1:
            definitions[r["id"]].append(r)
        if r["flags"] == 0x3D and len(r["data"]) == 164:
            finals.append(r)
    internal = collections.defaultdict(list)
    for r in finals:
        internal[native.name_hash(final_name(r))].append(r)
    use = collections.Counter(native.name_hash(icon) for _, _, _, icon in inventory.iter_map_markers(master) if icon)
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row["name_hash_int"]].append(row)
    pool = []
    for row in rows:
        h = row["name_hash_int"]
        pool.append({**inventory.public_row(row),
                     "header_names": sorted({r["name"] for r in headers[h]}),
                     "header_definitions": [describe(r) for r in headers[h] if r["data"]],
                     "payload_name_matches": [describe(r) for r in internal[h]],
                     "authored_mapmaster_usage": use[h],
                     "donor_safe": False})
    maps = []
    for r in finals:
        if not r["name"].lower().startswith("gomapicon"):
            continue
        data = bytes(r["data"])
        proto_id, parent_id = data[0xC:0x1C], data[0x54:0x64]
        protos = definitions[proto_id]
        check(len(protos) == 1 and protos[0]["flags"] == 0x3D, "map final prototype is not unique")
        proto = protos[0]
        node_count = struct.unpack_from("<H", proto["data"], 0xC)[0]
        id_table = struct.unpack_from("<I", proto["data"], 0x18)[0]
        name_start = id_table - node_count * 56
        root_name = cstring(bytes(proto["data"]), name_start, name_start + 56)
        links = [x for x in children[proto["parent"]] if x["kind"] == 1 and not x["data"]]
        model_links = [x for x in links if x["name"].startswith("MDL_")]
        materials = []
        for link in model_links:
            for model in definitions[link["id"]]:
                for mat in children[model["parent"]]:
                    if mat["kind"] == 1 and not mat["data"] and mat["name"].startswith("MAT_"):
                        materials.append({"model": describe(model), "link": describe(mat),
                                          "definitions": [describe(x) for x in definitions[mat["id"]]]})
        h = native.name_hash(final_name(r))
        reasons = []
        if h not in groups:
            reasons.append("No GOPool row in this WAD; cannot donate an existing pool slot.")
        if use[h]:
            reasons.append(f"Authored mapmaster use: {use[h]}.")
        if r["name"] in ("gomapiconplayer", "gomapicons"):
            reasons.append("Player or map hierarchy root; live system resource.")
        if "_area" in r["name"]:
            reasons.append("Quest-area child; parent ID and Lua highlight use need preservation.")
        reasons.append("No runtime safety proof; absence of text matches is not proof of no use.")
        maps.append({**describe(r), "payload_name": final_name(r),
                     "payload_name_hash": f"{h:016X}", "gopool_rows": [inventory.public_row(x) for x in groups.get(h, [])],
                     "authored_mapmaster_usage": use[h], "prototype": describe(proto),
                     "prototype_root_node_name": root_name,
                     "parent_prototype_id": parent_id.hex(),
                     "parent_definitions": [describe(x) for x in definitions[parent_id]],
                     "prototype_child_links": [describe(x) for x in links],
                     "materials": materials, "donor_safe": False, "rejection_reasons": reasons})
    duplicate = []
    for h, rs in groups.items():
        if len(rs) > 1:
            duplicate.append({"hash": f"{h:016X}", "names": sorted({x["name"] for x in headers[h]}),
                              "rows": [inventory.public_row(x) for x in rs],
                              "sum_cnt": sum(x["cnt"] for x in rs),
                              "definitions": [describe(x) for x in internal[h]],
                              "semantics": "Native pool-add merges by resolved resource pointer and adds Cnt; not spare aliases."})
    return {"pool_rows": pool, "duplicate_groups": duplicate, "map_finals": maps,
            "counts": {"pool_rows": len(pool), "unique_pool_names": len(groups),
                       "pool_rows_with_header_matches": sum(bool(x["header_names"]) for x in pool),
                       "pool_rows_with_payload_name_matches": sum(bool(x["payload_name_matches"]) for x in pool),
                       "map_finals": len(maps), "safe_donors": 0},
            "unresolved_pool_rows": [x for x in pool if not x["header_names"]],
            "header_payload_name_mismatches": [describe(r) for r in finals if r["name"].lower() != final_name(r).lower()]}


class Pe:
    def __init__(self, raw):
        self.raw = raw
        pe = struct.unpack_from("<I", raw, 0x3C)[0]
        check(raw[pe:pe + 4] == b"PE\0\0", "invalid PE signature")
        check(struct.unpack_from("<Q", raw, pe + 48)[0] == BASE, "unexpected image base")
        count = struct.unpack_from("<H", raw, pe + 6)[0]
        opt = struct.unpack_from("<H", raw, pe + 20)[0]
        self.sections = []
        for i in range(count):
            at = pe + 24 + opt + i * 40
            _, rva, size, offset = struct.unpack_from("<4I", raw, at + 8)
            self.sections.append((rva, size, offset))

    def read(self, rva, size):
        for start, length, offset in self.sections:
            if start <= rva and rva + size <= start + length:
                return self.raw[offset + rva - start:offset + rva - start + size]
        raise ValueError("PE read outside file-backed section")


# Function labels are analysis. RVAs apply to EXPECTED_EXE only.
ANCHORS = [
    (0x951E40, 0xDC, "Lua CreateMarkerIcon unboxes marker/region, looks up marker, then creates icon.",
     {0x951E8D: "call 0x140761fe0", 0x951E9A: "call 0x140903f40"}),
    (0x903F40, 0x95, "Reads authored token +8 Icon string, case-folds and hashes, calls resource path.",
     {0x903F5E: "mov rax, qword ptr [rcx + 0x10]", 0x903F6A: "mov r10, qword ptr [rax + 8]",
      0x903FA4: "imul r9, rax, 0x401", 0x903FC4: "call 0x140750920"}),
    (0x750920, 0x295, "Looks up resource hash in WAD map, dependencies and global map before pool checkout.",
     {0x7509B0: "mov r8, qword ptr [r14 + 0x78]", 0x7509C8: "cmp rbx, qword ptr [rax]",
      0x750A3C: "call 0x1404b9020", 0x750B15: "call 0x140423100", 0x750B26: "call 0x14060eda0"}),
    (0x672A00, 0x5E, "GOPool loop resolves Name, reads u16 Cnt, calls pool-add; stride 16.",
     {0x672A0A: "movzx ebp, word ptr [rdi + rax + 8]", 0x672A13: "call 0x140423100",
      0x672A41: "movzx r8d, bp", 0x672A48: "call 0x14060dd80", 0x672A54: "add rdi, 0x10"}),
    (0x60DD80, 0x1CC, "Pool-add finds same resource pointer, adds capacity, then clones Cnt objects.",
     {0x60DDA4: "cmp qword ptr [rbx], rbp", 0x60DDA7: "je 0x14060de6b",
      0x60DE6B: "add dword ptr [rbx + 0x14], edi", 0x60DEBC: "call qword ptr [rax + 0x20]",
      0x60DEDA: "inc dword ptr [rbx + 8]", 0x60DEDD: "inc dword ptr [rbx + 0xc]",
      0x60DF24: "sub r15, 1", 0x60DF28: "jne 0x14060dea0"}),
    (0x60EDA0, 0x12B, "Checkout uses resource pointer pool; no pool or exhausted capacity returns null.",
     {0x60EDDC: "call 0x14060d8b0", 0x60EDE7: "je 0x14060eeb9",
      0x60EDF7: "cmp dword ptr [rbx + 8], ecx", 0x60EE11: "call 0x14060e0b0",
      0x60EEBE: "xor eax, eax"}),
    (0x60D8B0, 0xF5, "Pool lookup compares resource pointer, then recurses through dependency WADs.",
     {0x60D8D6: "cmp qword ptr [r9], r14", 0x60D972: "call 0x14060d8b0"}),
    (0x673FE0, 0x88, "Incremental warmup also iterates every row Cnt times; duplicate rows are not discarded.",
     {0x674004: "call 0x14060d4b0", 0x67401E: "movzx eax, word ptr [rdi + 8]",
      0x674022: "cmp ecx, eax"}),
    (0x5B813D, 0x18, "Separate memory estimate multiplies per-resource work by Cnt.",
     {0x5B813D: "movzx eax, word ptr [r14 + 8]", 0x5B8146: "imul eax, ebx", 0x5B8149: "add esi, eax"}),
]


def executable_evidence(raw):
    import capstone
    pe = Pe(raw)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    anchors = []
    for start, size, meaning, expected in ANCHORS:
        block = pe.read(start, size)
        decoded = {i.address - BASE: f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(block, BASE + start)}
        selected = []
        for rva, text in expected.items():
            check(decoded.get(rva) == text, f"native anchor mismatch at {rva:#x}: {decoded.get(rva)}")
            selected.append({"rva": f"0x{rva:X}", "instruction": text})
        anchors.append({"start_rva": f"0x{start:X}", "bytes": size, "sha256": sha(block),
                        "analysis": meaning, "checked_instructions": selected})
    return {"sha256": sha(raw), "image_base": f"0x{BASE:X}", "capstone_version": capstone.__version__,
            "anchors": anchors, "all_anchor_instructions_match": True,
            "limits": ["Static disassembly only; no live pool sizes measured.",
                       "Full WAD name-map construction and all heap bookkeeping remain untraced.",
                       "No claim that a Name-only DCB rename creates a resource alias."]}


def lua_evidence(root, names):
    check(root.is_dir(), "missing GoWLUA checkout")
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    check(commit == LUA_COMMIT, "GoWLUA checkout must use pinned commit")
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True)
    check(not dirty.strip(), "GoWLUA checkout is not clean")
    files = sorted(root.rglob("*.lua"))
    check(files, "no Lua source files")
    tokens = set()
    for name in names:
        tokens.add(name.lower())
        if name.lower().startswith("go"):
            tokens.add(name[2:].lower())
    tokens.update(["createmarkericon", "poolcount", "poolhasspace"])
    hits, manifest = [], []
    for path in files:
        raw = path.read_bytes()
        rel = path.relative_to(root).as_posix()
        manifest.append({"path": rel, "sha256": sha(raw)})
        for lineno, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            words = {x.lower() for x in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", line)}
            matches = sorted(words & tokens)
            if matches:
                hits.append({"path": rel, "line": lineno, "tokens": matches})
    return {"repository": "https://github.com/MorseTheCode/GoWLUA", "commit": commit,
            "source_files": len(files), "file_hashes": manifest, "token_hits": hits,
            "limits": "Exact identifiers, full names and names without go prefix scanned. Dynamic strings, binary-only code and other builds can still use a resource. No-match never proves safe."}


def candidate_audit(path):
    raw = path.read_bytes()
    records = logical.parse_wad(raw)
    candidates = [r for r in records if r["name"] == logical.RAVEN_WAD_NAME and r["data"]]
    return {"label": path.parent.name, "sha256": sha(raw), "bytes": len(raw),
            "type_accounting": type_accounting(records),
            "raven_finals": [{**describe(r), "payload_name": final_name(r),
                              "header_payload_name_match": final_name(r) == r["name"]} for r in candidates],
            "runtime_valid": False, "note": "Read existing offline candidate only. Name mismatch is evidence of incomplete rename, not proven crash cause."}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--lua-root", type=Path, required=True)
    ap.add_argument("--python-module-dir", type=Path)
    ap.add_argument("--candidate-wad", type=Path, action="append", default=[])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = inventory.report_path(args.output)
    if args.python_module_dir:
        sys.path.insert(0, str(args.python_module_dir.resolve()))
    game = args.game_root.resolve()
    check(not out.is_relative_to(game), "report must stay outside game tree")
    paths = [game / "exec/wad/pc_le/r_ui.wad", game / "exec/dc/pc_le/wad_r_ui.dcb",
             game / "exec/dc/pc_le/mapmaster.dcb", game / "GoW.exe"]
    expected = [inventory.EXPECTED_WAD_SHA256, inventory.EXPECTED_DCB_SHA256,
                inventory.EXPECTED_MAPMASTER_SHA256, EXPECTED_EXE]
    blobs = [p.read_bytes() for p in paths]
    for p, raw, pin in zip(paths, blobs, expected):
        check(sha(raw) == pin, f"source pin differs: {p.name}")
    rows = inventory.parse_gopool(native.Dcb(paths[1]))
    records = logical.parse_wad(blobs[0])
    check(logical.serialize_wad(records) == blobs[0], "WAD byte round-trip failed")
    evidence = wad_evidence(records, rows, native.Dcb(paths[2]))
    evidence["type_accounting"] = type_accounting(records)
    check(evidence["type_accounting"]["all_rig_type_counts_match"], "stock rig type counts differ")
    names = {n for r in evidence["pool_rows"] for n in r["header_names"]}
    names.update(r["name"] for r in evidence["map_finals"])
    result = {"result": "STATIC_REGISTRY_RESEARCH_NO_SAFE_DONOR", "game_files_written": False,
              "runtime_test_ready": False, "source_hashes": {p.name: sha(b) for p, b in zip(paths, blobs)},
              "wad_byte_round_trip": True, "wad": evidence, "executable": executable_evidence(blobs[3]),
              "lua": lua_evidence(args.lua_root.resolve(), names),
              "existing_candidate_audits": [candidate_audit(p.resolve()) for p in args.candidate_wad],
              "route_decisions": {
                  "gopool_name_only_rename": "Rejected. Name selects an already defined resource; no safe donor and no alias mapping shown.",
                  "in_place_wad_retarget": "Not ready. No safe map donor; must preserve header, payload names, IDs, scopes, model/material users and pool budgets.",
                  "append_new_wad_resource": "Not ready. Old builder selects type by file payload index instead of payload type; final type is 0x20001, not 0xD. Full heap bookkeeping remains unresolved.",
                  "alternate_native_registration": "Native pool-add exists but takes resolved resources and WAD context. No safe public class-registration API established."}}
    check(all(sha(p.read_bytes()) == h for p, h in zip(paths, expected)), "source changed during scan")
    result["source_hashes_unchanged_after_scan"] = True
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": evidence["counts"], "duplicate_groups": len(evidence["duplicate_groups"]),
                      "native_anchors": len(ANCHORS), "lua_files": result["lua"]["source_files"],
                      "runtime_test_ready": False, "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
