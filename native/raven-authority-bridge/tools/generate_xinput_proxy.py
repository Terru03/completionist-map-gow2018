#!/usr/bin/env python3
"""Generate exact XINPUT1_4 export definition, x64 thunks, and C++ contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_contract(path: Path) -> dict:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema") != 1 or contract.get("dll", "").lower() != "xinput1_4.dll":
        raise ValueError("unsupported XInput contract")
    exports = contract.get("exports")
    if not isinstance(exports, list) or not exports:
        raise ValueError("contract has no exports")
    ordinals = [item.get("ordinal") for item in exports]
    if any(not isinstance(value, int) or value < 1 or value > 65535 for value in ordinals):
        raise ValueError("invalid export ordinal")
    if len(set(ordinals)) != len(ordinals):
        raise ValueError("duplicate export ordinal")
    names = [item.get("name") for item in exports if item.get("name") is not None]
    if any(not isinstance(value, str) or not value for value in names):
        raise ValueError("invalid export name")
    if len(set(names)) != len(names):
        raise ValueError("duplicate export name")
    custom = contract.get("custom_export_ordinal")
    if not isinstance(custom, int) or custom in ordinals:
        raise ValueError("invalid custom export ordinal")
    return contract


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def generate_def(contract: dict) -> str:
    lines = ["LIBRARY XINPUT1_4", "EXPORTS"]
    for item in contract["exports"]:
        ordinal = item["ordinal"]
        target = f"CompletionistXInputThunk{ordinal}"
        if item["name"] is None:
            lines.append(f"    {target} @{ordinal} NONAME")
        else:
            lines.append(f"    {item['name']}={target} @{ordinal}")
    lines.append(
        "    CompletionistMapGetRavenSnapshotV1 "
        f"@{contract['custom_export_ordinal']}"
    )
    return "\n".join(lines) + "\n"


def generate_asm(contract: dict) -> str:
    lines = [
        "option casemap:none",
        "",
        "EXTERN CompletionistResolveXInputExport:PROC",
        "",
        ".code",
        "",
        "; Preserve all Win64 argument registers while resolver runs, then tail-jump.",
        "XINPUT_THUNK MACRO ordinal:req",
        "CompletionistXInputThunk&ordinal PROC FRAME",
        "    sub rsp, 088h",
        "    .allocstack 088h",
        "    .endprolog",
        "    mov qword ptr [rsp+020h], rcx",
        "    mov qword ptr [rsp+028h], rdx",
        "    mov qword ptr [rsp+030h], r8",
        "    mov qword ptr [rsp+038h], r9",
        "    movdqu xmmword ptr [rsp+040h], xmm0",
        "    movdqu xmmword ptr [rsp+050h], xmm1",
        "    movdqu xmmword ptr [rsp+060h], xmm2",
        "    movdqu xmmword ptr [rsp+070h], xmm3",
        "    mov ecx, ordinal",
        "    call CompletionistResolveXInputExport",
        "    mov qword ptr [rsp+080h], rax",
        "    mov rcx, qword ptr [rsp+020h]",
        "    mov rdx, qword ptr [rsp+028h]",
        "    mov r8, qword ptr [rsp+030h]",
        "    mov r9, qword ptr [rsp+038h]",
        "    movdqu xmm0, xmmword ptr [rsp+040h]",
        "    movdqu xmm1, xmmword ptr [rsp+050h]",
        "    movdqu xmm2, xmmword ptr [rsp+060h]",
        "    movdqu xmm3, xmmword ptr [rsp+070h]",
        "    mov rax, qword ptr [rsp+080h]",
        "    add rsp, 088h",
        "    jmp rax",
        "CompletionistXInputThunk&ordinal ENDP",
        "ENDM",
        "",
    ]
    lines.extend(f"XINPUT_THUNK {item['ordinal']}" for item in contract["exports"])
    lines.extend(["", "END", ""])
    return "\n".join(lines)


def generate_header(contract: dict) -> str:
    lines = [
        "#pragma once",
        "",
        "#include <array>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        "namespace completionist {",
        "",
        "struct XInputExportSpec {",
        "  std::uint16_t ordinal;",
        "  std::string_view name;",
        "};",
        "",
        f"inline constexpr std::array<XInputExportSpec, {len(contract['exports'])}> kXInputExports{{{{",
    ]
    for item in contract["exports"]:
        name = "" if item["name"] is None else item["name"]
        lines.append(f'    XInputExportSpec{{{item["ordinal"]}, "{name}"}},')
    lines.extend(
        [
            "}};",
            f"inline constexpr std::uint16_t kSnapshotExportOrdinal = {contract['custom_export_ordinal']};",
            "",
            "}  // namespace completionist",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--def-output", type=Path, required=True)
    parser.add_argument("--asm-output", type=Path, required=True)
    parser.add_argument("--header-output", type=Path, required=True)
    args = parser.parse_args()
    contract = load_contract(args.contract)
    write_if_changed(args.def_output, generate_def(contract))
    write_if_changed(args.asm_output, generate_asm(contract))
    write_if_changed(args.header_output, generate_header(contract))
    print(f"RAVEN_XINPUT_PROXY_GENERATED exports={len(contract['exports'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
