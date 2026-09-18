#!/usr/bin/env python3
"""Summarize an existing authoritative Raven quest-record capture.

No game/process access. Reads the latest raven-authoritative-quest-records
report and emits a compact correlation report focused on candidate contributor
containers: pointer targets whose scalar fields correlate with region goal or
progress, repeated layouts across parents, and small 0/1-like arrays.
"""
from __future__ import annotations
import argparse, json, math, os, re, statistics
from collections import defaultdict, Counter
from pathlib import Path

def i32_from_hex(h,off):
    b=bytes.fromhex(h)
    if off+4>len(b): return None
    return int.from_bytes(b[off:off+4],"little",signed=True)

def q64_from_hex(h,off):
    b=bytes.fromhex(h)
    if off+8>len(b): return None
    return int.from_bytes(b[off:off+8],"little",signed=False)

def small_binary_runs(h):
    b=bytes.fromhex(h)
    out=[]
    for width in (1,2,4,8):
        vals=[]
        for off in range(0,len(b)-width+1,width):
            v=int.from_bytes(b[off:off+width],"little")
            vals.append(v)
        best=[]
        start=None
        for i,v in enumerate(vals):
            if v in (0,1):
                if start is None:start=i
            else:
                if start is not None and i-start>=2: best.append((start,i,vals[start:i]))
                start=None
        if start is not None and len(vals)-start>=2: best.append((start,len(vals),vals[start:]))
        for s,e,vs in best:
            out.append({"width":width,"offset":s*width,"count":e-s,"values":vs})
    return out

def walk_targets(row):
    stack=[]
    for origin in ("value_pointer_targets","definition_pointer_targets"):
        for t in row.get(origin,[]) or []:
            stack.append((origin,1,t))
    out=[]
    while stack:
        origin,depth,t=stack.pop()
        out.append((origin,depth,t))
        for c in t.get("pointer_targets",[]) or []:
            stack.append((origin,depth+1,c))
    return out

def fingerprint_target(t):
    # layout fingerprint based on offsets of pointer-like qwords and small scalar offsets,
    # independent of absolute addresses/values.
    sc=t.get("scalars",{})
    ptrs=tuple(x["offset_hex"] for x in sc.get("qwords",[]) if x.get("pointer_like"))
    small=tuple(x["offset_hex"] for x in sc.get("small_dwords",[]))
    return {"ptr_offsets":ptrs,"small_offsets":small}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    data=json.loads(args.input.read_text(encoding="utf-8"))
    records=data["records"]

    candidates=[]
    fp_groups=defaultdict(list)
    per_region={}
    for name,row in records.items():
        if not row.get("found"): continue
        prog=row["expected_progress"]; goal=row["expected_goal"]
        reg={"progress":prog,"goal":goal,"targets":[]}
        for origin,depth,t in walk_targets(row):
            h=t.get("hex","")
            if not h: continue
            sc=t.get("scalars",{})
            hits=[]
            for d in sc.get("small_dwords",[]) or []:
                v=d["i32"]
                flags=[]
                if v==prog: flags.append("progress")
                if v==goal: flags.append("goal")
                if 0<=v<=max(goal,8): flags.append("small")
                if flags:
                    hits.append({"offset":d["offset_hex"],"value":v,"flags":flags})
            runs=[r for r in small_binary_runs(h) if r["count"]<=max(goal+4,12)]
            fp=fingerprint_target(t)
            fpkey=json.dumps(fp,sort_keys=True)
            item={
                "region":name,"origin":origin,"depth":depth,
                "source_offset":t.get("source_offset_hex"),
                "address":t.get("address_hex"),
                "fingerprint":fp,
                "scalar_hits":hits,
                "binary_runs":runs[:40],
            }
            reg["targets"].append(item)
            fp_groups[fpkey].append(item)
            if hits or runs:
                candidates.append(item)
        per_region[name]=reg

    repeated=[]
    for fpkey,items in fp_groups.items():
        regions=sorted(set(x["region"] for x in items))
        if len(regions)>=3:
            repeated.append({
                "region_count":len(regions),
                "regions":regions,
                "fingerprint":json.loads(fpkey),
                "examples":[{k:x.get(k) for k in ("region","origin","depth","source_offset","address")} for x in items[:12]],
            })
    repeated.sort(key=lambda x:(-x["region_count"],len(x["fingerprint"]["ptr_offsets"])+len(x["fingerprint"]["small_offsets"])))

    # Cross-region correlations: for every target position identified by origin/depth/source_offset
    # and scalar offset, measure exact matches to progress/goal.
    corr=defaultdict(lambda:{"records":0,"progress_matches":0,"goal_matches":0,"values":[],"regions":[]})
    for name,row in records.items():
        if not row.get("found"): continue
        prog=row["expected_progress"]; goal=row["expected_goal"]
        for origin,depth,t in walk_targets(row):
            src=t.get("source_offset_hex")
            for d in (t.get("scalars",{}).get("small_dwords",[]) or []):
                key=(origin,depth,src,d["offset_hex"])
                c=corr[key]; c["records"]+=1; c["values"].append(d["i32"]); c["regions"].append(name)
                if d["i32"]==prog: c["progress_matches"]+=1
                if d["i32"]==goal: c["goal_matches"]+=1
    correlations=[]
    for key,c in corr.items():
        if c["records"]<3: continue
        correlations.append({
            "origin":key[0],"depth":key[1],"source_offset":key[2],"scalar_offset":key[3],
            "records":c["records"],"progress_matches":c["progress_matches"],"goal_matches":c["goal_matches"],
            "distinct_values":sorted(set(c["values"]))[:64],
            "regions":c["regions"][:64],
        })
    correlations.sort(key=lambda x:(-(x["progress_matches"]+x["goal_matches"]),-x["records"]))

    # Region-focused candidate list for the important partial/known regions.
    focus_names=[
      "RegionSummary_VF_Raven_Parent","RegionSummary_FD_Raven_Parent",
      "RegionSummary_HSH_Raven_Parent","RegionSummary_PP_Raven_Parent",
      "RegionSummary_RP_Raven_Parent","RegionSummary_CALS_Raven_Parent",
      "RegionSummary_HEL_Raven_Parent","RegionSummary_HTTK_Raven_Parent",
    ]
    focus={}
    for n in focus_names:
        if n not in per_region: continue
        ts=[]
        for t in per_region[n]["targets"]:
            if t["scalar_hits"] or t["binary_runs"]:
                ts.append(t)
        focus[n]={"progress":per_region[n]["progress"],"goal":per_region[n]["goal"],"candidate_targets":ts[:250]}

    out={
      "schema":1,
      "source":str(args.input),
      "record_count":len(records),
      "top_correlations":correlations[:300],
      "repeated_layouts":repeated[:120],
      "focus_regions":focus,
      "candidate_target_count":len(candidates),
      "notes":[
        "This is post-processing only; no game/process/save access.",
        "A strong contributor candidate should repeat across RegionSummary parents and expose scalar/array shape tracking goal while per-element state can explain progress."
      ]
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"RAVEN_QUEST_RECORD_SUMMARY_COMPLETE candidates={len(candidates)} correlations={len(correlations)} repeatedLayouts={len(repeated)}")
    for c in correlations[:20]:
        print(f"CORR origin={c['origin']} depth={c['depth']} src={c['source_offset']} scalar={c['scalar_offset']} records={c['records']} progress={c['progress_matches']} goal={c['goal_matches']} values={c['distinct_values'][:12]}")
    return 0

if __name__=="__main__": raise SystemExit(main())
