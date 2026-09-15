"""Read-only live probe for the canonical Alfheim Raven.

This deliberately does NOT call DebugActiveProcess, install breakpoints, suspend
threads, or write process memory. It opens GoW.exe with QUERY_INFORMATION and
VM_READ only, resolves the scheduler outer for alf355_chiseldungeon.wad, obtains
that outer's exact runtime registry ID, enumerates the flavor-1 GameObject bank,
and scores live objects against exact canonical Raven evidence.

The result is evidence only. A candidate token is never promoted to an exact
persistent-key PASS by this tool alone.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
EXPECTED_WAD_SHA256 = "2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268"
TARGET_WAD = "alf355_chiseldungeon.wad"
TARGET_GUID = "95b9c644-4d47-9ac6-8207-b1829d02909b"
TARGET_NAME = "goprecisionchallenge_raven_perch"
TARGET_FIELD = "ravenKilled"
TARGET_RECORD_ID = "44c6b995c69a474d82b107829c90029d"
TARGET_OVERRIDE_RECORD_ID = "44c6b995c69a474d82b107829c91029d"
TARGET_PROTOTYPE = "f4f22e4546b2194891ad7f9a7c5b6dc4"
TARGET_INDEX = 9633
TARGET_OFFSET = 0x32E3C60
TARGET_POS = (355.9026702633928, -13.425154601028225, 150.08795393212495)
REGISTRY_TABLE_RVA = 0x22A98C0
SCHEDULER_OUTER_SENTINEL_RVA = 0x11C7928

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_ALL = 0x03

if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.ReadProcessMemory.restype = wintypes.BOOL
    psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
                                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    psapi.EnumProcessModulesEx.restype = wintypes.BOOL
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    psapi.GetModuleFileNameExW.restype = wintypes.DWORD


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_target_payload(wad: Path) -> bytes:
    if sha256_path(wad) != EXPECTED_WAD_SHA256:
        raise RuntimeError("target WAD SHA256 mismatch")
    helper = Path(__file__).with_name("raven_catalogue.py")
    spec = importlib.util.spec_from_file_location("readonly_raven_catalogue", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {helper}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = module.parse_wad(wad.read_bytes())
    row = records[TARGET_INDEX]
    if row["offset"] != TARGET_OFFSET or row["id"].hex() != TARGET_RECORD_ID:
        raise RuntimeError("canonical Raven WAD record changed")
    return row["data"]


def encode_token(registry_id: int, flavor: int, slot: int) -> int:
    return 1 | ((registry_id & 0xFFFF) << 1) | ((flavor & 1) << 17) | ((slot & 0xFFFFF) << 18)


class Reader:
    def __init__(self, pid: int):
        if sys.platform != "win32":
            raise RuntimeError("live read-only probe requires Windows")
        self.pid = pid
        self.handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def read(self, address: int, size: int) -> bytes:
        if not address or size <= 0:
            raise ValueError("invalid read")
        buf = ctypes.create_string_buffer(size)
        done = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(done)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw[:done.value]

    def try_read(self, address: int, size: int) -> bytes | None:
        try:
            data = self.read(address, size)
        except (OSError, ValueError):
            return None
        return data if data else None

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def module(self) -> tuple[int, str]:
        modules = (wintypes.HMODULE * 2048)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcessModulesEx(self.handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), LIST_MODULES_ALL):
            raise ctypes.WinError(ctypes.get_last_error())
        if needed.value < ctypes.sizeof(wintypes.HMODULE):
            raise RuntimeError("PSAPI returned no executable module")
        mod = modules[0]
        buf = ctypes.create_unicode_buffer(32768)
        if not psapi.GetModuleFileNameExW(self.handle, mod, buf, len(buf)):
            raise ctypes.WinError(ctypes.get_last_error())
        base = ctypes.cast(mod, ctypes.c_void_p).value
        if not base:
            raise RuntimeError("null executable module base")
        return int(base), buf.value

    def cstring(self, address: int, limit: int = 512) -> str | None:
        raw = self.try_read(address, limit)
        if raw is None:
            return None
        raw = raw.split(b"\0", 1)[0]
        if not raw:
            return None
        try:
            return raw.decode("utf-8", "strict")
        except UnicodeDecodeError:
            return None


def plausible_ptr(value: int) -> bool:
    return 0x10000 <= value <= 0x00007FFFFFFFFFFF and value % 8 == 0


def wad_name(reader: Reader, wad_ptr: int) -> str | None:
    """Decode proved [WAD+0x50]+0x54 filename using inline and pointer forms."""
    try:
        owner = reader.u64(wad_ptr + 0x50)
    except OSError:
        return None
    if not plausible_ptr(owner):
        return None
    direct = reader.cstring(owner + 0x54)
    if direct and ".wad" in direct.lower():
        return direct
    try:
        string_ptr = reader.u64(owner + 0x54)
    except OSError:
        return direct
    if plausible_ptr(string_ptr):
        pointed = reader.cstring(string_ptr)
        if pointed:
            return pointed
    return direct


def scheduler_outers(reader: Reader, base: int) -> list[dict]:
    sentinel = base + SCHEDULER_OUTER_SENTINEL_RVA
    rows: list[dict] = []
    seen: set[int] = set()
    try:
        node = reader.u64(sentinel)
    except OSError:
        return rows
    for _ in range(4096):
        if not node or node == sentinel or node in seen or not plausible_ptr(node):
            break
        seen.add(node)
        raw = reader.try_read(node, 0x58)
        if raw is None or len(raw) < 0x48:
            break
        nxt = struct.unpack_from("<Q", raw, 0x00)[0]
        registry_id = struct.unpack_from("<I", raw, 0x10)[0]
        config = struct.unpack_from("<Q", raw, 0x18)[0]
        resource_hash = struct.unpack_from("<Q", raw, 0x30)[0]
        wad_ptr = struct.unpack_from("<Q", raw, 0x40)[0]
        name = wad_name(reader, wad_ptr) if plausible_ptr(wad_ptr) else None
        rows.append({
            "address": f"0x{node:X}", "registry_id": registry_id,
            "type_116_config": f"0x{config:X}", "resource_hash": f"0x{resource_hash:X}",
            "wad_ptr": f"0x{wad_ptr:X}", "wad_name": name,
        })
        node = nxt
    return rows


def registry_rows(reader: Reader, base: int) -> list[dict]:
    raw = reader.try_read(base + REGISTRY_TABLE_RVA, 64 * 8)
    if raw is None or len(raw) != 64 * 8:
        raise RuntimeError("cannot read 64-entry GameObject registry table")
    rows = []
    for index in range(64):
        ptr = struct.unpack_from("<Q", raw, index * 8)[0]
        if not plausible_ptr(ptr):
            continue
        state = reader.try_read(ptr, 0x38)
        if state is None or len(state) < 0x34:
            continue
        registry_id = struct.unpack_from("<I", state, 0x00)[0]
        bank = struct.unpack_from("<Q", state, 0x20)[0]
        cursor = struct.unpack_from("<I", state, 0x28)[0]
        live = struct.unpack_from("<I", state, 0x2C)[0]
        capacity = struct.unpack_from("<I", state, 0x30)[0]
        if capacity > 0x100000:
            continue
        rows.append({
            "table_index": index, "address": ptr, "registry_id": registry_id,
            "bank": bank, "cursor": cursor, "live_count": live, "capacity": capacity,
        })
    return rows


def evidence_needles(payload: bytes) -> list[tuple[str, bytes, int]]:
    return [
        ("exact_payload", payload, 120),
        ("guid_ascii", TARGET_GUID.encode("ascii"), 70),
        ("object_name_ascii", TARGET_NAME.encode("ascii"), 50),
        ("progression_field", TARGET_FIELD.encode("ascii"), 35),
        ("final_record_id", bytes.fromhex(TARGET_RECORD_ID), 30),
        ("override_record_id", bytes.fromhex(TARGET_OVERRIDE_RECORD_ID), 25),
        ("prototype_id", bytes.fromhex(TARGET_PROTOTYPE), 25),
    ]


def scan_blob(blob: bytes, payload: bytes) -> set[str]:
    found = {name for name, needle, _ in evidence_needles(payload) if needle and needle in blob}
    floats = [struct.pack("<f", float(v)) for v in TARGET_POS]
    doubles = [struct.pack("<d", float(v)) for v in TARGET_POS]
    if all(v in blob for v in floats):
        found.add("world_position_float_components")
    if all(v in blob for v in doubles):
        found.add("world_position_double_components")
    return found


def score_labels(labels: set[str], payload: bytes) -> int:
    scores = {name: score for name, _, score in evidence_needles(payload)}
    scores["world_position_float_components"] = 45
    scores["world_position_double_components"] = 45
    return sum(scores.get(label, 0) for label in labels)


def inspect_object(reader: Reader, obj: int, expected_registry: int, expected_slot: int,
                   payload: bytes, max_nodes: int = 64) -> dict | None:
    root = reader.try_read(obj, 0x300)
    if root is None or len(root) < 0x288:
        return None
    flags = struct.unpack_from("<I", root, 0x278)[0]
    registry_id = struct.unpack_from("<I", root, 0x280)[0] & 0xFFFF
    slot = struct.unpack_from("<I", root, 0x284)[0] & 0xFFFFF
    flavor = (flags >> 3) & 1
    if registry_id != (expected_registry & 0xFFFF) or slot != expected_slot or flavor != 1:
        return None

    labels: set[str] = set()
    hits: list[dict] = []
    queue: list[tuple[int, int]] = [(obj, 0)]
    seen: set[int] = set()
    nodes = 0
    while queue and nodes < max_nodes:
        address, depth = queue.pop(0)
        if address in seen:
            continue
        seen.add(address)
        size = 0x500 if depth else 0x300
        blob = reader.try_read(address, size)
        if blob is None:
            continue
        nodes += 1
        local = scan_blob(blob, payload)
        for label in sorted(local - labels):
            hits.append({"label": label, "address": f"0x{address:X}", "depth": depth})
        labels |= local
        if depth >= 2:
            continue
        pointer_region = blob[: min(len(blob), 0x300)]
        for off in range(0, len(pointer_region) - 7, 8):
            ptr = struct.unpack_from("<Q", pointer_region, off)[0]
            if plausible_ptr(ptr) and ptr not in seen:
                queue.append((ptr, depth + 1))
                if len(queue) + nodes >= max_nodes * 3:
                    break

    token = encode_token(registry_id, flavor, slot)
    return {
        "object": f"0x{obj:X}", "registry_id": registry_id, "flavor": flavor, "slot": slot,
        "token": token, "token_hex": f"0x{token:X}", "score": score_labels(labels, payload),
        "evidence": sorted(labels), "evidence_hits": hits, "graph_nodes_read": nodes,
    }


def inspect_registry(reader: Reader, row: dict, payload: bytes) -> dict:
    capacity = row["capacity"]
    bank = row["bank"]
    if capacity <= 1 or capacity > 0x10000 or not plausible_ptr(bank):
        return {"objects": [], "error": "invalid flavor-1 bank/capacity"}
    raw = reader.try_read(bank, capacity * 8)
    if raw is None or len(raw) != capacity * 8:
        return {"objects": [], "error": "cannot read flavor-1 bank"}
    objects = []
    occupied = 0
    for slot in range(1, capacity):
        obj = struct.unpack_from("<Q", raw, slot * 8)[0]
        if not plausible_ptr(obj):
            continue
        occupied += 1
        item = inspect_object(reader, obj, row["registry_id"], slot, payload)
        if item is not None:
            objects.append(item)
    objects.sort(key=lambda x: (-x["score"], x["slot"]))
    return {"occupied_bank_slots": occupied, "validated_objects": len(objects), "objects": objects}


def snapshot(pid: int, exe: Path, wad: Path) -> dict:
    if sha256_path(exe) != EXPECTED_EXE_SHA256:
        raise RuntimeError("GoW.exe SHA256 mismatch")
    payload = load_target_payload(wad)
    reader = Reader(pid)
    try:
        base, path = reader.module()
        if Path(path).resolve() != exe.resolve():
            raise RuntimeError(f"PID {pid} executable mismatch: {path}")
        outers = scheduler_outers(reader, base)
        target_outers = [row for row in outers if row.get("wad_name") and TARGET_WAD in row["wad_name"].lower()]
        registries = registry_rows(reader, base)
        registry_by_id = {row["registry_id"]: row for row in registries}
        target_results = []
        for outer in target_outers:
            reg = registry_by_id.get(outer["registry_id"])
            item = {"outer": outer, "registry": None, "inspection": None}
            if reg is not None:
                public_reg = {k: (f"0x{v:X}" if k in ("address", "bank") else v) for k, v in reg.items()}
                item["registry"] = public_reg
                item["inspection"] = inspect_registry(reader, reg, payload)
            target_results.append(item)

        candidates = []
        for item in target_results:
            inspection = item.get("inspection") or {}
            for obj in inspection.get("objects", []):
                if obj["score"] > 0:
                    candidates.append({**obj, "registry_id": item["outer"]["registry_id"]})
        candidates.sort(key=lambda x: (-x["score"], x["slot"]))

        return {
            "schema": 1,
            "analysis": "gow_raven_readonly_registry_snapshot",
            "pid": pid, "module_base": f"0x{base:X}", "module_path": path,
            "exe_sha256": EXPECTED_EXE_SHA256, "wad_sha256": EXPECTED_WAD_SHA256,
            "safety": {
                "debugger_attached": False, "breakpoints_installed": False,
                "process_writes": False, "thread_suspend_resume": False,
                "save_or_progression_writes": False, "access": "PROCESS_QUERY_INFORMATION|PROCESS_VM_READ",
            },
            "scheduler_outer_count": len(outers),
            "target_wad_outer_count": len(target_outers),
            "target_wad_outers": target_results,
            "registry_table_live_entries": len(registries),
            "candidate_count": len(candidates),
            "top_candidates": candidates[:25],
            "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
            "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        }
    finally:
        reader.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--wad", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = snapshot(a.pid, a.exe, a.wad)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"READONLY_SNAPSHOT_OK pid={a.pid}")
    print(f"target_wad_outer_count={report['target_wad_outer_count']}")
    print(f"candidate_count={report['candidate_count']}")
    for index, candidate in enumerate(report["top_candidates"][:5], 1):
        print(f"candidate_{index}=token={candidate['token_hex']} registry={candidate['registry_id']} slot={candidate['slot']} score={candidate['score']} evidence={','.join(candidate['evidence'])}")
    print("BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY")
    print("BLOCKED_EXACT_UNLOADED_STATE_ORACLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
