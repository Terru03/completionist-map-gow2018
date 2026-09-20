#!/usr/bin/env python3
"""Capture exact custom-userdata SubObject keys from staged WAD checkpoint records.

Read-only runtime diagnostic. Reads only the already-proven staged WAD record
array and referenced payload pool. For each valid custom-userdata carrier, it
records the custom-record class key/payload used as __subobjs keys and the
associated state-table fields.

This is intentionally narrower than a process-memory scan. It performs no
writes, debugger attach, remote calls, or save-file access.
"""
from __future__ import annotations

import argparse
import ctypes as C
import importlib.util
import json
import struct
import sys
from pathlib import Path
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
IDENTITIES=REPO/"catalogue"/"odins-ravens-save-identities.json"
OBSERVER=HERE/"capture-staged-wad-raven-state-readonly.py"
DECODER=HERE/"decode-active-raven-subobject-state.py"
CARRIER=HERE/"gow-custom-userdata-carrier.py"

KNOWN_VIKING_FUNERAL_TOKEN=0x1BB001DD
KNOWN_VIKING_FUNERAL_ID="raven_642d0d164af0a5d4076e77933c549a5d"
KNOWN_WIDTHS={0:2,1:5,2:3,3:3,5:3}

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {path}")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def choose_tokens(inspect):
    candidates=inspect.get("metadata_candidates",[])
    good=[]
    for c in candidates:
        widths={int(k):int(v) for k,v in c.get("used_tag_widths",{}).items()}
        if all(widths.get(tag,exp)==exp for tag,exp in KNOWN_WIDTHS.items() if tag in widths):
            toks=[]
            ok=True
            for t in c.get("tokens",[]):
                raw=bytes.fromhex(t["raw_hex"])
                if not raw:
                    ok=False;break
                toks.append({"tag":raw[0],"payload":int.from_bytes(raw[1:],"little"),"width":len(raw),"raw_hex":raw.hex()})
            if ok: good.append(toks)
    if not good: return None
    # Prefer exact native width candidate and then shortest deterministic encoding.
    good.sort(key=lambda ts:(sum(t["width"] for t in ts),tuple(t["raw_hex"] for t in ts)))
    return good[0]

def decode_rows(inspect,tokens,strings):
    hdr=inspect["header"]
    pair_count=hdr["metadata_pair_count"];row_count=hdr["row_count"]
    if len(tokens)!=pair_count*2:return []
    pairs=[(tokens[2*i],tokens[2*i+1]) for i in range(pair_count)]
    raw=bytes.fromhex(inspect["six_byte_rows_hex"])
    rows=[]
    for i in range(row_count):
        first,count,aux=struct.unpack_from("<HHH",raw,i*6)
        rows.append({"first_pair":first,"pair_count":count,"aux":aux})
    def s(tok):
        if tok["tag"]==2 and tok["payload"]<len(strings): return strings[tok["payload"]]
        return None
    def ti(tok):
        if tok["tag"]==3 and 1<=tok["payload"]<=len(rows): return tok["payload"]-1
        return None
    out=[]
    subrows=[]
    for ri,row in enumerate(rows):
        for key,val in pairs[row["first_pair"]:row["first_pair"]+row["pair_count"]]:
            if s(key)=="__subobjs":
                x=ti(val)
                if x is not None:subrows.append(x)
    records=inspect.get("records",[])
    for sri in sorted(set(subrows)):
        row=rows[sri]
        for key,val in pairs[row["first_pair"]:row["first_pair"]+row["pair_count"]]:
            if key["tag"]!=5 or key["payload"]>=len(records):continue
            rec=records[key["payload"]]
            state_row=ti(val)
            fields=[]
            if state_row is not None:
                rr=rows[state_row]
                for sk,sv in pairs[rr["first_pair"]:rr["first_pair"]+rr["pair_count"]]:
                    fields.append({
                        "key_string":s(sk),
                        "key_tag":sk["tag"],"key_payload":sk["payload"],"key_raw_hex":sk["raw_hex"],
                        "value_tag":sv["tag"],"value_payload":sv["payload"],"value_raw_hex":sv["raw_hex"],
                        "value_string":s(sv),
                        "value_boolean":bool(sv["payload"]) if sv["tag"]==0 and sv["payload"] in (0,1) else None,
                    })
            ph=rec.get("payload_hex") if rec.get("valid") else None
            pb=bytes.fromhex(ph) if ph else b""
            out.append({
                "subobj_row":sri,
                "record_index":key["payload"],
                "record_class_key":rec.get("class_key"),
                "record_payload_length":len(pb),
                "record_payload_hex":ph,
                "payload_u32_le":struct.unpack("<I",pb)[0] if len(pb)==4 else None,
                "matches_known_viking_funeral_token":len(pb)==4 and struct.unpack("<I",pb)[0]==KNOWN_VIKING_FUNERAL_TOKEN,
                "state_row":state_row,
                "state_fields":fields,
            })
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    if sys.platform!="win32" or C.sizeof(C.c_void_p)!=8: raise RuntimeError("64-bit Windows required")

    obs=load_module("staged_obs",OBSERVER)
    dec=load_module("staged_dec",DECODER)
    car=load_module("staged_carrier",CARRIER)
    ids=json.loads(IDENTITIES.read_text(encoding="utf-8"))
    idrows=ids["identities"]
    registry_hash=int(idrows[0]["registry_hash_hex"],16)
    object_map={int(x["object_hash_hex"],16):x["catalogue_id"] for x in idrows}

    k=obs.k32_api();pid,name=obs.find_process(k);base,exe=obs.main_module(k,pid,name)
    sha=obs.sha256_file(Path(exe)).lower()
    if sha!=obs.EXE_SHA: raise RuntimeError(f"unsupported GoW.exe SHA-256: {sha}")
    p=k.OpenProcess(obs.PROCESS_VM_READ|obs.PROCESS_QUERY_INFORMATION,False,pid)
    if not p: raise obs.winerr("OpenProcess read-only failed")

    carriers=[];total_subobjs=0;known_hits=[]
    try:
        pool_size=obs.u32(obs.read(k,p,base+obs.PAYLOAD_SIZE_RVA,4))
        pool_base=obs.u64(obs.read(k,p,base+obs.PAYLOAD_BASE_RVA,8))
        count=obs.u32(obs.read(k,p,base+obs.RECORD_COUNT_RVA,4))
        if count>obs.MAX_RECORDS: raise RuntimeError(f"implausible record count {count}")
        if pool_size>obs.MAX_POOL_SIZE: raise RuntimeError(f"implausible pool size {pool_size}")
        pool_end=pool_base+pool_size

        for i in range(count):
            addr=base+obs.RECORD_BASE_RVA+i*obs.RECORD_STRIDE
            rr=obs.read(k,p,addr,obs.RECORD_STRIDE)
            name_text=obs.printable_name(rr[obs.RECORD_NAME_OFF:obs.RECORD_NAME_OFF+obs.RECORD_NAME_SIZE])
            key=obs.u32(rr,obs.RECORD_KEY_OFF)
            pa=obs.u64(rr,obs.RECORD_PAYLOAD_A_OFF)
            size=obs.u32(rr,obs.RECORD_PAYLOAD_SIZE_OFF)
            if size<=0 or size>obs.MAX_RECORD_PAYLOAD:continue
            if not(pool_size>0 and pa>=pool_base and pa+size>=pa and pa+size<=pool_end):continue
            payload=obs.read(k,p,pa,size)
            decoded=dec.decode_carriers(payload,registry_hash,object_map)
            for ci,c in enumerate(decoded.get("carriers",[])):
                start=c["carrier_offset"];end=c["carrier_end"]
                if not(0<=start<end<=len(payload)):continue
                raw=payload[start:end]
                inspect=car.inspect_carrier(raw,256)
                tokens=choose_tokens(inspect)
                if tokens is None:continue
                subobjs=decode_rows(inspect,tokens,c.get("strings",[]))
                if not subobjs:continue
                total_subobjs+=len(subobjs)
                for s in subobjs:
                    if s["matches_known_viking_funeral_token"]:
                        known_hits.append({"record_index":i,"record_name":name_text,"carrier_index":ci,**s})
                carriers.append({
                    "staged_record_index":i,
                    "staged_key_u32":key,
                    "staged_name":name_text,
                    "staged_payload_size":size,
                    "carrier_index":ci,
                    "carrier_offset":start,
                    "carrier_length":end-start,
                    "strings":c.get("strings",[]),
                    "header":c.get("header"),
                    "subobj_table_rows":c.get("subobj_table_rows",[]),
                    "subobjects":subobjs,
                })
    finally:
        obs.close(k,p)

    report={
        "schema":1,
        "captured_utc":datetime.now(timezone.utc).isoformat(),
        "analysis":"staged_wad_subobject_keys_readonly",
        "process":{"pid":pid,"module_base":f"0x{base:X}","exe_sha256":sha},
        "record_count":count,
        "pool_base":f"0x{pool_base:X}",
        "pool_size":pool_size,
        "carrier_count":len(carriers),
        "subobject_count":total_subobjs,
        "known_viking_funeral_token_hex":f"0x{KNOWN_VIKING_FUNERAL_TOKEN:08X}",
        "known_viking_funeral_catalogue_id":KNOWN_VIKING_FUNERAL_ID,
        "known_token_hits":known_hits,
        "carriers":carriers,
        "safety":{
            "open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "process_memory_written":False,"debugger_attached":False,
            "remote_game_code_called":False,"active_save_opened":False,
            "save_written":False,"progression_written":False,"game_files_written":False,
        },
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=[
        "Completionist Map - staged WAD SubObject key capture",
        f"record_count={count} carrier_count={len(carriers)} subobject_count={total_subobjs}",
        f"known_viking_funeral_token=0x{KNOWN_VIKING_FUNERAL_TOKEN:08X}",
        f"known_token_hits={len(known_hits)}","",
        "CARRIERS",
    ]
    for c in carriers:
        L.append(f"  record={c['staged_record_index']} name={c['staged_name']!r} key=0x{c['staged_key_u32']:08X} size={c['staged_payload_size']} subobjs={len(c['subobjects'])}")
        for s in c["subobjects"]:
            L.append(
                f"    SUBOBJ class={s['record_class_key']} payloadLen={s['record_payload_length']} "
                f"payload={s['record_payload_hex']} u32={('0x%08X'%s['payload_u32_le']) if s['payload_u32_le'] is not None else 'n/a'} "
                f"knownViking={str(s['matches_known_viking_funeral_token']).lower()} stateRow={s['state_row']}"
            )
            for fld in s["state_fields"]:
                if fld["key_string"] is not None or fld["value_boolean"] is not None:
                    L.append(f"      FIELD key={fld['key_string']!r} valueTag={fld['value_tag']} value={fld['value_payload']} bool={fld['value_boolean']}")
    L += ["","KNOWN VIKING FUNERAL TOKEN HITS"]
    for h in known_hits:
        L.append(f"  record={h['record_index']} name={h['record_name']!r} payload={h['record_payload_hex']} stateRow={h['state_row']}")
    L += ["","SAFETY process_memory_written=false active_save_opened=false save_written=false progression_written=false"]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"STAGED_WAD_SUBOBJECT_KEYS_COMPLETE carriers={len(carriers)} subobjects={total_subobjs} knownTokenHits={len(known_hits)}")
    print("process_memory_written=false active_save_opened=false save_written=false progression_written=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
