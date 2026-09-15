"""Capture canonical Raven scheduler -> allocator provenance from supported GoW.exe.

This Windows-only debugger uses temporary one-byte software breakpoints in the
live process. It never changes GoW.exe on disk, save data, or progression data.
Every breakpoint byte is version locked and restored before detach.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time
from typing import Iterable


EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TARGET_GUID = "95b9c644-4d47-9ac6-8207-b1829d02909b"
TARGET_WAD = "alf355_chiseldungeon.wad"
TARGET_WAD_SHA256 = "2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268"
TARGET_RECORD_OFFSET = 0x32E3C60
TARGET_RECORD_INDEX = 9633
TARGET_RECORD_ID = "44c6b995c69a474d82b107829c90029d"
REGISTRY_TABLE_RVA = 0x22A98C0
SCHEDULER_OUTER_SENTINEL_RVA = 0x11C7928

# First instruction bytes at every live breakpoint plus semantic anchors used
# to decode its register contract. All values belong to supported EXE hash.
BREAKPOINTS = {
    "canonical_loader_call": (0x859C0D, "e83ed3ffff"),
    "allocator_entry": (0x4EF2B0, "4055"),
    "allocator_fields_ready": (0x4EF3BE, "488d8770010000"),
}
ANCHORS = {
    "worker_outer_lookup": (0x8583E2, "488b053ff59600"),
    "worker_inner_lookup": (0x85840F, "418bcf"),
    "worker_wad_save": (0x8588E0, "48894d90"),
    "descriptor_no_hint": (0x859BA9, "c7442430ffffffff"),
    "descriptor_builder": (0x859BD6, "e8d5caffff"),
    "loader_wad_arg": (0x859C03, "498bd6"),
    "allocator_registry_scan": (0x4EF2C2, "488d0df7a7db01"),
    "allocator_cursor_load": (0x4EF33F, "418b5128"),
    "allocator_slot_store": (0x4EF369, "49893cc8"),
    "allocator_cursor_store": (0x4EF36D, "41895128"),
    "gameobject_registry_store": (0x4EF3A5, "898f80020000"),
    "gameobject_slot_store": (0x4EF3B8, "898784020000"),
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encode_token(registry_id: int, flavor: int, slot: int) -> int:
    if not 0 <= registry_id <= 0xFFFF:
        raise ValueError("registry_id outside 16 bits")
    if flavor not in (0, 1):
        raise ValueError("flavor outside one bit")
    if not 0 <= slot <= 0xFFFFF:
        raise ValueError("slot outside 20 bits")
    return 1 | (registry_id << 1) | (flavor << 17) | (slot << 18)


def decode_token(token: int) -> dict[str, int]:
    return {
        "registry_id": (token >> 1) & 0xFFFF,
        "flavor": (token >> 17) & 1,
        "slot": (token >> 18) & 0xFFFFF,
    }


def gameobject_tuple(field_278: int, field_280: int, field_284: int) -> dict[str, int]:
    value = {
        "registry_id": field_280 & 0xFFFF,
        "flavor": (field_278 >> 3) & 1,
        "slot": field_284 & 0xFFFFF,
    }
    value["token"] = encode_token(value["registry_id"], value["flavor"], value["slot"])
    return value


def circular_scan(bank: list[int], cursor: int, capacity: int) -> dict:
    if capacity <= 1 or len(bank) != capacity:
        raise ValueError("invalid registry bank/capacity")
    tested = []
    current = cursor
    for _ in range(capacity + 1):
        candidate = current
        current = (current + 1) % capacity
        if candidate == 0:
            continue
        occupied = bank[candidate] != 0
        tested.append({"slot": candidate, "occupied": occupied, "object": f"0x{bank[candidate]:X}"})
        if not occupied:
            return {"start_cursor": cursor, "tested": tested, "selected_slot": candidate, "next_cursor": current}
    raise RuntimeError("allocator bank has no free nonzero slot")


def _stable_entry(run: dict) -> dict:
    alloc = run.get("allocator", {})
    obj = run.get("gameobject", {})
    return {
        "exact_record_bound": bool(run.get("exact_record_binding", {}).get("proved")),
        "registry_id": alloc.get("registry_id"),
        "cursor": alloc.get("cursor"),
        "live_count": alloc.get("live_count"),
        "capacity": alloc.get("capacity"),
        "occupancy_sha256": alloc.get("occupancy_sha256"),
        "selected_slot": alloc.get("selected_slot"),
        "flavor": obj.get("decoded", {}).get("flavor"),
        "token": obj.get("decoded", {}).get("token"),
        "history_complete": bool(
            run.get("allocator_history", {}).get("complete_since_fresh_registry")
            and run.get("allocator_history", {}).get("stable_event_identities_complete")
        ),
        "history_causal_sha256": run.get("allocator_history", {}).get("causal_sha256"),
    }


def compare_runs(run_a: dict, run_b: dict) -> dict:
    a, b = _stable_entry(run_a), _stable_entry(run_b)
    keys = ("registry_id", "cursor", "live_count", "occupancy_sha256", "selected_slot", "flavor", "token")
    equal = {key: a[key] is not None and a[key] == b[key] for key in keys}
    exact_both = a["exact_record_bound"] and b["exact_record_bound"]
    history_causal = (
        a["history_complete"] and b["history_complete"]
        and a["history_causal_sha256"] is not None
        and a["history_causal_sha256"] == b["history_causal_sha256"]
    )
    if exact_both and all(equal.values()) and history_causal:
        classification = "deterministic_reconstructible_from_causal_runtime_mapping"
        status = "PASS_EXACT_GAMEOBJECT_PERSISTENT_KEY"
        edge = None
    elif exact_both and equal["registry_id"] and equal["selected_slot"] and equal["flavor"] and equal["token"]:
        classification = "repeatable_but_prior_dynamic_history_not_causally_explained"
        status = "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY"
        edge = "capture and normalize complete allocation/free ancestry from fresh registry construction to target event"
    else:
        classification = "different_or_exact_record_not_bound"
        status = "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY"
        edge = "obtain exact canonical raw-record ancestry and comparable allocator entry state in both clean reloads"
    return {
        "schema": 1,
        "analysis": "gow_raven_scheduler_allocator_comparison",
        "run_a": a,
        "run_b": b,
        "equal": equal,
        "exact_canonical_record_bound_both": exact_both,
        "causal_history_reproducible": history_causal,
        "classification": classification,
        "gameobject_persistent_key_status": status,
        "precise_remaining_edge": edge,
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
    }


def load_target_record(wad_path: Path) -> dict:
    if sha256_path(wad_path) != TARGET_WAD_SHA256:
        raise RuntimeError("target WAD SHA256 mismatch")
    module_path = Path(__file__).with_name("raven_catalogue.py")
    spec = importlib.util.spec_from_file_location("runtime_raven_catalogue", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load raven_catalogue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = wad_path.read_bytes()
    records = module.parse_wad(raw)
    row = records[TARGET_RECORD_INDEX]
    if row["offset"] != TARGET_RECORD_OFFSET or row["id"].hex() != TARGET_RECORD_ID:
        raise RuntimeError("canonical physical Raven record changed")
    end = TARGET_RECORD_OFFSET + 96 + row["size"]
    exact = raw[TARGET_RECORD_OFFSET:end]
    if raw.count(exact) != 1:
        raise RuntimeError("canonical full record bytes are not unique in WAD")
    return {
        "raw": exact,
        "payload": row["data"],
        "payload_unique": raw.count(row["data"]) == 1,
        "name": row["name"],
        "kind": row["kind"],
        "flags": row["flags"],
        "size": row["size"],
        "parent_index": row["parent"],
        "sha256": hashlib.sha256(exact).hexdigest(),
    }


def exact_binding_from_blobs(blobs: Iterable[dict], target: dict) -> dict:
    raw_hits, payload_hits = [], []
    name_bytes = target["name"].encode("ascii")
    component_hits = {"name": [], "record_id": []}
    record_id = bytes.fromhex(TARGET_RECORD_ID)
    for blob in blobs:
        data = base64.b64decode(blob["data_base64"])
        address = int(blob["address"], 16)
        for label, needle, sink in (
            ("raw", target["raw"], raw_hits),
            ("payload", target["payload"], payload_hits),
            ("name", name_bytes, component_hits["name"]),
            ("record_id", record_id, component_hits["record_id"]),
        ):
            start = 0
            while True:
                found = data.find(needle, start)
                if found < 0:
                    break
                sink.append({"blob": blob["label"], "address": f"0x{address + found:X}", "offset": found})
                start = found + 1
    method = None
    hits = []
    if raw_hits:
        method, hits = "unique_full_raw_record_bytes", raw_hits
    elif payload_hits and target.get("payload_unique", False):
        method, hits = "unique_full_raw_record_payload", payload_hits
    return {
        "proved": method is not None,
        "method": method,
        "hits": hits,
        "supporting_component_hits": component_hits,
        "canonical_offset": f"0x{TARGET_RECORD_OFFSET:X}",
        "canonical_index": TARGET_RECORD_INDEX,
        "record_id": TARGET_RECORD_ID,
        "full_record_sha256": target["sha256"],
        "note": "Name/record-ID component hits never establish target identity by themselves.",
    }


def verify_image(exe: Path) -> bytes:
    if sha256_path(exe) != EXPECTED_EXE_SHA256:
        raise RuntimeError("GoW.exe SHA256 mismatch")
    raw = exe.read_bytes()
    pe_offset = struct.unpack_from("<I", raw, 0x3C)[0]
    optional = pe_offset + 24
    section_count = struct.unpack_from("<H", raw, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", raw, pe_offset + 20)[0]
    sections = optional + optional_size

    def file_bytes(rva: int, size: int) -> bytes:
        for index in range(section_count):
            pos = sections + index * 40
            virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", raw, pos + 8)
            if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
                delta = rva - virtual_address
                return raw[raw_offset + delta:raw_offset + delta + size]
        raise RuntimeError(f"RVA 0x{rva:X} not file backed")

    for name, (rva, expected_hex) in {**BREAKPOINTS, **ANCHORS}.items():
        expected = bytes.fromhex(expected_hex)
        actual = file_bytes(rva, len(expected))
        if actual != expected:
            raise RuntimeError(f"instruction anchor {name} changed at RVA 0x{rva:X}: {actual.hex()}")
    return raw


if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    PROCESS_ACCESS = 0x0010 | 0x0020 | 0x0008 | 0x0400
    THREAD_ACCESS = 0x0002 | 0x0008 | 0x0010 | 0x0040
    TH32CS_SNAPMODULE = 0x00000008 | 0x00000010
    TH32CS_SNAPTHREAD = 0x00000004
    PAGE_EXECUTE_READWRITE = 0x40
    DBG_CONTINUE = 0x00010002
    DBG_EXCEPTION_NOT_HANDLED = 0x80010001
    EXCEPTION_BREAKPOINT = 0x80000003
    EXCEPTION_SINGLE_STEP = 0x80000004
    EXIT_PROCESS_DEBUG_EVENT = 5
    EXCEPTION_DEBUG_EVENT = 1
    CREATE_THREAD_DEBUG_EVENT = 2
    CREATE_PROCESS_DEBUG_EVENT = 3
    LOAD_DLL_DEBUG_EVENT = 6
    CONTEXT_ALL = 0x0010001F
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
                    ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
                    ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
                    ("szModule", wintypes.WCHAR * 256), ("szExePath", wintypes.WCHAR * 260)]

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                    ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]

    class EXCEPTION_RECORD(ctypes.Structure):
        pass
    EXCEPTION_RECORD._fields_ = [("ExceptionCode", wintypes.DWORD), ("ExceptionFlags", wintypes.DWORD),
        ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)), ("ExceptionAddress", ctypes.c_void_p),
        ("NumberParameters", wintypes.DWORD), ("ExceptionInformation", ctypes.c_size_t * 15)]

    class EXCEPTION_DEBUG_INFO(ctypes.Structure):
        _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", wintypes.DWORD)]

    class DEBUG_UNION(ctypes.Union):
        _fields_ = [("Exception", EXCEPTION_DEBUG_INFO), ("padding", ctypes.c_byte * 176)]

    class DEBUG_EVENT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("dwDebugEventCode", wintypes.DWORD), ("dwProcessId", wintypes.DWORD),
                    ("dwThreadId", wintypes.DWORD), ("u", DEBUG_UNION)]

    class CONTEXT64(ctypes.Structure):
        _fields_ = [("P1Home", ctypes.c_ulonglong), ("P2Home", ctypes.c_ulonglong),
            ("P3Home", ctypes.c_ulonglong), ("P4Home", ctypes.c_ulonglong),
            ("P5Home", ctypes.c_ulonglong), ("P6Home", ctypes.c_ulonglong),
            ("ContextFlags", wintypes.DWORD), ("MxCsr", wintypes.DWORD),
            ("SegCs", wintypes.WORD), ("SegDs", wintypes.WORD), ("SegEs", wintypes.WORD),
            ("SegFs", wintypes.WORD), ("SegGs", wintypes.WORD), ("SegSs", wintypes.WORD),
            ("EFlags", wintypes.DWORD), ("Dr0", ctypes.c_ulonglong), ("Dr1", ctypes.c_ulonglong),
            ("Dr2", ctypes.c_ulonglong), ("Dr3", ctypes.c_ulonglong),
            ("Dr6", ctypes.c_ulonglong), ("Dr7", ctypes.c_ulonglong),
            ("Rax", ctypes.c_ulonglong), ("Rcx", ctypes.c_ulonglong),
            ("Rdx", ctypes.c_ulonglong), ("Rbx", ctypes.c_ulonglong),
            ("Rsp", ctypes.c_ulonglong), ("Rbp", ctypes.c_ulonglong),
            ("Rsi", ctypes.c_ulonglong), ("Rdi", ctypes.c_ulonglong),
            ("R8", ctypes.c_ulonglong), ("R9", ctypes.c_ulonglong),
            ("R10", ctypes.c_ulonglong), ("R11", ctypes.c_ulonglong),
            ("R12", ctypes.c_ulonglong), ("R13", ctypes.c_ulonglong),
            ("R14", ctypes.c_ulonglong), ("R15", ctypes.c_ulonglong),
            ("Rip", ctypes.c_ulonglong), ("Extended", ctypes.c_byte * (1232 - 256))]

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.VirtualProtectEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                          wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetThreadContext.argtypes = [wintypes.HANDLE, ctypes.POINTER(CONTEXT64)]
    kernel32.SetThreadContext.argtypes = [wintypes.HANDLE, ctypes.POINTER(CONTEXT64)]
    kernel32.WaitForDebugEvent.argtypes = [ctypes.POINTER(DEBUG_EVENT), wintypes.DWORD]
    kernel32.ContinueDebugEvent.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]


class RuntimeCapture:
    def __init__(self, pid: int, exe: Path, wad: Path, tool_commit: str, output: Path, runs: int):
        if sys.platform != "win32":
            raise RuntimeError("live capture requires Windows")
        self.pid, self.exe, self.wad = pid, exe, wad
        self.tool_commit, self.output, self.run_count = tool_commit, output, runs
        self.target = load_target_record(wad)
        verify_image(exe)
        self.process = kernel32.OpenProcess(PROCESS_ACCESS, False, pid)
        if not self.process:
            raise ctypes.WinError(ctypes.get_last_error())
        self.module_base, self.module_path = self._module()
        if Path(self.module_path).resolve() != exe.resolve():
            raise RuntimeError(f"debugged module differs from verified EXE: {self.module_path}")
        self.breakpoints: dict[int, dict] = {}
        self.pending_reinsert: dict[int, int] = {}
        self.suspended: dict[int, list[int]] = {}
        self.pending_loader: dict[int, dict] = {}
        self.pending_allocator: dict[int, dict] = {}
        self.histories: dict[int, dict] = {}
        self.initial_registry_ids: set[int] = set()
        self.runs: list[dict] = []
        self.errors: list[str] = []
        self.attached = False

    def _module(self) -> tuple[int, str]:
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, self.pid)
        if snapshot == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            row = MODULEENTRY32W(); row.dwSize = ctypes.sizeof(row)
            if not kernel32.Module32FirstW(snapshot, ctypes.byref(row)):
                raise ctypes.WinError(ctypes.get_last_error())
            return ctypes.addressof(row.modBaseAddr.contents), row.szExePath
        finally:
            kernel32.CloseHandle(snapshot)

    def read(self, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        done = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(self.process, ctypes.c_void_p(address), buffer, size, ctypes.byref(done)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[:done.value]

    def write(self, address: int, data: bytes) -> None:
        old = wintypes.DWORD()
        if not kernel32.VirtualProtectEx(self.process, ctypes.c_void_p(address), len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(old)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            done = ctypes.c_size_t()
            if not kernel32.WriteProcessMemory(self.process, ctypes.c_void_p(address), data, len(data), ctypes.byref(done)) or done.value != len(data):
                raise ctypes.WinError(ctypes.get_last_error())
            kernel32.FlushInstructionCache(self.process, ctypes.c_void_p(address), len(data))
        finally:
            ignored = wintypes.DWORD()
            kernel32.VirtualProtectEx(self.process, ctypes.c_void_p(address), len(data), old.value, ctypes.byref(ignored))

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def _context(self, tid: int) -> tuple[int, CONTEXT64]:
        thread = kernel32.OpenThread(THREAD_ACCESS, False, tid)
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        context = CONTEXT64(); context.ContextFlags = CONTEXT_ALL
        if not kernel32.GetThreadContext(thread, ctypes.byref(context)):
            kernel32.CloseHandle(thread)
            raise ctypes.WinError(ctypes.get_last_error())
        return thread, context

    def _thread_ids(self) -> list[int]:
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        result = []
        try:
            row = THREADENTRY32(); row.dwSize = ctypes.sizeof(row)
            ok = kernel32.Thread32First(snapshot, ctypes.byref(row))
            while ok:
                if row.th32OwnerProcessID == self.pid:
                    result.append(row.th32ThreadID)
                ok = kernel32.Thread32Next(snapshot, ctypes.byref(row))
        finally:
            kernel32.CloseHandle(snapshot)
        return result

    def _suspend_others(self, hit_tid: int) -> None:
        held = []
        for tid in self._thread_ids():
            if tid == hit_tid:
                continue
            handle = kernel32.OpenThread(0x0002, False, tid)
            if handle and kernel32.SuspendThread(handle) != 0xFFFFFFFF:
                held.append(handle)
            elif handle:
                kernel32.CloseHandle(handle)
        self.suspended[hit_tid] = held

    def _resume_others(self, hit_tid: int) -> None:
        for handle in self.suspended.pop(hit_tid, []):
            kernel32.ResumeThread(handle)
            kernel32.CloseHandle(handle)

    def _install(self) -> None:
        for name, (rva, expected_hex) in BREAKPOINTS.items():
            address = self.module_base + rva
            expected = bytes.fromhex(expected_hex)
            actual = self.read(address, len(expected))
            if actual != expected:
                raise RuntimeError(f"live instruction mismatch for {name}: {actual.hex()}")
            self.breakpoints[address] = {"name": name, "rva": rva, "original": expected[:1], "armed": False}
        for address, item in self.breakpoints.items():
            self.write(address, b"\xCC"); item["armed"] = True

    def _restore_all(self) -> bool:
        error_count = len(self.errors)
        for tid in list(self.pending_reinsert):
            try:
                thread, context = self._context(tid)
                try:
                    context.EFlags &= ~0x100
                    if not kernel32.SetThreadContext(thread, ctypes.byref(context)):
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    kernel32.CloseHandle(thread)
            except Exception as error:
                self.errors.append(f"trap-flag restore failed for thread {tid}: {error}")
        self.pending_reinsert.clear()
        for address, item in self.breakpoints.items():
            try:
                if item["armed"]:
                    self.write(address, item["original"]); item["armed"] = False
            except Exception as error:
                self.errors.append(f"breakpoint restore failed at 0x{address:X}: {error}")
        for tid in list(self.suspended):
            self._resume_others(tid)
        return len(self.errors) == error_count

    def _walk_list(self, sentinel: int, index: int) -> int:
        current = self.u64(sentinel)
        for _ in range(index):
            if current == sentinel:
                raise RuntimeError("scheduler list ended before requested index")
            current = self.u64(current)
        if current == sentinel:
            raise RuntimeError("scheduler index resolved to sentinel")
        return current

    def _blob(self, label: str, address: int, size: int, parent: str | None = None, pointer_offset: int | None = None) -> dict:
        data = self.read(address, size)
        return {"label": label, "address": f"0x{address:X}", "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(), "parent": parent,
                "pointer_offset": pointer_offset, "data_base64": base64.b64encode(data).decode("ascii")}

    def _pointer_graph(self, roots: list[tuple[str, int, int]], depth: int = 2, limit: int = 96) -> list[dict]:
        queue = [(label, address, size, None, None, 0) for label, address, size in roots if address]
        seen, blobs = set(), []
        while queue and len(blobs) < limit:
            label, address, size, parent, pointer_offset, level = queue.pop(0)
            if address in seen or not 0x10000 <= address <= 0x00007FFFFFFFFFFF:
                continue
            seen.add(address)
            try:
                blob = self._blob(label, address, min(size, 0x1000), parent, pointer_offset)
            except OSError:
                continue
            blobs.append(blob)
            if level >= depth:
                continue
            data = base64.b64decode(blob["data_base64"])
            for offset in range(0, len(data) - 7, 8):
                pointer = struct.unpack_from("<Q", data, offset)[0]
                if 0x10000 <= pointer <= 0x00007FFFFFFFFFFF and pointer not in seen:
                    queue.append((f"ptr_d{level + 1}_{len(blobs)}_{offset:X}", pointer, 0x400,
                                  blob["label"], offset, level + 1))
        return blobs

    def _on_loader(self, tid: int, context: CONTEXT64) -> None:
        outer_index = self.u32(context.Rbp - 0x20)
        inner_index = self.u32(context.Rbp - 0x80)
        inner_saved = self.u64(context.Rbp - 0x18)
        wad_saved = self.u64(context.Rbp - 0x70)
        outer = self._walk_list(self.module_base + SCHEDULER_OUTER_SENTINEL_RVA, outer_index)
        inner = self._walk_list(outer + 0x20, inner_index)
        wad_from_outer = self.u64(outer + 0x40)
        if inner != inner_saved or wad_saved != context.Rdx or wad_from_outer != context.Rdx:
            raise RuntimeError("worker frame does not match scheduler list/WAD ancestry")
        inner_data = self.u64(inner + 0x10)
        blobs = self._pointer_graph([
            ("descriptor", context.Rcx, 0x220), ("descriptor_source", context.Rbp + 0x820, 0x190),
            ("scheduler_outer", outer, 0x80), ("scheduler_inner", inner, 0x80),
            ("scheduler_inner_data", inner_data, 0x300), ("wad", context.Rdx, 0xD00),
        ])
        binding = exact_binding_from_blobs(blobs, self.target)
        wad_names = (TARGET_WAD.encode("ascii").lower(), b"wad_alf355_chiseldungeon")
        wad_name_hits = []
        parents = {blob["label"]: blob.get("parent") for blob in blobs}

        def ancestry_root(label: str) -> str:
            seen = set()
            while parents.get(label) and label not in seen:
                seen.add(label)
                label = parents[label]
            return label

        for blob in blobs:
            data = base64.b64decode(blob["data_base64"]).lower()
            for wad_name in wad_names:
                found = data.find(wad_name)
                if found >= 0:
                    wad_name_hits.append({"blob": blob["label"], "offset": found,
                                          "matched": wad_name.decode("ascii"),
                                          "ancestry_root": ancestry_root(blob["label"])})
        for hit in binding["hits"]:
            hit["ancestry_root"] = ancestry_root(hit["blob"])
        binding["record_bytes_proved"] = binding["proved"]
        binding["canonical_wad_identity_proved"] = any(
            hit["ancestry_root"] in {"wad", "scheduler_outer", "scheduler_inner", "scheduler_inner_data"}
            for hit in wad_name_hits
        )
        binding["proved"] = binding["record_bytes_proved"] and binding["canonical_wad_identity_proved"]
        event = {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "thread_id": tid, "outer_index": outer_index, "inner_index": inner_index,
            "outer_pointer": f"0x{outer:X}", "inner_pointer": f"0x{inner:X}",
            "inner_data_pointer": f"0x{inner_data:X}", "descriptor_pointer": f"0x{context.Rcx:X}",
            "wad_pointer": f"0x{context.Rdx:X}", "wad_registry_id": self.u32(context.Rdx + 0xC3C),
            "wad_name_hits": wad_name_hits, "exact_record_binding": binding, "provenance_blobs": blobs,
        }
        if binding["proved"]:
            self.pending_loader[tid] = event

    def _registry_for_id(self, registry_id: int) -> tuple[int, int]:
        table = self.module_base + REGISTRY_TABLE_RVA
        for index in range(64):
            pointer = self.u64(table + index * 8)
            if pointer and self.u32(pointer) == registry_id:
                return index, pointer
        raise RuntimeError(f"registry {registry_id} absent from global table")

    def _snapshot_initial_registries(self) -> None:
        table = self.module_base + REGISTRY_TABLE_RVA
        for index in range(64):
            pointer = self.u64(table + index * 8)
            if pointer:
                self.initial_registry_ids.add(self.u32(pointer))

    def _on_allocator(self, tid: int, context: CONTEXT64) -> None:
        loader = self.pending_loader.get(tid)
        if loader is not None and context.R8 != 0:
            raise RuntimeError("canonical target unexpectedly used explicit slot hint")
        registry_id = context.Rdx & 0xFFFFFFFF
        if loader is not None and registry_id != loader["wad_registry_id"]:
            raise RuntimeError("allocator registry ID differs from target WAD +0xC3C")
        table_index, registry = self._registry_for_id(registry_id)
        bank_pointer = self.u64(registry + 0x20)
        cursor, live_count, capacity = struct.unpack("<III", self.read(registry + 0x28, 12))
        bank = list(struct.unpack(f"<{capacity}Q", self.read(bank_pointer, capacity * 8)))
        if context.R8:
            hint = self.u32(context.R8 + 4)
            scan = ({"start_cursor": hint, "tested": [{"slot": 0, "occupied": bool(bank[0]),
                     "object": f"0x{bank[0]:X}"}], "selected_slot": 0, "next_cursor": cursor}
                    if hint == 0 else circular_scan(bank, hint, capacity))
        else:
            scan = circular_scan(bank, cursor, capacity)
        occupancy = bytes(1 if value else 0 for value in bank)
        history = self.histories.setdefault(registry_id, {
            "events": [], "expected_bank": None, "external_changes": [],
            "first_observed_empty": False,
        })
        external = []
        if history["expected_bank"] is None:
            history["first_observed_empty"] = cursor == 0 and live_count == 0 and not any(bank)
        else:
            external = [index for index, (expected, actual) in enumerate(zip(history["expected_bank"], bank))
                        if expected != actual]
            if external:
                history["external_changes"].append({"before_event": len(history["events"]), "slots": external})
        allocation = {
            "object_pointer": f"0x{context.Rcx:X}", "registry_id": registry_id,
            "registry_pointer": f"0x{registry:X}", "registry_table_index": table_index,
            "bank_pointer": f"0x{bank_pointer:X}", "cursor": cursor, "live_count": live_count,
            "capacity": capacity, "occupancy_sha256": hashlib.sha256(occupancy).hexdigest(),
            "scan": scan, "selected_slot": scan["selected_slot"], "slot_hint_pointer": context.R8,
            "external_bank_changes_since_previous_allocation": external,
        }
        compact = {key: allocation[key] for key in (
            "registry_id", "registry_table_index", "cursor", "live_count", "capacity",
            "occupancy_sha256", "selected_slot", "external_bank_changes_since_previous_allocation")}
        compact["ordinal"] = len(history["events"])
        history["events"].append(compact)
        predicted = list(bank)
        predicted[scan["selected_slot"]] = context.Rcx
        history["expected_bank"] = predicted
        self.pending_allocator[tid] = {"loader": loader, "allocator": allocation,
                                       "object": context.Rcx, "history": history}

    def _on_fields_ready(self, tid: int, context: CONTEXT64) -> None:
        pending = self.pending_allocator.pop(tid, None)
        if pending is None or pending["object"] != context.Rdi:
            return
        field_278 = self.u32(context.Rdi + 0x278)
        field_280 = self.u32(context.Rdi + 0x280)
        field_284 = self.u32(context.Rdi + 0x284)
        decoded = gameobject_tuple(field_278, field_280, field_284)
        allocation = pending["allocator"]
        if decoded["registry_id"] != allocation["registry_id"] or decoded["slot"] != allocation["selected_slot"]:
            raise RuntimeError("GameObject fields differ from allocator inputs/selected slot")
        loader = pending["loader"]
        if loader is None:
            return
        history = pending["history"]
        normalized_history = history["events"]
        history_hash = hashlib.sha256(json.dumps(
            normalized_history, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        state_complete = (
            allocation["registry_id"] not in self.initial_registry_ids
            and history["first_observed_empty"] and not history["external_changes"]
        )
        run = {
            "run_label": chr(ord("A") + len(self.runs)),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "executable": {"path": str(self.exe), "sha256": EXPECTED_EXE_SHA256, "module_base": f"0x{self.module_base:X}"},
            "capture_tool_commit": self.tool_commit,
            "target": {"instance_guid": TARGET_GUID, "wad": TARGET_WAD,
                       "wad_sha256": TARGET_WAD_SHA256, "record_offset": f"0x{TARGET_RECORD_OFFSET:X}",
                       "record_index": TARGET_RECORD_INDEX, "record_id": TARGET_RECORD_ID},
            "scheduler": {key: value for key, value in loader.items() if key not in ("provenance_blobs", "exact_record_binding")},
            "exact_record_binding": loader["exact_record_binding"],
            "provenance_blobs": loader["provenance_blobs"],
            "allocator": allocation,
            "gameobject": {"pointer": f"0x{context.Rdi:X}", "field_0x278": field_278,
                           "field_0x280": field_280, "field_0x284": field_284, "decoded": decoded},
            "allocator_history": {
                "complete_since_fresh_registry": state_complete,
                "stable_event_identities_complete": False,
                "causal_sha256": history_hash if state_complete else None,
                "events": normalized_history,
                "external_bank_changes": history["external_changes"],
                "reason": "Allocator state transitions are captured from first empty observation when possible; stable canonical identities for preceding events remain unbound.",
            },
            "registry_lifecycle": (
                "not present at attach; first allocation observed with empty bank/cursor/live count"
                if state_complete else "pre-existing, reused, or changed outside captured allocation events"
            ),
            "safety": {"exe_disk_written": False, "save_written": False, "progression_written": False,
                       "temporary_process_breakpoints_restored_on_detach": True},
        }
        self.runs.append(run)
        self.pending_loader.pop(tid, None)
        print(f"RUN_{run['run_label']}_EXACT_TARGET_CAPTURED", flush=True)
        if len(self.runs) < self.run_count:
            print("Return to main menu. Reload same save/context. Approach exact Raven again. Do not kill or collect it.", flush=True)

    def _handle_hit(self, tid: int, address: int, item: dict) -> None:
        thread, context = self._context(tid)
        try:
            context.Rip = address
            try:
                if item["name"] == "canonical_loader_call":
                    self._on_loader(tid, context)
                elif item["name"] == "allocator_entry":
                    self._on_allocator(tid, context)
                elif item["name"] == "allocator_fields_ready":
                    self._on_fields_ready(tid, context)
            except Exception as error:
                self.errors.append(f"{item['name']} observation failed: {error}")
            self.write(address, item["original"]); item["armed"] = False
            self._suspend_others(tid)
            context.EFlags |= 0x100
            if not kernel32.SetThreadContext(thread, ctypes.byref(context)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.pending_reinsert[tid] = address
        except Exception:
            try:
                context.Rip = address
                context.EFlags &= ~0x100
                if not kernel32.SetThreadContext(thread, ctypes.byref(context)):
                    raise ctypes.WinError(ctypes.get_last_error())
            except Exception as rollback_error:
                self.errors.append(f"thread-context rollback failed for thread {tid}: {rollback_error}")
            self._resume_others(tid)
            raise
        finally:
            kernel32.CloseHandle(thread)

    def _single_step(self, tid: int) -> None:
        address = self.pending_reinsert.get(tid)
        if address is None:
            return
        item = self.breakpoints[address]
        self.write(address, b"\xCC"); item["armed"] = True
        thread, context = self._context(tid)
        try:
            context.EFlags &= ~0x100
            if not kernel32.SetThreadContext(thread, ctypes.byref(context)):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(thread)
        self.pending_reinsert.pop(tid, None)
        self._resume_others(tid)

    def _write_output(self, complete: bool, cleanup_ok: bool) -> None:
        for run in self.runs:
            run["safety"]["temporary_process_breakpoints_restored_on_detach"] = cleanup_ok
        result = {
            "schema": 1, "analysis": "gow_raven_scheduler_allocator_runtime",
            "capture_complete": complete, "requested_runs": self.run_count, "captured_runs": len(self.runs),
            "runs": self.runs, "errors": self.errors,
            "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
            "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        }
        if len(self.runs) >= 2:
            result["comparison"] = compare_runs(self.runs[0], self.runs[1])
            result["gameobject_persistent_key_status"] = result["comparison"]["gameobject_persistent_key_status"]
        self.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def run(self) -> int:
        print("Debugger ready. Load same target save/context. Approach exact Raven. Do not kill or collect it.", flush=True)
        if not kernel32.DebugActiveProcess(self.pid):
            raise ctypes.WinError(ctypes.get_last_error())
        self.attached = True
        event = DEBUG_EVENT()
        cleanup_ok = False
        try:
            if not kernel32.DebugSetProcessKillOnExit(False):
                raise ctypes.WinError(ctypes.get_last_error())
            self._install()
            self._snapshot_initial_registries()
            while len(self.runs) < self.run_count:
                if not kernel32.WaitForDebugEvent(ctypes.byref(event), 1000):
                    if ctypes.get_last_error() == 121:
                        continue
                    raise ctypes.WinError(ctypes.get_last_error())
                status = DBG_CONTINUE
                if event.dwDebugEventCode == EXCEPTION_DEBUG_EVENT:
                    code = event.Exception.ExceptionRecord.ExceptionCode
                    address = int(event.Exception.ExceptionRecord.ExceptionAddress or 0)
                    if code == EXCEPTION_BREAKPOINT and address in self.breakpoints:
                        self._handle_hit(event.dwThreadId, address, self.breakpoints[address])
                    elif code == EXCEPTION_SINGLE_STEP and event.dwThreadId in self.pending_reinsert:
                        self._single_step(event.dwThreadId)
                    elif code not in (EXCEPTION_BREAKPOINT,):
                        status = DBG_EXCEPTION_NOT_HANDLED
                elif event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT:
                    self.errors.append("GoW.exe exited before requested captures completed")
                    if not kernel32.ContinueDebugEvent(event.dwProcessId, event.dwThreadId, status):
                        raise ctypes.WinError(ctypes.get_last_error())
                    break
                if not kernel32.ContinueDebugEvent(event.dwProcessId, event.dwThreadId, status):
                    raise ctypes.WinError(ctypes.get_last_error())
        except KeyboardInterrupt:
            self.errors.append("capture interrupted")
        finally:
            cleanup_ok = self._restore_all()
            if self.attached:
                if not kernel32.DebugActiveProcessStop(self.pid):
                    self.errors.append(f"debugger detach failed: {ctypes.WinError(ctypes.get_last_error())}")
                    cleanup_ok = False
                self.attached = False
            kernel32.CloseHandle(self.process)
            self._write_output(len(self.runs) == self.run_count and cleanup_ok, cleanup_ok)
        return 0 if len(self.runs) == self.run_count and cleanup_ok else 2


def self_test() -> None:
    token = encode_token(0x1234, 1, 0x54321)
    assert decode_token(token) == {"registry_id": 0x1234, "flavor": 1, "slot": 0x54321}
    bank = [0, 11, 22, 0, 44]
    assert circular_scan(bank, 1, 5)["selected_slot"] == 3
    assert circular_scan([0, 0, 2], 0, 3)["selected_slot"] == 1
    print("SELF_TEST_PASSED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    capture = sub.add_parser("capture")
    capture.add_argument("--pid", type=int, required=True)
    capture.add_argument("--exe", type=Path, required=True)
    capture.add_argument("--wad", type=Path, required=True)
    capture.add_argument("--tool-commit", required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--runs", type=int, default=2)
    compare = sub.add_parser("compare")
    compare.add_argument("--run-a", type=Path, required=True)
    compare.add_argument("--run-b", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    if args.command == "compare":
        result = compare_runs(json.loads(args.run_a.read_text()), json.loads(args.run_b.read_text()))
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(result["gameobject_persistent_key_status"])
        print(result["production_oracle_status"])
        return 0
    if args.command == "capture":
        if args.runs != 2:
            raise SystemExit("capture requires exactly two clean reload runs")
        return RuntimeCapture(args.pid, args.exe, args.wad, args.tool_commit, args.output, args.runs).run()
    parser.error("choose capture or compare, or use --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
