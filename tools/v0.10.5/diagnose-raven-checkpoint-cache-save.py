#!/usr/bin/env python3
"""Read-only check for Completionist Raven cache evidence in the active GoW game.sav."""
from __future__ import annotations
import argparse, hashlib, json, struct, zlib
from pathlib import Path

CACHE_KEY=b"__CompletionistMapV105Cache"
CATALOGUE_PREFIX=b"raven_"
MAX_DECOMPRESSED=8*1024*1024
INPUT_LIMIT=2*1024*1024

def sha256_file(path: Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def valid_zlib_header(data:bytes,off:int)->bool:
    if off+1>=len(data): return False
    cmf,flg=data[off],data[off+1]
    return (cmf & 0x0F)==8 and (cmf>>4)<=7 and (((cmf<<8)|flg)%31)==0

def try_stream(data:bytes,off:int):
    src=data[off:min(len(data),off+INPUT_LIMIT)]
    try:
        obj=zlib.decompressobj()
        raw=obj.decompress(src,MAX_DECOMPRESSED+1)
        if len(raw)>MAX_DECOMPRESSED or not obj.eof or not raw: return None
        consumed=len(src)-len(obj.unused_data)
        if consumed<=2: return None
        return raw,consumed
    except zlib.error:
        return None

def scan(path:Path)->dict:
    before=sha256_file(path)
    data=path.read_bytes()
    hdr={}
    if len(data)>=32:
        words=struct.unpack_from("<8I",data,0)
        hdr={"magic_u32":words[0],"header_size":words[4],"slot_stride":words[5],"declared_file_size":words[6]}
    raw_cache_hits=[]
    pos=0
    while True:
        at=data.find(CACHE_KEY,pos)
        if at<0: break
        raw_cache_hits.append(at); pos=at+1

    successful=0
    cache_streams=[]
    catalogue_streams=[]
    cursor=0
    while True:
        at=data.find(b"\x78",cursor)
        if at<0: break
        cursor=at+1
        if not valid_zlib_header(data,at): continue
        got=try_stream(data,at)
        if got is None: continue
        raw,consumed=got
        successful+=1
        cache_count=raw.count(CACHE_KEY)
        catalogue_count=raw.count(CATALOGUE_PREFIX)
        if cache_count:
            cache_streams.append({
                "offset":at,"compressed_bytes":consumed,"decompressed_bytes":len(raw),
                "sha256":hashlib.sha256(raw).hexdigest(),
                "cache_key_count":cache_count,"catalogue_prefix_count":catalogue_count
            })
        elif catalogue_count:
            catalogue_streams.append({
                "offset":at,"compressed_bytes":consumed,"decompressed_bytes":len(raw),
                "sha256":hashlib.sha256(raw).hexdigest(),
                "catalogue_prefix_count":catalogue_count
            })
    after=sha256_file(path)
    if before!=after:
        raise RuntimeError("Active save hash changed during read-only scan")
    return {
        "path":str(path),"bytes":len(data),"sha256":before,"header":hdr,
        "raw_cache_key_offsets":raw_cache_hits,
        "successful_zlib_streams":successful,
        "cache_streams":cache_streams,
        "catalogue_id_streams":catalogue_streams[:100],
        "cache_present":bool(raw_cache_hits or cache_streams),
        "source_hash_unchanged":True
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--save-root",type=Path,default=Path.home()/"Saved Games"/"God of War")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    root=args.save_root.expanduser().resolve()
    saves=sorted(p for p in root.rglob("game.sav") if p.is_file())
    if not saves: raise RuntimeError(f"No game.sav found under {root}")
    rows=[scan(p) for p in saves]
    payload={
        "schema":1,
        "scan_kind":"read_only_active_save_completionist_cache_check",
        "save_root":str(root),
        "files":rows,
        "cache_present_any":any(x["cache_present"] for x in rows),
        "save_or_progression_written":False
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print(f"RAVEN_CACHE_SAVE_SCAN cache_present_any={str(payload['cache_present_any']).lower()} saves={len(rows)}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
