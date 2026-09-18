#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, re, struct, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
CLOSURE_RE=re.compile(r"QM_CLOSURE name=([A-Za-z0-9_]+) type=function tostring=function:\\s*(?:0x)?([0-9A-Fa-f]+)")

def load_helper():
    p=HERE/"read-raven-gameobject-identity-memory.py"
    spec=importlib.util.spec_from_file_location("gow_qm_closure_mem",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def pe_exec_ranges(exe:Path,module_base:int):
    raw=exe.read_bytes(); peoff=struct.unpack_from("<I",raw,0x3C)[0]
    nsec=struct.unpack_from("<H",raw,peoff+6)[0]
    optsz=struct.unpack_from("<H",raw,peoff+20)[0]; sec0=peoff+24+optsz
    out=[]
    for i in range(nsec):
        o=sec0+i*40
        name=raw[o:o+8].split(b"\0",1)[0].decode("ascii","replace")
        vsize,rva,rawsize,_=struct.unpack_from("<IIII",raw,o+8)
        ch=struct.unpack_from("<I",raw,o+36)[0]
        if ch & 0x20000000:
            out.append((module_base+rva,module_base+rva+max(vsize,rawsize),name))
    return out

def parse_closures(log:Path):
    text=log.read_text(encoding="utf-8",errors="replace")
    out={}
    for m in CLOSURE_RE.finditer(text):
        out[m.group(1)]=int(m.group(2),16)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--loader-log",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if sys.platform!="win32": raise RuntimeError("Windows-only")
    closures=parse_closures(args.loader_log)
    if not closures: raise RuntimeError("No QM_CLOSURE function addresses found")
    helper=load_helper(); k32=helper.configure_kernel32()
    pid,exe_name=helper.find_supported_process(k32)
    module_base,module_size,exe_path=helper.get_main_module(k32,pid,exe_name)
    exe=Path(exe_path); exe_sha=helper.sha256_file(exe)
    if exe_sha.lower()!=EXPECTED_SHA256: raise RuntimeError(f"unsupported GoW.exe sha256 {exe_sha}")
    exec_ranges=pe_exec_ranges(exe,module_base)
    access=helper.PROCESS_VM_READ|helper.PROCESS_QUERY_INFORMATION
    proc=k32.OpenProcess(access,False,pid)
    if not proc: raise helper.winerr("OpenProcess(read-only) failed")
    try:
        rows={}
        for name,addr in closures.items():
            blob=helper.read_mem(k32,proc,addr,0x100)
            qwords=[]
            for off in range(0,0x100,8):
                val=struct.unpack_from("<Q",blob,off)[0]
                in_module=module_base<=val<module_base+module_size
                exec_sec=None
                for lo,hi,sec in exec_ranges:
                    if lo<=val<hi:
                        exec_sec=sec; break
                if in_module:
                    qwords.append({
                        "offset":off,"offset_hex":f"0x{off:X}",
                        "value_hex":f"0x{val:X}",
                        "rva":val-module_base,"rva_hex":f"0x{val-module_base:X}",
                        "executable_section":exec_sec,
                    })
            rows[name]={
                "closure_address_hex":f"0x{addr:X}",
                "first_0x100_hex":blob.hex(),
                "module_pointer_qwords":qwords,
                "executable_candidates":[q for q in qwords if q["executable_section"]],
            }
        report={
            "schema":1,
            "analysis":"questmanager_lua_cclosure_native_pointer_capture",
            "process":{"pid":pid,"exe_name":exe_name,"exe_sha256":exe_sha,
                       "module_base":f"0x{module_base:X}","module_size":module_size},
            "closures":rows,
            "safety":{"open_process_access":"PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                      "debugger_attached":False,"remote_code_called":False,
                      "process_memory_written":False,"save_or_progression_written":False},
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(f"QM_CLOSURE_NATIVE_CAPTURED count={len(rows)}")
        for name,row in rows.items():
            print(f"{name} closure={row['closure_address_hex']} execCandidates={len(row['executable_candidates'])}")
            for c in row["executable_candidates"]:
                print(f"  off={c['offset_hex']} rva={c['rva_hex']} sec={c['executable_section']}")
        print("process_memory_written=false save_or_progression_written=false")
    finally:
        helper.close_handle(k32,proc)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr); raise SystemExit(1)
