#!/usr/bin/env python3
"""Read-only alternate Raven identity representation probe for active game.sav.

Searches all 53 proven Raven identities in representations that may survive after
the exact 17-byte custom-userdata carrier form is gone:
- object_hash as little- and big-endian u64;
- each 16-byte exact GameObject identity-vector element;
- transformed leaf identity;
- instance GUID in RFC/raw hex order and Windows GUID memory order;
- source record IDs backing each transformed identity element.

Search scope:
- entire raw game.sav;
- every validated zlib stream in each of the 20 aligned ring slots.

No state inference is made here. This is presence evidence only.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, uuid, zlib
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
IDENTITIES=REPO/"catalogue"/"odins-ravens-save-identities.json"
MAX_DECOMPRESSED=8*1024*1024
INPUT_LIMIT=2*1024*1024

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()

def layout(blob:bytes):
    if len(blob)<32: raise RuntimeError("save too short")
    w=struct.unpack_from("<8I",blob,0)
    stride=int(w[5]); declared=int(w[6])
    if declared!=len(blob): raise RuntimeError("declared file size mismatch")
    prefix=len(blob)%stride
    count=(len(blob)-prefix)//stride
    if count!=20: raise RuntimeError(f"expected 20 slots, got {count}")
    return prefix,stride,count

def valid_zlib(data:bytes,off:int)->bool:
    if off+1>=len(data): return False
    cmf,flg=data[off],data[off+1]
    return (cmf&0x0f)==8 and (cmf>>4)<=7 and (((cmf<<8)|flg)%31)==0

def dec(data:bytes,off:int):
    if not valid_zlib(data,off): return None
    src=data[off:min(len(data),off+INPUT_LIMIT)]
    try:
        o=zlib.decompressobj()
        raw=o.decompress(src,MAX_DECOMPRESSED+1)
        if len(raw)>MAX_DECOMPRESSED or not o.eof or not raw: return None
        used=len(src)-len(o.unused_data)
        return (raw,used) if used>2 else None
    except zlib.error:
        return None

def guid_orders(text:str):
    u=uuid.UUID(text)
    return {
        "instance_guid_rfc":u.bytes,
        "instance_guid_windows":u.bytes_le,
    }

def build_needles(doc:dict):
    by_bytes=defaultdict(list)
    for row in doc["identities"]:
        cid=row["catalogue_id"]
        oh=int(row["object_hash_hex"],16)
        forms={
            "object_hash_le":oh.to_bytes(8,"little"),
            "object_hash_be":oh.to_bytes(8,"big"),
        }
        forms.update(guid_orders(row["instance_guid"]))
        for i,h in enumerate(row["identity_elements_hex"]):
            forms[f"identity_element_{i}"]=bytes.fromhex(h)
        if row["identity_elements_hex"]:
            forms["identity_leaf"]=bytes.fromhex(row["identity_elements_hex"][-2] if len(row["identity_elements_hex"])>=2 else row["identity_elements_hex"][-1])
            forms["prototype_identity"]=bytes.fromhex(row["identity_elements_hex"][-1])
        for i,item in enumerate(row.get("transform_identity_elements",[])):
            rid=item.get("source_record_id")
            if isinstance(rid,str) and len(rid)==32:
                forms[f"source_record_id_{i}"]=bytes.fromhex(rid)
        for kind,needle in forms.items():
            by_bytes[needle].append((cid,kind))
    return by_bytes

def hit_map(raw:bytes, needles):
    hits=[]
    for needle,labels in needles.items():
        count=raw.count(needle)
        if not count: continue
        for cid,kind in labels:
            hits.append({"catalogue_id":cid,"kind":kind,"count":count,"needle_bytes":len(needle)})
    return hits

def summarize(hits):
    ids=sorted(set(h["catalogue_id"] for h in hits))
    kinds=defaultdict(set)
    for h in hits: kinds[h["kind"]].add(h["catalogue_id"])
    return {
        "unique_raven_count":len(ids),
        "catalogue_ids":ids,
        "representation_counts":{k:len(v) for k,v in sorted(kinds.items())},
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-root",type=Path,default=Path.home()/"Saved Games"/"God of War")
    ap.add_argument("--identities",type=Path,default=IDENTITIES)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()

    root=a.save_root.expanduser().resolve()
    saves=sorted(p.resolve() for p in root.rglob("game.sav") if p.is_file())
    if len(saves)!=1: raise RuntimeError(f"expected one active game.sav, found {len(saves)}")
    save=saves[0]
    before=sha256_file(save)
    blob=save.read_bytes()
    ids=json.loads(a.identities.read_text(encoding="utf-8"))
    if ids.get("identity_count")!=53: raise RuntimeError("identity catalogue incomplete")
    needles=build_needles(ids)

    raw_hits=hit_map(blob,needles)
    prefix,stride,count=layout(blob)
    slots=[]
    union_hits=[]
    for i in range(count):
        slot=blob[prefix+i*stride:prefix+(i+1)*stride]
        slot_raw=hit_map(slot,needles)
        stream_rows=[]
        cursor=0
        while True:
            at=slot.find(b"\x78",cursor)
            if at<0: break
            cursor=at+1
            got=dec(slot,at)
            if got is None: continue
            raw,used=got
            hs=hit_map(raw,needles)
            if hs:
                stream_rows.append({
                    "offset":at,
                    "compressed_bytes":used,
                    "summary":summarize(hs),
                    "hits":hs,
                })
                union_hits.extend(hs)
        union_hits.extend(slot_raw)
        if slot_raw or stream_rows:
            slots.append({
                "slot":i,
                "raw_summary":summarize(slot_raw),
                "raw_hits":slot_raw,
                "stream_rows":stream_rows,
            })

    union_hits.extend(raw_hits)
    after=sha256_file(save)
    if before!=after: raise RuntimeError("active save changed during read-only probe")

    report={
        "schema":1,
        "analysis":"active_save_alternate_raven_identity_representations",
        "save_sha256":before,
        "identity_catalogue_sha256":sha256_file(a.identities),
        "raw_save_summary":summarize(raw_hits),
        "raw_save_hits":raw_hits,
        "union_summary":summarize(union_hits),
        "slots_with_hits":slots,
        "safety":{
            "active_save_opened_read_only":True,
            "source_hash_unchanged":True,
            "save_written":False,
            "progression_written":False,
            "game_process_opened":False,
        },
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    u=report["union_summary"]
    print(f"RAVEN_ALT_IDENTITY_PRESENCE_COMPLETE union={u['unique_raven_count']}")
    print("representations="+",".join(f"{k}:{v}" for k,v in u["representation_counts"].items()))
    for row in slots:
        ids_here=set(row["raw_summary"]["catalogue_ids"])
        for s in row["stream_rows"]: ids_here.update(s["summary"]["catalogue_ids"])
        print(f"slot={row['slot']} identities={len(ids_here)}")
    print("source_hash_unchanged=true save_written=false progression_written=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
