"""Static and offline failure-path tests. No live game writes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("partial", HERE / "patch-raven-resident-partial-linearization.py")
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class PartialLinearizationTests(unittest.TestCase):
    def test_pinned_helpers(self):
        for name in subject.PINS:
            subject.load_pinned(name)

    def test_changed_helper_refused(self):
        with patch.object(Path, "read_bytes", return_value=b"changed"):
            with self.assertRaisesRegex(ValueError, "pinned helper changed"):
                subject.load_pinned("build-raven-ui-logical-clone.py")

    def test_active_rows_and_raw_tail(self):
        gnf = subject.load_pinned("patch-raven-resident-artwork.py")
        transform = subject.load_pinned("inspect-resident-partial-linearization.py")
        for width in (148, 156):
            for fmt, block_bytes in ((0x29, 16), (0x23, 8)):
                meta = {"width": width, "height": width, "mips": 8,
                        "format": fmt, "data_size": 5696 * block_bytes}
                image = b"".join(i.to_bytes(block_bytes, "little") for i in range(5696))
                meta["image"] = image
                rebuilt, details = subject.reconstruct(meta, gnf, transform)
                self.assertEqual(len(rebuilt), 576 * block_bytes)
                for row, layout in zip(details, gnf.mip_layout(meta, block_bytes // 2)[2:]):
                    aw, ah = row["active_blocks"]
                    pw, _ = row["padded_blocks"]
                    expected = []
                    for y in range(ah):
                        for x in range(aw):
                            # Independent Morton inverse: interleave x/y bits.
                            morton = sum(((x >> b) & 1) << (2 * b) | ((y >> b) & 1) << (2 * b + 1) for b in range(3))
                            index = ((y // 8) * (pw // 8) + x // 8) * 64 + morton
                            expected.append(image[layout["offset"] + index * block_bytes:layout["offset"] + (index + 1) * block_bytes])
                    start = row["resident_offset"]
                    packed = b"".join(expected)
                    self.assertEqual(rebuilt[start:start + len(packed)], packed)
                    raw_start = layout["offset"] + len(packed)
                    self.assertEqual(rebuilt[start + len(packed):start + row["bytes"]], image[raw_start:layout["offset"] + layout["bytes"]])

    def test_exact_failure_ranges_split_by_mip(self):
        details = [{"mip": 2, "resident_offset": 0, "bytes": 4}, {"mip": 3, "resident_offset": 4, "bytes": 4}]
        with self.assertRaisesRegex(ValueError, '"mip": 2, "start": 2, "end_exclusive": 4.*"mip": 3, "start": 4, "end_exclusive": 5'):
            subject.require_exact(b"abXXXfgh", b"abcdefgh", "stock", details)

    def test_bad_base_refused_before_reading_other_inputs(self):
        with self.assertRaisesRegex(ValueError, "clean registered-Raven base"):
            subject.patch(b"bad", None, None, None, None)

    def test_bad_dcb_mapmaster_and_pack_refused(self):
        for failure, expected_message in ((0, "DCB"), (1, "mapmaster"), (2, "texpack")):
            hashes = [subject.EXPECTED_DCB, subject.EXPECTED_MAPMASTER, subject.EXPECTED_RAVEN_PACK]
            hashes[failure] = "bad"
            with patch.object(subject, "sha", return_value=subject.EXPECTED_BASE_WAD), patch.object(subject, "file_sha", side_effect=hashes):
                with self.assertRaisesRegex(ValueError, expected_message):
                    subject.patch(b"fixture", None, None, None, None)

    def test_cli_refuses_existing_output_without_touching_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.write_bytes(b"keep")
            argv = ["patcher", "--output", str(output), "--report", str(Path(tmp) / "report")]
            for name in ("wad", "dcb", "mapmaster", "root-texpack", "raven-texpack"):
                argv.extend([f"--{name}", str(Path(tmp) / name)])
            with patch("sys.argv", argv), self.assertRaisesRegex(ValueError, "new files"):
                subject.main()
            self.assertEqual(output.read_bytes(), b"keep")
            self.assertFalse((Path(tmp) / "report").exists())


if __name__ == "__main__":
    unittest.main()
