#!/usr/bin/env python3
"""Search authoritative Raven quest-record captures for exact Raven identities.

Post-processing only: no game/process/save access. Searches the latest raw
authoritative quest-record pointer graph for every exact known Raven identity
representation:
- 64-bit object hash (little/big endian)
- 17-byte serialized GameObject payload
- instance GUID (RFC bytes and Windows bytes_le)
- each 16-byte identity-vector element
- full concatenated identity vector

Hits are grouped by RegionSummary parent and Raven catalogue id.
"""
from __future__ import annotations
import argparse, json, struct, uuid
from collections import defaultdict
from pathlib import Path

def iter_blobs(record):
    yield ("value", record.get("value_hex"))
    yield ("definition", record.get("definition_hex"))
    stack=[]
    for origin in ("value_pointer_targets","definition_pointer_targets"):
        for t in record.get(origin,[]) or []:
            stack.append((origin,1,t))
    while stack:
        origin,depth,t=stack.pop()
        label=f"{origin}/d{depth}/src={t.get('source_offset_hex')}/addr={t.get('address_hex')}"
        yield (label,t.get("hex"))
        for c in t.get("pointer_targets",[]) or []:
            stack.append((origin,depth+1,c))

def needles(identity):
    out=[]
    h=int(identity["object_hash_hex"],16)
    out.append(("object_hash_le",struct.pack("<Q",h)))
    out.append(("object_hash_be",struct.pack(">Q",h)))
    payload=bytes.fromhex(identity["serialized_payload_hex"])
    out.append(("serialized_payload",payload))
    g=uuid.UUID(identity["instance_guid"])
    out.append(("instance_guid_bytes",g.bytes))
    out.append(("instance_guid_bytes_le",g.bytes_le))
    elems=[bytes.fromhex(x) for x in identity.get("identity_elements_hex",[])]
    for i,e in enumerate(elems):
        out.append((f"identity_element_{i}",e))
    if elems:
        out.append(("identity_vector_concat",b"".join(elems)))
        out.append(("identity_vector_concat_reversed",b"".join(reversed(elems))))
    # remove duplicate byte needles while retaining strongest label
    seen=set(); uniq=[]
    for label,b in out:
        if not b or b in seen: continue
        seen.add(b); uniq.append((label,b))
    return uniq

def find_all(hay,needle):
    pos=0
    while True:
        i=hay.find(needle,pos)
        if i<0:return
        yield i
        pos=i+1

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--quest-report",type=Path,required=True)
    ap.add_argument("--identities",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    report=json.loads(args.quest_report.read_text(encoding="utf-8"))
    ids=json.loads(args.identities.read_text(encoding="utf-8"))["identities"]

    raven_needles={}
    meta={}
    for ident in ids:
        cid=ident["catalogue_id"]
        raven_needles[cid]=needles(ident)
        meta[cid]={
          "catalogue_id":cid,"region":ident.get("region"),"realm":ident.get("realm"),
          "wad":ident.get("wad"),"object_hash_hex":ident["object_hash_hex"],
          "instance_guid":ident["instance_guid"],
        }

    hits=[]
    region_hits=defaultdict(set)
    representation_counts=defaultdict(int)
    searched_blobs=0; searched_bytes=0
    for parent,record in report["records"].items():
        for label,hx in iter_blobs(record):
            if not hx: continue
            try: hay=bytes.fromhex(hx)
            except Exception: continue
            searched_blobs+=1; searched_bytes+=len(hay)
            for cid,ns in raven_needles.items():
                for repr_name,needle in ns:
                    for off in find_all(hay,needle):
                        hits.append({
                          "parent":parent,"blob":label,"offset":off,"offset_hex":f"0x{off:X}",
                          "catalogue_id":cid,"representation":repr_name,
                          **meta[cid],
                        })
                        region_hits[parent].add(cid)
                        representation_counts[repr_name]+=1

    # Collapse repeated representations of the same Raven at the same logical blob.
    grouped=defaultdict(lambda:{"representations":set(),"offsets":set()})
    for h in hits:
        k=(h["parent"],h["blob"],h["catalogue_id"])
        grouped[k]["representations"].add(h["representation"])
        grouped[k]["offsets"].add(h["offset_hex"])
    collapsed=[]
    for (parent,blob,cid),v in grouped.items():
        collapsed.append({
          "parent":parent,"blob":blob,"catalogue_id":cid,
          "region":meta[cid]["region"],"realm":meta[cid]["realm"],"wad":meta[cid]["wad"],
          "object_hash_hex":meta[cid]["object_hash_hex"],
          "representations":sorted(v["representations"]),
          "offsets":sorted(v["offsets"]),
        })
    collapsed.sort(key=lambda x:(x["parent"],x["blob"],x["catalogue_id"]))

    out={
      "schema":1,
      "analysis":"exact_raven_identity_search_in_authoritative_quest_graph",
      "source_quest_report":str(args.quest_report),
      "source_identity_catalogue":str(args.identities),
      "raven_identity_count":len(ids),
      "searched_blobs":searched_blobs,
      "searched_bytes":searched_bytes,
      "raw_hit_count":len(hits),
      "collapsed_hit_count":len(collapsed),
      "representation_counts":dict(sorted(representation_counts.items())),
      "parents_with_hits":{k:sorted(v) for k,v in sorted(region_hits.items())},
      "hits":collapsed,
      "interpretation":(
        "Any exact Raven identity hit reachable from a RegionSummary record is a direct candidate "
        "for the missing per-instance contributor mapping. Zero hits proves this bounded two-hop "
        "QuestManager graph does not embed any of the solved Raven identity representations."
      ),
      "safety":{"postprocess_only":True,"game_launched":False,"process_opened":False,
                "save_or_progression_written":False},
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"RAVEN_IDENTITY_QUEST_GRAPH_SEARCH_COMPLETE ravens={len(ids)} blobs={searched_blobs} bytes={searched_bytes} rawHits={len(hits)} collapsedHits={len(collapsed)}")
    for parent,cids in sorted(region_hits.items()):
        print(f"PARENT_HITS {parent} count={len(cids)} ids={','.join(sorted(cids))}")
    for h in collapsed[:100]:
        print(f"HIT parent={h['parent']} raven={h['catalogue_id']} repr={','.join(h['representations'])} blob={h['blob']} offsets={','.join(h['offsets'])}")
    print("game_launched=false process_opened=false save_or_progression_written=false")

if __name__=="__main__": raise SystemExit(main())
