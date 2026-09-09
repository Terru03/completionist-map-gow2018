#!/usr/bin/env python3
"""Summarize the already-generated Raven in-world resource trace without rescanning game files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TARGET_ORDER = (
    "DockPoint.InWorld_tMPIcon_Name",
    "SIDE.InWorld_tMPIcon_Name",
    "CompletionistRaven.HUD_IconName_control",
    "DockPoint.HUD_IconName_control",
)


def rel(path: str, game_root: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(game_root).resolve())).replace("\\", "/")
    except Exception:
        return path.replace("\\", "/")


def compact_ascii(value: str) -> str:
    text = " ".join(value.split())
    if len(text) > 180:
        return text[:177] + "..."
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        type=Path,
        default=Path("build/v0.10.4-raven-inworld-trace/inworld-resource-trace.json"),
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=Path("build/v0.10.4-raven-inworld-trace/inworld-resource-topology-summary.json"),
    )
    args = ap.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"trace report not found: {args.input}")
    report = json.loads(args.input.read_text(encoding="utf-8"))
    if report.get("result") != "READ_ONLY_RAVEN_INWORLD_RESOURCE_TRACE":
        raise ValueError("input is not the expected Raven in-world trace report")

    game_root = str(report.get("game_root", ""))
    rows: list[dict] = []
    for file_row in report.get("files_with_findings", []):
        path = str(file_row.get("path", ""))
        relative = rel(path, game_root)
        target_hits = file_row.get("target_hits", {}) or {}
        ascii_hits = file_row.get("ascii_hits", {}) or {}
        for label, hits in target_hits.items():
            for hit in hits:
                rows.append(
                    {
                        "target": label,
                        "path": relative,
                        "offset": hit.get("offset"),
                        "offset_hex": hit.get("offset_hex"),
                        "context_hex": hit.get("context_hex"),
                        "ascii_context": compact_ascii(str(hit.get("ascii_context", ""))),
                        "file_sha256": file_row.get("sha256"),
                        "same_file_ascii_hints": sorted(ascii_hits.keys()),
                    }
                )

    summary = {
        "schema": 1,
        "result": "RAVEN_INWORLD_RESOURCE_TOPOLOGY_SUMMARY",
        "source_trace": str(args.input),
        "files_scanned": report.get("files_scanned"),
        "target_hit_counts": report.get("target_hit_counts"),
        "hits": rows,
        "game_files_written": False,
        "interpretation_gate": (
            "Use these exact file/offset pairs to identify the DockPoint/SIDE in-world resource domain. "
            "Do not bind a custom Raven InWorld_tMPIcon_Name until the corresponding physical resource "
            "and registration topology are identified."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("RAVEN_INWORLD_RESOURCE_TOPOLOGY_SUMMARY")
    print(f"  source: {args.input}")
    for label in TARGET_ORDER:
        matching = [r for r in rows if r["target"] == label]
        print(f"\n{label}: {len(matching)} hit(s)")
        for row in matching:
            hints = ",".join(row["same_file_ascii_hints"]) if row["same_file_ascii_hints"] else "none"
            print(f"  {row['path']} @ {row['offset_hex']}  ascii-hints={hints}")
            if row["ascii_context"]:
                print(f"    ascii: {row['ascii_context']}")
            if row["context_hex"]:
                print(f"    hex:   {row['context_hex']}")
    print("\n  game files written: false")
    print(f"  output: {args.output}")


if __name__ == "__main__":
    main()
