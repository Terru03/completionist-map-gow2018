#!/usr/bin/env python3
"""Search already-enumerated LuaContext backing arenas for Raven persistence signatures.

Read-only runtime diagnostic. Requires the same running GoW process/session as the
source LuaContext cache capture. Uses only ReadProcessMemory/Toolhelp snapshots.

Important: scans arena capacity, not proven live-allocation extents. Hits are evidence
of physical presence only and MUST NOT yet be treated as authoritative/current state.
"""
from __future__ import annotations
import argparse, ctypes as C, hashlib, json, struct, sys
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
SCAN_CHUNK=1024*1024
MAX_ARENA=8*1024*1024
RAVEN_PREFIX=bytes.fromhex("01b0b227342530c24e")
TEXT_PATTERNS={
    "ravenKilled":b"ravenKilled",
    "__subobjs":b"__subobjs",
    "__PickleTable":b"__PickleTable",
    "__SoftPickleTable":b"__SoftPickleTable",
    "_SUBOBJECT_CHUNKS":b"_SUBOBJECT_CHUNKS",
}

class PROCESSENTRY32W(C.Structure):
    _fields_=[("dwSize",W.DWORD),("cntUsage",W.DWORD),("th32ProcessID",W.DWORD),
      ("th32DefaultHeapID",C.c_size_t),("th32ModuleID",W.DWORD),("cntThreads",W.DWORD),
      ("th32ParentProcessID",W.DWORD),("pcPriClassBase",W.LONG),("dwFlags",W.DWORD),
      ("szExeFile",W.WCHAR*MAX_PATH)]
class MODULEENTRY32W(C.Structure):
    _fields_=[("dwSize",W.DWORD),("th32ModuleID",W.DWORD),("th32ProcessID",W.DWORD),
      ("GlblcntUsage",W.DWORD),("ProccntUsage",W.DWORD),("modBaseAddr",C.POINTER(C.c_ubyte)),
      ("modBaseSize",W.DWORD),("hModule",W.HMODULE),("szModule",W.WCHAR*256),
      ("szExePath",W.WCHAR*MAX_PATH)]

def k32_api():
    k=C.WinDLL("kernel32",use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Process32FirstW.argtypes=[W.HANDLE,C.POINTER(PROCESSENTRY32W)];k.Process32FirstW.restype=W.BOOL
    k.Process32NextW.argtypes=[W.HANDLE,C.POINTER(PROCESSENTRY32W)];k.Process32NextW.restype=W.BOOL
    k.Module32FirstW.argtypes=[W.HANDLE,C.POINTER(MODULEENTRY32W)];k.Module32FirstW.restype=W.BOOL
    k.Module32NextW.argtypes=[W.HANDLE,C.POINTER(MODULEENTRY32W)];k.Module32NextW.restype=W.BOOL
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.ReadProcessMemory.argtypes=[W.HANDLE,W.LPCVOID,W.LPVOID,C.c_size_t,C.POINTER(C.c_size_t)]
    k.ReadProcessMemory.restype=W.BOOL
    k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle.restype=W.BOOL
    return k
def close(k,h):
    if h and int(C.cast(h,C.c_void_p).value or 0) not in (0,INVALID_HANDLE_VALUE):k.CloseHandle(h)
def winerr(prefix):
    e=C.get_last_error();return RuntimeError(f"{prefix}: WinError {e}: {C.FormatError(e).strip()}")
def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def find_process(k):
    s=k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0)
    if C.cast(s,C.c_void_p).value==INVALID_HANDLE_VALUE:raise winerr("process snapshot failed")
    found=[]
    try:
        pe=PROCESSENTRY32W();pe.dwSize=C.sizeof(pe);ok=k.Process32FirstW(s,C.byref(pe))
        while ok:
            n=str(pe.szExeFile)
            if n.lower() in {"gow.exe","godofwar.exe"}:found.append((int(pe.th32ProcessID),n))
            ok=k.Process32NextW(s,C.byref(pe))
    finally:close(k,s)
    if len(found)!=1:raise RuntimeError(f"expected one running GoW process, found {found}")
    return found[0]
def main_module(k,pid,name):
    s=k.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid)
    if C.cast(s,C.c_void_p).value==INVALID_HANDLE_VALUE:raise winerr("module snapshot failed")
    try:
        me=MODULEENTRY32W();me.dwSize=C.sizeof(me);ok=k.Module32FirstW(s,C.byref(me))
        while ok:
            if str(me.szModule).lower()==name.lower():
                base=C.cast(me.modBaseAddr,C.c_void_p).value
                return int(base),str(me.szExePath)
            ok=k.Module32NextW(s,C.byref(me))
    finally:close(k,s)
    raise RuntimeError("GoW module not found")
def read(k,p,a,n):
    buf=(C.c_ubyte*n)();done=C.c_size_t()
    if not k.ReadProcessMemory(p,C.c_void_p(a),buf,n,C.byref(done)):raise winerr(f"RPM 0x{a:X}")
    if done.value!=n:raise RuntimeError(f"short read 0x{a:X}: {done.value}/{n}")
    return bytes(buf)
def safe_read(k,p,a,n):
    try:return read(k,p,a,n)
    except Exception:return None
def q64(b,o):return struct.unpack_from("<Q",b,o)[0]

def preview(k,p,address,radius=32):
    start=max(0x10000,address-radius)
    raw=safe_read(k,p,start,radius*2+17)
    return {"start":f"0x{start:X}","hex":raw.hex() if raw else None}

def scan_arena(k,p,start,size,identity_by_payload):
    maxpat=max([17,len(RAVEN_PREFIX),*(len(x) for x in TEXT_PATTERNS.values())])
    overlap=maxpat-1
    pos=0;tail=b"";hits=[];seen=set()
    while pos<size:
        want=min(SCAN_CHUNK,size-pos)
        raw=safe_read(k,p,start+pos,want)
        if raw is None:
            pos+=want;tail=b"";continue
        buf=tail+raw;base=start+pos-len(tail)
        # Raven custom-userdata prefix; read full 17-byte payload.
        off=buf.find(RAVEN_PREFIX)
        while off>=0:
            absolute=base+off
            if off+17<=len(buf):
                payload=buf[off:off+17].hex()
                key=("raven_payload",absolute)
                if key not in seen:
                    seen.add(key)
                    ident=identity_by_payload.get(payload)
                    hits.append({
                      "kind":"raven_serialized_payload","address":f"0x{absolute:X}",
                      "offset":absolute-start,"payload_hex":payload,
                      "matched":ident is not None,
                      "catalogue_id":ident.get("catalogue_id") if ident else None,
                      "wad":ident.get("wad") if ident else None,
                      "realm":ident.get("realm") if ident else None,
                      "region":ident.get("region") if ident else None,
                      "preview":preview(k,p,absolute),
                    })
            off=buf.find(RAVEN_PREFIX,off+1)
        for name,pat in TEXT_PATTERNS.items():
            off=buf.find(pat)
            while off>=0:
                absolute=base+off;key=(name,absolute)
                if key not in seen:
                    seen.add(key)
                    hits.append({"kind":"text","name":name,"address":f"0x{absolute:X}",
                                 "offset":absolute-start,"preview":preview(k,p,absolute)})
                off=buf.find(pat,off+1)
        tail=buf[-overlap:] if len(buf)>=overlap else buf
        pos+=want
    hits.sort(key=lambda x:x["offset"])
    return hits

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-report",type=Path,required=True)
    ap.add_argument("--identities",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    if sys.platform!="win32" or C.sizeof(C.c_void_p)!=8:raise RuntimeError("64-bit Windows required")

    src=json.loads(a.source_report.read_text(encoding="utf-8"))
    ids=json.loads(a.identities.read_text(encoding="utf-8"))
    identity_by_payload={x["serialized_payload_hex"].lower():x for x in ids["identities"]}

    k=k32_api();pid,name=find_process(k);base,exe=main_module(k,pid,name)
    sha=sha256_file(exe).lower()
    if sha!=EXE_SHA:raise RuntimeError(f"unsupported GoW.exe SHA256 {sha}")
    expected_pid=int(src["process"]["pid"])
    expected_base=int(src["process"]["module_base"],16)
    if pid!=expected_pid or base!=expected_base:
        raise RuntimeError(
          f"source capture belongs to pid/base {expected_pid}/0x{expected_base:X}; "
          f"current is {pid}/0x{base:X}. Keep the same game session or rerun the cache capture first."
        )

    contexts=[x for x in src["valid_contexts"] if int(x.get("node_count",0))>0]
    p=k.OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION,False,pid)
    if not p:raise winerr("OpenProcess read-only failed")
    outctx=[];total_bytes=0
    try:
        for ci,ctx in enumerate(contexts):
            cptr=int(ctx["lua_context_ptr"],16)
            nodes=[]
            for n in ctx["nodes"]:
                nptr=int(n["node_ptr"],16);sptr=int(n["storage_ptr"],16)
                current=safe_read(k,p,nptr,0x30)
                if current is None:continue
                if f"0x{q64(current,0x28):X}".lower()!=n["storage_ptr"].lower():
                    continue
                st=safe_read(k,p,sptr,0x40)
                if st is None:continue
                usable=q64(st,0x10);arena=q64(st,0x28)
                if usable<=0 or usable>MAX_ARENA or arena<0x10000:
                    nodes.append({"node_ptr":n["node_ptr"],"error":"implausible_arena",
                                  "usable":usable,"arena":f"0x{arena:X}"})
                    continue
                total_bytes+=usable
                hits=scan_arena(k,p,arena,usable,identity_by_payload)
                nodes.append({
                  "node_ptr":n["node_ptr"],"profile_key":n["resource_key_hex"],
                  "backing_size":n["backing_size_u32"],"storage_ptr":n["storage_ptr"],
                  "usable_bytes":usable,"arena_start":f"0x{arena:X}",
                  "hit_count":len(hits),
                  "matched_raven_count":sum(1 for h in hits if h["kind"]=="raven_serialized_payload" and h["matched"]),
                  "unknown_raven_prefix_count":sum(1 for h in hits if h["kind"]=="raven_serialized_payload" and not h["matched"]),
                  "text_hit_count":sum(1 for h in hits if h["kind"]=="text"),
                  "hits":hits,
                })
            outctx.append({"source_context_ptr":ctx["lua_context_ptr"],"source_node_count":ctx["node_count"],
                           "nodes":nodes,
                           "hit_count":sum(int(x.get("hit_count",0)) for x in nodes)})
    finally:close(k,p)

    matched=[]
    for c in outctx:
        for n in c["nodes"]:
            for h in n.get("hits",[]):
                if h.get("kind")=="raven_serialized_payload" and h.get("matched"):
                    matched.append(h["catalogue_id"])
    report={
      "schema":1,"captured_utc":datetime.now(timezone.utc).isoformat(),
      "result":"LUA_BACKING_ARENA_RAVEN_SIGNATURE_SCAN_COMPLETE",
      "source_report":str(a.source_report),"process":{"pid":pid,"module_base":f"0x{base:X}","exe_sha256":sha},
      "contexts_scanned":len(outctx),"arena_bytes_scanned":total_bytes,
      "matched_raven_hit_count":len(matched),"unique_matched_ravens":sorted(set(matched)),
      "unique_matched_raven_count":len(set(matched)),
      "contexts":outctx,
      "interpretation_warning":"Arena capacity may include stale/free bytes; signature hits prove physical presence only, not current authority.",
      "safety":{"open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                "debugger_attached":False,"remote_game_code_called":False,
                "process_memory_written":False,"active_save_opened":False,
                "save_or_progression_written":False,"game_files_written":False}
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")

    L=["Completionist Map - Lua backing arena Raven signature scan",
       f"result={report['result']}",f"contexts={len(outctx)} bytes_scanned={total_bytes}",
       f"matched_raven_hits={len(matched)} unique_matched_ravens={len(set(matched))}",
       "WARNING: scans arena capacity; hits are physical-presence evidence, not yet authoritative/current state.",""]
    for ci,c in enumerate(outctx):
        L.append(f"CONTEXT {ci} ptr={c['source_context_ptr']} nodes={c['source_node_count']} hits={c['hit_count']}")
        for ni,n in enumerate(c["nodes"]):
            L.append(f"  NODE {ni} ptr={n['node_ptr']} arena={n.get('arena_start')} usable={n.get('usable_bytes')} hits={n.get('hit_count',0)} matched_ravens={n.get('matched_raven_count',0)} text={n.get('text_hit_count',0)}")
            for h in n.get("hits",[]):
                if h["kind"]=="raven_serialized_payload":
                    L.append(f"    RAVEN off=0x{h['offset']:X} addr={h['address']} matched={h['matched']} id={h.get('catalogue_id')} wad={h.get('wad')}")
                else:
                    L.append(f"    TEXT off=0x{h['offset']:X} addr={h['address']} name={h['name']}")
        L.append("")
    L += ["SAFETY","OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
          "process_memory_written=false","active_save_opened=false","save_or_progression_written=false"]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"LUA_BACKING_ARENA_RAVEN_SIGNATURE_SCAN_COMPLETE contexts={len(outctx)} unique_ravens={len(set(matched))} bytes={total_bytes}")
    print("process_memory_written=false active_save_opened=false save_or_progression_written=false")
    return 0

if __name__=="__main__":raise SystemExit(main())
