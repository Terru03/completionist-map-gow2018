"""Trace the exact GoW GameObject token resolver and identity-field provenance.

Read-only, version-locked analysis of the supported GoW.exe. The common Lua
GameObject unbox helper at RVA 0x5F9350 has been proved to decode the opaque Lua
object token and call RVA 0x4EF0B0 with three components:
  low16  = (token >> 1)  & 0xFFFF
  flavor = (token >> 17) & 1
  bank20 = (token >> 18) & 0xFFFFF

This scanner recovers the exact function containing 0x4EF0B0, its direct call
edges, exact direct callers, RIP-relative ASCII references, and functions that
reference the live GameObject identity-field displacements +0x278/+0x280/+0x284.
The purpose is to locate where those fields are populated from persistent WAD
object data. No game launch and no save I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
IMAGE_SCN_MEM_EXECUTE = 0x20000000
UNBOX_RVA = 0x5F9350
RESOLVER_RVA = 0x4EF0B0
PACKER_RVA = 0x60B9C0
FIELD_DISPS = {"field_278": 0x278, "field_280": 0x280, "field_284": 0x284}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class PE:
    def __init__(self, data: bytes):
        self.data = data
        if data[:2] != b"MZ": raise RuntimeError("not MZ")
        peoff = struct.unpack_from("<I", data, 0x3C)[0]
        if data[peoff:peoff+4] != b"PE\0\0": raise RuntimeError("bad PE")
        nsec = struct.unpack_from("<H", data, peoff + 6)[0]
        optsz = struct.unpack_from("<H", data, peoff + 20)[0]
        opt = peoff + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x20B: raise RuntimeError("not PE32+")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        if self.image_base != IMAGE_BASE: raise RuntimeError(f"unexpected image base {self.image_base:#x}")
        self.size_of_image = struct.unpack_from("<I", data, opt + 56)[0]
        dd = opt + 112
        self.exception_rva, self.exception_size = struct.unpack_from("<II", data, dd + 3*8)
        sec0 = opt + optsz
        self.sections = []
        for i in range(nsec):
            o = sec0 + i*40
            name = data[o:o+8].split(b"\0",1)[0].decode("ascii","replace")
            vsize, rva, rawsize, raw = struct.unpack_from("<IIII", data, o+8)
            ch = struct.unpack_from("<I", data, o+36)[0]
            self.sections.append({"name":name,"vsize":vsize,"rva":rva,"rawsize":rawsize,"raw":raw,"exec":bool(ch & IMAGE_SCN_MEM_EXECUTE)})
        self.runtime_functions = self._runtime_functions()

    def rva_to_file(self, rva: int) -> int | None:
        for s in self.sections:
            span = max(s["vsize"], s["rawsize"])
            if s["rva"] <= rva < s["rva"] + span:
                d = rva - s["rva"]
                return s["raw"] + d if d < s["rawsize"] else None
        return None

    def file_to_rva(self, off: int) -> int | None:
        for s in self.sections:
            if s["raw"] <= off < s["raw"] + s["rawsize"]:
                return s["rva"] + off - s["raw"]
        return None

    def _runtime_functions(self):
        off = self.rva_to_file(self.exception_rva)
        if off is None: raise RuntimeError("exception directory not mapped")
        rows=[]
        for p in range(off, off+self.exception_size-11, 12):
            begin,end,unwind=struct.unpack_from("<III", self.data, p)
            if begin and end>begin and end<=self.size_of_image:
                rows.append({"begin":begin,"end":end,"unwind":unwind})
        rows.sort(key=lambda r:r["begin"])
        return rows

    def function_for(self, rva: int):
        lo,hi=0,len(self.runtime_functions)
        while lo<hi:
            mid=(lo+hi)//2
            if self.runtime_functions[mid]["begin"] <= rva: lo=mid+1
            else: hi=mid
        if lo==0:return None
        row=self.runtime_functions[lo-1]
        return row if row["begin"] <= rva < row["end"] else None

    def bytes_for(self, fn):
        off=self.rva_to_file(fn["begin"])
        if off is None:return b""
        return self.data[off:off+fn["end"]-fn["begin"]]

    def ascii_at_rva(self, rva:int, cap:int=160):
        off=self.rva_to_file(rva)
        if off is None:return None
        out=bytearray()
        for b in self.data[off:off+cap]:
            if b==0:break
            if b<0x20 or b>0x7E:return None
            out.append(b)
        if not out or off+len(out)>=len(self.data) or self.data[off+len(out)]!=0:return None
        return out.decode("ascii","replace")


def direct_edges(pe: PE, fn):
    blob=pe.bytes_for(fn); base=fn["begin"]; out=[]
    for i in range(max(0,len(blob)-4)):
        if blob[i] not in (0xE8,0xE9): continue
        disp=struct.unpack_from("<i",blob,i+1)[0]
        dest=base+i+5+disp
        if not (0 <= dest < pe.size_of_image): continue
        tf=pe.function_for(dest)
        out.append({"kind":"call" if blob[i]==0xE8 else "jmp","site":base+i,"dest":dest,"target_function_begin":tf["begin"] if tf else None})
    return out


def direct_callers(pe: PE, target_rva:int):
    out=[]
    for s in pe.sections:
        if not s["exec"]: continue
        start,end=s["raw"],min(len(pe.data),s["raw"]+s["rawsize"])
        for off in range(start,end-4):
            if pe.data[off] != 0xE8: continue
            site=pe.file_to_rva(off)
            if site is None: continue
            disp=struct.unpack_from("<i",pe.data,off+1)[0]
            if site+5+disp != target_rva: continue
            fn=pe.function_for(site)
            out.append({"site":site,"function_begin":fn["begin"] if fn else None,"function_end":fn["end"] if fn else None})
    return out


def rip_ascii_refs(pe: PE, fn):
    blob=pe.bytes_for(fn); base=fn["begin"]; out=[]; seen=set()
    for i in range(max(0,len(blob)-7)):
        rex,op,modrm=blob[i],blob[i+1],blob[i+2]
        if not (0x40 <= rex <= 0x4F and op in (0x8D,0x8B) and (modrm & 0xC7)==0x05): continue
        disp=struct.unpack_from("<i",blob,i+3)[0]
        target=base+i+7+disp
        text=pe.ascii_at_rva(target)
        if text and (target,text) not in seen:
            seen.add((target,text)); out.append({"site":base+i,"target":target,"text":text})
    return out


def field_hits_for_function(pe: PE, fn):
    blob=pe.bytes_for(fn); base=fn["begin"]; hits={k:[] for k in FIELD_DISPS}
    for label,disp in FIELD_DISPS.items():
        needle=struct.pack("<I",disp)
        p=0
        while True:
            p=blob.find(needle,p)
            if p<0:break
            lo=max(0,p-5); hi=min(len(blob),p+9)
            prefix=blob[lo:p]
            # Heuristic classification only; raw bytes are retained for review.
            write_like=any(op in prefix[-4:] for op in (0x88,0x89,0xC6,0xC7))
            read_like=any(op in prefix[-4:] for op in (0x8A,0x8B,0x0F))
            hits[label].append({"site":base+p,"window_hex":blob[lo:hi].hex(),"write_like":write_like,"read_like":read_like})
            p+=1
    return hits


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()
    exe=args.game_root.resolve()/"GoW.exe"
    before=sha256(exe)
    if before != EXPECTED_SHA256: raise RuntimeError(f"Unexpected GoW.exe SHA-256: {before}")
    pe=PE(exe.read_bytes())

    resolver_fn=pe.function_for(RESOLVER_RVA)
    if resolver_fn is None: raise RuntimeError("No pdata function contains resolver RVA 0x4EF0B0")
    unbox_fn=pe.function_for(UNBOX_RVA)
    packer_fn=pe.function_for(PACKER_RVA)

    resolver={
        "entry_rva":RESOLVER_RVA,
        "function_begin":resolver_fn["begin"],"function_end":resolver_fn["end"],
        "size":resolver_fn["end"]-resolver_fn["begin"],
        "calls":direct_edges(pe,resolver_fn),
        "callers":direct_callers(pe,RESOLVER_RVA),
        "ascii_refs":rip_ascii_refs(pe,resolver_fn),
        "bytes_hex":pe.bytes_for(resolver_fn).hex(),
    }

    field_functions=[]
    for fn in pe.runtime_functions:
        hits=field_hits_for_function(pe,fn)
        distinct=sum(1 for v in hits.values() if v)
        if distinct < 2: continue
        strings=rip_ascii_refs(pe,fn)
        calls=direct_edges(pe,fn)
        write_count=sum(1 for vals in hits.values() for h in vals if h["write_like"])
        score=distinct*10 + write_count*5
        if any(c["dest"]==RESOLVER_RVA for c in calls): score += 20
        if any(c["dest"]==PACKER_RVA for c in calls): score += 10
        field_functions.append({
            "begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],
            "score":score,"write_like_count":write_count,"field_hits":hits,
            "calls":calls,"ascii_refs":strings,
            "is_packer":fn["begin"] <= PACKER_RVA < fn["end"],
            "is_unbox":fn["begin"] <= UNBOX_RVA < fn["end"],
            "is_resolver":fn["begin"] <= RESOLVER_RVA < fn["end"],
        })
    field_functions.sort(key=lambda r:(-r["score"],r["begin"]))

    after=sha256(exe)
    if after != before: raise RuntimeError("GoW.exe changed during scan")
    report={
        "schema":1,"analysis":"gameobject_token_resolver_provenance","exe_sha256":before,
        "proved_token_decode":{"low16":"(token >> 1) & 0xFFFF","flavor":"(token >> 17) & 1","bank20":"(token >> 18) & 0xFFFFF","resolver_rva":"0x4EF0B0"},
        "unbox_function":({"begin":unbox_fn["begin"],"end":unbox_fn["end"]} if unbox_fn else None),
        "packer_function":({"begin":packer_fn["begin"],"end":packer_fn["end"]} if packer_fn else None),
        "resolver":resolver,"identity_field_functions":field_functions,
        "safety":{"read_only":True,"game_launched":False,"save_opened":False,"progression_written":False,"source_hash_unchanged":True},
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - exact GameObject token resolver provenance",
        f"exe_sha256={before}",
        "token_decode: low16=(token>>1)&0xFFFF flavor=(token>>17)&1 bank20=(token>>18)&0xFFFFF",
        f"resolver_entry=0x{RESOLVER_RVA:X} fn=0x{resolver_fn['begin']:X}-0x{resolver_fn['end']:X} size={resolver_fn['end']-resolver_fn['begin']}",
        f"resolver_direct_callers={len(resolver['callers'])}",
    ]
    for c in resolver["callers"]:
        lines.append(f"  CALLER site=0x{c['site']:X} fn={('0x%X'%c['function_begin']) if c['function_begin'] is not None else 'none'}")
    lines.append("resolver_edges:")
    for e in resolver["calls"]:
        lines.append(f"  {e['kind'].upper()} 0x{e['site']:X} -> 0x{e['dest']:X} targetFn={('0x%X'%e['target_function_begin']) if e['target_function_begin'] is not None else 'none'}")
    for s in resolver["ascii_refs"]:
        lines.append(f"  STR 0x{s['site']:X} {s['text']!r}")
    lines.append("")
    lines.append("TOP IDENTITY-FIELD FUNCTIONS")
    for f in field_functions[:40]:
        labels=','.join(k for k,v in f["field_hits"].items() if v)
        lines.append(f"  0x{f['begin']:X}-0x{f['end']:X} score={f['score']} writes={f['write_like_count']} fields={labels} packer={str(f['is_packer']).lower()} unbox={str(f['is_unbox']).lower()} resolver={str(f['is_resolver']).lower()}")
        for s in f["ascii_refs"]:
            if any(k in s["text"].lower() for k in ("wad","guid","object","gameobject","ref","instance","level","stream","spawn")):
                lines.append(f"    STR 0x{s['site']:X} {s['text']!r}")
        for label,vals in f["field_hits"].items():
            for h in vals[:4]:
                if h["write_like"]:
                    lines.append(f"    WRITE? {label} site=0x{h['site']:X} bytes={h['window_hex']}")
    lines.extend(["","source_hash_unchanged=true game_launched=false save_opened=false progression_written=false"])
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("GAMEOBJECT_TOKEN_RESOLVER_SCAN_PASSED")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
