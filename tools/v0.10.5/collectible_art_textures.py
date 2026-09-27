"""Compile supplied PNGs into separate game map resources. Keep source art intact."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

import collectible_family_art as art
import collectible_completion_adapters as adapters

ASSETS = art.ROOT / 'assets/icons/families'
FAMILY_PNG = {name: name + '.png' for name in (
    'artefact', 'cipher_chest', 'coffin', 'jotnar_shrine', 'legendary_chest',
    'lore_marker', 'lore_scroll', 'nornir_bell', 'nornir_chest', 'nornir_mechanism',
    'nornir_seal', 'realm_tear', 'treasure_map', 'wooden_chest')}
FAMILY_PNG['treasure_dig'] = 'buried_treasure.png'
PACK = 'completionist_v105_family_art'
PACK_FILES = {'exec/patch/pc_le/' + PACK + suffix for suffix in ('.texpack', '.texpack.toc')}
PRESERVED = {'exec/dc/pc_le/wad_r_perm.dcb', 'exec/dc/pc_le/mapcoords.dcb',
    'exec/dc/pc_le/compassgraph.dcb', 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua',
    'dxgi.dll', 'mods/completionist-map/native/collectible-base-dxgi.dll',
    'mods/completionist-map/native/raven-native-bridge-manifest.json', 'GoW.exe', 'version.dll',
    'mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua'}
PRESERVED.update('mods/lua/' + adapters.PREFIX + row[0] for row in adapters.SCRIPTS.values())
BASE_FILES = {art.WAD, art.MASTER, art.POOL, art.BOOT}
TOOL_ROOT = Path(os.environ['LOCALAPPDATA']) / 'CompletionistMap/tools'
TOOLS = {
    'texconv': (TOOL_ROOT / 'DirectXTex-may2026/texconv.exe',
                'dcfdec10244e02cf5037fba089c55fb7e1326b1c8181742d77d15fa5cb5eef06'),
    'gowtool': (TOOL_ROOT / 'GOWTool-v0.1.3-alpha/GOWTool.exe',
                'c1b0f3c7fb9dd2b26ae7ef4ac377308761fd3c7afb21dac7e4bee20160a0008b')}
io = art.load('family_art_safe_io', art.HERE / 'install-nornir-map-id-test.py')
mapping = art.load('family_texture_mapping', art.HERE.parent / 'v0.10.4/inspect-resident-block-mapping.py')
transform = art.load('family_resident_transform', art.HERE.parent / 'v0.10.4/inspect-resident-partial-linearization.py')
binding = art.load('family_pack_binding', art.HERE.parent / 'v0.10.4/patch-raven-texpack-userhash-binding.py')


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            art.need(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(io.safe(path).read_text(), object_pairs_hook=unique)


def freeze_baseline(game, output):
    game, output = io.safe(game), io.safe(output)
    art.need(not output.is_relative_to(game) and not game.is_relative_to(output), 'output overlaps game')
    files = {name: io.sha(game / name) for name in sorted(BASE_FILES | PRESERVED | PACK_FILES)}
    art.need(all(files[name] is not None for name in BASE_FILES | PRESERVED), 'installed baseline file missing')
    prior = read_json(art.BUILD / 'baseline.json')
    art.need(all(files.get(n) == h for n, h in prior['files'].items()), 'installed artwork baseline changed')
    data = {'schema': 2, 'game_root': str(game), 'files': files}
    path = io.safe(output / 'baseline.json')
    if path.exists():
        art.need(read_json(path) == data, 'frozen installation differs')
    for name, value in files.items():
        target = output / 'baseline' / name
        current = io.sha(target)
        art.need(current is None or current == value, 'baseline copy drift: ' + name)
    for name, value in files.items():
        if value is not None and io.sha(output / 'baseline' / name) is None:
            io.atomic_copy(game / name, output / 'baseline' / name, value, None)
    art.need(files == {name: io.sha(game / name) for name in files}, 'installation changed during freeze')
    if not path.exists():
        io.write_json(path, data)
    return data


def check_baseline(game, output):
    data = read_json(output / 'baseline.json')
    art.need(data.get('schema') == 2 and data.get('game_root') == str(io.safe(game)) and
             set(data.get('files', {})) == BASE_FILES | PRESERVED | PACK_FILES, 'invalid frozen art baseline')
    prior = read_json(art.BUILD / 'baseline.json')
    art.need(all(data['files'].get(n) == h for n, h in prior['files'].items()), 'frozen art baseline differs')
    for name, value in data['files'].items():
        art.need(io.sha(output / 'baseline' / name) == value, 'frozen art file drift: ' + name)
    for name in PRESERVED:
        art.need(io.sha(game / name) == data['files'][name], 'completion installation drift: ' + name)
    return data


def run(command, cwd=None):
    result = subprocess.run([str(x) for x in command], cwd=cwd, capture_output=True, text=True, errors='replace')
    art.need(result.returncode == 0, 'texture tool failed (' + str(result.returncode) + '): ' + result.stdout + result.stderr)
    return result.stdout


def source_inputs():
    sources = [ASSETS / name for name in FAMILY_PNG.values()]
    sources += [Path(__file__), art.HERE / 'collectible_family_art.py',
                art.HERE / 'install-collectible-family-art.py',
                art.HERE / 'build-collectible-locations.py',
                art.HERE / 'build-nornir-map-id-test.py',
                art.locations.CATALOGUE, art.locations.ADDITIONAL, art.locations.CATEGORIES]
    sources += [art.HERE.parent / 'v0.10.4' / name for name in (
        'inspect-resident-block-mapping.py', 'inspect-resident-partial-linearization.py',
        'patch-raven-texpack-userhash-binding.py',
        'build-raven-ui-logical-clone.py', 'build-nornir-map-hud-offline.py')]
    result = {p.relative_to(art.ROOT).as_posix(): io.sha(p) for p in sorted(set(sources))}
    for name, (path, expected) in TOOLS.items():
        art.need(io.sha(path) == expected, 'pinned texture tool differs: ' + name)
        result['tool:' + name] = expected
    art.need(all(result.values()), 'source input missing')
    return result


def bind_user_hashes(pack, toc, desired):
    entries, toc_entries = binding.parse_texpack_entries(pack), binding.parse_texpack_entries(toc)
    art.need(entries == toc_entries and len(entries) == len(desired) and
             {r['file_hash'] for r in entries} == set(desired), 'pack/TOC texture identities differ')
    art.need(len(set(desired.values())) == len(desired) and all(0 < v < 0xFFFFFFFFFFFFFFFF for v in desired.values()),
             'texture user hashes not unique')
    patched, patched_toc = bytearray(pack), bytearray(toc)
    edits, toc_edits = [], []
    for row in entries:
        target = desired[row['file_hash']]
        art.need(row['user_hash'] in (0xFFFFFFFFFFFFFFFF, target), 'unexpected generated texture user hash')
        at = row['entry_offset'] + 8
        block_info = row['block_info_off']
        art.need(0 <= block_info <= len(pack) - 32, 'texture block info outside pack')
        block = struct.unpack_from('<I', pack, block_info)[0] << 4
        art.need(0 <= block <= len(pack) - 0x50, 'texture block outside pack')
        tag, span, _, kind = struct.unpack_from('<IIII', pack, block)
        art.need((tag, span, kind) == (1, 0x124, 5) and
                 struct.unpack_from('<I', pack, block + 0x10)[0] == 0x20464E47 and
                 struct.unpack_from('<I', pack, block + 0x40)[0] == 0x52455355,
                 'texture GNF header differs')
        gnf_at = block + 0x48
        art.need(struct.unpack_from('<Q', pack, gnf_at)[0] == row['user_hash'], 'GNF user hash differs')
        for offset in (at, gnf_at):
            struct.pack_into('<Q', patched, offset, target)
            edits.append(offset)
        struct.pack_into('<Q', patched_toc, at, target)
        toc_edits.append(at)
    inverse, toc_inverse = bytearray(patched), bytearray(patched_toc)
    for at in edits:
        inverse[at:at + 8] = pack[at:at + 8]
    for at in toc_edits:
        toc_inverse[at:at + 8] = toc[at:at + 8]
    art.need(bytes(inverse) == pack and bytes(toc_inverse) == toc, 'texture binding inverse failed')
    return bytes(patched), bytes(patched_toc)


def compile_textures(output, inputs):
    cache_id = art.sha(json.dumps(inputs, sort_keys=True).encode())
    # GOWTool needs short paths for each DDS file.
    work = io.safe(art.ROOT / 'build/art-textures' / cache_id[:16])
    manifest = work / 'textures.json'
    if manifest.exists():
        data = read_json(manifest)
        art.need(data.get('source_inputs') == inputs, 'texture cache inputs differ')
        for name, value in data['files'].items():
            art.need(io.sha(work / name) == value, 'texture cache drift: ' + name)
        return work, data
    pack_dir = work / PACK
    pack_dir.mkdir(parents=True, exist_ok=True)
    definitions = {}
    for family, png in sorted(FAMILY_PNG.items()):
        source = ASSETS / png
        source_sha = io.sha(source)
        row = {'source': source.relative_to(art.ROOT).as_posix(), 'source_sha256': source_sha}
        for role, fmt in (('diffuse', 'BC7_UNORM_SRGB'), ('emissive', 'BC1_UNORM')):
            target = work / 'dds' / role
            target.mkdir(parents=True, exist_ok=True)
            run([TOOLS['texconv'][0], '-nologo', '-y', '-w', '148', '-h', '148', '-m', '8',
                 '-c', '000000', '-f', fmt, '-o', target, source])
            compiled = target / (source.stem + '.dds')
            art.need(compiled.is_file(), 'DDS output missing')
            file_hash = int.from_bytes(art.identity(family, role + ':' + source_sha, 8), 'little')
            name = f'TX_cmf_{family}_{role[:4]}_{file_hash:016X}'
            art.need(len(name) < 56, 'texture name too long')
            shutil.copyfile(compiled, pack_dir / (name + '.dds'))
            row[role] = {'name': name, 'file_hash': file_hash, 'dds_sha256': io.sha(compiled)}
        definitions[family] = row
        print('DDS_OK ' + family, flush=True)
    run([TOOLS['gowtool'][0], 'texpack', '-i', '-p', pack_dir], cwd=TOOLS['gowtool'][0].parent)
    desired = {row[role]['file_hash']: int.from_bytes(art.identity(family,
               role + ':user:' + row['source_sha256'], 8), 'little')
               for family, row in definitions.items() for role in ('diffuse', 'emissive')}
    pack_path, toc_path = work / (PACK + '.texpack'), work / (PACK + '.texpack.toc')
    fixed, fixed_toc = bind_user_hashes(pack_path.read_bytes(), toc_path.read_bytes(), desired)
    pack_path.write_bytes(fixed)
    toc_path.write_bytes(fixed_toc)
    pack = mapping.parse_texpack(work / (PACK + '.texpack'))
    art.need(pack['tex_count'] == 2 * len(FAMILY_PNG), 'texture pack count differs')
    base = art.logical.parse_wad((output / 'baseline' / art.WAD).read_bytes())
    residents = work / 'resident'
    residents.mkdir(exist_ok=True)
    for family, row in definitions.items():
        for role, block_bytes in (('diffuse', 16), ('emissive', 8)):
            texture = row[role]
            stream, meta = mapping.streamed_payload(pack, texture['file_hash'])
            body, _ = transform.reconstruct_resident_body(stream, block_bytes, 148, 148)
            _, donor = art.clone.unique_texture(base, art.RAVEN[role], gpu=True)
            resident = body + bytes(donor['data'][-12:])
            art.need(len(resident) == len(donor['data']) and resident != bytes(donor['data']),
                     'resident texture differs from required layout')
            relative = 'resident/' + family + '_' + role + '.bin'
            (work / relative).write_bytes(resident)
            texture.update(user_hash=int(meta['user_hash'], 16), resident=relative,
                           resident_sha256=art.sha(resident))
    for role in ('diffuse', 'emissive'):
        for field in ('file_hash', 'user_hash', 'resident_sha256'):
            art.need(len({r[role][field] for r in definitions.values()}) == len(definitions),
                     'family texture alias: ' + role + ':' + field)
    files = {p.relative_to(work).as_posix(): io.sha(p) for p in work.rglob('*') if p.is_file()}
    data = {'source_inputs': inputs, 'families': definitions, 'files': files,
            'dimensions': [148, 148], 'mips': 8, 'black_chromakey': True,
            'diffuse_format': 'BC7_UNORM_SRGB', 'emissive_format': 'BC1_UNORM'}
    io.write_json(manifest, data)
    return work, data


def compose(output, work, compiled):
    source = output / 'baseline'
    specs, resources = [], {}
    for family, row in sorted(compiled['families'].items()):
        spec = art.spec_for(family)
        resources[family] = spec['resource']
        textures = {role: {k: row[role][k] for k in ('name', 'file_hash', 'user_hash')}
                    for role in ('diffuse', 'emissive')}
        for role, texture in textures.items():
            texture['resident'] = (work / row[role]['resident']).read_bytes()
        specs.append((spec, textures))
    outputs, proof = {}, {'textures': compiled}
    outputs[art.WAD], proof[art.WAD] = art.build_wad((source / art.WAD).read_bytes(), specs)
    outputs[art.MASTER], proof[art.MASTER] = art.build_master((source / art.MASTER).read_bytes(), resources)
    outputs[art.POOL], proof[art.POOL] = art.build_pool((source / art.POOL).read_bytes(), resources)
    boot = read_json(source / art.BOOT)
    entry = '../../patch/pc_le/' + PACK
    art.need(entry not in boot['patch-texpacks'], 'family art pack already installed')
    boot['patch-texpacks'].append(entry)
    outputs[art.BOOT] = (json.dumps(boot, indent=2) + '\n').encode()
    for name in PACK_FILES:
        outputs[name] = (work / Path(name).name).read_bytes()
    return outputs, proof


def build(game=art.locations.GAME, output=art.BUILD / 'all-types'):
    art.need(set(FAMILY_PNG) == {r['family'] for r in art.all_definitions()}, 'family art coverage differs')
    game, output = io.safe(game), io.safe(output)
    art.need(not output.is_relative_to(game) and not game.is_relative_to(output), 'output overlaps game')
    if not (output / 'baseline.json').exists():
        freeze_baseline(game, output)
    check_baseline(game, output)
    inputs = source_inputs()
    work, compiled = compile_textures(output, inputs)
    first, proof = compose(output, work, compiled)
    second, repeated_proof = compose(output, work, compiled)
    art.need(first == second and proof == repeated_proof, 'family art composition differs')
    art.need(source_inputs() == inputs, 'source changed during build')
    check_baseline(game, output)
    proof['two_compositions_equal'] = True
    result = art.freeze_package(first, proof, output, baseline_root=output, source_inputs=inputs)
    print('FAMILY_ART_BUILT types=15 markers=498 package=' + result['package_id'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=art.locations.GAME)
    parser.add_argument('--output', type=Path, default=art.BUILD / 'all-types')
    args = parser.parse_args()
    build(args.game, args.output)
