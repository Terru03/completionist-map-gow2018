"""Extend the reusable GoW research SQLite index with static PE data pointers.

The original index is instruction-centric.  Native callback registries, vtables,
class descriptors, and registration arrays frequently store function addresses
in .rdata/.data without any code immediate/RIP reference to the target function.
This one-time extension indexes aligned 64-bit image pointers from non-executable
PE sections into SQLite so later analyses remain database-only.

Read-only with respect to GoW.exe, game data, and saves.  The only write is to
the local .research-index SQLite database and requested report files.
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

TARGETS = {
    "core_pickle_unpickle": 0x5AECC7,
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "restore_dispatch": 0x5AD4A0,
    "byte_serializer": 0x7E7F10,
    "userdata_serializer": 0x7E9190,
    "userdata_serializer_helper": 0x7E9340,
    "gameobject_token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
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


def section_name(pe, rva: int):
    sec = pe.section_for_rva(rva)
    return sec["name"] if sec else None


def fn_begin(pe, rva: int):
    fn = pe.function_for(rva)
    return fn["begin"] if fn else None


def ensure_schema(con: sqlite3.Connection):
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_ptrs(
            location_rva INTEGER PRIMARY KEY,
            location_section TEXT NOT NULL,
            value_rva INTEGER NOT NULL,
            target_section TEXT,
            target_exec INTEGER NOT NULL,
            target_function INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_data_ptrs_value ON data_ptrs(value_rva);
        CREATE INDEX IF NOT EXISTS idx_data_ptrs_target_fn ON data_ptrs(target_function);
        CREATE INDEX IF NOT EXISTS idx_data_ptrs_location_section ON data_ptrs(location_section);
        """
    )
    con.commit()


def scan_data_pointers(pe):
    rows = []
    scanned_bytes = 0
    for sec in pe.sections:
        if sec["exec"] or sec["rawsize"] <= 0:
            continue
        raw_start = sec["raw"]
        raw_end = min(len(pe.data), raw_start + sec["rawsize"])
        scanned_bytes += max(0, raw_end - raw_start)
        # Windows x64 static pointer tables/descriptors are naturally 8-byte
        # aligned.  Align by RVA rather than raw file offset.
        first_delta = (-sec["rva"]) & 7
        off = raw_start + first_delta
        while off + 8 <= raw_end:
            value = struct.unpack_from("<Q", pe.data, off)[0]
            if pe.image_base <= value < pe.image_base + pe.size_of_image:
                value_rva = value - pe.image_base
                target_sec = pe.section_for_rva(value_rva)
                if target_sec is not None:
                    loc_rva = sec["rva"] + (off - raw_start)
                    rows.append((
                        loc_rva,
                        sec["name"],
                        value_rva,
                        target_sec["name"],
                        1 if target_sec["exec"] else 0,
                        fn_begin(pe, value_rva) if target_sec["exec"] else None,
                    ))
            off += 8
    return rows, scanned_bytes


def refs_for_target(con: sqlite3.Connection, target: int):
    cur = con.execute(
        """
        SELECT d.location_rva,d.location_section,d.value_rva,d.target_section,
               d.target_exec,d.target_function,s.text AS location_string
        FROM data_ptrs d
        LEFT JOIN strings s ON s.rva=d.location_rva
        WHERE d.value_rva=?
        ORDER BY d.location_rva
        """,
        (target,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def neighborhood(con: sqlite3.Connection, location: int, radius: int = 0x80):
    cur = con.execute(
        """
        SELECT d.location_rva,d.location_section,d.value_rva,d.target_section,
               d.target_exec,d.target_function,s.text AS target_string
        FROM data_ptrs d
        LEFT JOIN strings s ON s.rva=d.value_rva
        WHERE d.location_rva BETWEEN ? AND ?
        ORDER BY d.location_rva
        """,
        (location - radius, location + radius),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


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
    ensure_schema(con)

    # Rebuild deterministically so reruns are safe after schema/tool changes.
    con.execute("DELETE FROM data_ptrs")
    rows, scanned_bytes = scan_data_pointers(pe)
    con.executemany(
        "INSERT INTO data_ptrs(location_rva,location_section,value_rva,target_section,target_exec,target_function) VALUES(?,?,?,?,?,?)",
        rows,
    )
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('data_ptr_index_complete','1')")
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('data_ptr_count',?)", (str(len(rows)),))
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('data_ptr_scanned_bytes',?)", (str(scanned_bytes),))
    con.commit()

    refs = {name: refs_for_target(con, rva) for name, rva in TARGETS.items()}
    neighborhoods = {}
    for name, matches in refs.items():
        neighborhoods[name] = [
            {"location_rva": m["location_rva"], "entries": neighborhood(con, m["location_rva"])}
            for m in matches[:50]
        ]

    # Rank static pointer clusters that contain two or more persistence targets.
    clusters = {}
    for name, matches in refs.items():
        for m in matches:
            bucket = m["location_rva"] // 0x100
            row = clusters.setdefault(bucket, {"base": bucket * 0x100, "targets": set(), "locations": []})
            row["targets"].add(name)
            row["locations"].append({"target": name, "location_rva": m["location_rva"]})
    cluster_rows = []
    for c in clusters.values():
        c["targets"] = sorted(c["targets"])
        c["locations"] = sorted(c["locations"], key=lambda x: x["location_rva"])
        if len(c["targets"]) >= 2:
            cluster_rows.append(c)
    cluster_rows.sort(key=lambda x: (-len(x["targets"]), x["base"]))

    result = {
        "schema": 1,
        "analysis": "gow_static_data_pointer_index",
        "exe_sha256": EXPECTED_SHA256,
        "scanned_nonexec_bytes": scanned_bytes,
        "data_pointer_count": len(rows),
        "target_refs": refs,
        "target_neighborhoods": neighborhoods,
        "multi_target_clusters": cluster_rows[:100],
        "game_launched": False,
        "save_opened": False,
        "exe_modified": False,
    }
    con.close()

    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = [
        "Completionist Map - static PE data-pointer extension for reusable SQLite index",
        f"exe_sha256={EXPECTED_SHA256}",
        f"scanned_nonexec_bytes={scanned_bytes}",
        f"data_pointer_count={len(rows)}",
        "",
        "TARGET STATIC POINTER REFERENCES",
    ]
    for name, rva in TARGETS.items():
        matches = refs[name]
        lines.append(f"- {name} 0x{rva:X}: {len(matches)} static pointer(s)")
        for m in matches[:20]:
            lines.append(
                f"    PTR location=0x{m['location_rva']:X} section={m['location_section']} "
                f"target_fn={'NONE' if m['target_function'] is None else f'0x{m['target_function']:X}'}"
            )
            for n in neighborhood(con, m["location_rva"], 0x40) if False else []:
                pass
    lines += ["", "MULTI-TARGET POINTER CLUSTERS"]
    for i, c in enumerate(cluster_rows[:50], 1):
        lines.append(f"#{i} base=0x{c['base']:X} targets={c['targets']}")
        for x in c["locations"]:
            lines.append(f"    0x{x['location_rva']:X} -> {x['target']}")
    Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("GOW_DATA_POINTER_INDEX_EXTENSION_PASSED")
    print(f"data_pointer_count={len(rows)}")
    for name in TARGETS:
        print(f"{name}_static_ptrs={len(refs[name])}")


if __name__ == "__main__":
    main()
