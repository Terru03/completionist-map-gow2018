"""Static resource-resolution audit for the corrected Raven map class.

Read-only.  This proves the corrected offline candidate is internally addressable
by the same folded-name hash used by WAD_R_UI.GOPool and by the native resource
lookup path.  It does not install the candidate or claim runtime success.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
RAVEN_WAD_NAME = "gomapiconcompletionistraven"
RAVEN_DCB_NAME = "goMapIconCompletionistRaven"
RAVEN_HASH = 0x584F31DC8BD6E738
RAVEN_FINAL_ID = bytes.fromhex("3d8f7153809e6db191c2d5e354f1e88c")
RAVEN_PROTO_ID = bytes.fromhex("f29a83d61d2fe0b9bb96123ffe77225d")
RAVEN_MODEL_ID = bytes.fromhex("e281a8d67849d97b3d5e7d88f140f59b")
RAVEN_MATERIAL_ID = bytes.fromhex("dac6009fd0f18caad2ed322463c3d0c8")
RAVEN_PROTO_NAME = "goProtoMapIconCompletionistRaven"
RAVEN_MODEL_NAME = "MDL_completionistraven"
RAVEN_MATERIAL_NAME = "MAT_AE4AD85BB993F040"
PARENT_NAME = "goProtoNW633B8059"
EXPECTED_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"
EXPECTED_DCB = "b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("completionist_logical", path)
    check(spec is not None and spec.loader is not None, "could not load WAD/DCB parser")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def folded_name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def embedded_final_name(record: dict) -> str:
    check(record["flags"] == 0x3D and len(record["data"]) == 164,
          f"unexpected final-instance layout for {record['name']}")
    raw = bytes(record["data"])
    end = raw.find(b"\0", 0x1C, 0x54)
    check(end >= 0, "unterminated final embedded name")
    return raw[0x1C:end].decode("ascii")


def one_by_id(records: list[dict], rid: bytes, *, with_data: bool = True) -> dict:
    rows = [r for r in records if r["id"] == rid and bool(r["data"]) == with_data]
    check(len(rows) == 1, f"expected one {'definition' if with_data else 'link'} for {rid.hex()}, found {len(rows)}")
    return rows[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-dir", type=Path, required=True)
    ap.add_argument("--build-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    candidate_dir = args.candidate_dir.resolve()
    wad_path = candidate_dir / "r_ui.wad"
    dcb_path = candidate_dir / "wad_r_ui.dcb"
    check(wad_path.is_file() and dcb_path.is_file(), "corrected candidate files are missing")
    wad_raw, dcb_raw = wad_path.read_bytes(), dcb_path.read_bytes()
    check(sha(wad_raw) == EXPECTED_WAD, "corrected Raven WAD hash differs from pinned build")
    check(sha(dcb_raw) == EXPECTED_DCB, "corrected Raven DCB hash differs from pinned build")

    build = json.loads(args.build_report.read_text(encoding="utf-8"))
    check(build.get("result") == "OFFLINE_RAVEN_UI_REGISTERED_CLASS_CANDIDATE_BUILT", "wrong build report")
    check(build.get("source_hashes_unchanged_after_build") is True, "source-integrity gate was not green")
    check(build.get("gowtool_parser_validation", {}).get("passed") is True, "GOWTool parser gate was not green")
    check(build["candidate"]["r_ui_wad"]["sha256"] == EXPECTED_WAD, "build report WAD hash mismatch")
    check(build["candidate"]["wad_r_ui_dcb"]["sha256"] == EXPECTED_DCB, "build report DCB hash mismatch")

    logical = load_logical()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "candidate WAD byte round-trip failed")

    # The native constructor at 0x617A50 hashes authored resource names with the
    # same case-folded 0x401 algorithm used by WAD_R_UI.GOPool.  Prove the custom
    # final has a unique hash-to-name identity among distinct WAD names.
    check(folded_name_hash(RAVEN_WAD_NAME) == RAVEN_HASH, "WAD Raven folded hash mismatch")
    check(folded_name_hash(RAVEN_DCB_NAME) == RAVEN_HASH, "DCB Raven folded hash mismatch")
    hash_to_names: dict[int, set[str]] = {}
    for record in records:
        if not record["name"]:
            continue
        h = folded_name_hash(record["name"])
        hash_to_names.setdefault(h, set()).add(record["name"].upper())
    raven_hash_names = sorted(hash_to_names.get(RAVEN_HASH, set()))
    check(raven_hash_names == [RAVEN_WAD_NAME.upper()],
          f"Raven name hash collides with distinct WAD name(s): {raven_hash_names}")

    final = one_by_id(records, RAVEN_FINAL_ID)
    check(final["name"].lower() == RAVEN_WAD_NAME, "Raven final header name mismatch")
    check(embedded_final_name(final).lower() == RAVEN_WAD_NAME, "Raven final embedded name mismatch")
    check(bytes(final["data"])[0x0C:0x1C] == RAVEN_PROTO_ID, "Raven final does not target Raven prototype")

    proto = one_by_id(records, RAVEN_PROTO_ID)
    model = one_by_id(records, RAVEN_MODEL_ID)
    material = one_by_id(records, RAVEN_MATERIAL_ID)
    check(proto["name"].lower() == RAVEN_PROTO_NAME.lower(), "Raven prototype name mismatch")
    check(model["name"].lower() == RAVEN_MODEL_NAME.lower(), "Raven model name mismatch")
    check(material["name"].lower() == RAVEN_MATERIAL_NAME.lower(), "Raven material name mismatch")

    # Prove the custom final is linked into the same authored map-icon parent
    # resource scope as stock map icons, so native WAD traversal can discover it.
    parent_def = logical.one_record(records, name=PARENT_NAME, has_data=True)
    check(parent_def["parent"] is not None, "map-icon parent definition is ungrouped")
    parent_start = parent_def["parent"]
    parent_end = logical.matching_group_end(records, parent_start)
    parent_links = [
        r for r in records[parent_start:parent_end + 1]
        if not r["data"] and r["kind"] == 1 and r["id"] == RAVEN_FINAL_ID and
           r["name"].lower() == RAVEN_WAD_NAME
    ]
    check(len(parent_links) == 1, f"expected one Raven parent-scope link, found {len(parent_links)}")

    # WAD_R_UI.GOPool must contain exactly one custom class hash with capacity 1.
    chunks = logical.parse_dcb_chunks(dcb_raw)
    data_chunk = logical.one_chunk(chunks, 12)
    data = dcb_raw[data_chunk["start"]:data_chunk["end"]]
    pool_count = struct.unpack_from("<I", data, 8)[0]
    check(pool_count == 256, f"unexpected candidate GOPool count: {pool_count}")
    rows = [data[0x90 + i * 16:0xA0 + i * 16] for i in range(pool_count)]
    raven_rows = [row for row in rows if struct.unpack_from("<Q", row, 0)[0] == RAVEN_HASH]
    check(len(raven_rows) == 1, f"expected one Raven GOPool row, found {len(raven_rows)}")
    cnt = struct.unpack_from("<H", raven_rows[0], 8)[0]
    check(cnt == 1, f"unexpected Raven GOPool capacity: {cnt}")

    result = {
        "result": "STATIC_RAVEN_REGISTERED_CLASS_RESOLUTION_PROVED",
        "game_files_written": False,
        "save_files_written": False,
        "runtime_test_ready": True,
        "candidate_hashes": {"r_ui.wad": sha(wad_raw), "wad_r_ui.dcb": sha(dcb_raw)},
        "folded_name_hash": f"{RAVEN_HASH:016X}",
        "wad_and_dcb_names_hash_identically": True,
        "distinct_wad_name_hash_collision": False,
        "raven_hash_names": raven_hash_names,
        "final_header_payload_name_consistent": True,
        "final_to_prototype_link_exact": True,
        "prototype_model_material_definitions_unique": True,
        "map_icon_parent_scope_link_count": len(parent_links),
        "gopool": {"count": pool_count, "raven_rows": len(raven_rows), "raven_cnt": cnt},
        "gowtool_parser_validation_inherited": True,
        "static_resolution_gate_passed": True,
        "remaining_unknown": "Runtime field proof that GoW loader accepts the grown corrected r_ui.wad and instantiates goMapIconCompletionistRaven.",
    }

    check(wad_path.read_bytes() == wad_raw and dcb_path.read_bytes() == dcb_raw,
          "candidate files changed during static audit")
    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "static_resolution_gate_passed": True,
        "runtime_test_ready": True,
        "raven_hash": f"{RAVEN_HASH:016X}",
        "gopool_cnt": cnt,
        "output": str(out),
    }, indent=2))
    print("No God of War files, saves, boot options, or progression state were modified.")


if __name__ == "__main__":
    main()
