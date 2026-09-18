#!/usr/bin/env python3
"""Read LuaClient +0x70/+0x78 serialized pickle buffers from live GoW memory.

Safety:
- PROCESS_QUERY_INFORMATION | PROCESS_VM_READ only
- no debugger, no thread suspension, no process writes
- no game/save/progression writes

Static proof used:
  LuaClient slot14 save   -> RVA 0x5B2130
  LuaClient slot16 restore-> RVA 0x5B2280
  0x5AF4E0 reads qword [LuaClient+0x70] / [LuaClient+0x78]
  each points to [i32 length][carrier bytes]
  those bytes are passed to the proven carrier restore root 0x7E9550.

The probe locates the LuaClient vtable in the supported executable, scans only
committed readable process regions for live LuaClient objects, then parses both
native pickle buffers with the existing carrier parser and joins every 17-byte
GameObject payload against the solved 53-Raven identity catalogue.
"""
from __future__ import annotations
import argparse, ctypes as C, hashlib, importlib.util, json, os, struct, sys
from ctypes import wintypes as W
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXPECTED_EXE_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
PREFERRED_BASE=0x140000000
SAVE_RVA=0x5B2130
RESTORE_RVA=0x5B2280
VTABLE_SAVE_SLOT=14
VTABLE_RESTORE_SLOT=16
PROCESS_QUERY_INFORMATION=0x0400
PROCESS_VM_READ=0x0010
MEM_COMMIT=0x1000
MEM_PRIVATE=0x20000
MEM_MAPPED=0x40000
PAGE_NOACCESS=0x01
PAGE_GUARD=0x100
READABLE={0x02,0x04,0x08,0x20,0x40,0x80}
MAX_USER=0x00007FFFFFFFFFFF
MAX_BUFFER=32*1024*1024
CHUNK=4*1024*1024

def load_helper(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {path}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

MEM=load_helper("gow_mem",HERE/"read-raven-gameobject-identity-memory.py")
CARRIER=load_helper("gow_carrier",HERE/"gow-custom-userdata-carrier.py")

def pe_sections(raw:bytes):
    pe=struct.unpack_from("<I",raw,0x3C)[0]
    nsec=struct.unpack_from("<H",raw,pe+6)[0]
    optsz=struct.unpack_from("<H",raw,pe+20)[0]
    opt=pe+24
    magic=struct.unpack_from("<H",raw,opt)[0]
    if magic!=0x20B: raise RuntimeError("expected PE32+")
    image_base=struct.unpack_from("<Q",raw,opt+24)[0]
    sec0=opt+optsz
    out=[]
    for i in range(nsec):
        o=sec0+i*40
        name=raw[o:o+8].split(b"\0",1)[0].decode("ascii","replace")
        vsize,rva,rawsize,rawptr=struct.unpack_from("<IIII",raw,o+8)
        out.append({"name":name,"rva":rva,"vsize":vsize,"rawsize":rawsize,"rawptr":rawptr})
    return image_base,out

def fileoff_to_rva(off:int,sections):
    for s in sections:
        lo=s["rawptr"]; hi=lo+s["rawsize"]
        if lo<=off<hi: return s["rva"]+(off-lo)
    return None

def find_luaclient_vtables(exe:Path):
    raw=exe.read_bytes()
    image_base,sections=pe_sections(raw)
    save_va=image_base+SAVE_RVA
    restore_va=image_base+RESTORE_RVA
    needle=struct.pack("<Q",save_va)
    hits=[]; pos=0
    while True:
        i=raw.find(needle,pos)
        if i<0: break
        start=i-VTABLE_SAVE_SLOT*8
        if start>=0 and start+VTABLE_RESTORE_SLOT*8+8<=len(raw):
            rv=struct.unpack_from("<Q",raw,start+VTABLE_RESTORE_SLOT*8)[0]
            if rv==restore_va:
                rva=fileoff_to_rva(start,sections)
                if rva is not None:
                    # Require several first slots to point back into image.
                    first=[struct.unpack_from("<Q",raw,start+j*8)[0] for j in range(0,20)]
                    imageish=sum(1 for v in first if image_base<=v<image_base+0x4000000)
                    if imageish>=10:
                        hits.append({"file_offset":start,"rva":rva,"rva_hex":f"0x{rva:X}","image_pointer_slots":imageish})
        pos=i+1
    # unique by RVA
    uniq={x["rva"]:x for x in hits}
    return image_base,[uniq[k] for k in sorted(uniq)]

def configure_virtual_query(k32):
    k32.VirtualQueryEx.argtypes=[W.HANDLE,W.LPCVOID,W.LPVOID,C.c_size_t]
    k32.VirtualQueryEx.restype=C.c_size_t

def virtual_regions(k32,proc):
    configure_virtual_query(k32)
    addr=0
    buf=C.create_string_buffer(48)
    while addr<MAX_USER:
        n=k32.VirtualQueryEx(proc,C.c_void_p(addr),buf,C.sizeof(buf))
        if not n: break
        b=buf.raw
        base=struct.unpack_from("<Q",b,0)[0]
        size=struct.unpack_from("<Q",b,24)[0]
        state=struct.unpack_from("<I",b,32)[0]
        protect=struct.unpack_from("<I",b,36)[0]
        typ=struct.unpack_from("<I",b,40)[0]
        if size<=0: break
        yield base,size,state,protect,typ
        nxt=base+size
        if nxt<=addr: break
        addr=nxt

def readable(protect:int):
    if protect & PAGE_GUARD or protect & PAGE_NOACCESS: return False
    return (protect & 0xFF) in READABLE

def scan_pattern(k32,proc,pattern:bytes):
    hits=[]
    regions=0; bytes_scanned=0
    for base,size,state,protect,typ in virtual_regions(k32,proc):
        if state!=MEM_COMMIT or typ not in (MEM_PRIVATE,MEM_MAPPED) or not readable(protect):
            continue
        regions+=1
        off=0
        tail=b""
        while off<size:
            want=min(CHUNK,size-off)
            data=MEM.safe_read(k32,proc,base+off,want)
            if data is None:
                off+=want; tail=b""; continue
            bytes_scanned+=len(data)
            blob=tail+data
            start_base=base+off-len(tail)
            p=0
            while True:
                i=blob.find(pattern,p)
                if i<0:break
                hits.append(start_base+i)
                p=i+1
            tail=blob[-(len(pattern)-1):] if len(pattern)>1 else b""
            off+=want
    return hits,{"regions_scanned":regions,"bytes_scanned":bytes_scanned}

def plausible_ptr(v:int):
    return 0x10000<=v<=MAX_USER and (v&7)==0

def extract_ascii(blob:bytes):
    vals=[]; cur=bytearray()
    for b in blob:
        if 32<=b<=126:
            cur.append(b)
        else:
            if len(cur)>=5:
                s=cur.decode("ascii","replace")
                if ".wad" in s.lower() or "level" in s.lower() or "lua" in s.lower():
                    vals.append(s[:220])
            cur.clear()
    if len(cur)>=5:
        s=cur.decode("ascii","replace")
        if ".wad" in s.lower() or "level" in s.lower() or "lua" in s.lower(): vals.append(s[:220])
    return vals[:80]

def identity_catalogue(path:Path):
    data=json.loads(path.read_text(encoding="utf-8"))["identities"]
    by_payload={}
    for x in data:
        by_payload[x["serialized_payload_hex"].lower()]={
            "catalogue_id":x["catalogue_id"],"region":x.get("region"),"realm":x.get("realm"),
            "wad":x.get("wad"),"object_hash_hex":x.get("object_hash_hex"),"instance_guid":x.get("instance_guid")
        }
    return by_payload

def buffer_report(k32,proc,ptr:int,label:str,out_dir:Path,client_index:int,ids):
    row={"label":label,"pointer_hex":f"0x{ptr:X}","present":False}
    if not plausible_ptr(ptr): return row
    head=MEM.safe_read(k32,proc,ptr,4)
    if head is None or len(head)!=4:return row
    length=struct.unpack("<i",head)[0]
    row["length"]=length
    if length<=0 or length>MAX_BUFFER:return row
    data=MEM.safe_read(k32,proc,ptr+4,length)
    if data is None or len(data)!=length:return row
    row["present"]=True
    row["sha256"]=hashlib.sha256(data).hexdigest()
    bin_name=f"client-{client_index:03d}-{label}.bin"
    (out_dir/bin_name).write_bytes(data)
    row["file"]=bin_name
    try:
        parsed=CARRIER.inspect_carrier(data)
        row["carrier_valid"]=True
        row["header"]=parsed.get("header")
        row["decompression"]=parsed.get("decompression")
        prefix=bytes.fromhex(parsed.get("decompressed_prefix_hex") or "")
        row["prefix_ascii"]=extract_ascii(prefix)
        row["contains_ravenKilled"]=b"ravenKilled\x00" in prefix
        matches=[]
        for rec in parsed.get("records",[]):
            if not rec.get("valid"):continue
            payload=(rec.get("payload_hex") or "").lower()
            ident=ids.get(payload)
            if ident:
                matches.append({"record_index":rec["index"],"class_key":rec.get("class_key"),
                                "payload_hex":payload,**ident})
        row["matched_ravens"]=matches
        row["matched_raven_count"]=len(matches)
        row["record_count"]=len(parsed.get("records",[]))
    except Exception as exc:
        row["carrier_valid"]=False
        row["carrier_error"]=repr(exc)
    return row

def shallow_client_strings(k32,proc,head:bytes):
    found=[]
    for off in range(0,min(len(head),0xA0)-7,8):
        ptr=struct.unpack_from("<Q",head,off)[0]
        if not plausible_ptr(ptr):continue
        blob=MEM.safe_read(k32,proc,ptr,0x500)
        if blob:
            vals=extract_ascii(blob)
            if vals:found.append({"field_offset_hex":f"0x{off:X}","pointer_hex":f"0x{ptr:X}","strings":vals[:12]})
    return found[:40]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--identities",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    args=ap.parse_args()
    if os.name!="nt":raise RuntimeError("Windows-only")
    ids=identity_catalogue(args.identities)
    k32=MEM.configure_kernel32()
    pid,exe_name=MEM.find_supported_process(k32)
    module_base,module_size,exe_path=MEM.get_main_module(k32,pid,exe_name)
    exe=Path(exe_path)
    exe_sha=MEM.sha256_file(exe)
    if exe_sha.lower()!=EXPECTED_EXE_SHA256:raise RuntimeError(f"unsupported GoW.exe {exe_sha}")
    preferred,vtables=find_luaclient_vtables(exe)
    if not vtables:raise RuntimeError("LuaClient vtable not found statically")
    runtime_vtables=[module_base+x["rva"] for x in vtables]

    proc=k32.OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,False,pid)
    if not proc:raise MEM.winerr("OpenProcess(read-only) failed")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    try:
        raw_hits=[]; scan_stats={}
        for vrva,vptr in zip([x["rva"] for x in vtables],runtime_vtables):
            hits,stats=scan_pattern(k32,proc,struct.pack("<Q",vptr))
            raw_hits.extend((h,vptr,vrva) for h in hits)
            scan_stats[f"0x{vrva:X}"]=stats

        seen=set(); clients=[]
        for address,vptr,vrva in sorted(raw_hits):
            if address in seen:continue
            seen.add(address)
            head=MEM.safe_read(k32,proc,address,0xA0)
            if head is None or len(head)<0x80:continue
            if struct.unpack_from("<Q",head,0)[0]!=vptr:continue
            lua_state=struct.unpack_from("<Q",head,0x58)[0]
            p70=struct.unpack_from("<Q",head,0x70)[0]
            p78=struct.unpack_from("<Q",head,0x78)[0]
            # Strong sanity: at least one known structural field must be pointer-like.
            if not (plausible_ptr(lua_state) or plausible_ptr(p70) or plausible_ptr(p78)):continue
            idx=len(clients)
            row={
                "index":idx,"address_hex":f"0x{address:X}","vtable_rva_hex":f"0x{vrva:X}",
                "lua_state_hex":f"0x{lua_state:X}","field_0x70_hex":f"0x{p70:X}","field_0x78_hex":f"0x{p78:X}",
                "shallow_identity_strings":shallow_client_strings(k32,proc,head),
            }
            row["pickle_0x70"]=buffer_report(k32,proc,p70,"pickle70",args.output_dir,idx,ids)
            row["pickle_0x78"]=buffer_report(k32,proc,p78,"pickle78",args.output_dir,idx,ids)
            clients.append(row)

        matched={}
        for c in clients:
            for key in ("pickle_0x70","pickle_0x78"):
                b=c[key]
                for m in b.get("matched_ravens",[]) or []:
                    matched.setdefault(m["catalogue_id"],[]).append({
                        "client_index":c["index"],"buffer":key,"record_index":m["record_index"],
                        "region":m.get("region"),"realm":m.get("realm"),"wad":m.get("wad")
                    })
        report={
            "schema":1,"analysis":"live_luaclient_pickle_buffers","captured_utc":datetime.now(timezone.utc).isoformat(),
            "process":{"pid":pid,"exe_name":exe_name,"exe_path":str(exe),"exe_sha256":exe_sha,
                       "module_base_hex":f"0x{module_base:X}","module_size":module_size},
            "static":{"preferred_image_base_hex":f"0x{preferred:X}",
                      "save_rva_hex":f"0x{SAVE_RVA:X}","restore_rva_hex":f"0x{RESTORE_RVA:X}",
                      "vtable_candidates":vtables,
                      "runtime_vtables_hex":[f"0x{x:X}" for x in runtime_vtables]},
            "scan_stats":scan_stats,
            "raw_vtable_hit_count":len(raw_hits),
            "validated_luaclient_count":len(clients),
            "clients":clients,
            "matched_raven_catalogue_ids":sorted(matched),
            "matched_raven_count":len(matched),
            "matched_raven_locations":matched,
            "safety":{"access":"PROCESS_QUERY_INFORMATION|PROCESS_VM_READ","debugger_attached":False,
                      "thread_suspend_resume":False,"process_memory_written":False,
                      "game_files_written":False,"save_or_progression_written":False},
        }
        (args.output_dir/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(f"LUACLIENT_PICKLE_BUFFER_CAPTURE_COMPLETE clients={len(clients)} matchedRavens={len(matched)} rawVtableHits={len(raw_hits)}")
        for c in clients:
            b70=c["pickle_0x70"];b78=c["pickle_0x78"]
            print(f"CLIENT {c['index']} addr={c['address_hex']} lua={c['lua_state_hex']} "
                  f"p70={b70.get('length')} valid70={b70.get('carrier_valid')} ravens70={b70.get('matched_raven_count',0)} "
                  f"p78={b78.get('length')} valid78={b78.get('carrier_valid')} ravens78={b78.get('matched_raven_count',0)}")
            for x in (b70.get("matched_ravens") or [])+(b78.get("matched_ravens") or []):
                print(f"  RAVEN {x['catalogue_id']} region={x.get('region')} wad={x.get('wad')}")
        print("MATCHED_IDS="+",".join(sorted(matched)))
        print("process_memory_written=false save_or_progression_written=false")
    finally:
        MEM.close_handle(k32,proc)

if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr);raise SystemExit(1)
