#!/usr/bin/env python3
"""Install, verify, or roll back the Nornir model group isolation test."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_native_installer", HERE / "install-nornir-native-test.py")
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

base.BUILD = base.ROOT / "build/nornir-native-isolated-test"
base.REPORT = base.BUILD / "report.json"
base.BACKUPS = base.BUILD / "backups"
base.EXPECTED_KIND = "NORNIR_SEPARATE_ISOLATED_MARKERS_TEST"
base.RESULT_LABEL = "NORNIR_NATIVE_ISOLATED_TEST"

if __name__ == "__main__":
    base.main()
