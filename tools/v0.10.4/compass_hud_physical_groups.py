"""Read physical HUD roles; transform explicit slots without guessing aliases."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import struct


def load_module(filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_module("build-raven-compass-hud-three-payload.py")
check = BASE.check
REPO = Path(__file__).resolve().parents[2]
PEERS = ("DockPoint", "FastTravel", "Valkyrie", "MAIN", "SIDE")


def safe_output(path: Path, tree: Path) -> Path:
    path, tree = path.resolve(), tree.resolve()
    check(path != tree and path.is_relative_to(tree), f"output must stay below {tree}: {path}")
    check(not path.is_dir(), f"output is directory: {path}")
    check(not path.exists() or path.stat().st_nlink == 1, f"output has hard links: {path}")
    return path


def group_roles(records: list[dict], target: int) -> list[dict]:
    check(0 <= target < len(records), "target index out of bounds")
    payload = records[target]
    check(payload["kind"] == 1 and bool(payload["data"]), "target must be payload")
    start = payload["parent"]
    check(start is not None and 0 <= start < target and records[start]["kind"] == 2,
          "target must have containing group")
    roles, stack = [], []
    for index in range(start, len(records)):
        row = records[index]
        kind, data = row["kind"], row["data"]
        if index != start:
            check(stack and row["parent"] == stack[-1], f"parent mismatch at {index}")
        if kind == 2:
            check(not data and row["flags"] == 0, "group start has data or flags")
            role = "group_start" if index == start else "nested_group_start"
            depth = len(stack)
            stack.append(index)
        elif kind == 3:
            check(stack and not data and row["flags"] == 0, "invalid group end")
            stack.pop()
            depth = len(stack)
            role = "group_end" if not stack else "nested_group_end"
        else:
            check(kind == 1, f"unsupported record kind {kind}")
            depth = len(stack)
            if index == target:
                role = "target_payload"
            elif data:
                role = "auxiliary_payload" if depth == 1 else "nested_payload"
            else:
                check(row["flags"] == 0, f"zero-data resource has flags at {index}")
                role = "dependency_link" if depth == 1 else "nested_dependency_link"
        roles.append({"index": index, "relative_index": index - start,
                      "depth": depth, "role": role})
        if not stack:
            check(start < target < index, "target outside group")
            return roles
    raise ValueError("group has no matching end")


def first_dword(row: dict) -> int | None:
    return struct.unpack_from("<I", row["data"])[0] if len(row["data"]) >= 4 else None


def validate_hud_group(records: list[dict], target: int, resource_role: str) -> dict:
    roles = group_roles(records, target)
    layouts = {
        "model": ["group_start", "target_payload", "dependency_link", "dependency_link", "group_end"],
        "prototype": ["group_start", "target_payload", "dependency_link", "auxiliary_payload", "group_end"],
        "root": ["group_start", "target_payload", "group_end"],
    }
    check(resource_role in layouts, f"unknown HUD role {resource_role}")
    check([r["role"] for r in roles] == layouts[resource_role], f"{resource_role} grammar changed")
    rows = [records[r["index"]] for r in roles]
    check(rows[0]["parent"] is None, "HUD grammar requires top-level group")
    shapes = {"model": (0x8E, 80, 0x1002000C),
              "prototype": (0x3D, 1184, 0x10001), "root": (0x3D, 164, 0x20001)}
    payload = records[target]
    check((payload["flags"], len(payload["data"]), first_dword(payload)) == shapes[resource_role],
          f"{resource_role} payload shape changed")
    if resource_role == "prototype":
        script = rows[3]
        check((script["flags"], len(script["data"]), first_dword(script)) == (0x18, 96, 0x10005),
              "prototype auxiliary script shape changed")
        data = payload["data"]
        check(struct.unpack_from("<H", data, 0xC)[0] == 2, "prototype node count changed")
        check(struct.unpack_from("<I", data, 0x18)[0] == 0x3A8, "prototype ID table offset changed")
        check(bytes(data[0x3A8:0x3B8]) == payload["id"], "prototype self-ID slot changed")
    return {"start": roles[0]["index"], "end": roles[-1]["index"],
            "physical_count": len(rows), "payload_count": sum(bool(r["data"]) for r in rows),
            "roles": [r["role"] for r in roles]}


def clone_resource(records: list[dict], target: int, new_name: str, new_id: bytes,
                   *, links: dict | None = None, inline: dict | None = None) -> list[dict]:
    """Clone whole scope; caller supplies proven local slots. No name/ID sweep."""
    roles = group_roles(records, target)
    start = roles[0]["index"]
    clone = copy.deepcopy(records[start:roles[-1]["index"] + 1])
    check(len(new_id) == 16 and len(new_name.encode("ascii")) <= 55, "invalid clone identity")
    payload = clone[target - start]
    if payload["flags"] == 0x3D and first_dword(payload) == 0x20001:
        check(len(payload["data"]) == 164, "root payload shape changed")
        old_name_field = payload["name"].encode("ascii").ljust(56, b"\0")
        check(bytes(payload["data"][0x1C:0x54]) == old_name_field, "root internal name differs")
        payload["data"][0x1C:0x54] = new_name.encode("ascii").ljust(56, b"\0")
    payload["name"], payload["id"] = new_name, new_id
    for relative, (old_id, name, new_link_id) in (links or {}).items():
        check(0 <= relative < len(roles) and roles[relative]["role"] == "dependency_link",
              "retarget requires local dependency link")
        row = clone[relative]
        check(row["id"] == old_id and len(new_link_id) == 16, "local dependency ID mismatch")
        check(len(name.encode("ascii")) <= 55, "dependency name too long")
        row["name"], row["id"] = name, new_link_id
    changed = set()
    for offset, (old_id, replacement) in (inline or {}).items():
        check(len(old_id) == len(replacement) == 16, "inline ID width changed")
        check(0 <= offset <= len(payload["data"]) - 16, "inline ID offset out of bounds")
        span = set(range(offset, offset + 16))
        check(not changed.intersection(span), "inline ID slots overlap")
        check(bytes(payload["data"][offset:offset + 16]) == old_id, "inline source ID mismatch")
        payload["data"][offset:offset + 16] = replacement
        changed.update(span)
    for row in clone:
        row["original_offset"] = None
        row["payload_index"] = None
        row["parent"] = row["parent"] - start if row["parent"] is not None else None
    return clone


def clone_accounting(rows: list[dict], source_counts: dict[int, int]) -> dict:
    deltas = {key: 0 for key in source_counts}
    for row in rows:
        key = first_dword(row)
        if key in deltas:
            deltas[key] += 1
    payloads = sum(bool(r["data"]) for r in rows)
    accounted = sum(deltas.values())
    return {"physical_records": len(rows), "payload_records": payloads,
            "accounting_delta": accounted,
            "type_deltas": {f"0x{k:X}": v for k, v in deltas.items() if v},
            "matches_three_payload_gate": payloads == 3 and accounted == 2}
