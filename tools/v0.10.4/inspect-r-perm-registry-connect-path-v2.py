"""Corrected runner for the read-only R_Perm registry connect-path trace.

The original tracer's transfer guard accidentally read 29 bytes while the
already-proven transfer sequence is 28 bytes. That made the guard fail on the
pinned executable even though the sequence was unchanged. This wrapper reuses
all parsing/graph helpers from the original tracer and performs the same scan
with the byte-exact 28-byte guard.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
BASE_SCRIPT = HERE / "inspect-r-perm-registry-connect-path.py"

spec = importlib.util.spec_from_file_location("rperm_connect_base", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load base tracer: {BASE_SCRIPT}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    exe = game / "GoW.exe"
    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("report must remain outside the game directory")
    if not exe.is_file():
        raise FileNotFoundError(exe)
    digest = m.sha256(exe)
    if digest != m.EXPECTED_EXE:
        raise ValueError(f"GoW.exe SHA mismatch: {digest}")

    pe = m.PE(exe.read_bytes())
    funcs = m.runtime_functions(pe)
    calls = m.all_direct_calls(pe, funcs)
    graph = m.build_graph(calls)
    writes = m.source_slot_writes(pe, funcs)
    writer_owners = {
        int(w["owner"]["begin_rva"], 16)
        for w in writes
        if w["owner"] is not None
    }

    connect_bytes = pe.read_rva(m.RPERM_CONNECT_CALL_SITE, 5)
    if connect_bytes[0] != 0xE8:
        raise ValueError("R_Perm connect call encoding changed")
    rel = struct.unpack_from("<i", connect_bytes, 1)[0]
    if m.RPERM_CONNECT_CALL_SITE + 5 + rel != m.RPERM_CONNECT_TARGET:
        raise ValueError("R_Perm connect call target changed")

    expected_transfer = bytes.fromhex(
        "488B1D70C7BB0048891DD19FC40148892D62C7BB0048891DA3BF9901"
    )
    transfer_window = pe.read_rva(m.TRANSFER_SITE, len(expected_transfer))
    if transfer_window != expected_transfer:
        raise ValueError(
            "registry transfer sequence changed: "
            f"expected={expected_transfer.hex().upper()} actual={transfer_window.hex().upper()}"
        )

    roots = {}
    for label, addr in m.PRE_OWNER_ROOTS.items():
        p = m.shortest_path(graph, addr, writer_owners, 6)
        roots[label] = {
            "root_rva": f"0x{addr:X}",
            "shortest_direct_call_path_to_source_writer": (
                None if p is None else [f"0x{x:X}" for x in p]
            ),
            "summary": m.fn_summary(pe, funcs, calls, addr),
        }

    reachable_writers = {}
    for label, row in roots.items():
        p = row["shortest_direct_call_path_to_source_writer"]
        if p:
            reachable_writers[label] = p[-1]

    unique_writer_summaries = []
    for owner in sorted(writer_owners):
        owner_writes = [
            w for w in writes
            if w["owner"] and int(w["owner"]["begin_rva"], 16) == owner
        ]
        unique_writer_summaries.append({
            "owner": m.fn_summary(pe, funcs, calls, owner),
            "writes": owner_writes,
        })

    owner_caller_fn = next((f for f in funcs if f["begin"] == m.OWNER_CALLER), None)
    pre_owner_calls = []
    if owner_caller_fn:
        for c in calls:
            if c["owner"] == m.OWNER_CALLER and c["site"] < m.OWNER_CALL_SITE:
                pre_owner_calls.append({
                    "site_rva": f"0x{c['site']:X}",
                    "target_rva": f"0x{c['target_owner']:X}",
                })

    transfer_fn = next((f for f in funcs if f["begin"] == m.TRANSFER_OWNER), None)
    transfer_strings = (
        [] if transfer_fn is None
        else m.ascii_rip_refs(pe, transfer_fn["begin"], transfer_fn["end"])
    )
    rperm_strings = [
        r for r in transfer_strings
        if r["text"] in (
            "R_Perm", "ST_Global", "LT_Global", "BL_Global",
            "resource_dependency_graph"
        ) or "Connecting" in r["text"]
    ]

    if roots["rperm_connect_421040"]["shortest_direct_call_path_to_source_writer"]:
        conclusion = "R_PERM_CONNECT_DIRECT_CALL_GRAPH_REACHES_SOURCE_WRITER"
        next_gate = (
            "Inspect the identified writer path and the registry object it publishes. "
            "Then map that object's object/name/type index back to R_Perm authored data "
            "before modifying any DCB or WAD."
        )
    elif any(v for k, v in reachable_writers.items() if k != "owner_caller_682020"):
        conclusion = "R_PERM_PRETRANSFER_HELPER_REACHES_SOURCE_WRITER"
        next_gate = (
            "Inspect the reachable pre-transfer writer path and prove which R_Perm loader "
            "callback supplies 0x12390E0. Do not bypass ShowMarker or patch another data file yet."
        )
    else:
        conclusion = "R_PERM_SOURCE_WRITE_REQUIRES_INDIRECT_CALL_TRACE"
        next_gate = (
            "The source writer is not reachable through direct E8 calls from the R_Perm "
            "connect/pre-transfer roots, so resolve the indirect/vtable callback used by "
            "RVA 0x421040 or the immediately preceding owner-caller helpers."
        )

    report = {
        "result": m.RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": str(exe),
        "source_sha256": digest,
        "guard_fix": {
            "original_bug": "transfer guard read 29 bytes for a 28-byte proven sequence",
            "validated_bytes": len(expected_transfer),
            "transfer_sequence_hex": expected_transfer.hex().upper(),
        },
        "known_handoff": {
            "source_slot_rva": f"0x{m.SOURCE_SLOT:X}",
            "registry_slot_rva": f"0x{m.REGISTRY_SLOT:X}",
            "alias_slot_rva": f"0x{m.ALIAS_SLOT:X}",
            "transfer_owner_rva": f"0x{m.TRANSFER_OWNER:X}",
            "transfer_site_rva": f"0x{m.TRANSFER_SITE:X}",
            "rperm_connect_call_site_rva": f"0x{m.RPERM_CONNECT_CALL_SITE:X}",
            "rperm_connect_target_rva": f"0x{m.RPERM_CONNECT_TARGET:X}",
            "rperm_related_strings_in_transfer_owner": rperm_strings,
        },
        "source_slot_writes": {
            "instruction_count": len(writes),
            "owner_function_count": len(writer_owners),
            "writes": writes,
            "writer_owner_summaries": unique_writer_summaries,
        },
        "root_reachability": roots,
        "reachable_writer_by_root": reachable_writers,
        "owner_caller_pre_transfer_direct_calls": pre_owner_calls,
        "conclusion": conclusion,
        "next_gate": next_gate,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(m.RESULT)
    print("  transfer guard: 28-byte sequence validated")
    print(f"  source-slot write instructions: {len(writes)}; writer owners: {len(writer_owners)}")
    for label, row in roots.items():
        p = row["shortest_direct_call_path_to_source_writer"]
        print(f"  {label}: {' -> '.join(p) if p else 'no direct-call path <=6'}")
    print(f"  conclusion: {conclusion}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
