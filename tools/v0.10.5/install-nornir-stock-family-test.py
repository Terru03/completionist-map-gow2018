#!/usr/bin/env python3
"""Install, verify, or roll back Nornir IDs using existing game artwork."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_stock_installer", HERE / "install-nornir-map-id-test.py")
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

base.BUILD = base.ROOT / "build/nornir-stock-family-test"
base.REPORT = base.BUILD / "report.json"
base.BACKUPS = base.BUILD / "backups"
base.EXPECTED_KIND = "NORNIR_STOCK_FAMILY_MARKERS_TEST"
base.RESULT_LABEL = "NORNIR_STOCK_FAMILY_TEST"

if __name__ == "__main__":
    base.main()
