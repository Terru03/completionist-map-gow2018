"""Extend the reusable GoW SQLite index with MSVC x64 RTTI/vtables.

Uses the already-built static data_ptrs table. It parses valid Complete Object
Locators (COLs), TypeDescriptor names, and contiguous executable vtable slots,
then stores them in SQLite. This is a one-time reusable index extension, not a
single-address probe.

Read-only with respect to the game and saves. Writes only to the local research
SQLite database and requested report files.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
PERSISTENCE_TARGETS = {
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_thunk": 0x5B2280,
    "on_unpickle_internal": 0x5B2324,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pe_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_cstr(pe, rva: int, max_len: int = 512):
    off = pe.rva_to_file(rva)
    if off is None:
        return None
    end = min(len(pe.data), off + max_len)
    z = pe.data.find(b"\0", off, end)
    if z < 0:
        return None
    raw = pe.data[off:z]
    if not raw:
        return ""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 or ord(c) > 0x7E for c in text):
        return None
    return text


def parse_col(pe, col_rva: int):
    off = pe.rva_to_file(col_rva)
    if off is None or off + 24 > len(pe.data):
        return None
    sig, offset, cd_offset, type_rva, class_rva, self_rva = struct.unpack_from("<IIIIII", pe.data, off)
    if sig != 1 or self_rva != col_rva:
        return None
    if pe.section_for_rva(type_rva) is None or pe.section_for_rva(class_rva) is None:
        return None
    # MSVC x64 TypeDescriptor: two 8-byte fields, then decorated name.
    name = read_cstr(pe, type_rva + 16)
    if not name or not name.startswith("."):
        return None
    return {
        "col_rva": col_rva,
        "offset": offset,
        "cd_offset": cd_offset,
        "type_rva": type_rva,
        "class_desc_rva": class_rva,
        "name": name,
    }


def ensure_schema(con: sqlite3.Connection):
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS rtti_cols(
            col_rva INTEGER PRIMARY KEY,
            type_rva INTEGER NOT NULL,
            class_desc_rva INTEGER NOT NULL,
            object_offset INTEGER NOT NULL,
            cd_offset INTEGER NOT NULL,
            decorated_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rtti_vtables(
            vtable_rva INTEGER PRIMARY KEY,
            col_pointer_rva INTEGER NOT NULL,
            col_rva INTEGER NOT NULL,
            decorated_name TEXT NOT NULL,
            slot_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rtti_vslots(
            vtable_rva INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,
            slot_rva INTEGER NOT NULL,
            target_rva INTEGER NOT NULL,
            target_function INTEGER,
            PRIMARY KEY(vtable_rva, slot_index)
        );
        CREATE INDEX IF NOT EXISTS idx_rtti_vslots_target ON rtti_vslots(target_rva);
        CREATE INDEX IF NOT EXISTS idx_rtti_vtables_name ON rtti_vtables(decorated_name);
        """
    )
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    exe = Path(args.exe)
    db = Path(args.db)
    if not exe.is_file():
        raise SystemExit(f"missing exe: {exe}")
    if sha256(exe).lower() != EXPECTED_SHA256:
        raise SystemExit("unsupported GoW.exe SHA256")
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")

    base = load_pe_module()
    pe = base.PE(exe.read_bytes())
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "data_ptrs" not in tables:
        raise SystemExit("data_ptrs missing; run static pointer extension first")
    ensure_schema(con)
    con.execute("DELETE FROM rtti_vslots")
    con.execute("DELETE FROM rtti_vtables")
    con.execute("DELETE FROM rtti_cols")

    # Candidate COLs are image pointers stored in non-executable sections whose
    # target is also non-executable. Parse/validate instead of blindly scanning.
    candidate_cols = sorted({r[0] for r in con.execute(
        "SELECT DISTINCT value_rva FROM data_ptrs WHERE target_exec=0"
    )})
    cols = {}
    for rva in candidate_cols:
        rec = parse_col(pe, rva)
        if rec:
            cols[rva] = rec
            con.execute(
                "INSERT INTO rtti_cols VALUES(?,?,?,?,?,?)",
                (rva, rec["type_rva"], rec["class_desc_rva"], rec["offset"], rec["cd_offset"], rec["name"]),
            )

    vtables = []
    for col_rva, rec in cols.items():
        for (loc,) in con.execute(
            "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva", (col_rva,)
        ).fetchall():
            vtable = loc + 8
            first = con.execute(
                "SELECT target_exec FROM data_ptrs WHERE location_rva=?", (vtable,)
            ).fetchone()
            if not first or first[0] != 1:
                continue
            slots = []
            for i in range(128):
                slot_rva = vtable + i * 8
                row = con.execute(
                    "SELECT value_rva,target_exec,target_function FROM data_ptrs WHERE location_rva=?", (slot_rva,)
                ).fetchone()
                if not row or row[1] != 1:
                    break
                slots.append({"slot_index": i, "slot_rva": slot_rva, "target_rva": row[0], "target_function": row[2]})
            if len(slots) < 2:
                continue
            con.execute(
                "INSERT OR REPLACE INTO rtti_vtables VALUES(?,?,?,?,?)",
                (vtable, loc, col_rva, rec["name"], len(slots)),
            )
            for s in slots:
                con.execute(
                    "INSERT OR REPLACE INTO rtti_vslots VALUES(?,?,?,?,?)",
                    (vtable, s["slot_index"], s["slot_rva"], s["target_rva"], s["target_function"]),
                )
            vtables.append({
                "vtable_rva": vtable,
                "col_pointer_rva": loc,
                "col_rva": col_rva,
                "decorated_name": rec["name"],
                "slot_count": len(slots),
                "slots": slots,
            })

    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('msvc_rtti_index_complete','1')")
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('msvc_rtti_col_count',?)", (str(len(cols)),))
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('msvc_rtti_vtable_count',?)", (str(len(vtables)),))
    con.commit()

    persistence_hits = []
    target_values = set(PERSISTENCE_TARGETS.values())
    for vt in vtables:
        hits = [s for s in vt["slots"] if s["target_rva"] in target_values]
        if hits:
            persistence_hits.append({**vt, "persistence_slots": hits})

    # Exact known vtable neighborhood discovered from static pointer analysis.
    known_vtable = next((v for v in vtables if v["vtable_rva"] == 0xE04018), None)

    result = {
        "schema": 1,
        "analysis": "gow_msvc_rtti_vtable_index",
        "exe_sha256": EXPECTED_SHA256,
        "col_count": len(cols),
        "vtable_count": len(vtables),
        "persistence_vtables": persistence_hits,
        "known_persistence_vtable_E04018": known_vtable,
        "game_launched": False,
        "save_opened": False,
        "exe_modified": False,
    }
    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - MSVC RTTI/vtable reusable index extension",
        f"exe_sha256={EXPECTED_SHA256}",
        f"col_count={len(cols)}",
        f"vtable_count={len(vtables)}",
        f"persistence_vtable_count={len(persistence_hits)}",
        "",
        "PERSISTENCE VTABLES",
    ]
    for i, vt in enumerate(persistence_hits, 1):
        lines.append(
            f"#{i} vtable=0x{vt['vtable_rva']:X} col=0x{vt['col_rva']:X} name={vt['decorated_name']!r} slots={vt['slot_count']}"
        )
        for s in vt["persistence_slots"]:
            labels = [k for k,v in PERSISTENCE_TARGETS.items() if v == s["target_rva"]]
            lines.append(
                f"    SLOT index={s['slot_index']} offset=0x{s['slot_index']*8:X} address=0x{s['slot_rva']:X} -> 0x{s['target_rva']:X} labels={labels}"
            )
        for s in vt["slots"]:
            lines.append(
                f"    VFUNC index={s['slot_index']} offset=0x{s['slot_index']*8:X} -> 0x{s['target_rva']:X} fn={'NONE' if s['target_function'] is None else f'0x{s['target_function']:X}'}"
            )
    if known_vtable is None:
        lines += ["", "KNOWN E04018 VTABLE: not recognized by RTTI parser"]
    else:
        lines += ["", f"KNOWN E04018 VTABLE CLASS={known_vtable['decorated_name']!r} COL=0x{known_vtable['col_rva']:X}"]
    Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")
    con.close()

    print("GOW_MSVC_RTTI_INDEX_EXTENSION_PASSED")
    print(f"col_count={len(cols)}")
    print(f"vtable_count={len(vtables)}")
    print(f"persistence_vtable_count={len(persistence_hits)}")
    if known_vtable:
        print(f"known_E04018_class={known_vtable['decorated_name']}")


if __name__ == "__main__":
    main()
