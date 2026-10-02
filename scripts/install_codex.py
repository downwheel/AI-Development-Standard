"""Install a reviewed host edition; no external services or Git mutations."""
from pathlib import Path, PurePosixPath
import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from package_lib import ROOT, is_office_lock, legacy_findings, load_package, no_links, sha, valid_name

START = '<!-- team-skills:managed:start -->'
END = '<!-- team-skills:managed:end -->'

def check_profile_path(home, path):
    path.relative_to(home)
    path.resolve().relative_to(home)
    for candidate in [path, *path.parents]:
        if candidate == home:
            break
        if candidate.is_symlink() or (candidate.exists() and getattr(candidate.lstat(), 'st_file_attributes', 0) & 1024):
            raise ValueError('Profile path contains a link: ' + str(candidate))

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.team-skills-tmp')
    with temporary.open('xb') as out: out.write(data)
    os.replace(temporary, path)

def profile_block(original, replacement):
    # Recognize the prior managed block without retaining its former branding.
    starts=list(re.finditer(r'<!-- ([a-z0-9-]*team-skills):managed:start -->', original))
    ends=list(re.finditer(r'<!-- ([a-z0-9-]*team-skills):managed:end -->', original))
    if len(starts)!=len(ends) or len(starts)>1:
        raise ValueError('Ambiguous managed block; preserve and review AGENTS.md')
    if starts:
        if starts[0].group(1)!=ends[0].group(1) or starts[0].start()>=ends[0].start():
            raise ValueError('Ambiguous managed block; preserve and review AGENTS.md')
        a=starts[0].start(); b=ends[0].end()
        return original[:a]+replacement.rstrip()+original[b:]
    return original + ('\n\n' if original and not original.endswith('\n\n') else '') + replacement.rstrip() + '\n'

def obsolete_skills(home, owned, names):
    prior_names=set()
    for rel in owned:
        path=PurePosixPath(rel)
        if ('\\' in rel or path.is_absolute() or '..' in path.parts
                or len(path.parts)<3 or path.parts[0]!='skills' or not valid_name(path.parts[1])):
            raise ValueError('Invalid owned Skill path: '+rel)
        prior_names.add(path.parts[1])
    retired=[]
    for name in sorted(prior_names-set(names)):
        dest=home/'skills'/name
        check_profile_path(home,dest)
        if not dest.exists():continue
        for path in dest.rglob('*'):
            check_profile_path(home,path)
            if path.is_file():
                rel=path.relative_to(home).as_posix()
                if owned.get(rel)!=sha(path.read_bytes()):
                    raise ValueError('Unowned or locally edited retired Skill file: '+str(path))
        retired.append(dest)
    return retired

def main(edition='codex'):
    harness_name='AGENTS.md' if edition=='codex' else 'CLAUDE.md'
    env_name='CODEX_HOME' if edition=='codex' else 'CLAUDE_CONFIG_DIR'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--'+edition+'-home', dest='codex_home', type=Path, default=Path(os.environ.get(env_name,Path.home()/('.'+edition))))
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--apply', action='store_true', help='Apply the displayed local plan; default is read-only')
    args=parser.parse_args()
    if not args.codex_home.expanduser().is_absolute():
        parser.error('--' + edition + '-home must be an absolute path')
    no_links(args.codex_home.expanduser())
    home=args.codex_home.expanduser().resolve()
    if home==ROOT or ROOT in home.parents or home in ROOT.parents:
        raise ValueError('Host profile and distribution must not overlap')
    manifest=load_package()
    names=manifest['skill_names']
    source_root=ROOT/'skills'/edition
    for name in [harness_name,'config.toml']:
        check_profile_path(home,home/name)
    legacy=legacy_findings(home,edition)
    if legacy:
        raise ValueError('Legacy standard still present; follow docs/MIGRATION.md before installation: '+', '.join(legacy))
    observed={}
    def observe(path):
        check_profile_path(home,path)
        if path not in observed:
            observed[path]=path.read_bytes() if path.exists() else None
        return observed[path]
    receipt_path=home/'team-skills-receipt.json'
    receipt_before=observe(receipt_path)
    prior=json.loads(receipt_before) if receipt_before is not None else {}
    owned=prior.get('installed_files',{})
    retired=obsolete_skills(home,owned,names)
    config_path=home/'team-skills.json'
    config_before=observe(config_path)
    previous_config=json.loads(config_before) if config_before is not None else {}
    requested_workspace=(args.workspace_root or Path(previous_config.get('workspace_root',Path.home()/'AI-Workspace'))).expanduser()
    if not requested_workspace.is_absolute():
        raise ValueError('Workspace must be an absolute path')
    no_links(requested_workspace)
    workspace=requested_workspace.resolve()
    if any(workspace==p or p in workspace.parents or workspace in p.parents for p in [ROOT,home]):
        raise ValueError('Workspace must be separate from the distribution and Host profile')
    if workspace.exists() and not workspace.is_dir():
        raise ValueError('Workspace is not a directory')
    files={}; changed=[];retired_files=[]
    for name in names:
        dest=home/'skills'/name
        check_profile_path(home, dest)
        if dest.exists() and (dest.is_symlink() or getattr(dest.lstat(),'st_file_attributes',0)&1024):
            raise ValueError('Existing Skill is linked: '+name)
        expected=[]
        for src in (source_root/name).rglob('*'):
            if not src.is_file() or is_office_lock(src):continue
            target=dest/src.relative_to(source_root/name)
            check_profile_path(home, target)
            rel=target.relative_to(home).as_posix(); data=src.read_bytes(); files[rel]=sha(data); expected.append(target)
            current_bytes=observe(target)
            if current_bytes is not None:
                current=sha(current_bytes)
                if current!=sha(data) and owned.get(rel)!=current:
                    raise ValueError('Unowned or locally edited Skill file: '+str(target))
            if current_bytes!=data: changed.append((target,data))
        if dest.exists():
            for p in dest.rglob('*'):check_profile_path(home,p)
            extra=[p for p in dest.rglob('*') if p.is_file() and not is_office_lock(p) and p not in expected]
            for p in extra:
                if owned.get(p.relative_to(home).as_posix())!=sha(observe(p)):
                    raise ValueError('Unowned or locally edited obsolete Skill file: '+str(p))
                retired_files.append(p)
    agents=home/harness_name
    check_profile_path(home, agents)
    agents_before=observe(agents)
    old_agents=agents_before.decode('utf-8') if agents_before is not None else ''
    if 'team-development-standard:managed:start' in old_agents:
        raise ValueError('Disconnect the backed-up legacy standard before activating team skills')
    new_agents=profile_block(old_agents,(ROOT/'adapters'/edition/harness_name).read_text(encoding='utf-8')).encode('utf-8')
    config=dict(previous_config)
    config.pop('upstream_commit',None)
    config.update({'schema_version':1,'distribution_root':str(ROOT),'edition':edition,'package_version':manifest['version'],'workspace_root':str(workspace)})
    config_bytes=(json.dumps(config,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    for p,data in [(agents,new_agents),(config_path,config_bytes)]:
        if observe(p)!=data:changed.append((p,data))
    plan={'mode':'apply' if args.apply else 'plan','edition':edition,'version':manifest['version'],'distribution_root':str(ROOT),edition+'_home':str(home),'skill_count':len(names),'changed_files':len(changed),'retired_skills':len(retired),'retired_files':len(retired_files),'workspace_root':str(workspace),'other_host_modified':False,'mcp_modified':False}
    receipt={'schema_version':1,'distribution_root':str(ROOT),'edition':edition,'package_version':manifest['version'],'package_manifest_sha256':sha((ROOT/'manifest.json').read_bytes()),'installed_files':files,'skill_count':len(names),'workspace_root':str(workspace),'last_backup':prior.get('last_backup')}
    encoded=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    receipt_changed=receipt_before!=encoded
    plan['receipt_changed']=receipt_changed
    if not args.apply:
        print(json.dumps(plan,ensure_ascii=False,indent=2));return
    backup=None
    workspace.mkdir(parents=True,exist_ok=True)
    if changed or retired or retired_files or receipt_changed:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup=home/'team-skills-backups'/stamp
        check_profile_path(home, backup)
        receipt['last_backup']=str(backup)
        encoded=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        changes=[*changed,(receipt_path,encoded)]
        before={p:observed[p] for p,_ in changes}
        for p,raw in observed.items():
            if (p.read_bytes() if p.exists() else None)!=raw:
                raise RuntimeError('Profile changed after inspection; installation was not applied: '+str(p))
        for p,_ in changes:
            temporary=p.with_name(p.name+'.team-skills-tmp')
            check_profile_path(home,temporary)
            if temporary.exists():raise ValueError('Interrupted temporary write; preserve and review: '+str(temporary))
        backup.mkdir(parents=True)
        for p,raw in before.items():
            if raw is not None:
                dest=backup/p.relative_to(home);dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(raw)
                if dest.read_bytes()!=raw:raise RuntimeError('Backup verification failed: '+str(dest))
        applied=[];moved=[]
        try:
            for p,data in changes:
                current=p.read_bytes() if p.exists() else None
                if current!=before[p]:raise RuntimeError('Profile changed during installation: '+str(p))
                atomic(p,data);applied.append((p,data))
            for rel,h in files.items():
                if sha((home/rel).read_bytes())!=h:raise RuntimeError('Post-install mismatch: '+rel)
            # Recheck ownership immediately before moving obsolete names to backup.
            if obsolete_skills(home,owned,names)!=retired:raise RuntimeError('Retired skills changed during installation')
            for path in [*retired_files,*retired]:
                target=backup/path.relative_to(home)
                check_profile_path(home,path);check_profile_path(home,target)
                if path in retired_files and path.read_bytes()!=observed[path]:
                    raise RuntimeError('Obsolete file changed during installation: '+str(path))
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.move(str(path),str(target));moved.append((path,target))
        except Exception as error:
            conflicts=[]
            for path,target in reversed(moved):
                if path.exists():conflicts.append(str(path))
                else:shutil.move(str(target),str(path))
            for p,data in reversed(applied):
                if not p.is_file() or p.read_bytes()!=data:
                    conflicts.append(str(p));continue
                if before[p] is None:p.unlink()
                else:atomic(p,before[p])
            raise RuntimeError('Installation failed; original files restored where unchanged. Backup: '+str(backup)+'; conflicts: '+str(conflicts)) from error
    print(json.dumps({**plan,'verified_files':len(files),'receipt':str(receipt_path)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
