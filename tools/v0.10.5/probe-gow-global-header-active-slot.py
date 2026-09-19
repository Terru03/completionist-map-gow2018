#!/usr/bin/env python3
"""Read-only GoW global-header / active-slot correlation probe.

The file has one declared 208-byte global header, followed by alignment padding
and 20 fixed save-ring slots. This probe compares the global header across:
- the active game.sav;
- the frozen Raven alive save;
- the frozen Raven dead save.

It correlates changed header fields with physical slot indices, slot timestamps,
slot starts/ends, and newest-slot selection. No save or game files are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

HEADER = 208
PREFIX = 4160
STRIDE = 1677512
SLOTS = 20
TOTAL = 33554400


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()


def unique_game_save(root: Path) -> Path:
    xs=sorted(p.resolve() for p in root.rglob("game.sav") if p.is_file())
    if len(xs)!=1:
        raise RuntimeError(f"expected one game.sav under {root}, found {len(xs)}")
    return xs[0]


def locate_frozen(desktop: Path):
    roots = [Path.home() / "Documents", desktop]
    dirs = []
    for base in roots:
        if not base.is_dir():
            continue
        dirs.extend(p for p in base.glob("GodOfWar-RavenAliveDead-*") if p.is_dir())
    dirs = sorted(set(p.resolve() for p in dirs), key=lambda p: p.name)
    if not dirs:
        raise RuntimeError(
            "frozen GodOfWar-RavenAliveDead-* backup not found under Documents or Desktop"
        )
    preferred = [
        p for p in dirs if p.name == "GodOfWar-RavenAliveDead-20260915-220250"
    ]
    root = preferred[0] if preferred else dirs[-1]
    alive=unique_game_save(root/"alive")
    dead=unique_game_save(root/"dead")
    return root,alive,dead


def parse(path: Path):
    raw=path.read_bytes()
    if len(raw)!=TOTAL:
        raise RuntimeError(f"unexpected save length {len(raw)} for {path}")
    hdr=raw[:HEADER]
    slots=[]
    for i in range(SLOTS):
        start=PREFIX+i*STRIDE
        sh=raw[start:start+HEADER]
        ts=struct.unpack_from("<I",sh,0)[0]
        slots.append({
            "slot":i,
            "start":start,
            "end":start+STRIDE,
            "timestamp_u32":ts,
            "header_sha256":hashlib.sha256(sh).hexdigest(),
        })
    newest=max(slots,key=lambda x:x["timestamp_u32"])
    u8=list(hdr)
    u16={off:struct.unpack_from("<H",hdr,off)[0] for off in range(0,HEADER-1,2)}
    u32={off:struct.unpack_from("<I",hdr,off)[0] for off in range(0,HEADER-3,4)}
    u64={off:struct.unpack_from("<Q",hdr,off)[0] for off in range(0,HEADER-7,8)}
    return {
        "path":str(path),
        "sha256":sha256_file(path),
        "header_hex":hdr.hex(),
        "u8":u8,"u16":u16,"u32":u32,"u64":u64,
        "slots":slots,
        "newest_slot":newest["slot"],
        "newest_timestamp_u32":newest["timestamp_u32"],
    }


def changed_runs(a: bytes,b: bytes):
    out=[]; s=None
    for i,(x,y) in enumerate(zip(a,b)):
        if x!=y and s is None: s=i
        if x==y and s is not None:
            out.append((s,i-s)); s=None
    if s is not None: out.append((s,len(a)-s))
    return out


def correlate(doc):
    hdr=bytes.fromhex(doc["header_hex"])
    slot_times={x["timestamp_u32"]:x["slot"] for x in doc["slots"]}
    starts={x["start"]:x["slot"] for x in doc["slots"]}
    ends={x["end"]:x["slot"] for x in doc["slots"]}
    out=[]
    for width,fmt in ((1,"<B"),(2,"<H"),(4,"<I"),(8,"<Q")):
        step=width
        for off in range(0,HEADER-width+1,step):
            v=struct.unpack_from(fmt,hdr,off)[0]
            labels=[]
            if 0<=v<SLOTS: labels.append(f"slot_index:{v}")
            if v==doc["newest_slot"]: labels.append("newest_slot_index")
            if v in slot_times: labels.append(f"slot_timestamp:{slot_times[v]}")
            if v in starts: labels.append(f"slot_start:{starts[v]}")
            if v in ends: labels.append(f"slot_end:{ends[v]}")
            # Common transformed pointers/index forms.
            if v>=PREFIX and (v-PREFIX)%STRIDE==0:
                idx=(v-PREFIX)//STRIDE
                if 0<=idx<SLOTS: labels.append(f"slot_start_formula:{idx}")
            if v and v%STRIDE==0:
                idx=v//STRIDE
                if 0<=idx<=SLOTS: labels.append(f"stride_multiple:{idx}")
            if labels:
                out.append({"width":width,"offset":off,"offset_hex":f"0x{off:X}","value":v,"labels":labels})
    return out


def diff_fields(a,b):
    out=[]
    ah=bytes.fromhex(a["header_hex"]); bh=bytes.fromhex(b["header_hex"])
    for width,fmt in ((1,"<B"),(2,"<H"),(4,"<I"),(8,"<Q")):
        for off in range(0,HEADER-width+1,width):
            av=struct.unpack_from(fmt,ah,off)[0]; bv=struct.unpack_from(fmt,bh,off)[0]
            if av!=bv:
                out.append({"width":width,"offset":off,"offset_hex":f"0x{off:X}","a":av,"b":bv})
    return out


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-root",type=Path,default=Path.home()/"Saved Games"/"God of War")
    ap.add_argument("--desktop",type=Path,default=Path.home()/"Desktop")
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()

    active=unique_game_save(args.save_root.expanduser().resolve())
    frozen_root,alive,dead=locate_frozen(args.desktop.expanduser().resolve())
    paths={"active":active,"alive":alive,"dead":dead}
    before={k:sha256_file(v) for k,v in paths.items()}
    docs={k:parse(v) for k,v in paths.items()}
    after={k:sha256_file(v) for k,v in paths.items()}
    if before!=after:
        raise RuntimeError("source save hash changed during read-only global-header probe")

    rawh={k:bytes.fromhex(v["header_hex"]) for k,v in docs.items()}
    report={
        "schema":1,
        "analysis":"gow_global_header_active_slot_correlation",
        "frozen_root":str(frozen_root),
        "sources":docs,
        "correlations":{k:correlate(v) for k,v in docs.items()},
        "alive_to_dead":{
            "changed_runs":[{"offset":s,"offset_hex":f"0x{s:X}","length":n} for s,n in changed_runs(rawh["alive"],rawh["dead"])],
            "changed_fields":diff_fields(docs["alive"],docs["dead"]),
            "newest_slot_before":docs["alive"]["newest_slot"],
            "newest_slot_after":docs["dead"]["newest_slot"],
        },
        "dead_to_active":{
            "changed_runs":[{"offset":s,"offset_hex":f"0x{s:X}","length":n} for s,n in changed_runs(rawh["dead"],rawh["active"])],
            "changed_fields":diff_fields(docs["dead"],docs["active"]),
        },
        "safety":{
            "active_save_opened_read_only":True,
            "frozen_saves_opened_read_only":True,
            "source_hashes_unchanged":True,
            "save_written":False,
            "progression_written":False,
            "game_process_opened":False,
            "game_files_written":False,
        }
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - GoW global-header active-slot correlation",
        f"frozen_root={frozen_root}",
        "",
    ]
    for name in ("alive","dead","active"):
        d=docs[name]
        lines.append(f"{name}: sha256={d['sha256']} newestSlot={d['newest_slot']} newestTimestamp={d['newest_timestamp_u32']}")
        cs=report["correlations"][name]
        for row in cs:
            # Suppress trivial zero-valued slot-index coincidences.
            if row["value"]==0 and all(x.startswith("slot_index") for x in row["labels"]):
                continue
            lines.append(f"  field offset={row['offset_hex']} width={row['width']} value={row['value']} labels={','.join(row['labels'])}")

    lines.extend(["","ALIVE -> DEAD GLOBAL HEADER CHANGES"])
    if not report["alive_to_dead"]["changed_runs"]:
        lines.append("  none")
    else:
        for row in report["alive_to_dead"]["changed_runs"]:
            lines.append(f"  run offset={row['offset_hex']} length={row['length']}")
        for row in report["alive_to_dead"]["changed_fields"]:
            if row["width"] in (4,8):
                lines.append(f"  field offset={row['offset_hex']} width={row['width']} {row['a']} -> {row['b']}")

    lines.extend(["","SAFETY active_save_opened_read_only=true frozen_saves_opened_read_only=true source_hashes_unchanged=true save_written=false progression_written=false"])
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    changes=len(report["alive_to_dead"]["changed_runs"])
    correlated=sum(len(v) for v in report["correlations"].values())
    print(f"GOW_GLOBAL_HEADER_ACTIVE_SLOT_PROBE_COMPLETE changedRuns={changes} correlations={correlated} aliveNewest={docs['alive']['newest_slot']} deadNewest={docs['dead']['newest_slot']} activeNewest={docs['active']['newest_slot']}")
    print("source_hashes_unchanged=true save_written=false progression_written=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
