#!/usr/bin/env python3
"""Resolve catalogue Raven -> GameObject identity with read-only process memory."""
from __future__ import annotations
import argparse, ctypes as C, hashlib, json, struct, sys
from ctypes import wintypes as W
from datetime import datetime, timezone
from pathlib import Path

EXE_SHA="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
REGISTRY_ID=238
TABLE_BEGIN=0x22A98C0
TABLE_END=0x22A9AC0
IDENTITY_METHOD_RVA=0x550700
KNOWN_ID="raven_642d0d164af0a5d4076e77933c549a5d"
KNOWN_TOKEN=0x1BB001DD
KNOWN_HASH=0x98BE1707BA2D65A9
PROCESS_VM_READ=0x0010
PROCESS_QUERY_INFORMATION=0x0400
TH32CS_SNAPPROCESS=2
TH32CS_SNAPMODULE=8
TH32CS_SNAPMODULE32=16
INVALID_HANDLE_VALUE=C.c_void_p(-1).value
MAX_PATH=260
MAX_VECTOR_COUNT=256
MAX_PARENT_DEPTH=64
MASK64=0xFFFFFFFFFFFFFFFF

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
    if h and int(C.cast(h,C.c_void_p).value or 0) not in (0,INVALID_HANDLE_VALUE): k.CloseHandle(h)

def winerr(prefix):
    code=C.get_last_error()
    return RuntimeError(f"{prefix}: WinError {code}: {C.FormatError(code).strip()}")

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def find_process(k):
    snap=k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0)
    if C.cast(snap,C.c_void_p).value==INVALID_HANDLE_VALUE: raise winerr("process snapshot failed")
    found=[]
    try:
        pe=PROCESSENTRY32W();pe.dwSize=C.sizeof(pe)
        ok=k.Process32FirstW(snap,C.byref(pe))
        while ok:
            name=str(pe.szExeFile)
            if name.lower() in {"gow.exe","godofwar.exe"}: found.append((int(pe.th32ProcessID),name))
            ok=k.Process32NextW(snap,C.byref(pe))
    finally: close(k,snap)
    if len(found)!=1: raise RuntimeError(f"expected one running God of War process, found {found}")
    return found[0]

def main_module(k,pid,name):
    snap=k.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid)
    if C.cast(snap,C.c_void_p).value==INVALID_HANDLE_VALUE: raise winerr("module snapshot failed")
    try:
        me=MODULEENTRY32W();me.dwSize=C.sizeof(me)
        ok=k.Module32FirstW(snap,C.byref(me))
        while ok:
            if str(me.szModule).lower()==name.lower():
                base=C.cast(me.modBaseAddr,C.c_void_p).value
                if not base: raise RuntimeError("NULL module base")
                return int(base),int(me.modBaseSize),str(me.szExePath)
            ok=k.Module32NextW(snap,C.byref(me))
    finally: close(k,snap)
    raise RuntimeError("main GoW module not found")

def read(k,p,address,size):
    if size<=0:return b""
    buf=(C.c_ubyte*size)();done=C.c_size_t()
    if not k.ReadProcessMemory(p,C.c_void_p(address),buf,size,C.byref(done)):
        raise winerr(f"ReadProcessMemory(0x{address:X},{size}) failed")
    if done.value!=size: raise RuntimeError(f"short read 0x{address:X}: {done.value}/{size}")
    return bytes(buf)

def safe_read(k,p,address,size):
    try:return read(k,p,address,size)
    except Exception:return None

class Reader:
    def __init__(self,k,p):self.k=k;self.p=p;self.read_count=0
    def read(self,a,n):self.read_count+=1;return read(self.k,self.p,a,n)
    def u8(self,a):return self.read(a,1)[0]
    def u32(self,a):return struct.unpack("<I",self.read(a,4))[0]
    def u64(self,a):return struct.unpack("<Q",self.read(a,8))[0]

def read_vector(r,ptr,source):
    if not ptr:return [],{"source":source,"ptr":None,"count":0}
    count=r.u32(ptr)
    if count>MAX_VECTOR_COUNT:raise RuntimeError(f"{source}: vector count {count}")
    raw=r.read(ptr+4,count*16) if count else b""
    els=[raw[i:i+16] for i in range(0,len(raw),16)]
    return els,{"source":source,"ptr":f"0x{ptr:X}","count":count,"elements_hex":[x.hex() for x in els]}

def append_identity(r,obj,events,depth=0,seen=None):
    if seen is None:seen=set()
    if depth>MAX_PARENT_DEPTH:raise RuntimeError("identity recursion cap")
    if obj in seen:raise RuntimeError("identity recursion cycle")
    seen.add(obj)
    try:
        external=r.u64(obj+0x240)
        if external:
            els,e=read_vector(r,external,f"object+0x240 depth={depth}")
            events.append({"kind":"external_vector","object_ptr":f"0x{obj:X}","depth":depth,**e})
            return els
        flags=r.u8(obj+0x278)
        if flags&0x80:return []
        out=[]
        parent=r.u64(obj+0x28)
        if parent:out.extend(append_identity(r,parent,events,depth+1,seen))
        meta=r.u64(obj+0x30)
        if meta and r.u8(meta+2)==2:
            b0=r.u64(meta+0xB0)
            vec=r.u64(b0+0x10) if b0 else 0
            if vec:
                els,e=read_vector(r,vec,f"metadata depth={depth}")
                events.append({"kind":"metadata_vector","object_ptr":f"0x{obj:X}","depth":depth,**e})
                out.extend(els)
        return out
    finally:seen.remove(obj)

def build_identity(r,obj):
    meta=r.u64(obj+0x30)
    if not meta:raise RuntimeError("NULL metadata")
    typ=r.u8(meta+2);flags=r.u32(meta+0x68)
    special=typ==1 and ((flags>>19)&1)!=0
    events=[];els=append_identity(r,obj,events)
    own=None
    if not special:
        own=r.read(obj+0x40,16);els.append(own)
    return els,{
        "metadata_ptr":f"0x{meta:X}","metadata_type_byte":typ,
        "metadata_flags_68_hex":f"0x{flags:08X}","special_flag_bit19":bool((flags>>19)&1),
        "object_plus_40_hex":own.hex() if own is not None else None,"events":events,
    }

def identity_hash(elements):
    v=0
    for e in elements:
        if len(e)!=16:raise RuntimeError("identity element length changed")
        for b in e:
            v=((v+b)*0x401)&MASK64
            v^=v>>6
    return v

def token_for_slot(slot):return 1|(REGISTRY_ID<<1)|(slot<<18)

def validate_catalogue(game_root,catalogue):
    rows=catalogue.get("ravens",[])
    if len(rows)!=53:raise RuntimeError(f"expected 53 Ravens, found {len(rows)}")
    tags={};checks=[];files={}
    try:
        for row in rows:
            cid=row["catalogue_id"];tag=bytes.fromhex(row["native"]["final_record_id"])
            if len(tag)!=16:raise RuntimeError(f"{cid}: invalid final_record_id")
            if tag in tags:raise RuntimeError(f"{cid}: duplicate final_record_id")
            wad=game_root/"exec"/"wad"/"pc_le"/row["source"]["wad"]
            fh=files.get(wad)
            if fh is None:
                fh=wad.open("rb");files[wad]=fh
            oo=int(row["source"]["override_offset"],0);fo=int(row["source"]["final_offset"],0)
            fh.seek(oo+0xAC);at_override=fh.read(16)
            fh.seek(fo+8);at_final=fh.read(16)
            ok1=at_override==tag;ok2=at_final==tag
            checks.append({"catalogue_id":cid,"wad":wad.name,"final_record_id_hex":tag.hex(),
                           "override_plus_ac_hex":at_override.hex(),"final_header_id_hex":at_final.hex(),
                           "override_matches":ok1,"final_header_matches":ok2})
            if not ok1 or not ok2:
                raise RuntimeError(f"{cid}: authored identity relationship changed")
            tags[tag]=row
    finally:
        for fh in files.values():fh.close()
    return tags,checks

def find_registry(k,p,base):
    matches=[]
    for entry in range(base+TABLE_BEGIN,base+TABLE_END,8):
        raw=safe_read(k,p,entry,8)
        if raw is None:continue
        desc=struct.unpack("<Q",raw)[0]
        if not desc:continue
        rid=safe_read(k,p,desc,4)
        if rid is None or struct.unpack("<I",rid)[0]!=REGISTRY_ID:continue
        head=read(k,p,desc+8,0x18)
        arr=struct.unpack_from("<Q",head,0)[0];count=struct.unpack_from("<I",head,0x10)[0]
        matches.append((desc,entry,arr,count))
    if len(matches)!=1:raise RuntimeError(f"expected one registry {REGISTRY_ID}, found {len(matches)}")
    desc,entry,arr,count=matches[0]
    if count>1048576:raise RuntimeError(f"implausible registry count {count}")
    return {"descriptor":desc,"table_entry":entry,"array_ptr":arr,"count":count}

def sweep(k,p,base,reg,tags):
    count=reg["count"];arr=reg["array_ptr"]
    raw=read(k,p,arr,count*8) if count else b""
    objs=struct.unpack(f"<{count}Q",raw) if count else ()
    expected_method=base+IDENTITY_METHOD_RVA
    stats={"non_null":0,"identity_method":0,"built":0,"failures":0}
    matches=[];ambiguous=[]
    for slot,obj in enumerate(objs):
        if not obj:continue
        stats["non_null"]+=1
        vh=safe_read(k,p,obj,8)
        if vh is None:continue
        vt=struct.unpack("<Q",vh)[0]
        mh=safe_read(k,p,vt+0x38,8)
        if mh is None or struct.unpack("<Q",mh)[0]!=expected_method:continue
        stats["identity_method"]+=1
        rr=Reader(k,p)
        try:els,build=build_identity(rr,obj);stats["built"]+=1
        except Exception:stats["failures"]+=1;continue
        hits=[(i,e,tags[e]) for i,e in enumerate(els) if e in tags]
        if not hits:continue
        ids={x[2]["catalogue_id"] for x in hits}
        token=token_for_slot(slot);h=identity_hash(els)
        base_row={"token_hex":f"0x{token:016X}","registry":REGISTRY_ID,"slot":slot,
                  "object_ptr":f"0x{obj:X}","object_hash_hex":f"0x{h:016X}",
                  "identity_elements_hex":[e.hex() for e in els],"builder":build,
                  "read_process_memory_calls":rr.read_count}
        if len(ids)!=1:
            ambiguous.append({**base_row,"catalogue_ids":sorted(ids)});continue
        cid=next(iter(ids));row=next(x[2] for x in hits if x[2]["catalogue_id"]==cid)
        matches.append({**base_row,"catalogue_id":cid,"display_name":row.get("display_name"),
                        "wad":row["source"]["wad"],
                        "matched_element_indexes":[i for i,_,x in hits if x["catalogue_id"]==cid]})
    return stats,matches,ambiguous

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--game-root",type=Path,default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--catalogue",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    if sys.platform!="win32" or C.sizeof(C.c_void_p)!=8:raise RuntimeError("64-bit Windows required")
    game_root=a.game_root.resolve()
    catalogue=json.loads(a.catalogue.read_text(encoding="utf-8"))
    tags,checks=validate_catalogue(game_root,catalogue)

    k=k32_api();pid,name=find_process(k);base,size,exe=main_module(k,pid,name)
    exe_sha=sha256_file(exe)
    if exe_sha.lower()!=EXE_SHA:raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")
    p=k.OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION,False,pid)
    if not p:raise winerr("OpenProcess read-only failed")
    try:
        reg=find_registry(k,p,base)
        stats,raw_matches,ambiguous=sweep(k,p,base,reg,tags)
    finally:close(k,p)

    by={}
    for row in raw_matches:by.setdefault(row["catalogue_id"],[]).append(row)
    resolved=[];duplicates=[]
    for cid,items in sorted(by.items()):
        if len(items)==1:resolved.append(items[0])
        else:duplicates.append({"catalogue_id":cid,"tokens":[x["token_hex"] for x in items]})
    all_ids=sorted(r["catalogue_id"] for r in catalogue["ravens"])
    found={r["catalogue_id"] for r in resolved}
    missing=[x for x in all_ids if x not in found]

    known=[r for r in resolved if r["catalogue_id"]==KNOWN_ID]
    sanity={"catalogue_id":KNOWN_ID,"present":bool(known),
            "expected_token_hex":f"0x{KNOWN_TOKEN:016X}",
            "expected_object_hash_hex":f"0x{KNOWN_HASH:016X}","exact_match":None}
    if known:
        exact=int(known[0]["token_hex"],16)==KNOWN_TOKEN and int(known[0]["object_hash_hex"],16)==KNOWN_HASH
        sanity.update({"actual_token_hex":known[0]["token_hex"],
                       "actual_object_hash_hex":known[0]["object_hash_hex"],"exact_match":exact})
        if not exact:raise RuntimeError("known VikingFuneral Raven identity sanity check failed")

    complete=len(resolved)==53 and not missing and not duplicates and not ambiguous
    report={
        "schema":1,"captured_utc":datetime.now(timezone.utc).isoformat(),
        "result":"ALL_53_RAVEN_GAMEOBJECT_IDENTITIES_RESOLVED" if complete else "PARTIAL_RAVEN_GAMEOBJECT_IDENTITY_SWEEP",
        "process":{"pid":pid,"exe_name":name,"module_base":f"0x{base:X}","module_size":size,"exe_sha256":exe_sha},
        "catalogue":{"entries":53,"unique_final_record_ids":len(tags),"authored_identity_checks":checks,
                     "all_override_plus_ac_match_final_record_id":all(x["override_matches"] for x in checks)},
        "registry":{"id":REGISTRY_ID,"descriptor":f"0x{reg['descriptor']:X}",
                    "table_entry":f"0x{reg['table_entry']:X}","array_ptr":f"0x{reg['array_ptr']:X}",
                    "count":reg["count"],**stats},
        "resolved_count":len(resolved),"resolved":resolved,
        "missing_count":len(missing),"missing_catalogue_ids":missing,
        "duplicate_catalogue_matches":duplicates,"ambiguous_vector_matches":ambiguous,
        "known_raven_sanity":sanity,
        "safety":{"open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                  "debugger_attached":False,"remote_game_code_called":False,
                  "process_memory_written":False,"active_save_opened":False,
                  "save_or_progression_written":False,"game_files_written":False},
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    lines=[
        "Completionist Map - all Raven GameObject identities read-only sweep",
        f"result={report['result']}",
        f"registry={REGISTRY_ID} count={reg['count']} non_null={stats['non_null']} identity_method={stats['identity_method']} vectors={stats['built']} failures={stats['failures']}",
        f"resolved={len(resolved)} missing={len(missing)} duplicates={len(duplicates)} ambiguous={len(ambiguous)}",
        "known_vikingfuneral="+("absent" if not known else "exact_match"),
        "",
        "RESOLVED",
    ]
    for row in resolved:
        lines.append(f"{row['catalogue_id']} token={row['token_hex']} slot={row['slot']} object_hash={row['object_hash_hex']} wad={row['wad']}")
    if missing:lines+=["","MISSING",*missing]
    lines+=["","SAFETY","OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "process_memory_written=false","active_save_opened=false","save_or_progression_written=false"]
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"ALL_RAVEN_GAMEOBJECT_IDENTITIES_READONLY_SWEEP_COMPLETE resolved={len(resolved)} missing={len(missing)} registry_non_null={stats['non_null']} vectors={stats['built']}")
    print("process_memory_written=false active_save_opened=false save_or_progression_written=false")
    return 0

if __name__=="__main__":raise SystemExit(main())
