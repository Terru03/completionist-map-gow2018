"""Read pinned native gates and class query; objdump runs, God of War does not."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'),HERE/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    compare = load('compare-native-raven-no-render.py')
    native = load('inspect-compass-showmarker-native-validation.py')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', type=Path, default=Path('G:/SteamLibrary/steamapps/common/GodOfWar'))
    parser.add_argument('--objdump', default='objdump')
    parser.add_argument('--output', type=Path, default=compare.ARCHIVE/'completionist-v104-native-raven-no-render-native-gates.json')
    args = parser.parse_args()
    game = args.game_root.resolve()
    compare.safe_output(args.output, compare.ARCHIVE, game)
    compare.ensure_closed()
    executable = game/'GoW.exe'
    before = compare.file_info(executable)
    compare.check(before.get('sha256')==native.EXPECTED_EXE,'GoW.exe differs from pinned build.')
    program = shutil.which(args.objdump)
    compare.check(program is not None, 'GNU objdump required for read-only native trace.')
    pe = native.PE(executable.read_bytes())
    signatures = {
        0x6C0CAF: '498d8de0210200488bd3e86237b1ff84c00f8424040000',
        0x2AD4F7: 'e984374100',
        0x761817: '483902741148ffc14883c228493bc87cef',
        0x94F6C9: '4c39a050080000751b',
    }
    for rva, expected in signatures.items():
        compare.check(pe.read_rva(rva,len(bytes.fromhex(expected))).hex()==expected,f'Native gate changed: {rva:#x}')
    name_offset = pe.raw.index(b'FindMarkersByIconClass\0')
    name_va = pe.image_base+pe.offset_to_rva(name_offset)
    compare.check(pe.read_rva(0x11CF980,16)==struct.pack('<QQ',name_va,pe.image_base+0x94F480), 'FindMarkersByIconClass binding changed.')
    windows = {
        'show_wrapper': (0x94FF80,0x950172),
        'request_worker': (0x2AD490,0x2AD502),
        'show_membership_gate': (0x6C0C80,0x6C0CCD),
        'membership_hash_lookup': (0x1D4420,0x1D44BA),
        'show_resource_lookup': (0x6C0E2A,0x6C0E6A),
        'show_early_return': (0x6C10EA,0x6C10F7),
        'map_coordinate_join': (0x7617FC,0x76182D),
        'compass_coordinate_ingest': (0x8B0B4C,0x8B0C38),
        'compass_coordinate_registry': (0x8B0DD4,0x8B0F0C),
        'compass_coordinate_stride': (0x8B10AD,0x8B10CE),
        'find_by_class_hash_and_scan': (0x94F5F5,0x94F710),
        'find_by_class_lua_output': (0x94F710,0x94F82A),
    }
    disassembly = {}
    for label,(start,end) in windows.items():
        output = subprocess.check_output([program,'-d','-Mintel',
            f'--start-address={pe.image_base+start:#x}',f'--stop-address={pe.image_base+end:#x}',str(executable)],text=True)
        disassembly[label]={'start_rva':hex(start),'end_rva_exclusive':hex(end),
            'source_bytes_sha256':compare.digest(pe.read_rva(start,end-start)),
            'instructions':[line.strip() for line in output.splitlines() if line.strip().startswith('140')]}
    report = {'result':'READ_ONLY_NATIVE_RAVEN_NO_RENDER_GATES',
        'captured_utc':datetime.now(timezone.utc).isoformat(), 'source':before,
        'objdump':{'path':program,'version':subprocess.check_output([program,'--version'],text=True).splitlines()[0]},
        'image_base':hex(pe.image_base), 'address_convention':'Report windows use RVAs; disassembly uses preferred image base. No runtime process read.',
        'binding':{'name':'FindMarkersByIconClass','table_rva':'0x11CF980','wrapper_rva':'0x94F480'},
        'observations':[
            'Show request worker reads request marker at +0x10, class at +0x18; tail-calls native show at RVA 0x2AD4F7.',
            'Native show calls key membership lookup RVA 0x1D4420 on manager+0x221E0 at RVA 0x6C0CB9.',
            'False membership returns at RVA 0x6C10EA before class/resource lookup. No Lua error path in this gate.',
            'Membership routine probes u64 keys in 0x50-byte slots; absent key returns false.',
            'Coordinate ingest obtains type 0x40A, reads UID from coordinate row +0, advances by 0x28, writes keys into global registry 0x142C6CF60.',
            'Worker manager address 0x142C4AD80 plus 0x221E0 equals coordinate registry 0x142C6CF60.',
            'Map join scans coordinate UIDs by 0x28 stride; unmatched UID skips position population.',
            'FindMarkersByIconClass hashes each supplied class, scans shown-marker registry 0x142C647B0, compares record+0x850 with class hash, copies matching marker IDs to Lua table.',
            'FindMarkersByIconClass does not inspect projected position, distance label, in-world sprite, GPU texture or screen pixels.'
        ], 'limits':[
            'Pinned static control-flow evidence supports missing coordinate registration as pre-render blocker.',
            'No live worker/registry snapshot. Does not prove absence of every other population path or a sole visual cause.',
            'A/B visual recovery remains untested. Graph edge loss is established separately by DCB comparison.'
        ], 'windows':disassembly,
        'safety':{'game_launched':False,'game_files_written':False,'saves_or_progression_accessed':False}}
    compare.ensure_closed()
    compare.check(compare.file_info(executable)==before,'GoW.exe changed during trace.')
    compare.write_report(args.output,report,game)
    print('READ_ONLY_NATIVE_RAVEN_NO_RENDER_GATES: signatures and binding verified; report '+str(args.output))


if __name__=='__main__':
    main()
