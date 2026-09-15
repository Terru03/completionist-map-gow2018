"""Compatibility launcher for Raven scheduler/allocator runtime capture.

Loads the version-locked capture implementation unchanged, but replaces only
process module discovery with a PSAPI-first implementation plus Toolhelp retry.
This isolates Windows/Steam startup enumeration quirks from capture semantics.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import importlib.util
from pathlib import Path
import sys
import time


CAPTURE = Path(__file__).with_name("capture-raven-scheduler-allocator-runtime.py")


def load_capture():
    spec = importlib.util.spec_from_file_location("raven_runtime_capture_compat_target", CAPTURE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CAPTURE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_module_discovery(module) -> None:
    psapi = module.psapi
    kernel32 = module.kernel32

    LIST_MODULES_ALL = 0x03
    ERROR_BAD_LENGTH = 24
    ERROR_PARTIAL_COPY = 299

    psapi.EnumProcessModulesEx.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
    ]
    psapi.EnumProcessModulesEx.restype = wintypes.BOOL
    psapi.GetModuleFileNameExW.argtypes = [
        wintypes.HANDLE,
        wintypes.HMODULE,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    psapi.GetModuleFileNameExW.restype = wintypes.DWORD

    kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(module.MODULEENTRY32W)]
    kernel32.Module32FirstW.restype = wintypes.BOOL

    def psapi_module(self):
        modules = (wintypes.HMODULE * 2048)()
        needed = wintypes.DWORD()
        ctypes.set_last_error(0)
        ok = psapi.EnumProcessModulesEx(
            self.process,
            modules,
            ctypes.sizeof(modules),
            ctypes.byref(needed),
            LIST_MODULES_ALL,
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        count = needed.value // ctypes.sizeof(wintypes.HMODULE)
        if count < 1:
            raise RuntimeError("PSAPI returned no modules for GoW process")
        if count > len(modules):
            raise RuntimeError(f"PSAPI module buffer too small: required {count}, capacity {len(modules)}")
        exe_module = modules[0]
        path_buffer = ctypes.create_unicode_buffer(32768)
        ctypes.set_last_error(0)
        length = psapi.GetModuleFileNameExW(
            self.process, exe_module, path_buffer, len(path_buffer)
        )
        if not length:
            raise ctypes.WinError(ctypes.get_last_error())
        base = ctypes.cast(exe_module, ctypes.c_void_p).value
        if not base:
            raise RuntimeError("PSAPI returned null executable module base")
        return int(base), path_buffer.value

    def toolhelp_module(self):
        last_error = 0
        for attempt in range(1, 61):
            ctypes.set_last_error(0)
            snapshot = kernel32.CreateToolhelp32Snapshot(module.TH32CS_SNAPMODULE, self.pid)
            if snapshot == module.INVALID_HANDLE_VALUE:
                last_error = ctypes.get_last_error()
                if last_error in (ERROR_BAD_LENGTH, ERROR_PARTIAL_COPY):
                    time.sleep(0.1)
                    continue
                raise ctypes.WinError(last_error)
            try:
                row = module.MODULEENTRY32W()
                row.dwSize = ctypes.sizeof(row)
                ctypes.set_last_error(0)
                if kernel32.Module32FirstW(snapshot, ctypes.byref(row)):
                    return ctypes.addressof(row.modBaseAddr.contents), row.szExePath
                last_error = ctypes.get_last_error()
            finally:
                kernel32.CloseHandle(snapshot)
            if last_error in (ERROR_BAD_LENGTH, ERROR_PARTIAL_COPY, 18):
                time.sleep(0.1)
                continue
            raise ctypes.WinError(last_error)
        raise ctypes.WinError(last_error)

    def robust_module(self):
        print("CAPTURE_STARTUP_STAGE=ModuleDiscoveryPSAPI", flush=True)
        try:
            base, path = psapi_module(self)
            print(f"CAPTURE_MODULE_DISCOVERY=PSAPI base=0x{base:X} path={path}", flush=True)
            return base, path
        except Exception as error:
            print(f"CAPTURE_MODULE_DISCOVERY_PSAPI_FAILED={error}", flush=True)
        print("CAPTURE_STARTUP_STAGE=ModuleDiscoveryToolhelpRetry", flush=True)
        base, path = toolhelp_module(self)
        print(f"CAPTURE_MODULE_DISCOVERY=TOOLHELP base=0x{base:X} path={path}", flush=True)
        return base, path

    module.RuntimeCapture._module = robust_module


def main() -> int:
    module = load_capture()
    if sys.platform == "win32":
        install_module_discovery(module)
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
