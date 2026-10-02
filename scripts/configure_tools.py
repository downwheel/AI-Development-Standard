"""Plan/apply standard MCP and design-skill setup without changing credentials."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from package_lib import ROOT, load_package, no_links, sha
from install_codex import atomic


def run(command, env=None, timeout=30):
    result = subprocess.run(command, env=env, cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=timeout,
                            creationflags=0x08000000 if os.name == 'nt' else 0)
    if result.returncode:
        # CLI output can contain personal configuration or expanded credentials.
        raise RuntimeError('Command failed (output withheld): ' + Path(command[0]).name)
    return result.stdout


def codex_servers(binary, home):
    rows = json.loads(run([binary, 'mcp', 'list', '--json'], dict(os.environ, CODEX_HOME=str(home))))
    return {row['name']: row for row in rows}


def claude_config_path(home):
    default = Path.home() / '.claude'
    if home == default.resolve() and not os.environ.get('CLAUDE_CONFIG_DIR'):
        return Path.home() / '.claude.json'
    return home / '.claude.json'


def toml_additions(servers):
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    lines = []
    for name, server in servers.items():
        lines += ['', '[mcp_servers.' + quote(name) + ']']
        if server['type'] == 'http':
            lines += ['url = ' + quote(server['url'])]
            if name == 'github':
                lines += ['bearer_token_env_var = "GITHUB_PAT_TOKEN"']
        else:
            lines += ['command = ' + quote(server['command']),
                      'args = ' + quote(server['args'])]
            if server.get('env'):
                lines += ['[mcp_servers.' + quote(name) + '.env]']
                lines += [quote(k) + ' = ' + quote(v) for k, v in server['env'].items()]
    return '\n'.join(lines) + '\n'


def existing_status(name, current, host):
    transport = current.get('transport', {}) if host == 'codex' else current
    if current.get('enabled') is False:
        return 'existing_disabled'
    url = transport.get('url', '').rstrip('/')
    expected_urls = {'figma': {'https://mcp.figma.com/mcp'},
                     'context7': {'https://mcp.context7.com/mcp', 'https://mcp.context7.com/mcp/oauth'},
                     'github': {'https://api.githubcopilot.com/mcp'}}
    if url in expected_urls.get(name, set()):
        return 'existing_configuration_preserved'
    packages = {'context7': '@upstash/context7-mcp', 'playwright': '@playwright/mcp'}
    args = ' '.join(transport.get('args') or [])
    if name in packages and packages[name] in args:
        return 'existing_configuration_preserved'
    return 'existing_configuration_needs_review'


def apply_files(changes, backup_root, verify=None):
    """Back up exact bytes; reject concurrent edits and roll back unchanged writes."""
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = backup_root / stamp
    no_links(backup)
    for path, before, after in changes:
        no_links(path)
        if (path.read_bytes() if path.exists() else None) != before:
            raise RuntimeError('Configuration changed after inspection: ' + str(path))
        if path.with_name(path.name + '.team-skills-tmp').exists():
            raise ValueError('Interrupted write exists: ' + str(path))
    backup.mkdir(parents=True)
    index = []
    for number, (path, before, _) in enumerate(changes):
        filename = str(number) + '.backup'
        if before is not None:
            (backup / filename).write_bytes(before)
            if (backup / filename).read_bytes() != before:
                raise RuntimeError('Backup verification failed: ' + str(path))
        index.append({'path': str(path), 'previous_file': filename if before is not None else None})
    (backup / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    written = []
    try:
        for path, before, after in changes:
            if (path.read_bytes() if path.exists() else None) != before:
                raise RuntimeError('Configuration changed during setup: ' + str(path))
            if after is None:
                path.unlink()
            else:
                atomic(path, after)
            written.append((path, before, after))
            if (path.read_bytes() if path.exists() else None) != after:
                raise RuntimeError('Post-write verification failed: ' + str(path))
        if verify is not None:
            verify()
    except Exception as error:
        conflicts = []
        for path, before, after in reversed(written):
            if (path.read_bytes() if path.exists() else None) != after:
                conflicts.append(str(path))
            elif before is None:
                path.unlink()
            else:
                atomic(path, before)
        raise RuntimeError('Setup failed; restored unchanged writes. Backup: ' + str(backup)
                           + '; conflicts: ' + str(conflicts)) from error
    return str(backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=['codex', 'claude'], required=True)
    parser.add_argument('--home', type=Path, help='Absolute target profile directory')
    parser.add_argument('--codex-bin', help='Needed for Codex configuration inspection')
    parser.add_argument('--node-bin', help='Node.js 20.18.1+ executable')
    parser.add_argument('--npx-cli', type=Path, help='npm/bin/npx-cli.js paired with Node')
    parser.add_argument('--provided', action='append', default=[], choices=['figma', 'context7', 'github', 'playwright', 'awesome-design'],
                        help='Only when this capability was observed in an enabled host plugin or inspected existing provider; recheck on updates')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--prepare-runtime', action='store_true', help='With --apply, download pinned stdio packages and run --help')
    args = parser.parse_args()
    if args.prepare_runtime and not args.apply:
        parser.error('--prepare-runtime requires --apply')
    manifest = load_package()
    env_name = 'CODEX_HOME' if args.host == 'codex' else 'CLAUDE_CONFIG_DIR'
    requested = (args.home or Path(os.environ.get(env_name, Path.home() / ('.' + args.host)))).expanduser()
    if not requested.is_absolute():
        parser.error('--home must be absolute')
    no_links(requested)
    home = requested.resolve()
    config_path = home / 'config.toml' if args.host == 'codex' else claude_config_path(home)
    for path in [config_path, home / 'team-skills.json', home / 'team-tools-receipt.json']:
        no_links(path)
    profile = json.loads((home / 'team-skills.json').read_text(encoding='utf-8'))
    if profile.get('edition') != args.host:
        raise ValueError('Install this host edition before configuring tools')
    workspace = Path(profile['workspace_root'])
    no_links(workspace)
    if not workspace.is_absolute() or any(workspace == p or p in workspace.parents or workspace in p.parents for p in [ROOT, home]):
        raise ValueError('Workspace must be separate from the package and profile')
    before = config_path.read_bytes() if config_path.exists() else None
    if args.host == 'codex':
        binary = args.codex_bin or shutil.which('codex')
        if not binary:
            raise ValueError('Codex CLI required; supply --codex-bin')
        existing = codex_servers(binary, home)
        config = None
    else:
        config = json.loads(before.decode('utf-8-sig')) if before else {}
        existing = config.get('mcpServers', {})
        if not isinstance(existing, dict):
            raise ValueError('Invalid user MCP configuration')
    defaults = json.loads((ROOT / 'integrations/default-tools.json').read_text(encoding='utf-8'))['tools']
    node = args.node_bin or shutil.which('node')
    npx = args.npx_cli
    if node:
        node = str(Path(node).resolve())
        version = run([node, '--version']).strip().lstrip('v')
        if tuple(int(x) for x in version.split('.')[:3]) < (20, 18, 1):
            node = None
        elif npx is None:
            candidates = [Path(node).parent / 'node_modules/npm/bin/npx-cli.js',
                          Path(node).parent.parent / 'lib/node_modules/npm/bin/npx-cli.js']
            npx = next((p for p in candidates if p.is_file()), None)
    if npx is not None and (not npx.is_absolute() or not npx.is_file()):
        raise ValueError('--npx-cli must identify an existing absolute npx-cli.js')
    cache = workspace / 'results/tool-runtime/npm-cache'
    output = workspace / 'results/browser'
    desired = {}
    status = {}
    for name in ['figma', 'context7', 'github', 'playwright']:
        if name in existing:
            status[name] = existing_status(name, existing[name], args.host)
            if status[name] == 'existing_configuration_needs_review' and name in args.provided:
                status[name] = 'existing_provider_reused_runtime_not_checked'
            continue
        if name in args.provided:
            status[name] = 'provided_by_host_plugin_unverified'
            continue
        spec = defaults[name]
        if spec['transport'] == 'http':
            server = {'type': 'http', 'url': spec['url']}
            if name == 'github':
                server['headers'] = {'Authorization': 'Bearer ${GITHUB_PAT_TOKEN}'}
        elif node and npx:
            extra = (['--isolated', '--headless', '--browser', spec['browser_windows' if os.name == 'nt' else 'browser_other'],
                      '--output-dir', str(output)] if name == 'playwright' else [])
            server = {'type': 'stdio', 'command': node, 'args': [str(npx), '--yes', spec['package'], *extra],
                      'env': {'npm_config_cache': str(cache)}}
        else:
            status[name] = 'pending_node_or_npx'
            continue
        desired[name] = server
        status[name] = 'configuration_added' if args.apply else 'configuration_planned'
    changes = []
    if desired:
        if args.host == 'codex':
            text = (before or b'').decode('utf-8-sig')
            if re.search(r'''(?m)^\s*(?:mcp_servers|"mcp_servers"|'mcp_servers')\s*=''', text):
                raise ValueError('Inline mcp_servers needs manual conversion to TOML tables; configuration unchanged')
            after = (before or b'') + toml_additions(desired).encode('utf-8')
        else:
            config['mcpServers'] = {**existing, **desired}
            after = (json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        changes.append((config_path, before, after))
    receipt_path = home / 'team-tools-receipt.json'
    receipt_before = receipt_path.read_bytes() if receipt_path.exists() else None
    prior = json.loads(receipt_before) if receipt_before else {}
    installed = dict(prior.get('design_files', {}))
    if 'awesome-design' in args.provided:
        status['awesome-design'] = 'provided_by_host_plugin_unverified'
    else:
        source = ROOT / 'integrations/awesome-design-md'
        target = home / 'skills/awesome-design-md'
        no_links(target)
        installed = {}
        for src in source.rglob('*'):
            if not src.is_file():
                continue
            dest = target / src.relative_to(source)
            no_links(dest)
            rel = dest.relative_to(home).as_posix()
            raw = dest.read_bytes() if dest.exists() else None
            new = src.read_bytes()
            installed[rel] = sha(new)
            if raw is not None and raw != new and prior.get('design_files', {}).get(rel) != sha(raw):
                raise ValueError('Locally edited/unowned design skill: ' + str(dest))
            if raw != new:
                changes.append((dest, raw, new))
        if target.exists():
            for file in target.rglob('*'):
                no_links(file)
                if file.is_file() and file.relative_to(home).as_posix() not in installed:
                    raw = file.read_bytes()
                    rel = file.relative_to(home).as_posix()
                    if prior.get('design_files', {}).get(rel) != sha(raw):
                        raise ValueError('Extra or locally edited design file needs review: ' + str(file))
                    changes.append((file, raw, None))
        status['awesome-design'] = 'skill_installed' if args.apply else 'skill_planned'
    receipt = {'schema_version': 1, 'edition': args.host, 'package_version': manifest['version'],
               'design_files': installed, 'configured_server_names': sorted(set(prior.get('configured_server_names', [])) | set(desired))}
    encoded = (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if encoded != receipt_before:
        changes.append((receipt_path, receipt_before, encoded))
    report = {'mode': 'apply' if args.apply else 'plan', 'host': args.host, 'configuration': str(config_path),
              'changed_files': len(changes), 'tools': status, 'runtime': {},
              'authentication': {'figma': 'verify_or_complete_oauth_in_host',
                                 'github': ('verify_existing_host_provider' if 'github' in args.provided and 'github' not in desired
                                            else 'environment_variable_present_not_verified' if os.environ.get('GITHUB_PAT_TOKEN') else 'pending_GITHUB_PAT_TOKEN')},
              'live_connections': 'not_checked'}
    if args.apply:
        def verify_config():
            if args.host == 'codex':
                active = codex_servers(binary, home)
                if not set(desired).issubset(active):
                    raise RuntimeError('Codex did not recognize the added configuration')
        if changes:
            report['backup'] = apply_files(changes, home / 'team-tools-backups', verify_config)
        if args.prepare_runtime:
            # Only execute new/owned commands with the exact standard package, never arbitrary existing commands.
            active = codex_servers(binary, home) if args.host == 'codex' else json.loads(config_path.read_text(encoding='utf-8')).get('mcpServers', {})
            for name in ['context7', 'playwright']:
                record = active.get(name, {})
                server = record.get('transport', {}) if args.host == 'codex' else record
                package = defaults[name]['package']
                command_args = server.get('args') or []
                if not node or not npx or server.get('command') != node or command_args[:3] != [str(npx), '--yes', package]:
                    report['runtime'][name] = 'existing_provider_preserved_or_prerequisite_pending'
                    continue
                no_links(cache)
                no_links(output)
                output.mkdir(parents=True, exist_ok=True)
                try:
                    run([node, str(npx), '--yes', package, '--help'],
                        dict(os.environ, npm_config_cache=str(cache)), timeout=180)
                    report['runtime'][name] = 'package_prepared_browser_and_auth_not_checked'
                except (RuntimeError, subprocess.TimeoutExpired):
                    report['runtime'][name] = 'preparation_failed_retry_after_network_check'
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.apply and (any(value.startswith('pending_') or value.endswith('needs_review') or value == 'existing_disabled' for value in status.values())
                       or any(value.startswith('preparation_failed') for value in report['runtime'].values())):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
