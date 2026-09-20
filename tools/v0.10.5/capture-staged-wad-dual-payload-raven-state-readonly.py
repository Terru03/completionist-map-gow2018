#!/usr/bin/env python3
"""Capture both staged-WAD variable payload channels and decode exact Raven state.

Static tracing proves each 0xA8 staged WAD record has two variable payload
descriptors backed by the same global payload pool:
  channel A: +0x30/+0x38 pointers, +0x40 size
  channel B: +0x48/+0x50 pointers, +0x58 size

The previous observer inspected channel B only. This read-only observer inspects
both channels, exact-matches all 53 Raven GameObject identities, and reuses the
solved custom-userdata Raven decoder. No writes, debugger, remote calls, or save
file access are performed.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
OBSERVER=HERE/"capture-staged-wad-raven-state-readonly.py"
DECODER=HERE/"decode-active-raven-subobject-state.py"
IDENTITIES=REPO/"catalogue"/"odins-ravens-save-identities.json"

CHANNELS={
    "A_softpickle_candidate":{"ptr_a_off":0x30,"ptr_b_off":0x38,"size_off":0x40},
    "B_wad_checkpoint":{"ptr_a_off":0x48,"ptr_b_off":0x50,"size_off":0x58},
}
KNOWN_FUNERAL_RAVEN="01b0b227342530c24ea9652dba0717be98"
MAX_TOTAL_BYTES=16*1024*1024

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {path}")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    if sys.platform!="win32" or C.sizeof(C.c_void_p)!=8: raise RuntimeError("64-bit Windows required")

    obs=load_module("staged_dual_obs",OBSERVER)
    dec=load_module("staged_dual_dec",DECODER)

    ids=json.loads(IDENTITIES.read_text(encoding="utf-8"))
    rows=ids.get("identities")
    if not isinstance(rows,list) or len(rows)!=53: raise RuntimeError("expected 53 Raven identities")
    object_map={int(x["object_hash_hex"],16):x["catalogue_id"] for x in rows}
    payload_map=[(bytes.fromhex(x["serialized_payload_hex"]),x) for x in rows]
    registry_hash=int(rows[0]["registry_hash_hex"],16)
    meta={x["catalogue_id"]:x for x in rows}
    funeral_needle=bytes.fromhex(KNOWN_FUNERAL_RAVEN)

    k=obs.k32_api();pid,name=obs.find_process(k);base,exe=obs.main_module(k,pid,name)
    sha=obs.sha256_file(Path(exe)).lower()
    if sha!=obs.EXE_SHA: raise RuntimeError(f"unsupported GoW.exe SHA-256: {sha}")
    p=k.OpenProcess(obs.PROCESS_VM_READ|obs.PROCESS_QUERY_INFORMATION,False,pid)
    if not p: raise obs.winerr("OpenProcess read-only failed")

    records=[];total_bytes=0;state_by_id=defaultdict(set);known_funeral_hits=[]
    channel_summary={n:{"payload_records":0,"payload_bytes":0,"identity_records":0,"identity_count":0,
                        "decoded_records":0,"decoded_entries":0,"killed_ids":set(),"false_ids":set()} for n in CHANNELS}
    try:
        pool_size=obs.u32(obs.read(k,p,base+obs.PAYLOAD_SIZE_RVA,4))
        pool_base=obs.u64(obs.read(k,p,base+obs.PAYLOAD_BASE_RVA,8))
        count=obs.u32(obs.read(k,p,base+obs.RECORD_COUNT_RVA,4))
        if count>obs.MAX_RECORDS: raise RuntimeError(f"implausible staged record count: {count}")
        if pool_size>obs.MAX_POOL_SIZE: raise RuntimeError(f"implausible staged pool size: {pool_size}")
        pool_end=pool_base+pool_size

        for i in range(count):
            addr=base+obs.RECORD_BASE_RVA+i*obs.RECORD_STRIDE
            raw=obs.read(k,p,addr,obs.RECORD_STRIDE)
            rec={"index":i,"address":f"0x{addr:X}","key_hex":f"0x{obs.u32(raw,obs.RECORD_KEY_OFF):08X}",
                 "name":obs.printable_name(raw[obs.RECORD_NAME_OFF:obs.RECORD_NAME_OFF+obs.RECORD_NAME_SIZE]),"channels":{}}
            for cname,cfg in CHANNELS.items():
                pa=obs.u64(raw,cfg["ptr_a_off"]);pb=obs.u64(raw,cfg["ptr_b_off"]);size=obs.u32(raw,cfg["size_off"])
                out={"ptr_a":f"0x{pa:X}","ptr_b":f"0x{pb:X}","size":size,"in_pool":False,
                     "sha256":None,"exact_raven_identity_hits":[],"known_funeral_raven_offsets":[],"decoded":None}
                if size==0:
                    rec["channels"][cname]=out;continue
                if size>obs.MAX_RECORD_PAYLOAD:
                    out["rejected"]=f"size_above_cap_0x{size:X}";rec["channels"][cname]=out;continue
                valid=(pool_size>0 and pa>=pool_base and pa+size>=pa and pa+size<=pool_end)
                out["in_pool"]=valid
                if not valid:
                    out["rejected"]="outside_proven_pool_extent";rec["channels"][cname]=out;continue
                if total_bytes+size>MAX_TOTAL_BYTES: raise RuntimeError("aggregate payload read cap exceeded")
                payload=obs.read(k,p,pa,size);total_bytes+=size
                s=channel_summary[cname];s["payload_records"]+=1;s["payload_bytes"]+=size
                out["sha256"]=hashlib.sha256(payload).hexdigest()
                hits=obs.identity_hits(payload,payload_map);out["exact_raven_identity_hits"]=hits
                if hits:
                    s["identity_records"]+=1;s["identity_count"]+=len(hits)
                start=0
                while True:
                    at=payload.find(funeral_needle,start)
                    if at<0:break
                    out["known_funeral_raven_offsets"].append(at)
                    known_funeral_hits.append({"record_index":i,"record_name":rec["name"],"channel":cname,"offset":at})
                    start=at+1
                decoded=dec.decode_carriers(payload,registry_hash,object_map)
                compact={
                    "stream_count":decoded["stream_count"],"carrier_header_candidates":decoded["carrier_header_candidates"],
                    "decoded_carrier_count":decoded["decoded_carrier_count"],"carriers_with_subobjs":decoded["carriers_with_subobjs"],
                    "raven_entry_count":decoded["raven_entry_count"],"killed_raven_count":decoded["killed_raven_count"],
                    "killed_raven_catalogue_ids":decoded["killed_raven_catalogue_ids"],
                    "explicit_false_raven_catalogue_ids":decoded["explicit_false_raven_catalogue_ids"],
                    "raven_entries":decoded["raven_entries"],
                }
                out["decoded"]=compact
                if compact["raven_entry_count"]:
                    s["decoded_records"]+=1;s["decoded_entries"]+=compact["raven_entry_count"]
                    s["killed_ids"].update(compact["killed_raven_catalogue_ids"]);s["false_ids"].update(compact["explicit_false_raven_catalogue_ids"])
                    for e in compact["raven_entries"]:
                        st=e.get("ravenKilled")
                        if st is not None: state_by_id[e["catalogue_id"]].add(bool(st))
                rec["channels"][cname]=out
            records.append(rec)
    finally:
        obs.close(k,p)

    conflicts=sorted(rid for rid,states in state_by_id.items() if len(states)>1)
    exact_states=[]
    for rid in sorted(state_by_id):
        states=state_by_id[rid];m=meta[rid]
        exact_states.append({"catalogue_id":rid,"ravenKilled":next(iter(states)) if len(states)==1 else None,
                             "conflict":len(states)>1,"wad":m.get("wad"),"realm":m.get("realm"),"region":m.get("region")})
    summary={}
    for n,s in channel_summary.items():
        summary[n]={k:(sorted(v) if isinstance(v,set) else v) for k,v in s.items()}

    report={
        "schema":1,"captured_utc":datetime.now(timezone.utc).isoformat(),"analysis":"staged_wad_dual_payload_raven_state_readonly",
        "process":{"pid":pid,"module_base":f"0x{base:X}","exe_sha256":sha},
        "layout":{"record_count":count,"record_base_rva":f"0x{obs.RECORD_BASE_RVA:X}","record_stride":obs.RECORD_STRIDE,
                  "pool_base":f"0x{pool_base:X}","pool_size":pool_size,
                  "channels":{n:{k:(f"0x{v:X}" if k.endswith("_off") else v) for k,v in c.items()} for n,c in CHANNELS.items()}},
        "total_payload_bytes_read":total_bytes,"known_funeral_raven_payload_hex":KNOWN_FUNERAL_RAVEN,
        "known_funeral_raven_hits":known_funeral_hits,"channel_summary":summary,
        "decoded_exact_states":exact_states,"decoded_exact_state_count":len(exact_states),"conflicting_catalogue_ids":conflicts,
        "records":records,
        "safety":{"open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION","process_memory_written":False,
                  "debugger_attached":False,"remote_game_code_called":False,"active_save_opened":False,
                  "save_written":False,"progression_written":False,"game_files_written":False},
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=["Completionist Map - staged WAD dual payload Raven state capture",
       f"record_count={count} pool_base=0x{pool_base:X} pool_size={pool_size} total_payload_bytes_read={total_bytes}",
       f"known_funeral_raven_hits={len(known_funeral_hits)} decoded_exact_state_count={len(exact_states)} conflicts={len(conflicts)}",""]
    for n,s in summary.items():
        L += [f"CHANNEL {n}",
              f"  payload_records={s['payload_records']} payload_bytes={s['payload_bytes']}",
              f"  identity_records={s['identity_records']} identity_count={s['identity_count']}",
              f"  decoded_records={s['decoded_records']} decoded_entries={s['decoded_entries']}",
              f"  killed_count={len(s['killed_ids'])} explicit_false_count={len(s['false_ids'])}"]
    L += ["","KNOWN FUNERAL RAVEN HITS"]
    for h in known_funeral_hits:L.append(f"  record={h['record_index']} name={h['record_name']!r} channel={h['channel']} offset={h['offset']}")
    L += ["","DECODED EXACT STATES"]
    for e in exact_states:L.append(f"  id={e['catalogue_id']} ravenKilled={e['ravenKilled']} conflict={str(e['conflict']).lower()} realm={e['realm']} region={e['region']} wad={e['wad']}")
    L += ["","RECORDS WITH RAVEN EVIDENCE"]
    for rec in records:
        for n,ch in rec["channels"].items():
            d=ch.get("decoded")
            if ch["exact_raven_identity_hits"] or ch["known_funeral_raven_offsets"] or (d and d["raven_entry_count"]):
                L.append(f"  idx={rec['index']} name={rec['name']!r} channel={n} size={ch['size']} identities={len(ch['exact_raven_identity_hits'])} decoded={d['raven_entry_count'] if d else 0}")
                for h in ch["exact_raven_identity_hits"]:L.append(f"    ID {h['catalogue_id']} off={h['offset']}")
                if d:
                    for e in d["raven_entries"]:L.append(f"    STATE {e['catalogue_id']} ravenKilled={e.get('ravenKilled')}")
    L += ["","SAFETY process_memory_written=false active_save_opened=false save_written=false progression_written=false"]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"STAGED_WAD_DUAL_PAYLOAD_RAVEN_CAPTURE_COMPLETE records={count} funeralHits={len(known_funeral_hits)} decodedStates={len(exact_states)} conflicts={len(conflicts)}")
    print("process_memory_written=false active_save_opened=false save_written=false progression_written=false")
    return 0

if __name__=="__main__":raise SystemExit(main())
