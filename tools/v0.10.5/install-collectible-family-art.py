"""Apply/verify/roll back an artwork-only package, preserving the completion code."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import uuid
import collectible_family_art as art

io = art.load("family_art_transaction", art.HERE / "install-collectible-locations.py")
# Use the established path and atomic-copy primitives, not its old baseline pins.
io = io.base
BASE_FILES = {art.WAD, art.MASTER, art.POOL, art.BOOT}
PRESERVED = {"exec/dc/pc_le/wad_r_perm.dcb", "exec/dc/pc_le/mapcoords.dcb",
             "exec/dc/pc_le/compassgraph.dcb", "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua",
             "dxgi.dll", "mods/completionist-map/native/collectible-base-dxgi.dll",
             "mods/completionist-map/native/raven-native-bridge-manifest.json"}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            art.need(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(io.safe(path).read_text(), object_pairs_hook=unique)


def digest_file(path):
    return io.sha(path)


def validate(data):
    art.need(type(data.get('schema')) is int and data['schema'] in (1, 2) and data.get("kind") == "COLLECTIBLE_FAMILY_MAP_ART",
             "unknown artwork package")
    names = set(data["files"])
    packs = names - BASE_FILES
    pack_sets = [{'exec/patch/pc_le/completionist_v105_family_art' + stem + suffix
                  for suffix in ('.texpack', '.texpack.toc')} for stem in ('', '_probe')]
    art.need(BASE_FILES <= names and packs in pack_sets, 'artwork path allowlist differs')
    preserved = PRESERVED
    if data['schema'] == 2:
        import collectible_art_textures
        preserved = collectible_art_textures.PRESERVED
        art.need(isinstance(data.get('source_inputs'), dict) and data['source_inputs'], 'art source proof missing')
        art.need(data.get('proof', {}).get('two_compositions_equal') is True, 'repeat composition proof missing')
    art.need(set(data["preserved"]) == preserved, "preserved file allowlist differs")
    for item in data["files"].values():
        art.need(set(item) == {"before", "after"}, "invalid file hash fields")
        art.need(item['before'] is None or isinstance(item['before'], str) and
                 re.fullmatch(r'[0-9a-f]{64}', item['before']), 'invalid before hash')
        art.need(isinstance(item['after'], str) and re.fullmatch(r'[0-9a-f]{64}', item['after']), 'invalid after hash')
    for value in data['preserved'].values():
        art.need(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), 'invalid preserved hash')
    if data['schema'] == 2:
        for value in data['source_inputs'].values():
            art.need(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), 'invalid source hash')
    identity_data = data['files'] if data['schema'] == 1 else {
        'files': data['files'], 'source_inputs': data['source_inputs']}
    identity = art.sha(json.dumps(identity_data, sort_keys=True).encode())
    art.need(data["package_id"] == identity, "package identity differs")


def preserve(data, game):
    for name, expected in data["preserved"].items():
        art.need(digest_file(io.safe(game / name)) == expected, "preserved file changed: " + name)


def read_operation(journal, game, output):
    journal, game, output = io.safe(journal), io.safe(game), io.safe(output)
    art.need(journal.name == "operation.json" and journal.parent.parent == output / "backups" and
             re.fullmatch(r"[0-9a-f]{32}", journal.parent.name), "unknown artwork journal")
    data = read_json(journal)
    validate(data)
    art.need(data["game_root"] == str(game), "journal game root differs")
    art.need(data.get('status') in {'prepared', 'installing', 'installed', 'rolling_back', 'rolled_back',
                                  'rollback_failed'}, 'invalid operation status')
    return data


def rollback(journal, game, output, stopped=io.game_stopped):
    stopped()
    data = read_operation(journal, game, output)
    # Check every file before modifying any; refuse unrelated edits or damaged backups.
    preserve(data, game)
    for name, item in data["files"].items():
        art.need(digest_file(io.safe(game / name)) in (item["before"], item["after"]), "unrelated edit: " + name)
        art.need(digest_file(io.safe(journal.parent / "before" / name)) == item["before"], "backup drift: " + name)
    data["status"] = "rolling_back"
    io.write_json(journal, data)
    try:
        for name, item in reversed(list(data['files'].items())):
            stopped()
            path = io.safe(game / name)
            if digest_file(path) == item['before']:
                continue
            art.need(digest_file(path) == item['after'], 'target changed during rollback')
            if item['before'] is None:
                path.unlink()
            else:
                io.atomic_copy(io.safe(journal.parent / 'before' / name), path, item['before'], item['after'])
        preserve(data, game)
        art.need(all(digest_file(io.safe(game / n)) == v['before'] for n, v in data['files'].items()),
                 'rollback verification failed')
        data['status'] = 'rolled_back'
        data.pop('rollback_error', None)
        io.write_json(journal, data)
    except Exception as error:
        data['status'], data['rollback_error'] = 'rollback_failed', str(error)
        io.write_json(journal, data)
        raise


def verify(journal, game, output):
    data = read_operation(journal, game, output)
    art.need(data["status"] == "installed", "artwork package not installed")
    preserve(data, game)
    for name, item in data["files"].items():
        art.need(digest_file(io.safe(game / name)) == item["after"], "installed drift: " + name)
        art.need(digest_file(io.safe(journal.parent / "before" / name)) == item["before"], "backup drift: " + name)


def install(game, output, stopped=io.game_stopped):
    stopped()
    game, output = io.safe(game), io.safe(output)
    art.need(not output.is_relative_to(game) and not game.is_relative_to(output), 'output overlaps game')
    data = read_json(output / 'report.json')
    validate(data)
    package = io.safe(output / "packages" / data["package_id"] / "game-root")
    if data['schema'] == 2:
        art.need(read_json(package.parent / 'report.json') == data, 'immutable art report differs')
    for name, item in data["files"].items():
        art.need(digest_file(io.safe(package / name)) == item["after"], "candidate drift: " + name)
        art.need(digest_file(io.safe(game / name)) == item["before"], "installed baseline drift: " + name)
    preserve(data, game)
    directory = io.safe(output / "backups" / uuid.uuid4().hex)
    directory.mkdir(parents=True)
    for name, item in data["files"].items():
        if item["before"] is not None:
            target = io.safe(directory / "before" / name)
            io.atomic_copy(io.safe(game / name), target, item['before'], None)
    journal = directory / "operation.json"
    data.update(game_root=str(game), status="prepared")
    io.write_json(journal, data)
    try:
        data["status"] = "installing"
        io.write_json(journal, data)
        for name, item in data["files"].items():
            stopped()
            io.atomic_copy(io.safe(package / name), io.safe(game / name), item["after"], item["before"])
        data["status"] = "installed"
        io.write_json(journal, data)
        verify(journal, game, output)
    except Exception as error:
        try:
            rollback(journal, game, output, stopped)
        except Exception as rollback_error:
            raise RuntimeError(f'Artwork install failed; close game and retry rollback: {journal}: {rollback_error}') from error
        raise
    return journal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify", "rollback"))
    parser.add_argument("--game", type=Path, default=art.locations.GAME)
    parser.add_argument("--output", type=Path, default=art.BUILD / "probe")
    parser.add_argument("--operation", type=Path)
    args = parser.parse_args()
    if args.action == "install":
        art.need(args.operation is None, "install does not take an operation")
        print(install(args.game, args.output))
    else:
        art.need(args.operation is not None, "operation required")
        globals()[args.action](args.operation, args.game, args.output)
        print("ARTWORK_" + args.action.upper() + "_OK")
