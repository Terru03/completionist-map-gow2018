"""Small, version-pinned native type/binding inventory. No process access."""

import argparse
import hashlib
from pathlib import Path
import struct

EXPECTED = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
BASE = 0x140000000
ATTRS = 0x141082030
TYPES = {0x409: "MapCoords", 0x40A: "MapCoordsInfo", 0x40B: "CompassHelper",
         0x40C: "CompassHelperInfo", 0x40D: "CompassGraphEdge", 0x40E: "CompassGraphEdgeInfo",
         0x40F: "MapToken", 0x410: "Marker", 0x413: "Region", 0x414: "Realm", 0x415: "MapInfo"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    raw = args.exe.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED:
        raise ValueError("Executable hash differs. Do not reuse these addresses.")
    pe, = struct.unpack_from("<I", raw, 0x3C)
    count, = struct.unpack_from("<H", raw, pe + 6)
    optional_size, = struct.unpack_from("<H", raw, pe + 20)
    sections = []
    for i in range(count):
        o = pe + 24 + optional_size + 40 * i
        _, rva, size, file_offset = struct.unpack_from("<4I", raw, o + 8)
        sections.append((rva, size, file_offset))

    def read(va, size):
        rva = va - BASE
        for start, length, offset in sections:
            if start <= rva and rva + size <= start + length:
                return raw[offset + rva - start:offset + rva - start + size]
        raise ValueError("Address outside file-backed PE section")

    def string(va):
        return read(va, 180).split(b"\0")[0].decode("ascii")

    lines = ["Completionist v0.10.3 native engine inventory", f"SHA256 {digest}",
             "Preferred image base 0x140000000. Runtime addresses require ASLR rebase.",
             "TypeAttribute layout from Nukem9 Kinetica/RTTI.h; values read from local executable.", ""]
    for index in range(0x459A, 0x45EE):
        field = read(ATTRS + index * 32, 32)
        name, _, offset, size, flags, _, parent = struct.unpack_from("<QQHHBBH", field)
        if parent in TYPES:
            lines.append(f"NATIVE_MARKER_API type={TYPES[parent]} type_id=0x{parent:X} attr=0x{index:X} "
                         f"offset=0x{offset:X} size={size} kind={flags >> 2} field={string(name)}")
    for label, start, end in [("Compass binding-name block", 0x140E2DA10, 0x140E2DC40),
                              ("Map binding-name block", 0x140E2DEE8, 0x140E2E270)]:
        lines += ["", label]
        values = read(start, end - start).split(b"\0")
        lines.extend(v.decode("ascii") for v in values if v and all(32 <= c < 127 for c in v))
    lines += ["", "Disassembly anchors verified separately; labels below are analysis, not exported symbols:",
              "RVA 0x94FF80 LuaCompass::ShowMarker; lookup at 0x94FFF8; class type 0x11E at 0x95009E.",
              "RVA 0x2AD490 queued ShowMarker request worker; native show dispatch at 0x2AD4F7.",
              "RVA 0x760F40 native realm/region/marker lookup; marker scan stride 0x80.",
              "RVA 0x76135E map initialization reads MapInfo 0x415.",
              "RVA 0x76164C map initialization reads MapCoordsInfo 0x40A.",
              "RVA 0x761817 joins marker uID to MapCoords uID; reads position from +0x10 at 0x76182D.",
              "RVA 0x8B0B4E compass initialization reads MapCoordsInfo 0x40A.",
              "RVA 0x8B0BC6 compass initialization reads CompassHelperInfo 0x40C.",
              "RVA 0x8B179C compass initialization reads CompassGraphEdgeInfo 0x40E.",
              "RVA 0x6C0C80 native show; checks manager +0x221E0 at 0x6C0CB9 before icon creation.",
              "RVA 0x6C0E65 requests authored UI icon; path/position init calls at 0x6C0EDA, 0x6C0EE9."]
    output = args.output.resolve()
    if output.is_relative_to(args.exe.resolve().parent):
        raise ValueError("Inventory must stay outside game directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"NATIVE_MARKER_API inventory={output}")


if __name__ == "__main__":
    main()
