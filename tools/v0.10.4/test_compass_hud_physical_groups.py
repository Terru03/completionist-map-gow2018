"""Offline role, clone, count, and path safety tests. No game files needed."""
import copy
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


MODULE = Path(__file__).with_name("compass_hud_physical_groups.py")
if MODULE.exists():
    spec = importlib.util.spec_from_file_location("hud_groups_test", MODULE)
    hud = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hud)
else:
    hud = None


def record(kind=1, flags=0, name="", rid=bytes(16), data=b"", parent=0):
    return {"kind": kind, "flags": flags, "name": name, "id": rid,
            "data": bytearray(data), "parent": parent, "header": bytearray(96),
            "padding": bytes((-len(data)) % 16), "original_offset": 0,
            "payload_index": 0 if data else None}


def group(role="model"):
    shape = {"model": (0x8E, 80, 0x1002000C),
             "prototype": (0x3D, 1184, 0x10001), "root": (0x3D, 164, 0x20001)}
    flags, size, key = shape[role]
    data = bytearray(size)
    struct.pack_into("<I", data, 0, key)
    rows = [record(2, name="GroupStart", rid=b"S" * 16, parent=None),
            record(flags=flags, name="source", rid=b"D" * 16, data=data)]
    if role == "prototype":
        struct.pack_into("<H", rows[1]["data"], 0xC, 2)
        struct.pack_into("<I", rows[1]["data"], 0x18, 0x3A8)
        rows[1]["data"][0x3A8:0x3B8] = b"D" * 16
        rows.extend([record(name="model", rid=b"M" * 16),
                     record(flags=0x18, name="SCP_source", rid=b"X" * 16,
                            data=struct.pack("<I", 0x10005) + bytes(92))])
    elif role == "model":
        rows.extend([record(name="material", rid=b"A" * 16),
                     record(name="mesh", rid=b"B" * 16)])
    elif role == "root":
        rows[1]["data"][0x1C:0x54] = b"source" + bytes(50)
    rows.append(record(3, name="GroupEnd", rid=b"E" * 16))
    return rows


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(hud, "physical group implementation missing")

    def test_generic_boundaries_are_not_definition_aliases(self):
        rows = group()
        roles = hud.group_roles(rows, 1)
        self.assertEqual([r["role"] for r in roles],
                         ["group_start", "target_payload", "dependency_link", "dependency_link", "group_end"])
        self.assertEqual([r["depth"] for r in roles], [0, 1, 1, 1, 0])

    def test_script_is_payload_not_zero_data_link(self):
        rows = group("prototype")
        roles = hud.group_roles(rows, 1)
        self.assertEqual(roles[3]["role"], "auxiliary_payload")
        self.assertEqual(hud.validate_hud_group(rows, 1, "prototype")["payload_count"], 2)

    def test_names_do_not_define_roles(self):
        rows = group()
        for row in rows:
            row["name"] = "same_name"
        self.assertEqual(hud.validate_hud_group(rows, 1, "model")["payload_count"], 1)

    def test_clone_changes_only_selected_definition_and_local_link(self):
        rows = group()
        before = copy.deepcopy(rows)
        clone = hud.clone_resource(rows, 1, "new", b"N" * 16,
                                   links={2: (b"A" * 16, "raven_mat", b"R" * 16)})
        self.assertEqual(rows, before)
        self.assertEqual(clone[1]["name"], "new")
        self.assertEqual(clone[1]["id"], b"N" * 16)
        self.assertEqual(clone[2]["id"], b"R" * 16)
        self.assertEqual(clone[2]["name"], "raven_mat")
        for i in [0, 3, 4]:
            self.assertEqual(hud.BASE.load_helper().record_bytes(clone[i]),
                             hud.BASE.load_helper().record_bytes(before[i]))

    def test_nested_same_name_and_id_stay_unchanged(self):
        rows = group()
        rows[4:4] = [record(2, name="source", rid=b"D" * 16),
                     record(name="source", rid=b"D" * 16, parent=4),
                     record(3, name="source", rid=b"D" * 16, parent=4)]
        clone = hud.clone_resource(rows, 1, "new", b"N" * 16)
        for i in [4, 5, 6]:
            self.assertEqual(clone[i]["name"], "source")
            self.assertEqual(clone[i]["id"], b"D" * 16)
        with self.assertRaisesRegex(ValueError, "local dependency"):
            hud.clone_resource(rows, 1, "new", b"N" * 16,
                               links={5: (b"D" * 16, "bad", b"Z" * 16)})
        with self.assertRaisesRegex(ValueError, "grammar"):
            hud.validate_hud_group(rows, 1, "model")

    def test_self_id_retarget_uses_proven_slot(self):
        rows = group("prototype")
        clone = hud.clone_resource(rows, 1, "new", b"N" * 16,
                                   inline={0x3A8: (b"D" * 16, b"N" * 16)})
        self.assertEqual(clone[1]["data"][0x3A8:0x3B8], b"N" * 16)
        self.assertEqual(clone[3]["data"], rows[3]["data"])
        self.assertEqual(clone[3]["flags"], 0x18)

    def test_root_clone_updates_loader_name_inside_payload(self):
        rows = group("root")
        clone = hud.clone_resource(rows, 1, "new_root", b"N" * 16)
        self.assertEqual(clone[1]["data"][0x1C:0x54], b"new_root" + bytes(48))
        self.assertEqual(rows[1]["data"][0x1C:0x54], b"source" + bytes(50))

    def test_root_mismatched_loader_name_rejected(self):
        rows = group("root")
        rows[1]["data"][0x1C] = ord("X")
        with self.assertRaisesRegex(ValueError, "internal name"):
            hud.clone_resource(rows, 1, "new", b"N" * 16)

    def test_overlapping_inline_slots_rejected(self):
        rows = group()
        with self.assertRaisesRegex(ValueError, "overlap"):
            hud.clone_resource(rows, 1, "new", b"N" * 16,
                               inline={8: (bytes(16), b"N" * 16), 9: (bytes(16), b"R" * 16)})

    def test_wrong_link_or_inline_source_rejected(self):
        for kwargs in [{"links": {2: (b"Z" * 16, "bad", b"R" * 16)}},
                       {"inline": {0xC: (b"Z" * 16, b"R" * 16)}},
                       {"inline": {79: (b"Z" * 16, b"R" * 16)}}]:
            with self.assertRaises(ValueError):
                hud.clone_resource(group(), 1, "new", b"N" * 16, **kwargs)

    def test_truncated_or_wrong_parent_group_rejected(self):
        rows = group()
        with self.assertRaises(ValueError):
            hud.group_roles(rows[:-1], 1)
        rows[2]["parent"] = None
        with self.assertRaisesRegex(ValueError, "parent"):
            hud.group_roles(rows, 1)

    def test_nonzero_flags_not_accepted_as_dependency_link(self):
        rows = group()
        rows[2]["flags"] = 0x18
        with self.assertRaises(ValueError):
            hud.group_roles(rows, 1)

    def test_complete_clone_count_includes_script_accounting(self):
        rows = group("model") + group("prototype") + group("root")
        result = hud.clone_accounting(rows, {0x10001: 1725, 0x20001: 2073, 0x10005: 2600})
        self.assertEqual(result["physical_records"], 13)
        self.assertEqual(result["payload_records"], 4)
        self.assertEqual(result["accounting_delta"], 3)
        self.assertEqual(result["type_deltas"]["0x10005"], 1)
        self.assertFalse(result["matches_three_payload_gate"])

    def test_output_must_stay_in_designated_repo_tree(self):
        repo = Path(__file__).resolve().parents[2]
        valid = repo / "build/v0.10.4/hud-test/r_ui.wad"
        self.assertEqual(hud.safe_output(valid, repo / "build/v0.10.4"), valid)
        for invalid in [repo / "r_ui.wad", repo / "build/v0.10.4/../../bad.wad",
                        repo / "build/v0.10.4"]:
            with self.assertRaises(ValueError):
                hud.safe_output(invalid, repo / "build/v0.10.4")

    def test_inspector_reports_payloads_and_resolved_dependency(self):
        path = MODULE.with_name("inspect-compass-hud-physical-groups.py")
        self.assertTrue(path.exists(), "inspector missing")
        inspector = hud.load_module(path.name)
        rows = group()
        rows.append(record(flags=0x14, name="material", rid=b"A" * 16, data=bytes(384), parent=None))
        result = inspector.describe_group(rows, 1, "model", {b"A" * 16: [5]})
        link = result["records"][2]
        self.assertTrue(link["zero_data_dependency_link"])
        self.assertEqual(link["resolved_targets"][0]["record_index"], 5)
        self.assertTrue(result["records"][1]["is_target_payload"])
        self.assertEqual(result["records"][2]["parent_relative_index"], 0)

    def test_inspector_rejects_unpinned_source_before_parse(self):
        path = MODULE.with_name("inspect-compass-hud-physical-groups.py")
        self.assertTrue(path.exists(), "inspector missing")
        inspector = hud.load_module(path.name)
        with self.assertRaisesRegex(ValueError, "source WAD hash"):
            inspector.inspect(b"wrong source", {})

    def test_v3_blocked_gate_does_not_write_candidate(self):
        path = MODULE.with_name("build-raven-compass-hud-three-payload-v3.py")
        self.assertTrue(path.exists(), "v3 preflight missing")
        builder = hud.load_module(path.name)
        root = Path(__file__).resolve().parents[2]
        tree = root / "build/v0.10.4"
        tree.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tree) as temporary:
            dest = Path(temporary) / "r_ui.wad"
            result = builder.blocked_report({"required_clone": {
                "physical_records": 13, "payload_records": 4, "accounting_delta": 3,
                "matches_three_payload_gate": False}}, dest)
            self.assertFalse(result["candidate_written"])
            self.assertFalse(result["ready_for_runtime_test"])
            self.assertFalse(dest.exists())
            dest.write_bytes(b"old candidate")
            with self.assertRaisesRegex(ValueError, "already exists"):
                builder.blocked_report({"required_clone": {}}, dest)
            self.assertEqual(dest.read_bytes(), b"old candidate")

    def test_usage_error_is_not_structural_block(self):
        builder = hud.load_module("build-raven-compass-hud-three-payload-v3.py")
        result = subprocess.run([sys.executable, str(MODULE.with_name(
            "build-raven-compass-hud-three-payload-v3.py"))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotEqual(result.returncode, getattr(builder, "BLOCKED_EXIT_CODE", 2))
        self.assertNotIn("OFFLINE_RAVEN_COMPASS_HUD_THREE_PAYLOAD_BLOCKED", result.stdout)

    def test_hard_link_output_rejected_without_touching_target(self):
        tree = hud.REPO / "build/v0.10.4"
        tree.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tree) as temporary:
            source = Path(temporary) / "source.json"
            link = Path(temporary) / "report.json"
            source.write_text("keep", encoding="utf-8")
            os.link(source, link)
            with self.assertRaisesRegex(ValueError, "hard links"):
                hud.safe_output(link, tree)
            self.assertEqual(source.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
