"""Extract compact __codesideluaclass xref windows from an archived static trace.

Read-only post-processing. This never opens GoW.exe or any save. It consumes the
latest gow-gameobject-userdata-persistence archive already committed to the repo
and emits compact windows around every exact __codesideluaclass xref so the
producer/setter can be distinguished from lookup consumers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

KEY_RVA = 0xDF6660
EXPECTED_KEY = "__codesideluaclass"


def h(value: int | None) -> str | None:
    return None if value is None else f"0x{value:X}"


def newest_archive(repo: Path) -> Path:
    base = repo / "archive" / "field-logs" / "source-scans"
    matches = sorted(base.glob("gow-gameobject-userdata-persistence-*"))
    if not matches:
        raise RuntimeError("no gow-gameobject-userdata-persistence archive found")
    return matches[-1]


def instruction_window(instructions: list[dict], site: int, radius: int) -> list[dict]:
    index = next((i for i, row in enumerate(instructions) if row.get("rva") == site), None)
    if index is None:
        return []
    lo = max(0, index - radius)
    hi = min(len(instructions), index + radius + 1)
    return instructions[lo:hi]


def normalize_row(row: dict) -> dict:
    out = {
        "rva": h(row.get("rva")),
        "bytes": row.get("bytes"),
        "mnemonic": row.get("mnemonic"),
        "op_str": row.get("op_str"),
    }
    if "rip_targets" in row:
        out["rip_targets"] = [h(x) for x in row["rip_targets"]]
    if "immediates" in row:
        out["immediates"] = [h(x) if isinstance(x, int) and x >= 0 else x for x in row["immediates"]]
    return out


def analyze(source: Path, radius: int) -> dict:
    report = json.loads(source.read_text(encoding="utf-8"))
    lookup = report["exact_userdata_class_lookup"]
    if lookup["key_ascii"].lower() != EXPECTED_KEY:
        raise AssertionError(f"unexpected key: {lookup['key_ascii']!r}")

    owners = {row["begin"]: row for row in report.get("reference_owner_functions", [])}
    xrefs = []
    missing = []
    for ref in lookup["key_rip_refs"]:
        site = ref["site"]
        owner_begin = ref["source_function"]
        owner = owners.get(owner_begin)
        if owner is None:
            missing.append({"site": h(site), "owner": h(owner_begin), "reason": "owner disassembly absent"})
            continue
        instructions = owner.get("instructions", [])
        window = instruction_window(instructions, site, radius)
        if not window:
            missing.append({"site": h(site), "owner": h(owner_begin), "reason": "xref instruction absent from owner"})
            continue
        xrefs.append({
            "site": h(site),
            "owner_begin": h(owner_begin),
            "owner_end": h(owner.get("end")),
            "owner_size": owner.get("size"),
            "window": [normalize_row(row) for row in window],
        })

    targeted = report.get("targeted_functions", {})
    targeted_out = {}
    for name in ("gameobject_registration", "userdata_constructor", "userdata_serializer", "userdata_lookup_helper"):
        fn = targeted.get(name)
        if not fn:
            continue
        targeted_out[name] = {
            "begin": h(fn.get("begin")),
            "end": h(fn.get("end")),
            "size": fn.get("size"),
            "instructions": [normalize_row(row) for row in fn.get("instructions", [])],
        }

    return {
        "schema": 1,
        "analysis": "gow_codesideluaclass_xrefs",
        "source_archive": str(source.parent).replace("\\", "/"),
        "source_analysis": report.get("analysis"),
        "exact_lookup_corrected_status": "PASS_EXACT_USERDATA_CLASS_LOOKUP",
        "key_ascii": lookup["key_ascii"],
        "key_rva": h(KEY_RVA),
        "xref_count": len(lookup["key_rip_refs"]),
        "extracted_xref_count": len(xrefs),
        "missing_xrefs": missing,
        "xrefs": xrefs,
        "targeted_functions": targeted_out,
        "safety": {
            "postprocess_only": True,
            "game_exe_opened": False,
            "active_save_opened": False,
            "frozen_save_opened": False,
            "game_launched": False,
            "files_written_outside_archive": False,
        },
    }


def render_text(report: dict) -> str:
    lines = [
        "GoW __codesideluaclass xref extraction",
        "=======================================",
        f"source={report['source_archive']}",
        f"lookup_status={report['exact_lookup_corrected_status']}",
        f"key={report['key_ascii']}",
        f"xref_count={report['xref_count']}",
        f"extracted_xref_count={report['extracted_xref_count']}",
        "",
    ]
    for item in report["xrefs"]:
        lines.append(f"XREF site={item['site']} owner={item['owner_begin']} size={item['owner_size']}")
        for row in item["window"]:
            marker = " ==>" if row["rva"] == item["site"] else "    "
            extra = ""
            if row.get("rip_targets"):
                extra += " rip=" + ",".join(row["rip_targets"])
            if row.get("immediates"):
                extra += " imm=" + ",".join(str(x) for x in row["immediates"])
            lines.append(f"{marker} {row['rva']:>10}  {row['bytes'] or '':<24} {row['mnemonic'] or ''} {row['op_str'] or ''}{extra}")
        lines.append("")

    for name, fn in report["targeted_functions"].items():
        lines.append(f"TARGET {name} begin={fn['begin']} end={fn['end']} size={fn['size']}")
        for row in fn["instructions"]:
            extra = ""
            if row.get("rip_targets"):
                extra += " rip=" + ",".join(row["rip_targets"])
            if row.get("immediates"):
                extra += " imm=" + ",".join(str(x) for x in row["immediates"])
            lines.append(f"     {row['rva']:>10}  {row['bytes'] or '':<24} {row['mnemonic'] or ''} {row['op_str'] or ''}{extra}")
        lines.append("")

    if report["missing_xrefs"]:
        lines.append("MISSING")
        for row in report["missing_xrefs"]:
            lines.append(json.dumps(row, sort_keys=True))
    return "\n".join(lines) + "\n"


def self_test() -> None:
    assert EXPECTED_KEY == "__codesideluaclass"
    fake = [
        {"rva": 1, "mnemonic": "nop", "op_str": "", "bytes": "90"},
        {"rva": 2, "mnemonic": "lea", "op_str": "rdx, [rip]", "bytes": "48"},
        {"rva": 3, "mnemonic": "call", "op_str": "rax", "bytes": "ff"},
    ]
    assert [x["rva"] for x in instruction_window(fake, 2, 1)] == [1, 2, 3]
    print("SELF_TEST_PASSED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--radius", type=int, default=28)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-text", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output_json is None or args.output_text is None:
        parser.error("--output-json and --output-text are required")
    repo = Path(__file__).resolve().parents[2]
    archive = args.source or newest_archive(repo)
    source = archive / "gow-gameobject-userdata-persistence.json" if archive.is_dir() else archive
    report = analyze(source, args.radius)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text(render_text(report), encoding="utf-8")
    print(report["exact_lookup_corrected_status"])
    print(f"XREFS={report['extracted_xref_count']}/{report['xref_count']}")
    print(f"MISSING={len(report['missing_xrefs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
