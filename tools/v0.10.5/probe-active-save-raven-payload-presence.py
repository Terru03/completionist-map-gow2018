#!/usr/bin/env python3
"""Read-only exact Raven payload presence probe for active game.sav.

Searches all 53 proven serialized Raven GameObject payloads:
- in the raw save;
- per aligned ring slot;
- inside every validated zlib stream of each slot.

This deliberately does not infer killed/alive state. It only establishes whether
the exact persistent identities are present outside the narrow ravenKilled carrier
filter used by the previous authority probe.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, zlib
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
    w=struct.unpack_from("<8I",blob,0)
    stride=w[5]; prefix=len(blob)%stride; count=(len(blob)-prefix)//stride
    if w[6]!=len(blob) or count!=20: raise RuntimeError("unsupported game.sav layout")
    return prefix,stride,count

def valid_zlib(data:bytes,off:int)->bool:
    if off+1>=len(data): return False
    cmf,flg=data[off],data[off+1]
    return (cmf&0x0f)==8 and (cmf>>4)<=7 and (((cmf<<8)|flg)%31)==0

def dec(data:bytes,off:int):
    if not valid_zlib(data,off): return None
    src=data[off:min(len(data),off+INPUT_LIMIT)]
    try:
        o=zlib.decompressobj(); raw=o.decompress(src,MAX_DECOMPRESSED+1)
        if not o.eof or not raw or len(raw)>MAX_DECOMPRESSED: return None
        used=len(src)-len(o.unused_data)
        return (raw,used) if used>2 else None
    except zlib.error: return None

def matches(raw:bytes,payloads:dict[bytes,str]):
    out=[]
    for payload,cid in payloads.items():
        n=raw.count(payload)
        if n: out.append({"catalogue_id":cid,"count":n})
    return sorted(out,key=lambda x:x["catalogue_id"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--save-root",type=Path,default=Path.home()/"Saved Games"/"God of War")
    ap.add_argument("--identities",type=Path,default=IDENTITIES)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    saves=sorted(p.resolve() for p in a.save_root.expanduser().resolve().rglob("game.sav") if p.is_file())
    if len(saves)!=1: raise RuntimeError(f"expected one active game.sav, found {len(saves)}")
    save=saves[0]; before=sha256_file(save); blob=save.read_bytes()
    ids=json.loads(a.identities.read_text(encoding="utf-8"))
    payloads={bytes.fromhex(r["serialized_payload_hex"]):r["catalogue_id"] for r in ids["identities"]}
    if len(payloads)!=53: raise RuntimeError("expected 53 unique Raven payloads")
    prefix,stride,count=layout(blob)
    slots=[]
    union=set()
    for i in range(count):
        slot=blob[prefix+i*stride:prefix+(i+1)*stride]
        raw_hits=matches(slot,payloads)
        stream_hits={}
        cursor=0; stream_count=0
        while True:
            at=slot.find(b"\x78",cursor)
            if at<0: break
            cursor=at+1
            got=dec(slot,at)
            if got is None: continue
            decoded,used=got; stream_count+=1
            h=matches(decoded,payloads)
            if h:
                stream_hits[str(at)]={"compressed_bytes":used,"hits":h}
                union.update(x["catalogue_id"] for x in h)
        union.update(x["catalogue_id"] for x in raw_hits)
        slots.append({
            "slot":i,"validated_streams":stream_count,
            "raw_payload_hits":raw_hits,
            "decompressed_stream_payload_hits":stream_hits,
            "unique_raven_identities":sorted(
                set(x["catalogue_id"] for x in raw_hits) |
                {x["catalogue_id"] for row in stream_hits.values() for x in row["hits"]}
            )
        })
    after=sha256_file(save)
    if before!=after: raise RuntimeError("active save changed during read-only probe")
    out={
        "schema":1,"analysis":"active_save_exact_raven_payload_presence",
        "save_sha256":before,"layout":{"prefix":prefix,"stride":stride,"slots":count},
        "union_unique_raven_identity_count":len(union),
        "union_raven_catalogue_ids":sorted(union),
        "slots":slots,
        "safety":{"active_save_opened_read_only":True,"source_hash_unchanged":True,
                  "save_written":False,"progression_written":False}
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"RAVEN_PAYLOAD_PRESENCE_COMPLETE union={len(union)}")
    for row in slots:
        if row["unique_raven_identities"]:
            print(f"slot={row['slot']} identities={len(row['unique_raven_identities'])}")
    print("source_hash_unchanged=true save_written=false progression_written=false")
    return 0
if __name__=="__main__": raise SystemExit(main())
