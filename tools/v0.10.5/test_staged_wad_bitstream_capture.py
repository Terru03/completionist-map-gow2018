"""Check bounded snapshot and descriptor rejection without game access."""
import importlib.util
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bit_capture", HERE / "capture-staged-wad-bitstream-raven-state-readonly.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
obs = capture.load_observer()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.base = 0x140000000
        self.pointer = 0x200000000
        self.payload = b"\x02\x00\x00\x00"
        self.table = bytearray(obs.RECORD_STRIDE)
        struct.pack_into("<h", self.table, 0x28, -1)
        struct.pack_into("<QQI", self.table, 0x30, self.pointer, self.pointer, len(self.payload))
        self.memory = {
            self.base + obs.PAYLOAD_SIZE_RVA: struct.pack("<I", len(self.payload)),
            self.base + obs.PAYLOAD_BASE_RVA: struct.pack("<Q", self.pointer),
            self.base + obs.RECORD_COUNT_RVA: struct.pack("<I", 1),
            self.base + obs.RECORD_BASE_RVA: bytes(self.table),
            self.pointer: self.payload,
        }

    def read(self, address, size):
        raw = self.memory[address]
        self.assertEqual(len(raw), size)
        return raw

    def test_stable_unloaded_record(self):
        layout, table, pool = capture.snapshot(self.read, self.base, obs)
        records = capture.channel_a_records(layout, table, pool, obs)
        self.assertEqual(records[0][0]["native_slot_index"], -1)
        self.assertEqual(records[0][1], self.payload)

    def test_changed_pool_rejected(self):
        count = 0
        def changing(address, size):
            nonlocal count
            raw = self.read(address, size)
            if address == self.pointer:
                count += 1
                if count == 2:
                    return b"\x03" + raw[1:]
            return raw
        with self.assertRaisesRegex(RuntimeError, "snapshot changed"):
            capture.snapshot(changing, self.base, obs)

    def test_bad_count_rejected_before_pool_read(self):
        self.memory[self.base + obs.RECORD_COUNT_RVA] = struct.pack("<I", obs.MAX_RECORDS + 1)
        with self.assertRaisesRegex(RuntimeError, "record count"):
            capture.snapshot(self.read, self.base, obs)

    def test_payload_outside_pool_rejected(self):
        struct.pack_into("<Q", self.table, 0x30, self.pointer - 1)
        with self.assertRaisesRegex(RuntimeError, "outside pinned pool"):
            capture.channel_a_records((4, self.pointer, 1), self.table, self.payload, obs)

    def test_oversized_record_rejected(self):
        struct.pack_into("<I", self.table, 0x40, 0x10002)
        with self.assertRaisesRegex(RuntimeError, "envelope cap"):
            capture.channel_a_records((4, self.pointer, 1), self.table, self.payload, obs)

    def test_bad_cursor_and_slot_rejected(self):
        struct.pack_into("<Q", self.table, 0x38, self.pointer + 5)
        with self.assertRaisesRegex(RuntimeError, "cursor outside"):
            capture.channel_a_records((4, self.pointer, 1), self.table, self.payload, obs)
        struct.pack_into("<h", self.table, 0x28, 64)
        with self.assertRaisesRegex(RuntimeError, "invalid native slot"):
            capture.channel_a_records((4, self.pointer, 1), self.table, self.payload, obs)


if __name__ == "__main__":
    unittest.main()
