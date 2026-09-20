#!/usr/bin/env python3
"""Capture the staged WAD checkpoint records and decode exact Raven state read-only.

This observer is deliberately narrow. It reads only the checkpoint/WAD staging
metadata proven by the static 0x668683 trace and the payload extents referenced
by those records. It does not scan arbitrary process memory and never writes to
the game, save files, or progression state.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import struct
import sys
from collections import defaultdict
from ctypes import wintypes as W
from datetime import datetime, timezone
from pathlib import Path

EXE_SHA="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
PROCESS_VM_READ=0x0010
PROCESS_QUERY_INFORMATION=0x0400
TH32CS_SNAPPROCESS=2
TH32CS_SNAPMODULE=8
TH32CS_SNAPMODULE32=16
INVALID_HANDLE_VALUE=C.c_void_p(-1).value
MAX_PATH=260

# Proven by static trace around 0x668683..0x66878B.
PAYLOAD_SIZE_RVA=0x22C6938
PAYLOAD_BASE_RVA=0x22C6940
RECORD_COUNT_RVA=0x22C696C
RECORD_BASE_RVA=0x22C7170
RECORD_STRIDE=0xA8
RECORD_KEY_OFF=0x24
RECORD_PAYLOAD_A_OFF=0x48
RECORD_PAYLOAD_B_OFF=0x50
RECORD_PAYLOAD_SIZE_OFF=0x58
RECORD_NAME_OFF=0x84
RECORD_NAME_SIZE=0x24
MAX_RECORDS=4096
MAX_POOL_SIZE=0x140000
MAX_RECORD_PAYLOAD=0x140000

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
DEFAULT_IDENTITIES=REPO/"catalogue"/"odins-ravens-save-identities.json"
DECODER=HERE/"decode-active-raven-subobject-state.py"

class PROCESSENTRY32W(C.Structure):
    _fields_=[
        ("dwSize",W.DWORD),("cntUsage",W.DWORD),("th32ProcessID",W.DWORD),
        ("th32DefaultHeapID",C.c_size_t),("th32ModuleID",W.DWORD),
        ("cntThreads",W.DWORD),("th32ParentProcessID",W.DWORD),
        ("pcPriClassBase",W.LONG),("dwFlags",W.DWORD),
        ("szExeFile",W.WCHAR*MAX_PATH),
    ]

class MODULEENTRY32W(C.Structure):
    _fields_=[
        ("dwSize",W.DWORD),("th32ModuleID",W.DWORD),("th32ProcessID",W.DWORD),
        ("GlblcntUsage",W.DWORD),("ProccntUsage",W.DWORD),
        ("modBaseAddr",C.POINTER(C.c_ubyte)),("modBaseSize",W.DWORD),
        ("hModule",W.HMODULE),("szModule",W.WCHAR*256),
        ("szExePath",W.WCHAR*MAX_PATH),
    ]

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def load_decoder():
    spec=importlib.util.spec_from_file_location("staged_raven_decoder",DECODER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load decoder: {DECODER}")
    m=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=m
    spec.loader.exec_module(m)
    return m

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
    k.CloseHandle.argtypes=[W.HANDLE]
    k.CloseHandle.restype=W.BOOL
    return k

def close(k,h):
    if h and int(C.cast(h,C.c_void_p).value or 0) not in (0,INVALID_HANDLE_VALUE):
        k.CloseHandle(h)

def winerr(prefix):
    e=C.get_last_error()
    return RuntimeError(f"{prefix}: WinError {e}: {C.FormatError(e).strip()}")

def find_process(k):
    s=k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0)
    if C.cast(s,C.c_void_p).value==INVALID_HANDLE_VALUE:
        raise winerr("process snapshot failed")
    found=[]
    try:
        pe=PROCESSENTRY32W();pe.dwSize=C.sizeof(pe)
        ok=k.Process32FirstW(s,C.byref(pe))
        while ok:
            n=str(pe.szExeFile)
            if n.lower() in {"gow.exe","godofwar.exe"}:
                found.append((int(pe.th32ProcessID),n))
            ok=k.Process32NextW(s,C.byref(pe))
    finally:
        close(k,s)
    if len(found)!=1:
        raise RuntimeError(f"expected exactly one running God of War process, found {found}")
    return found[0]

def main_module(k,pid,name):
    s=k.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid)
    if C.cast(s,C.c_void_p).value==INVALID_HANDLE_VALUE:
        raise winerr("module snapshot failed")
    try:
        me=MODULEENTRY32W();me.dwSize=C.sizeof(me)
        ok=k.Module32FirstW(s,C.byref(me))
        while ok:
            if str(me.szModule).lower()==name.lower():
                base=C.cast(me.modBaseAddr,C.c_void_p).value
                if not base:
                    raise RuntimeError("NULL module base")
                return int(base),str(me.szExePath)
            ok=k.Module32NextW(s,C.byref(me))
    finally:
        close(k,s)
    raise RuntimeError("GoW main module not found")

def read(k,p,address,size):
    if size<0:
        raise RuntimeError("negative read")
    if size==0:
        return b""
    buf=(C.c_ubyte*size)();done=C.c_size_t()
    if not k.ReadProcessMemory(p,C.c_void_p(address),buf,size,C.byref(done)):
        raise winerr(f"ReadProcessMemory(0x{address:X},{size}) failed")
    if done.value!=size:
        raise RuntimeError(f"short read 0x{address:X}: {done.value}/{size}")
    return bytes(buf)

def safe_read(k,p,address,size):
    try:
        return read(k,p,address,size)
    except Exception:
        return None

def u32(raw,off=0): return struct.unpack_from("<I",raw,off)[0]
def u64(raw,off=0): return struct.unpack_from("<Q",raw,off)[0]

def printable_name(raw:bytes):
    raw=raw.split(b"\0",1)[0]
    if not raw:
        return None
    if not all(32<=b<127 for b in raw):
        return None
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None

def identity_hits(payload:bytes, payload_map):
    hits=[]
    for needle,row in payload_map:
        start=0
        while True:
            at=payload.find(needle,start)
            if at<0:
                break
            hits.append({
                "offset":at,
                "catalogue_id":row["catalogue_id"],
                "wad":row.get("wad"),
                "realm":row.get("realm"),
                "region":row.get("region"),
                "serialized_payload_hex":row["serialized_payload_hex"],
            })
            start=at+1
    hits.sort(key=lambda x:(x["offset"],x["catalogue_id"]))
    return hits

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--identities",type=Path,default=DEFAULT_IDENTITIES)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    if sys.platform!="win32" or C.sizeof(C.c_void_p)!=8:
        raise RuntimeError("64-bit Windows required")

    ids=json.loads(a.identities.read_text(encoding="utf-8"))
    rows=ids.get("identities")
    if not isinstance(rows,list) or len(rows)!=53:
        raise RuntimeError(f"expected 53 Raven identities, found {0 if not isinstance(rows,list) else len(rows)}")
    object_map={int(x["object_hash_hex"],16):x["catalogue_id"] for x in rows}
    if len(object_map)!=53:
        raise RuntimeError("Raven object hashes are not unique")
    registry_hash=int(rows[0]["registry_hash_hex"],16)
    if any(int(x["registry_hash_hex"],16)!=registry_hash for x in rows):
        raise RuntimeError("Raven registry hashes disagree")
    payload_map=[(bytes.fromhex(x["serialized_payload_hex"]),x) for x in rows]
    meta={x["catalogue_id"]:x for x in rows}
    decoder=load_decoder()

    k=k32_api()
    pid,name=find_process(k)
    base,exe_path=main_module(k,pid,name)
    exe_sha=sha256_file(Path(exe_path)).lower()
    if exe_sha!=EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    p=k.OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION,False,pid)
    if not p:
        raise winerr("OpenProcess read-only failed")

    records=[]
    union_true=set()
    union_false=set()
    raw_identity_ids=set()
    conflicts=set()
    total_payload_bytes=0
    state_by_id=defaultdict(set)
    try:
        pool_size=u32(read(k,p,base+PAYLOAD_SIZE_RVA,4))
        pool_base=u64(read(k,p,base+PAYLOAD_BASE_RVA,8))
        count=u32(read(k,p,base+RECORD_COUNT_RVA,4))

        if count>MAX_RECORDS:
            raise RuntimeError(f"implausible staged record count: {count}")
        if pool_size>MAX_POOL_SIZE:
            raise RuntimeError(f"implausible staged payload pool size: 0x{pool_size:X}")
        if pool_size and pool_base<0x10000:
            raise RuntimeError(f"implausible staged payload pool base: 0x{pool_base:X}")

        for i in range(count):
            addr=base+RECORD_BASE_RVA+i*RECORD_STRIDE
            raw=read(k,p,addr,RECORD_STRIDE)
            key=u32(raw,RECORD_KEY_OFF)
            pa=u64(raw,RECORD_PAYLOAD_A_OFF)
            pb=u64(raw,RECORD_PAYLOAD_B_OFF)
            size=u32(raw,RECORD_PAYLOAD_SIZE_OFF)
            name_text=printable_name(raw[RECORD_NAME_OFF:RECORD_NAME_OFF+RECORD_NAME_SIZE])

            row={
                "index":i,
                "address":f"0x{addr:X}",
                "key_u32":key,
                "key_hex":f"0x{key:08X}",
                "name":name_text,
                "payload_a":f"0x{pa:X}",
                "payload_b":f"0x{pb:X}",
                "payload_size":size,
                "payload_in_pool":False,
                "payload_sha256":None,
                "ravenKilled_text_hits":[],
                "exact_raven_identity_hits":[],
                "decoded":None,
            }

            if size==0:
                records.append(row)
                continue
            if size>MAX_RECORD_PAYLOAD:
                row["payload_rejected"]=f"size_above_cap_0x{size:X}"
                records.append(row)
                continue

            pool_end=pool_base+pool_size
            in_pool=(pool_size>0 and pa>=pool_base and pa+size>=pa and pa+size<=pool_end)
            row["payload_in_pool"]=in_pool
            if not in_pool:
                row["payload_rejected"]="outside_proven_pool_extent"
                records.append(row)
                continue

            payload=read(k,p,pa,size)
            total_payload_bytes+=len(payload)
            row["payload_sha256"]=hashlib.sha256(payload).hexdigest()
            pos=0
            while True:
                at=payload.find(b"ravenKilled",pos)
                if at<0: break
                row["ravenKilled_text_hits"].append(at);pos=at+1

            hits=identity_hits(payload,payload_map)
            row["exact_raven_identity_hits"]=hits
            raw_identity_ids.update(h["catalogue_id"] for h in hits)

            decoded=decoder.decode_carriers(payload,registry_hash,object_map)
            compact={
                "stream_count":decoded["stream_count"],
                "carrier_header_candidates":decoded["carrier_header_candidates"],
                "decoded_carrier_count":decoded["decoded_carrier_count"],
                "carriers_with_subobjs":decoded["carriers_with_subobjs"],
                "raven_entry_count":decoded["raven_entry_count"],
                "killed_raven_count":decoded["killed_raven_count"],
                "killed_raven_catalogue_ids":decoded["killed_raven_catalogue_ids"],
                "explicit_false_raven_catalogue_ids":decoded["explicit_false_raven_catalogue_ids"],
                "raven_entries":decoded["raven_entries"],
            }
            row["decoded"]=compact
            union_true.update(compact["killed_raven_catalogue_ids"])
            union_false.update(compact["explicit_false_raven_catalogue_ids"])
            for e in compact["raven_entries"]:
                st=e.get("ravenKilled")
                if st is not None:
                    state_by_id[e["catalogue_id"]].add(bool(st))
            records.append(row)
    finally:
        close(k,p)

    for rid,states in state_by_id.items():
        if len(states)>1:
            conflicts.add(rid)

    exact_states=[]
    for rid in sorted(state_by_id):
        m=meta[rid]
        states=state_by_id[rid]
        exact_states.append({
            "catalogue_id":rid,
            "ravenKilled":next(iter(states)) if len(states)==1 else None,
            "conflict":len(states)>1,
            "wad":m.get("wad"),
            "realm":m.get("realm"),
            "region":m.get("region"),
        })

    region_summary=defaultdict(lambda:{"true":[],"false":[],"conflict":[]})
    for e in exact_states:
        region=e.get("region") or "<unknown>"
        if e["conflict"]:
            region_summary[region]["conflict"].append(e["catalogue_id"])
        elif e["ravenKilled"] is True:
            region_summary[region]["true"].append(e["catalogue_id"])
        elif e["ravenKilled"] is False:
            region_summary[region]["false"].append(e["catalogue_id"])

    report={
        "schema":1,
        "captured_utc":datetime.now(timezone.utc).isoformat(),
        "analysis":"staged_wad_raven_state_readonly",
        "process":{"pid":pid,"module_base":f"0x{base:X}","exe_path":exe_path,"exe_sha256":exe_sha},
        "layout":{
            "record_count_rva":f"0x{RECORD_COUNT_RVA:X}",
            "record_base_rva":f"0x{RECORD_BASE_RVA:X}",
            "record_stride":RECORD_STRIDE,
            "key_offset":f"0x{RECORD_KEY_OFF:X}",
            "payload_a_offset":f"0x{RECORD_PAYLOAD_A_OFF:X}",
            "payload_b_offset":f"0x{RECORD_PAYLOAD_B_OFF:X}",
            "payload_size_offset":f"0x{RECORD_PAYLOAD_SIZE_OFF:X}",
            "name_offset":f"0x{RECORD_NAME_OFF:X}",
            "pool_base_rva":f"0x{PAYLOAD_BASE_RVA:X}",
            "pool_size_rva":f"0x{PAYLOAD_SIZE_RVA:X}",
        },
        "staging":{"record_count":len(records),"pool_base":f"0x{pool_base:X}","pool_size":pool_size,
                   "payload_bytes_read":total_payload_bytes},
        "records":records,
        "records_with_payload":sum(1 for x in records if x["payload_size"]>0 and x["payload_in_pool"]),
        "records_with_ravenKilled_text":sum(1 for x in records if x["ravenKilled_text_hits"]),
        "records_with_exact_raven_identity":sum(1 for x in records if x["exact_raven_identity_hits"]),
        "records_with_decoded_raven_entries":sum(1 for x in records if x.get("decoded") and x["decoded"]["raven_entry_count"]>0),
        "raw_exact_identity_catalogue_ids":sorted(raw_identity_ids),
        "raw_exact_identity_count":len(raw_identity_ids),
        "decoded_exact_states":exact_states,
        "decoded_exact_state_count":len(exact_states),
        "decoded_killed_catalogue_ids":sorted(union_true),
        "decoded_explicit_false_catalogue_ids":sorted(union_false),
        "conflicting_catalogue_ids":sorted(conflicts),
        "region_state_summary":dict(sorted(region_summary.items())),
        "safety":{
            "open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "process_memory_written":False,
            "debugger_attached":False,
            "remote_game_code_called":False,
            "active_save_opened":False,
            "save_written":False,
            "progression_written":False,
            "game_files_written":False,
        },
    }

    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=[
        "Completionist Map - staged WAD Raven state capture",
        f"pid={pid} module_base=0x{base:X}",
        f"record_count={len(records)} pool_base=0x{pool_base:X} pool_size={pool_size}",
        f"payload_bytes_read={total_payload_bytes}",
        f"records_with_payload={report['records_with_payload']}",
        f"records_with_ravenKilled_text={report['records_with_ravenKilled_text']}",
        f"records_with_exact_raven_identity={report['records_with_exact_raven_identity']}",
        f"records_with_decoded_raven_entries={report['records_with_decoded_raven_entries']}",
        f"raw_exact_identity_count={report['raw_exact_identity_count']}",
        f"decoded_exact_state_count={report['decoded_exact_state_count']}",
        f"decoded_killed_count={len(union_true)}",
        f"decoded_explicit_false_count={len(union_false)}",
        f"conflict_count={len(conflicts)}",
        "",
        "RECORDS",
    ]
    for x in records:
        d=x.get("decoded")
        L.append(
            f"  idx={x['index']} key={x['key_hex']} name={x['name']!r} size={x['payload_size']} "
            f"in_pool={str(x['payload_in_pool']).lower()} identities={len(x['exact_raven_identity_hits'])} "
            f"ravenKilledText={len(x['ravenKilled_text_hits'])} "
            f"decodedEntries={(d['raven_entry_count'] if d else 0)}"
        )
        if d and d["raven_entry_count"]:
            for e in d["raven_entries"]:
                m=meta.get(e["catalogue_id"],{})
                L.append(
                    f"    RAVEN id={e['catalogue_id']} state={e.get('ravenKilled')} "
                    f"realm={m.get('realm')} region={m.get('region')} wad={m.get('wad')}"
                )
    L += ["","EXACT DECODED STATES"]
    for e in exact_states:
        L.append(
            f"  id={e['catalogue_id']} ravenKilled={e['ravenKilled']} conflict={str(e['conflict']).lower()} "
            f"realm={e['realm']} region={e['region']} wad={e['wad']}"
        )
    L += [
        "",
        "SAFETY OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION "
        "process_memory_written=false active_save_opened=false save_written=false "
        "progression_written=false remote_game_code_called=false",
    ]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")

    print(
        "STAGED_WAD_RAVEN_STATE_CAPTURE_COMPLETE "
        f"records={len(records)} decoded_states={len(exact_states)} "
        f"killed={len(union_true)} false={len(union_false)} conflicts={len(conflicts)}"
    )
    print("process_memory_written=false active_save_opened=false save_written=false progression_written=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
