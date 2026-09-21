#!/usr/bin/env python3
"""Pin EXE and archive exact Channel A / Lua restore instruction windows."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
WINDOWS = {
    "channel_a_writer": (0x82B250, 0x82B42D),
    "lua_bit_writer": (0x23F9C0, 0x23FA94),
    "channel_a_read_and_cursor_reset": (0x6740E1, 0x674133),
    "bit_reader_init_and_slot_lookup": (0x82C4E0, 0x82C6A0),
    "lua_bit_reader": (0x23FE12, 0x23FE97),
    "checkpoint_luaclient_restore_call": (0x24001D, 0x240078),
    "msb_bit_read": (0xA20280, 0xA20326),
    "msb_bit_write": (0xA20220, 0xA20280),
    "descriptor_reader": (0x667380, 0x667470),
    "pool_remove_and_rebase": (0x667230, 0x6672C0),
    "record_ingest": (0x82CF00, 0x82D658),
    "record_creation": (0x82C820, 0x82CD76),
    "channel_a_retirement": (0x82D760, 0x82DA64),
    "channel_b_retirement": (0x82D660, 0x82D74B),
    "staged_checkpoint_writer": (0x6687F0, 0x668AB4),
    "checkpoint_record_apply": (0x66BA10, 0x66C058),
    "record_asset_binding": (0x549481, 0x54961E),
    "record_loaded_owner": (0x25CFD0, 0x25D5B3),
    "full_wad_bit_restore": (0x23FAA0, 0x240078),
    "live_client_roundtrip": (0x464EF0, 0x465225),
    "client_onpickle_carrier_producer": (0x5B2130, 0x5B227A),
    "client_context_clear": (0x5A6260, 0x5A6269),
    "client_restore_and_deferred_copy": (0x5B2280, 0x5B249F),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--capstone-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("bridge", HERE / "trace-checkpoint-restore-bridge.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    digest = bridge.sha256(args.exe)
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {digest}")
    pe = bridge.PE(args.exe.read_bytes())
    sys.path.insert(0, str(args.capstone_path))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    blocks = {}
    lines = ["Staged WAD bitstream boundary: pinned static evidence", f"exe_sha256={digest}",
             f"preferred_image_base=0x{pe.image_base:X}", "All instruction labels are RVAs."]
    for name, (start, end) in WINDOWS.items():
        rows = []
        lines.extend(["", f"{name} 0x{start:X}..0x{end:X}"])
        for ins in md.disasm(pe.read(start, end - start), pe.image_base + start):
            targets = [ins.address + ins.size + op.mem.disp - pe.image_base
                       for op in ins.operands if op.type == 3 and ins.reg_name(op.mem.base) == "rip"]
            row = {"rva": ins.address - pe.image_base, "bytes": ins.bytes.hex(),
                   "mnemonic": ins.mnemonic, "operands": ins.op_str, "rip_target_rvas": targets}
            rows.append(row)
            suffix = " ".join(f"RIP=0x{x:X}" for x in targets)
            lines.append(f"{row['rva']:08X} {row['bytes']:22} {ins.mnemonic:7} {ins.op_str} {suffix}")
        blocks[name] = rows
    report = {"exe_sha256": digest, "image_base": pe.image_base, "windows": blocks,
              "mode": "static_read_only", "game_launched": False, "process_accessed": False}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "instructions.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "instructions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"STATIC_BITSTREAM_BOUNDARY_COMPLETE windows={len(blocks)} sha256={digest}")


if __name__ == "__main__":
    main()
