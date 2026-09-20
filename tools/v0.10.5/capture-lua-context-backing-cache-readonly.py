#!/usr/bin/env python3
"""Enumerate unloaded-resource Lua backing nodes from a running GoW process.

Read-only runtime capture. No debugger, no process writes, no save-file access.

Discovery:
- locate exact LuaContext vtable pointer (module_base + 0xDF2F50)
  in committed private writable memory;
- validate candidate+0x178 as a reciprocal sentinel-headed intrusive list;
- walk each validated cache and record 0x30-byte backing-node fields.

Known build: GoW.exe SHA256
caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import struct
import sys
from ctypes import wintypes as W
from datetime import datetime, timezone
from pathlib import Path

EXE_SHA="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
LUA_CONTEXT_VTABLE_RVA=0xDF2F50
CACHE_HEAD_OFFSET=0x178
NODE_SIZE=0x30

PROCESS_VM_READ=0x0010
PROCESS_QUERY_INFORMATION=0x0400
TH32CS_SNAPPROCESS=0x00000002
TH32CS_SNAPMODULE=0x00000008
TH32CS_SNAPMODULE32=0x00000010
INVALID_HANDLE_VALUE=C.c_void_p(-1).value
MAX_PATH=260

MEM_COMMIT=0x1000
MEM_PRIVATE=0x20000
PAGE_NOACCESS=0x01
PAGE_READONLY=0x02
PAGE_READWRITE=0x04
PAGE_WRITECOPY=0x08
PAGE_EXECUTE_READWRITE=0x40
PAGE_EXECUTE_WRITECOPY=0x80
PAGE_GUARD=0x100

SCAN_PROTECTIONS={PAGE_READWRITE,PAGE_WRITECOPY,PAGE_EXECUTE_READWRITE,PAGE_EXECUTE_WRITECOPY}
MAX_USER_ADDRESS=0x00007FFFFFFFFFFF
SCAN_CHUNK=4*1024*1024
MAX_CANDIDATES=256
MAX_CACHE_NODES=4096

class PROCESSENTRY32W(C.Structure):
    _fields_=[
        ("dwSize",W.DWORD),("cntUsage",W.DWORD),("th32ProcessID",W.DWORD),
        ("th32DefaultHeapID",C.c_size_t),("th32ModuleID",W.DWORD),
        ("cntThreads",W.DWORD),("th32ParentProcessID",W.DWORD),
        ("pcPriClassBase",W.LONG),("dwFlags",W.DWORD),("szExeFile",W.WCHAR*MAX_PATH),
    ]

class MODULEENTRY32W(C.Structure):
    _fields_=[
        ("dwSize",W.DWORD),("th32ModuleID",W.DWORD),("th32ProcessID",W.DWORD),
        ("GlblcntUsage",W.DWORD),("ProccntUsage",W.DWORD),
        ("modBaseAddr",C.POINTER(C.c_ubyte)),("modBaseSize",W.DWORD),
        ("hModule",W.HMODULE),("szModule",W.WCHAR*256),("szExePath",W.WCHAR*MAX_PATH),
    ]

class MEMORY_BASIC_INFORMATION64(C.Structure):
    _fields_=[
        ("BaseAddress",C.c_void_p),
        ("AllocationBase",C.c_void_p),
        ("AllocationProtect",W.DWORD),
        ("__alignment1",W.DWORD),
        ("RegionSize",C.c_size_t),
        ("State",W.DWORD),
        ("Protect",W.DWORD),
        ("Type",W.DWORD),
        ("__alignment2",W.DWORD),
    ]

def k32_api():
    k=C.WinDLL("kernel32",use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD]
    k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Process32FirstW.argtypes=[W.HANDLE,C.POINTER(PROCESSENTRY32W)]
    k.Process32FirstW.restype=W.BOOL
    k.Process32NextW.argtypes=[W.HANDLE,C.POINTER(PROCESSENTRY32W)]
    k.Process32NextW.restype=W.BOOL
    k.Module32FirstW.argtypes=[W.HANDLE,C.POINTER(MODULEENTRY32W)]
    k.Module32FirstW.restype=W.BOOL
    k.Module32NextW.argtypes=[W.HANDLE,C.POINTER(MODULEENTRY32W)]
    k.Module32NextW.restype=W.BOOL
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]
    k.OpenProcess.restype=W.HANDLE
    k.ReadProcessMemory.argtypes=[W.HANDLE,W.LPCVOID,W.LPVOID,C.c_size_t,C.POINTER(C.c_size_t)]
    k.ReadProcessMemory.restype=W.BOOL
    k.VirtualQueryEx.argtypes=[W.HANDLE,W.LPCVOID,C.POINTER(MEMORY_BASIC_INFORMATION64),C.c_size_t]
    k.VirtualQueryEx.restype=C.c_size_t
    k.CloseHandle.argtypes=[W.HANDLE]
    k.CloseHandle.restype=W.BOOL
    return k

def close(k,h):
    if h and int(C.cast(h,C.c_void_p).value or 0) not in (0,INVALID_HANDLE_VALUE):
        k.CloseHandle(h)

def winerr(prefix):
    code=C.get_last_error()
    return RuntimeError(f"{prefix}: WinError {code}: {C.FormatError(code).strip()}")

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def find_process(k):
    snap=k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0)
    if C.cast(snap,C.c_void_p).value==INVALID_HANDLE_VALUE:
        raise winerr("process snapshot failed")
    found=[]
    try:
        pe=PROCESSENTRY32W();pe.dwSize=C.sizeof(pe)
        ok=k.Process32FirstW(snap,C.byref(pe))
        while ok:
            name=str(pe.szExeFile)
            if name.lower() in {"gow.exe","godofwar.exe"}:
                found.append((int(pe.th32ProcessID),name))
            ok=k.Process32NextW(snap,C.byref(pe))
    finally:
        close(k,snap)
    if len(found)!=1:
        raise RuntimeError(f"expected one running God of War process, found {found}")
    return found[0]

def main_module(k,pid,name):
    snap=k.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid)
    if C.cast(snap,C.c_void_p).value==INVALID_HANDLE_VALUE:
        raise winerr("module snapshot failed")
    try:
        me=MODULEENTRY32W();me.dwSize=C.sizeof(me)
        ok=k.Module32FirstW(snap,C.byref(me))
        while ok:
            if str(me.szModule).lower()==name.lower():
                base=C.cast(me.modBaseAddr,C.c_void_p).value
                if not base:raise RuntimeError("NULL module base")
                return int(base),int(me.modBaseSize),str(me.szExePath)
            ok=k.Module32NextW(snap,C.byref(me))
    finally:
        close(k,snap)
    raise RuntimeError("main GoW module not found")

def read(k,p,address,size):
    if size<=0:return b""
    buf=(C.c_ubyte*size)()
    done=C.c_size_t()
    if not k.ReadProcessMemory(p,C.c_void_p(address),buf,size,C.byref(done)):
        raise winerr(f"ReadProcessMemory(0x{address:X},{size}) failed")
    if done.value!=size:
        raise RuntimeError(f"short read 0x{address:X}: {done.value}/{size}")
    return bytes(buf)

def safe_read(k,p,address,size):
    try:return read(k,p,address,size)
    except Exception:return None

def u32(raw,off):return struct.unpack_from("<I",raw,off)[0]
def i32(raw,off):return struct.unpack_from("<i",raw,off)[0]
def u64(raw,off):return struct.unpack_from("<Q",raw,off)[0]

def is_canonical_user_ptr(v):
    return v==0 or (0x10000<=v<=MAX_USER_ADDRESS)

def region_iter(k,p):
    addr=0
    mbi=MEMORY_BASIC_INFORMATION64()
    sz=C.sizeof(mbi)
    while addr<MAX_USER_ADDRESS:
        got=k.VirtualQueryEx(p,C.c_void_p(addr),C.byref(mbi),sz)
        if not got:
            # Sparse/unqueryable address: advance one allocation granularity.
            addr+=0x10000
            continue
        base=int(C.cast(mbi.BaseAddress,C.c_void_p).value or 0)
        size=int(mbi.RegionSize)
        if size<=0:
            addr+=0x1000
            continue
        yield {
            "base":base,"size":size,"state":int(mbi.State),
            "protect":int(mbi.Protect),"type":int(mbi.Type),
            "allocation_base":int(C.cast(mbi.AllocationBase,C.c_void_p).value or 0),
        }
        nxt=base+size
        addr=nxt if nxt>addr else addr+0x1000

def scan_vtable_candidates(k,p,vtable_ptr):
    pattern=struct.pack("<Q",vtable_ptr)
    candidates=[]
    stats={"regions_total":0,"regions_scanned":0,"bytes_scanned":0,"read_failures":0,"raw_pattern_hits":0}
    for reg in region_iter(k,p):
        stats["regions_total"]+=1
        prot=reg["protect"]
        baseprot=prot&0xFF
        if reg["state"]!=MEM_COMMIT or reg["type"]!=MEM_PRIVATE:
            continue
        if prot&PAGE_GUARD or baseprot==PAGE_NOACCESS or baseprot not in SCAN_PROTECTIONS:
            continue
        stats["regions_scanned"]+=1
        start=reg["base"];remaining=reg["size"];pos=0;tail=b""
        while pos<remaining:
            want=min(SCAN_CHUNK,remaining-pos)
            raw=safe_read(k,p,start+pos,want)
            if raw is None:
                stats["read_failures"]+=1
                pos+=want
                tail=b""
                continue
            stats["bytes_scanned"]+=len(raw)
            buf=tail+raw
            base_addr=start+pos-len(tail)
            off=buf.find(pattern)
            while off>=0:
                cand=base_addr+off
                stats["raw_pattern_hits"]+=1
                candidates.append(cand)
                if len(candidates)>MAX_CANDIDATES:
                    raise RuntimeError(f"too many LuaContext vtable candidates (> {MAX_CANDIDATES})")
                off=buf.find(pattern,off+1)
            tail=buf[-7:] if len(buf)>=7 else buf
            pos+=want
    return sorted(set(candidates)),stats

def validate_and_walk(k,p,candidate,vtable_ptr):
    head=candidate+CACHE_HEAD_OFFSET
    h=safe_read(k,p,head,16)
    if h is None:
        return None,"sentinel_unreadable"
    nxt,prev=struct.unpack("<QQ",h)
    if not (is_canonical_user_ptr(nxt) and is_canonical_user_ptr(prev)):
        return None,"sentinel_noncanonical"

    # Empty sentinel is structurally valid.
    if nxt==head and prev==head:
        return {
            "lua_context_ptr":candidate,
            "vtable_ptr":vtable_ptr,
            "cache_head":head,
            "empty":True,
            "nodes":[],
            "node_count":0,
        },None

    if nxt in (0,head) or prev in (0,head):
        return None,"sentinel_half_empty"

    # Reciprocal endpoint validation.
    nr=safe_read(k,p,nxt,16)
    pr=safe_read(k,p,prev,16)
    if nr is None or pr is None:
        return None,"endpoint_unreadable"
    nnext,nprev=struct.unpack("<QQ",nr)
    pnext,pprev=struct.unpack("<QQ",pr)
    if nprev!=head or pnext!=head:
        return None,"sentinel_reciprocal_mismatch"

    nodes=[]
    seen=set()
    cur=nxt
    previous=head
    for idx in range(MAX_CACHE_NODES):
        if cur==head:
            break
        if cur in seen:
            return None,"node_cycle_without_sentinel"
        seen.add(cur)
        raw=safe_read(k,p,cur,NODE_SIZE)
        if raw is None:
            return None,f"node_{idx}_unreadable"
        qnext=u64(raw,0x00);qprev=u64(raw,0x08)
        if qprev!=previous:
            return None,f"node_{idx}_prev_mismatch"
        if not (is_canonical_user_ptr(qnext) and is_canonical_user_ptr(qprev)):
            return None,f"node_{idx}_noncanonical_links"

        next_raw=safe_read(k,p,qnext,16)
        if next_raw is None:
            return None,f"node_{idx}_next_unreadable"
        if u64(next_raw,0x08)!=cur:
            return None,f"node_{idx}_next_prev_mismatch"

        storage=u64(raw,0x28)
        owner=u64(raw,0x20)
        storage_preview=safe_read(k,p,storage,0x40).hex() if storage and safe_read(k,p,storage,0x40) is not None else None
        owner_preview=safe_read(k,p,owner,0x40).hex() if owner and safe_read(k,p,owner,0x40) is not None else None

        nodes.append({
            "index":idx,
            "node_ptr":f"0x{cur:X}",
            "next_ptr":f"0x{qnext:X}",
            "prev_ptr":f"0x{qprev:X}",
            "backing_size_u32":u32(raw,0x10),
            "backing_size_i32":i32(raw,0x10),
            "resource_key_hex":f"0x{u64(raw,0x18):016X}",
            "owner_ptr":f"0x{owner:X}",
            "storage_ptr":f"0x{storage:X}",
            "node_raw_hex":raw.hex(),
            "owner_preview_40_hex":owner_preview,
            "storage_preview_40_hex":storage_preview,
        })
        previous=cur
        cur=qnext
    else:
        return None,f"node_cap_exceeded_{MAX_CACHE_NODES}"

    if cur!=head:
        return None,"walk_did_not_terminate_at_sentinel"
    if previous!=prev:
        return None,"sentinel_prev_does_not_match_last_node"

    return {
        "lua_context_ptr":candidate,
        "vtable_ptr":vtable_ptr,
        "cache_head":head,
        "empty":False,
        "nodes":nodes,
        "node_count":len(nodes),
    },None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--game-root",type=Path,default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    if sys.platform!="win32" or C.sizeof(C.c_void_p)!=8:
        raise RuntimeError("64-bit Windows required")

    k=k32_api()
    pid,name=find_process(k)
    base,module_size,exe_path=main_module(k,pid,name)
    exe_sha=sha256_file(exe_path)
    if exe_sha.lower()!=EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    p=k.OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION,False,pid)
    if not p:raise winerr("OpenProcess read-only failed")
    try:
        expected_vtable=base+LUA_CONTEXT_VTABLE_RVA
        raw_candidates,scan_stats=scan_vtable_candidates(k,p,expected_vtable)
        valid=[];rejected=[]
        for cand in raw_candidates:
            vr=safe_read(k,p,cand,8)
            if vr is None or struct.unpack("<Q",vr)[0]!=expected_vtable:
                rejected.append({"candidate":f"0x{cand:X}","reason":"vtable_changed"})
                continue
            row,reason=validate_and_walk(k,p,cand,expected_vtable)
            if row is None:
                rejected.append({"candidate":f"0x{cand:X}","reason":reason})
            else:
                row={**row,
                     "lua_context_ptr":f"0x{row['lua_context_ptr']:X}",
                     "vtable_ptr":f"0x{row['vtable_ptr']:X}",
                     "cache_head":f"0x{row['cache_head']:X}"}
                valid.append(row)
    finally:
        close(k,p)

    nonempty=[x for x in valid if x["node_count"]>0]
    result={
        "schema":1,
        "captured_utc":datetime.now(timezone.utc).isoformat(),
        "result":"LUA_CONTEXT_BACKING_CACHE_ENUMERATED" if valid else "NO_VALID_LUA_CONTEXT_FOUND",
        "process":{
            "pid":pid,"exe_name":name,"module_base":f"0x{base:X}",
            "module_size":module_size,"exe_sha256":exe_sha,
            "expected_lua_context_vtable":f"0x{base+LUA_CONTEXT_VTABLE_RVA:X}",
        },
        "scan":scan_stats,
        "raw_candidate_count":len(raw_candidates),
        "raw_candidates":[f"0x{x:X}" for x in raw_candidates],
        "valid_context_count":len(valid),
        "nonempty_context_count":len(nonempty),
        "valid_contexts":valid,
        "rejected_candidates":rejected,
        "safety":{
            "open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "virtual_query_ex_only":True,
            "debugger_attached":False,
            "remote_game_code_called":False,
            "process_memory_written":False,
            "active_save_opened":False,
            "save_or_progression_written":False,
            "game_files_written":False,
        }
    }

    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")

    L=[
        "Completionist Map - LuaContext unloaded-resource backing cache read-only capture",
        f"result={result['result']}",
        f"pid={pid} module_base=0x{base:X} expected_vtable=0x{base+LUA_CONTEXT_VTABLE_RVA:X}",
        f"regions_scanned={scan_stats['regions_scanned']} bytes_scanned={scan_stats['bytes_scanned']} raw_hits={len(raw_candidates)}",
        f"valid_contexts={len(valid)} nonempty_contexts={len(nonempty)}",
        ""
    ]
    for ci,ctx in enumerate(valid):
        L.append(f"CONTEXT {ci} ptr={ctx['lua_context_ptr']} head={ctx['cache_head']} nodes={ctx['node_count']} empty={ctx['empty']}")
        for n in ctx["nodes"]:
            L.append(
                f"  NODE {n['index']} ptr={n['node_ptr']} key={n['resource_key_hex']} "
                f"size_u32={n['backing_size_u32']} size_i32={n['backing_size_i32']} "
                f"owner={n['owner_ptr']} storage={n['storage_ptr']}"
            )
        L.append("")
    if rejected:
        L.append("REJECTED CANDIDATES")
        for x in rejected:
            L.append(f"  {x['candidate']} reason={x['reason']}")
        L.append("")
    L += [
        "SAFETY",
        "OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
        "process_memory_written=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
    ]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")

    print(
        f"LUA_CONTEXT_BACKING_CACHE_READONLY_CAPTURE_COMPLETE "
        f"valid={len(valid)} nonempty={len(nonempty)} raw={len(raw_candidates)}"
    )
    print("process_memory_written=false active_save_opened=false save_or_progression_written=false")
    return 0 if valid else 2

if __name__=="__main__":
    raise SystemExit(main())
