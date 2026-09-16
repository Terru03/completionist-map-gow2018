#!/usr/bin/env python3
"""Corrected bidirectional replay proof for the frozen Raven native carrier."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zlib

HERE = Path(__file__).resolve().parent
LEGACY_PATH = HERE / "compare-raven-native-carriers.py"
RAVEN_NAME = b"ravenKilled\x00"
BASE_PREFIX = b"__subobjs\x00mapSummaryComplete\x00"
CLASS_KEY = 0x75E050AB149B4062


def load_legacy():
    spec = importlib.util.spec_from_file_location("raven_carrier_legacy", LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {LEGACY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selftest() -> None:
    alive = bytes.fromhex(
        "5f5f7375626f626a73006d617053756d6d617279436f6d706c65746500"
        "62409b14ab50e07501b0b227342530c24ee561807520d55c16"
        "62409b14ab50e07501b0b227342530c24ea0a803505c2eb7ad"
    )
    dead = bytes.fromhex(
        "5f5f7375626f626a73006d617053756d6d617279436f6d706c65746500"
        "726176656e4b696c6c656400"
        "62409b14ab50e07501b0b227342530c24ee561807520d55c16"
        "62409b14ab50e07501b0b227342530c24ea9652dba0717be98"
        "62409b14ab50e07501b0b227342530c24ea0a803505c2eb7ad"
    )
    assert len(alive) == 79 and len(dead) == 116
    assert alive[:29] == BASE_PREFIX
    assert dead[:41] == BASE_PREFIX + RAVEN_NAME
    assert digest(alive) == "a20550b246cb5e25acc12402c64093110969eff4ba1fdd2b66e6850d359d2172"
    assert digest(dead) == "620bb85be8fd0ebf9c778eb06aba0e532ca57c74bec2d2252694512728e7f308"
    for level in (7, 8, 9):
        assert digest(zlib.compress(alive, level)) == "d705e131c7b737682e2b410936bb0646c94166f795ca3456792507c365fffc03"
        assert digest(zlib.compress(dead, level)) == "171052571d7a5db05d4821ffe08ee0c9d6941f74b644254e6bb2925ce4134c8e"
    print("RAVEN_NATIVE_CARRIER_REPLAY_V2_SELFTEST_PASSED")


def analyse(alive_path: Path, dead_path: Path, out_dir: Path) -> dict:
    m = load_legacy()
    before = {"alive": m.sha256_file(alive_path), "dead": m.sha256_file(dead_path)}
    alive = m.parse_carrier(alive_path.read_bytes(), "alive")
    dead = m.parse_carrier(dead_path.read_bytes(), "dead")

    basic = {
        "alive_prefix_expected": alive["prefix"] == BASE_PREFIX,
        "dead_prefix_is_alive_plus_raven": dead["prefix"] == alive["prefix"] + RAVEN_NAME,
        "alive_record_count_2": len(alive["records"]) == 2,
        "dead_record_count_3": len(dead["records"]) == 3,
        "record0_preserved": alive["records"][0]["raw"] == dead["records"][0]["raw"],
        "record1_moves_to_dead2": alive["records"][1]["raw"] == dead["records"][2]["raw"],
        "all_class_keys_expected": all(r["class_key"] == CLASS_KEY for r in alive["records"] + dead["records"]),
    }
    if not all(basic.values()):
        raise RuntimeError(f"basic frozen Raven checks failed: {basic}")

    inserted_record = dead["records"][1]["raw"]

    forward_prefix = alive["prefix"] + RAVEN_NAME
    forward_records = [alive["records"][0]["raw"], inserted_record, alive["records"][1]["raw"]]
    forward_section0 = alive["section0"] + [alive["header"]["record_blob_offset"]]
    base_a = alive["metadata_pairs"][2]
    new_pair_a = [m.copy_token(base_a[0], add=0x100), m.copy_token(base_a[1], add=0x100)]
    base_b = alive["metadata_pairs"][-1]
    new_pair_b = [m.copy_token(base_b[0], add=1), m.copy_token(base_b[1])]
    forward_metadata = (
        alive["metadata_pairs"][:3]
        + [new_pair_a]
        + [alive["metadata_pairs"][3]]
        + [new_pair_b]
        + [alive["metadata_pairs"][4]]
    )
    ar = [tuple(r["values"]) for r in alive["rows"]]
    forward_rows = [
        ar[0],
        (ar[1][0], ar[1][1] + 1, ar[1][2]),
        *[(r[0] + 1, r[1], r[2]) for r in ar[2:]],
        (ar[-1][0] + 2, 1, 0),
    ]

    reverse_prefix = dead["prefix"][:-len(RAVEN_NAME)]
    reverse_records = [dead["records"][0]["raw"], dead["records"][2]["raw"]]
    reverse_section0 = dead["section0"][:-1]
    reverse_metadata = dead["metadata_pairs"][:3] + [dead["metadata_pairs"][4]] + [dead["metadata_pairs"][6]]
    dr = [tuple(r["values"]) for r in dead["rows"]]
    reverse_rows = [
        dr[0],
        (dr[1][0], dr[1][1] - 1, dr[1][2]),
        *[(r[0] - 1, r[1], r[2]) for r in dr[2:4]],
    ]

    forward_components = {
        "prefix": forward_prefix == dead["prefix"],
        "records": forward_records == [r["raw"] for r in dead["records"]],
        "section0": forward_section0 == dead["section0"],
        "metadata": [m.encode_pair(p) for p in forward_metadata] == [m.encode_pair(p) for p in dead["metadata_pairs"]],
        "rows": forward_rows == [tuple(r["values"]) for r in dead["rows"]],
    }
    reverse_components = {
        "prefix": reverse_prefix == alive["prefix"],
        "records": reverse_records == [r["raw"] for r in alive["records"]],
        "section0": reverse_section0 == alive["section0"],
        "metadata": [m.encode_pair(p) for p in reverse_metadata] == [m.encode_pair(p) for p in alive["metadata_pairs"]],
        "rows": reverse_rows == [tuple(r["values"]) for r in alive["rows"]],
    }

    forward_levels = m.compression_matches(
        forward_prefix, forward_records, forward_section0, forward_metadata,
        forward_rows, alive["header"]["scalar_c"], dead["carrier"]
    )
    reverse_levels = m.compression_matches(
        reverse_prefix, reverse_records, reverse_section0, reverse_metadata,
        reverse_rows, dead["header"]["scalar_c"], alive["carrier"]
    )
    exact = (
        all(forward_components.values()) and all(reverse_components.values())
        and bool(forward_levels) and bool(reverse_levels)
    )
    verdict = (
        "RAVEN_NATIVE_CARRIER_BIDIRECTIONAL_REPLAY_EXACT"
        if exact else "RAVEN_NATIVE_CARRIER_REPLAY_NOT_EXACT"
    )

    inserted = dead["records"][1]
    after = {"alive": m.sha256_file(alive_path), "dead": m.sha256_file(dead_path)}
    if before != after:
        raise RuntimeError("frozen saves changed during read-only replay")

    summary = {
        "schema": 2,
        "analysis": "raven_native_carrier_bidirectional_replay_v2",
        "verdict": verdict,
        "source_hashes_before": before,
        "source_hashes_after": after,
        "source_hashes_unchanged": True,
        "basic_checks": basic,
        "alive": m.public_carrier(alive),
        "dead": m.public_carrier(dead),
        "inserted_raven_record": {
            **{k: v for k, v in inserted.items() if k != "raw"},
            "seed_source": "frozen_dead_observation",
        },
        "derived_forward_rules": {
            "string_rule": "append ravenKilled\\0 to decoded prefix",
            "string_insert_offset": len(alive["prefix"]),
            "record_insert_index": 1,
            "section0_rule": "append old record_blob_offset",
            "metadata_new_pair_a_rule": "old pair[2] token values + 0x100",
            "metadata_new_pair_b_rule": "old final pair first token + 1; partner unchanged",
            "row_rule": "row0 same; row1.second+1; rows2..end first+1; append (old_last.first+2,1,0)",
        },
        "forward_component_checks": forward_components,
        "reverse_component_checks": reverse_components,
        "forward_exact_zlib_levels": forward_levels,
        "reverse_exact_zlib_levels": reverse_levels,
        "forward_exact": all(forward_components.values()) and bool(forward_levels),
        "reverse_exact": all(reverse_components.values()) and bool(reverse_levels),
        "remaining_unknown": "generic derivation/binding of inserted record trailing 64-bit identity to the specific Raven/world instance",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "summary.md").write_text(
        "\n".join([
            "# Raven native carrier bidirectional replay v2",
            "",
            f"**Verdict:** `{verdict}`",
            "",
            f"- Forward exact zlib levels: `{forward_levels}`",
            f"- Reverse exact zlib levels: `{reverse_levels}`",
            f"- Raven string append offset: `{len(alive['prefix'])}`",
            "- Raven record insert index: `1`",
            f"- Raven record trailing identity: `{inserted['trailing_u64_hex']}`",
            "",
            "The only opaque DEAD-side seed is the new 25-byte Raven record itself.",
            "All carrier framing, prefix, table and compression changes are rebuilt deterministically.",
        ]) + "\n",
        encoding="utf-8",
    )
    for label, c in (("alive", alive), ("dead", dead)):
        (out_dir / f"{label}-carrier.bin").write_bytes(c["carrier"])
        (out_dir / f"{label}-decoded.bin").write_bytes(c["decoded"])

    print(verdict)
    print("FORWARD_COMPONENTS=" + json.dumps(forward_components, sort_keys=True))
    print("REVERSE_COMPONENTS=" + json.dumps(reverse_components, sort_keys=True))
    print("FORWARD_EXACT_ZLIB_LEVELS=" + (",".join(map(str, forward_levels)) or "NONE"))
    print("REVERSE_EXACT_ZLIB_LEVELS=" + (",".join(map(str, reverse_levels)) or "NONE"))
    print(f"RAVEN_RECORD_TRAILING_IDENTITY={inserted['trailing_u64_hex']}")
    if not exact:
        raise SystemExit(2)
    print("RAVEN_NATIVE_CARRIER_REPLAY_V2_PASSED")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest")
    an = sub.add_parser("analyse")
    an.add_argument("--alive", type=Path, required=True)
    an.add_argument("--dead", type=Path, required=True)
    an.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    if args.command == "selftest":
        selftest()
    else:
        analyse(args.alive, args.dead, args.output_dir)


if __name__ == "__main__":
    main()
