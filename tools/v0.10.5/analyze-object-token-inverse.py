"""Find native candidates that decode GoW's opaque GameObject Lua token.

Read-only, version-locked GoW.exe analysis. The proven GameObject token packer at
RVA 0x60B9C0 constructs the Lua-side opaque handle from GameObject fields at
+0x278, +0x280, and +0x284. This scanner searches exact x64 runtime-function
boundaries for those same displacements and complementary bit-manipulation
signatures, then ranks likely inverse/resolver functions. It never launches the
game or opens saves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TOKEN_PACKER_RVA = 0x60B9C0
IMAGE_SCN_MEM_EXECUTE = 0x20000000
FIELD_PATTERNS = {
    "field_278": bytes.fromhex("78020000"),
    "field_280": bytes.fromhex("80020000"),
    "field_284": bytes.fromhex("84020000"),
}
MASK20 = bytes.fromhex("ffff0f00")


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

    def rva_to_file(self, rva: int) -> int|None:
        for s in self.sections:
            span = max(s["vsize"], s["rawsize"])
            if s["rva"] <= rva < s["rva"] + span:
                d = rva - s["rva"]
                return s["raw"] + d if d < s["rawsize"] else None
        return None

    def _runtime_functions(self):
        off = self.rva_to_file(self.exception_rva)
        if off is None: raise RuntimeError("exception directory not mapped")
        rows=[]
        for p in range(off, off+self.exception_size-11, 12):
            begin,end,unwind = struct.unpack_from("<III", self.data, p)
            if begin and end > begin and end <= self.size_of_image:
                rows.append({"begin":begin,"end":end,"unwind":unwind})
        rows.sort(key=lambda r:r["begin"])
        return rows

    def bytes_for_function(self, fn):
        off = self.rva_to_file(fn["begin"])
        if off is None: return b""
        return self.data[off:off + fn["end"]-fn["begin"]]

    def function_for(self, rva:int):
        lo,hi=0,len(self.runtime_functions)
        while lo<hi:
            mid=(lo+hi)//2
            if self.runtime_functions[mid]["begin"] <= rva: lo=mid+1
            else: hi=mid
        if lo==0:return None
        row=self.runtime_functions[lo-1]
        return row if row["begin"] <= rva < row["end"] else None

    def ascii_at_rva(self, rva:int, cap:int=120):
        off=self.rva_to_file(rva)
        if off is None:return None
        out=bytearray()
        for b in self.data[off:off+cap]:
            if b==0:break
            if b<0x20 or b>0x7E:return None
            out.append(b)
        if not out or off+len(out)>=len(self.data) or self.data[off+len(out)]!=0:return None
        return out.decode("ascii","replace")


def direct_calls(pe:PE, fn):
    blob=pe.bytes_for_function(fn); base=fn["begin"]; out=[]
    for i in range(max(0,len(blob)-4)):
        if blob[i] != 0xE8: continue
        disp=struct.unpack_from("<i",blob,i+1)[0]
        dest=base+i+5+disp
        if 0 <= dest < pe.size_of_image:
            tf=pe.function_for(dest)
            out.append({"site":base+i,"dest":dest,"target_function_begin":tf["begin"] if tf else None})
    return out


def rip_ascii_refs(pe:PE, fn):
    blob=pe.bytes_for_function(fn); base=fn["begin"]; out=[]; seen=set()
    for i in range(max(0,len(blob)-7)):
        rex,op,modrm=blob[i],blob[i+1],blob[i+2]
        if not (0x40 <= rex <= 0x4F and op in (0x8D,0x8B) and (modrm & 0xC7)==0x05): continue
        disp=struct.unpack_from("<i",blob,i+3)[0]
        target=base+i+7+disp
        text=pe.ascii_at_rva(target)
        if text and (target,text) not in seen:
            seen.add((target,text)); out.append({"site":base+i,"target":target,"text":text})
    return out


def positions(blob:bytes, needle:bytes):
    out=[]; p=0
    while True:
        p=blob.find(needle,p)
        if p<0:return out
        out.append(p); p+=1


def score_function(blob:bytes, field_hits:dict[str,list[int]]):
    fields=sum(1 for v in field_hits.values() if v)
    score=fields*10
    mask20=positions(blob,MASK20)
    if mask20: score += 6
    # common x64 immediate shifts by 16 or 1; broad but only used after field filtering
    shr16=[]; shr1=[]; lowbit=[]
    for i in range(max(0,len(blob)-4)):
        if blob[i] in (0x48,0x49) and i+3 < len(blob) and blob[i+1] == 0xC1 and blob[i+3] == 0x10:
            shr16.append(i); score += 2
        if blob[i] in (0x48,0x49) and i+3 < len(blob) and blob[i+1] in (0xD1,0xC1) and blob[i+3 if blob[i+1]==0xC1 else i+2] == 0x01:
            shr1.append(i); score += 1
        # and/test immediate 1 forms
        if i+3 < len(blob) and blob[i] in (0x83,0xF6,0xF7) and blob[i+2] == 0x01:
            lowbit.append(i); score += 1
    return score,mask20,shr16,shr1,lowbit


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()
    exe=args.game_root.resolve()/"GoW.exe"
    before=sha256(exe)
    if before != EXPECTED_SHA256: raise RuntimeError(f"Unexpected GoW.exe SHA-256: {before}")
    pe=PE(exe.read_bytes())
    candidates=[]
    for fn in pe.runtime_functions:
        blob=pe.bytes_for_function(fn)
        if not blob: continue
        hits={name:positions(blob,pat) for name,pat in FIELD_PATTERNS.items()}
        if sum(1 for v in hits.values() if v) < 2: continue
        score,mask20,shr16,shr1,lowbit=score_function(blob,hits)
        calls=direct_calls(pe,fn)
        strings=rip_ascii_refs(pe,fn)
        candidates.append({
            "begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],
            "score":score,"is_known_packer":fn["begin"] <= TOKEN_PACKER_RVA < fn["end"],
            "field_hits":{k:[fn["begin"]+x for x in v] for k,v in hits.items()},
            "mask20_hits":[fn["begin"]+x for x in mask20],
            "shift16_hits":[fn["begin"]+x for x in shr16],
            "shift1_hits":[fn["begin"]+x for x in shr1],
            "lowbit_hits":[fn["begin"]+x for x in lowbit],
            "calls":calls,"ascii_refs":strings,"bytes_hex":blob.hex(),
        })
    candidates.sort(key=lambda c:(-c["score"],c["begin"]))
    after=sha256(exe)
    if after != before: raise RuntimeError("GoW.exe changed during scan")
    report={"schema":1,"analysis":"object_token_inverse_candidates","exe_sha256":before,"known_packer_rva":hex(TOKEN_PACKER_RVA),"candidate_count":len(candidates),"candidates":candidates,"safety":{"read_only":True,"game_launched":False,"save_opened":False,"progression_written":False,"source_hash_unchanged":True}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    lines=["Completionist Map - object token inverse candidates",f"exe_sha256={before}",f"candidate_count={len(candidates)}",""]
    for c in candidates[:80]:
        fields=','.join(k for k,v in c["field_hits"].items() if v)
        lines.append(f"FUNCTION 0x{c['begin']:X}-0x{c['end']:X} score={c['score']} knownPacker={str(c['is_known_packer']).lower()} fields={fields} mask20={len(c['mask20_hits'])} shift16={len(c['shift16_hits'])} lowbit={len(c['lowbit_hits'])}")
        for s in c["ascii_refs"]:
            if any(k in s["text"].lower() for k in ("object","gameobject","ref","level","wad","guid","subobj","pickle")):
                lines.append(f"  STR 0x{s['site']:X} {s['text']!r}")
        for call in c["calls"][:24]:
            lines.append(f"  CALL 0x{call['site']:X} -> 0x{call['dest']:X}")
        lines.append("")
    lines.append("source_hash_unchanged=true game_launched=false save_opened=false progression_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("OBJECT_TOKEN_INVERSE_SCAN_PASSED")
    return 0

if __name__=="__main__": raise SystemExit(main())
