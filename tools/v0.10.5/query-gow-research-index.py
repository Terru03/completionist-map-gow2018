"""Query the local God of War static research SQLite index.

The expensive native/Lua scan is performed once by build-gow-research-index.py.
This tool turns later reverse-engineering questions into fast local lookups.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


def parse_int(value: str) -> int:
    return int(value, 0)


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def function_report(con, rva: int):
    fn = con.execute("SELECT * FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1", (rva, rva)).fetchone()
    if not fn:
        return {"query_rva": rva, "function": None}
    begin, end, size, section = fn
    return {
        "query_rva": rva,
        "function": {"begin": begin, "end": end, "size": size, "section": section},
        "callers": rows(con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest BETWEEN ? AND ? ORDER BY site", (begin, end-1))),
        "callees": rows(con.execute("SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (begin,))),
        "indirect_calls": rows(con.execute("SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site", (begin,))),
        "rip_refs": rows(con.execute("SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? ORDER BY site", (begin,))),
        "mem_refs": rows(con.execute("SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE src_fn=? ORDER BY site", (begin,))),
        "imm_refs": rows(con.execute("SELECT site,mnemonic,value_rva,target_section FROM imm_refs WHERE src_fn=? ORDER BY site", (begin,))),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--function", type=parse_int)
    g.add_argument("--callers", type=parse_int)
    g.add_argument("--callees", type=parse_int)
    g.add_argument("--disp", type=parse_int)
    g.add_argument("--string")
    g.add_argument("--string-contains")
    g.add_argument("--rip-target", type=parse_int)
    g.add_argument("--lua")
    g.add_argument("--file-contains")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"index database not found: {db}")
    con = sqlite3.connect(db)
    con.row_factory = None

    if args.function is not None:
        result = function_report(con, args.function)
    elif args.callers is not None:
        result = {"target": args.callers, "rows": rows(con.execute(
            "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest=? OR target_fn=? ORDER BY site LIMIT ?",
            (args.callers, args.callers, args.limit),
        ))}
    elif args.callees is not None:
        fn = function_report(con, args.callees)
        result = {"source": args.callees, "function": fn.get("function"), "rows": fn.get("callees", [])}
    elif args.disp is not None:
        result = {"disp": args.disp, "rows": rows(con.execute(
            "SELECT site,src_fn,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE disp=? ORDER BY src_fn,site LIMIT ?",
            (args.disp, args.limit),
        ))}
    elif args.string is not None:
        result = {"string": args.string, "strings": rows(con.execute(
            "SELECT rva,text FROM strings WHERE text=? ORDER BY rva LIMIT ?", (args.string, args.limit)
        ))}
        refs = []
        for s in result["strings"]:
            refs.extend(rows(con.execute(
                "SELECT site,src_fn,mnemonic,target,target_section FROM rip_refs WHERE target=? ORDER BY site LIMIT ?",
                (s["rva"], args.limit),
            )))
        result["refs"] = refs[:args.limit]
    elif args.string_contains is not None:
        q = f"%{args.string_contains}%"
        result = {"contains": args.string_contains, "rows": rows(con.execute(
            "SELECT rva,text FROM strings WHERE text LIKE ? ORDER BY rva LIMIT ?", (q, args.limit)
        ))}
    elif args.rip_target is not None:
        result = {"target": args.rip_target, "rows": rows(con.execute(
            "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site LIMIT ?",
            (args.rip_target, args.limit),
        ))}
    elif args.lua is not None:
        q = f"%{args.lua}%"
        result = {"lua": args.lua, "rows": rows(con.execute(
            "SELECT path,line,text FROM lua_hits WHERE text LIKE ? ORDER BY path,line LIMIT ?", (q, args.limit)
        ))}
    else:
        q = f"%{args.file_contains}%"
        result = {"file_contains": args.file_contains, "rows": rows(con.execute(
            "SELECT path,size,ext FROM game_files WHERE path LIKE ? ORDER BY path LIMIT ?", (q, args.limit)
        ))}

    con.close()
    text = json.dumps(result, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
