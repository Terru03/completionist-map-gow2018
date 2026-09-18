#!/usr/bin/env python3
"""Enumerate GoW GameObject registry 238 and match all 53 Raven identities.

Read-only live-memory probe. It requests only PROCESS_VM_READ and
PROCESS_QUERY_INFORMATION, reconstructs the already-proven 0x550700 GameObject
identity vector for each registered object, hashes it with the proven native
algorithm, and joins exact hashes to catalogue/odins-ravens-save-identities.json.

No debugger, remote code execution, process write, save write, progression write,
streaming call, or game API call is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
REGISTRY_ID=238
EXPECTED_EXE_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
KNOWN_RAVEN_ID="raven_642d0d164af0a5d4076e77933c549a5d"
KNOWN_RAVEN_TOKEN=0x1BB001DD
KNOWN_RAVEN_HASH=0x98BE1707BA2D65A9

def load_module(name:str, filename:str):
    path=HERE/filename
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load helper {path}")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def registry_descriptor(helper,k32,process,module_base:int,registry_id:int):
    matches=[]
    begin=module_base+helper.REGISTRY_TABLE_BEGIN_RVA
    end=module_base+helper.REGISTRY_TABLE_END_RVA
    for entry in range(begin,end,8):
        raw=helper.safe_read(k32,process,entry,8)
        if raw is None: continue
        ptr=struct.unpack("<Q",raw)[0]
        if not ptr: continue
        rid_raw=helper.safe_read(k32,process,ptr,4)
        if rid_raw is None: continue
        rid=struct.unpack("<I",rid_raw)[0]
        if rid==registry_id:
            matches.append((entry,ptr))
    if len(matches)!=1:
        raise RuntimeError(f"registry {registry_id}: expected one descriptor, found {len(matches)}")
    return matches[0]

def packed_token(registry:int, flavor:int, slot:int)->int:
    return 1 | (registry<<1) | (flavor<<17) | (slot<<18)

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identities",type=Path,default=REPO/"catalogue"/"odins-ravens-save-identities.json")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    if sys.platform!="win32":
        raise RuntimeError("Windows-only read-only live-memory probe")

    helper=load_module("gow_readonly_registry238","read-raven-gameobject-identity-memory.py")
    identity=load_module("gow_exact_identity_registry238","capture-raven-exact-identity-vector.py")

    doc=json.loads(args.identities.read_text(encoding="utf-8"))
    rows=doc.get("identities")
    if not isinstance(rows,list) or len(rows)!=53:
        raise RuntimeError("expected complete 53-Raven save-identity catalogue")
    by_hash={int(r["object_hash_hex"],16):r["catalogue_id"] for r in rows}
    if len(by_hash)!=53:
        raise RuntimeError("Raven object hashes are not unique")

    k32=helper.configure_kernel32()
    pid,exe_name=helper.find_supported_process(k32)
    module_base,module_size,exe_path=helper.get_main_module(k32,pid,exe_name)
    exe_sha=helper.sha256_file(exe_path)
    if exe_sha.lower()!=EXPECTED_EXE_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    access=helper.PROCESS_VM_READ|helper.PROCESS_QUERY_INFORMATION
    process=k32.OpenProcess(access,False,pid)
    if not process:
        raise helper.winerr("OpenProcess(read-only) failed")

    try:
        table_entry,descriptor=registry_descriptor(helper,k32,process,module_base,REGISTRY_ID)
        arrays=[]
        matches={}
        pointer_seen={}
        failures=[]
        identity_successes=0
        nonnull=0

        for flavor,base_off in ((0,0x08),(1,0x20)):
            array_ptr=helper.u64(k32,process,descriptor+base_off)
            count=helper.u32(k32,process,descriptor+base_off+0x10)
            if count>1_000_000:
                raise RuntimeError(f"registry {REGISTRY_ID} flavor {flavor}: implausible count {count}")
            raw=helper.read_mem(k32,process,array_ptr,count*8) if count else b""
            pointers=struct.unpack("<"+("Q"*count),raw) if count else ()
            flavor_nonnull=sum(1 for p in pointers if p)
            nonnull+=flavor_nonnull
            arrays.append({
                "flavor":flavor,
                "array_ptr":f"0x{array_ptr:X}",
                "count":count,
                "nonnull_slots":flavor_nonnull,
            })

            for slot,obj in enumerate(pointers):
                if not obj: continue
                # The same GameObject can appear in more than one handle slot. Its
                # identity hash is object-derived, so reconstruct it once.
                cached=pointer_seen.get(obj)
                if cached is None:
                    reader=identity.Reader(helper,k32,process)
                    try:
                        elements,build=identity.build_550700(reader,obj)
                        object_hash=identity.raw_identity_hash(elements)
                        cached=("ok",object_hash,len(elements),reader.read_count,build["path"])
                        identity_successes+=1
                    except Exception as exc:
                        cached=("error",repr(exc))
                        if len(failures)<80:
                            failures.append({
                                "object_ptr":f"0x{obj:X}",
                                "flavor":flavor,
                                "slot":slot,
                                "error":repr(exc),
                            })
                    pointer_seen[obj]=cached

                if cached[0]!="ok": continue
                object_hash=cached[1]
                cid=by_hash.get(object_hash)
                if cid is None: continue
                token=packed_token(REGISTRY_ID,flavor,slot)
                row={
                    "catalogue_id":cid,
                    "object_hash_hex":f"0x{object_hash:016X}",
                    "token_hex":f"0x{token:016X}",
                    "registry":REGISTRY_ID,
                    "flavor":flavor,
                    "slot":slot,
                    "object_ptr":f"0x{obj:X}",
                    "identity_element_count":cached[2],
                    "identity_read_calls":cached[3],
                    "identity_path":cached[4],
                }
                matches.setdefault(cid,[]).append(row)

        matched_ids=sorted(matches)
        duplicate_ids=sorted(cid for cid,v in matches.items() if len(v)>1)
        missing=sorted(set(r["catalogue_id"] for r in rows)-set(matched_ids))
        known_rows=matches.get(KNOWN_RAVEN_ID,[])
        known_exact=any(
            int(r["token_hex"],16)==KNOWN_RAVEN_TOKEN and
            int(r["object_hash_hex"],16)==KNOWN_RAVEN_HASH
            for r in known_rows
        )

        report={
            "schema":1,
            "captured_utc":datetime.now(timezone.utc).isoformat(),
            "analysis":"read_only_registry238_full_raven_identity_join",
            "process":{
                "pid":pid,"exe_name":exe_name,"exe_sha256":exe_sha,
                "module_base":f"0x{module_base:X}","module_size":module_size,
            },
            "registry":{
                "id":REGISTRY_ID,
                "table_entry":f"0x{table_entry:X}",
                "descriptor":f"0x{descriptor:X}",
                "arrays":arrays,
            },
            "scan":{
                "nonnull_slots":nonnull,
                "unique_object_pointers":len(pointer_seen),
                "identity_successes":identity_successes,
                "identity_failures":sum(1 for v in pointer_seen.values() if v[0]=="error"),
                "failure_samples":failures,
            },
            "raven_join":{
                "catalogue_count":53,
                "matched_catalogue_count":len(matched_ids),
                "matched_catalogue_ids":matched_ids,
                "missing_catalogue_count":len(missing),
                "missing_catalogue_ids":missing,
                "duplicate_catalogue_ids":duplicate_ids,
                "matches":matches,
                "known_viking_funeral_token_exact":known_exact,
            },
            "result":(
                "REGISTRY238_ALL_53_RAVENS_RESOLVED"
                if len(matched_ids)==53 and not duplicate_ids and known_exact
                else "REGISTRY238_PARTIAL_RAVEN_RESOLUTION"
            ),
            "safety":{
                "open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                "debugger_attached":False,
                "remote_game_code_called":False,
                "process_memory_written":False,
                "save_or_progression_written":False,
                "game_files_written":False,
            },
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(f"{report['result']} matched={len(matched_ids)}/53 nonnull={nonnull} objects={len(pointer_seen)}")
        print(f"known_viking_funeral_token_exact={str(known_exact).lower()}")
        for cid in matched_ids:
            vals=matches[cid]
            print(cid+" "+" ".join(f"flavor={v['flavor']} slot={v['slot']} token={v['token_hex']}" for v in vals))
        print("process_memory_written=false save_or_progression_written=false")
        return 0
    finally:
        helper.close_handle(k32,process)

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        raise SystemExit(1)
