"""Fail-closed two-file native data A/B. Default checks only. Never launches game."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('raven_compare', HERE/'compare-native-raven-no-render.py')
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)
check = compare.check
STATE = compare.BUILD/'ab-transactions'
NAMES = ('mapcoords.dcb','compassgraph.dcb')
KIND = 'v104-native-raven-coordinate-graph-ab-v1'


def sha(path):
    result = compare.file_info(Path(path))
    check(result['exists'], f'Missing file: {path}')
    return result['sha256']


def plain_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            check(not item.is_symlink() and not item.is_junction(), f'Linked path refused: {item}')
    check(not path.exists() or path.is_dir() or path.stat().st_nlink == 1, f'Hard links refused: {path}')
    return path


def require_hash(path, expected):
    plain_path(path)
    check(sha(path) == expected, f'Hash mismatch; refusing overwrite/use: {path}')


def save_manifest(path, value):
    plain_path(path)
    temporary = path.with_name('manifest-'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def replace_checked(source, target, before, after):
    """Stage bytes; recheck source and destination before one-file atomic replace."""
    source, target = Path(source), Path(target)
    require_hash(source, after)
    require_hash(target, before)
    staged = target.with_name(target.name+'.raven-ab-'+uuid.uuid4().hex+'.tmp')
    try:
        with source.open('rb') as src, staged.open('xb') as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        require_hash(staged, after)
        require_hash(target, before)
        os.replace(staged, target)
        require_hash(target, after)
    finally:
        if staged.exists():
            staged.unlink()


def validate_rows(rows, game):
    check(set(rows)==set(NAMES), 'A/B must contain exactly mapcoords and compassgraph.')
    game = plain_path(game).resolve()
    for name,row in rows.items():
        target = plain_path(row['target']).resolve()
        check(target.is_relative_to(game) and target.name==name, 'A/B target escaped game or changed name.')
        check(len(row['before'])==len(row['after'])==64 and row['before']!=row['after'], 'Bad A/B hashes.')


def validate_manifest(manifest, rows, game):
    plain_path(manifest)
    value = compare.read_json(manifest)
    check(value['kind']==KIND and value['game_root']==str(game.resolve()), 'Wrong A/B manifest/game root.')
    check(set(value['rows'])==set(rows), 'Wrong manifest file set.')
    for name,row in rows.items():
        recorded = value['rows'][name]
        for key in ('target','before','after'):
            check(recorded[key]==row[key], f'Manifest differs from pinned {name}/{key}.')
        check(recorded['backup']==str(manifest.parent/(name+'.before')), 'Backup path redirected.')
        require_hash(recorded['backup'],row['before'])
    return value


def rollback_pair(manifest, rows, game, guard):
    validate_rows(rows, game)
    value = validate_manifest(manifest,rows,game)
    guard()
    # Validate entire pair before first restore; accept interrupted before/after mix.
    for row in rows.values():
        plain_path(row['target'])
        check(sha(row['target']) in (row['before'],row['after']), 'Live file changed; rollback refused.')
    value['state'] = 'rollback_pending'
    save_manifest(manifest,value)
    for name,row in rows.items():
        guard()
        if sha(row['target'])==row['after']:
            replace_checked(value['rows'][name]['backup'],row['target'],row['after'],row['before'])
        else:
            require_hash(row['target'],row['before'])
    value['state']='rolled_back'
    value['rolled_back_utc']=datetime.now(timezone.utc).isoformat()
    save_manifest(manifest,value)
    return manifest


def install_pair(rows, state, game, guard):
    validate_rows(rows,game)
    state = plain_path(state)
    check(not state.resolve().is_relative_to(game.resolve()), 'Backups must stay outside game.')
    guard()
    for row in rows.values():
        require_hash(row['target'],row['before'])
        require_hash(row['source'],row['after'])
    state.mkdir(parents=True,exist_ok=True)
    for old in state.glob('*/manifest.json'):
        check(compare.read_json(old).get('state')=='rolled_back', f'Unresolved A/B transaction: {old}')
    folder = state/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    folder.mkdir()
    value = {'kind':KIND, 'state':'backup_complete','game_root':str(game.resolve()),
        'created_utc':datetime.now(timezone.utc).isoformat(),'rows':{},
        'save_progression_marker_state_written':False, 'game_launched':False}
    for name,row in rows.items():
        backup = folder/(name+'.before')
        with Path(row['target']).open('rb') as src, backup.open('xb') as dst:
            shutil.copyfileobj(src,dst)
            dst.flush(); os.fsync(dst.fileno())
        require_hash(backup,row['before'])
        value['rows'][name]={**row,'backup':str(backup)}
    manifest = folder/'manifest.json'
    save_manifest(manifest,value)
    try:
        guard()
        for row in rows.values():
            require_hash(row['target'],row['before'])
            require_hash(row['source'],row['after'])
        value['state']='install_pending'
        save_manifest(manifest,value)
        for row in rows.values():
            guard()
            replace_checked(row['source'],row['target'],row['before'],row['after'])
        guard()
        value['state']='installed'
        value['installed_utc']=datetime.now(timezone.utc).isoformat()
        save_manifest(manifest,value)
    except Exception:
        # Preserve manifest/backups on failed recovery; never restore unknown target bytes.
        rollback_pair(manifest,rows,game,guard)
        raise
    return manifest


def pinned_rows(game):
    return {name:{'target':str(game/'exec/dc/pc_le'/name),
        'source':str(compare.BUILD/'historical'/name),
        'before':compare.LIVE['exec/dc/pc_le/'+name], 'after':compare.HISTORICAL[name]} for name in NAMES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('check','install','collect','rollback'),default='check')
    parser.add_argument('--game-root',type=Path,default=Path('G:/SteamLibrary/steamapps/common/GodOfWar'))
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--hud',choices=('visible','absent','unknown'),default='unknown')
    parser.add_argument('--world',choices=('visible','absent','unknown'),default='unknown')
    args=parser.parse_args()
    game=plain_path(args.game_root).resolve()
    branch=subprocess.check_output(['git','-C',str(compare.REPO),'branch','--show-current'],text=True).strip()
    check(branch==compare.BRANCH,'Wrong branch for Raven A/B.')
    compare.ensure_closed()
    rows=pinned_rows(game)
    if args.mode=='collect':
        check(args.manifest is not None,'Collect needs exact --manifest path printed by install.')
        manifest=plain_path(args.manifest).resolve()
        check(manifest.is_relative_to(STATE.resolve()) and manifest.name=='manifest.json','Collect manifest outside A/B tree.')
        value=validate_manifest(manifest,rows,game)
        check(value['state']=='installed','Collect before rollback; manifest must be installed.')
        expected={**compare.LIVE, **compare.PATCH_FILES, **{'exec/dc/pc_le/'+n:compare.HISTORICAL[n] for n in NAMES}}
        for path,digest in expected.items(): require_hash(game/path,digest)
        inventory={path:compare.file_info(game/path) for path in [*expected,'mods/loader_log.txt']}
        log=game/'mods/loader_log.txt'
        installed=datetime.fromisoformat(value['installed_utc']).timestamp()
        check(log.stat().st_mtime>=installed,'Loader log predates A/B install; stale evidence refused.')
        evidence=compare.runtime_evidence(log.read_text(encoding='utf-8-sig',errors='replace'))
        result={'result':'NATIVE_RAVEN_DATA_AB_CAPTURED_NOT_VISUAL_PROOF',
            'captured_utc':datetime.now(timezone.utc).isoformat(),'manifest':compare.file_info(manifest),
            'transaction':value,'inventory':inventory,'runtime':evidence,
            'user_observation':{'hud':args.hud,'world':args.world,'source':'explicit CLI options; not agent-observed'},
            'safety':{'game_launched':False,'game_files_written':False,'save_progression_marker_state_written':False}}
        compare.ensure_closed()
        check(all(compare.file_info(game/p)==info for p,info in inventory.items()),'Input changed during collection.')
        out=compare.ARCHIVE/('completionist-v104-native-raven-data-ab-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.json')
        compare.write_report(out,result,game)
        print('A/B evidence saved; no rollback or publish run. '+str(out))
        return
    if args.mode=='rollback':
        check(args.manifest is not None,'Rollback needs exact --manifest path printed by install.')
        manifest=plain_path(args.manifest).resolve()
        check(manifest.is_relative_to(STATE.resolve()) and manifest.name=='manifest.json', 'Rollback manifest outside A/B state tree.')
        # Rollback intentionally independent of mutable report, candidate files and preserved artwork.
        # Exact targets, before/after hashes, backups, game path and process gate still required.
        rollback_pair(manifest,rows,game,compare.ensure_closed)
        print('ROLLED_BACK: exact two-file source state restored. '+str(manifest))
        return
    report_path=compare.ARCHIVE/'completionist-v104-native-raven-no-render-comparison.json'
    report=compare.read_json(report_path)
    check(report['ab_control']['eligible'] is True, 'Comparison did not qualify this A/B.')
    check(report['safety']['inventory_unchanged_during_analysis'] is True,'Comparison source state not stable.')
    patches=report['patch_files']
    check(len(patches)==2 and all(p.get('exists') for p in patches), 'Active artwork patch pair missing from report.')
    patch_prefix=game/'exec/patch/pc_le/completionist_v104_raven_map'
    check({Path(p['path']) for p in patches}=={Path(str(patch_prefix)+s) for s in ('.texpack','.texpack.toc')},'Unexpected artwork patch paths.')
    check({str(Path(p['path']).relative_to(game)).replace('\\','/'):p['sha256'] for p in patches}==compare.PATCH_FILES,'Artwork report differs from pinned patch pair.')
    for old_state in ('v0.10.3-native-raven-dcb','v0.10.3-native-runtime','v0.10.4-packed-raven-runtime','v0.10.4-packed-raven-hud-art-runtime'):
        check(not (compare.REPO/'build'/old_state/'active.json').exists(), f'Conflicting active manifest: {old_state}; reconcile, do not delete.')
    route_manifest=compare.read_json(compare.REPO/'build/v0.10.4-raven-native-route-reproof/active.json')
    check(route_manifest['map_after_sha256'].lower()==compare.LIVE['mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'], 'Route manifest no longer matches pinned Lua.')
    preserved={k:v for k,v in compare.LIVE.items() if k not in ('exec/dc/pc_le/mapcoords.dcb','exec/dc/pc_le/compassgraph.dcb')}
    def guard():
        compare.ensure_closed()
        for path,expected in preserved.items(): require_hash(game/path,expected)
        for p in patches: require_hash(p['path'],p['sha256'])
    guard()
    validate_rows(rows,game)
    for row in rows.values():
        require_hash(row['source'],row['after'])
        require_hash(row['target'],row['before'])
    if args.mode=='check':
        print('AB_CHECK_PASSED_NOT_INSTALLED: exact sources, candidates, artwork, Lua, branch and closed-game gates passed.')
        return
    manifest=install_pair(rows,STATE,game,guard)
    print('AB_INSTALLED: mapcoords.dcb + compassgraph.dcb only. Game not launched.')
    print('Rollback: py -3 tools/v0.10.4/native-raven-data-ab.py --mode rollback --manifest "'+str(manifest)+'"')


if __name__=='__main__':
    main()
