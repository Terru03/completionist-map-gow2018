#!/usr/bin/env python3
"""Read GoW Raven RegionSummary counter trees directly from live memory, read-only.

This emulates the proved native getters without calling game code:
  GetCounter              0x841E50
  GetCounterChild         0x841CE0
  GetCounterChildrenCount 0x841D50
  common lookup           0x841EC0

Proved layout from those wrappers:
  global lookup count  = module + 0x22F2B5C (int32)
  global lookup table  = *(module + 0x22F2B60)
  lookup record stride = 16 bytes: key:u64, counter_index:i32, value:i32
  counter owner        = *(module + 0x22E7988)
  counter array        = *(counter_owner + 0xB10)
  counter stride       = 64 bytes
  child list pointer   = counter + 0x08
  child count          = counter + 0x10
  each child key       = u64 child_list[i]

The string-key hash is the exact case-insensitive loop recovered from 0x841EC0.
Only PROCESS_VM_READ | PROCESS_QUERY_INFORMATION are requested. No game code is
called and no process/save/progression/game file is written.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, struct, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
EXPECTED_EXE_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
LOOKUP_COUNT_RVA=0x22F2B5C
LOOKUP_PTR_RVA=0x22F2B60
COUNTER_OWNER_RVA=0x22E7988
LOOKUP_STRIDE=16
COUNTER_STRIDE=64
MAX_LOOKUP_COUNT=1_000_000
MAX_CHILDREN=4096
MASK64=0xFFFFFFFFFFFFFFFF

def load_module(name, filename):
    p=HERE/filename
    spec=importlib.util.spec_from_file_location(name,p)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def counter_hash(text:str)->int:
    value=0
    for b in text.encode("utf-8"):
        if 0x61<=b<=0x7A: b-=0x20
        value=((value+b)*0x401)&MASK64
        value ^= value>>6
    return value

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()

def string_candidates(row:dict):
    out={}
    def add(label,v):
        if isinstance(v,str) and v:
            out[label]=v
    add("catalogue_id",row.get("catalogue_id"))
    add("realm",row.get("realm"))
    add("region",row.get("region"))
    add("region_id",row.get("region_id"))
    n=row.get("native",{})
    for k in ("instance_guid","final_record_id","override_record_id","prototype_id",
              "parent_prototype_id","script_guid","object_name","override_name"):
        add("native."+k,n.get(k))
    guid=n.get("instance_guid")
    if isinstance(guid,str):
        add("native.instance_guid_nohyphen",guid.replace("-",""))
    src=row.get("source",{})
    add("source.wad",src.get("wad"))
    for i,t in enumerate(src.get("transform_chain",[])):
        if isinstance(t,dict):
            add(f"source.transform_chain[{i}].record_id",t.get("record_id"))
            add(f"source.transform_chain[{i}].name",t.get("name"))
    p=row.get("progression",{})
    add("progression.parent_quest",p.get("parent_quest"))
    add("progression.instance_key",p.get("instance_key"))
    add("progression.field",p.get("field"))
    return out

def printable_hash_matches(path:Path, wanted:set[int]):
    raw=path.read_bytes()
    found=defaultdict(set)
    rx=re.compile(rb"[A-Za-z0-9_./:\\-]{3,192}")
    for m in rx.finditer(raw):
        try: s=m.group().decode("ascii")
        except UnicodeDecodeError: continue
        h=counter_hash(s)
        if h in wanted:
            found[h].add(s)
    # Also locate the key bytes themselves and retain a small printable context.
    raw_key_hits=defaultdict(list)
    for key in wanted:
        needle=struct.pack("<Q",key)
        start=0
        while len(raw_key_hits[key])<32:
            at=raw.find(needle,start)
            if at<0: break
            lo=max(0,at-64); hi=min(len(raw),at+72)
            context="".join(chr(b) if 32<=b<127 else "." for b in raw[lo:hi])
            raw_key_hits[key].append({"offset":at,"offset_hex":f"0x{at:X}","ascii_context":context})
            start=at+1
    return found,raw_key_hits

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root",type=Path,default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--catalogue",type=Path,default=REPO/"catalogue"/"odins-ravens.json")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if sys.platform!="win32": raise RuntimeError("Windows-only live-memory probe")

    helper=load_module("gow_counter_tree_readonly","read-raven-gameobject-identity-memory.py")
    catalogue=json.loads(args.catalogue.read_text(encoding="utf-8"))
    ravens=catalogue["ravens"]
    parent_rows=defaultdict(list)
    for row in ravens:
        parent_rows[row["progression"]["parent_quest"]].append(row)

    candidate_by_hash=defaultdict(list)
    for row in ravens:
        for label,text in string_candidates(row).items():
            candidate_by_hash[counter_hash(text)].append({
                "catalogue_id":row["catalogue_id"],"field":label,"text":text,
            })

    k32=helper.configure_kernel32()
    pid,exe_name=helper.find_supported_process(k32)
    module_base,module_size,exe_path=helper.get_main_module(k32,pid,exe_name)
    exe_sha=helper.sha256_file(exe_path)
    if exe_sha.lower()!=EXPECTED_EXE_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")
    access=helper.PROCESS_VM_READ|helper.PROCESS_QUERY_INFORMATION
    process=k32.OpenProcess(access,False,pid)
    if not process: raise helper.winerr("OpenProcess(read-only) failed")

    try:
        lookup_count=struct.unpack("<i",helper.read_mem(k32,process,module_base+LOOKUP_COUNT_RVA,4))[0]
        lookup_ptr=helper.u64(k32,process,module_base+LOOKUP_PTR_RVA)
        owner=helper.u64(k32,process,module_base+COUNTER_OWNER_RVA)
        counter_array=helper.u64(k32,process,owner+0xB10)
        if not (0<lookup_count<=MAX_LOOKUP_COUNT): raise RuntimeError(f"implausible lookup_count {lookup_count}")
        if not lookup_ptr or not owner or not counter_array: raise RuntimeError("counter global pointer is null")

        raw=helper.read_mem(k32,process,lookup_ptr,lookup_count*LOOKUP_STRIDE)
        lookup={}
        duplicate_keys=[]
        for i in range(lookup_count):
            key,index,value=struct.unpack_from("<Qii",raw,i*LOOKUP_STRIDE)
            rec={"record_index":i,"key":key,"key_hex":f"0x{key:016X}",
                 "counter_index":index,"value":value}
            if key in lookup: duplicate_keys.append(f"0x{key:016X}")
            else: lookup[key]=rec

        parents=[]
        all_child_keys=set()
        for parent_name,rows in sorted(parent_rows.items()):
            key=counter_hash(parent_name)
            rec=lookup.get(key)
            p={"parent":parent_name,"parent_hash_hex":f"0x{key:016X}",
               "catalogue_count":len(rows),"lookup_found":rec is not None}
            if rec is None:
                parents.append(p); continue
            idx=rec["counter_index"]
            p.update({"counter_index":idx,"value":rec["value"]})
            if idx<0:
                p["counter_error"]="negative_counter_index"; parents.append(p); continue
            cptr=counter_array+idx*COUNTER_STRIDE
            child_ptr=helper.u64(k32,process,cptr+0x08)
            child_count=struct.unpack("<i",helper.read_mem(k32,process,cptr+0x10,4))[0]
            if not (0<=child_count<=MAX_CHILDREN):
                p["counter_error"]=f"implausible_child_count:{child_count}"; parents.append(p); continue
            children=[]
            child_raw=helper.read_mem(k32,process,child_ptr,child_count*8) if child_count else b""
            for i in range(child_count):
                child_key=struct.unpack_from("<Q",child_raw,i*8)[0]
                all_child_keys.add(child_key)
                child_rec=lookup.get(child_key)
                children.append({
                    "ordinal":i,
                    "key_hex":f"0x{child_key:016X}",
                    "lookup_found":child_rec is not None,
                    "value":child_rec["value"] if child_rec else None,
                    "counter_index":child_rec["counter_index"] if child_rec else None,
                    "catalogue_string_hash_matches":candidate_by_hash.get(child_key,[]),
                })
            p.update({
                "child_count":child_count,
                "children":children,
                "child_value_sum":sum(c["value"] for c in children if isinstance(c.get("value"),int)),
            })
            parents.append(p)

        # Search only WADs associated with Raven parents for child-key names/embedded keys.
        wad_evidence={}
        wad_to_parents=defaultdict(set)
        for parent_name,rows in parent_rows.items():
            for row in rows: wad_to_parents[row["source"]["wad"]].add(parent_name)
        for wad,parents_for_wad in sorted(wad_to_parents.items()):
            path=args.game_root/"exec"/"wad"/"pc_le"/wad
            if not path.is_file(): continue
            relevant=set()
            for p in parents:
                if p["parent"] in parents_for_wad:
                    for c in p.get("children",[]): relevant.add(int(c["key_hex"],16))
            if not relevant: continue
            strings,key_hits=printable_hash_matches(path,relevant)
            wad_evidence[wad]={
                "sha256":sha256(path),
                "parents":sorted(parents_for_wad),
                "child_key_string_matches":{f"0x{k:016X}":sorted(v) for k,v in strings.items()},
                "embedded_child_key_hits":{f"0x{k:016X}":v for k,v in key_hits.items() if v},
            }

        partial=[p for p in parents if p.get("lookup_found") and p.get("child_count") and 0<p.get("value",0)<p.get("child_count",0)]
        report={
            "schema":1,
            "captured_utc":datetime.now(timezone.utc).isoformat(),
            "analysis":"read_only_native_raven_counter_tree",
            "process":{"pid":pid,"exe_name":exe_name,"exe_sha256":exe_sha,
                       "module_base":f"0x{module_base:X}","module_size":module_size},
            "native_layout":{
                "lookup_count_rva":f"0x{LOOKUP_COUNT_RVA:X}",
                "lookup_ptr_rva":f"0x{LOOKUP_PTR_RVA:X}",
                "counter_owner_rva":f"0x{COUNTER_OWNER_RVA:X}",
                "lookup_count":lookup_count,"lookup_ptr":f"0x{lookup_ptr:X}",
                "counter_owner":f"0x{owner:X}","counter_array":f"0x{counter_array:X}",
                "lookup_stride":LOOKUP_STRIDE,"counter_stride":COUNTER_STRIDE,
            },
            "parents":parents,
            "partial_parents":[p["parent"] for p in partial],
            "all_child_key_count":len(all_child_keys),
            "duplicate_lookup_keys":duplicate_keys[:128],
            "wad_evidence":wad_evidence,
            "safety":{"open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                      "remote_game_code_called":False,"debugger_attached":False,
                      "process_memory_written":False,"save_or_progression_written":False,
                      "game_files_written":False},
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(f"RAVEN_COUNTER_TREE_CAPTURED lookup={lookup_count} parents={len(parents)} partial={len(partial)} childKeys={len(all_child_keys)}")
        for p in parents:
            print(f"{p['parent']} value={p.get('value')} children={p.get('child_count')} childSum={p.get('child_value_sum')}")
            for c in p.get("children",[]):
                ms=c["catalogue_string_hash_matches"]
                print(f"  child[{c['ordinal']}] key={c['key_hex']} value={c['value']} candidateMatches={len(ms)}")
        print("process_memory_written=false save_or_progression_written=false")
        return 0
    finally:
        helper.close_handle(k32,process)

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr); raise SystemExit(1)
