"""Correlate static PE pointer tables with GoW persistence/GameObject ownership.

Requires the reusable SQLite index plus the data_ptrs extension. This is a pure
SQLite query: it does not rescan GoW.exe. It joins static .rdata/.data pointers
with indexed strings, RIP references, functions, call edges, and known native
persistence anchors to identify registration tables/class descriptors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

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
STRING_TARGETS = (
    "GameObject",
    "__codesideluaclass",
    "OnPickleInternal",
    "OnUnpickleInternal",
    "__PickleTable",
    "__SoftPickleTable",
    "core.pickle",
    "Pickle",
    "Unpickle",
)
INTERESTING_TERMS = (
    "gameobject", "pickle", "unpickle", "serialize", "deserialize",
    "checkpoint", "restore", "codesideluaclass", "guid", "wad",
)


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def ptr_refs(con, rva):
    return rows(con.execute(
        "SELECT location_rva,location_section,value_rva,target_section,target_exec,target_function "
        "FROM data_ptrs WHERE value_rva=? ORDER BY location_rva", (rva,)
    ))


def pointer_neighborhood(con, location, radius=0x100):
    return rows(con.execute(
        "SELECT d.location_rva,d.location_section,d.value_rva,d.target_section,d.target_exec,d.target_function,"
        "s.text AS target_string FROM data_ptrs d LEFT JOIN strings s ON s.rva=d.value_rva "
        "WHERE d.location_rva BETWEEN ? AND ? ORDER BY d.location_rva",
        (location-radius, location+radius),
    ))


def code_refs_to_window(con, lo, hi):
    return rows(con.execute(
        "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs "
        "WHERE target BETWEEN ? AND ? ORDER BY src_fn,site", (lo, hi)
    ))


def fn_strings(con, fn):
    return rows(con.execute(
        "SELECT site,target,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",
        (fn,),
    ))


def fn_calls(con, fn):
    return rows(con.execute(
        "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (fn,)
    ))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")
    con = sqlite3.connect(db)

    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "data_ptrs" not in tables:
        raise SystemExit("data_ptrs table missing; run pointer extension first")
    meta = dict(con.execute("SELECT key,value FROM meta").fetchall())
    if meta.get("data_ptr_index_complete") != "1":
        raise SystemExit("data pointer index is not marked complete")

    # Resolve named string RVAs from the existing string index.
    string_rvas = {}
    for text in STRING_TARGETS:
        hit = con.execute("SELECT rva FROM strings WHERE text=? ORDER BY rva LIMIT 1", (text,)).fetchone()
        string_rvas[text] = hit[0] if hit else None

    target_ptrs = {name: ptr_refs(con, rva) for name, rva in TARGETS.items()}
    string_ptrs = {text: (ptr_refs(con, rva) if rva is not None else []) for text, rva in string_rvas.items()}

    # Every exact static reference becomes a candidate descriptor/table center.
    seeds = []
    for name, refs in target_ptrs.items():
        for ref in refs:
            seeds.append((ref["location_rva"], f"fn:{name}"))
    for text, refs in string_ptrs.items():
        for ref in refs:
            seeds.append((ref["location_rva"], f"str:{text}"))

    # Deduplicate nearby seeds into 0x200-byte ownership windows.
    buckets = {}
    for loc, label in seeds:
        base = loc & ~0xFF
        b = buckets.setdefault(base, {"base": base, "labels": set(), "seed_locations": []})
        b["labels"].add(label)
        b["seed_locations"].append({"location": loc, "label": label})

    clusters = []
    owner_map = {}
    for b in buckets.values():
        lo, hi = b["base"] - 0x100, b["base"] + 0x1FF
        entries = rows(con.execute(
            "SELECT d.location_rva,d.location_section,d.value_rva,d.target_section,d.target_exec,d.target_function,"
            "s.text AS target_string FROM data_ptrs d LEFT JOIN strings s ON s.rva=d.value_rva "
            "WHERE d.location_rva BETWEEN ? AND ? ORDER BY d.location_rva", (lo, hi)
        ))
        refs = code_refs_to_window(con, lo, hi)
        owners = sorted({r["src_fn"] for r in refs if r["src_fn"] is not None})
        owner_details = []
        for fn in owners:
            strings = fn_strings(con, fn)
            interesting = [x for x in strings if any(t in (x["target_string"] or "").lower() for t in INTERESTING_TERMS)]
            calls = fn_calls(con, fn)
            owner_details.append({
                "function": fn,
                "table_refs": [r for r in refs if r["src_fn"] == fn],
                "interesting_strings": interesting[:30],
                "calls": calls[:100],
            })
            rec = owner_map.setdefault(fn, {"function": fn, "clusters": set(), "labels": set(), "refs": 0, "interesting_strings": {}})
            rec["clusters"].add(b["base"])
            rec["labels"].update(b["labels"])
            rec["refs"] += sum(1 for r in refs if r["src_fn"] == fn)
            for s in interesting:
                rec["interesting_strings"][s["target_string"]] = s["site"]
        clusters.append({
            "base": b["base"],
            "labels": sorted(b["labels"]),
            "seed_locations": sorted(b["seed_locations"], key=lambda x: x["location"]),
            "entries": entries,
            "code_refs": refs,
            "owners": owner_details,
        })

    # Prefer clusters combining GameObject/class-name evidence with persistence functions.
    def cluster_score(c):
        labels = c["labels"]
        fn_n = sum(x.startswith("fn:") for x in labels)
        str_n = sum(x.startswith("str:") for x in labels)
        go = int(any(x in labels for x in ("str:GameObject", "str:__codesideluaclass")))
        persistence = int(any(x.startswith("fn:") and x not in ("fn:gameobject_token_resolver", "fn:lua_gameobject_unbox", "fn:gameobject_token_packer") for x in labels))
        return go*500 + persistence*300 + fn_n*100 + str_n*60 + len(c["owners"])*40 + len(c["code_refs"])

    clusters.sort(key=lambda c: (-cluster_score(c), c["base"]))
    for c in clusters:
        c["score"] = cluster_score(c)

    owner_rows = []
    for rec in owner_map.values():
        labels = sorted(rec["labels"])
        score = 100*len(labels) + 40*len(rec["clusters"]) + 5*rec["refs"] + 25*len(rec["interesting_strings"])
        owner_rows.append({
            "function": rec["function"],
            "score": score,
            "clusters": sorted(rec["clusters"]),
            "labels": labels,
            "refs": rec["refs"],
            "interesting_strings": [{"text": k, "site": v} for k,v in sorted(rec["interesting_strings"].items())],
        })
    owner_rows.sort(key=lambda x: (-x["score"], x["function"]))

    result = {
        "schema": 1,
        "analysis": "gow_static_pointer_ownership",
        "index_meta": meta,
        "targets": TARGETS,
        "string_rvas": string_rvas,
        "target_static_ptrs": target_ptrs,
        "string_static_ptrs": string_ptrs,
        "ranked_clusters": clusters[:150],
        "ranked_owner_functions": owner_rows[:150],
        "exe_rescanned": False,
        "game_launched": False,
        "save_opened": False,
    }
    con.close()

    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = [
        "Completionist Map - static pointer ownership correlation",
        "exe_rescanned=false",
        f"data_ptr_count={meta.get('data_ptr_count','?')}",
        "",
        "EXACT STATIC POINTER COUNTS",
    ]
    for name, rva in TARGETS.items():
        lines.append(f"- {name} 0x{rva:X}: {len(target_ptrs[name])}")
        for ref in target_ptrs[name][:20]:
            lines.append(f"    0x{ref['location_rva']:X} [{ref['location_section']}]")
    lines += ["", "STRING DESCRIPTOR POINTER COUNTS"]
    for text in STRING_TARGETS:
        rva = string_rvas[text]
        lines.append(f"- {text!r}: rva={'NONE' if rva is None else f'0x{rva:X}'} ptrs={len(string_ptrs[text])}")
        for ref in string_ptrs[text][:20]:
            lines.append(f"    0x{ref['location_rva']:X} [{ref['location_section']}]")

    lines += ["", "TOP STATIC POINTER CLUSTERS"]
    for i,c in enumerate(clusters[:60], 1):
        lines.append(f"#{i} base=0x{c['base']:X} score={c['score']} labels={c['labels']} owners={len(c['owners'])}")
        for s in c["seed_locations"][:20]:
            lines.append(f"    SEED 0x{s['location']:X} {s['label']}")
        for o in c["owners"][:10]:
            lines.append(f"    OWNER fn=0x{o['function']:X} refs={len(o['table_refs'])} strings={[x['target_string'] for x in o['interesting_strings'][:8]]}")
        for e in c["entries"][:30]:
            extra = f" str={e['target_string']!r}" if e['target_string'] else ""
            tf = f" fn=0x{e['target_function']:X}" if e['target_function'] is not None else ""
            lines.append(f"    PTR 0x{e['location_rva']:X} -> 0x{e['value_rva']:X}{tf}{extra}")

    lines += ["", "TOP TABLE OWNER FUNCTIONS"]
    for i,o in enumerate(owner_rows[:60], 1):
        lines.append(f"#{i} fn=0x{o['function']:X} score={o['score']} labels={o['labels']} refs={o['refs']}")
        for s in o["interesting_strings"][:10]:
            lines.append(f"    STRING 0x{s['site']:X} {s['text']!r}")

    Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GOW_STATIC_POINTER_OWNERSHIP_ANALYSIS_PASSED")
    print(f"clusters={len(clusters)}")
    print(f"owners={len(owner_rows)}")


if __name__ == "__main__":
    main()
