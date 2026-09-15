"""Trace the canonical WAD loader record -> persistent GameObject tuple edge.

Read-only, version-locked static analysis. Focuses on the shared canonical-looking
0x858320 path that calls descriptor builder 0x8566B0 at 0x859BD6 and loader
0x856F50 at 0x859C0D, plus the exact RBX provenance used by 0x82D1FB to load
registry_id from [rbx+0x24]. No save access, game launch, or executable writes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000

CANONICAL_OWNER = 0x858320
CANONICAL_BUILDER_CALL = 0x859BD6
CANONICAL_LOADER_CALL = 0x859C0D
DESCRIPTOR_BUILDER = 0x8566B0
LOADER = 0x856F50
REGISTRY_OWNER = 0x82CF00
REGISTRY_SOURCE = 0x82D1FB
REGISTRY_STORE = 0x82D203


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_canonical_loader_pe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load PE helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_capstone():
    repo = Path(__file__).resolve().parents[2]
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def ascii_at(pe, rva: int, limit: int = 120):
    off = pe.rva_to_file(rva)
    if off is None:
        return None
    raw = pe.data[off:off + limit]
    end = raw.find(b"\0")
    if end < 4:
        return None
    raw = raw[:end]
    if any(b < 0x20 or b > 0x7E for b in raw):
        return None
    return raw.decode("ascii", "replace")


def disassemble(md, pe, fn_rva: int, op_imm, op_mem, rip_reg):
    fn = pe.function_for(fn_rva)
    if fn is None:
        raise RuntimeError(f"no function for 0x{fn_rva:X}")
    rows = []
    for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + fn["begin"]):
        row = {"rva": ins.address - IMAGE_BASE, "bytes": ins.bytes.hex(), "mnemonic": ins.mnemonic, "op_str": ins.op_str}
        rip_targets = []
        immediates = []
        for op in ins.operands:
            if op.type == op_imm:
                v = op.imm
                if IMAGE_BASE <= v < IMAGE_BASE + pe.size_of_image:
                    v -= IMAGE_BASE
                immediates.append(v)
            elif op.type == op_mem and op.mem.base == rip_reg:
                t = ins.address + ins.size + op.mem.disp - IMAGE_BASE
                rip_targets.append(t)
        if immediates:
            row["immediates"] = immediates
        if rip_targets:
            row["rip_targets"] = rip_targets
            strings = []
            for t in rip_targets:
                s = ascii_at(pe, t)
                if s:
                    strings.append({"rva": t, "ascii": s})
            if strings:
                row["ascii_targets"] = strings
        rows.append(row)
    return {"begin": fn["begin"], "end": fn["end"], "instructions": rows}


def window(rows, center_rva: int, before=30, after=12):
    idx = next((i for i, r in enumerate(rows) if r["rva"] == center_rva), None)
    if idx is None:
        return []
    return rows[max(0, idx-before):min(len(rows), idx+after+1)]


def stack_arg_writes(rows, call_rva: int):
    idx = next(i for i, r in enumerate(rows) if r["rva"] == call_rva)
    out = {}
    for disp in (0x20, 0x28, 0x30, 0x38):
        needle_a = f"[rsp + 0x{disp:x}]"
        needle_b = f"[rsp + {disp}]"
        hit = None
        for r in reversed(rows[max(0, idx-160):idx]):
            if r["mnemonic"] in ("mov", "lea") and (needle_a in r["op_str"] or needle_b in r["op_str"]):
                if r["op_str"].startswith(("dword ptr [rsp", "qword ptr [rsp", "word ptr [rsp", "byte ptr [rsp")):
                    hit = r
                    break
        out[f"rsp_plus_{disp:02x}"] = hit
    return out


def written_register(op_str: str):
    if not op_str:
        return None
    dest = op_str.split(",", 1)[0].strip()
    if dest in ("rax","eax","ax","al","rbx","ebx","bx","bl","rcx","ecx","cx","cl","rdx","edx","dx","dl","rsi","esi","si","sil","rdi","edi","di","dil","r8","r8d","r8w","r9","r9d","r9w","r10","r10d","r11","r11d","r12","r12d","r13","r13d","r14","r14d","r15","r15d"):
        return dest
    return None


def normalize_reg(reg: str | None):
    if not reg:
        return None
    groups = {
        "rax": {"rax","eax","ax","al"}, "rbx": {"rbx","ebx","bx","bl"},
        "rcx": {"rcx","ecx","cx","cl"}, "rdx": {"rdx","edx","dx","dl"},
        "rsi": {"rsi","esi","si","sil"}, "rdi": {"rdi","edi","di","dil"},
        "r8": {"r8","r8d","r8w"}, "r9": {"r9","r9d","r9w"},
        "r10": {"r10","r10d"}, "r11": {"r11","r11d"}, "r12": {"r12","r12d"},
        "r13": {"r13","r13d"}, "r14": {"r14","r14d"}, "r15": {"r15","r15d"},
    }
    for root, names in groups.items():
        if reg in names:
            return root
    return reg


def trace_stack_source(rows, call_rva: int, stack_write):
    if not stack_write:
        return {"stack_write": None, "register_source": None}
    parts = stack_write["op_str"].split(",", 1)
    if len(parts) != 2:
        return {"stack_write": stack_write, "register_source": None}
    src = parts[1].strip()
    root = normalize_reg(src)
    if root == src and not re.fullmatch(r"r(?:1[0-5]|[8-9]|[abcd]x|si|di)|e(?:ax|bx|cx|dx|si|di)|[abcd][xl]|[sd]il?", src):
        return {"stack_write": stack_write, "source_literal": src, "register_source": None}
    idx = next(i for i, r in enumerate(rows) if r["rva"] == stack_write["rva"])
    source = None
    chain = []
    for r in reversed(rows[max(0, idx-100):idx]):
        dest = normalize_reg(written_register(r["op_str"]))
        if dest == root:
            source = r
            chain.append(r)
            break
    return {"stack_write": stack_write, "source_register": root, "register_source": source, "chain": chain}


def rbx_provenance(rows):
    idx = next(i for i, r in enumerate(rows) if r["rva"] == REGISTRY_SOURCE)
    writes = []
    for r in rows[:idx]:
        dest = normalize_reg(written_register(r["op_str"]))
        if dest == "rbx":
            writes.append(r)
    last = writes[-1] if writes else None
    return {
        "last_rbx_write": last,
        "recent_rbx_writes": writes[-12:],
        "source_window": window(rows, last["rva"], 28, 18) if last else [],
        "registry_window": window(rows, REGISTRY_SOURCE, 32, 24),
    }


def callers(con, dest: int):
    return [{"site": a, "source_function": b, "kind": c} for a,b,c in con.execute(
        "SELECT site,src_fn,kind FROM edges WHERE dest=? ORDER BY site", (dest,)
    )]


def self_test():
    assert CANONICAL_BUILDER_CALL < CANONICAL_LOADER_CALL
    assert REGISTRY_SOURCE + 8 == REGISTRY_STORE
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path):
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA mismatch: {digest}")
    pe_mod = load_pe_module(); pe = pe_mod.PE(exe.read_bytes())
    Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    md = Cs(arch, mode); md.detail = True

    canonical = disassemble(md, pe, CANONICAL_OWNER, op_imm, op_mem, rip_reg)
    registry = disassemble(md, pe, REGISTRY_OWNER, op_imm, op_mem, rip_reg)
    crows = canonical["instructions"]; rrows = registry["instructions"]

    builder_present = any(r["rva"] == CANONICAL_BUILDER_CALL and DESCRIPTOR_BUILDER in r.get("immediates", []) for r in crows)
    loader_present = any(r["rva"] == CANONICAL_LOADER_CALL and LOADER in r.get("immediates", []) for r in crows)
    registry_present = any(r["rva"] == REGISTRY_SOURCE and "[rbx + 0x24]" in r["op_str"] for r in rrows)

    stack_writes = stack_arg_writes(crows, CANONICAL_BUILDER_CALL)
    arg7 = trace_stack_source(crows, CANONICAL_BUILDER_CALL, stack_writes["rsp_plus_30"])
    rbx = rbx_provenance(rrows)

    with sqlite3.connect(db) as con:
        incoming = {
            "canonical_owner": callers(con, CANONICAL_OWNER),
            "registry_owner": callers(con, REGISTRY_OWNER),
        }

    stable_slot_candidate = arg7.get("stack_write") is not None and "0xffffffff" not in arg7["stack_write"].get("op_str", "")
    status = "PASS_CANONICAL_LOADER_RECORD_TRACE" if builder_present and loader_present and registry_present else "BLOCKED_CANONICAL_LOADER_RECORD_TRACE"

    return {
        "schema": 1,
        "analysis": "gow_canonical_loader_record",
        "status": status,
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "canonical_path": {
            "owner": CANONICAL_OWNER,
            "builder_call": CANONICAL_BUILDER_CALL,
            "loader_call": CANONICAL_LOADER_CALL,
            "builder_present": builder_present,
            "loader_present": loader_present,
            "builder_call_window": window(crows, CANONICAL_BUILDER_CALL, 70, 35),
            "loader_call_window": window(crows, CANONICAL_LOADER_CALL, 30, 20),
            "stack_argument_writes": stack_writes,
            "arg7_slot_provenance": arg7,
            "stable_slot_candidate": stable_slot_candidate,
        },
        "registry_record": {
            "owner": REGISTRY_OWNER,
            "source_site": REGISTRY_SOURCE,
            "store_site": REGISTRY_STORE,
            "registry_source_present": registry_present,
            "rbx_provenance": rbx,
        },
        "incoming_callers": incoming,
        "precise_missing_edge": "connect canonical 0x858320 builder arg7 slot source and 0x82CF00 RBX record provenance to the same WAD/catalogue record identity",
        "safety": {"analysis_mode": "read-only", "game_launched": False, "active_save_opened": False, "frozen_save_opened": False, "save_or_progression_written": False, "exe_written": False},
    }


def render_text(r):
    arg7 = r["canonical_path"]["arg7_slot_provenance"]
    rbx = r["registry_record"]["rbx_provenance"]
    return "\n".join([
        "GoW canonical loader record trace",
        "=================================",
        f"status={r['status']}",
        f"gameobject_persistent_key_status={r['gameobject_persistent_key_status']}",
        f"canonical_owner=0x{r['canonical_path']['owner']:X}",
        f"builder_call=0x{r['canonical_path']['builder_call']:X}",
        f"loader_call=0x{r['canonical_path']['loader_call']:X}",
        f"stable_slot_candidate={str(r['canonical_path']['stable_slot_candidate']).lower()}",
        f"arg7_stack_write={arg7.get('stack_write')}",
        f"arg7_register_source={arg7.get('register_source')}",
        f"last_rbx_write={rbx.get('last_rbx_write')}",
        f"precise_missing_edge={r['precise_missing_edge']}",
        "",
    ])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--exe", type=Path); p.add_argument("--db", type=Path)
    p.add_argument("--output-json", type=Path); p.add_argument("--output-text", type=Path)
    a = p.parse_args()
    if a.self_test:
        self_test(); return 0
    if any(x is None for x in (a.exe, a.db, a.output_json, a.output_text)):
        p.error("--exe, --db, --output-json and --output-text required")
    r = analyze(a.exe, a.db)
    a.output_json.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    a.output_text.write_text(render_text(r), encoding="utf-8")
    print(r["status"]); print(r["gameobject_persistent_key_status"]); print(r["production_oracle_status"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
