"""Fixture-free transactional tests for Raven candidate/proof refresh."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
PREPARE_PATH = HERE / "prepare-all-ravens-delivery-candidate.py"

spec = importlib.util.spec_from_file_location("raven_delivery_prepare_test", PREPARE_PATH)
prepare_mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prepare_mod)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class RavenDeliveryPrepareTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "candidate"
        self.report = self.root / "proof.json"
        self.catalogue = self.root / "catalogue.json"
        self.output.mkdir(parents=True)

        self.build = prepare_mod.build
        self.saved = {
            "OUTPUT": self.build.OUTPUT,
            "REPORT": self.build.REPORT,
            "CATALOGUE": self.build.CATALOGUE,
            "SOURCE_HASHES": dict(self.build.SOURCE_HASHES),
            "write_bytes_atomic": self.build.stage.write_bytes_atomic,
        }

        source_catalogue = json.loads(
            (HERE.parents[1] / "catalogue" / "odins-ravens.json").read_text(
                encoding="utf-8"
            )
        )
        self.catalogue.write_text(
            json.dumps(source_catalogue, sort_keys=True), encoding="utf-8"
        )

        self.build.OUTPUT = self.output
        self.build.REPORT = self.report
        self.build.CATALOGUE = self.catalogue

        self.map_base = b"fixture-map-base"
        self.event_base = b"fixture-event-base"
        source_hashes = dict(self.saved["SOURCE_HASHES"])
        source_hashes[self.build.MAP_LUA] = sha(self.map_base)
        source_hashes[self.build.EVENT_LUA] = sha(self.event_base)
        self.build.SOURCE_HASHES = source_hashes

        self.binary_bytes = {
            self.build.MASTER: b"fixture-mapmaster-binary",
            self.build.COORDS: b"fixture-mapcoords-binary",
            self.build.POOL: b"fixture-ui-pool-binary",
        }
        self.generated_before = {
            self.build.MAP_LUA: self.map_base
            + b"\n-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS\n-- old map hook\n",
            self.build.EVENT_LUA: self.event_base
            + b"\n-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS\n-- old event hook\n",
        }

        files: dict[str, dict[str, int | str]] = {}
        for relative, raw in {**self.binary_bytes, **self.generated_before}.items():
            path = self.output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            files[relative] = {"sha256": sha(raw), "bytes": len(raw)}

        self.proof_before_obj = {
            "ready_for_runtime_test": True,
            "files": files,
            "router": {"old": True},
            "state": {"old": True},
        }
        self.proof_before = json.dumps(
            self.proof_before_obj, sort_keys=True, indent=2
        ).encode("utf-8")
        self.report.write_bytes(self.proof_before)

        self.all_paths = [
            self.output / self.build.MASTER,
            self.output / self.build.COORDS,
            self.output / self.build.POOL,
            self.output / self.build.MAP_LUA,
            self.output / self.build.EVENT_LUA,
            self.report,
        ]
        self.before_bytes = {path: path.read_bytes() for path in self.all_paths}

    def tearDown(self):
        self.build.OUTPUT = self.saved["OUTPUT"]
        self.build.REPORT = self.saved["REPORT"]
        self.build.CATALOGUE = self.saved["CATALOGUE"]
        self.build.SOURCE_HASHES = self.saved["SOURCE_HASHES"]
        self.build.stage.write_bytes_atomic = self.saved["write_bytes_atomic"]
        self.temp.cleanup()

    def assert_exact_pre_refresh_state(self):
        for path, expected in self.before_bytes.items():
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.read_bytes(), expected, path)

    def inject_failure_on_write(self, fail_at: int):
        original = self.saved["write_bytes_atomic"]
        calls = {"count": 0}

        def failing_write(root, path, raw, label):
            calls["count"] += 1
            if calls["count"] == fail_at:
                raise RuntimeError(f"INJECTED_WRITE_FAILURE_{fail_at}")
            return original(root, path, raw, label)

        self.build.stage.write_bytes_atomic = failing_write
        return calls

    def test_refresh_rolls_back_every_file_when_each_write_position_fails(self):
        # The success path writes map Lua, event Lua and then proof JSON.
        for fail_at in (1, 2, 3):
            with self.subTest(fail_at=fail_at):
                self.assert_exact_pre_refresh_state()
                calls = self.inject_failure_on_write(fail_at)
                with self.assertRaisesRegex(
                    RuntimeError, f"INJECTED_WRITE_FAILURE_{fail_at}"
                ):
                    prepare_mod.prepare(check_only=False, refresh_proof=True)
                self.assertEqual(calls["count"], fail_at)
                self.assert_exact_pre_refresh_state()
                self.build.stage.write_bytes_atomic = self.saved[
                    "write_bytes_atomic"
                ]

    def test_success_refresh_changes_only_generated_payloads_and_metadata(self):
        binary_before = {
            relative: (self.output / relative).read_bytes()
            for relative in self.binary_bytes
        }
        binary_proof_before = {
            relative: dict(self.proof_before_obj["files"][relative])
            for relative in self.binary_bytes
        }

        prepare_mod.prepare(check_only=False, refresh_proof=True)
        prepare_mod.prepare(check_only=True, refresh_proof=False)

        proof_after = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(set(proof_after["files"]), set(self.proof_before_obj["files"]))

        for relative, raw in binary_before.items():
            self.assertEqual((self.output / relative).read_bytes(), raw)
            self.assertEqual(proof_after["files"][relative], binary_proof_before[relative])

        catalogue = json.loads(self.catalogue.read_text(encoding="utf-8"))
        for relative in (self.build.MAP_LUA, self.build.EVENT_LUA):
            spec = prepare_mod.GENERATED[relative]
            base = self.map_base if relative == self.build.MAP_LUA else self.event_base
            hook = self.build.render_lua(
                catalogue,
                spec["template"],
                spec["token"],
                spec["state_rows"],
            )
            expected = base + b"\n" + hook
            actual = (self.output / relative).read_bytes()
            self.assertEqual(actual, expected)
            self.assertEqual(proof_after["files"][relative]["sha256"], sha(expected))
            self.assertEqual(proof_after["files"][relative]["bytes"], len(expected))

        self.assertEqual(proof_after["router"], self.build.router_contract())
        self.assertEqual(proof_after["state"], self.build.state_contract())

    def test_file_set_mismatch_refuses_before_any_write(self):
        extra = self.output / "unexpected.bin"
        extra.write_bytes(b"unexpected")
        calls = {"count": 0}
        original = self.saved["write_bytes_atomic"]

        def counting_write(root, path, raw, label):
            calls["count"] += 1
            return original(root, path, raw, label)

        self.build.stage.write_bytes_atomic = counting_write
        with self.assertRaisesRegex(ValueError, "candidate file set differs"):
            prepare_mod.prepare(check_only=False, refresh_proof=True)
        self.assertEqual(calls["count"], 0)
        extra.unlink()
        self.assert_exact_pre_refresh_state()

    def test_binary_tamper_refuses_before_any_write(self):
        binary = self.output / self.build.MASTER
        binary.write_bytes(b"tampered")
        calls = {"count": 0}
        original = self.saved["write_bytes_atomic"]

        def counting_write(root, path, raw, label):
            calls["count"] += 1
            return original(root, path, raw, label)

        self.build.stage.write_bytes_atomic = counting_write
        with self.assertRaisesRegex(ValueError, "accepted candidate differs"):
            prepare_mod.prepare(check_only=False, refresh_proof=True)
        self.assertEqual(calls["count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
