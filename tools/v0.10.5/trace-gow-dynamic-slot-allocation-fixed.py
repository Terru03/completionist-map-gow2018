"""Compatibility wrapper for trace-gow-dynamic-slot-allocation.py.

The exact no-hint allocator target at 0x4EF4C0 is executable but is not covered
by a PE runtime-function (.pdata) entry in the supported GoW.exe. Reuse the
original tracer while replacing decode_fn with a bounded exact-target decoder
when no runtime-function entry exists.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ORIGINAL = Path(__file__).with_name("trace-gow-dynamic-slot-allocation.py")
spec = importlib.util.spec_from_file_location("gow_dynamic_slot_original", ORIGINAL)
if spec is None or spec.loader is None:
    raise RuntimeError(f"unable to load original tracer: {ORIGINAL}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_original_decode_fn = mod.decode_fn


def decode_fn_with_fallback(md, pe, rva: int, op_imm, op_mem, rip_reg):
    fn = pe.function_for(rva)
    if fn is not None:
        return _original_decode_fn(md, pe, rva, op_imm, op_mem, rip_reg)

    # Some valid executable entry points in GoW.exe are leaf/thunk-style code
    # without a dedicated .pdata record. Decode from the exact call target up
    # to the next known runtime-function boundary, capped to keep this narrow.
    next_begins = [row["begin"] for row in pe.runtime_functions if row["begin"] > rva]
    next_begin = min(next_begins) if next_begins else rva + 0x400
    end = min(next_begin, rva + 0x400)
    if end <= rva:
        end = rva + 0x100

    rows = mod.decode_window(md, pe, rva, end, op_imm, op_mem, rip_reg)
    if not rows:
        raise RuntimeError(f"fallback decode produced no instructions at 0x{rva:X}")

    # Trim trailing padding once the first return is reached, but preserve
    # unconditional tail-jump entries because 0x4EF4C0 may be a thunk.
    trimmed = []
    for row in rows:
        trimmed.append(row)
        if row["mnemonic"] in ("ret", "retf"):
            break

    actual_end = trimmed[-1]["rva"] + len(bytes.fromhex(trimmed[-1]["bytes"]))
    return {
        "begin": rva,
        "end": actual_end,
        "size": actual_end - rva,
        "instructions": trimmed,
        "boundary_source": "bounded_exact_target_fallback",
        "next_runtime_function": next_begin,
    }


mod.decode_fn = decode_fn_with_fallback

if __name__ == "__main__":
    raise SystemExit(mod.main())
