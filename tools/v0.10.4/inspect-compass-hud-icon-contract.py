"""Read-only audit of the native CompassIconClass IconName resource contract.

The UID-sorted CompletionistRaven class was accepted and manager-verified while
cloning DockPoint. Replacing only IconName with the existing map resource hash
584F31DC8BD6E738 made ShowMarker return successfully, then the game crashed
before manager verification. This probe compares every stock CompassIconClass
IconName against r_ui.wad, compares stock goboatdock with the dedicated Raven
resource, and disassembles the native compass show/icon-creation neighborhood.

No game, save, progression, marker-state, or mod file is written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
EXPECTED_PERM = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"
EXPECTED_RUI = "9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3"
TYPE_ID = 0x11E
DOCK_ICON = 0x82F0296748C7393D
RAVEN_ICON = 0x584F31DC8BD6E738
NATIVE_SHOW_RVA = 0x6C0C80
PRIOR_ICON_CREATE_SITE = 0x6C0E65
RESULT = "READ_ONLY_COMPASS_HUD_ICON_CONTRACT"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_local(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wad_match_rows(wadmod, records: list[dict], target_hash: int) -> list[dict]:
    out = []
    for index, row in enumerate(records):
        name = row["name"]
        if not name or wadmod.name_hash(name) != target_hash:
            continue
        parent_index = row.get("parent")
        parent_name = records[parent_index]["name"] if parent_index is not None else None
        data = bytes(row["data"])
        out.append({
            "record_index": index,
            "name": name,
            "kind": int(row["kind"]),
            "flags": f"0x{int(row['flags']):X}",
            "data_bytes": len(data),
            "payload_index": row.get("payload_index"),
            "file_offset": None if row.get("original_offset") is None else f"0x{int(row['original_offset']):X}",
            "resource_id": bytes(row["id"]).hex(),
            "parent_index": parent_index,
            "parent_name": parent_name,
            "payload_prefix_hex": data[:64].hex().upper() if data else "",
        })
    return out


def payload_type_key(wadmod, records: list[dict], payload_index: int | None) -> str | None:
    if payload_index is None:
        return None
    payloads = wadmod.payload_records(records)
    if len(payloads) < 2:
        return None
    rows = wadmod.read_type_table(bytes(payloads[1]["data"]))
    hits = [r for r in rows if r["base"] <= payload_index < r["base"] + r["count"]]
    if len(hits) != 1:
        return None
    return f"0x{int(hits[0]['key']):X}"


def first_payload(matches: list[dict], records: list[dict]) -> tuple[dict, dict] | None:
    for item in matches:
        if item["data_bytes"]:
            return item, records[item["record_index"]]
    return None


def compare_payloads(a: bytes, b: bytes) -> dict:
    common = min(len(a), len(b))
    diffs = [i for i in range(common) if a[i] != b[i]]
    if len(a) != len(b):
        diffs.extend(range(common, max(len(a), len(b))))
    return {
        "left_bytes": len(a),
        "right_bytes": len(b),
        "difference_count": len(diffs),
        "first_difference_offsets": [f"0x{x:X}" for x in diffs[:64]],
        "left_hex": a.hex().upper(),
        "right_hex": b.hex().upper(),
    }


def native_analysis(native, exe_raw: bytes) -> dict:
    pe = native.PE(exe_raw)
    funcs = native.parse_runtime_functions(pe)
    fn = native.containing_function(funcs, NATIVE_SHOW_RVA)
    if fn is None:
        raise ValueError("native compass show function was not found in .pdata")
    begin, end = int(fn["begin"]), int(fn["end"])
    result = {
        "function": {"begin": f"0x{begin:X}", "end": f"0x{end:X}"},
        "prior_icon_create_site": f"0x{PRIOR_ICON_CREATE_SITE:X}",
        "hex_window": native.hex_window(pe, PRIOR_ICON_CREATE_SITE, 160),
        "heuristic_direct_calls": native.heuristic_calls(pe, max(begin, PRIOR_ICON_CREATE_SITE - 192), min(end, PRIOR_ICON_CREATE_SITE + 256), funcs),
    }
    try:
        import capstone  # type: ignore
        from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP  # type: ignore
    except Exception as exc:
        result["capstone"] = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
        return result

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    code = pe.read_rva(begin, end - begin)
    insns = list(md.disasm(code, native.IMAGE_BASE + begin))
    decoded = []
    calls = []
    rip_refs = []
    lo = max(begin, PRIOR_ICON_CREATE_SITE - 0x180)
    hi = min(end, PRIOR_ICON_CREATE_SITE + 0x220)
    for insn in insns:
        rva = int(insn.address - native.IMAGE_BASE)
        if lo <= rva < hi:
            decoded.append({
                "rva": f"0x{rva:X}",
                "bytes": insn.bytes.hex().upper(),
                "mnemonic": insn.mnemonic,
                "op_str": insn.op_str,
            })
        if not (lo <= rva < hi):
            continue
        if insn.mnemonic == "call":
            target = None
            kind = "indirect"
            if insn.operands and insn.operands[0].type == X86_OP_IMM:
                target = int(insn.operands[0].imm - native.IMAGE_BASE)
                kind = "direct"
            calls.append({"site_rva": f"0x{rva:X}", "kind": kind,
                          "target_rva": None if target is None else f"0x{target:X}",
                          "op_str": insn.op_str})
        for op in insn.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                target = rva + insn.size + int(op.mem.disp)
                rip_refs.append({
                    "site_rva": f"0x{rva:X}",
                    "target_rva": f"0x{target:X}",
                    "mnemonic": insn.mnemonic,
                    "op_str": insn.op_str,
                    "ascii": pe.ascii_at_rva(target),
                })
    result["capstone"] = {
        "available": True,
        "window_start": f"0x{lo:X}",
        "window_end": f"0x{hi:X}",
        "decoded": decoded,
        "calls": calls,
        "rip_relative_refs": rip_refs,
    }
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    output = args.output.resolve()
    if output.is_relative_to(game):
        raise ValueError("report must stay outside the game directory")

    exe = game / "GoW.exe"
    perm = game / "exec/dc/pc_le/wad_r_perm.dcb"
    rui = game / "exec/wad/pc_le/r_ui.wad"
    for path in (exe, perm, rui):
        if not path.is_file():
            raise FileNotFoundError(path)

    hashes = {"GoW.exe": digest(exe), "wad_r_perm.dcb": digest(perm), "r_ui.wad": digest(rui)}
    expected = {"GoW.exe": EXPECTED_EXE, "wad_r_perm.dcb": EXPECTED_PERM, "r_ui.wad": EXPECTED_RUI}
    for name, want in expected.items():
        if hashes[name] != want:
            raise ValueError(f"{name} differs from researched baseline: {hashes[name]}")

    dcb = load_local("build-packed-raven-compass-class.py", "completionist_dcb")
    wadmod = load_local("build-raven-ui-logical-clone.py", "completionist_wad")
    native = load_local("inspect-compass-showmarker-native-validation.py", "completionist_native")

    perm_raw = perm.read_bytes()
    chunks = dcb.parse_chunks(perm_raw)
    data = bytes(dcb.one(chunks, 12)["payload"])
    _h8, exports, _tail = dcb.parse_exports(dcb.one(chunks, 13)["payload"])
    classes = []
    for e in sorted((x for x in exports if int(x["type_id"]) == TYPE_ID), key=lambda x: int(x["root"])):
        root = int(e["root"])
        icon, radius, inworld, scale = struct.unpack_from("<QQQf", data, root)
        is_main = data[root + 0x1C]
        classes.append({
            "name": e["name"], "uid": f"{int(e['uid']):016X}", "root": f"0x{root:X}",
            "IconName": f"{icon:016X}", "RadiusIconName": f"{radius:016X}",
            "InWorld_tMPIcon_Name": f"{inworld:016X}", "IconScale": scale, "IsMainQuest": bool(is_main),
        })

    rui_raw = rui.read_bytes()
    records = wadmod.parse_wad(rui_raw)
    resolved_classes = []
    for row in classes:
        icon = int(row["IconName"], 16)
        matches = wad_match_rows(wadmod, records, icon)
        for m in matches:
            m["payload_type_key"] = payload_type_key(wadmod, records, m["payload_index"])
        resolved_classes.append({"class": row["name"], "IconName": row["IconName"], "matches": matches})

    dock_matches = wad_match_rows(wadmod, records, DOCK_ICON)
    raven_matches = wad_match_rows(wadmod, records, RAVEN_ICON)
    for m in dock_matches + raven_matches:
        m["payload_type_key"] = payload_type_key(wadmod, records, m["payload_index"])

    dock_payload = first_payload(dock_matches, records)
    raven_payload = first_payload(raven_matches, records)
    comparison = None
    if dock_payload is not None and raven_payload is not None:
        dock_meta, dock_rec = dock_payload
        raven_meta, raven_rec = raven_payload
        dock_data = bytes(dock_rec["data"])
        raven_data = bytes(raven_rec["data"])
        comparison = compare_payloads(dock_data, raven_data)
        comparison.update({
            "dock_name": dock_meta["name"],
            "raven_name": raven_meta["name"],
            "dock_type_key": dock_meta.get("payload_type_key"),
            "raven_type_key": raven_meta.get("payload_type_key"),
            "dock_prototype_id_at_0x0C": dock_data[0x0C:0x1C].hex() if len(dock_data) >= 0x1C else None,
            "raven_prototype_id_at_0x0C": raven_data[0x0C:0x1C].hex() if len(raven_data) >= 0x1C else None,
        })

    native_report = native_analysis(native, exe.read_bytes())
    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "source_hashes": hashes,
        "runtime_observation": {
            "previous_registration_only_result": "CompletionistRaven accepted and manager-verified with DockPoint visuals",
            "hud_override_result": "ShowMarker returned ok=true, then game crashed before manager verification",
            "changed_field": "CompletionistRaven.IconName only",
            "bad_test_value": f"{RAVEN_ICON:016X}",
        },
        "stock_compass_classes": classes,
        "stock_iconname_wad_resolution": resolved_classes,
        "dock_icon": {"hash": f"{DOCK_ICON:016X}", "matches": dock_matches},
        "raven_map_resource_hash": {"hash": f"{RAVEN_ICON:016X}", "matches": raven_matches},
        "dock_vs_raven_payload": comparison,
        "native_show_icon_creation": native_report,
        "conclusion": "HUD_ICONNAME_RESOURCE_CONTRACT_REQUIRES_SEPARATE_PROOF",
        "next_gate": (
            "Use the stock IconName resolution set plus native 0x6C0C80 icon-creation data flow to identify the exact authored HUD resource/template contract. "
            "Do not point CompassIconClass.IconName at goMapIconCompletionistRaven again, do not alter InWorld_tMPIcon_Name, and do not modify shared DockPoint resources."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  stock CompassIconClass rows: {len(classes)}")
    print(f"  Dock IconName matches: {len(dock_matches)}")
    print(f"  Raven map-resource hash matches: {len(raven_matches)}")
    if comparison is not None:
        print(f"  Dock/Raven payload differences: {comparison['difference_count']}")
        print(f"  Dock type: {comparison['dock_type_key']}; Raven type: {comparison['raven_type_key']}")
        print(f"  Dock prototype: {comparison['dock_prototype_id_at_0x0C']}")
        print(f"  Raven prototype: {comparison['raven_prototype_id_at_0x0C']}")
    cap = native_report.get("capstone", {})
    print(f"  native show function: {native_report['function']['begin']}-{native_report['function']['end']}")
    print(f"  Capstone available: {bool(cap.get('available'))}")
    if cap.get("available"):
        print(f"  calls near icon creation: {len(cap.get('calls', []))}")
    print(f"  report: {output}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
