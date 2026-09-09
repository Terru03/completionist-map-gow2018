#!/usr/bin/env python3
"""Source-resolving wrapper for the v0.10.4 Nornir lifecycle offline builder.

The first lifecycle gate assumed every gameplay Lua existed under mods/lua_source.
Some GoW Lua-loader installs only expose UI sources there. For the two stock chest
scripts this wrapper resolves a clean local source without writing the game:

1. mods/lua_source/<script>
2. mods/lua/<script>.pre-v100-backup, if it is clean
3. the installed v0.10.1 Completionist override, but only when its exact known
   observational instrumentation can be removed in memory and the result is clean

Unknown/older modified scripts are rejected. The resolved bytes are then handed to
the original strict builder, whose structural and exact-inverse checks still apply.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "build-nornir-lifecycle-offline.py"
_spec = importlib.util.spec_from_file_location("nornir_lifecycle_base", BASE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load base builder: {BASE_PATH}")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

V101_RUNIC_MARKER = "-- Completionist Map v0.10.1 Nornir state publisher."
V101_STANDARD_MARKER = "-- Completionist Map v0.10.1 authoritative Nornir chest-open publisher."


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig")


def _has_completionist(text: str) -> bool:
    return (
        "CompletionistMap" in text
        or "[CompletionistMap" in text
        or "BEGIN COMPLETIONIST" in text
    )


def _strip_helper(text: str, marker: str, function_header: str) -> str | None:
    start = text.find(marker)
    if start < 0:
        return None
    end = text.find(function_header, start)
    if end < 0:
        return None
    return text[:start] + text[end:]


def _remove_lines_containing(text: str, needle: str) -> str:
    return "".join(line for line in text.splitlines(keepends=True) if needle not in line)


def _normalize_v101_runic(raw: bytes) -> bytes | None:
    text = _decode(raw)
    text = _strip_helper(text, V101_RUNIC_MARKER, "function OnScriptLoaded(level, go)")
    if text is None:
        return None
    text = _remove_lines_containing(text, "CompletionistMapV100_DumpNornir(")
    if _has_completionist(text):
        return None
    required = (
        "local keysUsed = 0",
        "local challengeComplete = false",
        "local runeTable = {}",
        'keyType = go:GetLuaTableAttribute("KeyType")',
        "function OnScriptLoaded(level, go)",
        "function OnStart(level, go)",
        "function OnKeyBroken(runeIndex)",
        "  CheckKeys()",
    )
    if any(token not in text for token in required):
        return None
    return text.encode("utf-8")


def _normalize_v101_standard(raw: bytes) -> bytes | None:
    text = _decode(raw)
    text = _strip_helper(text, V101_STANDARD_MARKER, "function OnScriptLoaded(level, obj)")
    if text is None:
        return None
    text = _remove_lines_containing(text, "CompletionistMapV100_PublishRunicChestOpened(")
    if _has_completionist(text):
        return None
    required = (
        "function OnScriptLoaded(level, obj)",
        "function OnStart(level, obj)",
        "function OnOpened()",
        "state = states.OPENED",
        'chestType == "Runic_Axe" or chestType == "Runic_Blades"',
        "parentObj = thisObj.Parent.Parent",
    )
    if any(token not in text for token in required):
        return None
    return text.encode("utf-8")


def _clean_candidate(path: Path) -> bytes | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    try:
        text = _decode(raw)
    except UnicodeDecodeError:
        return None
    if _has_completionist(text):
        return None
    return raw


def clean_loader_source_v2(game: Path, rel: Path) -> tuple[Path, bytes]:
    primary = game / "mods/lua_source" / rel
    clean = _clean_candidate(primary)
    if clean is not None:
        print(f"NORNIR_LIFECYCLE_SOURCE rel={rel.as_posix()} provenance=lua_source path={primary}")
        return primary, clean

    live = game / "mods/lua" / rel
    backup = Path(str(live) + ".pre-v100-backup")

    clean_backup = _clean_candidate(backup)
    if clean_backup is not None:
        print(f"NORNIR_LIFECYCLE_SOURCE rel={rel.as_posix()} provenance=pre-v100-backup-clean path={backup}")
        return backup, clean_backup

    name = rel.name.lower()
    normalizer = None
    if name == "interact_chest_runic.lua":
        normalizer = _normalize_v101_runic
    elif name == "interact_chest_standard.lua":
        normalizer = _normalize_v101_standard

    if normalizer is not None:
        # Prefer the current installed override because v0.10.1 wrote these files
        # from a validated stock source. A backup is considered second only when it
        # carries that exact same recognizable v0.10.1 instrumentation.
        for provenance, path in (
            ("installed-v101-deinstrumented-in-memory", live),
            ("backup-v101-deinstrumented-in-memory", backup),
        ):
            if not path.is_file():
                continue
            try:
                normalized = normalizer(path.read_bytes())
            except UnicodeDecodeError:
                normalized = None
            if normalized is not None:
                print(f"NORNIR_LIFECYCLE_SOURCE rel={rel.as_posix()} provenance={provenance} path={path}")
                print("NORNIR_LIFECYCLE_SOURCE_NORMALIZATION game_file_written=false exact_known_v101_instrumentation_removed_in_memory=true")
                return path, normalized

    checked = [primary, backup, live]
    details = "; ".join(f"{p}={'file' if p.is_file() else 'missing'}" for p in checked)
    raise ValueError(
        "no trusted clean lifecycle source could be resolved for "
        f"{rel.as_posix()}; checked: {details}. "
        "Unknown Completionist-modified sources are intentionally rejected."
    )


base.clean_loader_source = clean_loader_source_v2

if __name__ == "__main__":
    base.main()
