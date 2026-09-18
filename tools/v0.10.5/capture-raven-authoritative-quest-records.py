#!/usr/bin/env python3
"""Read-only capture of authoritative Raven RegionSummary quest records.

Reproduces the proved native QuestManager lookup from 0x1EC9A0 against the
global quest table at module RVA 0x2C2C4A0. Each hash-table slot is 0x58 bytes:
  +0x00 u64 quest hash
  +0x08 .. +0x57 live quest value (0x50 bytes)

Proved getters:
  value +0x48 -> progress (GetQuestProgressAndGoal)
  value +0x10 -> static quest definition
  definition +0x30 -> goal
  definition +0x40 -> child-quest count (GetChildrenQuestIds)

The probe captures all Raven RegionSummary records, their 0x50-byte values,
their static definitions, and bounded one/two-hop pointer targets so field
correlation can identify any contributor-sized per-instance structures.
It uses PROCESS_VM_READ|PROCESS_QUERY_INFORMATION only.
"""
from __future__ import annotations
import argparse, importlib.util, json, struct, sys
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
QUEST_TABLE_RVA=0x2C2C4A0
ENTRY_STRIDE=0x58
VALUE_SIZE=0x50
MAX_BUCKETS=2_000_000
MAX_TARGET_BYTES=0x200

PARENTS={
"RegionSummary_ALF_Raven_Parent":(2,2),
"RegionSummary_BC_Raven_Parent":(2,2),
"RegionSummary_BM_Raven_Parent":(0,1),
"RegionSummary_BSW_Raven_Parent":(1,1),
"RegionSummary_BT_Raven_Parent":(1,1),
"RegionSummary_BW_Raven_Parent":(0,1),
"RegionSummary_CALS_Raven_Parent":(1,1),
"RegionSummary_FD_Raven_Parent":(4,5),
"RegionSummary_FOOT_Raven_Parent":(0,2),
"RegionSummary_FOR_Raven_Parent":(0,1),
"RegionSummary_HEL_Raven_Parent":(6,6),
"RegionSummary_HM01_Raven_Parent":(1,1),
"RegionSummary_HM02_Raven_Parent":(0,2),
"RegionSummary_HSH_Raven_Parent":(1,2),
"RegionSummary_HTTK_Raven_Parent":(0,5),
"RegionSummary_ISA_Raven_Parent":(0,1),
"RegionSummary_ISW_Raven_Parent":(1,1),
"RegionSummary_MT_Raven_Parent":(0,1),
"RegionSummary_PP_Raven_Parent":(2,4),
"RegionSummary_RP_Raven_Parent":(3,6),
"RegionSummary_SM_Raven_Parent":(0,2),
"RegionSummary_VF_Raven_Parent":(2,3),
"Quest_Labor_KillRavens":(27,51),
}

def load_helper():
    p=HERE/"read-raven-gameobject-identity-memory.py"
    spec=importlib.util.spec_from_file_location("gow_raven_qrecords",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def qhash(text:str)->int:
    v=0
    for b in text.encode("utf-8"):
        if 0x61<=b<=0x7A:b-=0x20
        v=((v+b)*0x401)&0xFFFFFFFFFFFFFFFF
        v ^= v>>6
    return v

def u64(b,o=0): return struct.unpack_from("<Q",b,o)[0]
def i32(b,o=0): return struct.unpack_from("<i",b,o)[0]
def u32(b,o=0): return struct.unpack_from("<I",b,o)[0]

def likely_ptr(v:int)->bool:
    return 0x10000 <= v <= 0x00007FFFFFFFFFFF

def safe_read(helper,k32,proc,addr,size):
    if not likely_ptr(addr): return None
    try:return helper.read_mem(k32,proc,addr,size)
    except Exception:return None

def dump_scalars(blob:bytes):
    dwords=[]
    for off in range(0,len(blob)-3,4):
        sv=i32(blob,off); uv=u32(blob,off)
        if -1024<=sv<=65535:
            dwords.append({"offset":off,"offset_hex":f"0x{off:X}","i32":sv,"u32":uv})
    qwords=[]
    for off in range(0,len(blob)-7,8):
        v=u64(blob,off)
        qwords.append({"offset":off,"offset_hex":f"0x{off:X}","value":v,"value_hex":f"0x{v:X}","pointer_like":likely_ptr(v)})
    return {"small_dwords":dwords,"qwords":qwords}

def pointer_targets(helper,k32,proc,blob:bytes,base_label:str,depth:int=1):
    out=[]
    seen=set()
    for off in range(0,len(blob)-7,8):
        ptr=u64(blob,off)
        if not likely_ptr(ptr) or ptr in seen: continue
        target=safe_read(helper,k32,proc,ptr,MAX_TARGET_BYTES)
        if target is None: continue
        seen.add(ptr)
        row={"source_offset":off,"source_offset_hex":f"0x{off:X}",
             "address":ptr,"address_hex":f"0x{ptr:X}",
             "hex":target.hex(),"scalars":dump_scalars(target)}
        if depth>1:
            row["pointer_targets"]=pointer_targets(helper,k32,proc,target,base_label+".ptr",depth-1)
        out.append(row)
    return out

def lookup(helper,k32,proc,table:int,key:int):
    hdr=helper.read_mem(k32,proc,table,0x20)
    last=u64(hdr,0x08)
    entries=u64(hdr,0x18)
    if last+1<=0 or last+1>MAX_BUCKETS or not likely_ptr(entries):
        raise RuntimeError(f"implausible quest table: last={last} entries=0x{entries:X}")
    if key==0:
        present=hdr[0x10]!=0
        return (table+0x20 if present else None),{"last_index":last,"bucket_count":last+1,"entries":entries,"zero_key_present":present}
    count=last+1
    idx=key%count; start=idx
    while True:
        slot=entries+idx*ENTRY_STRIDE
        slot_key=struct.unpack("<Q",helper.read_mem(k32,proc,slot,8))[0]
        if slot_key==key:
            return slot+8,{"last_index":last,"bucket_count":count,"entries":entries,"slot_index":idx,"slot_address":slot}
        if slot_key==0:return None,{"last_index":last,"bucket_count":count,"entries":entries,"slot_index":idx,"empty_hit":True}
        idx=0 if idx==last else idx+1
        if idx==start:return None,{"last_index":last,"bucket_count":count,"entries":entries,"wrapped":True}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if sys.platform!="win32":raise RuntimeError("Windows-only live-memory capture")
    helper=load_helper(); k32=helper.configure_kernel32()
    pid,exe_name=helper.find_supported_process(k32)
    module_base,module_size,exe_path=helper.get_main_module(k32,pid,exe_name)
    exe_sha=helper.sha256_file(exe_path)
    if exe_sha.lower()!=EXPECTED_SHA256:raise RuntimeError(f"unsupported GoW.exe SHA256 {exe_sha}")
    proc=k32.OpenProcess(helper.PROCESS_VM_READ|helper.PROCESS_QUERY_INFORMATION,False,pid)
    if not proc:raise helper.winerr("OpenProcess(read-only) failed")
    try:
        table=helper.u64(k32,proc,module_base+QUEST_TABLE_RVA)
        if not table:raise RuntimeError("quest table pointer is null")
        records={}
        correlation={}
        for name,(expected_progress,expected_goal) in PARENTS.items():
            key=qhash(name)
            value_addr,meta=lookup(helper,k32,proc,table,key)
            row={"hash":key,"hash_hex":f"0x{key:016X}","lookup":meta,
                 "expected_progress":expected_progress,"expected_goal":expected_goal,
                 "found":value_addr is not None}
            if value_addr is not None:
                value=helper.read_mem(k32,proc,value_addr,VALUE_SIZE)
                progress=i32(value,0x48)
                definition=u64(value,0x10)
                row.update({"value_address":value_addr,"value_address_hex":f"0x{value_addr:X}",
                            "value_hex":value.hex(),"value_scalars":dump_scalars(value),
                            "progress_at_0x48":progress,
                            "definition_address":definition,"definition_address_hex":f"0x{definition:X}"})
                dblob=safe_read(helper,k32,proc,definition,MAX_TARGET_BYTES)
                if dblob is not None:
                    row["definition_hex"]=dblob.hex()
                    row["definition_scalars"]=dump_scalars(dblob)
                    row["goal_at_0x30"]=i32(dblob,0x30)
                    row["child_quest_count_at_0x40"]=i32(dblob,0x40)
                    row["definition_pointer_targets"]=pointer_targets(helper,k32,proc,dblob,"definition",1)
                row["value_pointer_targets"]=pointer_targets(helper,k32,proc,value,"value",2)
            records[name]=row

        # Correlate small dword offsets in the live 0x50-byte value with known progress/goal.
        for off in range(0,VALUE_SIZE-3,4):
            vals=[]; prog_hits=0; goal_hits=0; found=0
            for name,row in records.items():
                if not row.get("found"):continue
                blob=bytes.fromhex(row["value_hex"]); v=i32(blob,off)
                found+=1; vals.append(v)
                if v==row["expected_progress"]:prog_hits+=1
                if v==row["expected_goal"]:goal_hits+=1
            correlation[f"0x{off:X}"]={"progress_matches":prog_hits,"goal_matches":goal_hits,
                                       "records":found,"distinct_values":sorted(set(vals))[:128]}
        report={"schema":1,"captured_utc":datetime.now(timezone.utc).isoformat(),
                "analysis":"authoritative_raven_region_quest_records",
                "process":{"pid":pid,"exe_name":exe_name,"exe_sha256":exe_sha,
                           "module_base":f"0x{module_base:X}","module_size":module_size},
                "quest_table":{"global_rva":f"0x{QUEST_TABLE_RVA:X}","address":f"0x{table:X}"},
                "records":records,"value_field_correlation":correlation,
                "safety":{"open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                          "remote_code_called":False,"debugger_attached":False,
                          "process_memory_written":False,"save_or_progression_written":False,
                          "game_files_written":False}}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(f"RAVEN_QUEST_RECORD_CAPTURED records={len(records)}")
        for n,r in records.items():
            print(f"{n} found={r['found']} progress={r.get('progress_at_0x48')} goal={r.get('goal_at_0x30')} childQuests={r.get('child_quest_count_at_0x40')}")
        best=sorted(correlation.items(),key=lambda kv:(kv[1]["progress_matches"],kv[1]["goal_matches"]),reverse=True)[:8]
        print("TOP_VALUE_FIELD_CORRELATIONS")
        for off,c in best:print(f"  {off}: progressMatches={c['progress_matches']} goalMatches={c['goal_matches']}")
        print("process_memory_written=false save_or_progression_written=false")
    finally:
        helper.close_handle(k32,proc)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr);raise SystemExit(1)
