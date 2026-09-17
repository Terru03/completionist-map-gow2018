#!/usr/bin/env python3
"""Guarded one-line fix for v0.10.5 transaction-mode forwarding."""
from __future__ import annotations

from pathlib import Path


HERE = Path(__file__).resolve().parent
TARGET = HERE / "all-ravens-runtime-test.ps1"
OLD = ". $engine -LibraryOnly"
NEW = ". $engine -Mode $Mode -GameRoot $GameRoot -ConfirmRuntimeTest:$ConfirmRuntimeTest -LibraryOnly"

text = TARGET.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
old_count = text.count(OLD)
new_count = text.count(NEW)

if new_count == 1 and old_count == 0:
    print("ALL_RAVENS_RUNTIME_ARG_FORWARDING_ALREADY_APPLIED")
elif old_count == 1 and new_count == 0:
    TARGET.write_text(text.replace(OLD, NEW, 1), encoding="utf-8", newline="\n")
    print("ALL_RAVENS_RUNTIME_ARG_FORWARDING_APPLIED")
else:
    raise RuntimeError(
        f"runtime forwarding guard failed: old_count={old_count} new_count={new_count}"
    )
