"""Run the existing GameObject token allocator tracer with safe leaf-function fallbacks.

The supported GoW.exe contains several exact native leaf helpers that have no
x64 .pdata unwind entry. The base tracer is intentionally reused here; this
wrapper only teaches its PE.function_for lookup to synthesize a bounded code
range when one of the exact known target entrypoints is missing from .pdata.

Read-only static analysis only. No game launch and no save I/O.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / "trace-gameobject-token-allocator.py"

spec = importlib.util.spec_from_file_location("completionist_token_allocator_base", BASE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load base tracer: {BASE}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_original_function_for = mod.PE.function_for
_target_entries = sorted(set(mod.TARGETS.values()))


def _bounded_target_end(pe, entry: int) -> int:
    later = [value for value in _target_entries if value > entry]
    end = min(entry + 0x200, later[0] if later else entry + 0x200)
    section = pe.section_for_rva(entry)
    if section is not None:
        section_end = section["rva"] + max(section["vsize"], section["rawsize"])
        end = min(end, section_end)
    if end <= entry:
        raise RuntimeError(f"Invalid synthesized target span for {entry:#x}")
    return end


def _function_for_with_leaf_fallback(self, rva: int):
    row = _original_function_for(self, rva)
    if row is not None:
        return row
    # Only synthesize boundaries for the exact, version-locked target entries.
    # Arbitrary addresses remain unresolved/fail-closed.
    if rva not in _target_entries:
        return None
    return {
        "begin": rva,
        "end": _bounded_target_end(self, rva),
        "unwind": 0,
        "synthetic_leaf": True,
    }


mod.PE.function_for = _function_for_with_leaf_fallback

if __name__ == "__main__":
    mod.main()
