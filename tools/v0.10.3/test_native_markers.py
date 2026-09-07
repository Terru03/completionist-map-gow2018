import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("native", Path(__file__).with_name("inspect-native-markers.py"))
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def chunk(kind, payload):
    data = struct.pack("<HHI", kind, 0x10, len(payload)) + bytes(88) + payload
    return data + bytes((-len(data)) % 16)


def fixture(delta=32, relocations=(0, 24), export_hash=None):
    blob = bytearray(56)
    struct.pack_into("<QI", blob, 0, 16, 1)
    struct.pack_into("<Qq3e3efff", blob, 16, 0xFFFFFFFF00000001, delta,
                     1, 2, 3, 0, 0, 1, 1, -1, 0)
    blob += b"WAD_Test\0"
    name = "MAP_COORDS_PERM_DATA"
    uid = native.name_hash(name) if export_hash is None else export_hash
    exports = struct.pack("<QIIQQ", 1, 0, 0x40A, 32, uid) + name.encode() + b"\0"
    rel = struct.pack(f"<I{len(relocations)}I", len(relocations), *relocations)
    return b"".join(chunk(k, p) for k, p in [(11, bytes(4)), (12, blob), (13, exports), (14, bytes(4)), (15, rel)])


class NativeDataTests(unittest.TestCase):
    def read(self, data):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.dcb"
            path.write_bytes(data)
            return native.Dcb(path)

    def test_self_relative_pointer_and_half_vector(self):
        dcb = self.read(fixture())
        row = native.read_positions(dcb, "MAP_COORDS_PERM_DATA", 0x40A)[0xFFFFFFFF00000001]
        self.assertEqual(row["wad"], "WAD_Test")
        self.assertEqual(row["position"], (1, 2, 3))

    def test_hash_matches_engine_export_and_folds_case(self):
        self.assertEqual(native.name_hash("MAP_PERM_DATA"), 0xA00037606F638079)
        self.assertEqual(native.name_hash("map_perm_data"), 0xA00037606F638079)

    def test_truncation_rejected(self):
        with self.assertRaises(ValueError):
            self.read(fixture()[:-20])

    def test_pointer_outside_blob_rejected(self):
        with self.assertRaises(ValueError):
            self.read(fixture(delta=500000))

    def test_unrelocated_pointer_rejected(self):
        dcb = self.read(fixture(relocations=(0,)))
        with self.assertRaises(ValueError):
            native.read_positions(dcb, "MAP_COORDS_PERM_DATA", 0x40A)

    def test_wrong_export_hash_rejected(self):
        with self.assertRaises(ValueError):
            self.read(fixture(export_hash=1))


if __name__ == "__main__":
    unittest.main()
