"""Build an OFFLINE Raven-only stock SIDE compass A/B control.

The currently installed mapmenu.lua does not contain the older dedicated Raven
ShowMarker(candidate, markerType) bridge. It uses the stock MapOn:ShowOnCompass
path and derives markerType from the marker's authored map flags. This control
therefore leaves that stock path intact and inserts one guarded override directly
before the unique stock ShowMarker(self.currMarkerID, markerType) call.

Only the Completionist Raven is redirected to the stock SIDE CompassIconClass.
Every other map marker continues to use the original stock markerType selection.
The script itself never writes game files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "fb68996fad866acb978d6743b5d6054d0f2a82dba485a307ee810fc100c2be45"
RAVEN_NAME = "Completionist_V103_Veithurgard_Raven_01"
RAVEN_BYTES = RAVEN_NAME.encode("ascii")
SHOW_CALL = b"      game.Compass.ShowMarker(self.currMarkerID, markerType)"
ASSERT_LINE = b'      assert(markerType ~= nil, "unable to find ShowOnCompass marker type")'
BEGIN = b"      -- BEGIN COMPLETIONIST V0.10.4 RAVEN SIDE A/B CONTROL"
END = b"      -- END COMPLETIONIST V0.10.4 RAVEN SIDE A/B CONTROL"
RESULT = "OFFLINE_RAVEN_NATIVE_SIDE_CONTROL_BUILT"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build(raw: bytes) -> tuple[bytes, dict]:
    source_sha = sha256(raw)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            "mapmenu.lua is not the inspected runtime baseline: "
            f"expected {EXPECTED_SOURCE_SHA256}, got {source_sha}"
        )

    show_count = raw.count(SHOW_CALL)
    assert_count = raw.count(ASSERT_LINE)
    raven_count = raw.count(RAVEN_BYTES)
    if show_count != 1:
        raise ValueError(f"expected exactly one stock ShowMarker(self.currMarkerID, markerType), found {show_count}")
    if assert_count != 1:
        raise ValueError(f"expected exactly one stock markerType assertion, found {assert_count}")
    if raven_count < 1:
        raise ValueError("Completionist Raven marker identity is missing from installed mapmenu")
    if raw.count(BEGIN) != 0 or raw.count(END) != 0:
        raise ValueError("Raven SIDE A/B control already appears to be applied")

    show_offset = raw.index(SHOW_CALL)
    assert_offset = raw.index(ASSERT_LINE)
    if not assert_offset < show_offset or show_offset - assert_offset > 512:
        raise ValueError("stock markerType assertion and ShowMarker call are not in the expected local block")

    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    lines = [
        BEGIN,
        b'      local ravenInfoOK, completionistRavenInfo = pcall(function()',
        b'        return game.Map.GetMarkerInfo("' + RAVEN_BYTES + b'")',
        b"      end)",
        b"      local completionistRavenSelected = self.completionistMapV100Selected == true",
        b"      if not completionistRavenSelected and ravenInfoOK and completionistRavenInfo ~= nil then",
        b"        completionistRavenSelected = tostring(self.currMarkerID) == tostring(completionistRavenInfo.Id)",
        b"      end",
        b"      if completionistRavenSelected then",
        b'        markerType = "SIDE"',
        b"      end",
        END,
    ]
    injection = newline.join(lines) + newline
    candidate = raw[:show_offset] + injection + raw[show_offset:]

    if candidate.count(BEGIN) != 1 or candidate.count(END) != 1:
        raise ValueError("SIDE control insertion did not resolve exactly once")
    if candidate.count(SHOW_CALL) != 1:
        raise ValueError("stock ShowMarker call changed during SIDE control insertion")
    if candidate.count(ASSERT_LINE) != 1:
        raise ValueError("stock markerType assertion changed during SIDE control insertion")
    if candidate.count(RAVEN_BYTES) != raven_count + 1:
        raise ValueError("unexpected Raven identity count after SIDE control insertion")
    if candidate[:show_offset] != raw[:show_offset]:
        raise ValueError("bytes before SIDE control insertion changed")
    suffix_start = show_offset + len(injection)
    if candidate[suffix_start:] != raw[show_offset:]:
        raise ValueError("bytes after SIDE control insertion changed")
    if candidate[:show_offset] + candidate[suffix_start:] != raw:
        raise ValueError("removing the inserted SIDE control does not reconstruct source byte-for-byte")

    report = {
        "result": RESULT,
        "source_sha256": source_sha,
        "expected_source_sha256": EXPECTED_SOURCE_SHA256,
        "candidate_sha256": sha256(candidate),
        "source_bytes": len(raw),
        "candidate_bytes": len(candidate),
        "byte_length_delta": len(injection),
        "source_mapmenu_sha256_pinned": True,
        "stock_show_call_count": show_count,
        "stock_assert_count": assert_count,
        "raven_identity_count_before": raven_count,
        "stock_show_call_unchanged": True,
        "only_guarded_raven_side_override_inserted": True,
        "source_reconstructs_exactly_after_removing_insertion": True,
        "insertion_offset": show_offset,
        "insertion_bytes": len(injection),
        "marker_name": RAVEN_NAME,
        "marker_type_before": "stock_flag_derived",
        "marker_type_after": "SIDE",
        "selection_guard": {
            "primary": "self.completionistMapV100Selected == true",
            "fallback": "self.currMarkerID equals game.Map.GetMarkerInfo(Raven).Id",
            "lookup_protected_by_pcall": True,
        },
        "native_marker_id_unchanged": True,
        "native_marker_coordinates_graph_unchanged": True,
        "raven_wad_artwork_unchanged": True,
        "wad_r_perm_dcb_unchanged": True,
        "game_files_written": False,
        "purpose": (
            "A/B control on the actual installed stock MapOn:ShowOnCompass path: if stock SIDE restores "
            "routed/native compass presentation for the exact same Raven marker ID, coordinates and graph, "
            "the remaining custom-class defect is in CompassIconClass behavior/presentation fields."
        ),
    }
    return candidate, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    raw = source.read_bytes()
    candidate, report = build(raw)

    if output == source or report_path == source:
        raise ValueError("offline control output/report must not overlap source")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report["source"] = str(source)
    report["output"] = str(output)
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if source.read_bytes() != raw:
        raise ValueError("source mapmenu changed during offline build")

    print(RESULT)
    print("  installed path: stock MapOn:ShowOnCompass")
    print("  Raven-only markerType override: stock flag-derived -> SIDE")
    print("  stock ShowMarker call unchanged: true")
    print("  same marker ID / coords / graph: true")
    print("  non-Raven map markers changed: false")
    print("  game files written: false")
    print(f"  candidate: {output}")
    print(f"  report:    {report_path}")


if __name__ == "__main__":
    main()
