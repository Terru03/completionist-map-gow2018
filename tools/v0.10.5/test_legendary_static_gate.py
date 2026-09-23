"""Offline checks for the Legendary generation gate."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import unittest

import legendary_static_gate as gate


class LegendaryStaticGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = tuple(json.loads(path.read_text(encoding="utf-8")) for path in (
            gate.CATALOGUE, gate.AUDIT, gate.IDENTITIES, gate.SCOPE, gate.SEMANTICS,
            gate.MARKER_ASSETS
        ))

    def test_real_evidence_stays_fail_closed(self) -> None:
        report = gate.assess(*self.inputs)
        self.assertEqual(report["status"], "BLOCKED_FAIL_CLOSED")
        self.assertFalse(report["runtime_generation_allowed"])
        self.assertEqual(report["exact_identity_count"], 33)
        self.assertEqual(report["observed_exact_staged_state_count"], 32)
        self.assertEqual(report["direct_native_binding_count"], 0)
        self.assertEqual(len(report["unresolved_catalogue_ids"]), 2)
        with self.assertRaisesRegex(ValueError, "Legendary generation blocked"):
            gate.require_generation_ready(report)

    def test_unresolved_keys_have_exact_frozen_states_but_stay_unresolved(self) -> None:
        rows = gate.diagnose_unresolved(self.inputs[0])
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["state_float32"] for r in rows}, {4.0})
        self.assertEqual(len({r["serialized_flag1_hex"] for r in rows}), 2)

    def test_ownership_table_keeps_proposed_regions_unproved(self) -> None:
        rows = gate.assess(*self.inputs)["ownership_proof_rows"]
        self.assertEqual(len(rows), 35)
        self.assertTrue(all(row["region_name"] is None for row in rows))
        self.assertTrue(all(row["proof_strength"] ==
                            "placement_and_identity_only_no_direct_region_binding"
                            for row in rows))
        self.assertEqual(sum(row["production_eligibility"] == "tracked_collectible"
                             for row in rows), 33)
        self.assertEqual({row["wad"] for row in rows if row["wad"] in {
            "stn200_lakeext.wad", "xpl300_stronghold.wad",
            "cal500_runevault.wad", "cal740_leftwing.wad"}}, {
            "stn200_lakeext.wad", "xpl300_stronghold.wad",
            "cal500_runevault.wad", "cal740_leftwing.wad"})

    def test_invented_binding_flag_cannot_promote_inferred_row(self) -> None:
        inputs = copy.deepcopy(self.inputs)
        row = next(r for r in inputs[0]["collectibles"]
                   if r.get("family") == "legendary_chest" and
                   r.get("production_eligibility") == "tracked_collectible")
        row["progression"]["native_binding_evidence"] = {"status": "PASS_EXACT"}
        report = gate.assess(*inputs)
        selected = next(r for r in report["candidate_rows"]
                        if r["catalogue_id"] == row["catalogue_id"])
        self.assertFalse(selected["direct_native_binding_proven"])

    def test_changed_serialized_identity_is_rejected(self) -> None:
        inputs = copy.deepcopy(self.inputs)
        inputs[3]["production_rows"][0]["serialized_flag1_hex"] = "00" * 17
        with self.assertRaisesRegex(ValueError, "serialized identity differs"):
            gate.assess(*inputs)

    def test_changed_candidate_membership_is_rejected(self) -> None:
        inputs = copy.deepcopy(self.inputs)
        inputs[3]["production_catalogue_ids"].pop()
        with self.assertRaisesRegex(ValueError, "candidate sets differ"):
            gate.assess(*inputs)

    def test_missing_opened_state_proof_is_rejected(self) -> None:
        inputs = copy.deepcopy(self.inputs)
        inputs[4]["status"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "OPENED scalar proof missing"):
            gate.assess(*inputs)

    def test_malformed_staged_state_is_rejected(self) -> None:
        inputs = copy.deepcopy(self.inputs)
        row = next(r for r in inputs[2]["identities"] if r.get("staged_state"))
        row["staged_state"]["state_raw_hex"] = "00"
        with self.assertRaisesRegex(ValueError, "malformed staged state token"):
            gate.assess(*inputs)

    def test_catalogue_checkout_and_git_blob_have_same_content(self) -> None:
        path = gate.CATALOGUE
        blob = subprocess.check_output(["git", "show", "HEAD:config/collectibles/v0.10.5/all-collectibles.json"], cwd=gate.REPO)
        self.assertEqual(hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                         hashlib.sha256(blob).hexdigest())

    def test_marker_asset_audit_cannot_promote_generation(self) -> None:
        inputs = copy.deepcopy(self.inputs)
        inputs[5]["custom_marker_resource_ready"] = True
        with self.assertRaisesRegex(ValueError, "asset audit differs or attempts promotion"):
            gate.assess(*inputs)


if __name__ == "__main__":
    unittest.main()
