"""Test registry reader edge cases. No game mutation or binary fixture files."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("registry", HERE / "inspect-map-class-registry.py")
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)
inv = registry.inventory


class FakeDcb:
    def __init__(self, count=255, start=0x90):
        self.count, self.start = count, start
        self.blob = bytearray(4272)
        for i in range(255):
            struct.pack_into("<QH", self.blob, 0x90 + 16 * i, i + 1, 1)

    def root(self, name, kind):
        return 0

    def array(self, root, stride):
        return range(self.start, self.start + self.count * stride, stride)


class RegistryTests(unittest.TestCase):
    def test_duplicate_rows_keep_distinct_counts_and_offsets(self):
        dcb = FakeDcb()
        for i, count in [(208, 8), (212, 2)]:
            struct.pack_into("<QH", dcb.blob, 0x90 + i * 16, 0x74FAAE7497B39361, count)
        rows = inv.parse_gopool(dcb)
        dup = [r for r in rows if r["name_hash_int"] == 0x74FAAE7497B39361]
        self.assertEqual([(r["row_index"], r["cnt"]) for r in dup], [(208, 8), (212, 2)])
        self.assertEqual(len(rows), 255)

    def test_wrong_pointer_or_count_rejected(self):
        for dcb in [FakeDcb(count=254), FakeDcb(start=0x80)]:
            with self.assertRaisesRegex(ValueError, "pointer/count"):
                inv.parse_gopool(dcb)

    def test_padding_and_truncation_rejected(self):
        dcb = FakeDcb()
        dcb.blob[0x9A] = 1
        with self.assertRaisesRegex(ValueError, "padding"):
            inv.parse_gopool(dcb)
        dcb.blob = dcb.blob[:-1]
        with self.assertRaisesRegex(ValueError, "size"):
            inv.parse_gopool(dcb)

    def test_report_cannot_target_game_or_save_or_source(self):
        for path in [Path("G:/SteamLibrary/steamapps/common/GodOfWar/report.json"),
                     Path.home() / "Saved Games/report.json", HERE / "inspect-map-class-registry.py",
                     HERE.parent.parent / "archive/field-logs/../../outside.json",
                     HERE.parent.parent / "archive/field-logs/r_ui.wad"]:
            with self.assertRaisesRegex(ValueError, "report must"):
                inv.report_path(path)

    def test_payload_name_separate_from_header(self):
        data = bytearray(164)
        data[0x1C:0x29] = b"gomapicondock"
        r = {"name": "gomapiconcompletionistraven", "flags": 0x3D, "data": data}
        self.assertEqual(registry.final_name(r), "gomapicondock")
        self.assertNotEqual(registry.final_name(r), r["name"])

    def test_unterminated_payload_name_rejected(self):
        r = {"flags": 0x3D, "data": bytearray(b"a" * 164)}
        with self.assertRaisesRegex(ValueError, "unterminated"):
            registry.final_name(r)

    def test_hash_case_fold_and_known_raven(self):
        self.assertEqual(inv.native.name_hash("goMapIconCompletionistRaven"), 0x584F31DC8BD6E738)
        self.assertEqual(inv.native.name_hash("goMapIconDock"), inv.native.name_hash("gomapicondock"))

    def test_missing_whole_rig_type_fails_accounting(self):
        records = [{"name": "metadata", "data": b"x", "flags": 0} for _ in range(2)]
        table = [{"key": k, "count": int(k == 0x40001)} for k in (0x10001, 0x20001, 0x30001, 0x40001)]
        with patch.object(registry.logical, "read_type_table", return_value=table):
            report = registry.type_accounting(records)
        self.assertFalse(report["all_rig_type_counts_match"])
        missing = next(r for r in report["rig_type_counts"] if r["type_key"] == "0x40001")
        self.assertEqual((missing["observed_payloads"], missing["declared_count"]), (0, 1))

    def test_wrong_declared_final_count_fails_accounting(self):
        records = [{"name": "metadata", "data": b"x", "flags": 0} for _ in range(2)]
        records.append({"name": "test_final", "data": struct.pack("<I", 0x20001), "flags": 0x3D})
        table = [{"key": k, "count": 0} for k in (0x10001, 0x20001, 0x30001, 0x40001)]
        with patch.object(registry.logical, "read_type_table", return_value=table):
            report = registry.type_accounting(records)
        self.assertFalse(report["all_rig_type_counts_match"])


if __name__ == "__main__":
    unittest.main()
