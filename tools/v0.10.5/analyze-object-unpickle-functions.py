"""Function-level trace of GoW's object pickle/unpickle native path.

Version-locked, read-only analysis of GoW.exe. Uses the PE x64 exception table
(.pdata) to recover exact native function boundaries containing references to
__subobjs / __prevunpickle / pickle roots, then inventories direct CALLs and
RIP-relative ASCII references inside those functions. No game launch or save I/O.
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
TARGETS = ("__prevunpickle", "__PickleTable", "__SoftPickleTable", "__subobjs")
IMAGE_SCN_MEM_EXECUTE = 0x20000000


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
        self.exception_rva, self.exception_size = struct.unpack_from("<II", data, dd + 3 * 8)
        sec0 = opt + optsz
        self.sections = []
        for i in range(nsec):
            o = sec0 + i * 40
            name = data[o:o+8].split(b"\0",1)[0].decode("ascii","replace")
            vsize, rva, rawsize, raw = struct.unpack_from("<IIII", data, o + 8)
            ch = struct.unpack_from("<I", data, o + 36)[0]
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

    def _runtime_functions(self) -> list[dict]:
        off = self.rva_to_file(self.exception_rva)
        if off is None: raise RuntimeError("exception directory not mapped")
        rows = []
        for p in range(off, off + self.exception_size - 11, 12):
            begin, end, unwind = struct.unpack_from("<III", self.data, p)
            if begin and end > begin and end <= self.size_of_image:
                rows.append({"begin":begin,"end":end,"unwind":unwind})
        rows.sort(key=lambda x:x["begin"])
        return rows

    def function_for(self, rva: int) -> dict | None:
        lo, hi = 0, len(self.runtime_functions)
        while lo < hi:
            mid = (lo + hi)//2
            if self.runtime_functions[mid]["begin"] <= rva: lo = mid + 1
            else: hi = mid
        if lo == 0: return None
        row = self.runtime_functions[lo-1]
        return row if row["begin"] <= rva < row["end"] else None

    def bytes_for_function(self, fn: dict) -> bytes:
        off = self.rva_to_file(fn["begin"])
        if off is None: return b""
        return self.data[off:off + fn["end"] - fn["begin"]]

    def ascii_at_rva(self, rva: int, cap: int = 120) -> str | None:
        off = self.rva_to_file(rva)
        if off is None: return None
        out = bytearray()
        for b in self.data[off:off+cap]:
            if b == 0: break
            if b < 0x20 or b > 0x7E: return None
            out.append(b)
        if not out or off + len(out) >= len(self.data) or self.data[off+len(out)] != 0: return None
        return out.decode("ascii", "replace")


def all_occurrences(data: bytes, needle: bytes) -> list[int]:
    out=[]; pos=0
    while True:
        pos=data.find(needle,pos)
        if pos<0:return out
        out.append(pos); pos+=1


def riprel_refs_to(pe: PE, target_va: int) -> list[int]:
    out=[]
    for s in pe.sections:
        if not s["exec"]: continue
        start,end=s["raw"],min(len(pe.data),s["raw"]+s["rawsize"])
        for disp_off in range(start,end-3):
            disp=struct.unpack_from("<i",pe.data,disp_off)[0]
            disp_rva=s["rva"]+disp_off-start
            if IMAGE_BASE+disp_rva+4+disp==target_va: out.append(disp_rva)
    return out


def direct_calls(pe: PE, fn: dict) -> list[dict]:
    """Raw E8 candidates bounded to a known function; destinations are validated to image/pdata."""
    blob=pe.bytes_for_function(fn); out=[]; base=fn["begin"]
    for i in range(0,max(0,len(blob)-4)):
        if blob[i] != 0xE8: continue
        disp=struct.unpack_from("<i",blob,i+1)[0]
        site=base+i; dest=site+5+disp
        if not (0 <= dest < pe.size_of_image): continue
        target_fn=pe.function_for(dest)
        out.append({"site":site,"dest":dest,"target_function_begin":target_fn["begin"] if target_fn else None})
    return out


def rip_ascii_refs(pe: PE, fn: dict) -> list[dict]:
    """Decode common REX + LEA/MOV r64,[RIP+disp32] forms and keep ASCII targets."""
    blob=pe.bytes_for_function(fn); base=fn["begin"]; out=[]; seen=set()
    for i in range(0,max(0,len(blob)-7)):
        rex,op,modrm=blob[i],blob[i+1],blob[i+2]
        if not (0x40 <= rex <= 0x4F and op in (0x8D,0x8B) and (modrm & 0xC7)==0x05): continue
        disp=struct.unpack_from("<i",blob,i+3)[0]
        target=base+i+7+disp
        text=pe.ascii_at_rva(target)
        if text is None or (target,text) in seen: continue
        seen.add((target,text)); out.append({"site":base+i,"target":target,"text":text})
    return out


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()
    exe=args.game_root.resolve()/"GoW.exe"
    before=sha256(exe)
    if before != EXPECTED_SHA256: raise RuntimeError(f"Unexpected GoW.exe SHA-256: {before}")
    pe=PE(exe.read_bytes())

    refs=[]
    for name in TARGETS:
        for file_off in all_occurrences(pe.data,name.encode("ascii")+b"\0"):
            rva=pe.file_to_rva(file_off)
            if rva is None: continue
            for disp_rva in riprel_refs_to(pe,IMAGE_BASE+rva):
                fn=pe.function_for(disp_rva)
                refs.append({"name":name,"xref_rva":disp_rva,"function_begin":fn["begin"] if fn else None,"function_end":fn["end"] if fn else None})

    unique={}
    for ref in refs:
        if ref["function_begin"] is None: continue
        key=(ref["function_begin"],ref["function_end"])
        unique[key]=pe.function_for(ref["function_begin"])

    functions=[]
    for key in sorted(unique):
        fn=unique[key]
        calls=direct_calls(pe,fn)
        functions.append({
            "begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],
            "refs":[r for r in refs if r["function_begin"]==fn["begin"]],
            "calls":calls,
            "calls_token_packer":any(c["dest"]==TOKEN_PACKER_RVA for c in calls),
            "ascii_refs":rip_ascii_refs(pe,fn),
            "bytes_hex":pe.bytes_for_function(fn).hex(),
        })

    # One-hop callees with exact pdata boundaries, to expose candidate resolvers.
    callee_begins=sorted({c["target_function_begin"] for f in functions for c in f["calls"] if c["target_function_begin"] is not None})
    callees=[]
    for begin in callee_begins:
        fn=pe.function_for(begin)
        if fn is None: continue
        callees.append({
            "begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],
            "calls_token_packer":any(c["dest"]==TOKEN_PACKER_RVA for c in direct_calls(pe,fn)),
            "ascii_refs":rip_ascii_refs(pe,fn),
        })

    after=sha256(exe)
    if after != before: raise RuntimeError("GoW.exe changed during scan")
    report={"schema":1,"analysis":"object_unpickle_function_trace","exe_sha256":before,"runtime_function_count":len(pe.runtime_functions),"refs":refs,"functions":functions,"one_hop_callees":callees,"safety":{"read_only":True,"game_launched":False,"save_opened":False,"progression_written":False,"source_hash_unchanged":True}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")

    lines=["Completionist Map - function-level object unpickle trace",f"exe_sha256={before}",f"runtime_functions={len(pe.runtime_functions)}",f"interesting_functions={len(functions)}",""]
    for f in functions:
        labels=", ".join(f"{r['name']}@0x{r['xref_rva']:X}" for r in f["refs"])
        lines.append(f"FUNCTION 0x{f['begin']:X}-0x{f['end']:X} size={f['size']} tokenPacker={str(f['calls_token_packer']).lower()} refs={labels}")
        for c in f["calls"]:
            lines.append(f"  CALL 0x{c['site']:X} -> 0x{c['dest']:X} targetFn={('0x%X'%c['target_function_begin']) if c['target_function_begin'] is not None else 'none'}")
        for s in f["ascii_refs"]:
            lines.append(f"  STR  0x{s['site']:X} -> 0x{s['target']:X} {s['text']!r}")
        lines.append("")
    lines.append("ONE-HOP CALLEE SUMMARY")
    for c in callees:
        interesting=[s["text"] for s in c["ascii_refs"] if any(k in s["text"].lower() for k in ("pickle","object","subobj","level","wad","guid","ref"))]
        if c["calls_token_packer"] or interesting:
            lines.append(f"  0x{c['begin']:X}-0x{c['end']:X} size={c['size']} tokenPacker={str(c['calls_token_packer']).lower()} strings={interesting}")
    lines.extend(["","source_hash_unchanged=true game_launched=false save_opened=false progression_written=false"])
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("OBJECT_UNPICKLE_FUNCTION_SCAN_PASSED")
    return 0

if __name__=="__main__": raise SystemExit(main())
