"""Generate ordered Nornir checkpoint identities from exact native paths."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/v0.10.5'))
import nornir_saved_state
import nornir_catalogue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = nornir_saved_state.build(json.loads(nornir_catalogue.SOURCE.read_text()))
    lines = ['#pragma once', '#include <array>', '#include "chest_authority.h"',
             'namespace completionist {',
             f'inline constexpr char kNornirContract[] = "{nornir_saved_state.contract(rows)}";',
             'inline constexpr std::array<ChestIdentity, 22> kNornirCatalogue{{']
    for row in rows:
        lines.append('  ChestIdentity{%s, %s, UINT64_C(0x%s), UINT64_C(0x%s)},' %
                     (json.dumps(row['catalogue_id']), json.dumps(row['wad']), row['registry_hash'], row['object_hash']))
    lines += ['}};', '}', '']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
