#!/usr/bin/env python3
"""Resolve the six Raven prototype identity elements from shipped WAD data.

Static/read-only. No process access and no save access.

Already-proven Raven identity structure:
  runtime scene identity elements =
      reverse(catalogue.source.transform_chain)
      with byte 12 decremented by one for every 16-byte record ID.

For the known VikingFuneral Raven this exactly reproduces:
  6a40442bc7277743a15f2986a3279901
  82bdafe150a9ea49ac27331f1525d1d5
  160d2d64d4a5f04a93776e075d9a543c

The remaining element, object+0x40, is the prototype/object identity. This tool
builds a static record-reference graph around each of the six catalogue
prototype IDs and reports the candidate 16-byte record IDs that those prototype
records reference, with offsets and Raven-related record names.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

KNOWN_CATALOGUE_ID="raven_642d0d164af0a5d4076e77933c549a5d"
KNOWN_OBJECT_PLUS_40=bytes.fromhex("805b030bf339564cb157837c52906465")
KNOWN_HASH=0x98BE1707BA2D65A9
MASK64=0xFFFFFFFFFFFFFFFF

def load_catalogue_helper():
    p=Path(__file__).with_name("raven_catalogue.py")
    spec=importlib.util.spec_from_file_location("raven_catalogue_static",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def identity_record_id(record_id_hex:str)->bytes:
    raw=bytearray.fromhex(record_id_hex)
    if len(raw)!=16: raise ValueError("record id is not 16 bytes")
    raw[12]=(raw[12]-1)&0xFF
    return bytes(raw)

def scene_vector(row:dict)->list[bytes]:
    chain=row["source"]["transform_chain"]
    return [identity_record_id(item["record_id"]) for item in reversed(chain)]

def raw_identity_hash(elements:list[bytes])->int:
    value=0
    for element in elements:
        if len(element)!=16: raise ValueError("identity element is not 16 bytes")
        for byte in element:
            value=((value+byte)*0x401)&MASK64
            value^=value>>6
    return value

def find_all(data:bytes,needle:bytes):
    out=[];start=0
    while True:
        at=data.find(needle,start)
        if at<0:return out
        out.append(at);start=at+1

def record_for_offset(records:list[dict],at:int):
    for rec in records:
        hs=rec["offset"];ps=hs+96;pe=ps+rec["size"]
        if hs<=at<ps:return rec,"header",at-hs
        if ps<=at<pe:return rec,"payload",at-hs
    return None,None,None

def refs_in_record(rec:dict,record_ids:dict[bytes,list[dict]]):
    data=rec["data"];hits=[]
    for off in range(0,max(0,len(data)-15)):
        value=data[off:off+16]
        targets=record_ids.get(value)
        if not targets: continue
        hits.append({
            "payload_offset":f"0x{off:X}",
            "absolute_offset":f"0x{rec['offset']+96+off:X}",
            "value_hex":value.hex(),
            "targets":[{"name":t["name"],"offset":f"0x{t['offset']:X}","kind":t["kind"]} for t in targets[:16]],
        })
    return hits

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--game-root",type=Path,default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--catalogue",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    rc=load_catalogue_helper()
    catalogue=json.loads(a.catalogue.read_text(encoding="utf-8"))
    rows=catalogue["ravens"]
    if len(rows)!=53:raise RuntimeError(f"expected 53 Ravens, found {len(rows)}")

    prototype_groups={}
    for row in rows:
        prototype_groups.setdefault(row["native"]["prototype_id"],[]).append(row)

    wad_cache={}
    for row in rows:
        name=row["source"]["wad"]
        if name in wad_cache:continue
        p=a.game_root/"exec"/"wad"/"pc_le"/name
        raw=p.read_bytes()
        records=rc.parse_wad(raw)
        ids={}
        for rec in records:ids.setdefault(rec["id"],[]).append(rec)
        wad_cache[name]={"path":str(p),"raw":raw,"records":records,"ids":ids}

    known=next(r for r in rows if r["catalogue_id"]==KNOWN_CATALOGUE_ID)
    known_scene=scene_vector(known)
    known_expected=[
        bytes.fromhex("6a40442bc7277743a15f2986a3279901"),
        bytes.fromhex("82bdafe150a9ea49ac27331f1525d1d5"),
        bytes.fromhex("160d2d64d4a5f04a93776e075d9a543c"),
    ]
    if known_scene!=known_expected:
        raise RuntimeError("known Raven scene-vector transform no longer matches proven identity")

    groups=[]
    for prototype_id,group_rows in sorted(prototype_groups.items()):
        proto=bytes.fromhex(prototype_id)
        if len(proto)!=16:raise RuntimeError(f"bad prototype id {prototype_id}")
        wad_names=sorted({r["source"]["wad"] for r in group_rows})
        occurrences=[]
        source_records=[]
        candidate_refs=[]

        for wad_name in wad_names:
            info=wad_cache[wad_name]
            raw=info["raw"];records=info["records"];ids=info["ids"]
            for at in find_all(raw,proto):
                rec,where,rel=record_for_offset(records,at)
                occurrences.append({
                    "wad":wad_name,
                    "absolute_offset":f"0x{at:X}",
                    "where":where,
                    "record_name":rec["name"] if rec else None,
                    "record_id_hex":rec["id"].hex() if rec else None,
                    "record_offset":f"0x{rec['offset']:X}" if rec else None,
                    "relative_to_record":f"0x{rel:X}" if rel is not None else None,
                })
                if rec and rec not in source_records:source_records.append(rec)

            for rec in records:
                if rec["id"]==proto and rec not in source_records:
                    source_records.append(rec)

        for rec in source_records:
            # Need the owning WAD for this record. Recover it from occurrences or
            # by identity within each cached record list.
            owner=None
            for wad_name in wad_names:
                if any(x is rec for x in wad_cache[wad_name]["records"]):
                    owner=wad_name;break
            if owner is None:continue
            refs=refs_in_record(rec,wad_cache[owner]["ids"])
            for ref in refs:
                targets=ref["targets"]
                ravenish=("raven" in rec["name"].lower()) or any("raven" in t["name"].lower() for t in targets)
                candidate_refs.append({
                    "wad":owner,
                    "source_record_name":rec["name"],
                    "source_record_id_hex":rec["id"].hex(),
                    "source_record_offset":f"0x{rec['offset']:X}",
                    "raven_related":ravenish,
                    **ref,
                })

        unique_candidates={}
        for ref in candidate_refs:
            key=ref["value_hex"]
            item=unique_candidates.setdefault(key,{
                "value_hex":key,"hits":0,"raven_related_hits":0,"examples":[]
            })
            item["hits"]+=1
            if ref["raven_related"]:item["raven_related_hits"]+=1
            if len(item["examples"])<12:item["examples"].append(ref)
        ranked=sorted(unique_candidates.values(),key=lambda x:(-x["raven_related_hits"],-x["hits"],x["value_hex"]))

        groups.append({
            "prototype_id":prototype_id,
            "catalogue_count":len(group_rows),
            "catalogue_ids":[r["catalogue_id"] for r in group_rows],
            "wads":wad_names,
            "prototype_occurrences":occurrences,
            "candidate_referenced_record_ids":ranked[:64],
        })

    # Show exact static hash reconstruction for the known Raven as a hard proof.
    known_vector=known_scene+[KNOWN_OBJECT_PLUS_40]
    known_hash=raw_identity_hash(known_vector)
    if known_hash!=KNOWN_HASH:
        raise RuntimeError(f"known Raven static hash mismatch 0x{known_hash:016X}")

    report={
        "schema":1,
        "analysis":"raven_prototype_identity_static_resolution",
        "catalogue_entries":len(rows),
        "unique_prototypes":len(prototype_groups),
        "known_raven":{
            "catalogue_id":KNOWN_CATALOGUE_ID,
            "scene_elements_hex":[x.hex() for x in known_scene],
            "object_plus_40_hex":KNOWN_OBJECT_PLUS_40.hex(),
            "reconstructed_object_hash_hex":f"0x{known_hash:016X}",
            "expected_object_hash_hex":f"0x{KNOWN_HASH:016X}",
            "exact_match":known_hash==KNOWN_HASH,
        },
        "prototype_groups":groups,
        "safety":{
            "static_game_files_read_only":True,
            "process_accessed":False,
            "active_save_opened":False,
            "save_or_progression_written":False,
            "game_files_written":False,
        },
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - Raven prototype identity static resolution",
        f"catalogue_entries={len(rows)} unique_prototypes={len(prototype_groups)}",
        f"known_raven_hash=0x{known_hash:016X} exact_match={known_hash==KNOWN_HASH}",
        "",
    ]
    for g in groups:
        lines.append(f"PROTOTYPE {g['prototype_id']} ravens={g['catalogue_count']} wads={len(g['wads'])}")
        lines.append(f"  occurrences={len(g['prototype_occurrences'])}")
        for occ in g["prototype_occurrences"][:20]:
            lines.append(
                f"    {occ['wad']} {occ['record_name']} id={occ['record_id_hex']} "
                f"where={occ['where']} rel={occ['relative_to_record']} abs={occ['absolute_offset']}"
            )
        lines.append("  candidate referenced record IDs:")
        for cand in g["candidate_referenced_record_ids"][:20]:
            lines.append(
                f"    {cand['value_hex']} hits={cand['hits']} raven_related={cand['raven_related_hits']}"
            )
            for ex in cand["examples"][:3]:
                names=",".join(t["name"] for t in ex["targets"])
                lines.append(
                    f"      {ex['wad']} {ex['source_record_name']} +{ex['payload_offset']} -> {names}"
                )
        lines.append("")

    lines += [
        "SAFETY",
        "static_game_files_read_only=true",
        "process_accessed=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
    ]
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(
        "RAVEN_PROTOTYPE_IDENTITY_STATIC_RESOLUTION_COMPLETE "
        f"prototypes={len(prototype_groups)} known_hash_exact=true"
    )
    print("process_accessed=false active_save_opened=false save_or_progression_written=false")

if __name__=="__main__":main()
