#!/usr/bin/env python3
"""Read-only inventory and Raven-identity scan of the full active GoW save tree.

Unlike earlier probes that only opened game.sav, this inventories every regular file
under ~/Saved Games/God of War and scans each file for all 53 proven Raven identity
representations, both raw and inside validated zlib streams.

It never writes inside the save tree. Every scanned source file is SHA-256 verified
unchanged after the scan.
"""
from __future__ import annotations

import argparse, hashlib, json, struct, uuid, zlib
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
IDENTITIES=REPO/"catalogue"/"odins-ravens-save-identities.json"
MAX_DECOMPRESSED=16*1024*1024
INPUT_LIMIT=4*1024*1024
MAX_FILE_BYTES=512*1024*1024

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()

def guid_forms(text:str):
    u=uuid.UUID(text)
    return {"instance_guid_rfc":u.bytes,"instance_guid_windows":u.bytes_le}

def build_needles(doc:dict):
    d=defaultdict(list)
    for row in doc["identities"]:
        cid=row["catalogue_id"]
        oh=int(row["object_hash_hex"],16)
        forms={
            "serialized_payload":bytes.fromhex(row["serialized_payload_hex"]),
            "object_hash_le":oh.to_bytes(8,"little"),
            "object_hash_be":oh.to_bytes(8,"big"),
        }
        forms.update(guid_forms(row["instance_guid"]))
        for i,h in enumerate(row["identity_elements_hex"]):
            forms[f"identity_element_{i}"]=bytes.fromhex(h)
        for i,item in enumerate(row.get("transform_identity_elements",[])):
            rid=item.get("source_record_id")
            if isinstance(rid,str) and len(rid)==32:
                forms[f"source_record_id_{i}"]=bytes.fromhex(rid)
        for kind,needle in forms.items():
            d[needle].append((cid,kind))
    return d

def hits(raw:bytes,needles):
    out=[]
    for needle,labels in needles.items():
        n=raw.count(needle)
        if not n: continue
        for cid,kind in labels:
            out.append({"catalogue_id":cid,"kind":kind,"count":n})
    return out

def summarize(rows):
    ids=sorted(set(x["catalogue_id"] for x in rows))
    by=defaultdict(set)
    for x in rows: by[x["kind"]].add(x["catalogue_id"])
    return {"unique_raven_count":len(ids),"catalogue_ids":ids,
            "representation_counts":{k:len(v) for k,v in sorted(by.items())}}

def valid_zlib(data:bytes,off:int):
    if off+1>=len(data): return False
    cmf,flg=data[off],data[off+1]
    return (cmf&0x0f)==8 and (cmf>>4)<=7 and (((cmf<<8)|flg)%31)==0

def dec(data:bytes,off:int):
    if not valid_zlib(data,off): return None
    src=data[off:min(len(data),off+INPUT_LIMIT)]
    try:
        o=zlib.decompressobj()
        raw=o.decompress(src,MAX_DECOMPRESSED+1)
        if not o.eof or not raw or len(raw)>MAX_DECOMPRESSED: return None
        used=len(src)-len(o.unused_data)
        return (raw,used) if used>2 else None
    except zlib.error:
        return None

def scan_file(path:Path,root:Path,needles):
    size=path.stat().st_size
    before=sha256_file(path)
    row={"relative_path":path.relative_to(root).as_posix(),"bytes":size,"sha256":before}
    if size>MAX_FILE_BYTES:
        row.update({"skipped_content":True,"skip_reason":"file_too_large"})
        after=sha256_file(path)
        if before!=after: raise RuntimeError(f"source changed during scan: {path}")
        row["source_hash_unchanged"]=True
        return row

    raw=path.read_bytes()
    raw_hits=hits(raw,needles)
    stream_hits=[]
    cursor=0; valid_streams=0
    while True:
        at=raw.find(b"\x78",cursor)
        if at<0: break
        cursor=at+1
        got=dec(raw,at)
        if got is None: continue
        decoded,used=got; valid_streams+=1
        hs=hits(decoded,needles)
        if hs:
            stream_hits.append({
                "offset":at,"compressed_bytes":used,
                "decompressed_bytes":len(decoded),
                "summary":summarize(hs),"hits":hs
            })

    union=list(raw_hits)
    for s in stream_hits: union.extend(s["hits"])
    row.update({
        "skipped_content":False,
        "validated_zlib_streams":valid_streams,
        "raw_summary":summarize(raw_hits),
        "raw_hits":raw_hits,
        "zlib_streams_with_hits":stream_hits,
        "union_summary":summarize(union),
    })
    after=sha256_file(path)
    if before!=after: raise RuntimeError(f"source changed during scan: {path}")
    row["source_hash_unchanged"]=True
    return row

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-root",type=Path,default=Path.home()/"Saved Games"/"God of War")
    ap.add_argument("--identities",type=Path,default=IDENTITIES)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()

    root=a.save_root.expanduser().resolve()
    if not root.is_dir(): raise RuntimeError(f"save root missing: {root}")
    doc=json.loads(a.identities.read_text(encoding="utf-8"))
    if doc.get("identity_count")!=53: raise RuntimeError("Raven identity catalogue incomplete")
    needles=build_needles(doc)

    files=sorted(p.resolve() for p in root.rglob("*") if p.is_file())
    rows=[scan_file(p,root,needles) for p in files]
    all_hits=[]
    for row in rows:
        if row.get("skipped_content"): continue
        all_hits.extend(row.get("raw_hits",[]))
        for s in row.get("zlib_streams_with_hits",[]): all_hits.extend(s["hits"])

    report={
        "schema":1,
        "analysis":"full_active_save_tree_raven_identity_inventory",
        "save_root":str(root),
        "file_count":len(rows),
        "files":rows,
        "tree_union_summary":summarize(all_hits),
        "identity_catalogue_sha256":sha256_file(a.identities),
        "safety":{
            "save_tree_opened_read_only":True,
            "all_source_hashes_unchanged":all(r["source_hash_unchanged"] for r in rows),
            "save_written":False,"progression_written":False,
            "game_process_opened":False,"game_files_written":False
        }
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"ACTIVE_SAVE_TREE_SCAN_COMPLETE files={len(rows)} union={report['tree_union_summary']['unique_raven_count']}")
    for row in rows:
        u=row.get("union_summary",{})
        print(f"file={row['relative_path']} bytes={row['bytes']} ravenIdentities={u.get('unique_raven_count',0)} zlib={row.get('validated_zlib_streams',0)}")
    print("all_source_hashes_unchanged=true save_written=false progression_written=false")
    return 0

if __name__=="__main__": raise SystemExit(main())
