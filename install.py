#!/usr/bin/env python3
"""Versioned local installer. Team Git and external accounts are never configured."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
sys.dont_write_bytecode=True
from harness.common import encoded, fail, HarnessError, overlap, sha256, scan_secrets
from harness.registry import atomic_json, normal_root

SOURCE=Path(__file__).resolve().parent
START=b'<!-- team-development-standard:managed:start -->'
END=b'<!-- team-development-standard:managed:end -->'
OLD_START=b'<!-- development-workflow:managed:start -->'
OLD_END=b'<!-- development-workflow:managed:end -->'

def source_manifest():
    from harness.history import _no_links
    _no_links(SOURCE)
    files=[]
    for p in sorted(SOURCE.rglob('*')):
        if not p.is_file() or any(part in {'.git','__pycache__','.venv','test-results'} for part in p.relative_to(SOURCE).parts) or p.suffix in {'.pyc','.pyo'} or p.name=='release-manifest.json': continue
        _no_links(p)
        if SOURCE.resolve() not in p.resolve().parents: fail('package_path_escape','Package content must remain inside the shared source.')
        if p.name=='.env' or (p.name.startswith('.env.') and p.name not in {'.env.example','.env.template'}) or p.suffix.lower() in {'.pem','.pfx','.p12','.key'}:
            fail('secret_path','Private credential paths cannot be packaged.')
        raw=scan_secrets(p.read_bytes())
        files.append({'path':p.relative_to(SOURCE).as_posix(),'sha256':sha256(raw),'bytes':len(raw)})
    digest=sha256(encoded(files))
    return {'schema_version':1,'version':'2.0.0','release_id':'2.0.0-'+digest[:16],'content_sha256':digest,'files':files}

def managed_block(raw, replacement):
    for start,end in [(START,END),(OLD_START,OLD_END)]:
        if start in raw:
            if raw.count(start)!=1 or raw.count(end)!=1: fail('managed_block_conflict','Managed routing markers are ambiguous.')
            a=raw.index(start); b=raw.index(end,a)+len(end)
            return raw[:a]+replacement+raw[b:]
    return raw+(b'\n\n' if raw else b'')+replacement+b'\n'

def assignment_end(text,start):
    """Find a TOML value boundary without treating quoted brackets as syntax."""
    quote=None; triple=False; depth=0; index=start
    while index<len(text):
        char=text[index]
        if quote:
            if quote=='"' and char=='\\': index+=2; continue
            ending=quote*3 if triple else quote
            if text.startswith(ending,index): quote=None; index+=len(ending); continue
        elif char in {'"',"'"}:
            quote=char; triple=text.startswith(char*3,index)
            index+=3 if triple else 1; continue
        elif char=='#':
            newline=text.find('\n',index)
            if newline<0: return len(text)
            if depth==0: return newline
            index=newline
        elif char in '[{': depth+=1
        elif char in ']}': depth-=1
        elif char=='\n' and depth==0: return index
        index+=1
    if quote or depth: fail('config_conflict','Unterminated MCP configuration value.')
    return len(text)


def table_expression(name):
    root=r'(?:mcp_servers|"mcp_servers"|\'mcp_servers\')'
    key=r'(?:'+re.escape(name)+r'|"'+re.escape(name)+r'"|\''+re.escape(name)+r'\')'
    return r'(?m)^\[[ \t]*'+root+r'[ \t]*\.[ \t]*'+key+r'[ \t]*\][ \t]*(?:#.*)?(?:\r?\n|$)'


def update_toml_table(raw,name,values,replace_table=False):
    text=raw.decode('utf-8-sig')
    expression=table_expression(name)
    matches=list(re.finditer(expression,text))
    if len(matches)>1: fail('config_conflict','Duplicate MCP table.')
    if not matches:
        block='\n\n[mcp_servers.'+name+']\n'+''.join(k+' = '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in values.items())
        return raw+block.encode('utf-8')
    match=matches[0]
    next_header=re.search(r'(?m)^\[[ \t]*[A-Za-z_"\']',text[match.end():])
    end=match.end()+next_header.start() if next_header else len(text)
    body=text[match.end():end]
    for key,value in values.items():
        pattern=r'(?m)^'+re.escape(key)+r'[ \t]*='
        line=key+' = '+json.dumps(value,ensure_ascii=False)
        assignments=list(re.finditer(pattern,body))
        if len(assignments)>1: fail('config_conflict','Duplicate managed MCP setting.')
        if assignments:
            item=assignments[0]
            end_value=assignment_end(body,item.end())
            body=body[:item.start()]+line+body[end_value:]
        else: body=body.rstrip()+'\n'+line+'\n'
    return (text[:match.end()]+body+text[end:]).encode('utf-8')

def routing():
    return (START+b'\n'+'''## 단계별 개발 표준

새 개발 작업은 development-workflow 길잡이 또는 사용자가 지정한 dev-* Skill로 진행한다. 일반 질문·조회·사소한 수정에 전체 승인 절차를 강제하지 않는다.

- 조사·요구·시스템 설계 → 실제 사용자 Gate A → 단위 설계·검사 계획 → 실제 사용자 Gate B → 구현·검증 순서다. 개별 Skill 재호출은 그 단계만 수행한다.
- team_harness MCP의 실제 version/schema를 확인한다. v2가 현재 세션에 없으면 설치 Skill의 scripts/harness.py CLI로 같은 개인 기록을 사용한다. 구 v1 development_workflow 도구로 새 기록을 만들지 않는다.
- 다음 단계는 정확한 artifact_id/revision_id/sha256를 참조한다. 자료 조회는 생성·승인·구현을 하지 않는다. 재작업은 새 revision으로 보존하며 필요한 범위만 재검토한다.
- 제품 Git branch/index/refs/config를 기록 수단으로 조작하지 않는다. 사용자가 환경 구성에서 허용한 별도 개인 journal Git의 내부 기록만 자동 저장한다. 팀 원격·제품 commit/push 권한으로 확대하지 않는다.
- 실제 편집 전 begin_implementation으로 승인·lease·baseline을 확보하고 편집 후 finish_implementation으로 실제 변경을 기록한다. run_checks의 실제 검사 근거 없이 검증 완료로 표시하지 않는다.
- Figma·Context7·DB·Playwright는 필요한 단계에서 실제 노출·권한·출처를 확인한다. 특정 예제의 기능·DB·기술 구성을 다른 프로젝트에 자동 적용하지 않는다.
- 운영 배포·운영 데이터 변경·외부 발송은 개발 Gate와 별도다. 복원은 개인 기록의 검증된 사본과 구체적 계획 승인을 사용한다.
- 이 도구는 협조적 절차 장치이며 동일 OS 계정의 다른 도구를 차단하거나 승인자 신원을 인증하지 않는다.
'''.encode('utf-8')+END)

LAUNCHER='''"""Generated host-local launcher. Common Skill source contains no personal paths."""
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
settings=Path(__file__).resolve().parents[1]/"runtime.json"
if not settings.is_file():
    raise SystemExit("Team Harness is not installed for this host Skill.")
runtime=json.loads(settings.read_text(encoding="utf-8"))
command=[runtime["python"],"-B","-X","utf8",runtime["entrypoint"],"--state-root",runtime["state_root"],"--standard-root",runtime["source_root"],*sys.argv[1:]]
raise SystemExit(subprocess.call(command))
'''

def build_plan(profile,state_root,python_path):
    from harness.history import _no_links
    profile=Path(profile).absolute(); state_root=Path(state_root).absolute()
    _no_links(profile); _no_links(state_root)
    profile=profile.resolve(); state_root=state_root.resolve()
    if overlap(state_root,SOURCE): fail('overlapping_roots','Shared source and personal state must not overlap.')
    for path in [profile,state_root,SOURCE,profile/'.codex',profile/'.claude',profile/'.claude.json']:
        _no_links(path)
    manifest=source_manifest(); release=state_root/'releases'/manifest['release_id']
    runtime={'schema_version':1,'python':str(Path(python_path).resolve()),'entrypoint':str(release/'team_harness.py'),'state_root':str(state_root),'standard_release':manifest['release_id'],'source_root':str(SOURCE)}
    writes=[]
    def add(path,raw,kind):
        path=Path(path)
        _no_links(path)
        original=path.read_bytes() if path.is_file() else None
        if original!=raw:
            writes.append({'path':str(path),'before_sha256':sha256(original) if original is not None else None,'after_sha256':sha256(raw),'content':raw,'kind':kind})
    # Only the immutable installed copy receives a manifest. A mutable team
    # checkout remains working-source, so editing and testing it cannot inherit
    # the identity of an older installed release.
    for row in manifest['files']:
        target=release/row['path']
        _no_links(target)
        if target.exists() and sha256(target.read_bytes())!=row['sha256']: fail('release_modified','An existing immutable release was modified.')
        source_path=SOURCE/row['path']; _no_links(source_path)
        raw=source_path.read_bytes()
        if sha256(raw)!=row['sha256']: fail('package_changed','Shared source changed during package preparation; retry after edits finish.')
        add(target,raw,'release')
    add(release/'release-manifest.json',encoded(manifest),'release')
    metadata_file=SOURCE/'adapters/codex/skill-metadata.json'
    metadata=json.loads(metadata_file.read_text(encoding='utf-8'))['skills'] if metadata_file.is_file() else {}
    names=sorted(p.name for p in (SOURCE/'skills').iterdir() if p.is_dir() and (p/'SKILL.md').is_file())
    if len(names)!=11: fail('incomplete_package','Expected 11 completed common Skills.')
    for host in ['.codex','.claude']:
        for name in names:
            src=SOURCE/'skills'/name; dest=profile/host/'skills'/name
            existing=dest/'SKILL.md'
            if existing.exists() and not (dest/'runtime.json').exists() and name!='development-workflow':
                fail('skill_conflict','An unmanaged Skill already occupies '+name)
            for p in src.rglob('*'):
                if p.is_file(): add(dest/p.relative_to(src),p.read_bytes(),'host-skill')
            add(dest/'runtime.json',encoded(runtime),'host-runtime')
            add(dest/'scripts/harness.py',LAUNCHER.encode('utf-8'),'host-launcher')
            if host=='.codex' and name in metadata:
                interface=metadata[name]['interface']
                yaml='interface:\n'+''.join('  '+k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in interface.items())
                old=(dest/'agents/openai.yaml').read_text(encoding='utf-8') if (dest/'agents/openai.yaml').is_file() else ''
                remainder=re.sub(r'(?ms)^interface:\s*\n.*?(?=^[^ \t\r\n#]|\Z)','',old)
                add(dest/'agents/openai.yaml',(yaml+remainder).encode('utf-8'),'host-metadata')
    for target in [profile/'.codex/AGENTS.md',profile/'.claude/CLAUDE.md']:
        original=target.read_bytes() if target.is_file() else b''
        add(target,managed_block(original,routing()),'host-routing')
    command=[runtime['python'],'-B','-X','utf8',runtime['entrypoint'],'--state-root',runtime['state_root'],'--standard-root',runtime['source_root'],'serve']
    config=profile/'.codex/config.toml'
    original=config.read_bytes() if config.is_file() else b''
    updated=update_toml_table(original,'team_harness',{'command':command[0],'args':command[1:],'startup_timeout_sec':20,'tool_timeout_sec':1000,'enabled':True})
    if re.search(table_expression('development_workflow'),original.decode('utf-8-sig')):
        updated=update_toml_table(updated,'development_workflow',{'enabled':False})
    add(config,updated,'codex-config')
    claude_config=profile/'.claude.json'
    claude=json.loads(claude_config.read_text(encoding='utf-8-sig')) if claude_config.is_file() else {}
    previous=claude.setdefault('mcpServers',{}).get('team_harness',{})
    claude['mcpServers']['team_harness']={**previous,'type':'stdio','command':command[0],'args':command[1:]}
    add(claude_config,(json.dumps(claude,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),'claude-config')
    settings_path=state_root/'settings.json'; _no_links(settings_path)
    settings=json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.is_file() else {}
    for key,value in {'history_enabled':True,'history_remote':None,'automatic_prune':False,'accounts':'deferred','team_git':'deferred'}.items(): settings.setdefault(key,value)
    settings.update({'schema_version':1,'active_release':str(release),'standard_source_root':str(SOURCE),'python':runtime['python']})
    add(settings_path,encoded(settings),'personal-settings')
    return {'manifest':manifest,'runtime':runtime,'skill_names':names,'writes':writes}

def protect_private_directory(path):
    path=Path(path)
    from harness.history import _no_links
    _no_links(path)
    path.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        identity=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True)
        sid=next(csv.reader(identity.stdout.strip().splitlines()))[1]
        if not re.fullmatch(r'S-1-[0-9-]+',sid): fail('private_acl','Unable to resolve the current account SID.')
        result=subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],capture_output=True)
        if result.returncode: fail('private_acl','Unable to restrict the personal record directory to the current account and SYSTEM.')
    else:
        path.chmod(0o700)


def install(profile,state_root,python_path):
    plan=build_plan(profile,state_root,python_path)
    state_root=Path(state_root).resolve()
    protect_private_directory(state_root)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=state_root/'installation-backups'/stamp
    backup.mkdir(parents=True,exist_ok=False)
    receipt={'schema_version':1,'installed_at':stamp,'release_id':plan['manifest']['release_id'],'source_root':str(SOURCE),'state_root':str(state_root),
             'profile':str(Path(profile).resolve()),'runtime':plan['runtime'],'skills':plan['skill_names'],'files':[],'status':'prepared','accounts':'deferred','team_git':'deferred'}
    for index,row in enumerate(plan['writes']):
        target=Path(row['path'])
        from harness.history import _no_links
        _no_links(target)
        # Preserve source/config edits made after the preview was assembled.
        current=sha256(target.read_bytes()) if target.is_file() else None
        if current!=row['before_sha256']: fail('installation_conflict','A target changed during installation preparation.')
        backup_file=None
        if target.is_file():
            backup_file=backup/(str(index)+'.before')
            backup_file.write_bytes(target.read_bytes())
        receipt['files'].append({k:v for k,v in row.items() if k!='content'}|{'backup_path':str(backup_file) if backup_file else None})
    atomic_json(backup/'receipt.json',receipt)
    # Store exact recovery metadata before changing the first managed target.
    for row in plan['writes']:
        target=Path(row['path']); target.parent.mkdir(parents=True,exist_ok=True)
        from harness.history import _no_links
        _no_links(target)
        current=sha256(target.read_bytes()) if target.is_file() else None
        if current!=row['before_sha256']:
            fail('installation_conflict','A target changed before applying its managed update; use the saved receipt to reconcile.')
        fd,temp=tempfile.mkstemp(prefix='.install-',dir=target.parent)
        try:
            with os.fdopen(fd,'wb') as f: f.write(row['content']); f.flush(); os.fsync(f.fileno())
            os.replace(temp,target)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    receipt['status']='installed'
    atomic_json(backup/'receipt.json',receipt)
    atomic_json(state_root/'installation.json',receipt)
    return {'release_id':receipt['release_id'],'source_root':str(SOURCE),'state_root':str(state_root),'skill_count_per_host':len(receipt['skills']),'managed_files_changed':len(receipt['files']),'receipt':str(backup/'receipt.json'),'accounts':'deferred','team_git':'deferred'}

def rollback(receipt_path,apply=False,profile=None,state_root=None):
    from harness.history import _no_links
    profile=Path(profile or Path.home()).absolute()
    state_root=Path(state_root or Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'TeamDevelopment').absolute()
    _no_links(profile); _no_links(state_root)
    profile=profile.resolve(); state_root=state_root.resolve()
    expected_backup=state_root/'installation-backups'
    _no_links(Path(receipt_path))
    receipt_path=Path(receipt_path).resolve()
    if expected_backup not in receipt_path.parents: fail('rollback_scope','Receipt must be in the selected personal installation backup directory.')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    if Path(receipt['profile']).resolve()!=profile or Path(receipt['state_root']).resolve()!=state_root or Path(receipt['source_root']).resolve()!=SOURCE:
        fail('rollback_scope','Receipt does not belong to the selected profile, state root, and standard source.')
    changes=[]; conflicts=[]
    for row in receipt['files']:
        if row['kind']=='release': continue
        path=Path(row['path'])
        _no_links(path)
        allowed_files={profile/'.codex/config.toml',profile/'.codex/AGENTS.md',profile/'.claude.json',profile/'.claude/CLAUDE.md',SOURCE/'release-manifest.json',state_root/'settings.json'}
        allowed_skill=any(base in path.resolve().parents for base in [profile/'.codex/skills',profile/'.claude/skills'])
        if path.resolve() not in allowed_files and not allowed_skill: fail('rollback_scope','Receipt contains a target outside managed settings and Skill paths.')
        current=sha256(path.read_bytes()) if path.is_file() else None
        if row['backup_path']:
            backup_path=Path(row['backup_path']).resolve()
            _no_links(backup_path)
            if backup_path.parent!=receipt_path.parent: fail('rollback_scope','Backup file must be next to its installation receipt.')
        if current==row['before_sha256']: continue
        if current!=row['after_sha256']: conflicts.append(str(path)); continue
        if row['backup_path'] and sha256(Path(row['backup_path']).read_bytes())!=row['before_sha256']:
            conflicts.append(str(path)); continue
        changes.append(row)
    if apply and conflicts: fail('rollback_conflict','Managed files changed after installation; review the rollback plan.')
    if apply:
        for row in changes:
            path=Path(row['path'])
            _no_links(path)
            current=sha256(path.read_bytes()) if path.is_file() else None
            if current!=row['after_sha256']: fail('rollback_conflict','A target changed while rollback was in progress; completed restores are retained.')
            if row['backup_path']:
                backup_path=Path(row['backup_path']); _no_links(backup_path)
                raw=backup_path.read_bytes()
                if sha256(raw)!=row['before_sha256']: fail('rollback_conflict','A recovery copy changed during rollback.')
                fd,temporary=tempfile.mkstemp(prefix='.restore-install-',dir=path.parent)
                try:
                    with os.fdopen(fd,'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
                    os.replace(temporary,path)
                finally:
                    if os.path.exists(temporary): os.unlink(temporary)
            else: path.unlink()
        receipt['status']='rolled_back'
        receipt['rolled_back_at']=datetime.now(timezone.utc).isoformat()
        atomic_json(receipt_path,receipt)
        pointer=state_root/'installation.json'
        _no_links(pointer)
        if pointer.is_file() and json.loads(pointer.read_text(encoding='utf-8')).get('installed_at')==receipt['installed_at']:
            atomic_json(pointer,receipt)
    return {'mode':'applied' if apply else 'preview','changes':[r['path'] for r in changes],'conflicts':conflicts,'personal_history_retained':True,'release_retained':True}

def main():
    parser=argparse.ArgumentParser(description='Install shared Skills and Team Harness without account or Team Git setup')
    parser.add_argument('mode',choices=['plan','install','rollback'])
    parser.add_argument('--profile',default=str(Path.home()))
    parser.add_argument('--state-root',default=str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'TeamDevelopment'))
    parser.add_argument('--python',default=sys.executable)
    parser.add_argument('--receipt'); parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        if args.mode=='rollback':
            if not args.receipt: fail('missing_receipt','--receipt is required.')
            result=rollback(args.receipt,args.apply,args.profile,args.state_root)
        elif args.mode=='install': result=install(args.profile,args.state_root,args.python)
        else:
            plan=build_plan(args.profile,args.state_root,args.python)
            result={'release_id':plan['manifest']['release_id'],'runtime':plan['runtime'],'skills':plan['skill_names'],'changes':[{k:v for k,v in row.items() if k!='content'} for row in plan['writes']],'accounts':'deferred','team_git':'deferred'}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except HarnessError as exc:
        print(json.dumps({'error':exc.code,'message':str(exc)},ensure_ascii=False)); return 2
    return 0

if __name__=='__main__': raise SystemExit(main())
