"""Verify package/installed files; optionally ask the local host binary to discover skills."""
from pathlib import Path
import argparse
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from package_lib import ROOT, is_office_lock, legacy_findings, load_package, no_links, sha
from install_codex import profile_block


def native_skills(binary, home, names):
    env = dict(os.environ, CODEX_HOME=str(home))
    process = subprocess.Popen([binary, 'app-server'], cwd=ROOT, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace',
                               creationflags=0x08000000 if os.name == 'nt' else 0)
    messages = queue.Queue()

    def read_stdout():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                continue
        messages.put(None)

    def drain_stderr():
        for _ in process.stderr:
            pass

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=drain_stderr, daemon=True).start()

    def request(number, method, params):
        process.stdin.write(json.dumps({'id': number, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                item = messages.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if item is None:
                raise RuntimeError('Codex discovery process exited')
            if item.get('id') == number:
                if 'error' in item:
                    raise RuntimeError('Codex does not support the discovery request; check the app version')
                return item['result']
        raise TimeoutError('Timed out during Codex skill discovery')

    try:
        request(1, 'initialize', {'clientInfo': {'name': 'team-skills-verification', 'version': '1.0'}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        result = request(2, 'skills/list', {'cwds': [str(ROOT)], 'forceReload': True})
        groups = result.get('data', [])
        selected = []
        for group in groups:
            for skill in group.get('skills', []):
                if skill.get('name') in names and Path(skill.get('path', '')).resolve() == (home / 'skills' / skill['name'] / 'SKILL.md').resolve():
                    selected.append(skill)
        if {s['name'] for s in selected} != set(names) or len(selected) != len(names) or any(not s.get('enabled') for s in selected):
            raise RuntimeError('Codex did not discover all declared installed skills as enabled')
        return {'status': 'passed', 'discovered': len(selected), 'enabled': len(selected),
                'other_discovery_errors': sum(len(g.get('errors', [])) for g in groups), 'model_turn_started': False}
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def main(edition='codex'):
    harness_name='AGENTS.md' if edition=='codex' else 'CLAUDE.md'
    env_name='CODEX_HOME' if edition=='codex' else 'CLAUDE_CONFIG_DIR'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-only', action='store_true')
    parser.add_argument('--'+edition+'-home', dest='codex_home', type=Path, default=Path(os.environ.get(env_name, Path.home() / ('.'+edition))))
    parser.add_argument('--native', action='store_true', help='Discover host skills; may initialize caches, never starts a model turn')
    parser.add_argument('--'+edition+'-bin', dest='codex_bin', help='Host executable path if not on PATH')
    args = parser.parse_args()
    if args.package_only and args.native:
        parser.error('--native needs an installed profile')
    data = load_package()
    result = {'package': 'passed', 'version': data['version'], 'skills': len(data['skill_names']),
              'package_files': len(data['package_files']), 'installed': 'not_checked', 'native': {'status': 'not_checked'}}
    if not args.package_only:
        no_links(args.codex_home.expanduser())
        home = args.codex_home.expanduser().resolve()
        issues = legacy_findings(home,edition)
        if issues:
            raise ValueError('Legacy standard still present: ' + ', '.join(issues))
        receipt = json.loads((home / 'team-skills-receipt.json').read_text(encoding='utf-8'))
        config = json.loads((home / 'team-skills.json').read_text(encoding='utf-8'))
        expected = {}
        for row in data['files' if edition=='codex' else 'claude_files']:
            rel = 'skills/' + row['path'].removeprefix('skills/'+edition+'/')
            target = home / rel
            no_links(target)
            if not target.is_file() or sha(target.read_bytes()) != row['sha256']:
                raise ValueError('Installed skill differs from this package: ' + rel)
            expected[rel] = row['sha256']
        for name in data['skill_names']:
            for path in (home / 'skills' / name).rglob('*'):
                no_links(path)
                if path.is_file() and not is_office_lock(path) and path.relative_to(home).as_posix() not in expected:
                    raise ValueError('Unexpected installed skill file: ' + str(path))
        if receipt.get('installed_files') != expected or receipt.get('package_version') != data['version']:
            raise ValueError('Installation receipt differs from this package')
        if receipt.get('package_manifest_sha256') != sha((ROOT / 'manifest.json').read_bytes()):
            raise ValueError('Package changed since installation; run the installer after Pull')
        for current in [config, receipt]:
            if Path(current.get('distribution_root', '')).resolve() != ROOT or current.get('edition') != edition:
                raise ValueError('Installation points at another distribution')
        if config.get('package_version') != data['version'] or config.get('workspace_root') != receipt.get('workspace_root'):
            raise ValueError('Profile and receipt disagree')
        workspace = Path(config['workspace_root'])
        if not workspace.is_absolute() or not workspace.is_dir() or any(workspace == p or p in workspace.parents or workspace in p.parents for p in [ROOT, home]):
            raise ValueError('Workspace path is missing or overlaps the installation')
        agents = (home / harness_name).read_bytes().decode('utf-8')
        wanted = (ROOT / 'adapters'/edition/harness_name).read_text(encoding='utf-8')
        if profile_block(agents, wanted) != agents:
            raise ValueError('Installed managed harness block differs from this package')
        result.update(installed='passed', verified_skill_files=len(expected), workspace_root=str(workspace))
        if args.native:
            binary = args.codex_bin or shutil.which(edition)
            if not binary:
                raise ValueError(edition + ' executable not found; supply --' + edition + '-bin or verify in the app')
            probe=native_skills
            if edition=='claude':
                from verify_claude import native_skills as probe
            result['native'] = probe(binary, home, data['skill_names'])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
