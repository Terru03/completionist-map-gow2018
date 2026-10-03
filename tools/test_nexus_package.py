"""Test installer preflight before game files change."""

import hashlib
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("nexus_package", Path(__file__).with_name("build-nexus-package.py"))
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class PackageBuilderTests(unittest.TestCase):
    def make_source(self, source):
        for relative in PACKAGE.MOD_FILES:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture payload")
        bridge = source / "mods/completionist-map/native/collectible-base-dxgi.dll"
        (source / "dxgi.dll").write_bytes(b"fixture pin " + PACKAGE.sha256(bridge).encode("ascii"))
        (source / "mods/completionist-map/native/raven-native-bridge-manifest.json").write_text("{}")

    def test_inputs_inside_output_rejected_without_delete(self):
        for input_kind in ("source", "capacity", "bridge"):
            with self.subTest(input_kind=input_kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                output = root / "dist/package"
                output.mkdir(parents=True)
                source = output / "source" if input_kind == "source" else root / "source"
                self.make_source(source)
                capacity = source / "dxgi.dll"
                bridge = source / "mods/completionist-map/native/collectible-base-dxgi.dll"
                if input_kind == "capacity":
                    capacity = output / "capacity.dll"
                    capacity.write_bytes((source / "dxgi.dll").read_bytes())
                if input_kind == "bridge":
                    bridge = output / "bridge.dll"
                    bridge.write_bytes((source / "mods/completionist-map/native/collectible-base-dxgi.dll").read_bytes())
                sentinel = output / "keep.txt"
                sentinel.write_bytes(b"previous package")
                with mock.patch.multiple(PACKAGE, DIST=output.parent, PKG_DIR=output), redirect_stdout(io.StringIO()):
                    with self.assertRaises(ValueError):
                        PACKAGE.build(source, capacity, bridge)
                self.assertTrue(source.is_dir())
                self.assertTrue(capacity.is_file())
                self.assertTrue(bridge.is_file())
                self.assertEqual(sentinel.read_bytes(), b"previous package")

    def test_mismatched_pair_keeps_previous_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "source", root / "dist/package"
            self.make_source(source)
            (source / "dxgi.dll").write_bytes(b"wrong pinned bridge")
            output.mkdir(parents=True)
            sentinel = output / "keep.txt"
            sentinel.write_bytes(b"previous package")
            with mock.patch.multiple(PACKAGE, DIST=output.parent, PKG_DIR=output), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "bridge DLL hash"):
                    PACKAGE.build(source)
            self.assertEqual(sentinel.read_bytes(), b"previous package")


class InstallerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.source = self.root / "package"
        self.game.mkdir()
        (self.source / "scripts").mkdir(parents=True)
        self.exe = b"test executable"
        (self.game / "GoW.exe").write_bytes(self.exe)
        self.relative = "exec/dc/pc_le/mapcoords.dcb"
        self.stock = self.game / self.relative
        self.stock.parent.mkdir(parents=True)
        self.stock.write_bytes(b"stock map coordinates")
        self.payload = self.source / self.relative
        self.payload.parent.mkdir(parents=True)
        self.payload.write_bytes(b"mod map coordinates")
        self.boot = self.game / "exec/boot-options.json"
        self.boot.write_bytes(b'{"patch-texpacks":["stock"]}')
        (self.source / "scripts/install.ps1").write_text(PACKAGE.INSTALL_PS1, encoding="utf-8")

    def manifest(self, supported_hash):
        value = {
            "supported_exe_sha256": supported_hash,
            "files": {self.relative: {"sha256": hashlib.sha256(self.payload.read_bytes()).hexdigest()}},
        }
        (self.source / "manifest.json").write_text(json.dumps(value), encoding="utf-8")

    def install(self):
        environment = os.environ.copy()
        # Use Windows PowerShell modules, not paths from parent PowerShell 7.
        environment.pop("PSMODULEPATH", None)
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(self.source / "scripts/install.ps1"), "-TargetDir", str(self.game)],
            capture_output=True, text=True, timeout=30, env=environment,
        )

    def assert_untouched(self):
        self.assertEqual(self.stock.read_bytes(), b"stock map coordinates")
        self.assertEqual(self.boot.read_bytes(), b'{"patch-texpacks":["stock"]}')
        self.assertFalse((self.game / "completionist_backup").exists())

    def test_unsupported_executable_rejected_before_game_write(self):
        self.manifest("caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452")
        result = self.install()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("unsupported", result.stdout.lower())
        self.assert_untouched()

    def test_corrupt_payload_rejected_before_game_write(self):
        self.manifest(hashlib.sha256(self.exe).hexdigest())
        self.payload.write_bytes(b"corrupt package")
        result = self.install()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("hash", result.stdout.lower())
        self.assert_untouched()

    def test_missing_payload_rejected_before_game_write(self):
        self.manifest(hashlib.sha256(self.exe).hexdigest())
        self.payload.unlink()
        result = self.install()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_untouched()

    def test_invalid_boot_options_rejected_before_game_write(self):
        self.manifest(hashlib.sha256(self.exe).hexdigest())
        self.boot.write_bytes(b"not json")
        result = self.install()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stock.read_bytes(), b"stock map coordinates")
        self.assertEqual(self.boot.read_bytes(), b"not json")
        self.assertFalse((self.game / "completionist_backup").exists())

    def test_supported_install_registers_artwork_and_backs_up_stock(self):
        self.manifest(hashlib.sha256(self.exe).hexdigest())
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stock.read_bytes(), self.payload.read_bytes())
        self.assertEqual((self.game / "completionist_backup" / self.relative).read_bytes(), b"stock map coordinates")
        boot = json.loads(self.boot.read_text(encoding="utf-8-sig"))
        self.assertEqual(boot["patch-texpacks"], ["stock", "../../patch/pc_le/completionist_v105_family_art"])

    def test_repeat_install_keeps_original_backup_and_one_artwork_entry(self):
        self.manifest(hashlib.sha256(self.exe).hexdigest())
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.game / "completionist_backup" / self.relative).read_bytes(), b"stock map coordinates")
        boot = json.loads(self.boot.read_text(encoding="utf-8-sig"))
        self.assertEqual(boot["patch-texpacks"], ["stock", "../../patch/pc_le/completionist_v105_family_art"])


if __name__ == "__main__":
    unittest.main()
